# -*- coding: utf-8 -*-
"""EN: mod_video admin — stage TTL config, system library (publish/remove)
and global history (metadata only, never file content).

PT-BR: admin — tempo de vida do stage, biblioteca do sistema
(publicar/remover) e histórico global (só metadados, nunca o conteúdo).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from nicegui import ui

try:
    from mod_tisosdocfly.tema_modulo import notificar as _notificar
except Exception:
    def _notificar(msg, tipo="positive", **kwargs):
        try:
            ui.notify(msg, type=tipo)
        except Exception:
            pass


def _log():
    try:
        from mod_tisosdocfly import observabilidade
        return observabilidade.get_logger("video")
    except Exception:
        return None


def _botao(rotulo=None, *, variante="primario", icone=None, on_click=None,
           tooltip=None, testid=""):
    """EN: System-standard button (ui_comum) with raw fallback. PT-BR: botão
    no padrão do sistema (ui_comum) com fallback cru."""
    try:
        from mod_tisosdocfly.ui_comum import botao as _fab
        btn = _fab(rotulo, variante=variante, icone=icone, on_click=on_click,
                   tooltip=tooltip, chave_modulo="video")
        if btn is not None:
            if testid:
                try:
                    btn.props(f"data-testid={testid}")
                except Exception:
                    pass
            return btn
    except Exception:
        pass
    try:
        btn = ui.button(rotulo or "", icon=icone, on_click=on_click)
        if testid:
            try:
                btn.props(f"data-testid={testid}")
            except Exception:
                pass
        return btn
    except Exception:
        return None


def mostrar_administracao(usuario_logado: str = ""):
    """EN: Renders /admin/video. PT-BR: renderiza /admin/video."""
    try:
        from mod_video import bd_manipulador as _bd
    except Exception as e:
        try:
            ui.label("Administração indisponível.").classes("text-negative")
            lg = _log()
            if lg is not None:
                lg.exception(f"mostrar_administracao import: {e}")
        except Exception:
            pass
        return
    try:
        with ui.card().classes("w-full").style("padding: 20px; min-width: 0"):
            ui.label("Tempo de vida no servidor").classes("text-h6 font-bold")
            ui.label(
                "Minutos que o vídeo baixado fica no stage antes de expirar "
                "e ser excluído sozinho (padrão 10, vale para todo stage; "
                "só o publicado na biblioteca não expira).").classes(
                "text-caption text-grey-6")
            try:
                atual = _bd.cfg_expiracao_min()
            except Exception:
                atual = _bd.EXPIRACAO_PADRAO_MIN
            campo_min = ui.number("Minutos até expirar", value=atual,
                                  min=1, max=1440).props(
                "outlined dense").classes("w-full").props(
                "data-testid=video-admin-expiracao")

            def _salvar():
                try:
                    from mod_tisosdocfly.bd_conexao import set_config
                    from mod_tisosdocfly.bd_manipulador import audit_log
                    try:
                        valor = max(1, int(campo_min.value or 10))
                    except (TypeError, ValueError):
                        _notificar("Informe os minutos (número).",
                                   tipo="negative")
                        return
                    set_config("video_expiracao_min", str(valor))
                    try:
                        audit_log(usuario_logado, "video", "configuracao",
                                  f"expiracao={valor}min")
                    except Exception:
                        pass
                    _notificar(f"Tempo de vida: {valor} min.", tipo="positive")
                except Exception as e:
                    try:
                        lg = _log()
                        if lg is not None:
                            lg.exception(f"_salvar: {e}")
                    except Exception:
                        pass
                    _notificar("Erro ao salvar.", tipo="error")

            def _expirar_agora():
                try:
                    from nicegui import run as _run

                    async def _ir():
                        def _fazer():
                            return _bd.expirar_antigos()
                        n = await _run.io_bound(_fazer)
                        _notificar(f"{n} arquivo(s) expirado(s).",
                                   tipo="positive")
                    import asyncio as _aio
                    _aio.get_event_loop().create_task(_ir())
                except Exception as e:
                    try:
                        lg = _log()
                        if lg is not None:
                            lg.exception(f"_expirar_agora: {e}")
                    except Exception:
                        pass
                    _notificar("Erro ao expirar.", tipo="error")

            with ui.row().classes("w-full items-center flex-wrap").style(
                    "gap: .5rem; min-width: 0"):
                _botao("Salvar", icone="save", variante="primario",
                       on_click=_salvar, testid="video-admin-salvar")
                _botao("Expirar agora", icone="cleaning_services",
                       variante="primario", on_click=_expirar_agora,
                       testid="video-admin-expirar")

        with ui.card().classes("w-full").style("padding: 20px; min-width: 0"):
            ui.label("Biblioteca do sistema").classes("text-h6 font-bold")
            ui.label("Publicados: sem expiração, para todos com acesso ao "
                     "módulo (base para outros módulos, como as filas).").classes(
                "text-caption text-grey-6")
            area_bib = ui.column().classes("w-full").style("gap: .5rem").props(
                "data-testid=video-admin-biblioteca")

            @ui.refreshable
            def _render_bib():
                try:
                    itens = _bd.listar_biblioteca()
                except Exception:
                    itens = []
                try:
                    area_bib.clear()
                    with area_bib:
                        if not itens:
                            ui.label("Nada publicado.").classes(
                                "text-body2 text-grey-6")
                            return
                        for item in itens:
                            try:
                                _linha_bib_admin(item, _bd, usuario_logado,
                                                 _render_bib.refresh)
                            except Exception:
                                pass
                except Exception as e:
                    try:
                        lg = _log()
                        if lg is not None:
                            lg.exception(f"biblioteca admin: {e}")
                    except Exception:
                        pass

            _render_bib()

        with ui.card().classes("w-full").style("padding: 20px; min-width: 0"):
            ui.label("Histórico global").classes("text-h6 font-bold")
            try:
                total = _bd.contar_historico()
                linhas = _bd.listar_historico(limite=50)
            except Exception:
                total = 0
                linhas = []
            ui.label(f"{total} pedido(s) no total. Quem pediu, de onde, "
                     "quando e se concluiu — nunca o conteúdo.").classes(
                         "text-caption text-grey-6")
            if not linhas:
                ui.label("Nenhum download registrado.").classes(
                    "text-body2 text-grey-6")
                return
            for linha in linhas:
                try:
                    ui.label(
                        f"{linha.get('data_registro', '')[:16]} · "
                        f"{linha.get('user_nome', '')} · "
                        f"{linha.get('plataforma', '')} · "
                        f"{(linha.get('titulo') or linha.get('url', ''))[:60]} "
                        f"({linha.get('status', '')}"
                        f"{' · biblioteca' if linha.get('publicado') else ''})"
                    ).classes("text-body2")
                except Exception:
                    pass
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"mostrar_administracao: {e}")
        except Exception:
            pass
        try:
            ui.label("Administração indisponível.").classes("text-negative")
        except Exception:
            pass


def _linha_bib_admin(item, _bd, usuario_logado, recarregar):
    """EN: One published row (unpublish/delete). PT-BR: um publicado
    (despublicar/excluir)."""
    try:
        titulo = item.get("titulo") or item.get("arquivo") or ""
        with ui.row().classes("w-full items-center justify-between").style(
                "gap: .5rem; border-bottom: 1px solid #eee; padding: .4rem 0"):
            with ui.column().style("gap: 0; min-width: 0; flex: 1"):
                ui.label(titulo[:90]).classes("text-body2")
                ui.label(
                    f"{item.get('user_nome', '')} · "
                    f"{item.get('plataforma', '')}").classes(
                    "text-caption text-grey-6")
            with ui.row().style("gap: .25rem"):
                pid = item.get("id")

                def _despublicar(pid_=pid):
                    try:
                        ok, msg = _bd.despublicar_pedido(pid_,
                                                         ator=usuario_logado)
                        _notificar(msg, tipo="positive" if ok else "negative")
                        if ok:
                            try:
                                recarregar()
                            except Exception:
                                pass
                    except Exception:
                        pass

                def _excluir(pid_=pid):
                    try:
                        ok, msg = _bd.excluir_pedido(pid_, ator=usuario_logado)
                        _notificar(msg, tipo="positive" if ok else "negative")
                        if ok:
                            try:
                                recarregar()
                            except Exception:
                                pass
                    except Exception:
                        pass
                try:
                    _botao("Devolver ao stage", icone="reply",
                           variante="primario", on_click=_despublicar)
                except Exception:
                    pass
                try:
                    _botao("Excluir", icone="delete", variante="primario",
                           on_click=_excluir)
                except Exception:
                    pass
    except Exception:
        pass
