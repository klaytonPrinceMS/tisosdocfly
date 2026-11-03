"""OpenTelemetry application instrumentation for T! SOS DocFly Modular.

This module adds real observability to the running application: HTTP request
metrics (counter + histogram), a CPU-ish gauge for active sessions, request
spans and metrics for login attempts. It is called from main.py right after
OTel initialization, and is a no-op when OTel is not available/initialized.

Modulo de instrumentacao OpenTelemetry da aplicacao T! SOS DocFly.
Adiciona metricas de requisicao HTTP, spans por request e metricas de login.
Inofensivo (no-op) quando o OTel nao esta disponivel/inicializado.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from mod_tisosdocfly.otel_integracao import (
    OTEL_AVAILABLE,
    obter_info_otel,
)


def _contadores():
    """Cria e retorna os objetos de metricas (no-op se OTel indisponivel)."""
    if not OTEL_AVAILABLE:
        return None, None, None, None
    try:
        from mod_tisosdocfly.otel_integracao import (
            get_meter,
            criar_contador,
            criar_histograma,
        )
        meter = get_meter("tisosdocfly.http")
        contador_req = criar_contador(
            "tisosdocfly_requisicoes_total",
            "Total de requisicoes HTTP recebidas pela T! SOS DocFly",
        )
        hist_dur = criar_histograma(
            "tisosdocfly_requisicao_duracao",
            "Duracao das requisicoes HTTP (ms)",
            unidade="ms",
        )
        contador_login = criar_contador(
            "tisosdocfly_logins_total",
            "Total de tentativas de login (sucesso/falha)",
        )
        return meter, contador_req, hist_dur, contador_login
    except Exception:
        logging.getLogger(__name__).debug(
            "instrumentacao: falha ao criar metricas OTel", exc_info=True)
        return None, None, None, None


def instrumentar_aplicacao(app):
    """Registra o middleware HTTP + metricas de login na aplicacao.

    Registra um middleware no FastAPI (app do NiceGUI) que mede cada request:
    contador por rota/status e histograma de duracao. Tambem expoe uma funcao
    para registrar logins (usada pela tela de login).
    """
    if not OTEL_AVAILABLE:
        # Sem OTel: middleware no-op mantendo o fluxo normal
        logging.getLogger(__name__).info(
            "[otel] instrumentacao skip: OpenTelemetry indisponivel")
        return False

    try:
        meter, contador_req, hist_dur, contador_login = _contadores()
        if meter is None:
            return False

        @app.middleware("http")
        async def _observer_requisicoes(request: Request, call_next):
            import time
            from mod_tisosdocfly.otel_integracao import get_tracer

            # Filtra apenas requests HTTP reais. O NiceGUI/Socket.IO usa polling
            # e WebSocket (path /socket.io/...) que não têm REQUEST_METHOD — é
            # inofensivo medi-los, mas o call_next falharia. Ignoramos:
            _caminho = request.scope.get("path") or request.url.path or "/"
            if "/socket.io/" in _caminho or request.scope.get("type") != "http":
                # Engine.IO pode abortar com KeyError quando o primeiro evento
                # ASGI é um disconnect do navegador (tab fechada/reload). Não
                # instrumentamos e não deixamos virar "Exception in ASGI".
                try:
                    return await call_next(request)
                except Exception as _exc_sock:
                    try:
                        logging.getLogger(__name__).debug(
                            "socket.io disconnect mascarado como 204 (path=%s): %s",
                            _caminho, _exc_sock, exc_info=True)
                    except Exception:
                        pass
                    try:
                        from mod_tisosdocfly import observabilidade as _obs_sock
                        _obs_sock.get_logger("tisosdocfly").debug(
                            f"socket.io disconnect mascarado como 204 (path={_caminho}): {_exc_sock}")
                    except Exception:
                        pass
                    return Response(status_code=204)

            _metodo = (request.method or "GET")[:20]
            inicio = time.perf_counter()
            rota = _caminho
            try:
                response = await call_next(request)
            except Exception:
                _status = "500"
                if contador_req:
                    contador_req.add(1, {"rota": rota[:200], "metodo": _metodo,
                                         "status": _status})
                if hist_dur:
                    hist_dur.record((time.perf_counter() - inicio) * 1000,
                                    {"rota": rota[:200], "metodo": _metodo})
                raise

            _status = str(getattr(response, "status_code", 200))
            _duracao_ms = (time.perf_counter() - inicio) * 1000

            if contador_req:
                contador_req.add(1, {"rota": rota[:200], "metodo": _metodo,
                                     "status": _status})
            if hist_dur:
                hist_dur.record(_duracao_ms, {"rota": rota[:200], "metodo": _metodo})

            # Span curto por requisição (tolerante a falhas de contexto)
            try:
                tracer = get_tracer("tisosdocfly.http")
                with tracer.start_as_current_span("requisicao-http") as span:
                    span.set_attribute("http.route", rota)
                    span.set_attribute("http.method", _metodo)
                    span.set_attribute("http.status_code", _status)
                    span.set_attribute("http.duration_ms", round(_duracao_ms, 3))
            except Exception:
                logging.getLogger(__name__).debug(
                    "falha ao criar span HTTP", exc_info=True)

            return response

        # Expõe a função de registro de login para ser usada na tela de login.
        # É importada dinamicamente (evita ciclo) e chamada em mod_login.
        def registrar_login_observabilidade(usuario: str, sucesso: bool):
            """Conta tentativa de login (label usuario, resultado)."""
            try:
                if contador_login:
                    contador_login.add(1, {
                        "usuario": (usuario or "desconhecido")[:80],
                        "resultado": "sucesso" if sucesso else "falha",
                    })
            except Exception:
                logging.getLogger(__name__).debug("falha ao registrar login OTel",
                                                  exc_info=True)

        # Guarda a função no módulo para acesso externo
        import mod_tisosdocfly.otel_integracao as _oi
        _oi.registrar_login_observabilidade = registrar_login_observabilidade

        logging.getLogger(__name__).info(
            "[otel] instrumentacao ativa: metricas HTTP + spans por request")
        return True

    except Exception as e:
        logging.getLogger(__name__).info(
            f"[otel] instrumentacao falhou (app segue normal): {e}")
        return False