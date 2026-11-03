"""Telas do módulo Ambiental (rota /ambiental).

EN: Environmental screens — analysis list, creation, occurrences and report
conclusion.

PT-BR: Telas do Ambiental — lista de análises, criação, ocorrências e conclusão
do laudo. Renderiza dentro do layout de `pagina_restrita`; não monta menu.
"""
from nicegui import ui

from mod_tisosdocfly import observabilidade
from mod_tisosdocfly.tema_modulo import ler_tema, notificar
from mod_tisosdocfly.ui_comum import botao
from mod_tisosdocfly import ui_analise

from mod_ambiental import bd_manipulador as bd

_COR = "#2E7D32"


def _log():
    return observabilidade.get_logger("ambiental")


def _rotulo_status(status):
    return {"rascunho": "Rascunho", "em_revisao": "Em revisão",
            "concluido": "Concluído"}.get(status or "", status or "—")


def _cor_status(status):
    return {"rascunho": "grey", "em_revisao": "orange",
            "concluido": "green"}.get(status or "", "grey")


def mostrar_tela(user_nome: str, perfil_global: str = ""):
    """Monta a tela principal do módulo Ambiental."""
    try:
        _mostrar(user_nome, perfil_global)
    except Exception as e:
        try:
            _log().exception(f"mostrar_tela: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao carregar o módulo Ambiental.", tipo="error")


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
                ui.label("Ambiental").classes("text-h5")
                ui.label(
                    "Análises de voo para desmatamento, APP, queimada e "
                    "recuperação de áreas."
                ).classes("text-caption text-grey-7")
            ui.space()
            botao("Nova análise", icone="add", variante="solido",
                  chave_modulo=bd.CHAVE_MODULO,
                  on_click=lambda: _dialogo_nova(user_nome, _atualizar)
                  ).props("data-testid=ambiental-nova-analise")

        r = bd.resumo()
        with ui.row().classes("w-full").style("gap: 1rem"):
            for rotulo, valor, icone in (
                    ("Análises", r["total"], "analytics"),
                    ("Concluídas", r["concluido"], "check_circle"),
                    ("Em revisão", r["em_revisao"], "rate_review"),
                    ("Ocorrências", r["ocorrencias"], "warning")):
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
                .props("data-testid=ambiental-busca")
            busca.on_value_change(
                lambda e: (estado.update(busca=e.value or ""),
                           _atualizar()))
        ui.separator()
        _atualizar()


def _render_lista(ator, perfil_global, busca, refresh):
    analises = bd.listar_analises(busca)
    if not analises:
        with ui.card().classes("w-full"):
            ui.label("Nenhuma análise cadastrada.").classes("text-body1")
            ui.label(
                "Cadastre um voo em /voos e crie a primeira análise "
                "ambiental."
            ).classes("text-caption text-grey-7")
        return
    for linha in analises:
        (aid, voo_id, _cliente_id, _prop_id, area, tipo, status, resumo,
         criado_por, criado_em) = linha
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center").style("gap: 1rem"):
                with ui.column().style("gap: 0; min-width: 0; flex: 1 1 0"):
                    ui.label(f"Voo #{voo_id} · {tipo or 'tipo não informado'}")\
                        .classes("text-subtitle1")
                    ui.label(
                        f"{float(area or 0):.2f} ha · {criado_por or '—'} · "
                        f"{criado_em or '—'}"
                    ).classes("text-caption text-grey-7")
                ui.badge(_rotulo_status(status)).props(
                    f"color={_cor_status(status)}")
            if resumo:
                ui.label(resumo).classes("text-body2")
            ocorrencias = bd.listar_ocorrencias(aid)
            for o in ocorrencias:
                (oid, _aid, classe, severidade, area_m2, confianca,
                 revisao, evidencia, _criado) = o
                with ui.row().classes("w-full items-center").style(
                        "gap: .5rem"):
                    ui.label(
                        f"{classe} · {severidade} · "
                        f"{float(area_m2 or 0):.2f} m² · confiança "
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
                              ).props(f"data-testid=ambiental-revisar-{oid}")
                    if evidencia:
                        ui.label(evidencia).classes(
                            "text-caption text-grey-7")
            ui_analise.bloco_analise(ator, voo_id, bd.CHAVE_MODULO)
            with ui.row().style("gap: .5rem"):
                botao("Ocorrência", icone="add_alert", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid, t=tipo: _dialogo_ocorrencia(
                          ator, i, t, refresh)
                      ).props(f"data-testid=ambiental-ocorrencia-{aid}")
                botao("Concluir", icone="task_alt", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid: _concluir(ator, i, refresh)
                      ).props(f"data-testid=ambiental-concluir-{aid}")


def _dialogo_nova(ator, refresh):
    try:
        from mod_tisosdocfly import voos
        voos_disponiveis = voos.listar_voos()
    except Exception as e:
        try:
            _log().exception(f"_dialogo_nova: falha ao listar voos | {e}")
        except Exception:
            pass
        voos_disponiveis = []
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[720px]"):
        ui.label("Nova análise ambiental").classes("text-h6")
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
            .props("data-testid=ambiental-voo")
        with ui.row().classes("w-full").style("gap: .75rem"):
            area = ui.number("Área (ha)", value=0, format="%.2f").props(
                "outlined dense").classes("w-full") \
                .props("data-testid=ambiental-area")
            tipo = ui.select({t: t for t in bd.TIPOS}, label="Tipo",
                             value=bd.TIPOS[0]).props(
                "outlined dense").classes("w-full") \
                .props("data-testid=ambiental-tipo")
        resumo = ui.textarea("Resumo / observações").props(
            "outlined dense").classes("w-full") \
            .props("data-testid=ambiental-resumo")

        def salvar():
            try:
                ok, msg = bd.criar_analise(
                    ator, voo.value, area.value or 0, tipo.value or "outro",
                    resumo.value or "")
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
                  on_click=salvar).props("data-testid=ambiental-salvar")
    dlg.open()


def _dialogo_ocorrencia(ator, analise_id, tipo, refresh):
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[640px]"):
        ui.label(f"Ocorrência · análise #{analise_id}").classes("text-h6")
        ui.label(f"Tipo da análise: {tipo or '—'}").classes(
            "text-caption text-grey-7")
        classe = ui.select({c: c for c in bd.CLASSES}, label="Classe",
                           value=bd.CLASSES[0]).props(
            "outlined dense").classes("w-full") \
            .props("data-testid=ambiental-classe")
        severidade = ui.select({s: s for s in bd.SEVERIDADES},
                               label="Severidade",
                               value=bd.SEVERIDADES[0]).props(
            "outlined dense").classes("w-full") \
            .props("data-testid=ambiental-severidade")
        with ui.row().classes("w-full").style("gap: .75rem"):
            area = ui.number("Área afetada (m²)", value=0,
                             format="%.2f").props(
                "outlined dense").classes("w-full") \
                .props("data-testid=ambiental-area-m2")
            confianca = ui.number("Confiança (0-1)", value=0,
                                  format="%.2f").props(
                "outlined dense").classes("w-full") \
                .props("data-testid=ambiental-confianca")
        evidencia = ui.textarea("Evidência / observação").props(
            "outlined dense").classes("w-full") \
            .props("data-testid=ambiental-evidencia")
        revisao = ui.checkbox("Revisado por humano", value=False).props(
            "data-testid=ambiental-revisao")

        def salvar():
            try:
                ok, msg = bd.adicionar_ocorrencia(
                    ator, analise_id, classe.value, severidade.value,
                    area.value or 0, confianca.value or 0,
                    1 if revisao.value else 0, evidencia.value or "")
                if ok:
                    notificar("Ocorrência registrada.", tipo="positive")
                    dlg.close()
                    refresh()
                else:
                    notificar(str(msg), tipo="negative")
            except Exception as e:
                try:
                    _log().exception(f"salvar ocorrência: falha | {e}")
                except Exception:
                    pass
                notificar("Erro ao registrar a ocorrência.", tipo="error")

        with ui.row().classes("w-full justify-end").style("gap: .5rem"):
            botao("Cancelar", variante="texto", on_click=dlg.close)
            botao("Registrar", icone="save", chave_modulo=bd.CHAVE_MODULO,
                  on_click=salvar).props("data-testid=ambiental-registrar")
    dlg.open()


def _revisar(ocorrencia_id, refresh):
    try:
        ok = bd.marcar_revisao(ocorrencia_id, True)
        notificar("Revisão registrada." if ok else "Falha ao revisar.",
                  tipo="positive" if ok else "negative")
        if ok:
            refresh()
    except Exception as e:
        try:
            _log().exception(f"revisar: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao revisar a ocorrência.", tipo="error")


def _concluir(ator, analise_id, refresh):
    try:
        ok, msg = bd.atualizar_status(
            analise_id, "concluido",
            resumo="Laudo ambiental concluído. Revisar as ocorrências e "
                   "anexar as evidências do voo.")
        notificar(str(msg), tipo="positive" if ok else "negative")
        if ok:
            refresh()
    except Exception as e:
        try:
            _log().exception(f"concluir: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao concluir a análise.", tipo="error")
