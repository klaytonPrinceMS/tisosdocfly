"""Telas do módulo Inspeção Industrial (rota /inspecao-industrial).

EN: Industrial inspection screens — analysis list, creation, occurrences and
report conclusion.

PT-BR: Telas da Inspeção Industrial — lista de análises, criação, ocorrências
e conclusão do laudo. Renderiza dentro do layout de `pagina_restrita`; não
monta menu.
"""
import os

from nicegui import ui

from mod_skyrover import observabilidade
from mod_skyrover.tema_modulo import ler_tema, notificar
from mod_skyrover.ui_comum import botao
from mod_skyrover import ui_analise

from mod_inspecao_industrial import bd_manipulador as bd


def _log():
    return observabilidade.get_logger("inspecao_industrial")


def _rotulo_status(status):
    return {"rascunho": "Rascunho", "em_revisao": "Em revisão",
            "concluido": "Concluído"}.get(status or "", status or "—")


def _cor_status(status):
    return {"rascunho": "grey", "em_revisao": "orange",
            "concluido": "green"}.get(status or "", "grey")


def _voo_rotulo(voo):
    """Extrai id/data/cliente de um voo em dict ou tupla (API pública)."""
    try:
        if isinstance(voo, dict):
            return (voo.get("id"), voo.get("data_voo"),
                    voo.get("cliente_nome"))
        return voo[0], voo[3] if len(voo) > 3 else "", (
            voo[10] if len(voo) > 10 else "")
    except Exception:
        return None, "", ""


def mostrar_tela(user_nome: str, perfil_global: str = ""):
    """Monta a tela principal do módulo Inspeção Industrial."""
    try:
        _mostrar(user_nome, perfil_global)
    except Exception as e:
        try:
            _log().exception(f"mostrar_tela: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao carregar o módulo Inspeção Industrial.",
                  tipo="error")


def _mostrar(user_nome: str, perfil_global: str):
    bd.init_db()
    tema = ler_tema(bd.CHAVE_MODULO, cor_botao="#EF6C00",
                    cor_texto_botao="#FFFFFF")
    ui.colors(primary=tema["cor_botao"])
    estado = {"busca": ""}
    lista = ui.column().classes("w-full").style("gap: .75rem")

    def _atualizar():
        try:
            lista.clear()
            with lista:
                _render_lista(user_nome, estado["busca"], _atualizar)
        except Exception as e:
            try:
                _log().exception(f"_atualizar: falha | {e}")
            except Exception:
                pass
            notificar("Erro ao atualizar a lista de inspeções.",
                      tipo="error")

    with ui.column().classes("w-full").style("gap: 1.25rem"):
        with ui.row().classes("w-full items-center").style("gap: 1rem"):
            with ui.column().style("gap: 0; min-width: 0"):
                ui.label("Inspeção Industrial").classes("text-h5")
                ui.label(
                    "Análises de voo para estruturas, torres, linhas, tanques "
                    "e equipamentos industriais."
                ).classes("text-caption text-grey-7")
            ui.space()
            botao("Nova análise", icone="add", variante="solido",
                  chave_modulo=bd.CHAVE_MODULO,
                  on_click=lambda: _dialogo_nova(user_nome, _atualizar)
                  ).props("data-testid=inspecao-industrial-nova-analise")

        r = bd.resumo()
        with ui.row().classes("w-full").style("gap: 1rem"):
            for rotulo, valor, icone in (
                    ("Análises", r["total"], "analytics"),
                    ("Concluídas", r["concluido"], "check_circle"),
                    ("Em revisão", r["em_revisao"], "fact_check"),
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
                "Buscar por ativo, tipo ou status").props(
                "outlined dense clearable").classes("w-80")
            busca.on_value_change(
                lambda e: (estado.update(busca=e.value or ""),
                           _atualizar()))
        ui.separator()
        _atualizar()


def _render_lista(ator, busca, refresh):
    analises = bd.listar_analises(busca)
    if not analises:
        with ui.card().classes("w-full"):
            ui.label("Nenhuma inspeção cadastrada.").classes("text-body1")
            ui.label(
                "Cadastre um voo em /voos e crie a primeira análise de "
                "inspeção industrial."
            ).classes("text-caption text-grey-7")
        return
    for linha in analises:
        (aid, voo_id, _cliente_id, _prop_id, ativo, tipo, status, resumo,
         criado_por, criado_em) = linha
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center").style("gap: 1rem"):
                with ui.column().style("gap: 0; min-width: 0; flex: 1 1 0"):
                    ui.label(
                        f"Voo #{voo_id} · {ativo or 'ativo não informado'}"
                    ).classes("text-subtitle1")
                    ui.label(
                        f"{tipo or 'tipo não informado'} · "
                        f"{criado_por or '—'} · {criado_em or '—'}"
                    ).classes("text-caption text-grey-7")
                ui.badge(_rotulo_status(status)).props(
                    f"color={_cor_status(status)}")
            if resumo:
                ui.label(resumo).classes("text-body2")
            ocorrencias = bd.listar_ocorrencias(aid)
            for o in ocorrencias:
                (oid, _aid, classe, severidade, area_m2, confianca, revisao,
                 evidencia, _criado) = o
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
                              ).props(
                                  f"data-testid=inspecao-industrial-"
                                  f"revisar-{oid}")
                if evidencia:
                    ui.label(evidencia).classes(
                        "text-caption text-grey-7")
            ui_analise.bloco_analise(ator, voo_id, bd.CHAVE_MODULO)
            with ui.row().style("gap: .5rem"):
                botao("Gerar laudo PDF", icone="picture_as_pdf",
                      variante="contorno", chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid, v=voo_id, a=ativo:
                      _gerar_pdf(ator, i, v, a)
                      ).props(
                          f"data-testid=inspecao-industrial-pdf-{aid}")
                botao("Ocorrência", icone="add_alert", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid, a=ativo:
                      _dialogo_ocorrencia(ator, i, a, refresh)
                      ).props(
                          f"data-testid=inspecao-industrial-ocorrencia-{aid}")
                botao("Concluir", icone="task_alt", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid: _concluir(ator, i, refresh)
                      ).props(
                          f"data-testid=inspecao-industrial-concluir-{aid}")


def _dialogo_nova(ator, refresh):
    try:
        from mod_skyrover import voos
        voos_disponiveis = voos.listar_voos()
    except Exception:
        voos_disponiveis = []
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[720px]"):
        ui.label("Nova análise de inspeção industrial").classes("text-h6")
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
            vid, data_voo, cliente = _voo_rotulo(v)
            if vid is None:
                continue
            opcoes[vid] = f"#{vid} · {data_voo or 'sem data'} · {cliente}"
        if not opcoes:
            ui.label("Nenhum voo válido disponível.").classes(
                "text-body2 text-orange-9")
            botao("Fechar", variante="texto", on_click=dlg.close)
            dlg.open()
            return
        voo = ui.select(opcoes, label="Voo",
                        value=next(iter(opcoes))).props(
            "outlined dense").classes("w-full") \
            .props("data-testid=inspecao-industrial-voo")
        ativo = ui.input("Ativo / equipamento / TAG").props(
            "outlined dense").classes("w-full") \
            .props("data-testid=inspecao-industrial-ativo")
        tipo = ui.select({t: t for t in bd.TIPOS}, label="Tipo",
                         value=bd.TIPOS[0]).props(
            "outlined dense").classes("w-full") \
            .props("data-testid=inspecao-industrial-tipo")
        resumo = ui.textarea("Resumo / observações").props(
            "outlined dense").classes("w-full") \
            .props("data-testid=inspecao-industrial-resumo")

        def salvar():
            try:
                ok, msg = bd.criar_analise(
                    ator, voo.value, ativo.value or "",
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
                  on_click=salvar).props(
                "data-testid=inspecao-industrial-salvar")
    dlg.open()


def _dialogo_ocorrencia(ator, analise_id, ativo, refresh):
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[640px]"):
        ui.label(f"Ocorrência · análise #{analise_id}").classes("text-h6")
        ui.label(f"Ativo: {ativo or '—'}").classes(
            "text-caption text-grey-7")
        classe = ui.select({c: c for c in bd.CLASSES}, label="Classe",
                           value=bd.CLASSES[0]).props(
            "outlined dense").classes("w-full")
        severidade = ui.select({s: s for s in bd.SEVERIDADES},
                               label="Severidade",
                               value=bd.SEVERIDADES[0]).props(
            "outlined dense").classes("w-full")
        with ui.row().classes("w-full").style("gap: .75rem"):
            area = ui.number("Área afetada (m²)", value=0,
                             format="%.2f").props(
                "outlined dense").classes("w-full")
            confianca = ui.number("Confiança (0-1)", value=0,
                                  format="%.2f").props(
                "outlined dense").classes("w-full")
        evidencia = ui.textarea("Evidência / observação").props(
            "outlined dense").classes("w-full")
        revisao = ui.checkbox("Revisado por humano", value=False)

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
                  on_click=salvar)
    dlg.open()


def _revisar(ocorrencia_id, refresh):
    try:
        if bd.marcar_revisao(ocorrencia_id, True):
            notificar("Ocorrência marcada como revisada.", tipo="positive")
            refresh()
        else:
            notificar("Erro ao marcar a revisão.", tipo="error")
    except Exception as e:
        try:
            _log().exception(f"revisar: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao marcar a revisão.", tipo="error")


def _gerar_pdf(ator, analise_id, voo_id, ativo):
    """Gera o PDF da inspeção com as ocorrências já registradas."""
    try:
        from mod_skyrover import voos
        linha = bd.obter_analise(analise_id)
        if not linha:
            notificar("Análise não encontrada.", tipo="negative")
            return
        resumo = linha[7] or ""
        tipo = linha[5] or "inspeção"
        ocorrencias = []
        for o in bd.listar_ocorrencias(analise_id):
            ocorrencias.append({
                "classe": o[2],
                "severidade": o[3],
                "area_m2": float(o[4] or 0),
                "confianca": float(o[5] or 0),
                "evidencia": o[7] or "",
                "revisao_humana": int(o[6] or 0),
            })
        titulo = (f"Inspeção industrial — {ativo or 'ativo'} ({tipo}) — "
                  f"Voo #{voo_id}")
        caminho = voos.gerar_laudo_modulo_pdf(
            bd.CHAVE_MODULO, voo_id, titulo, resumo, ocorrencias, ator=ator)
        if not caminho:
            notificar("Não foi possível gerar o PDF.", tipo="negative")
            return
        with ui.dialog() as dlg, ui.card().classes("w-full max-w-[560px]"):
            ui.label("Laudo PDF gerado").classes("text-h6")
            ui.label(caminho).classes("text-caption text-grey-7")
            try:
                rel = os.path.relpath(
                    caminho, voos.diretorio_laudos()).replace("\\", "/")
                ui.link("Baixar PDF", f"/laudos/{rel}")
            except Exception:
                pass
            botao("Fechar", variante="texto", on_click=dlg.close,
                  chave_modulo=bd.CHAVE_MODULO)
        dlg.open()
    except Exception as e:
        try:
            _log().exception(f"_gerar_pdf: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao gerar o laudo PDF.", tipo="error")


def _concluir(ator, analise_id, refresh):
    try:
        ok, msg = bd.atualizar_status(
            analise_id, "concluido",
            resumo="Laudo de inspeção industrial concluído. Revisar as "
                   "ocorrências e anexar as evidências do voo.")
        notificar(str(msg), tipo="positive" if ok else "negative")
        if ok:
            refresh()
    except Exception as e:
        try:
            _log().exception(f"concluir: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao concluir a análise.", tipo="error")
