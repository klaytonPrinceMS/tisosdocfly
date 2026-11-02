"""Embedded MkDocs documentation: static build + serving.

Documentação MkDocs embutida: build estático + servir. A documentação é
servida na PORTA DO MKDOCS (padrão 8000), separada da porta do site (8080)."""
import os
import subprocess
import sys
import threading

from nicegui import app
from starlette.staticfiles import StaticFiles

# `BASE_DIR` é `src/` (código e assets); `DIR_PROJETO` é a raiz do repositório,
# onde ficam `mkdocs.yml` e a pasta `docs/`. O `mkdocs build` roda com
# `cwd=DIR_PROJETO` porque é de lá que ele resolve `docs_dir`/`site_dir` — rodar
# em `src/` faria o build procurar um `mkdocs.yml` que não existe ali.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_PROJETO = os.path.dirname(BASE_DIR)
SITE_DIR = os.path.join(DIR_PROJETO, "site")
ROTA = "/documentacao"
PORTA_PADRAO = 8001

_montado = False
_servidor = None
_porta_atual = None


def _build() -> tuple:
    """Builds site/ with the venv mkdocs. Returns (ok, short_error).

    Gera site/ com o mkdocs do próprio venv. Retorna (ok, erro_curto)."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "mkdocs", "build"],
            cwd=DIR_PROJETO, capture_output=True, text=True,             timeout=120,
        )
        ok = r.returncode == 0 and os.path.exists(os.path.join(SITE_DIR, "index.html"))
        return ok, "" if ok else ((r.stderr or r.stdout or "mkdocs falhou")[-400:])
    except Exception as e:
        return False, str(e)


def montar() -> bool:
    """Serves site/ as static route (idempotent; new files apply without remount).

    Serve site/ como rota estática (idempotente; arquivos novos valem sem remount)."""
    global _montado
    if _montado:
        return True
    if not os.path.exists(os.path.join(SITE_DIR, "index.html")):
        return False
    try:
        app.mount(ROTA, StaticFiles(directory=SITE_DIR, html=True), name="documentacao")
        _montado = True
        return True
    except Exception:
        return False


def iniciar_servidor(porta=PORTA_PADRAO) -> bool:
    """Serves site/ on the mkdocs port in a background thread (daemon).

    Serve a documentação gerada na PORTA DO MKDOCS (padrão 8001), separada
    da porta do site (8080). Idempotente: a primeira chamada inicia; as
    seguintes apenas confirmam. Falha NUNCA derruba o servidor. Se a porta
    pedida estiver ocupada (ex.: 8000 do snap), tenta as próximas 5."""
    global _servidor, _porta_atual
    if _servidor is not None:
        return True
    if not os.path.exists(os.path.join(SITE_DIR, "index.html")):
        return False
    # tenta a porta pedida e as próximas 5 se estiver ocupada
    for tentativa in range(6):
        try:
            from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

            class _Handler(SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory=SITE_DIR, **kwargs)

                def log_message(self, *args):  # silencia o log padrão por request
                    pass

            p = int((porta or PORTA_PADRAO) + tentativa) if tentativa else int(porta or PORTA_PADRAO)
            _servidor = ThreadingHTTPServer(("0.0.0.0", p), _Handler)  # nosec B104 — docs propositalmente na LAN (todos leem); admin controla via docs_ativo
            _porta_atual = p
            threading.Thread(target=_servidor.serve_forever, daemon=True).start()
            if tentativa:
                print(f"[documentacao] porta {porta} em uso, usando {p}")
            print(f"[documentacao] OK: servindo em http://localhost:{p}")
            return True
        except Exception as e:
            if tentativa == 0:
                print(f"[documentacao] aviso: não foi possível servir na porta "
                      f"{porta}: {e}")
                try:
                    _log = _log_doc()
                    if _log:
                        _log.warning(f"documentacao: nao foi possivel servir na porta {porta}: {e}")
                except Exception:
                    pass
            _servidor = None
            continue
    return False


def porta_documentacao():
    """Returns the port where the documentation server is running (or default)."""
    return _porta_atual or PORTA_PADRAO


def habilitada_no_boot():
    """Lê `docs_ativo` da tb_config. Padrão DESLIGADA desde 02/10/2026.

    Antes o padrão era ligada (`"1"`), e a documentação subia em todo boot —
    `mkdocs build` completo mais um servidor na LAN, para um servidor que
    ninguém tinha pedido. O padrão agora é o oposto do que o nome da chave
    sugere, e é intencional: `docs_ativo=1` continua significando "liga", e
    quem liga usa `--ativ-docs` ou este interruptor em Configurações.

    Falha de leitura devolve `False` (desligada): um banco que não responde
    não deve tirar um `mkdocs build` de 120 s do caminho do servidor.
    """
    try:
        from mod_skyrover.bd_conexao import get_config
        return (get_config("docs_ativo", "0") or "0").strip() == "1"
    except Exception:
        return False


def _log_doc():
    try:
        from mod_skyrover import observabilidade
        return observabilidade.get_logger("skyrover")
    except Exception:
        return None


def parar_servidor():
    """Para o servidor de documentação (idempotente, fail-soft).

    Encerra o `ThreadingHTTPServer` de fundo e limpa as referências —
    uma nova chamada a `iniciar_servidor()` recria tudo. Usada no
    shutdown gracioso (`main.py::_encerrar`). Falha NUNCA derruba.
    """
    global _servidor, _porta_atual
    srv, _servidor, _porta_atual = _servidor, None, None
    if srv is None:
        return False
    try:
        srv.shutdown()
        srv.server_close()
    except Exception as e:
        print(f"[documentacao] aviso ao parar servidor: {e}")
    return True


def construir_e_montar_documentacao(logar=True, porta=None) -> bool:
    """Build + mount + start the docs server. Falha NUNCA derruba o servidor.

    Gera o site/, monta a rota inline (compatibilidade) e inicia o servidor
    na porta da documentação (mkdocs, padrão 8000)."""
    ok, erro = _build()
    if not ok:
        if logar:
            print(f"[documentacao] FALHA no mkdocs build: {erro}")
        return False
    ok_serve = iniciar_servidor(porta or PORTA_PADRAO)
    if montar():
        if logar and not ok_serve:
            # `iniciar_servidor` JÁ loga "[documentacao] OK: servindo em ..."
            # quando sobe (linha 85) — repetir aqui duplicava a linha no boot.
            # Só resta avisar o fallback quando a porta ficou ocupada.
            print(f"[documentacao] montado em /documentacao (porta {porta} ocupada, docs via rota interna)")
    elif logar:
        print("[documentacao] build OK, mas nao foi possivel montar a rota agora")
    return True


def reconstruir() -> tuple:
    """Para o botão de Configurações: rebuild + garante rota. (ok, mensagem)."""
    ok, erro = _build()
    if not ok:
        return False, f"Falha no build da documentação: {erro}"
    iniciar_servidor(porta_documentacao())
    if montar():
        return True, (f"Documentação reconstruída — disponível em "
                      f"http://localhost:{porta_documentacao()}")
    return True, ("Arquivos regenerados. A documentação será servida em "
                  f"http://localhost:{porta_documentacao()}")
