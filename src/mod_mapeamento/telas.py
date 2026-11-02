"""Telas do módulo Mapeamento (rota /mapeamento).

EN: Mapping screens — analysis list, creation, geospatial products and report
conclusion.

PT-BR: Telas de Mapeamento — lista de análises, criação, produtos geoespaciais
e conclusão do laudo. Renderiza dentro do layout de `pagina_restrita`; não
monta menu.
"""
from nicegui import ui

from mod_skyrover import observabilidade
from mod_skyrover.tema_modulo import ler_tema, notificar
from mod_skyrover.ui_comum import botao
from mod_skyrover import ui_analise

from mod_mapeamento import bd_manipulador as bd

_COR = "#1565C0"


def _log():
    return observabilidade.get_logger("mapeamento")


def _rotulo_status(status):
    return {"rascunho": "Rascunho", "em_revisao": "Em revisão",
            "concluido": "Concluído"}.get(status or "", status or "—")


def _cor_status(status):
    return {"rascunho": "grey", "em_revisao": "orange",
            "concluido": "green"}.get(status or "", "grey")


def mostrar_tela(user_nome: str, perfil_global: str = ""):
    """Monta a tela principal do módulo Mapeamento."""
    try:
        _mostrar(user_nome, perfil_global)
    except Exception as e:
        try:
            _log().exception(f"mostrar_tela: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao carregar o módulo Mapeamento.", tipo="error")


def _mostrar(user_nome: str, perfil_global: str):
    bd.init_db()
    tema = ler_tema(bd.CHAVE_MODULO, cor_botao=_COR,
                    cor_texto_botao="#FFFFFF")
    ui.colors(primary=tema["cor_botao"])
    estado = {"busca": ""}
    lista = ui.column().classes("w-full").style("gap: .75rem")

    def _atualizar():
        try:
            lista.clear()
            with lista:
                _render_lista(user_nome, perfil_global, estado["busca"],
                              _atualizar)
        except Exception as e:
            try:
                _log().exception(f"_atualizar: falha | {e}")
            except Exception:
                pass
            notificar("Erro ao atualizar a lista de análises.",
                      tipo="error")

    with ui.column().classes("w-full").style("gap: 1.25rem"):
        with ui.row().classes("w-full items-center").style("gap: 1rem"):
            with ui.column().style("gap: 0; min-width: 0"):
                ui.label("Mapeamento").classes("text-h5")
                ui.label(
                    "Ortomosaico, topografia e volumetria com catálogo de "
                    "produtos geoespaciais por voo."
                ).classes("text-caption text-grey-7")
            ui.space()
            botao("Nova análise", icone="add", variante="solido",
                  chave_modulo=bd.CHAVE_MODULO,
                  on_click=lambda: _dialogo_nova(user_nome, _atualizar)
                  ).props("data-testid=mapeamento-nova-analise")

        r = bd.resumo()
        with ui.row().classes("w-full").style("gap: 1rem"):
            for rotulo, valor, icone in (
                    ("Análises", r["total"], "analytics"),
                    ("Concluídas", r["concluido"], "check_circle"),
                    ("Em revisão", r["em_revisao"], "rate_review"),
                    ("Produtos", r["produtos"], "layers")):
                with ui.card().style("min-width: 180px; flex: 1 1 180px"):
                    with ui.row().classes("items-center").style("gap: .5rem"):
                        ui.icon(icone).classes("text-2xl")
                        with ui.column().style("gap: 0"):
                            ui.label(str(valor)).classes("text-h5")
                            ui.label(rotulo).classes(
                                "text-caption text-grey-7")

        with ui.row().classes("w-full items-center").style("gap: .5rem"):
            busca = ui.input(
                "Buscar por tipo, status ou resumo").props(
                "outlined dense clearable").classes("w-80") \
                .props("data-testid=mapeamento-busca")
            busca.on_value_change(
                lambda e: (estado.update(busca=e.value or ""),
                           _atualizar()))
        ui.separator()
        _atualizar()


def _render_lista(ator, perfil_global, busca, refresh):
    analises = bd.listar_analises(busca)
    if not analises:
        with ui.card().classes("w-full"):
            ui.label("Nenhuma análise de mapeamento cadastrada.").classes(
                "text-body1")
            ui.label(
                "Cadastre um voo em /voos e crie a primeira análise de "
                "mapeamento."
            ).classes("text-caption text-grey-7")
        return
    for linha in analises:
        (aid, voo_id, _cliente_id, _prop_id, area_ha, gsd_cm, tipo, status,
         resumo, criado_por, criado_em) = linha
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center").style("gap: 1rem"):
                with ui.column().style("gap: 0; min-width: 0; flex: 1 1 0"):
                    ui.label(
                        f"Voo #{voo_id} · {tipo or 'tipo não informado'}"
                    ).classes("text-subtitle1")
                    ui.label(
                        f"{float(area_ha or 0):.2f} ha · GSD "
                        f"{float(gsd_cm or 0):.2f} cm/px · "
                        f"{criado_por or '—'} · {criado_em or '—'}"
                    ).classes("text-caption text-grey-7")
                ui.badge(_rotulo_status(status)).props(
                    f"color={_cor_status(status)}")
            if resumo:
                ui.label(resumo).classes("text-body2")
            produtos = bd.listar_produtos(aid)
            for p in produtos:
                (pid, _aid, nome, ptipo, caminho, hash_sha256, confianca,
                 _criado) = p
                with ui.column().style("gap: 0"):
                    ui.label(
                        f"{nome} · {ptipo} · confiança "
                        f"{float(confianca or 0):.2f}"
                    ).classes("text-body2")
                    if caminho:
                        ui.label(caminho).classes(
                            "text-caption text-grey-7")
                    if hash_sha256:
                        ui.label(f"sha256: {hash_sha256}").classes(
                            "text-caption text-grey-7")
            if produtos:
                ui.label(f"{len(produtos)} produto(s) registrado(s)").classes(
                    "text-caption text-grey-7")
            ui_analise.bloco_analise(ator, voo_id, bd.CHAVE_MODULO)
            with ui.row().style("gap: .5rem"):
                botao("Produto", icone="add_box", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid, t=tipo: _dialogo_produto(
                          ator, i, t, refresh)
                      ).props(f"data-testid=mapeamento-produto-{aid}")
                botao("Concluir", icone="task_alt", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid: _concluir(ator, i, refresh)
                      ).props(f"data-testid=mapeamento-concluir-{aid}")


def _dialogo_nova(ator, refresh):
    try:
        from mod_skyrover import voos
        voos_disponiveis = voos.listar_voos()
    except Exception as e:
        try:
            _log().exception(f"_dialogo_nova: falha ao listar voos | {e}")
        except Exception:
            pass
        voos_disponiveis = []
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[720px]"):
        ui.label("Nova análise de mapeamento").classes("text-h6")
        if not voos_disponiveis:
            ui.label(
                "Nenhum voo cadastrado. Cadastre um voo em /voos antes de "
                "criar a análise."
            ).classes("text-body2 text-orange-9")
            botao("Fechar", variante="texto", on_click=dlg.close)
            dlg.open()
            return
        opcoes = {}
        for v in voos_disponiveis:
            vid = v.get("id")
            opcoes[vid] = (
                f"#{vid} · {v.get('data_voo') or 'sem data'} · "
                f"{v.get('cliente_nome') or 'sem cliente'} · "
                f"{v.get('propriedade_nome') or 'sem propriedade'}")
        voo = ui.select(opcoes, label="Voo",
                        value=next(iter(opcoes))).props(
            "outlined dense").classes("w-full") \
            .props("data-testid=mapeamento-voo")
        with ui.row().classes("w-full").style("gap: .75rem"):
            area = ui.number("Área (ha)", value=0, format="%.2f").props(
                "outlined dense").classes("w-full") \
                .props("data-testid=mapeamento-area")
            gsd = ui.number("GSD (cm/px)", value=0, format="%.2f").props(
                "outlined dense").classes("w-full") \
                .props("data-testid=mapeamento-gsd")
        tipo = ui.select({t: t for t in bd.TIPOS}, label="Tipo",
                         value=bd.TIPOS[0]).props(
            "outlined dense").classes("w-full") \
            .props("data-testid=mapeamento-tipo")
        resumo = ui.textarea("Resumo / observações").props(
            "outlined dense").classes("w-full") \
            .props("data-testid=mapeamento-resumo")

        def salvar():
            try:
                ok, msg = bd.criar_analise(
                    ator, voo.value, area.value or 0, gsd.value or 0,
                    tipo.value or "outro", resumo.value or "")
                if ok:
                    notificar("Análise criada.", tipo="positive")
                    dlg.close()
                    refresh()
                else:
                    notificar(str(msg), tipo="negative")
            except Exception as e:
                try:
                    _log().exception(f"salvar análise: falha | {e}")
                except Exception:
                    pass
                notificar("Erro ao salvar a análise.", tipo="error")

        with ui.row().classes("w-full justify-end").style("gap: .5rem"):
            botao("Cancelar", variante="texto", on_click=dlg.close)
            botao("Salvar", icone="save", chave_modulo=bd.CHAVE_MODULO,
                  on_click=salvar).props("data-testid=mapeamento-salvar")
    dlg.open()


def _dialogo_produto(ator, analise_id, tipo_analise, refresh):
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[640px]"):
        ui.label(f"Produto · análise #{analise_id}").classes("text-h6")
        ui.label(f"Tipo da análise: {tipo_analise or '—'}").classes(
            "text-caption text-grey-7")
        nome = ui.input("Nome do produto").props(
            "outlined dense").classes("w-full") \
            .props("data-testid=mapeamento-produto-nome")
        tipo = ui.select({t: t for t in bd.TIPOS_PRODUTO}, label="Formato",
                         value=bd.TIPOS_PRODUTO[0]).props(
            "outlined dense").classes("w-full") \
            .props("data-testid=mapeamento-produto-tipo")
        caminho = ui.input("Caminho do arquivo").props(
            "outlined dense").classes("w-full") \
            .props("data-testid=mapeamento-produto-caminho")
        with ui.row().classes("w-full").style("gap: .75rem"):
            hash_sha256 = ui.input("SHA-256").props(
                "outlined dense").classes("w-full") \
                .props("data-testid=mapeamento-produto-hash")
            confianca = ui.number("Confiança (0-1)", value=0,
                                  format="%.2f").props(
                "outlined dense").classes("w-full") \
                .props("data-testid=mapeamento-produto-confianca")

        def salvar():
            try:
                ok, msg = bd.adicionar_produto(
                    ator, analise_id, nome.value or "", tipo.value or "outro",
                    caminho.value or "", hash_sha256.value or "",
                    confianca.value or 0)
                if ok:
                    notificar("Produto registrado.", tipo="positive")
                    dlg.close()
                    refresh()
                else:
                    notificar(str(msg), tipo="negative")
            except Exception as e:
                try:
                    _log().exception(f"salvar produto: falha | {e}")
                except Exception:
                    pass
                notificar("Erro ao registrar o produto.", tipo="error")

        with ui.row().classes("w-full justify-end").style("gap: .5rem"):
            botao("Cancelar", variante="texto", on_click=dlg.close)
            botao("Registrar", icone="save", chave_modulo=bd.CHAVE_MODULO,
                  on_click=salvar).props("data-testid=mapeamento-registrar")
    dlg.open()


def _concluir(ator, analise_id, refresh):
    try:
        ok, msg = bd.atualizar_status(
            analise_id, "concluido",
            resumo="Laudo de mapeamento concluído. Conferir os produtos e "
                   "os hashes antes da entrega.")
        notificar(str(msg), tipo="positive" if ok else "negative")
        if ok:
            refresh()
    except Exception as e:
        try:
            _log().exception(f"concluir: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao concluir a análise.", tipo="error")
