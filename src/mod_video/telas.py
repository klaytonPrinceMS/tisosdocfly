# -*- coding: utf-8 -*-
"""EN: Video download screen — paste the link, check it, pick video/audio,
download. Non-admins get the file auto-pushed to their PC (nothing stays on
the server); module admins keep it in stage and may publish it to the system
library. Heavy work (yt-dlp) runs in `run.io_bound` (§5.1). Each user only
sees their own downloads; the library is visible to everyone with access.

PT-BR: Tela de baixar vídeos — cole o link, confira, escolha vídeo/áudio,
baixe. Comum recebe o arquivo direto no PC (nada fica no servidor); admin do
módulo guarda no stage e pode publicar na biblioteca do sistema. O pesado
(yt-dlp) roda em `run.io_bound` (§5.1). Cada um vê só os próprios downloads;
a biblioteca é de todos com acesso.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from nicegui import ui

CHAVE = "video"

try:
    from mod_tisosdocfly.tema_modulo import notificar as _notificar
except Exception:
    def _notificar(msg, tipo="positive", **kwargs):
        try:
            ui.notify(msg, type=tipo)
        except Exception:
            pass


def _foi_desconexao(e):
    """EN: True when the browser left mid-handler (no traceback spam).
    PT-BR: verdadeiro quando o navegador saiu no meio (sem stack no log).
    Vale para "client deleted" e para "slot stack empty" (background task
    criando UI): nos dois casos não há navegador para avisar."""
    try:
        texto = str(e or "")
        return ("has been deleted" in texto
                or "slot stack" in texto
                or "background task" in texto)
    except Exception:
        return False


def _botao(rotulo=None, *, variante="primario", icone=None, on_click=None,
           tooltip=None, testid=""):
    """EN: System-standard button (ui_comum) with raw fallback. PT-BR: botão
    no padrão do sistema (ui_comum) com fallback cru."""
    try:
        from mod_tisosdocfly.ui_comum import botao as _fab
        btn = _fab(rotulo, variante=variante, icone=icone, on_click=on_click,
                   tooltip=tooltip, chave_modulo=CHAVE)
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


def _log():
    try:
        from mod_tisosdocfly import observabilidade
        return observabilidade.get_logger("video")
    except Exception:
        return None


def _eh_admin(user_nome, perfil_global):
    """EN: Module admin (or general admin). PT-BR: admin do módulo (ou geral)."""
    try:
        if (perfil_global or "") == "administrador_geral":
            return True
        from mod_tisosdocfly.autenticacao import eh_admin_do_modulo
        return bool(eh_admin_do_modulo(user_nome, CHAVE))
    except Exception:
        return False


def _tamanho_legivel(n):
    """EN: Human-readable size. PT-BR: tamanho legível."""
    try:
        n = int(n or 0)
        for unidade in ("B", "KB", "MB", "GB"):
            if n < 1024 or unidade == "GB":
                return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
            n /= 1024.0
        return f"{n:.1f} GB"
    except Exception:
        return ""


def _titulo_1_linha(texto, tooltip=True):
    """EN: Single-line title with lateral scroll. PT-BR: título em 1 linha
    com rolagem lateral (nunca estoura o cartão)."""
    try:
        lbl = ui.label((texto or "")[:200]).classes("text-body1").style(
            "display: block; width: 100%; max-width: 100%; "
            "white-space: nowrap; overflow-x: auto; overflow-y: hidden; "
            "min-width: 0; padding-bottom: 4px;")
        if tooltip:
            try:
                lbl.tooltip((texto or "")[:200])
            except Exception:
                pass
        return lbl
    except Exception:
        return None


def _duracao_legivel(seg):
    """EN: Seconds to h:mm:ss. PT-BR: segundos para h:mm:ss."""
    try:
        seg = int(seg or 0)
        h, resto = divmod(seg, 3600)
        m, s = divmod(resto, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
    except Exception:
        return ""


def _resta(expira_em):
    """EN: (text, expired?) for the countdown. PT-BR: (texto, expirou?) da
    contagem. Vazio = sem expiração (só biblioteca)."""
    try:
        txt = (expira_em or "").strip()
        if not txt:
            return "Sem expiração", False
        try:
            fim = datetime.strptime(txt, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return "", False
        seg = int((fim - datetime.now()).total_seconds())
        if seg <= 0:
            return "Expirado", True
        m, s = divmod(seg, 60)
        if m >= 60:
            h, m = divmod(m, 60)
            return f"Expira em {h}h{m:02d}", False
        return f"Expira em {m}:{s:02d}", False
    except Exception:
        return "", False


# Downloads vivos entre navegações (o processo sobrevive à página): pid ->
# {user_nome, url, plataforma, formato, titulo}. A página que abre reatacha
# as barras; ninguém vê pedido alheio (filtro por user_nome). O progresso
# também é global pelo mesmo motivo.
_TAREFAS_VIVAS = {}
_PROGRESSO_VIVO = {}

# Texto que volta ao campo após cada processamento (padrão da tela).
TEXTO_PADRAO_CAMPO = ("Posso até não concordar com suas ações gestos "
                      "e palavras, porém defenderei até a morte seu "
                      "direito, porém lembre-se suas ações tem "
                      "consequência")
# Cliente do navegador por pedido: task nova NÃO herda o slot (stack é por
# task!), então `ui.download`/`notify` em background levantavam "slot
# stack is empty" em silêncio. Com o cliente capturado no clique, `with
# cliente:` devolve o contexto. Sem cliente (navegou) = entrega pulada.
_CLIENTES = {}


def _cliente_atual():
    """EN: Browser client of this handler (or None). PT-BR: cliente desta
    ação (ou None)."""
    try:
        from nicegui import context as _ctx
        return _ctx.client
    except Exception:
        return None


def _cliente_vivo(cliente):
    """EN: Client still connected. PT-BR: cliente ainda conectado."""
    try:
        return cliente is not None and not bool(cliente.is_deleted)
    except Exception:
        return False


def _download_para_cliente(pid, caminho, filename=""):
    """EN: Pushes a file to the requester's browser (or skips). PT-BR:
    empurra o arquivo ao navegador de quem pediu (ou pula)."""
    try:
        cliente = _CLIENTES.get(pid)
        if not _cliente_vivo(cliente):
            return False
        with cliente:
            ui.download(caminho, filename=filename or None)
        return True
    except Exception:
        return False


def _notificar_cliente(pid, msg, tipo="positive"):
    """EN: Notifies the requester's browser (or skips). PT-BR: avisa no
    navegador de quem pediu (ou pula)."""
    try:
        cliente = _CLIENTES.get(pid)
        if not _cliente_vivo(cliente):
            return False
        with cliente:
            _notificar(msg, tipo=tipo)
        return True
    except Exception:
        return False
# Ouvinte por usuário: a tela aberta é avisada quando um pedido termina.
_OUVIDORES = {}
# Vagas simultâneas de download (lote grande derruba a conexão e o
# YouTube responde 403; o resto espera em "Na fila…"). Máquina pequena = 2.
_SEMAFORO = None
VAGAS_DOWNLOAD = 2


def _semaforo():
    """EN: Process-wide download slots (3). PT-BR: vagas de download (3)."""
    global _SEMAFORO
    try:
        import asyncio as _aio
        # Semáforo é global do processo (singleton): desde o Python 3.10 o
        # `Semaphore` não prende mais loop (`_loop` não existe), então a
        # checagem antiga recriava o objeto a cada chamada e o limite de
        # vagas nunca valia. Sem `if` por loop: uma instância só.
        if _SEMAFORO is None:
            _SEMAFORO = _aio.Semaphore(VAGAS_DOWNLOAD)
        return _SEMAFORO
    except Exception:
        return None


def _ouvir_conclusao(user_nome):
    """EN: Nudges the open screen (if any) to refresh. PT-BR: cutuca a tela
    aberta (se houver) para recarregar."""
    try:
        fn = _OUVIDORES.get(user_nome or "")
        if callable(fn):
            fn()
    except Exception:
        pass


def _avisar_seguro(msg, tipo="positive"):
    """EN: Notify that never raises (background task may lack client).
    PT-BR: avisa sem nunca levantar (task pode estar sem navegador)."""
    try:
        _notificar(msg, tipo=tipo)
    except Exception:
        pass


# Relógios de expiração do histórico (fora do closure da tela): pid ->
# {"expira": txt, "rotulos": [labels]}. O timer da tela repinta; rótulo
# morto é podado em silêncio (navegou = some).
_RELOGIOS_EXPIRACAO = {}


def _chaves_da_selecao(sel):
    """EN: Row ids from a table selection event (a LIST of rows). PT-BR:
    ids das linhas do evento de seleção (é LISTA de linhas)."""
    try:
        if isinstance(sel, dict):
            sel = sel.get("rows", sel.get("keys", []))
        return [(r.get("id") if isinstance(r, dict) else r)
                for r in (sel or [])]
    except Exception:
        return []


def _registrar_relogio(pid, expira_em, rotulo):
    """EN: Registers a live countdown label. PT-BR: registra um rótulo de
    contagem ao vivo."""
    try:
        if not pid or not expira_em or rotulo is None:
            return
        ent = _RELOGIOS_EXPIRACAO.get(pid)
        if ent is None:
            ent = {"expira": expira_em, "rotulos": []}
            _RELOGIOS_EXPIRACAO[pid] = ent
        ent["expira"] = expira_em
        ent["rotulos"].append(rotulo)
    except Exception:
        pass


def _pintar_relogios():
    """EN: Repaints history countdowns, pruning dead labels. PT-BR: repinta
    as contagens do histórico, podando rótulos mortos."""
    try:
        for pid in list(_RELOGIOS_EXPIRACAO):
            try:
                ent = _RELOGIOS_EXPIRACAO.get(pid) or {}
                texto, _ = _resta(ent.get("expira") or "")
                vivos = []
                for rot in ent.get("rotulos") or []:
                    try:
                        try:
                            morto = bool(rot.is_deleted)
                        except Exception:
                            morto = False
                        if morto:
                            continue
                        if texto:
                            rot.text = texto
                        vivos.append(rot)
                    except Exception:
                        pass
                if vivos:
                    ent["rotulos"] = vivos
                else:
                    _RELOGIOS_EXPIRACAO.pop(pid, None)
            except Exception:
                pass
    except Exception:
        pass


def abrir_player(titulo, caminho_ou_url, nome_arquivo="", poster=""):
    """EN: Watch dialog (video/audio). PT-BR: diálogo para assistir (vídeo/áudio).
    `poster` é a capa (URL da miniatura) exibida antes do play."""
    try:
        from mod_video import servico_download as _dl
        audio = _dl.eh_audio(nome_arquivo or caminho_ou_url)
    except Exception:
        audio = False
    try:
        with ui.dialog() as dlg, ui.card().classes("w-full").style(
                "min-width: min(720px, 92vw); padding: 16px"):
            ui.label((titulo or "Assistir")[:100]).classes("text-h6 font-bold")
            try:
                if audio:
                    ui.audio(caminho_ou_url).classes("w-full").props("controls")
                else:
                    vid = ui.video(caminho_ou_url).classes("w-full").props(
                        "controls")
                    if (poster or "").strip():
                        try:
                            vid._props["poster"] = poster.strip()[:500]
                        except Exception:
                            pass
            except Exception:
                ui.label("Não foi possível abrir o player.").classes(
                    "text-negative")
            with ui.row().classes("w-full justify-end mt-2"):
                _botao("Fechar", on_click=dlg.close, variante="primario")
        dlg.open()
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                if _foi_desconexao(e):

                    pass

                else:

                    lg.exception(f"abrir_player: {e}")
        except Exception:
            pass


def mostrar_tela(user_nome: str, perfil_global: str = ""):
    """EN: Renders the module screen. PT-BR: renderiza a tela do módulo."""
    try:
        from mod_video import bd_manipulador as _bd
        from mod_video import servico_download as _dl
    except Exception as e:
        try:
            ui.label("Vídeos indisponível.").classes("text-negative")
            lg = _log()
            if lg is not None:
                lg.exception(f"mostrar_tela import: {e}")
        except Exception:
            pass
        return
    try:
        admin = _eh_admin(user_nome, perfil_global)
    except Exception:
        admin = False
    # Comum não vê histórico nem biblioteca: o arquivo desce direto para o
    # PC dele e nada fica no servidor. Quem cura o acervo é o admin.
    _estado = {"recarregar": lambda: None}
    try:
        with ui.card().classes("w-full").style("padding: 20px; min-width: 0"):
            ui.label("Baixar vídeo ou áudio").classes("text-h6 font-bold")
            ui.label(
                "Cole o link, verifique e escolha: o formato exato do vídeo "
                "ou, sendo playlist, quais itens baixar. O botão de baixar "
                "só libera após a verificação. Baixe só conteúdo que você "
                "tem direito de usar."
                + ("" if admin else
                   " O arquivo desce direto para o seu computador — nada "
                   "fica guardado no servidor.")
            ).classes("text-body2 font-bold text-grey-9").style(
                "text-align: justify")
            ui.label(
                "Uso legítimo: esta ferramenta serve para baixar conteúdo "
                "livre de direitos autorais. O USUÁRIO é o responsável pelo "
                "que baixa — todo link usado fica registrado com quem pediu "
                "(usuário e data/hora), de onde (URL de origem), o quê "
                "(título e tamanho) e como (formato e plataforma). Esses "
                "registros seguem a LGPD — base legal do interesse legítimo "
                "e do cumprimento de obrigação legal (art. 7º), guarda para "
                "cumprimento de obrigação e exercício de direitos em processo "
                "(art. 16) e registro das operações de tratamento (art. 37) "
                "— e a Lei de Direitos Autorais (Lei nº 9.610/1998), podendo "
                "ser entregues à Justiça em caso de violação de direitos."
            ).classes("text-body2 text-grey-9").style(
                "text-align: justify; border-left: 4px solid #f9a825; "
                "padding-left: .5rem")
            _verificado = {"tipo": "", "url": "", "titulo": "", "opcoes": [],
                           "entradas": [], "miniatura": ""}
            _opcoes_map = {}
            _checks_playlist = []

            def _invalidar():
                try:
                    _verificado.update({"tipo": "", "url": "", "titulo": "", "opcoes": [],
                                        "entradas": [], "miniatura": ""})
                    _opcoes_map.clear()
                    _checks_playlist.clear()
                    try:
                        area_verificado.clear()
                    except Exception:
                        pass
                    try:
                        btn_baixar.disable()
                    except Exception:
                        pass
                    try:
                        campo_formato.disable()
                    except Exception:
                        pass
                    try:
                        btn_marcar.set_visibility(False)
                        btn_desmarcar.set_visibility(False)
                    except Exception:
                        pass
                except Exception:
                    pass

            def _marcar_todos():
                try:
                    for chk, _ent in _checks_playlist:
                        try:
                            chk.value = True
                            chk.update()
                        except Exception:
                            pass
                except Exception:
                    pass

            def _desmarcar_todos():
                try:
                    for chk, _ent in _checks_playlist:
                        try:
                            chk.value = False
                            chk.update()
                        except Exception:
                            pass
                except Exception:
                    pass

            # Link + verificar na mesma linha; controles em linha própria.
            # Flex com quebra só em tela estreita.
            with ui.row().classes("w-full items-center flex-wrap").style(
                    "gap: .5rem; min-width: 0"):
                campo_url = ui.input(
                    "Link do vídeo ou da playlist",
                    placeholder="https://www.youtube.com/watch?v=...",
                    value=TEXTO_PADRAO_CAMPO) \
                    .props("outlined dense").classes("shrink") \
                    .style("flex: 1 1 280px; min-width: 200px") \
                    .props("data-testid=video-url")
                campo_url.on_value_change(lambda e: _invalidar())
                btn_verificar = _botao("Verificar link", icone="search",
                                       variante="primario",
                                       testid="video-verificar")
                try:
                    btn_verificar.classes("shrink-0")
                    btn_verificar.style("width: min(100%, 320px)")
                except Exception:
                    pass
            # Episódios entre o link e os controles.
            area_verificado = ui.column().classes("w-full").style(
                "gap: .5rem; min-width: 0").props("data-testid=video-verificado")
            # Ordem: desmarcar, marcar, formato, processar.
            with ui.row().classes("w-full items-center flex-wrap").style(
                    "gap: .5rem; min-width: 0"):
                btn_desmarcar = _botao("Desmarcar todos", icone="deselect",
                                       variante="primario",
                                       on_click=_desmarcar_todos,
                                       testid="video-desmarcar-todos")
                btn_marcar = _botao("Marcar todos", icone="select_all",
                                    variante="primario", on_click=_marcar_todos,
                                    testid="video-marcar-todos")
                try:
                    btn_desmarcar.classes("shrink-0")
                    btn_marcar.classes("shrink-0")
                except Exception:
                    pass
                campo_formato = ui.select(
                    {}, value=None,
                    label="Formato (verifique o link antes)") \
                    .props("outlined dense").classes("shrink") \
                    .style("flex: 1 1 220px; min-width: 180px") \
                    .props("data-testid=video-formato")
                try:
                    campo_formato.disable()
                except Exception:
                    pass
                btn_baixar = _botao("Processar e preparar para download",
                                    icone="cloud_download",
                                    variante="primario",
                                    testid="video-baixar")
                try:
                    btn_baixar.classes("shrink-0")
                    btn_baixar.style("width: min(100%, 320px)")
                    btn_baixar.disable()
                except Exception:
                    pass
            # Marcar/desmarcar (só playlist) + estado.
            with ui.row().classes("w-full items-center flex-wrap").style(
                    "gap: .5rem; min-width: 0"):
                try:
                    btn_marcar.set_visibility(False)
                    btn_desmarcar.set_visibility(False)
                except Exception:
                    pass
                rotulo_estado = ui.label("").classes("text-caption text-grey-6")
            try:
                btn_baixar.disable()
            except Exception:
                pass
            try:
                # Aviso de qualidade só para admin e só sem ffmpeg: o comum
                # não administra o servidor e não precisa do recado.
                if admin:
                    aviso_q = _dl.aviso_qualidade()
                    if aviso_q:
                        ui.label(aviso_q).classes("text-caption text-orange-8")
            except Exception:
                pass
            if not _dl.yt_dlp_disponivel():
                ui.label(
                    "Baixador ainda não instalado no servidor (yt-dlp). "
                    "Avise o administrador.").classes("text-caption text-negative")
            ocupado = {"v": False}

            def _opcao_atual():
                try:
                    return _opcoes_map.get(campo_formato.value or "")
                except Exception:
                    return None

            async def _verificar():
                if ocupado["v"]:
                    return
                ocupado["v"] = True
                btn_verificar.disable()
                try:
                    area_verificado.clear()
                except Exception:
                    pass
                _verificado.update({"tipo": "", "url": "", "titulo": "", "opcoes": [],
                                    "entradas": [], "miniatura": ""})
                _opcoes_map.clear()
                _checks_playlist.clear()
                try:
                    btn_baixar.disable()
                except Exception:
                    pass
                with area_verificado:
                    with ui.row().classes("w-full items-center").style(
                            "gap: .5rem; min-width: 0"):
                        try:
                            ui.spinner(size="lg").props(
                                "aria-label=verificando-link")
                        except Exception:
                            pass
                        info_link = ui.label("Consultando o link…").classes(
                            "text-caption text-grey-7")
                # Palavras rodando enquanto lê (playlist leva ~30 s): prova
                # que o servidor não travou. Para sozinho ao concluir.
                _verificando = {"ativo": True, "i": 0}
                _msgs_ver = ["Consultando o link…",
                             "Contatando o site…",
                             "Aguardando resposta…",
                             "Verificando se é vídeo único ou playlist…",
                             "Lendo título do vídeo…",
                             "Lendo duração…",
                             "Descobrindo o autor…",
                             "Medindo qualidades…",
                             "Listando formatos de vídeo…",
                             "Listando formatos de áudio…",
                             "Conferindo tamanhos…",
                             "Separando o que dá para baixar…",
                             "Se for playlist, contando episódios…",
                             "Se for playlist, lendo cada episódio…",
                             "Montando opções de download…",
                             "Ajustando qualidade padrão…",
                             "Conferindo expiração…",
                             "Preparando a lista na tela…",
                             "Montando botões…",
                             "Organizando a exibição…"]

                def _girar_msg():
                    try:
                        if not _verificando.get("ativo"):
                            return
                        _verificando["i"] = (_verificando.get("i", 0) + 1) \
                            % len(_msgs_ver)
                        info_link.text = _msgs_ver[_verificando["i"]]
                    except Exception:
                        pass
                try:
                    ui.timer(6.0, _girar_msg).props(
                        "data-testid=video-verificando")
                except Exception:
                    pass
                try:
                    from nicegui import run as _run
                    url = _dl.validar_url(campo_url.value or "")
                    if not url:
                        texto_cru = (campo_url.value or "").strip()
                        if len(texto_cru) >= 2:
                            # EASTER EGG (modo fala) — NÃO DOCUMENTAR.
                            try:
                                _verificando["ativo"] = False
                            except Exception:
                                pass
                            try:
                                area_verificado.clear()
                            except Exception:
                                pass
                            if not _dl.tem_espeak():
                                with area_verificado:
                                    ui.label(
                                        "Servidor sem voz (espeak): peça ao "
                                        "administrador geral para instalar "
                                        "(`sudo apt install espeak`).").classes(
                                        "text-caption text-negative")
                                return
                            texto = texto_cru[:_dl.FALA_MAX_CHARS]
                            n = len(texto)
                            opcoes = [{
                                "id": fid, "rotulo": rot, "spec": fid,
                                "audio": True, "converter": False,
                                "mesclar": False}
                                for fid, rot in _dl.FORMATOS_FALA]
                            _verificado.update(
                                {"tipo": "fala", "url": "", "texto": texto,
                                 "titulo": " ".join(texto.split())[:60],
                                 "opcoes": opcoes})
                            with area_verificado:
                                ui.label(
                                    f"Texto para fala · {n} caractere(s) "
                                    f"(~{n // 850 + 1} min de áudio). "
                                    "Voz neural (Edge, pt-BR) com reserva "
                                    "offline.").classes(
                                    "text-body2 font-bold")
                                ui.label("Escolha o formato acima e clique "
                                         "em Baixar.").classes(
                                         "text-caption text-grey-6")
                            try:
                                mapa = {o["id"]: o["rotulo"]
                                        for o in opcoes}
                                _opcoes_map.update(
                                    {o["id"]: o for o in opcoes})
                                campo_formato.set_options(mapa)
                                campo_formato.value = opcoes[0]["id"]
                                campo_formato.update()
                            except Exception:
                                pass
                            try:
                                campo_formato.enable()
                            except Exception:
                                pass
                            try:
                                btn_baixar.enable()
                            except Exception:
                                pass
                            return
                        _notificar("Cole um link válido (http/https) ou "
                                   "um texto para virar áudio.",
                                   tipo="negative")
                        try:
                            area_verificado.clear()
                        except Exception:
                            pass
                        return

                    def _consultar():
                        return _dl.extrair_verificacao(url)
                    ver = await _run.io_bound(_consultar)
                    _verificado["url"] = url
                    try:
                        _verificando["ativo"] = False
                    except Exception:
                        pass
                    try:
                        area_verificado.clear()
                    except Exception:
                        pass
                    if not (ver or {}).get("tipo"):
                        with area_verificado:
                            ui.label(
                                f"{_dl.detectar_plataforma(url)}: não foi "
                                "possível ler o link — confira.").classes(
                                "text-caption text-negative")
                        return
                    if ver.get("tipo") == "playlist":
                        entradas = ver.get("entradas") or []
                        _verificado.update({"tipo": "playlist",
                                            "entradas": entradas})
                        with area_verificado:
                            ui.label(
                                f"Playlist: {(ver.get('titulo') or '')[:100]} "
                                f"({ver.get('total') or len(entradas)} "
                                "vídeo(s)"
                                f"{', mostrando 50' if ver.get('limitado') else ''}). "
                                "Marque os que quer baixar.").classes(
                                "text-body2 font-bold")
                            if not entradas:
                                ui.label("Nada legível nesta playlist.").classes(
                                    "text-caption text-negative")
                                return
                            try:
                                btn_marcar.set_visibility(True)
                                btn_desmarcar.set_visibility(True)
                            except Exception:
                                pass
                            with ui.column().style(
                                    "gap: 0; max-height: 240px; "
                                    "overflow-y: auto; min-width: 0").classes(
                                    "w-full border rounded px-2 py-1"):
                                for idx, ent in enumerate(entradas):
                                    try:
                                        dur = _duracao_legivel(
                                            ent.get("duracao_s") or 0)
                                        texto_ent = (
                                            f"{(ent.get('titulo') or 'Sem título')[:45]}"
                                            + (f" · {dur}" if dur and dur != "0:00"
                                               else ""))
                                        chk = ui.checkbox(
                                            texto_ent,
                                            value=True).classes("w-full").style(
                                            "min-width: 0")
                                        try:
                                            chk.tooltip(
                                                (ent.get("titulo") or "")[:200])
                                        except Exception:
                                            pass
                                        _checks_playlist.append((chk, ent))
                                    except Exception:
                                        pass
                        try:
                            # Sem ffmpeg, vídeo nem é oferecido (só o que
                            # desce de verdade): arquivo único ou áudio.
                            if _dl.tem_ffmpeg():
                                base = {k: v for k, v in _dl.FORMATOS}
                                padrao = "audio_mp3"
                            else:
                                base = {k: v for k, v in
                                        _dl.FORMATOS_SEM_FFMPEG}
                                padrao = "audio_orig"
                            campo_formato.set_options(base)
                            campo_formato.value = padrao
                            campo_formato.update()
                        except Exception:
                            pass
                        try:
                            campo_formato.enable()
                        except Exception:
                            pass
                        try:
                            btn_baixar.enable()
                        except Exception:
                            pass
                        return
                    # vídeo único: opções reais de formato
                    opcoes = ver.get("formatos") or []
                    _verificado.update({"tipo": "video", "opcoes": opcoes,
                                        "titulo": ver.get("titulo") or "",
                                        "miniatura": ver.get("miniatura") or ""})
                    dur = _duracao_legivel(ver.get("duracao_s") or 0)
                    with area_verificado:
                        ui.label(
                            f"{(ver.get('titulo') or '')[:100]}"
                            + (f" · {(ver.get('autor') or '')[:60]}"
                               if ver.get("autor") else "")
                            + (f" · {dur}" if dur and dur != "0:00" else "")
                        ).classes("text-body2 font-bold")
                        try:
                            so_audio = bool(opcoes) and not any(
                                not o.get("audio") for o in opcoes)
                        except Exception:
                            so_audio = False
                        if not opcoes:
                            ui.label(
                                "Sem arquivo único e sem ffmpeg no servidor: "
                                "este vídeo só existe em trilhas separadas. "
                                "Peça ao administrador geral "
                                "(instalação/ativação) para rodar "
                                "`instalar_externos.py --ffmpeg`.").classes(
                                "text-caption text-negative")
                            return
                        if so_audio and not _dl.tem_ffmpeg():
                            try:
                                detalhe = (f" (existe em até "
                                           f"{int(ver.get('max_altura') or 0)}p)"
                                           if ver.get("max_altura") else "")
                            except (TypeError, ValueError):
                                detalhe = ""
                            except Exception:
                                detalhe = ""
                            ui.label(
                                "Este vídeo não tem arquivo único de vídeo"
                                f"{detalhe}: sem ffmpeg no servidor, só o "
                                "áudio desce. Peça ao administrador geral "
                                "(instalação/ativação) para rodar "
                                "`instalar_externos.py --ffmpeg`.").classes(
                                "text-caption text-orange-8")
                        ui.label("Escolha o formato acima e clique em "
                                 "Baixar.").classes(
                            "text-caption text-grey-6")
                    try:
                        mapa = {o["id"]: o["rotulo"] for o in opcoes}
                        _opcoes_map.update({o["id"]: o for o in opcoes})
                        campo_formato.set_options(mapa)
                        try:
                            padrao = next(o["id"] for o in opcoes
                                          if o.get("audio"))
                        except StopIteration:
                            padrao = opcoes[0]["id"]
                        campo_formato.value = padrao
                        campo_formato.update()
                    except Exception:
                        pass
                    try:
                        campo_formato.enable()
                    except Exception:
                        pass
                    try:
                        btn_baixar.enable()
                    except Exception:
                        pass
                except Exception as e:
                    if _foi_desconexao(e):
                        # Saiu da página durante a consulta: sem stack, sem UI.
                        try:
                            ocupado["v"] = False
                        except Exception:
                            pass
                        return
                    try:
                        lg = _log()
                        if lg is not None:
                            if _foi_desconexao(e):

                                pass

                            else:

                                lg.exception(f"_verificar: {e}")
                    except Exception:
                        pass
                    try:
                        area_verificado.clear()
                        with area_verificado:
                            ui.label("Não foi possível consultar o link.").classes(
                                "text-caption text-negative")
                    except Exception:
                        pass
                finally:
                    try:
                        _verificando["ativo"] = False
                    except Exception:
                        pass
                    try:
                        btn_verificar.enable()
                    except Exception:
                        pass
                    ocupado["v"] = False

            try:
                btn_verificar.on_click(_verificar)
            except Exception:
                pass


            # Barras de download: uma por pedido (o usuário pode enfileirar
            # vários links; cada clique vira um pedido com a barra própria).
            # O hook do yt-dlp escreve bytes em `_PROGRESSO` (thread do
            # download) e o `ui.timer` repinta (event-loop) — nunca se toca
            # em widget fora do event-loop.
            # Andamento em grade fluida: quantos cards couberem por linha,
            # sempre ocupando a linha toda (auto-fit colapsa a coluna vazia;
            # 1fr estica). Cartão com respiro e barra larga.
            with ui.card().classes("w-full").style(
                    "padding: 20px; min-width: 0"):
                ui.label("Downloads em andamento").classes(
                    "text-h6 font-bold")
                _andamento = ui.element("div").style(
                    "display: grid; gap: .75rem; width: 100%; "
                    "grid-template-columns: repeat(auto-fit, "
                    "minmax(min(100%, 340px), 1fr));").props(
                    "data-testid=video-andamento")
            _linhas_andamento = {}
            # Global entre páginas: sair e voltar reatacha as barras vivas.
            _PROGRESSO = _PROGRESSO_VIVO
            # Seleção dos Meus arquivos (estilo PDF): pids marcados.
            _selecao = set()
            # Trava do rebuild: ignora o on_select disparado pelo código.
            _travando = {"v": False}
            # Contagens de expiração ao vivo: pid -> {"expira": txt,
            # "rotulo": label}. O timer de 1 s repinta junto com as barras.
            _EXPIRACAO = {}
            # Caixa de cada barra (a UI some junto com o registro): o
            # `_finalizar_barra` tira do timer, mas a caixa fica até a
            # remoção explícita — senão sobra botão morto na tela.
            _CAIXAS = {}

            def _cb_progresso(pid, info):
                try:
                    anterior = _PROGRESSO.get(pid) or {}
                    anterior.update(info or {})
                    _PROGRESSO[pid] = anterior
                except Exception:
                    pass

            def _pct_de(info):
                # Teto 0.99 até concluir: o total do YouTube é ESTIMATIVA e
                # estoura para cima ou para baixo — sem o teto a barra
                # saturava no começo e "não acompanhava" os MB do texto.
                try:
                    if (info or {}).get("status") in ("concluido",):
                        return 1.0
                    pct = (info or {}).get("pct")
                    if pct is not None:
                        return max(0.0, min(0.99, float(pct)))
                    baixado = (info or {}).get("baixado")
                    total = (info or {}).get("total")
                    if baixado and total:
                        return max(0.0, min(0.99,
                                            float(baixado) / float(total)))
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
                except Exception:
                    pass
                return 0.0

            def _texto_progresso(info):
                try:
                    estado = str((info or {}).get("status") or "")
                    if estado in ("na_fila", ""):
                        return "Na fila…"
                    if estado == "iniciando":
                        return "Iniciando…"
                    if estado == "processando":
                        return "Juntando/convertendo… só mais um instante."
                    if estado == "aguardando":
                        return "Limite do YouTube… nova tentativa em instantes."
                    if estado == "concluido":
                        return "Concluído."
                    if estado == "erro":
                        return "Falhou."
                    partes = []
                    pct = _pct_de(info)
                    if pct > 0:
                        partes.append(f"{pct * 100:.0f}%")
                    try:
                        baixado = (info or {}).get("baixado")
                        total = (info or {}).get("total")
                        if baixado and total:
                            partes.append(
                                f"{_tamanho_legivel(baixado)} de "
                                f"{_tamanho_legivel(total)}")
                        elif isinstance((info or {}).get("total_txt"), str) \
                                and (info or {}).get("total_txt"):
                            partes.append(
                                f"{pct * 100:.0f}% de "
                                f"{(info or {}).get('total_txt')}")
                    except Exception:
                        pass
                    try:
                        vel = (info or {}).get("vel")
                        if vel:
                            partes.append(
                                f"{_tamanho_legivel(float(vel))}/s")
                    except (TypeError, ValueError):
                        pass
                    except Exception:
                        pass
                    try:
                        eta = (info or {}).get("eta")
                        if eta not in (None, ""):
                            partes.append(f"ETA {_duracao_legivel(eta)}")
                    except Exception:
                        pass
                    return " · ".join(partes) if partes else "Baixando…"
                except Exception:
                    return "Baixando…"

            def _pintar_barras():
                try:
                    _pintar_relogios()
                except Exception:
                    pass
                try:
                    for pid, refs in list(_linhas_andamento.items()):
                        try:
                            try:
                                if refs.get("barra") is not None and bool(
                                        refs["barra"].is_deleted):
                                    _linhas_andamento.pop(pid, None)
                                    continue
                            except Exception:
                                pass
                            if refs.get("concluido"):
                                texto, _ = _resta(refs.get("expira") or "")
                                try:
                                    refs["rotulo"].text = (
                                        f"Concluído · {texto}" if texto
                                        else "Concluído.")
                                except Exception:
                                    pass
                                continue
                            info = _PROGRESSO.get(pid) or {}
                            try:
                                # Monotônica: estimate ruim fazia a barra
                                # VOLTAR (ou saturar); agora só anda.
                                pct = _pct_de(info)
                                try:
                                    pico = float(refs.get("pico") or 0.0)
                                except (TypeError, ValueError):
                                    pico = 0.0
                                except Exception:
                                    pico = 0.0
                                if pct < pico and not refs.get("concluido"):
                                    pct = pico
                                refs["pico"] = pct
                                refs["barra"].value = pct
                                refs["barra"].update()
                            except Exception:
                                try:
                                    refs["barra"].value = _pct_de(info)
                                except Exception:
                                    pass
                            refs["rotulo"].text = _texto_progresso(info)
                        except Exception:
                            pass
                    for pid, ref in list(_EXPIRACAO.items()):
                        try:
                            texto, _ = _resta(ref.get("expira") or "")
                            if texto:
                                ref["rotulo"].text = texto
                        except Exception:
                            pass
                except Exception:
                    pass

            ui.timer(1.0, _pintar_barras)

            def _nova_barra(pid, url, plataforma, titulo=""):
                estado = {"nome": None, "pronto": False}

                def _baixar_estado(pid_=pid):
                    try:
                        nome = estado.get("nome")
                        if not nome:
                            return
                        cam = _bd.caminho_arquivo(nome, publicado=False)
                        if cam and os.path.isfile(cam):
                            ui.download(cam, filename=nome)
                        else:
                            _notificar("Arquivo saiu do servidor "
                                       "(expirou).", tipo="negative")
                    except Exception:
                        pass

                def _excluir_estado(pid_=pid):
                    try:
                        import asyncio as _aio2
                        _aio2.get_event_loop().create_task(
                            _apagar_falha(pid_))
                    except Exception:
                        pass

                try:
                    with _andamento:
                        caixa = ui.column().style(
                            "gap: .4rem; min-width: 0; width: 100%; "
                            "border: 1px solid #e0e0e0; border-radius: 10px; "
                            "padding: 1rem")
                        with caixa:
                            with ui.row().classes(
                                    "w-full items-center flex-wrap").style(
                                    "gap: .5rem; min-width: 0"):
                                lbl_titulo = _titulo_1_linha(titulo or url)
                                try:
                                    lbl_titulo.style(
                                        "flex: 1 1 160px; min-width: 0")
                                except Exception:
                                    pass
                            barra = ui.linear_progress(value=0.0).classes(
                                "w-full").style("height: 12px")
                            rot = ui.label("Na fila…").classes(
                                "text-body2 text-grey-7")
                            # Enquanto baixa: SÓ o Interromper, ocupando a
                            # linha toda. Baixar/Excluir nascem ao concluir.
                            with ui.element("div").classes("w-full").style(
                                    "display: grid; min-width: 0; "
                                    "grid-template-columns: "
                                    "minmax(0, 1fr); "
                                    "gap: .5rem; align-items: stretch") as grade_acoes:
                                btn_stop = _botao(
                                    "Interromper", icone="close",
                                    variante="primario",
                                    on_click=lambda pid_=pid:
                                    _cancelar_pedido(pid_),
                                    tooltip="Só vale durante o download")
                            for _b in (btn_stop,):
                                try:
                                    if _b is not None:
                                        _b.classes("w-full").style(
                                            "min-width: 0")
                                except Exception:
                                    pass
                    _linhas_andamento[pid] = {"barra": barra, "rotulo": rot,
                                              "caixa": caixa,
                                              "titulo_label": lbl_titulo,
                                              "btn_dl": None,
                                              "btn_del": None,
                                              "btn_stop": btn_stop,
                                              "grade_acoes": grade_acoes,
                                              "estado": estado}
                    _CAIXAS[pid] = caixa
                    _PROGRESSO[pid] = {"status": "na_fila", "pct": 0.0}
                except Exception as e:
                    try:
                        lg = _log()
                        if lg is not None:
                            if _foi_desconexao(e):

                                pass

                            else:

                                lg.exception(f"_nova_barra: {e}")
                    except Exception:
                        pass

            async def _cancelar_pedido(pid):
                """EN: Cancels a running download and removes the job.
                PT-BR: cancela o download em curso e elimina o trabalho."""
                try:
                    from nicegui import run as _run
                    _dl.solicitar_cancelamento(pid)
                    _TAREFAS_VIVAS.pop(pid, None)
                    _CLIENTES.pop(pid, None)
                    try:
                        refs = _linhas_andamento.pop(pid, None)
                        if refs:
                            try:
                                refs["rotulo"].text = "Cancelando…"
                            except Exception:
                                pass
                    except Exception:
                        pass
                    _PROGRESSO.pop(pid, None)
                    caixa = _CAIXAS.pop(pid, None)

                    def _apagar():
                        try:
                            _bd.excluir_pedido(pid, ator=user_nome)
                        except Exception:
                            pass
                    await _run.io_bound(_apagar)
                    try:
                        if caixa is not None:
                            try:
                                caixa.delete()
                            except Exception:
                                caixa.clear()
                        elif refs:
                            try:
                                refs["caixa"].delete()
                            except Exception:
                                refs["caixa"].clear()
                    except Exception:
                        pass
                    _notificar("Download cancelado e removido.",
                               tipo="positive")
                    try:
                        _estado["recarregar"]()
                    except Exception:
                        pass
                except Exception as e:
                    try:
                        lg = _log()
                        if lg is not None:
                            if _foi_desconexao(e):

                                pass

                            else:

                                lg.exception(f"_cancelar_pedido: {e}")
                    except Exception:
                        pass
                    _notificar("Não foi possível cancelar.", tipo="negative")

            def _finalizar_barra(pid, ok=True, nome_arq="", titulo_final="",
                                   expira=""):
                # Andamento mostra SÓ o que ainda baixa: ao terminar (ok ou
                # falha), a barra sai e o resultado vive em Meus arquivos.
                try:
                    _linhas_andamento.pop(pid, None)
                    _PROGRESSO.pop(pid, None)
                    caixa = _CAIXAS.pop(pid, None)
                    try:
                        if caixa is not None:
                            try:
                                caixa.delete()
                            except Exception:
                                caixa.clear()
                    except Exception:
                        pass
                except Exception:
                    pass


            async def _apagar_falha(pid):
                """EN: Removes a row (bar + record) so no dead button stays.
                PT-BR: elimina a linha (barra + registro) sem deixar botão
                morto."""
                try:
                    from nicegui import run as _run
                    _linhas_andamento.pop(pid, None)
                    _PROGRESSO.pop(pid, None)
                    _TAREFAS_VIVAS.pop(pid, None)
                    _CLIENTES.pop(pid, None)
                    caixa = _CAIXAS.pop(pid, None)

                    def _apagar():
                        try:
                            _bd.excluir_pedido(pid, ator=user_nome)
                        except Exception:
                            pass
                    await _run.io_bound(_apagar)
                    try:
                        if caixa is not None:
                            try:
                                caixa.delete()
                            except Exception:
                                caixa.clear()
                    except Exception:
                        pass
                    try:
                        _estado["recarregar"]()
                    except Exception:
                        pass
                except Exception:
                    pass

            async def _executar_pedido(pid, url, formato, plataforma,
                                       spec=None, converter=None,
                                       mesclar=None, expira="",
                                       e_fala=False, texto_fala="",
                                       voz="F"):
                try:
                    from nicegui import run as _run

                    def _fazer():
                        if e_fala:
                            return _dl.sintetizar_fala(
                                texto_fala, pid, formato=formato,
                                progresso_cb=lambda info, pid_=pid:
                                _cb_progresso(pid_, info),
                                user_nome=user_nome, voz=voz)
                        return _dl.baixar(
                            url, formato, pid,
                            progresso_cb=lambda info, pid_=pid:
                            _cb_progresso(pid_, info),
                            spec=spec, converter=converter,
                            mesclar=mesclar, user_nome=user_nome)
                    try:
                        sem = _semaforo()
                    except Exception:
                        sem = None
                    if sem is not None:
                        try:
                            await sem.acquire()
                        except Exception:
                            pass
                    try:
                        if _dl.consumir_cancelamento(pid):
                            _TAREFAS_VIVAS.pop(pid, None)
                            try:
                                _dl.limpar_parciais(pid)
                            except Exception:
                                pass
                            return
                        ok, titulo, nome_arq, tamanho, msg = await _run.io_bound(
                            _fazer)
                    finally:
                        try:
                            if sem is not None:
                                sem.release()
                        except Exception:
                            pass
                    _TAREFAS_VIVAS.pop(pid, None)
                    if _dl.consumir_cancelamento(pid):
                        _CLIENTES.pop(pid, None)
                        # Cancelado no meio: a linha já foi excluída, nada
                        # a gravar, notificar ou abrir. O arquivo que pousou
                        # carrega o `-pid-` no nome e sai aqui (senão órfão).
                        try:
                            _dl.limpar_parciais(pid)
                        except Exception:
                            pass
                        return

                    def _fechar():
                        try:
                            mini = ""
                            try:
                                mini = str((_bd.obter_pedido(pid) or {}
                                            ).get("miniatura") or "")
                            except Exception:
                                mini = ""
                            if ok and not mini.strip():
                                try:
                                    mini = str((
                                        _dl.obter_informacoes(url) or {}
                                    ).get("miniatura") or "")
                                except Exception:
                                    mini = ""
                            if ok:
                                _bd.atualizar_status(
                                    pid, "pronto", titulo=titulo,
                                    arquivo=nome_arq, tamanho=tamanho,
                                    miniatura=mini or None)
                            else:
                                _bd.marcar_erro(pid, msg)
                        except Exception:
                            pass
                        try:
                            _bd._auditar(
                                user_nome,
                                "video_baixado" if ok else "video_erro",
                                f"{url[:120]}",
                                f"arquivo={(nome_arq or '')[:120]} | "
                                f"formato={formato} | "
                                f"plataforma={plataforma} | "
                                f"tamanho={tamanho} | "
                                f"{(titulo or msg)[:120]}")
                        except Exception:
                            pass
                        return ok
                    await _run.io_bound(_fechar)
                    _TAREFAS_VIVAS.pop(pid, None)
                    _CLIENTES.pop(pid, None)
                    _ouvir_conclusao(user_nome)
                    _finalizar_barra(pid, ok, nome_arq if ok else "", titulo if ok else "",
                                    expira if ok else "")
                    if not ok:
                        _notificar_cliente(pid, msg, tipo="negative")
                        try:
                            _estado["recarregar"]()
                        except Exception:
                            pass
                        return
                    # Servidor concluiu (baixou/juntou): desce para o PC
                    # na hora, para todo perfil. O arquivo FICA no stage
                    # até o TTL (10 min) para ZIP/separados — nada some
                    # antes da hora.
                    caminho = _bd.caminho_arquivo(nome_arq,
                                                  publicado=False)

                    if caminho and os.path.isfile(caminho):
                        _download_para_cliente(pid, caminho, nome_arq)
                        if not admin:
                            _notificar_cliente(
                                pid, "Desceu para o seu computador. "
                                "Fica no stage (10 min) para ZIP "
                                "ou baixar de novo.", tipo="positive")
                        else:
                            _notificar_cliente(
                                pid, "Desceu para o seu computador. Fica no "
                                "stage (10 min, sai sozinho): assista ou "
                                "publique na biblioteca.", tipo="positive")
                    else:
                        _avisar_seguro(msg, tipo="positive")
                    try:
                        _estado["recarregar"]()
                    except Exception:
                        pass
                    if admin:
                        try:
                            _mostrar_resultado_admin(
                                pid, titulo, nome_arq, _bd, _dl,
                                _estado["recarregar"], user_nome)
                        except Exception:
                            pass
                except Exception as e:
                    _TAREFAS_VIVAS.pop(pid, None)
                    _CLIENTES.pop(pid, None)
                    try:
                        _finalizar_barra(pid, False)
                    except Exception:
                        pass
                    if _foi_desconexao(e):
                        # Download terminou sem navegador: banco já fechado,
                        # sem stack e sem UI.
                        return
                    try:
                        lg = _log()
                        if lg is not None:
                            if _foi_desconexao(e):

                                pass

                            else:

                                lg.exception(f"_executar_pedido: {e}")
                    except Exception:
                        pass
                    try:
                        _notificar("Não foi possível baixar.", tipo="negative")
                    except Exception:
                        pass

            async def _baixar():
                # Só após a verificação: vídeo único usa a opção real
                # escolhida; playlist enfileira um pedido por item marcado.
                try:
                    from nicegui import run as _run
                    if _verificado.get("tipo") == "fala" and \
                            (_verificado.get("texto") or "").strip():
                        pass
                    elif not _verificado.get("tipo") \
                            or not _verificado.get("url"):
                        _notificar("Verifique o link antes de baixar.",
                                   tipo="negative")
                        return
                    try:
                        expira = _bd._daqui_a_minutos(
                            _bd.cfg_expiracao_min())
                    except Exception:
                        expira = ""
                    rotulo_estado.text = "Registrando…"
                    import asyncio as _aio
                    try:
                        _cliente_clique = _cliente_atual()
                    except Exception:
                        _cliente_clique = None

                    async def _enfileirar(url_item, formato_item,
                                          plataforma_item, titulo_previo="",
                                          spec=None, converter=None,
                                          mesclar=None, miniatura="",
                                          e_fala=False, texto_fala="",
                                          voz="F"):
                        try:
                            def _registrar():
                                return _bd.registrar_pedido(
                                    user_nome, url_item, plataforma_item,
                                    formato_item, expira_em=expira,
                                    titulo=titulo_previo,
                                    miniatura=miniatura)
                            pid = await _run.io_bound(_registrar)
                            if not pid:
                                return None
                            try:
                                _TAREFAS_VIVAS[pid] = {
                                    "user_nome": user_nome,
                                    "url": url_item,
                                    "plataforma": plataforma_item,
                                    "formato": formato_item,
                                    "titulo": titulo_previo or "",
                                    "miniatura": miniatura or ""}
                                if _cliente_vivo(_cliente_clique):
                                    _CLIENTES[pid] = _cliente_clique
                            except Exception:
                                pass
                            _nova_barra(pid, url_item, plataforma_item, titulo_previo)
                            _aio.get_event_loop().create_task(
                                _executar_pedido(pid, url_item, formato_item,
                                                 plataforma_item, spec,
                                                 converter, mesclar, expira,
                                                 e_fala=e_fala,
                                                 texto_fala=texto_fala,
                                                 voz=voz))
                            return pid
                        except Exception:
                            return None

                    if _verificado.get("tipo") == "playlist":
                        marcados = [(chk.value, ent)
                                    for chk, ent in _checks_playlist]
                        alvos = [(ent.get("url"), ent.get("titulo"))
                                 for marcado, ent in marcados
                                 if marcado and (ent or {}).get("url")]
                        if not alvos:
                            _notificar("Marque ao menos um vídeo.",
                                       tipo="negative")
                            rotulo_estado.text = ""
                            return
                        try:
                            padrao_lista = "audio_mp3" if _dl.tem_ffmpeg() \
                                else "audio_orig"
                        except Exception:
                            padrao_lista = "audio_mp3"
                        formato = campo_formato.value or padrao_lista
                        n = 0
                        for url_item, _tit in alvos:
                            try:
                                plat = _dl.detectar_plataforma(url_item)
                            except Exception:
                                plat = "Outro site"
                            pid = await _enfileirar(url_item, formato, plat,
                                                    _tit or "")
                            if pid:
                                n += 1
                        rotulo_estado.text = ""
                        campo_url.value = TEXTO_PADRAO_CAMPO
                        _invalidar()
                        _notificar(f"{n} pedido(s) na fila.",
                                   tipo="positive" if n else "negative")
                        return
                    if _verificado.get("tipo") == "fala":
                        # EASTER EGG (modo fala) — NÃO DOCUMENTAR.
                        opc = _opcao_atual()
                        if not opc:
                            _notificar("Verifique o texto antes de baixar.",
                                       tipo="negative")
                            rotulo_estado.text = ""
                            return
                        try:
                            _fid = str(opc.get("id") or "")
                            voz_opc = (_dl._formato_e_voz(_fid)[1]
                                       or "F")
                        except Exception:
                            voz_opc = "F"
                        pid = await _enfileirar(
                            "", opc.get("id") or "fala_mp3_francisca",
                            "Texto em áudio",
                            _verificado.get("titulo") or "fala",
                            e_fala=True,
                            texto_fala=_verificado.get("texto") or "",
                            voz=voz_opc)
                        rotulo_estado.text = ""
                        if not pid:
                            _notificar("Não foi possível registrar o pedido.",
                                       tipo="negative")
                            return
                        campo_url.value = TEXTO_PADRAO_CAMPO
                        _invalidar()
                        return
                    opc = _opcao_atual()
                    if not opc:
                        _notificar("Verifique o link antes de baixar.",
                                   tipo="negative")
                        rotulo_estado.text = ""
                        return
                    url = _verificado.get("url")
                    try:
                        plataforma = _dl.detectar_plataforma(url)
                    except Exception:
                        plataforma = "Outro site"
                    pid = await _enfileirar(
                        url, opc.get("id") or "video", plataforma,
                        _verificado.get("titulo") or "",
                        spec=opc.get("spec"), converter=opc.get("converter"),
                        mesclar=opc.get("mesclar"),
                        miniatura=_verificado.get("miniatura") or "")
                    rotulo_estado.text = ""
                    if not pid:
                        _notificar("Não foi possível registrar o pedido.",
                                   tipo="negative")
                        return
                    campo_url.value = TEXTO_PADRAO_CAMPO
                    _invalidar()
                except Exception as e:
                    try:
                        lg = _log()
                        if lg is not None:
                            if _foi_desconexao(e):

                                pass

                            else:

                                lg.exception(f"_baixar: {e}")
                    except Exception:
                        pass
                    _notificar("Não foi possível baixar.", tipo="negative")
                    rotulo_estado.text = ""

            try:
                btn_baixar.on_click(_baixar)
            except Exception:
                pass



        # Meus arquivos: todo perfil vê os PRÓPRIOS (o comum não tem
        # biblioteca, mas precisa rever o que baixou ao voltar à tela).
        with ui.card().classes("w-full").style("padding: 20px; min-width: 0"):
            ui.label("Meus arquivos").classes("text-h6 font-bold")
            ui.label("Só os seus: o que já desceu, o que está no stage e o "
                     "que falhou." if not admin else
                     "Stage do módulo. O comum recebe o arquivo direto no "
                     "PC.").classes("text-body2 font-bold text-grey-9")
            por_id_ref = {"linhas": []}

            def _cor_resta(seg):
                try:
                    if seg is None:
                        return ""
                    if seg <= 60:
                        return "red"
                    if seg <= 300:
                        return "amber"
                    return "green"
                except Exception:
                    return ""

            def _ao_selecionar(e):
                """Seleção da tabela (nativa, header marca todos). O evento
                é LISTA de linhas (TableSelectionEventArguments.selection),
                não dict — ler como dict era o bug que nunca marcava nada."""
                try:
                    if _travando.get("v"):
                        return
                    # O evento traz o estado FINAL: reconstrói em vez de
                    # somar (senão desmarcar nunca limpa).
                    _selecao.clear()
                    for k in _chaves_da_selecao(
                            getattr(e, "selection", None)):
                        try:
                            if k is not None:
                                _selecao.add(k)
                        except Exception:
                            pass
                except Exception:
                    pass

            def _selecionados():
                try:
                    por_id = {l.get("id"): l
                              for l in por_id_ref.get("linhas") or []}
                    return [por_id[p] for p in list(_selecao)
                            if p in por_id]
                except Exception:
                    return []

            def _excluir_sel():
                try:
                    alvos = _selecionados()
                    if not alvos:
                        _notificar("Marque ao menos um arquivo.",
                                   tipo="negative")
                        return
                    n = 0
                    for l in alvos:
                        try:
                            ok, _m = _bd.excluir_pedido(
                                l.get("id"), ator=user_nome)
                            if ok:
                                _selecao.discard(l.get("id"))
                                n += 1
                        except Exception:
                            pass
                    _notificar(f"{n} excluído(s).", tipo="positive")
                    _recarregar_historico()
                except Exception:
                    pass

            def _sep_sel():
                try:
                    marcados = _selecionados()
                    if not marcados:
                        _notificar("Marque ao menos um arquivo.",
                                   tipo="negative")
                        return
                    alvos = [l for l in marcados
                             if l.get("status") == "pronto"
                             and l.get("arquivo")]
                    if not alvos:
                        _notificar("Os marcados já saíram do servidor "
                                   "(entregues/expirados). Baixe de novo "
                                   "pelo link.", tipo="negative")
                        return
                    n = 0
                    for l in alvos:
                        try:
                            cam = _bd.caminho_arquivo(
                                l.get("arquivo"), publicado=False)
                            if cam and os.path.isfile(cam):
                                ui.download(
                                    cam, filename=l.get("arquivo"))
                                n += 1
                        except Exception:
                            pass
                    _notificar(
                        f"{n} download(s) iniciado(s). Se o navegador "
                        "barrar múltiplos, autorize ou use o ZIP.",
                        tipo="positive" if n else "negative")
                except Exception:
                    pass

            def _zip_sel():
                # ZIP com o cliente capturado no clique: sem ele (navegou),
                # o `with cliente` falha em silêncio e o ZIP fica no stage.
                try:
                    cliente_zip = _cliente_atual()
                    marcados = _selecionados()
                    if not marcados:
                        _notificar("Marque ao menos um arquivo.",
                                   tipo="negative")
                        return
                    nomes = [l.get("arquivo") for l in marcados
                             if l.get("status") == "pronto"
                             and l.get("arquivo")]
                    if not nomes:
                        _notificar("Os marcados já saíram do servidor "
                                   "(entregues/expirados). Baixe de novo "
                                   "pelo link.", tipo="negative")
                        return

                    async def _ir():
                        try:
                            from nicegui import run as _run2

                            def _zipar():
                                return _bd.zipar_selecao(user_nome, nomes)
                            zip_path = await _run2.io_bound(_zipar)
                            if not zip_path:
                                return
                            try:
                                if cliente_zip is not None:
                                    with cliente_zip:
                                        ui.download(zip_path)
                                else:
                                    ui.download(zip_path)
                            except Exception:
                                return
                            try:
                                import asyncio as _aioz2
                                _aioz2.get_event_loop().call_later(
                                    10.0, lambda: _remover_zip(zip_path))
                            except Exception:
                                pass
                        except Exception:
                            pass
                    import asyncio as _aioz
                    _aioz.get_event_loop().create_task(_ir())
                except Exception:
                    pass

            tabela_hist = ui.table(
                columns=[
                    {"name": "arquivo", "label": "Arquivo",
                     "field": "arquivo", "align": "left"},
                    {"name": "tam", "label": "Tamanho", "field": "tam"},
                    {"name": "sit", "label": "Situação", "field": "sit"},
                    {"name": "resta", "label": "Expira em",
                     "field": "resta"},
                ],
                rows=[], row_key="id", selection="multiple",
                on_select=_ao_selecionar,
            ).props("flat bordered dense").classes("w-full").props(
                "data-testid=video-historico")
            tabela_hist.add_slot("body-cell-resta", """
                <q-td :props="props">
                    <q-badge :color="props.row.cor" :label="props.row.resta">
                        <q-tooltip>Expira após o tempo configurado
                        (10 min padrão)</q-tooltip>
                    </q-badge>
                </q-td>
            """)
            linha_atual = [None]

            async def _acao_linha(acao):
                try:
                    por_id = {l.get("id"): l
                              for l in por_id_ref.get("linhas") or []}
                    l = por_id.get(linha_atual[0])
                    if not l:
                        return
                    if l.get("publicado"):
                        cam = _bd.caminho_arquivo(
                            l.get("arquivo"), publicado=True)
                        url_ver = _bd.url_biblioteca(l.get("arquivo"))
                    else:
                        cam = _bd.caminho_arquivo(
                            l.get("arquivo"), publicado=False)
                        url_ver = cam
                    pronto = bool(l.get("status") == "pronto" and cam
                                  and os.path.isfile(cam))
                    if acao == "assistir" and pronto:
                        poster = str(l.get("miniatura") or "")
                        if not poster.strip():
                            try:
                                from nicegui import run as _run2
                                info = await _run2.io_bound(
                                    lambda: _dl.obter_informacoes(
                                        l.get("url") or ""))
                                poster = str((info or {}).get(
                                    "miniatura") or "")
                                if poster.strip():
                                    _bd.definir_miniatura(
                                        l.get("id"), poster)
                            except Exception:
                                poster = ""
                        abrir_player(l.get("titulo") or "",
                                     url_ver or cam, l.get("arquivo"),
                                     poster=poster or "")
                    elif acao == "baixar" and pronto:
                        ui.download(cam, filename=l.get("arquivo"))
                    elif acao == "publicar" and admin and pronto \
                            and not l.get("publicado"):
                        ok, msg = _bd.publicar_pedido(
                            l.get("id"), ator=user_nome)
                        _notificar(msg, tipo="positive" if ok
                                   else "negative")
                        _recarregar_historico()
                    elif acao == "excluir":
                        _bd.excluir_pedido(l.get("id"), ator=user_nome)
                        _notificar("Excluído.", tipo="positive")
                        _recarregar_historico()
                except Exception:
                    pass

            with tabela_hist:
                with ui.context_menu() as menu_linha:
                    ui.item("Assistir",
                            on_click=lambda: _acao_linha("assistir"))
                    ui.item("Baixar",
                            on_click=lambda: _acao_linha("baixar"))
                    if admin:
                        ui.item("Publicar no sistema",
                                on_click=lambda: _acao_linha("publicar"))
                    ui.item("Excluir",
                            on_click=lambda: _acao_linha("excluir"))

            def _on_row(e):
                try:
                    linha_atual[0] = (e.args or [None, None])[1]
                except Exception:
                    pass
                try:
                    menu_linha.open()
                except Exception:
                    pass
            try:
                tabela_hist.on("row-click", _on_row)
            except Exception:
                pass

            barra_lote = ui.row().classes("w-full items-center").style(
                "gap: .5rem")
            with barra_lote:
                with ui.row().classes(
                        "w-full items-center justify-center flex-wrap").style(
                        "gap: .5rem; min-width: 0"):
                    _botao("Excluir selecionados", icone="delete",
                           variante="primario", on_click=_excluir_sel,
                           testid="video-excluir-sel")
                    _botao("Baixar ZIP", icone="folder_zip",
                           variante="primario", on_click=_zip_sel,
                           testid="video-zip-sel")
                    _botao("Baixar", icone="file_download",
                           variante="primario", on_click=_sep_sel,
                           testid="video-separados-sel")

            def _recarregar_historico():
                try:
                    linhas = _bd.listar_historico(user_nome, limite=30)
                except Exception:
                    linhas = []
                # Sem arquivo no disco, sem presença: expirado some, e
                # pronto sem arquivo (limpo pela expiração) também. Só fica
                # o que dá para agir: pendente (baixando), publicado e
                # pronto com arquivo existente. Erro fica (precisa de ação).
                try:
                    visiveis = []
                    for l in linhas or []:
                        try:
                            st = (l.get("status") or "")
                            if st == "expirado":
                                continue
                            if st == "pendente" or l.get("publicado") \
                                    or st == "erro":
                                visiveis.append(l)
                                continue
                            if st == "pronto" and l.get("arquivo"):
                                try:
                                    cam = _bd.caminho_arquivo(
                                        l.get("arquivo"), publicado=False)
                                    if cam and os.path.isfile(cam):
                                        visiveis.append(l)
                                        continue
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    linhas = visiveis
                except Exception:
                    pass
                try:
                    por_id_ref["linhas"] = linhas
                    ids = {l.get("id") for l in linhas}
                    for pid in list(_selecao):
                        if pid not in ids:
                            _selecao.discard(pid)

                    def _segundos(exp, caminho_fallback=""):
                        try:
                            from datetime import datetime as _dt
                            if exp:
                                fim = _dt.strptime((exp or "")[:19],
                                                   "%Y-%m-%d %H:%M:%S")
                                return int((fim - _dt.now()).total_seconds())
                            # Legado sem expira_em: estima pelo mtime + TTL
                            # (só exibição; a limpeza usa a mesma regra).
                            if caminho_fallback:
                                import time as _tt
                                try:
                                    ttl = _bd.cfg_expiracao_min() * 60
                                except Exception:
                                    ttl = 600
                                try:
                                    fim_ts = os.path.getmtime(
                                        caminho_fallback) + ttl
                                    return int(fim_ts - _tt.time())
                                except OSError:
                                    return None
                            return None
                        except Exception:
                            return None

                    def _fmt_resta(seg):
                        try:
                            if seg is None:
                                return ""
                            if seg <= 0:
                                return "Expirado"
                            m, s = divmod(int(seg), 60)
                            if m >= 60:
                                h, m = divmod(m, 60)
                                return f"{h}h{m:02d}"
                            return f"{m}:{s:02d}"
                        except Exception:
                            return ""

                    rows = []
                    for l in linhas:
                        try:
                            cam_tbl = ""
                            if l.get("status") == "pronto" \
                                    and not l.get("publicado"):
                                try:
                                    cam_tbl = _bd.caminho_arquivo(
                                        l.get("arquivo") or "",
                                        publicado=False)
                                except Exception:
                                    cam_tbl = ""
                            seg = _segundos(l.get("expira_em") or "",
                                            cam_tbl) \
                                if l.get("status") == "pronto" \
                                and not l.get("publicado") else None
                            titulo = l.get("titulo") or l.get("url") or ""
                            tamanho = _tamanho_legivel(
                                l.get("tamanho_bytes") or 0)
                            rows.append({
                                "id": l.get("id"),
                                "arquivo": titulo[:60],
                                "tam": tamanho if tamanho != "0 B" else "—",
                                "sit": l.get("status") or "",
                                "resta": _fmt_resta(seg) if seg is not None
                                else ("Na biblioteca" if l.get("publicado")
                                      else "—"),
                                "cor": _cor_resta(seg),
                            })
                        except Exception:
                            pass
                    _travando["v"] = True
                    try:
                        tabela_hist.rows = rows
                        tabela_hist.update()
                    except Exception:
                        pass
                    try:
                        tabela_hist.selected = [
                            r for r in rows if r["id"] in _selecao]
                        tabela_hist.update()
                    except Exception:
                        pass
                    _travando["v"] = False
                except Exception as e:
                    try:
                        lg = _log()
                        if lg is not None:
                            if _foi_desconexao(e):
                                pass
                            else:
                                lg.exception(f"historico: {e}")
                    except Exception:
                        pass
            _estado["recarregar"] = _recarregar_historico
            _recarregar_historico()
            try:
                # Expiração ao vivo, como no PDF (seleção preservada).
                ui.timer(30.0, _recarregar_historico)
            except Exception:
                pass

        # Biblioteca: só admin (o comum não cura acervo).
        if admin:
            with ui.card().classes("w-full").style("padding: 20px; min-width: 0"):
                ui.label("Biblioteca do sistema").classes("text-h6 font-bold")
                ui.label("Vídeos publicados pelos administradores — sem expiração, "
                         "para assistir ou salvar.").classes(
                             "text-caption text-grey-6")
                area_bib = ui.column().classes("w-full").style("gap: .5rem").props(
                    "data-testid=video-biblioteca")
                try:
                    itens = _bd.listar_biblioteca()
                except Exception:
                    itens = []
                try:
                    with area_bib:
                        if not itens:
                            ui.label("Nada publicado ainda.").classes(
                                "text-body2 text-grey-6")
                        for item in itens:
                            try:
                                _linha_biblioteca(item, _bd)
                            except Exception:
                                pass
                except Exception as e:
                    try:
                        lg = _log()
                        if lg is not None:
                            if _foi_desconexao(e):

                                pass

                            else:

                                lg.exception(f"biblioteca: {e}")
                    except Exception:
                        pass

            def _reatachar():
                """EN: Rebuilds bars for this user's live downloads. PT-BR:
                recria as barras dos downloads vivos deste usuário (voltou
                à tela no meio do processo)."""
                try:
                    for pid, t in list(_TAREFAS_VIVAS.items()):
                        try:
                            if (t or {}).get("user_nome") != user_nome:
                                continue
                            if pid in _linhas_andamento:
                                continue
                            _nova_barra(pid, (t or {}).get("url") or "",
                                        (t or {}).get("plataforma") or "",
                                        (t or {}).get("titulo") or "")
                        except Exception:
                            pass
                except Exception:
                    pass

            def _reconciliar_pendentes():
                """EN: Old 'pendente' rows with no live task failed. PT-BR:
                pendente antigo sem tarefa viva vira erro (sessão anterior
                ou reinício no meio). Só 2+ min para não pegar o recém-criado."""
                try:
                    from datetime import datetime as _dt
                    from datetime import timedelta as _td
                    linhas = _bd.listar_historico(user_nome, limite=100)
                    for l in linhas or []:
                        try:
                            if (l.get("status") or "") != "pendente":
                                continue
                            if l.get("id") in _TAREFAS_VIVAS:
                                continue
                            dt = _dt.strptime(
                                (l.get("data_registro") or "")[:19],
                                "%Y-%m-%d %H:%M:%S")
                            if _dt.now() - dt > _td(minutes=2):
                                _bd.marcar_erro(
                                    l["id"], "Não concluído (sessão anterior)")
                        except Exception:
                            pass
                except Exception:
                    pass

            def _recarregar_tudo():
                try:
                    _reatachar()
                except Exception:
                    pass
                try:
                    _estado["recarregar"]()
                except Exception:
                    pass

            try:
                _OUVIDORES[user_nome] = _recarregar_tudo
            except Exception:
                pass
            try:
                _reconciliar_pendentes()
            except Exception:
                pass
            try:
                _reatachar()
            except Exception:
                pass
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                if _foi_desconexao(e):

                    pass

                else:

                    lg.exception(f"mostrar_tela: {e}")
        except Exception:
            pass
        _notificar("Erro ao montar a tela de vídeos.", tipo="negative")


def _mostrar_resultado_admin(pedido_id, titulo, nome_arq, _bd, _dl,
                             recarregar, user_nome):
    """EN: Just-downloaded card for admins (watch/save/publish). PT-BR: cartão
    do recém-baixado para admin (assistir/salvar/publicar)."""
    try:
        caminho = _bd.caminho_arquivo(nome_arq, publicado=False)
        if not caminho or not os.path.isfile(caminho):
            return
        with ui.dialog() as dlg, ui.card().classes("w-full").style(
                "min-width: min(720px, 92vw); padding: 16px"):
            ui.label((titulo or nome_arq)[:100]).classes("text-h6 font-bold")
            ui.label("No stage (10 min, sai sozinho). Publique para a "
                     "biblioteca ou exclua quando não precisar mais.").classes(
                         "text-caption text-grey-6")
            try:
                if _dl.eh_audio(nome_arq):
                    ui.audio(caminho).classes("w-full").props("controls")
                else:
                    ui.video(caminho).classes("w-full").props("controls")
            except Exception:
                pass
            with ui.row().classes("w-full items-center flex-wrap").style(
                    "gap: .5rem; min-width: 0"):
                try:
                    _botao("Salvar no PC", icone="save_alt",
                           variante="primario",
                           on_click=lambda: ui.download(
                               caminho, filename=nome_arq))
                except Exception:
                    pass

                def _publicar():
                    try:
                        from nicegui import run as _run

                        async def _ir():
                            try:
                                def _fazer():
                                    return _bd.publicar_pedido(pedido_id,
                                                               ator=user_nome)
                                ok, msg = await _run.io_bound(_fazer)
                                try:
                                    _notificar(
                                        msg, tipo="positive" if ok
                                        else "negative")
                                except Exception:
                                    pass
                                try:
                                    recarregar()
                                except Exception:
                                    pass
                                if ok:
                                    try:
                                        dlg.close()
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        import asyncio as _aio
                        _aio.get_event_loop().create_task(_ir())
                    except Exception:
                        pass
                try:
                    _botao("Publicar no sistema", icone="publish",
                           variante="primario", on_click=_publicar,
                           testid="video-publicar")
                except Exception:
                    pass

                def _excluir():
                    try:
                        ok, msg = _bd.excluir_pedido(pedido_id,
                                                     ator=user_nome)
                        _notificar(msg, tipo="positive" if ok else "negative")
                        try:
                            recarregar()
                        except Exception:
                            pass
                        dlg.close()
                    except Exception:
                        pass
                try:
                    _botao("Excluir", icone="delete", variante="primario",
                           on_click=_excluir, testid="video-excluir")
                except Exception:
                    pass
                _botao("Fechar", on_click=dlg.close, variante="primario")
        dlg.open()
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                if _foi_desconexao(e):

                    pass

                else:

                    lg.exception(f"_mostrar_resultado_admin: {e}")
        except Exception:
            pass


def _remover_zip(zip_path):
    """EN: Removes the ephemeral ZIP. PT-BR: remove o ZIP efêmero."""
    try:
        if zip_path and os.path.isfile(zip_path):
            os.remove(zip_path)
    except OSError:
        pass
    except Exception:
        pass


def _linha_biblioteca(item, _bd):
    """EN: One library row (watch/save). PT-BR: uma linha da biblioteca
    (assistir/salvar)."""
    try:
        titulo = item.get("titulo") or item.get("arquivo") or ""
        meta = (f"{item.get('plataforma', '')} · "
                f"{_tamanho_legivel(item.get('tamanho_bytes') or 0)}")
        url = _bd.url_biblioteca(item.get("arquivo") or "")
        caminho = _bd.caminho_arquivo(item.get("arquivo") or "",
                                      publicado=True)
        pronto = bool(caminho and os.path.isfile(caminho))
        with ui.row().classes("w-full items-center justify-between").style(
                "gap: .5rem; border-bottom: 1px solid #eee; padding: .4rem 0"):
            with ui.column().style("gap: 0; min-width: 0; flex: 1"):
                ui.label(titulo[:90]).classes("text-body2")
                ui.label(meta).classes("text-caption text-grey-6")
            if pronto:
                with ui.row().classes("flex-wrap").style("gap: .25rem"):
                    try:
                        _botao("Assistir", icone="play_arrow",
                               variante="primario", on_click=(
                                   lambda u=url, t=titulo,
                                   n=item.get("arquivo"),
                                   p=item.get("miniatura") or "":
                                   abrir_player(t, u, n, poster=p)))
                    except Exception:
                        pass
                    try:
                        _botao("Salvar", icone="save_alt",
                               variante="primario",
                               on_click=(
                                   lambda c=caminho,
                                   n=item.get("arquivo"):
                                   ui.download(c, filename=n)))
                    except Exception:
                        pass
    except Exception:
        pass
