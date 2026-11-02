"""Telas do módulo Segurança Pública (rota /seguranca).

EN: Public safety screens — triage analyses with explicit human review.

PT-BR: Telas de Segurança Pública — análises de triagem com revisão humana
explícita. O módulo NÃO emite decisão de culpa; ele organiza evidências para
revisão de uma pessoa autorizada.
"""
from nicegui import ui

from mod_skyrover import observabilidade
from mod_skyrover.tema_modulo import ler_tema, notificar
from mod_skyrover.ui_comum import botao
from mod_skyrover import ui_analise

from mod_seguranca import bd_manipulador as bd


def _log():
    return observabilidade.get_logger("seguranca")


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
        notificar("Erro ao carregar o módulo Segurança Pública.",
                  tipo="error")


def _mostrar(user_nome, perfil_global):
    bd.init_db()
    tema = ler_tema(bd.CHAVE_MODULO, cor_botao="#455A64",
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
            notificar("Erro ao atualizar as análises.", tipo="error")

    with ui.column().classes("w-full").style("gap: 1.25rem"):
        with ui.row().classes("w-full items-center").style("gap: 1rem"):
            with ui.column().style("gap: 0; min-width: 0"):
                ui.label("Segurança Pública").classes("text-h5")
                ui.label(
                    "Triagem de aglomeração, pessoas, veículos, placas e "
                    "objetos de risco em imagens de voo."
                ).classes("text-caption text-grey-7")
            ui.space()
            botao("Nova triagem", icone="add", chave_modulo=bd.CHAVE_MODULO,
                  on_click=lambda: _dialogo_nova(user_nome, _atualizar)
                  ).props("data-testid=seguranca-nova")

        with ui.card().classes("w-full").style(
                "background: #FFF3E0; border-left: 4px solid #EF6C00"):
            with ui.row().classes("items-start").style("gap: .5rem"):
                ui.icon("gpp_maybe").classes("text-2xl text-orange-9")
                with ui.column().style("gap: 0"):
                    ui.label("Triagem, não veredito").classes(
                        "text-subtitle1 text-orange-10")
                    ui.label(
                        "Toda ocorrência exige revisão humana. O sistema não "
                        "decide culpa, não expõe listas de terceiros e só "
                        "confronta bases oficiais com convênio e base legal. "
                        "Acesso e consulta ficam na trilha de auditoria."
                    ).classes("text-caption text-orange-9")

        r = bd.resumo()
        with ui.row().classes("w-full").style("gap: 1rem"):
            for rotulo, valor, icone in (
                    ("Análises", r["total"], "analytics"),
                    ("Concluídas", r["concluido"], "check_circle"),
                    ("Ocorrências", r["ocorrencias"], "visibility"),
                    ("Revisão pendente", r["pendentes_revisao"], "fact_check")):
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
    analises = bd.listar_analises()
    if not analises:
        with ui.card().classes("w-full"):
            ui.label("Nenhuma triagem cadastrada.").classes("text-body1")
            ui.label("Cadastre um voo em /voos e crie a primeira triagem.")\
                .classes("text-caption text-grey-7")
        return
    for linha in analises:
        (aid, voo_id, _cliente_id, _prop_id, tipo, risco, status, resumo,
         criado_por, criado_em) = linha
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center").style("gap: 1rem"):
                with ui.column().style("gap: 0; min-width: 0; flex: 1 1 0"):
                    ui.label(f"Voo #{voo_id} · {tipo}").classes(
                        "text-subtitle1")
                    ui.label(
                        f"risco: {risco} · {criado_por or '—'} · "
                        f"{criado_em or '—'}"
                    ).classes("text-caption text-grey-7")
                ui.badge(_rotulo(status)).props(f"color={_cor(status)}")
            if resumo:
                ui.label(resumo).classes("text-body2")
            ocorrencias = bd.listar_ocorrencias(aid)
            for o in ocorrencias:
                (oid, _aid, classe, quantidade, confianca, revisao,
                 evidencia, _criado) = o
                with ui.row().classes("w-full items-center").style(
                        "gap: .5rem"):
                    ui.label(
                        f"{classe} · qtd {quantidade} · confiança "
                        f"{float(confianca or 0):.2f}"
                    ).classes("text-body2")
                    if revisao:
                        ui.badge("Revisado").props("color=green")
                    else:
                        ui.badge("Revisão pendente").props("color=orange")
                        botao("Revisar", icone="fact_check",
                              variante="texto",
                              chave_modulo=bd.CHAVE_MODULO,
                              on_click=lambda _, i=oid: _revisar(i, refresh)
                              ).props(f"data-testid=seguranca-revisar-{oid}")
            ui_analise.bloco_analise(ator, voo_id, bd.CHAVE_MODULO)
            with ui.row().style("gap: .5rem"):
                botao("Ocorrência", icone="add_alert", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid, t=tipo:
                      _dialogo_ocorrencia(ator, i, t, refresh)
                      ).props(f"data-testid=seguranca-ocorrencia-{aid}")
                botao("Concluir", icone="task_alt", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid: _concluir(ator, i, refresh)
                      ).props(f"data-testid=seguranca-concluir-{aid}")


def _dialogo_nova(ator, refresh):
    try:
        from mod_skyrover import voos
        disponiveis = voos.listar_voos()
    except Exception:
        disponiveis = []
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[720px]"):
        ui.label("Nova triagem de segurança").classes("text-h6")
        if not disponiveis:
            ui.label(
                "Nenhum voo cadastrado. Cadastre um voo em /voos antes de "
                "criar a triagem."
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
            .props("data-testid=seguranca-voo")
        tipo = ui.select({t: t for t in bd.TIPOS}, label="Tipo",
                         value="multipla").props(
            "outlined dense").classes("w-full")
        risco = ui.select({r: r for r in bd.NIVEIS_RISCO},
                          label="Nível de risco", value="baixo").props(
            "outlined dense").classes("w-full")
        resumo = ui.textarea("Resumo / observações").props(
            "outlined dense").classes("w-full")

        def salvar():
            ok, msg = bd.criar_analise(
                ator, voo.value, tipo.value or "multipla",
                risco.value or "baixo", resumo.value or "")
            if ok:
                notificar("Triagem criada.", tipo="positive")
                dlg.close()
                refresh()
            else:
                notificar(str(msg), tipo="negative")

        with ui.row().classes("w-full justify-end").style("gap: .5rem"):
            botao("Cancelar", variante="texto", on_click=dlg.close)
            botao("Salvar", icone="save", chave_modulo=bd.CHAVE_MODULO,
                  on_click=salvar).props("data-testid=seguranca-salvar")
    dlg.open()


def _dialogo_ocorrencia(ator, analise_id, tipo, refresh):
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[640px]"):
        ui.label(f"Ocorrência · triagem #{analise_id}").classes("text-h6")
        ui.label(f"Tipo: {tipo}").classes("text-caption text-grey-7")
        ui.label(
            "Registre o achado da triagem. A revisão humana é obrigatória "
            "antes de qualquer uso operacional."
        ).classes("text-caption text-orange-9")
        classe = ui.select({c: c for c in bd.CLASSES}, label="Classe",
                           value=bd.CLASSES[0]).props(
            "outlined dense").classes("w-full")
        with ui.row().classes("w-full").style("gap: .75rem"):
            quantidade = ui.number("Quantidade", value=0).props(
                "outlined dense").classes("w-full")
            confianca = ui.number("Confiança (0-1)", value=0,
                                  format="%.2f").props(
                "outlined dense").classes("w-full")
        evidencia = ui.textarea("Evidência / observação").props(
            "outlined dense").classes("w-full")
        revisao = ui.checkbox("Revisado por humano", value=False)

        def salvar():
            ok, msg = bd.adicionar_ocorrencia(
                ator, analise_id, classe.value, quantidade.value or 0,
                confianca.value or 0, 1 if revisao.value else 0,
                evidencia.value or "")
            if ok:
                notificar("Ocorrência registrada.", tipo="positive")
                dlg.close()
                refresh()
            else:
                notificar(str(msg), tipo="negative")

        with ui.row().classes("w-full justify-end").style("gap: .5rem"):
            botao("Cancelar", variante="texto", on_click=dlg.close)
            botao("Registrar", icone="save", chave_modulo=bd.CHAVE_MODULO,
                  on_click=salvar)
    dlg.open()


def _revisar(ocorrencia_id, refresh):
    if bd.marcar_revisao(ocorrencia_id, True):
        notificar("Ocorrência marcada como revisada.", tipo="positive")
        refresh()
    else:
        notificar("Erro ao marcar a revisão.", tipo="error")


def _concluir(ator, analise_id, refresh):
    ok, msg = bd.atualizar_status(
        analise_id, "concluido",
        resumo="Triagem concluída. Todas as ocorrências precisam de revisão "
               "humana antes de uso operacional.")
    notificar(str(msg), tipo="positive" if ok else "negative")
    if ok:
        refresh()
