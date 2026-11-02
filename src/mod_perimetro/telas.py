"""Telas do módulo Perímetro (rota /perimetro).

EN: Perimeter screens — audit list, creation, physical findings and RF import.

PT-BR: Telas do Perímetro — lista de auditorias, criação, achados físicos e
importação de varredura Wi-Fi/RF. Renderiza dentro do layout de
`pagina_restrita`; não monta menu. Nenhuma tela exibe BSSID cru: a rede é
identificada pelo SSID e pelo hash SHA-256.
"""
import os

from nicegui import ui

from mod_skyrover import observabilidade
from mod_skyrover import rf_scan
from mod_skyrover.tema_modulo import ler_tema, notificar
from mod_skyrover.ui_comum import botao

from mod_perimetro import bd_manipulador as bd


def _log():
    return observabilidade.get_logger("perimetro")


def _rotulo_status(status):
    return {"rascunho": "Rascunho", "em_revisao": "Em revisão",
            "concluido": "Concluído"}.get(status or "", status or "—")


def _cor_status(status):
    return {"rascunho": "grey", "em_revisao": "orange",
            "concluido": "green"}.get(status or "", "grey")


def _cor_severidade(severidade):
    return {"baixa": "grey", "media": "orange", "alta": "deep-orange",
            "critica": "red"}.get(severidade or "", "grey")


def _cor_risco(risco):
    return {"baixo": "green", "medio": "orange", "alto": "deep-orange",
            "critico": "red"}.get(risco or "", "grey")


def mostrar_tela(user_nome: str, perfil_global: str = ""):
    """Monta a tela principal do módulo Perímetro."""
    try:
        _mostrar(user_nome, perfil_global)
    except Exception as e:
        try:
            _log().exception(f"mostrar_tela: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao carregar o módulo Perímetro.", tipo="error")


def _mostrar(user_nome: str, perfil_global: str):
    bd.init_db()
    tema = ler_tema(bd.CHAVE_MODULO, cor_botao="#6A1B9A",
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
            notificar("Erro ao atualizar a lista de auditorias.",
                      tipo="error")

    with ui.column().classes("w-full").style("gap: 1.25rem"):
        with ui.row().classes("w-full items-center").style("gap: 1rem"):
            with ui.column().style("gap: 0; min-width: 0"):
                ui.label("Perímetro").classes("text-h5")
                ui.label(
                    "Pontos cegos de câmera, vãos de cerca, iluminação, "
                    "acessos e vazamento de Wi-Fi/RF do perímetro corporativo."
                ).classes("text-caption text-grey-7")
            ui.space()
            botao("Nova auditoria", icone="add", variante="solido",
                  chave_modulo=bd.CHAVE_MODULO,
                  on_click=lambda: _dialogo_nova(user_nome, _atualizar)
                  ).props("data-testid=perimetro-nova-auditoria")

        r = bd.resumo()
        with ui.row().classes("w-full").style("gap: 1rem"):
            for rotulo, valor, icone in (
                    ("Auditorias", r["total"], "fact_check"),
                    ("Concluídas", r["concluido"], "check_circle"),
                    ("Em revisão", r["em_revisao"], "autorenew"),
                    ("Achados", r["achados"], "warning"),
                    ("Wi-Fi abertas", r["rf_abertas"], "wifi_off"),
                    ("Fora do perímetro", r["fora_perimetro"],
                     "wrong_location")):
                with ui.card().style("min-width: 170px; flex: 1 1 170px"):
                    with ui.row().classes("items-center").style("gap: .5rem"):
                        ui.icon(icone).classes("text-2xl")
                        with ui.column().style("gap: 0"):
                            ui.label(str(valor)).classes("text-h5")
                            ui.label(rotulo).classes(
                                "text-caption text-grey-7")

        with ui.row().classes("w-full items-center").style("gap: .5rem"):
            busca = ui.input(
                "Buscar por local, tipo, status ou resumo").props(
                "outlined dense clearable").classes("w-80")
            busca.on_value_change(
                lambda e: (estado.update(busca=e.value or ""),
                           _atualizar()))
        ui.separator()
        _atualizar()


def _render_lista(ator, busca, refresh):
    auditorias = bd.listar_auditorias(busca)
    if not auditorias:
        with ui.card().classes("w-full"):
            ui.label("Nenhuma auditoria cadastrada.").classes("text-body1")
            ui.label(
                "Cadastre um voo em /voos e crie a primeira auditoria de "
                "perímetro."
            ).classes("text-caption text-grey-7")
        return
    for linha in auditorias:
        (aid, voo_id, _cliente_id, _prop_id, local, tipo, status, resumo,
         criado_por, criado_em) = linha
        achados = bd.listar_achados(aid)
        redes = bd.listar_rf(aid)
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center").style("gap: 1rem"):
                with ui.column().style("gap: 0; min-width: 0; flex: 1 1 0"):
                    ui.label(
                        f"Auditoria #{aid} · {local or 'local não informado'}"
                    ).classes("text-subtitle1")
                    ui.label(
                        f"Voo #{voo_id} · {tipo or 'perimetro'} · "
                        f"{criado_por or '—'} · {criado_em or '—'}"
                    ).classes("text-caption text-grey-7")
                ui.badge(_rotulo_status(status)).props(
                    f"color={_cor_status(status)}")
            if resumo:
                ui.label(resumo).classes("text-body2")
            ui.label(
                f"{len(achados)} achado(s) · {len(redes)} rede(s) RF"
            ).classes("text-caption text-grey-7")

            with ui.expansion(
                    f"Achados ({len(achados)}) e redes RF ({len(redes)})",
                    icon="manage_search").classes("w-full").props(
                    f"data-testid=perimetro-detalhes-{aid}"):
                _tabela_achados(achados, aid)
                _tabela_rf(redes, aid)

            with ui.row().style("gap: .5rem"):
                botao("Gerar laudo PDF", icone="picture_as_pdf",
                      variante="contorno", chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid: _gerar_pdf(ator, i)
                      ).props(f"data-testid=perimetro-pdf-{aid}")
                botao("Achado", icone="add_alert", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid: _dialogo_achado(
                          ator, i, refresh)
                      ).props(f"data-testid=perimetro-achado-{aid}")
                botao("Importar RF", icone="wifi_find", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid: _dialogo_rf(
                          ator, i, refresh)
                      ).props(f"data-testid=perimetro-importar-rf-{aid}")
                botao("Concluir", icone="task_alt", variante="contorno",
                      chave_modulo=bd.CHAVE_MODULO,
                      on_click=lambda _, i=aid: _concluir(ator, i, refresh)
                      ).props(f"data-testid=perimetro-concluir-{aid}")


def _gerar_pdf(ator, auditoria_id):
    """Gera o laudo PDF do perímetro com achados físicos e RF (BSSID em hash)."""
    try:
        from mod_skyrover import voos
        linha = bd.obter_auditoria(auditoria_id)
        if not linha:
            notificar("Auditoria não encontrada.", tipo="negative")
            return
        voo_id = linha[1]
        local = linha[4] or "perímetro"
        tipo = linha[5] or "perimetro"
        resumo = linha[7] or ""
        ocorrencias = []
        for a in bd.listar_achados(auditoria_id):
            ocorrencias.append({
                "classe": a[2],
                "severidade": a[3],
                "area_m2": 0,
                "confianca": float(a[4] or 0),
                "evidencia": a[6] or "",
                "revisao_humana": int(a[5] or 0),
            })
        for r in bd.listar_rf(auditoria_id):
            ocorrencias.append({
                "classe": f"rf:{r[2] or 'SSID'}",
                "severidade": r[9] or "baixo",
                "area_m2": 0,
                "confianca": 0.0,
                "evidencia": (
                    f"hash {str(r[3] or '')[:12]}… · banda {r[4]} · "
                    f"canal {r[5]} · rssi {r[6]} · {r[7]} · "
                    f"fora do perímetro: {'sim' if r[8] else 'não'}"
                ),
                "revisao_humana": 0,
            })
        titulo = f"Perímetro — {local} ({tipo}) — Auditoria #{auditoria_id}"
        caminho = voos.gerar_laudo_modulo_pdf(
            bd.CHAVE_MODULO, voo_id, titulo, resumo, ocorrencias, ator=ator)
        if not caminho:
            notificar("Não foi possível gerar o PDF.", tipo="negative")
            return
        with ui.dialog() as dlg, ui.card().classes("w-full max-w-[560px]"):
            ui.label("Laudo de perímetro gerado").classes("text-h6")
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


def _tabela_achados(achados, auditoria_id):
    if not achados:
        ui.label("Nenhum achado físico registrado.").classes(
            "text-caption text-grey-7")
        return
    with ui.column().classes("w-full").style("gap: .35rem").props(
            f"data-testid=perimetro-lista-achados-{auditoria_id}"):
        for (aid, _aud, classe, severidade, confianca, revisao, evidencia,
             lat, lon, criado_em) in achados:
            with ui.row().classes("w-full items-center").style("gap: .5rem"):
                ui.badge(classe or "—").props("outline")
                ui.badge(severidade or "—").props(
                    f"color={_cor_severidade(severidade)}")
                ui.label(
                    f"confiança {float(confianca or 0):.2f} · "
                    f"{'revisado' if revisao else 'pendente de revisão'} · "
                    f"{criado_em or '—'}"
                ).classes("text-caption text-grey-7")
                if lat is not None and lon is not None:
                    ui.label(f"{float(lat):.5f}, {float(lon):.5f}").classes(
                        "text-caption text-grey-7")
                if not revisao:
                    botao("Revisar", icone="verified", variante="texto",
                          chave_modulo=bd.CHAVE_MODULO,
                          on_click=lambda _, i=aid: _revisar(i)
                          ).props(f"data-testid=perimetro-revisar-{aid}")
            if evidencia:
                ui.label(evidencia).classes("text-body2").style(
                    "padding-left: .5rem")


def _tabela_rf(redes, auditoria_id):
    if not redes:
        ui.label("Nenhuma rede RF importada.").classes(
            "text-caption text-grey-7")
        return
    with ui.column().classes("w-full").style("gap: .35rem").props(
            f"data-testid=perimetro-lista-rf-{auditoria_id}"):
        for (rid, _aud, ssid, bssid_hash, banda, canal, rssi, seguranca,
             fora, risco, evidencia, _criado_em) in redes:
            with ui.row().classes("w-full items-center").style("gap: .5rem"):
                ui.label(ssid or "(SSID oculto)").classes("text-body2")
                ui.label(
                    f"{banda or '—'} · canal {canal or 0} · "
                    f"{float(rssi or 0):.0f} dBm"
                ).classes("text-caption text-grey-7")
                ui.badge(seguranca or "desconhecida").props("outline")
                ui.badge(risco or "baixo").props(
                    f"color={_cor_risco(risco)}")
                if fora:
                    ui.badge("fora do perímetro").props("color=red")
                if bssid_hash:
                    ui.label(f"hash {str(bssid_hash)[:12]}…").classes(
                        "text-caption text-grey-6")
            if evidencia:
                ui.label(evidencia).classes("text-caption text-grey-7").style(
                    "padding-left: .5rem")


def _opcoes_voos():
    try:
        from mod_skyrover import voos
        disponiveis = voos.listar_voos()
    except Exception:
        disponiveis = []
    opcoes = {}
    for voo in disponiveis or []:
        if isinstance(voo, dict):
            vid = voo.get("id")
            data_voo = voo.get("data_voo") or "sem data"
            cliente = voo.get("cliente_nome") or ""
        else:
            vid = voo[0] if voo else None
            data_voo = (voo[3] if len(voo) > 3 else "") or "sem data"
            cliente = voo[10] if len(voo) > 10 else ""
        if vid is not None:
            opcoes[vid] = f"#{vid} · {data_voo} · {cliente}"
    return opcoes


def _dialogo_nova(ator, refresh):
    opcoes = _opcoes_voos()
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[720px]"):
        ui.label("Nova auditoria de perímetro").classes("text-h6")
        if not opcoes:
            ui.label(
                "Nenhum voo cadastrado. Cadastre um voo em /voos antes de "
                "criar a auditoria."
            ).classes("text-body2 text-orange-9")
            botao("Fechar", variante="texto", on_click=dlg.close)
            dlg.open()
            return
        voo = ui.select(opcoes, label="Voo",
                        value=next(iter(opcoes))).props(
            "outlined dense").classes("w-full").props(
            "data-testid=perimetro-voo")
        local = ui.input("Local / unidade").props(
            "outlined dense").classes("w-full").props(
            "data-testid=perimetro-local")
        tipo = ui.select({t: t for t in bd.TIPOS},
                         label="Tipo de auditoria", value="perimetro").props(
            "outlined dense").classes("w-full").props(
            "data-testid=perimetro-tipo")
        resumo = ui.textarea("Resumo / escopo").props(
            "outlined dense").classes("w-full").props(
            "data-testid=perimetro-resumo")
        ui.label(
            "A varredura RF só pode ser importada com autorização do "
            "responsável pela rede. O BSSID é armazenado apenas como hash "
            "SHA-256."
        ).classes("text-caption text-grey-7")

        def salvar():
            try:
                ok, msg = bd.criar_auditoria(
                    ator, voo.value, local.value or "", tipo.value or
                    "perimetro", resumo.value or "")
                if ok:
                    notificar("Auditoria criada.", tipo="positive")
                    dlg.close()
                    refresh()
                else:
                    notificar(str(msg), tipo="negative")
            except Exception as e:
                try:
                    _log().exception(f"salvar auditoria: falha | {e}")
                except Exception:
                    pass
                notificar("Erro ao salvar a auditoria.", tipo="error")

        with ui.row().classes("w-full justify-end").style("gap: .5rem"):
            botao("Cancelar", variante="texto", on_click=dlg.close)
            botao("Salvar", icone="save", chave_modulo=bd.CHAVE_MODULO,
                  on_click=salvar).props(
                "data-testid=perimetro-salvar")
    dlg.open()


def _dialogo_achado(ator, auditoria_id, refresh):
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[640px]"):
        ui.label(f"Achado · auditoria #{auditoria_id}").classes("text-h6")
        classe = ui.select({c: c for c in bd.CLASSES},
                           label="Classe", value=bd.CLASSES[0]).props(
            "outlined dense").classes("w-full").props(
            "data-testid=perimetro-achado-classe")
        severidade = ui.select({s: s for s in bd.SEVERIDADES},
                               label="Severidade", value="media").props(
            "outlined dense").classes("w-full").props(
            "data-testid=perimetro-achado-severidade")
        with ui.row().classes("w-full").style("gap: .75rem"):
            confianca = ui.number("Confiança (0-1)", value=0,
                                  format="%.2f").props(
                "outlined dense").classes("w-full")
            revisao = ui.checkbox("Revisado por humano", value=False)
        with ui.row().classes("w-full").style("gap: .75rem"):
            latitude = ui.number("Latitude", format="%.6f").props(
                "outlined dense").classes("w-full")
            longitude = ui.number("Longitude", format="%.6f").props(
                "outlined dense").classes("w-full")
        evidencia = ui.textarea("Evidência / observação").props(
            "outlined dense").classes("w-full").props(
            "data-testid=perimetro-achado-evidencia")

        def salvar():
            ok, msg = bd.adicionar_achado(
                ator, auditoria_id, classe.value, severidade.value,
                confianca.value or 0, 1 if revisao.value else 0,
                evidencia.value or "", latitude.value, longitude.value)
            if ok:
                notificar("Achado registrado.", tipo="positive")
                dlg.close()
                refresh()
            else:
                notificar(str(msg), tipo="negative")

        with ui.row().classes("w-full justify-end").style("gap: .5rem"):
            botao("Cancelar", variante="texto", on_click=dlg.close)
            botao("Registrar", icone="save", chave_modulo=bd.CHAVE_MODULO,
                  on_click=salvar).props(
                "data-testid=perimetro-achado-salvar")
    dlg.open()


def _dialogo_rf(ator, auditoria_id, refresh):
    with ui.dialog() as dlg, ui.card().classes("w-full max-w-[760px]"):
        ui.label(f"Varredura RF · auditoria #{auditoria_id}").classes(
            "text-h6")
        ui.label(
            "Importe um CSV/JSON de varredura ou tente nmcli/iw no "
            "equipamento. Use somente em rede própria ou com autorização "
            "escrita do responsável. O BSSID cru é descartado: fica só o "
            "hash SHA-256."
        ).classes("text-caption text-grey-7 text-orange-9")
        formato = ui.select(
            {"auto": "Detectar automaticamente", "csv": "CSV/TSV",
             "json": "JSON"}, label="Formato", value="auto").props(
            "outlined dense").classes("w-full").props(
            "data-testid=perimetro-rf-formato")
        area = ui.textarea(
            "Conteúdo CSV/JSON",
            placeholder="ssid,bssid,banda,canal,rssi,seguranca\n"
                        "RedeExemplo,AA:BB:CC:DD:EE:FF,2.4GHz,6,-48,WPA2"
        ).props("outlined dense autogrow").classes("w-full").props(
            "data-testid=perimetro-rf-conteudo")

        def _parsear(texto, escolha):
            if escolha == "csv":
                return rf_scan.parse_csv(texto)
            if escolha == "json":
                return rf_scan.parse_json(texto)
            limpo = (texto or "").lstrip()
            if limpo.startswith("[") or limpo.startswith("{"):
                registros = rf_scan.parse_json(texto)
                if registros:
                    return registros
            return rf_scan.parse_csv(texto)

        def _importar(registros, origem):
            if not registros:
                notificar(f"Nenhum registro válido em {origem}.",
                          tipo="warning")
                return
            ok, msg = bd.importar_rf(ator, auditoria_id, registros)
            if ok:
                notificar(
                    f"{msg} rede(s) importada(s) de {origem}. "
                    f"BSSID armazenado como hash.", tipo="positive")
                dlg.close()
                refresh()
            else:
                notificar(str(msg), tipo="negative")

        def importar_texto():
            try:
                registros = _parsear(area.value or "", formato.value or "auto")
                _importar(registros, "conteúdo colado")
            except Exception as e:
                try:
                    _log().exception(f"importar RF: falha | {e}")
                except Exception:
                    pass
                notificar("Erro ao importar a varredura RF.", tipo="error")

        def varrer_agora():
            try:
                registros = rf_scan.escanear_ao_vivo()
                _importar(registros, "varredura local")
            except Exception as e:
                try:
                    _log().exception(f"varrer agora: falha | {e}")
                except Exception:
                    pass
                notificar("Varredura local indisponível.", tipo="warning")

        with ui.row().classes("w-full justify-end").style("gap: .5rem"):
            botao("Cancelar", variante="texto", on_click=dlg.close)
            botao("Varrer agora", icone="wifi_find", variante="contorno",
                  chave_modulo=bd.CHAVE_MODULO,
                  on_click=varrer_agora).props(
                "data-testid=perimetro-rf-varrer")
            botao("Importar", icone="upload", chave_modulo=bd.CHAVE_MODULO,
                  on_click=importar_texto).props(
                "data-testid=perimetro-rf-importar")
    dlg.open()


def _revisar(achado_id):
    try:
        if bd.marcar_revisao(achado_id, True):
            notificar("Achado marcado como revisado.", tipo="positive")
        else:
            notificar("Não foi possível marcar o achado.", tipo="negative")
    except Exception as e:
        try:
            _log().exception(f"_revisar: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao marcar a revisão.", tipo="error")


def _concluir(ator, auditoria_id, refresh):
    try:
        ok, msg = bd.atualizar_status(
            auditoria_id, "concluido",
            resumo="Auditoria de perímetro concluída. Revisar os achados e "
                   "as redes RF antes de emitir o laudo.")
        notificar(str(msg), tipo="positive" if ok else "negative")
        if ok:
            refresh()
    except Exception as e:
        try:
            _log().exception(f"concluir: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao concluir a auditoria.", tipo="error")
