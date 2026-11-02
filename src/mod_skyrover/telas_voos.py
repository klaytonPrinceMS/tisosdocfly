"""NiceGUI screens for the Onda 1 core flow: clients, flights, media, reports.

Telas da Onda 1 do Skyrover X1 — cliente → propriedade → voo → upload de
fotos/vídeos → laudo base. Todas as escritas validam o perfil antes de
gravar; o upload grava os arquivos em `midia/<voo_id>/` com nome seguro e
SHA-256, mantendo no banco central apenas os metadados.

A tela é montada por `mostrar_tela(nome, perfil)`, chamada pela rota `/voos`
do `main.py` depois de `pagina_restrita`.
"""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from nicegui import ui

from mod_skyrover import autenticacao, voos
from mod_skyrover.aba_modulo import cabecalho, campo_busca
from mod_skyrover.tema_modulo import notificar
from mod_skyrover import ui_comum

_CORES_STATUS = {
    "rascunho": "grey-7",
    "em_captura": "info",
    "capturado": "primary",
    "laudo_gerado": "positive",
    "arquivado": "warning",
}
_TAMANHO_MAX_UPLOAD = 512 * 1024 * 1024  # 512 MB por arquivo


def _log():
    """Logger loguru vinculado ao núcleo (`skyrover`)."""
    from mod_skyrover import observabilidade
    return observabilidade.get_logger("skyrover")


def _pode_escrever(nome, perfil):
    """True when the actor may create/edit clients, properties and flights.

    `administrador_geral` sempre pode; os demais precisam do papel de
    administrador no módulo `skyrover` em `tb_acesso_usuario` (quando
    existir). Perfil comum é somente leitura.
    """
    try:
        if (perfil or "") == "administrador_geral":
            return True
        return bool(autenticacao.eh_admin_do_modulo(nome, "skyrover"))
    except Exception as exc:
        try:
            _log().exception(f"telas_voos._pode_escrever: {exc}")
        except Exception:
            pass
        return False


def _fmt_bytes(valor):
    """Formata bytes em uma unidade legível (B, KB, MB, GB)."""
    try:
        n = float(valor or 0)
    except Exception:
        return "0 B"
    if n < 1024:
        return f"{int(n)} B"
    for unidade in ("KB", "MB", "GB", "TB"):
        n /= 1024.0
        if n < 1024 or unidade == "TB":
            return f"{n:.1f} {unidade}"
    return f"{int(n)} B"


def _btn(rotulo, on_click, *, icone=None, variante="primario", testid=None):
    """Cria um botão do tema e aplica o `data-testid` quando informado."""
    botao = ui_comum.botao(rotulo, variante=variante, icone=icone,
                           on_click=on_click, chave_modulo="skyrover")
    if botao is not None and testid:
        botao.props(f"data-testid={testid}")
    return botao


def _campo(rotulo, valor="", *, testid=None, multiline=False,
           placeholder=None):
    """Cria um campo de texto/área com o padrão visual do sistema."""
    if multiline:
        campo = ui.textarea(rotulo, value=valor or "")
    else:
        kwargs = {"value": valor or ""}
        if placeholder is not None:
            kwargs["placeholder"] = placeholder
        campo = ui.input(rotulo, **kwargs)
    campo.props("outlined dense").classes("w-full")
    if testid:
        campo.props(f"data-testid={testid}")
    return campo


def _erro(msg):
    """Notifica erro e registra no log (sem derrubar a tela)."""
    try:
        _log().error(f"telas_voos: {msg}")
    except Exception:
        pass
    notificar(msg, tipo="negative")


# =============================================================================
# Diálogos de cadastro
# =============================================================================

def _dialogo_novo_cliente(ator, ao_salvar):
    """Dialog to create a client (name is the only required field)."""
    with ui_comum.dialogo_formulario(
            "Novo cliente", chave_modulo="skyrover",
            descricao="O cliente é a raiz do fluxo: propriedades e voos "
                      "ficam vinculados a ele.") \
            as (dlg, _card, _miolo, grade):
        with grade:
            f_nome = _campo("Nome *", testid="voos-cliente-nome")
            f_doc = _campo("Documento", testid="voos-cliente-documento")
            f_email = _campo("E-mail", testid="voos-cliente-email")
            f_fone = _campo("Telefone", testid="voos-cliente-telefone")
            f_obs = _campo("Observação", testid="voos-cliente-observacao",
                           multiline=True)

        def salvar():
            try:
                nome_cliente = (f_nome.value or "").strip()
                if not nome_cliente:
                    notificar("Informe o nome do cliente.", tipo="warning")
                    return
                novo = voos.criar_cliente(
                    nome_cliente, documento=f_doc.value or "",
                    email=f_email.value or "", telefone=f_fone.value or "",
                    observacao=f_obs.value or "", ator=ator)
                if not novo:
                    _erro("Não foi possível criar o cliente.")
                    return
                notificar(f"Cliente '{nome_cliente}' criado.",
                          tipo="positive")
                dlg.close()
                ao_salvar()
            except Exception as exc:
                _log().exception(f"telas_voos.novo_cliente: {exc}")
                _erro("Erro inesperado ao criar o cliente.")

        ui_comum.rodape_dialogo(dlg, [("Salvar cliente", salvar)],
                                chave_modulo="skyrover")
    dlg.open()


def _dialogo_nova_propriedade(ator, ao_salvar):
    """Dialog to create a property bound to an existing client."""
    clientes = voos.listar_clientes()
    if not clientes:
        notificar("Cadastre um cliente antes de criar uma propriedade.",
                  tipo="warning")
        return
    opcoes = {c["id"]: c["nome"] for c in clientes}
    with ui_comum.dialogo_formulario(
            "Nova propriedade", chave_modulo="skyrover",
            descricao="A propriedade (área, talhão, imóvel) recebe os voos "
                      "do cliente selecionado.") \
            as (dlg, _card, _miolo, grade):
        with grade:
            f_cliente = ui.select(opcoes, label="Cliente *",
                                  value=clientes[0]["id"]) \
                .props("outlined dense").classes("w-full") \
                .props("data-testid=voos-propriedade-cliente")
            f_nome = _campo("Nome *", testid="voos-propriedade-nome")
            f_end = _campo("Endereço", testid="voos-propriedade-endereco")
            f_geo = _campo("Geometria / referência",
                           testid="voos-propriedade-geometria",
                           placeholder="ex.: polígono GeoJSON ou coordenadas")
            f_obs = _campo("Observação", testid="voos-propriedade-observacao",
                           multiline=True)

        def salvar():
            try:
                nome_prop = (f_nome.value or "").strip()
                if not nome_prop:
                    notificar("Informe o nome da propriedade.",
                              tipo="warning")
                    return
                if not f_cliente.value:
                    notificar("Selecione o cliente.", tipo="warning")
                    return
                nova = voos.criar_propriedade(
                    int(f_cliente.value), nome_prop,
                    endereco=f_end.value or "", geometria=f_geo.value or "",
                    observacao=f_obs.value or "", ator=ator)
                if not nova:
                    _erro("Não foi possível criar a propriedade.")
                    return
                notificar(f"Propriedade '{nome_prop}' criada.",
                          tipo="positive")
                dlg.close()
                ao_salvar()
            except Exception as exc:
                _log().exception(f"telas_voos.nova_propriedade: {exc}")
                _erro("Erro inesperado ao criar a propriedade.")

        ui_comum.rodape_dialogo(dlg, [("Salvar propriedade", salvar)],
                                chave_modulo="skyrover")
    dlg.open()


def _dialogo_novo_voo(ator, ao_salvar):
    """Dialog to create a flight bound to a client/property."""
    clientes = voos.listar_clientes()
    if not clientes:
        notificar("Cadastre um cliente e uma propriedade antes do voo.",
                  tipo="warning")
        return
    opcoes_clientes = {c["id"]: c["nome"] for c in clientes}
    cliente_inicial = clientes[0]
    propriedades = []
    for cliente in clientes:
        propriedades = voos.listar_propriedades(cliente_id=cliente["id"])
        if propriedades:
            cliente_inicial = cliente
            break
    if not propriedades:
        notificar("Cadastre uma propriedade para o cliente antes do voo.",
                  tipo="warning")
        return
    opcoes_prop = {p["id"]: p["nome"] for p in propriedades}

    with ui_comum.dialogo_formulario(
            "Novo voo", chave_modulo="skyrover",
            descricao="O voo guarda data, piloto, drone e GSD. Depois dele "
                      "vêm o upload das fotos/vídeos e o laudo base.") \
            as (dlg, _card, _miolo, grade):
        with grade:
            f_cliente = ui.select(opcoes_clientes, label="Cliente *",
                                  value=cliente_inicial["id"]) \
                .props("outlined dense").classes("w-full") \
                .props("data-testid=voos-voo-cliente")
            f_prop = ui.select(opcoes_prop, label="Propriedade *",
                               value=propriedades[0]["id"]) \
                .props("outlined dense").classes("w-full") \
                .props("data-testid=voos-voo-propriedade")
            f_data = ui.input("Data do voo *",
                              value=date.today().isoformat()) \
                .props("outlined dense type=date").classes("w-full") \
                .props("data-testid=voos-voo-data")
            f_piloto = _campo("Piloto", testid="voos-voo-piloto")
            f_drone = _campo("Drone", valor="Skyrover X1",
                             testid="voos-voo-drone")
            f_gsd = ui.number("GSD (cm/px)", value=None, min=0,
                              format="%.2f") \
                .props("outlined dense").classes("w-full") \
                .props("data-testid=voos-voo-gsd")
            f_status = ui.select(
                {"rascunho": "Rascunho", "em_captura": "Em captura",
                 "capturado": "Capturado"},
                label="Status", value="rascunho") \
                .props("outlined dense").classes("w-full") \
                .props("data-testid=voos-voo-status")
            f_obs = _campo("Observação", testid="voos-voo-observacao",
                           multiline=True)

        def _cliente_mudou(evento):
            try:
                props = voos.listar_propriedades(cliente_id=evento.value)
                f_prop.options = {p["id"]: p["nome"] for p in props}
                f_prop.value = next(iter(f_prop.options), None)
                f_prop.update()
            except Exception as exc:
                _log().exception(f"telas_voos.novo_voo.cliente_mudou: {exc}")

        f_cliente.on_value_change(_cliente_mudou)

        def salvar():
            try:
                if not f_cliente.value:
                    notificar("Selecione o cliente.", tipo="warning")
                    return
                if not f_prop.value:
                    notificar("Selecione a propriedade.", tipo="warning")
                    return
                if not (f_data.value or "").strip():
                    notificar("Informe a data do voo.", tipo="warning")
                    return
                novo = voos.criar_voo(
                    int(f_cliente.value), int(f_prop.value),
                    data_voo=f_data.value or "",
                    piloto=f_piloto.value or "", drone=f_drone.value or "",
                    gsd_cm=f_gsd.value, status=f_status.value or "rascunho",
                    observacao=f_obs.value or "", ator=ator)
                if not novo:
                    _erro("Não foi possível criar o voo.")
                    return
                notificar(f"Voo #{novo} criado.", tipo="positive")
                dlg.close()
                ao_salvar()
            except Exception as exc:
                _log().exception(f"telas_voos.novo_voo: {exc}")
                _erro("Erro inesperado ao criar o voo.")

        ui_comum.rodape_dialogo(dlg, [("Salvar voo", salvar)],
                                chave_modulo="skyrover")
    dlg.open()


# =============================================================================
# Diálogo de detalhe: upload, mídias e laudos
# =============================================================================

def _dialogo_voo(voo_id, ator, pode_editar, ao_mudar):
    """Dialog with the flight details, upload, media list and reports."""
    voo = voos.obter_voo(voo_id)
    if not voo:
        _erro("Voo não encontrado.")
        return

    with ui_comum.dialogo_formulario(
            f"Voo #{voo_id} — mídias e laudo", chave_modulo="skyrover") \
            as (dlg, _card, miolo, _grade):
        with miolo:
            ui.label(
                f"Cliente: {voo.get('cliente_nome') or '-'} · "
                f"Propriedade: {voo.get('propriedade_nome') or '-'}") \
                .classes("text-subtitle1")
            ui.label(
                f"Data: {voo.get('data_voo') or '-'} · Piloto: "
                f"{voo.get('piloto') or '-'} · Drone: "
                f"{voo.get('drone') or '-'} · Status: "
                f"{voo.get('status') or '-'}") \
                .classes("text-caption text-grey-7")
            if voo.get("observacao"):
                ui.label(voo["observacao"]).classes(
                    "text-body2 text-grey-8")

            ui.separator()

            @ui.refreshable
            def _midias():
                """Renders the uploaded media of this flight."""
                itens = voos.listar_midias_do_voo(voo_id)
                ui.label(f"Mídias ({len(itens)})").classes(
                    "text-subtitle2")
                if not itens:
                    ui.label("Nenhuma foto ou vídeo enviado ainda.") \
                        .classes("text-caption text-grey-7")
                    return
                for item in itens:
                    with ui.row().classes(
                            "w-full items-center justify-between "
                            "flex-wrap border rounded-lg px-3 py-1") \
                            .props(f"data-testid=voos-midia-{item['id']}"):
                        with ui.column().classes("min-w-0").style("gap: 0"):
                            ui.label(item.get("nome_seguro") or "-") \
                                .classes("text-body2 ellipsis")
                            ui.label(
                                f"{_fmt_bytes(item.get('tamanho_bytes'))} · "
                                f"{item.get('mime') or 'tipo desconhecido'} · "
                                f"sha256 {str(item.get('hash_sha256') or '')[:16]}…") \
                                .classes("text-caption text-grey-7")

            if pode_editar:
                async def receber_upload(evento):
                    """Saves one uploaded file outside the database.

                    Lê o conteúdo do `ui.upload`, grava em
                    `midia/<voo_id>/` com nome seguro e SHA-256, registra
                    a captura/mídia no banco central e atualiza a lista.
                    """
                    try:
                        conteudo = await evento.file.read()
                        if not conteudo:
                            notificar("Arquivo vazio — envio ignorado.",
                                      tipo="warning")
                            return
                        if len(conteudo) > _TAMANHO_MAX_UPLOAD:
                            notificar(
                                "Arquivo maior que 512 MB — envio ignorado.",
                                tipo="warning")
                            return
                        resultado = voos.salvar_arquivo_midia(
                            voo_id, evento.file.name, conteudo,
                            mime=evento.file.content_type or "", ator=ator)
                        if not resultado:
                            _erro("Não foi possível salvar o arquivo.")
                            return
                        notificar(
                            f"{resultado['nome_seguro']} enviado "
                            f"({_fmt_bytes(resultado['tamanho_bytes'])}).",
                            tipo="positive")
                        _midias.refresh()
                        ao_mudar()
                    except Exception as exc:
                        _log().exception(
                            f"telas_voos.receber_upload({voo_id}): {exc}")
                        _erro("Falha ao receber o arquivo.")

                ui.upload(on_upload=receber_upload, auto_upload=True,
                          multiple=True, max_file_size=_TAMANHO_MAX_UPLOAD) \
                    .props('accept="image/*,video/*" '
                           'label="Enviar fotos/vídeos" flat dense') \
                    .classes("w-full") \
                    .props("data-testid=voos-upload")
            else:
                ui.label("Somente leitura: seu perfil não pode enviar mídia.") \
                    .classes("text-caption text-grey-7")

            _midias()

            ui.separator()

            @ui.refreshable
            def _analises_ia():
                """Mostra o resultado do pipeline de imagem já armazenado."""
                itens = voos.listar_analises_ia(voo_id=voo_id)
                ui.label(f"Análises de imagem ({len(itens)})").classes(
                    "text-subtitle2")
                if not itens:
                    ui.label(
                        "Nenhuma análise executada. Use 'Analisar mídias' "
                        "para rodar o baseline/modelo sobre as fotos."
                    ).classes("text-caption text-grey-7")
                    return
                for item in itens:
                    try:
                        ocorrencias = __import__("json").loads(
                            item.get("ocorrencias_json") or "[]")
                    except Exception:
                        ocorrencias = []
                    with ui.expansion(
                            f"#{item['id']} · {item.get('modulo')} · "
                            f"{item.get('modelo') or 'baseline'}",
                            icon="analytics").classes("w-full") \
                            .props(f"data-testid=voos-analise-{item['id']}"):
                        ui.label(
                            f"Versão: {item.get('versao') or '-'} · "
                            f"Revisão humana: "
                            f"{'sim' if item.get('revisao_humana') else 'não'}"
                        ).classes("text-caption text-grey-7")
                        ui.label(item.get("resumo") or "") \
                            .classes("text-body2 whitespace-pre-line")
                        if ocorrencias:
                            ui.label(
                                f"{len(ocorrencias)} ocorrência(s) automática(s)"
                            ).classes("text-caption text-grey-7")

            _analises_ia()

            ui.separator()

            @ui.refreshable
            def _laudos():
                """Renders the reports already generated for this flight."""
                itens = voos.listar_laudos(voo_id=voo_id)
                ui.label(f"Laudos ({len(itens)})").classes("text-subtitle2")
                if not itens:
                    ui.label("Nenhum laudo gerado para este voo.") \
                        .classes("text-caption text-grey-7")
                    return
                for item in itens:
                    with ui.expansion(
                            f"#{item['id']} — {item.get('titulo') or 'Laudo'}",
                            icon="description").classes("w-full") \
                            .props(f"data-testid=voos-laudo-{item['id']}"):
                        ui.label(
                            f"Status: {item.get('status') or '-'} · "
                            f"Gerado em: {item.get('gerado_em') or '-'}") \
                            .classes("text-caption text-grey-7")
                        ui.label(item.get("resumo") or "") \
                            .classes("text-body2 whitespace-pre-line")
                        caminho_pdf = item.get("caminho_pdf")
                        if caminho_pdf:
                            try:
                                rel = os.path.relpath(
                                    caminho_pdf, voos.diretorio_laudos()
                                ).replace("\\", "/")
                                ui.link("Baixar PDF", f"/laudos/{rel}") \
                                    .props(
                                        f"data-testid=voos-laudo-pdf-{item['id']}"
                                    )
                            except Exception:
                                pass

            _laudos()

            def processar_multiespectral():
                """Processa bandas R/G/B/NIR/RE do voo e mostra as saídas."""
                if not pode_editar:
                    notificar("Seu perfil não pode processar bandas.",
                              tipo="warning")
                    return
                try:
                    resumo = voos.processar_multiespectral(
                        voo_id, ator=ator)
                    if not resumo:
                        notificar(
                            "Nenhum grupo de bandas encontrado. Nomeie os "
                            "arquivos com sufixo _R, _G, _B, _NIR e _RE.",
                            tipo="warning")
                        return
                    with ui.dialog() as _dlg, ui.card().classes(
                            "w-full max-w-[720px]"):
                        ui.label("Processamento multiespectral").classes(
                            "text-h6")
                        for base, item in resumo.items():
                            with ui.expansion(base, icon="layers") \
                                    .classes("w-full"):
                                if item.get("erro"):
                                    ui.label(item["erro"]).classes(
                                        "text-body2 text-orange-9")
                                    continue
                                ui.label(
                                    f"Bandas: {', '.join(item.get('bandas') or [])}"
                                ).classes("text-caption text-grey-7")
                                ui.label(f"JSON: {item.get('json')}") \
                                    .classes("text-caption")
                                for nome, caminho in (
                                        item.get("tiffs") or {}).items():
                                    ui.label(f"{nome}: {caminho}") \
                                        .classes("text-caption")
                        ui_comum.botao("Fechar", variante="texto",
                                       on_click=_dlg.close,
                                       chave_modulo="skyrover")
                    _dlg.open()
                except Exception as exc:
                    _log().exception(
                        f"telas_voos.processar_multiespectral: {exc}")
                    _erro("Erro ao processar as bandas.")

            def analisar_midias():
                """Executa o pipeline de imagem no voo e mostra o resumo."""
                if not pode_editar:
                    notificar("Seu perfil não pode executar análise.",
                              tipo="warning")
                    return
                _opcoes = {
                    "skyrover": "Núcleo (visão geral)",
                    "agro": "Agropecuário",
                    "vistoria_predial": "Vistoria Predial",
                    "seguranca": "Segurança Pública",
                    "ambiental": "Ambiental",
                    "obras": "Obras",
                    "mapeamento": "Mapeamento",
                    "defesa_civil": "Defesa Civil",
                    "inspecao_industrial": "Inspeção Industrial",
                    "eventos": "Eventos",
                }
                with ui.dialog() as _dlg, ui.card().classes(
                        "w-full max-w-[560px]"):
                    ui.label("Analisar mídias do voo").classes("text-h6")
                    ui.label(
                        "O baseline RGB gera métricas e ocorrências "
                        "conservadoras. Segurança Pública exige detector "
                        "homologado e revisão humana."
                    ).classes("text-caption text-grey-7")
                    _modulo = ui.select(
                        _opcoes, label="Módulo de análise",
                        value="skyrover").props("outlined dense") \
                        .classes("w-full") \
                        .props("data-testid=voos-analise-modulo")

                    def _executar():
                        try:
                            resumo = voos.executar_analise_ia(
                                voo_id, _modulo.value or "skyrover",
                                ator=ator)
                            notificar(
                                f"Análise: {resumo['analisadas']}/"
                                f"{resumo['total']} imagem(ns), "
                                f"{resumo['ocorrencias']} ocorrência(s).",
                                tipo="positive" if resumo["analisadas"]
                                else "warning")
                            _dlg.close()
                            _analises_ia.refresh()
                            ao_mudar()
                        except Exception as exc:
                            _log().exception(
                                f"telas_voos.analisar_midias: {exc}")
                            _erro("Erro ao analisar as mídias.")

                    with ui.row().classes("w-full justify-end") \
                            .style("gap: .5rem"):
                        ui_comum.botao("Cancelar", variante="texto",
                                       on_click=_dlg.close,
                                       chave_modulo="skyrover")
                        ui_comum.botao("Executar", icone="play_arrow",
                                       on_click=_executar,
                                       chave_modulo="skyrover") \
                            .props("data-testid=voos-analise-executar")
                _dlg.open()

            def gerar_laudo():
                """Creates the textual Onda 1 report for this flight."""
                if not pode_editar:
                    notificar("Seu perfil não pode gerar laudo.",
                              tipo="warning")
                    return
                try:
                    novo = voos.criar_laudo_base(voo_id, ator=ator)
                    if not novo:
                        _erro("Não foi possível gerar o laudo base.")
                        return
                    notificar(f"Laudo base #{novo} gerado.",
                              tipo="positive")
                    _laudos.refresh()
                    ao_mudar()
                except Exception as exc:
                    _log().exception(
                        f"telas_voos.gerar_laudo({voo_id}): {exc}")
                    _erro("Erro inesperado ao gerar o laudo.")

        acoes = []
        if pode_editar:
            acoes.append(("Analisar mídias (IA)", analisar_midias))
            acoes.append(("Processar multiespectral",
                          processar_multiespectral))
            acoes.append(("Gerar laudo PDF", gerar_laudo))
        ui_comum.rodape_dialogo(dlg, acoes, chave_modulo="skyrover",
                                classes_extra="mt-3")
    dlg.open()


# =============================================================================
# Tela principal
# =============================================================================

def mostrar_tela(nome, perfil=""):
    """Renders the `/voos` screen for an authenticated user.

    Lista os voos com cliente/propriedade/status e oferece os diálogos de
    cadastro apenas para quem pode escrever. O fluxo completo
    (cliente → propriedade → voo → upload → laudo) acontece em diálogos.
    """
    try:
        pode_editar = _pode_escrever(nome, perfil)
        estado = {"busca": ""}

        cabecalho(
            "Voos e laudos",
            "Cliente → propriedade → voo → upload → laudo base",
            chave_modulo="skyrover")

        if not pode_editar:
            ui.label(
                "Seu perfil está em modo somente leitura. Cadastros, uploads "
                "e laudos exigem administrador geral ou administrador do "
                "núcleo.").classes(
                "text-caption text-orange-9 bg-orange-1 p-2 rounded w-full")

        def _atualizar_busca(evento):
            estado["busca"] = (evento.value or "") if evento else ""
            _lista.refresh()

        with ui.row().classes(
                "w-full items-center justify-between flex-wrap") \
                .style("gap: 0.5rem"):
            busca = campo_busca(
                "Buscar por cliente, propriedade, piloto ou status",
                on_change=_atualizar_busca)
            busca.props("data-testid=voos-busca")
            with ui.row().classes("items-center flex-wrap") \
                    .style("gap: 0.5rem"):
                if pode_editar:
                    _btn("Novo cliente",
                         lambda: _dialogo_novo_cliente(
                             nome, _lista.refresh),
                         icone="person_add", variante="contorno",
                         testid="voos-novo-cliente")
                    _btn("Nova propriedade",
                         lambda: _dialogo_nova_propriedade(
                             nome, _lista.refresh),
                         icone="landscape", variante="contorno",
                         testid="voos-nova-propriedade")
                    _btn("Novo voo",
                         lambda: _dialogo_novo_voo(nome, _lista.refresh),
                         icone="flight_takeoff",
                         testid="voos-novo-voo")

        @ui.refreshable
        def _lista():
            """Renders the flight cards with client, property and status."""
            try:
                itens = voos.listar_voos(busca=estado["busca"])
            except Exception as exc:
                _log().exception(f"telas_voos._lista: {exc}")
                itens = []
            if not itens:
                with ui.card().classes("w-full"):
                    ui.label("Nenhum voo cadastrado ainda.").classes(
                        "text-body1")
                    if pode_editar:
                        ui.label(
                            "Comece cadastrando o cliente, depois a "
                            "propriedade e o voo.").classes(
                            "text-caption text-grey-7")
                return
            for voo in itens:
                cor = _CORES_STATUS.get(voo.get("status") or "",
                                        "grey-7")
                with ui.card().classes("w-full") \
                        .props(f"data-testid=voos-card-{voo['id']}"):
                    with ui.row().classes(
                            "w-full items-center justify-between "
                            "flex-wrap").style("gap: 0.5rem"):
                        with ui.column().style("gap: 0"):
                            ui.label(
                                f"Voo #{voo['id']} — "
                                f"{voo.get('cliente_nome') or 'sem cliente'}"
                                f" / {voo.get('propriedade_nome') or 'sem propriedade'}") \
                                .classes("text-subtitle1")
                            ui.label(
                                f"{voo.get('data_voo') or 'sem data'} · "
                                f"Piloto: {voo.get('piloto') or '-'} · "
                                f"Drone: {voo.get('drone') or '-'}") \
                                .classes("text-caption text-grey-7")
                        ui.badge(voo.get("status") or "-") \
                            .props(f"color={cor}")
                    with ui.row().classes("items-center flex-wrap") \
                            .style("gap: 0.5rem"):
                        _btn(
                            "Mídias e upload",
                            lambda vid=voo["id"]: _dialogo_voo(
                                vid, nome, pode_editar, _lista.refresh),
                            icone="perm_media", variante="contorno",
                            testid=f"voos-midias-{voo['id']}")

        _lista()
    except Exception as exc:
        try:
            _log().exception(f"telas_voos.mostrar_tela: {exc}")
        except Exception:
            pass
        notificar("Erro ao carregar a tela de voos.", tipo="error")
