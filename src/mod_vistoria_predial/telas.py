"""Telas do módulo Vistoria Predial (rota /vistoria-predial)."""
from nicegui import ui

from mod_tisosdocfly import observabilidade
from mod_tisosdocfly.tema_modulo import ler_tema, notificar
from mod_tisosdocfly.ui_comum import botao
from mod_tisosdocfly import ui_analise

from mod_vistoria_predial import bd_manipulador as bd


def _log():
    return observabilidade.get_logger("vistoria_predial")


def _rotulo(status):
    return {"rascunho": "Rascunho", "em_revisao": "Em revisão",
            "concluido": "Concluído"}.get(status or "", status or "—")


def _cor(status):
    return {"rascunho": "grey", "em_revisao": "orange",
            "concluido": "green"}.get(status or "", "grey")


def mostrar_tela(user_nome: str, perfil_global: str = ""):
    try:
        _mostrar(user_nome, perfil_global)
    except Exception as e:
        try:
            _log().exception(f"mostrar_tela: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao carregar o módulo Vistoria Predial.",
                  tipo="error")


def _mostrar(user_nome, perfil_global):
    bd.init_db()
    tema = ler_tema(bd.CHAVE_MODULO, cor_botao="#1565C0",
                    cor_texto_botao="#FFFFFF")
    ui.colors(primary=tema["cor_botao"])
    lista = ui.column().classes("w-full").style("gap: .75rem")

    def _atualizar():
        try:
            lista.clear()
            with lista:
                _render_lista(user_nome, _atualizar)
        except Exception as e:
            try:
                _log().exception(f"_atualizar: falha | {e}")
            except Exception:
                pass
            notificar("Erro ao atualizar as vistorias.", tipo="error")

    with ui.column().classes("w-full").style("gap: 1.25rem"):
        with ui.row().classes("w-full items-center").style("gap: 1rem"):
            with ui.column().style("gap: 0; min-width: 0"):
                ui.label("Vistoria Predial").classes("text-h5")
                ui.label(
                    "Laudo de fachada, telhado, estruturas e patologias "
                    "aparentes, com comparativo entre vistorias."
                ).classes("text-caption text-grey-7")
            ui.space()
            botao("Nova vistoria", icone="add", chave_modulo=bd.CHAVE_MODULO,
                  on_click=lambda: _dialogo_nova(user_nome, _atualizar)
                  ).props("data-testid=vistoria-nova")

        r = bd.resumo()
        with ui.row().classes("w-full").style("gap: 1rem"):
            for rotulo, valor, icone in (
                    ("Vistorias", r["total"], "apartment"),
                    ("Concluídas", r["concluido"], "check_circle"),
                    ("Em revisão", r["em_revisao"], "fact_check"),
                    ("Patologias", r["patologias"], "warning")):
                with ui.card().style("min-width: 180px; flex: 1 1 180px"):
                    with ui.row().classes("items-center").style("gap: .5rem"):
                        ui.icon(icone).classes("text-2xl")
                        with ui.column().style("gap: 0"):
                            ui.label(str(valor)).classes("text-h5")
                            ui.label(rotulo).classes(
                                "text-caption text-grey-7")
        ui.separator()
        _atualizar()


def _render_lista(ator, refresh):
    vistorias = bd.listar_vistorias()
    if not vistorias:
        with ui.card().classes("w-full"):
            ui.label("Nenhuma vistoria cadastrada.").classes("text-body1")
            ui.label("Cadastre um voo em /voos e crie a primeira vistoria.")\
                .classes("text-caption text-grey-7")
        return
    for linha in vistorias:
        (vid, voo_id, _cliente_id, _prop_id, imovel, tipo, status, resumo,
         criado_por, criado_em) = linha
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center").style("gap: 1rem"):
                with ui.column().style("gap: 0; min-width: 0; flex: 1 1 0"):
                    ui.label(f"Voo #{voo_id} · {imovel or 'imóvel não informado'}")\
                        .classes("text-subtitle1")
                    ui.label(
                        f"{tipo} · {criado_por or '—'} · {criado_em or '—'}"
                    ).classes("text-caption text-grey-7")
                ui.badge(_rotulo(status)).props(f"color={_cor(status)}")
            if resumo:
                ui.label(resumo).classes("text-body2")
            patologias = bd.listar_patologias(vid)
            if patologias:
                ui.label(f"{len(patologias)} patologia(s) registrada(s)")\
                    .classes("text-caption text-grey-7")
            ui_analise.bloco_analise(ator, voo_id, bd.CHAVE_MODULO)
            with ui.row().style("gap: .5rem"):
                botao("Patologia", icone="add_alert", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=vid, im=imovel:
                      _dialogo_patologia(ator, i, im, refresh)
                      ).props(f"data-testid=vistoria-patologia-{vid}")
                botao("Concluir", icone="task_alt", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=vid: _concluir(ator, i, refresh)
                      ).props(f"data-testid=vistoria-concluir-{vid}")


def _dialogo_nova(ator, refresh):
    try:
        from mod_tisosdocfly import voos
        disponiveis = voos.listar_voos()
    except Exception:
        disponiveis = []
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[720px]"):
        ui.label("Nova vistoria predial").classes("text-h6")
        if not disponiveis:
            ui.label(
                "Nenhum voo cadastrado. Cadastre um voo em /voos antes de "
                "criar a vistoria."
            ).classes("text-body2 text-orange-9")
            botao("Fechar", variante="texto", on_click=dlg.close)
            dlg.open()
            return
        opcoes = {}
        for v in disponiveis:
            cliente = v[10] if len(v) > 10 else ""
            opcoes[v[0]] = f"#{v[0]} · {v[3] or 'sem data'} · {cliente}"
        voo = ui.select(opcoes, label="Voo",
                        value=next(iter(opcoes))).props(
            "outlined dense").classes("w-full") \
            .props("data-testid=vistoria-voo")
        imovel = ui.input("Imóvel / endereço").props(
            "outlined dense").classes("w-full") \
            .props("data-testid=vistoria-imovel")
        tipo = ui.select({t: t for t in bd.TIPOS}, label="Tipo",
                         value="completa").props(
            "outlined dense").classes("w-full")
        resumo = ui.textarea("Resumo / observações").props(
            "outlined dense").classes("w-full")

        def salvar():
            ok, msg = bd.criar_vistoria(
                ator, voo.value, imovel.value or "", tipo.value or "completa",
                resumo.value or "")
            if ok:
                notificar("Vistoria criada.", tipo="positive")
                dlg.close()
                refresh()
            else:
                notificar(str(msg), tipo="negative")

        with ui.row().classes("w-full justify-end").style("gap: .5rem"):
            botao("Cancelar", variante="texto", on_click=dlg.close)
            botao("Salvar", icone="save", chave_modulo=bd.CHAVE_MODULO,
                  on_click=salvar).props("data-testid=vistoria-salvar")
    dlg.open()


def _dialogo_patologia(ator, vistoria_id, imovel, refresh):
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[640px]"):
        ui.label(f"Patologia · vistoria #{vistoria_id}").classes("text-h6")
        ui.label(f"Imóvel: {imovel or '—'}").classes(
            "text-caption text-grey-7")
        tipo = ui.select({p: p for p in bd.PATOLOGIAS}, label="Patologia",
                         value=bd.PATOLOGIAS[0]).props(
            "outlined dense").classes("w-full")
        severidade = ui.select({s: s for s in bd.SEVERIDADES},
                               label="Severidade",
                               value=bd.SEVERIDADES[0]).props(
            "outlined dense").classes("w-full")
        area = ui.number("Área afetada (m²)", value=0, format="%.2f").props(
            "outlined dense").classes("w-full")
        descricao = ui.textarea("Descrição / localização").props(
            "outlined dense").classes("w-full")
        revisao = ui.checkbox("Revisado por humano", value=False)

        def salvar():
            ok, msg = bd.adicionar_patologia(
                ator, vistoria_id, tipo.value, severidade.value,
                area.value or 0, descricao.value or "",
                1 if revisao.value else 0)
            if ok:
                notificar("Patologia registrada.", tipo="positive")
                dlg.close()
                refresh()
            else:
                notificar(str(msg), tipo="negative")

        with ui.row().classes("w-full justify-end").style("gap: .5rem"):
            botao("Cancelar", variante="texto", on_click=dlg.close)
            botao("Registrar", icone="save", chave_modulo=bd.CHAVE_MODULO,
                  on_click=salvar)
    dlg.open()


def _concluir(ator, vistoria_id, refresh):
    ok, msg = bd.atualizar_status(
        vistoria_id, "concluido",
        resumo="Vistoria concluída. Revisar as patologias e anexar as "
               "evidências do voo.")
    notificar(str(msg), tipo="positive" if ok else "negative")
    if ok:
        refresh()
