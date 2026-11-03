"""Telas do módulo Agropecuário (rota /agro).

EN: Agro screens — analysis list, creation, occurrences and report conclusion.

PT-BR: Telas do Agro — lista de análises, criação, ocorrências e conclusão do
laudo. Renderiza dentro do layout de `pagina_restrita`; não monta menu.
"""
from nicegui import ui

from mod_tisosdocfly import observabilidade
from mod_tisosdocfly.tema_modulo import ler_tema, notificar
from mod_tisosdocfly.ui_comum import botao
from mod_tisosdocfly import ui_analise

from mod_agro import bd_manipulador as bd


def _log():
    return observabilidade.get_logger("agro")


def _rotulo_status(status):
    return {"rascunho": "Rascunho", "processando": "Processando",
            "concluido": "Concluído"}.get(status or "", status or "—")


def _cor_status(status):
    return {"rascunho": "grey", "processando": "orange",
            "concluido": "green"}.get(status or "", "grey")


def mostrar_tela(user_nome: str, perfil_global: str = ""):
    """Monta a tela principal do módulo Agropecuário."""
    try:
        _mostrar(user_nome, perfil_global)
    except Exception as e:
        try:
            _log().exception(f"mostrar_tela: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao carregar o módulo Agropecuário.", tipo="error")


def _mostrar(user_nome: str, perfil_global: str):
    bd.init_db()
    tema = ler_tema(bd.CHAVE_MODULO, cor_botao="#2E7D32",
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
                ui.label("Agropecuário").classes("text-h5")
                ui.label(
                    "Lavoura, pastagem e rebanho: estande, falhas, "
                    "matocompetição e monitoramento de gado."
                ).classes("text-caption text-grey-7")
            ui.space()
            botao("Nova análise", icone="add", variante="solido",
                  chave_modulo=bd.CHAVE_MODULO,
                  on_click=lambda: _dialogo_nova(user_nome, _atualizar)
                  ).props("data-testid=agro-nova-analise")

        r = bd.resumo()
        with ui.row().classes("w-full").style("gap: 1rem"):
            for rotulo, valor, icone in (
                    ("Análises", r["total"], "analytics"),
                    ("Concluídas", r["concluido"], "check_circle"),
                    ("Em andamento", r["processando"], "autorenew"),
                    ("Ocorrências", r["ocorrencias"], "warning"),
                    ("Cabeças", r.get("cabecas", 0), "pets"),
                    ("Perda média", f"{r.get('perda_media', 0):.1f}%",
                     "trending_down")):
                with ui.card().style("min-width: 180px; flex: 1 1 180px"):
                    with ui.row().classes("items-center").style("gap: .5rem"):
                        ui.icon(icone).classes("text-2xl")
                        with ui.column().style("gap: 0"):
                            ui.label(str(valor)).classes("text-h5")
                            ui.label(rotulo).classes(
                                "text-caption text-grey-7")

        with ui.row().classes("w-full items-center").style("gap: .5rem"):
            busca = ui.input(
                "Buscar por talhão, cultura, índice ou status").props(
                "outlined dense clearable").classes("w-80")
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
                "agropecuária."
            ).classes("text-caption text-grey-7")
        return
    for linha in analises:
        (aid, voo_id, _cliente_id, _prop_id, talhao, cultura, indice,
         estagio, area_ha, resultado, status, criado_por, criado_em,
         tipo_analise, cabecas, area_pastagem, finalidade, perda,
         area_afetada) = linha
        tipo_analise = tipo_analise or "lavoura"
        cabecas = int(cabecas or 0)
        area_pastagem = float(area_pastagem or 0)
        finalidade = finalidade or "producao"
        perda = float(perda or 0)
        area_afetada = float(area_afetada or 0)
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center").style("gap: 1rem"):
                with ui.column().style("gap: 0; min-width: 0; flex: 1 1 0"):
                    ui.label(
                        f"Voo #{voo_id} · {talhao or 'talhão não informado'}"
                    ).classes("text-subtitle1")
                    extra = ""
                    if tipo_analise == "rebanho":
                        extra = f" · {cabecas} cabeça(s)"
                    if area_pastagem:
                        extra += f" · pastagem {area_pastagem:.2f} ha"
                    if finalidade != "producao":
                        extra += f" · {finalidade}"
                    if perda:
                        extra += f" · perda {perda:.1f}%"
                    if area_afetada:
                        extra += f" · afetada {area_afetada:.2f} ha"
                    ui.label(
                        f"{tipo_analise} · {cultura or 'cultura não informada'} · "
                        f"{indice or 'índice não informado'} · "
                        f"{area_ha or 0} ha · {criado_por or '—'}{extra}"
                    ).classes("text-caption text-grey-7")
                ui.badge(_rotulo_status(status)).props(
                    f"color={_cor_status(status)}")
            if resultado:
                ui.label(resultado).classes("text-body2")
            ocorrencias = bd.listar_ocorrencias(aid)
            if ocorrencias:
                ui.label(f"{len(ocorrencias)} ocorrência(s) registrada(s)")\
                    .classes("text-caption text-grey-7")
            ui_analise.bloco_analise(
                ator, voo_id, bd.CHAVE_MODULO,
                contexto={"tipo_analise": tipo_analise})
            with ui.row().style("gap: .5rem"):
                if tipo_analise in ("lavoura", "pastagem"):
                    botao("Linhas de plantio", icone="polyline",
                          variante="texto", chave_modulo=bd.CHAVE_MODULO,
                          on_click=lambda _, v=voo_id:
                          _detectar_linhas(ator, v, refresh)
                          ).props(f"data-testid=agro-linhas-{aid}")
                botao("Ocorrência", icone="add_alert", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid, t=talhao: _dialogo_ocorrencia(
                          ator, i, t, refresh)
                      ).props(f"data-testid=agro-ocorrencia-{aid}")
                botao("Concluir", icone="task_alt", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid: _concluir(ator, i, refresh)
                      ).props(f"data-testid=agro-concluir-{aid}")


def _dialogo_nova(ator, refresh):
    try:
        from mod_tisosdocfly import voos
        voos_disponiveis = voos.listar_voos()
    except Exception:
        voos_disponiveis = []
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[720px]"):
        ui.label("Nova análise agropecuária").classes("text-h6")
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
            vid, _cid, _pid, data_voo = v[0], v[1], v[2], v[3]
            cliente = v[10] if len(v) > 10 else ""
            opcoes[vid] = f"#{vid} · {data_voo or 'sem data'} · {cliente}"
        voo = ui.select(opcoes, label="Voo",
                        value=next(iter(opcoes))).props(
            "outlined dense").classes("w-full") \
            .props("data-testid=agro-voo")
        tipo_analise = ui.select(
            {t: t for t in bd.TIPOS_ANALISE},
            label="Tipo de análise", value="lavoura").props(
            "outlined dense").classes("w-full") \
            .props("data-testid=agro-tipo-analise")
        finalidade = ui.select(
            {f: f for f in bd.FINALIDADES},
            label="Finalidade", value="producao").props(
            "outlined dense").classes("w-full") \
            .props("data-testid=agro-finalidade")
        with ui.row().classes("w-full").style("gap: .75rem"):
            talhao = ui.input("Talhão / piquete").props(
                "outlined dense").classes(
                "w-full").props("data-testid=agro-talhao")
            cultura = ui.select({c: c for c in bd.CULTURAS},
                                label="Cultura / pastagem",
                                value=bd.CULTURAS[0]).props(
                "outlined dense").classes("w-full") \
                .props("data-testid=agro-cultura")
        with ui.row().classes("w-full").style("gap: .75rem"):
            indice = ui.select({i: i for i in bd.INDICES},
                               label="Índice", value=bd.INDICES[0]).props(
                "outlined dense").classes("w-full") \
                .props("data-testid=agro-indice")
            area = ui.number("Área (ha)", value=0, format="%.2f").props(
                "outlined dense").classes("w-full") \
                .props("data-testid=agro-area")
        with ui.row().classes("w-full").style("gap: .75rem"):
            cabecas = ui.number("Cabeças (rebanho)", value=0).props(
                "outlined dense").classes("w-full") \
                .props("data-testid=agro-cabecas")
            pastagem = ui.number("Área de pastagem (ha)", value=0,
                                 format="%.2f").props(
                "outlined dense").classes("w-full") \
                .props("data-testid=agro-pastagem")
        with ui.row().classes("w-full").style("gap: .75rem"):
            perda = ui.number("Perda estimada (%)", value=0,
                              format="%.1f").props(
                "outlined dense").classes("w-full") \
                .props("data-testid=agro-perda")
            afetada = ui.number("Área afetada (ha)", value=0,
                                format="%.2f").props(
                "outlined dense").classes("w-full") \
                .props("data-testid=agro-area-afetada")
        estagio = ui.input("Estágio fenológico / condição da pastagem").props(
            "outlined dense").classes("w-full")
        resultado = ui.textarea("Resultado / observações").props(
            "outlined dense").classes("w-full")

        def _ajustar_campos():
            tipo = tipo_analise.value or "lavoura"
            cabecas.visible = tipo == "rebanho"
            pastagem.visible = tipo in ("rebanho", "pastagem")

        tipo_analise.on_value_change(lambda _e: _ajustar_campos())
        _ajustar_campos()

        def salvar():
            try:
                ok, msg = bd.criar_analise(
                    ator, voo.value, talhao.value or "", cultura.value or "",
                    indice.value or "", estagio.value or "",
                    area.value or 0, resultado.value or "",
                    tipo_analise=tipo_analise.value or "lavoura",
                    cabecas_estimadas=cabecas.value or 0,
                    area_pastagem_ha=pastagem.value or 0,
                    finalidade=finalidade.value or "producao",
                    perda_estimada_pct=perda.value or 0,
                    area_afetada_ha=afetada.value or 0)
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
                  on_click=salvar).props("data-testid=agro-salvar")
    dlg.open()


def _dialogo_ocorrencia(ator, analise_id, talhao, refresh):
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[640px]"):
        ui.label(f"Ocorrência · análise #{analise_id}").classes("text-h6")
        ui.label(f"Talhão: {talhao or '—'}").classes(
            "text-caption text-grey-7")
        classe = ui.select({c: c for c in bd.CLASSES},
                           label="Classe", value=bd.CLASSES[0]).props(
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

        with ui.row().classes("w-full justify-end").style("gap: .5rem"):
            botao("Cancelar", variante="texto", on_click=dlg.close)
            botao("Registrar", icone="save", chave_modulo=bd.CHAVE_MODULO,
                  on_click=salvar)
    dlg.open()


def _detectar_linhas(ator, voo_id, refresh):
    """Roda o Hough puro em uma imagem do voo e mostra o resumo."""
    try:
        from mod_tisosdocfly import voos
        resultados = voos.detectar_linhas_plantio(
            voo_id, ator=ator, max_imagens=1, max_lado=192)
        if not resultados:
            notificar(
                "Nenhuma linha detectada. A imagem precisa ter vegetação "
                "em fileiras retas. Linhas curvas não são suportadas.",
                tipo="warning")
            return
        r = resultados[0]["resultado"]
        with ui.dialog() as dlg, ui.card().classes("w-full max-w-[560px]"):
            ui.label("Linhas de plantio (Hough)").classes("text-h6")
            ui.label(resultados[0]["resumo"]).classes("text-body2")
            ui.label(
                "O envelope da vegetação e a limpeza morfológica são "
                "aplicados antes do Hough. Valide em campo: linhas curvas "
                "não são bem representadas."
            ).classes("text-caption text-grey-7")
            botao("Fechar", variante="texto", on_click=dlg.close,
                  chave_modulo=bd.CHAVE_MODULO)
        dlg.open()
        # NÃO chame `refresh()` aqui: ele reconstrói o cartão e leva junto o
        # diálogo recém-aberto (o registro já foi gravado; a lista de IA
        # aparece no próximo carregamento).
    except Exception as e:
        try:
            _log().exception(f"_detectar_linhas: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao detectar linhas de plantio.", tipo="error")


def _concluir(ator, analise_id, refresh):
    try:
        ok, msg = bd.atualizar_status(
            analise_id, "concluido",
            resultado="Laudo agropecuário concluído. Revisar as ocorrências "
                      "e anexar as evidências do voo.")
        notificar(str(msg), tipo="positive" if ok else "negative")
        if ok:
            refresh()
    except Exception as e:
        try:
            _log().exception(f"concluir: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao concluir a análise.", tipo="error")
