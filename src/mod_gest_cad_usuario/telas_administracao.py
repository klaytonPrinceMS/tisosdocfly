"""User management — administration tab (admin geral only).

Aba Administração do módulo `gest_cad_usuario`: card padrão
"Configurações de cores" (via `bloco_aparencia` — prévia ao vivo e campos
de cores no padrão do tisosdocfly; "Restaurar padrão" usa `tema["_defaults"]`
e grava "" nos campos de botão = usar o padrão do próprio módulo em
`PADROES_TEMA`) e card de configurações específicas (tamanho mínimo da
senha). A edição de nome/ícone/ativo do módulo NÃO existe aqui — é
exclusiva do painel central /configuracoes (aba Módulo).

EN: Administration tab for `gest_cad_usuario`. Exposes the standard
"Configurações de cores" cupê (theme overrides saved under the `usuarios`
module key) and module-specific knobs such as the minimum password length.
Reserved for the global admin — module-level admins don't see this tab.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from nicegui import ui

from mod_tisosdocfly import observabilidade
from mod_tisosdocfly.bd_manipulador import audit_log
from mod_tisosdocfly.tema_modulo import bloco_aparencia, ler_tema, notificar
from mod_tisosdocfly.ui_comum import botao, card_admin, rodape_salvar_restaurar
from mod_gest_cad_usuario import bd_manipulador as gest

log = observabilidade.get_logger("gest_cad_usuario")


def mostrar_administracao(ator: str):
    """Render the administration tab content for the global admin.

    Renders the full administration panel: card with the standard
    appearance cupê (`bloco_aparencia`) + a module-specific card with the
    minimum password length. Relies on `ler_tema("usuarios", ...)` and
    `gest.senha_minima()` — no external state needed (the parent `mostrar_tela`
    simply calls this when the global admin selects the Administração tab).

    PT-BR: Renderiza todo o conteúdo do painel "Administração" (exclusivo do
    admin geral): card de aparência (6 campos de tema) + card de
    configurações específicas (tamanho mínimo da senha). Botões vazios
    herdam o tema do sistema (`tisosdocfly_*`). Use `ui.navigate.reload()` nos
    callbacks de salvar/restaurar para que o novo tema entre em vigor sem
    reiniciar o servidor — todo o ajuste é live.
    """
    try:
        _mostrar_administracao_segura(ator)
    except Exception:
        log.exception("mostrar_administracao: falha ao montar a aba Administração")
        notificar("Erro ao carregar a aba Administração", tipo="error")


def _mostrar_administracao_segura(ator: str):
    """Body of `mostrar_administracao` (see docstring above)."""
    from mod_tisosdocfly.bd_conexao import set_config

    tema = ler_tema("usuarios", cor_botao="#000000", cor_texto_botao="#FFFFFF",
                    texto_header="Cadastro de usuários, papéis e acessos por módulo (soft CRUD · LGPD).")
    tema["_defaults"] = {
        "cor_botao": "",
        "cor_texto_botao": "",
        "cor_fundo": "",
        "cor_titulo": "#212121",
        "btn_tamanho": "",
        "texto_header": "Cadastro de usuários, papéis e acessos por módulo (soft CRUD · LGPD).",
    }

    ui.colors(primary=tema["cor_botao"], accent=tema["cor_botao"])

    bloco_aparencia(ator, "usuarios", tema,
                    ao_salvar_descricao="configurações de cores salvas",
                    prefixo_auditoria="gest_cad_usuario")

    with card_admin("Configurações específicas", icone="tune",
                    chave_modulo="usuarios", grade=False, aberto=False):
        ui.label("Aplicado ao criar, duplicar e redefinir senha de usuário. "
                 "Valem sem restart.").classes("text-caption text-grey-6")
        inp_senha = ui.number(
            "Tamanho mínimo da senha (caracteres)",
            value=gest.senha_minima(), min=4, max=32, precision=0,
        ).props("outlined dense").classes("w-64") \
            .tooltip("Aplicado ao criar usuário e redefinir senha.")

        def salvar():
            """Applies the minimum-password-length setting and reloads.

            Grava `usuarios_senha_min` (clamp 4–32), audita, notifica e
            recarrega após 1 segundo — aplicação sem restart."""
            try:
                set_config("usuarios_senha_min",
                           max(4, int(inp_senha.value or gest.senha_minima())))
                try:
                    audit_log(ator, "gest_cad_usuario", "configuracao",
                              "tamanho mínimo de senha alterado")
                except Exception as e:
                    log.warning(f"audit_log falhou em gest_cad_usuario config: {e}")
                notificar("Configuração aplicada (vale sem reiniciar)",
                          tipo="positive")
                ui.timer(1.0, lambda: ui.navigate.reload(), once=True)
            except Exception:
                log.exception("gest_cad_usuario: falha ao salvar tamanho mínimo de senha")
                notificar("Erro inesperado ao salvar configuração", tipo="error")

        def resetar():
            """Restores the default minimum password length (6) and reloads.

            Restaura `usuarios_senha_min` para 6, audita, notifica e
            recarrega após 1 segundo."""
            try:
                set_config("usuarios_senha_min", 6)
                try:
                    audit_log(ator, "gest_cad_usuario", "configuracao",
                              "tamanho mínimo de senha restaurado ao padrão")
                except Exception as e:
                    log.warning(f"audit_log falhou em gest_cad_usuario reset: {e}")
                notificar("Padrões restaurados", tipo="positive")
                ui.timer(1.0, lambda: ui.navigate.reload(), once=True)
            except Exception:
                log.exception("gest_cad_usuario: falha ao restaurar tamanho mínimo de senha")
                notificar("Erro inesperado ao restaurar configuração", tipo="error")

        rodape_salvar_restaurar(salvar, restaurar=resetar, chave_modulo="usuarios")

    # Os cards de folha são OPCIONAIS no produto de laudos. Cada um roda
    # isolado: se o arquivo/coleta sumiu, o painel administrativo continua
    # funcionando e o erro fica no log.
    if _folha_tem_dados_locais():
        for _rotulo, _render_card in (("ficha detalhada", _card_detalhe),
                                      ("diárias", _card_diarias)):
            try:
                _render_card(ator)
            except Exception:
                log.exception(
                    f"mostrar_administracao: falha ao montar card de "
                    f"{_rotulo}; seguindo sem ele")

    from mod_tisosdocfly.rotinas import painel_backup
    painel_backup(ator, "usuarios")


def _folha_tem_dados_locais() -> bool:
    """Diz se ainda há folha (arquivos ou linhas) para justificar os cards.

    EN: Whether the payroll cards still have any data source.

    PT-BR: O produto não distribui mais a folha. Sem `dados/` nem linhas nas
    tabelas de folha, os cards de coleta/carga seriam apenas ruído — e a
    tela administrativa precisa continuar utilizável sem eles. Qualquer
    falha vira `False` (fail-soft).
    """
    try:
        base = os.path.join(_dir_modulo_gest(), "dados")
        if os.path.isdir(base):
            return True
    except Exception as e:
        log.warning(f"_folha_tem_dados_locais: falha ao checar dados/ | {e}")
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd
        return bool(_bd.folha_tem_dados())
    except Exception as e:
        log.warning(f"_folha_tem_dados_locais: falha ao consultar banco | {e}")
        return False


def _dir_modulo_gest():
    """Pasta do módulo (para achar `coleta_kbp.py` e `dados/`)."""
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return ""


def _status_detalhe():
    """Lê o estado da coleta/carga do detalhe (só arquivos, sem banco).

    Devolve dict com `json` (existe, total, competência, coletado_em,
    confronto, erros), `parcial` (lidas, próxima, modificada_em) e `lock`
    (iniciada_em, pid). Tudo fail-soft: arquivo ausente/ilegível vira
    campo vazio, nunca exceção (AGENTS §3.2).
    """
    import json as _json
    import time as _time
    status = {"json": None, "parcial": None, "lock": None,
              "capturado": None, "cadastro": None, "total_folha": 0}
    try:
        base = os.path.join(_dir_modulo_gest(), "dados")
        # O TOTAL DA FOLHA é o denominador da porcentagem. Sem ele, o painel
        # não sabe se 400 de 400 do parcial é quase tudo ou quase nada.
        try:
            arq_folha = os.path.join(base, "funcionarios.json")
            if os.path.exists(arq_folha):
                with open(arq_folha, encoding="utf-8") as f:
                    bruto_folha = _json.load(f)
                status["total_folha"] = len(bruto_folha.get("servidores") or [])
        except Exception as e:
            log.warning(f"gest status detalhe (folha): {e}")
        arq_json = os.path.join(base, "funcionarios_detalhe.json")
        try:
            if os.path.exists(arq_json):
                with open(arq_json, encoding="utf-8") as f:
                    bruto = _json.load(f)
                confronto = bruto.get("confronto") or []
                status["json"] = {
                    "total": bruto.get("total") or 0,
                    "competencia": bruto.get("competencia") or "",
                    "coletado_em": bruto.get("coletado_em") or "",
                    "mesma": sum(1 for c in confronto
                                 if (c or {}).get("veredito") == "MESMA_PESSOA"),
                    "homonimos": sum(1 for c in confronto
                                     if (c or {}).get("veredito") == "HOMONIMO"),
                    "erros": len(bruto.get("erros") or []),
                    "modificado_em": _time.strftime(
                        "%d/%m %H:%M",
                        _time.localtime(os.path.getmtime(arq_json))),
                }
        except Exception as e:
            log.warning(f"gest status detalhe (json): {e}")
        try:
            arq_par = os.path.join(base, "funcionarios_detalhe.parcial.json")
            if os.path.exists(arq_par):
                with open(arq_par, encoding="utf-8") as f:
                    bruto = _json.load(f)
                fichas = bruto.get("fichas") or []
                status["parcial"] = {
                    "lidas": len(fichas),
                    "competencia": bruto.get("competencia") or "",
                    "modificado_em": _time.strftime(
                        "%d/%m %H:%M",
                        _time.localtime(os.path.getmtime(arq_par))),
                }
        except Exception as e:
            log.warning(f"gest status detalhe (parcial): {e}")
        try:
            arq_prog = os.path.join(base, "coleta_progresso.json")
            if os.path.exists(arq_prog):
                with open(arq_prog, encoding="utf-8") as f:
                    bruto = _json.load(f)
                status["progresso"] = {
                    "competencia": bruto.get("competencia") or "",
                    "total": int(bruto.get("total") or 0),
                    "lidas": int(bruto.get("lidas") or 0),
                    "ultimo_nome": bruto.get("ultimo_nome") or "",
                    "ultimo_matricula": bruto.get("ultimo_matricula") or "",
                    "ultimo_cpf": bruto.get("ultimo_cpf") or "",
                    "atualizado_em": bruto.get("atualizado_em") or "",
                    "pid": bruto.get("pid") or 0,
                }
        except Exception as e:
            log.warning(f"gest status detalhe (progresso): {e}")
        try:
            arq_lock = os.path.join(base, ".coleta_kbp.lock")
            if os.path.exists(arq_lock):
                with open(arq_lock, encoding="utf-8") as f:
                    bruto = _json.load(f)
                status["lock"] = {
                    "iniciada_em": bruto.get("iniciada_em") or "",
                    "pid": bruto.get("pid") or 0,
                }
        except Exception as e:
            log.warning(f"gest status detalhe (lock): {e}")
    except Exception as e:
        log.warning(f"gest status detalhe: {e}")
    # Quantos servidores JÁ estão com contracheque no banco, e quantos o
    # cadastro tem. É o par que responde "quantas pessoas foram capturadas
    # até agora" — o número que o responsável fica olhando durante a hora e
    # meia de captura, e que até agora não tinha onde aparecer.
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd_st
        _det = _bd_st.contar_detalhes_financeiros()
        status["capturado"] = {
            "fichas": _det.get("fichas", 0),
            "pessoas": _det.get("pessoas", 0),
            "competencia": _det.get("competencia") or "",
        }
        status["cadastro"] = {"usuarios": _bd_st.contar_usuarios_total()}
    except Exception as e:
        log.warning(f"gest status detalhe (banco): {e}")
    return status


def _texto_status_detalhe(status):
    """O estado da coleta em linhas legíveis, com PORCENTAGEM.

    A porcentagem é calculada contra o total da FOLHA (`funcionarios.json`),
    não contra o que o JSON já tem: sem isso, uma coleta a meio caminho
    mostraria "100%" — porque o arquivo parcial tem 400 de 400 do que ele
    próprio planejou ler, e a pessoa achava que a folha inteira estava
    pronta.
    """
    try:
        linhas = []
        total_folha = int(status.get("total_folha") or 0)
        par = status.get("parcial") or {}
        js = status.get("json") or {}
        cap = status.get("capturado") or {}
        cad = status.get("cadastro") or {}

        # --- A COLUNA DO MEIO: está rodando? ---
        lock = status.get("lock") or {}
        if lock:
            linhas.append(
                f"COLETANDO desde {lock.get('iniciada_em', '')} "
                f"(processo {lock.get('pid', 0)}).")
        elif par:
            linhas.append("COLETA INTERROMPIDA — retomada de onde parou.")

        # --- O ANDAMENTO ---
        lidas = int(par.get("lidas") or 0)
        if total_folha and lidas:
            pct = min(100.0, 100.0 * lidas / total_folha)
            linhas.append(f"Andamento: {lidas}/{total_folha} fichas "
                          f"({pct:.1f}%) da folha.")
        elif par:
            linhas.append(f"Andamento: {lidas} fichas lidas.")
        if cap.get("fichas"):
            linhas.append(
                f"No banco: {cap.get('fichas', 0)} contracheque(s) de "
                f"{cap.get('pessoas', 0)} servidor(es)"
                + (f", competência {cap['competencia']}"
                   if cap.get("competencia") else "") + ".")
        if cad.get("usuarios"):
            linhas.append(f"Cadastro: {cad['usuarios']} usuário(s).")
        if not cap.get("fichas"):
            linhas.append("Nenhum contracheque capturado ainda — a pessoa "
                          "não verá proventos, descontos nem verbas até a "
                          "primeira coleta com --total concluída.")

        if js:
            linhas.append(
                f"Arquivo: {js.get('total', 0)} fichas "
                f"({js.get('competencia', '')}) em {js.get('coletado_em', '')}; "
                f"confronto: {js.get('mesma', 0)} mesma pessoa, "
                f"{js.get('homonimos', 0)} homônimo(s), "
                f"{js.get('erros', 0)} erro(s).")
        elif not par:
            linhas.append("Arquivo: ainda não coletado.")
        return " ".join(linhas)
    except Exception:
        return "Estado indisponível."


def _card_detalhe(ator):
    """Card da ficha detalhada: config, coleta e carga no banco.

    Três blocos: (1) configuração (URL do portal + intervalo entre
    fichas, gravados na `tb_config` central — o `coleta_kbp.py` lê de lá
    antes do arquivo); (2) coleta (botão que dispara o script destacado
    do servidor, com acompanhamento pelo parcial); (3) carga (lê o JSON
    ou o CSV gerado e popula o banco do módulo, sem duplicar: mesma
    ficha+competência não regrava, mesmo CPF parcial funde, CPFs
    distintos no mesmo nome separam).
    """
    import subprocess as _sp
    import sys as _sys
    from mod_tisosdocfly.bd_conexao import get_config, set_config

    def _cfg(chave, padrao):
        try:
            valor = get_config(chave, padrao)
            return padrao if valor in (None, "") else valor
        except Exception:
            return padrao

    def _url_efetiva():
        """O endereço que o coletor vai usar DE FATO, nesta ordem.

        `tb_config` (o que o administrador digita nesta tela) manda sobre o
        arquivo — é a troca que o responsável pediu para não precisar editar
        código. Mas quando a tela está vazia, o que vale é a BASE de
        `fonte_folha.json`, que é versionada e vem no commit para qualquer
        máquina que baixar o projeto.

        Sem isto, o campo aparecia vazio mesmo com a base configurada, e o
        administrador não tinha como saber que o sistema já estava
        apontando para o portal certo — parecia desatualizado.
        """
        da_tela = str(_cfg("usuarios_portal_url", "") or "").strip()
        if da_tela:
            return da_tela
        try:
            from mod_gest_cad_usuario import coleta_kbp as _coleta
            return str(getattr(_coleta, "RAIZ", "") or "").strip()
        except Exception:
            return ""

    with card_admin("Ficha detalhada (CPF parcial)", icone="badge",
                    chave_modulo="usuarios", grade=False, aberto=False):
        ui.label("Coleta a ficha de cada servidor (CPF parcial + "
                 "vencimentos) e carrega no banco do módulo. A coleta leva "
                 "~80 min e roda destacada do servidor; a carga não duplica: "
                 "mesmo CPF parcial é uma pessoa, CPFs distintos são pessoas "
                 "distintas.").classes("text-caption text-grey-6")
        inp_url = ui.input(
            "URL do portal (portal_url)",
            value=str(_url_efetiva()),
        ).props("outlined dense").classes("w-full") \
            .tooltip("Base do portal da transparência. Sem ela a coleta "
                     "recusa sem acessar nada. O que aparece aqui é o que o "
                     "sistema usa: o valor da tela (tb_config) quando existe, "
                     "senão a base de fonte_folha.json.")
        with ui.row().classes("w-full flex-wrap").style("gap: 0.5rem"):
            inp_min = ui.number(
                "Espera mínima entre fichas (s)",
                value=float(_cfg("usuarios_detalhe_intervalo_min_s", 2.0) or 2.0),
                min=0.1, max=3600, precision=1,
            ).props("outlined dense").classes("w-56") \
                .tooltip("Sorteada a cada ficha: intervalo fixo denuncia robô.")
            inp_max = ui.number(
                "Espera máxima entre fichas (s)",
                value=float(_cfg("usuarios_detalhe_intervalo_max_s", 6.0) or 6.0),
                min=0.1, max=3600, precision=1,
            ).props("outlined dense").classes("w-56") \
                .tooltip("Pode definir tempos maiores sem problema: a coleta "
                         "é mensal e o ritmo humano protege o servidor.")

        lbl_estado = ui.label(
            _texto_status_detalhe(_status_detalhe())).classes("text-caption")

        # ============ INDICAÇÃO VISUAL DA COLETA ============
        # Antes era só o texto, e a pergunta que a pessoa faz nos primeiros
        # minutos é visual: "quanto já entrou?" e "o último foi quem?".
        # Três peças — barra, contadores e o último coletado — porque cada
        # uma responde uma pergunta diferente, e nenhuma responde as três.
        #
        # Tudo escondido enquanto não há captura nenhuma: uma tela vazia de
        # gráfico no dia 1 é ruído, não informação.
        barra_progresso = ui.linear_progress(value=0.0).classes("w-full")
        caixa_visual = ui.column().classes("w-full gap-2")
        caixa_visual.visible = False
        with caixa_visual:
            with ui.row().classes("w-full items-center gap-4 flex-wrap"):
                lb_pct = ui.label("0%").classes("text-h6 font-bold text-primary")
                with ui.column().classes("gap-0"):
                    lb_lidas = ui.label("0").classes(
                        "text-h6 font-bold text-grey-9 leading-none")
                    ui.label("fichas lidas").classes(
                        "text-caption text-grey-6 leading-none")
                with ui.column().classes("gap-0"):
                    lb_total = ui.label("—").classes(
                        "text-h6 font-bold text-grey-9 leading-none")
                    ui.label("na folha").classes(
                        "text-caption text-grey-6 leading-none")
                with ui.column().classes("gap-0"):
                    lb_capturadas = ui.label("0").classes(
                        "text-h6 font-bold text-green-7 leading-none")
                    ui.label("no banco").classes(
                        "text-caption text-grey-6 leading-none")
                with ui.column().classes("gap-0"):
                    lb_pessoas = ui.label("0").classes(
                        "text-h6 font-bold text-green-7 leading-none")
                    ui.label("servidores").classes(
                        "text-caption text-grey-6 leading-none")

            ui.separator().classes("my-1")
            caixa_ultimo = ui.row().classes("w-full items-center gap-2 flex-wrap")
            with caixa_ultimo:
                ui.icon("person", size="18px").classes("text-grey-6")
                ui.label("Último coletado:").classes(
                    "text-caption text-grey-6")
                lb_ultimo = ui.label("—").classes(
                    "text-body2 font-medium")
                ui.label("·").classes("text-grey-5")
                lb_ultimo_hora = ui.label("").classes(
                    "text-caption text-grey-6")
            ui.label("Atualiza sozinho enquanto a coleta roda.").classes(
                "text-caption text-grey-5")

        def salvar():
            """Grava URL + intervalos na `tb_config` (vale sem restart)."""
            try:
                try:
                    minimo = max(0.1, float(inp_min.value or 2.0))
                    maximo = max(minimo, float(inp_max.value or 6.0))
                except (TypeError, ValueError):
                    notificar("Intervalo inválido (use números)", tipo="error")
                    return
                set_config("usuarios_portal_url",
                           str(inp_url.value or "").strip().rstrip("/"))
                set_config("usuarios_detalhe_intervalo_min_s", minimo)
                set_config("usuarios_detalhe_intervalo_max_s", maximo)
                try:
                    audit_log(ator, "gest_cad_usuario", "configuracao",
                              "coleta de ficha (URL + intervalos) alterada")
                except Exception as e:
                    log.warning(f"audit_log falhou em gest detalhe config: {e}")
                notificar("Configuração da coleta aplicada", tipo="positive")
                ui.timer(1.0, lambda: ui.navigate.reload(), once=True)
            except Exception:
                log.exception("gest_cad_usuario: falha ao salvar config do detalhe")
                notificar("Erro inesperado ao salvar configuração", tipo="error")

        def resetar():
            """Volta URL vazia + ritmo 2–6 s (padrão)."""
            try:
                set_config("usuarios_portal_url", "")
                set_config("usuarios_detalhe_intervalo_min_s", 2.0)
                set_config("usuarios_detalhe_intervalo_max_s", 6.0)
                try:
                    audit_log(ator, "gest_cad_usuario", "configuracao",
                              "coleta de ficha restaurada ao padrão")
                except Exception as e:
                    log.warning(f"audit_log falhou em gest detalhe reset: {e}")
                notificar("Padrões restaurados", tipo="positive")
                ui.timer(1.0, lambda: ui.navigate.reload(), once=True)
            except Exception:
                log.exception("gest_cad_usuario: falha ao restaurar config do detalhe")
                notificar("Erro inesperado ao restaurar configuração", tipo="error")

        def _atualizar_estado():
            """Redesenha barra, contadores e o texto de estado.
            One call, porque os números e o texto precisam concordar: mostrar
            a barra em 40% com o texto dizendo outra coisa é pior que não
            mostrar nada."""
            try:
                status = _status_detalhe()
                prog = status.get("progresso") or {}
                cap = status.get("capturado") or {}
                total = int(prog.get("total") or status.get("total_folha") or 0)
                lidas = int(prog.get("lidas") or 0)
                pct = (min(100.0, 100.0 * lidas / total) if total and lidas
                       else 0.0)

                # --- a barra e os números só existem se houver captura ---
                lido_ = bool(lidas or cap.get("fichas"))
                barra_progresso.set_value(pct / 100.0 if lido_ else 0.0)
                barra_progresso.visible = lido_
                caixa_visual.visible = lido_

                if lido_:
                    lb_lidas.text = f"{lidas}"
                    lb_total.text = f"{total}" if total else "—"
                    lb_pct.text = f"{pct:.1f}%"
                    lb_pct.classes("text-h6 font-bold " +
                                   ("text-green-7" if pct >= 100
                                    else "text-primary"))
                    lb_capturadas.text = f"{cap.get('fichas', 0)}"
                    lb_pessoas.text = f"{cap.get('pessoas', 0)}"
                    ult = (prog.get("ultimo_nome") or "").strip()
                    if ult:
                        lb_ultimo.text = (
                            f"{ult}  ·  cpf {prog.get('ultimo_cpf') or '—'}")
                        lb_ultimo_hora.text = (
                            f"matrícula {prog.get('ultimo_matricula') or '—'} · "
                            f"às {(prog.get('atualizado_em') or '')[11:19]}")
                        caixa_ultimo.visible = True
                    else:
                        caixa_ultimo.visible = False
                lbl_estado.text = _texto_status_detalhe(status)
            except Exception as e:
                log.warning(f"detalhe: falha ao atualizar o estado ({e})")

        ocupado = {"coletar": False, "carregar": False}
        # (fail-soft da fábrica: se um botão não sair, o card se omite e a
        # aba segue viva — por isso sem encadear `.props()` na criação.)
        with ui.row().classes("w-full flex-wrap").style("gap: 0.5rem"):
            btn_coletar = botao(
                "Coletar fichas agora", icone="download", on_click=None,
                variante="solido", chave_modulo="usuarios")
            btn_andamento = botao(
                "Atualizar andamento", icone="refresh", on_click=None,
                variante="contorno", chave_modulo="usuarios")
            btn_dispensar = botao(
                "Dispensar", icone="clear", on_click=None,
                variante="contorno", chave_modulo="usuarios")
        with ui.row().classes("w-full flex-wrap items-center").style("gap: 0.5rem"):
            formato = ui.select({"JSON": "JSON (funcionarios_detalhe.json)",
                                 "CSV": "CSV (funcionarios_detalhe.csv)"},
                                value="JSON", label="Arquivo para carregar") \
                .props("outlined dense").classes("w-80")
            btn_carregar = botao(
                "Carregar no banco", icone="upload", on_click=None,
                variante="solido", chave_modulo="usuarios")
        if None in (btn_coletar, btn_andamento, btn_dispensar, btn_carregar):
            log.warning("gest detalhe: fábrica de botões falhou; card omitido")
            return
        btn_coletar.props("data-testid=coleta-kbp-iniciar")
        btn_andamento.props("data-testid=coleta-kbp-andamento")
        btn_dispensar.props("data-testid=coleta-kbp-dispensar")
        btn_carregar.props("data-testid=coleta-kbp-carregar")
        girando = ui.spinner(size="lg")
        girando.visible = False

        async def coletar():
            """Dispara o `coleta_kbp.py` destacado (não trava a tela)."""
            from nicegui import run as _run
            if ocupado["coletar"]:
                return
            ocupado["coletar"] = True
            btn_coletar.disable()
            try:
                def _disparar():
                    import json as _json
                    import time as _time
                    base = os.path.join(_dir_modulo_gest(), "dados")
                    os.makedirs(base, exist_ok=True)
                    lock = os.path.join(base, ".coleta_kbp.lock")
                    if os.path.exists(lock):
                        return False, "Já há coleta marcada como iniciada."
                    script = os.path.join(_dir_modulo_gest(), "coleta_kbp.py")
                    pasta_log = observabilidade.LOG_DIR
                    try:
                        os.makedirs(pasta_log, exist_ok=True)
                    except Exception:
                        pasta_log = base
                    arq_log = os.path.join(
                        pasta_log,
                        "coleta_kbp_" + _time.strftime("%Y%m%d-%H%M%S") + ".log")
                    with open(arq_log, "a", encoding="utf-8") as fh:
                        proc = _sp.Popen(
                            # `--total`: sem ele o script só gravava os dois
                            # arquivos e NÃO tocava no banco — o botão dizia
                            # "coletar" e o cadastro não recebia ninguém. É a
                            # diferença entre uma hora de captura e um sistema
                            # que continua vazio.
                            [_sys.executable, script, "--total"],
                            # Raiz do repositório: o script resolve tudo por
                            # caminho absoluto, mas o cwd certo evita que um
                            # `--saida` relativo caia em pasta estranha.
                            cwd=os.path.dirname(_dir_modulo_gest()),
                            stdout=fh, stderr=_sp.STDOUT,
                            creationflags=(_sp.CREATE_NEW_PROCESS_GROUP
                                           if os.name == "nt" else 0),
                            start_new_session=(os.name != "nt"))
                    with open(lock, "w", encoding="utf-8") as fh:
                        _json.dump({"iniciada_em": _time.strftime(
                            "%d/%m %H:%M"), "pid": proc.pid}, fh)
                    return True, f"Coleta iniciada (pid {proc.pid})."
                ok, msg = await _run.io_bound(_disparar)
                notificar(msg, tipo="positive" if ok else "warning")
                _atualizar_estado()
            except Exception:
                log.exception("gest_cad_usuario: falha ao disparar coleta_kbp")
                notificar("Erro inesperado ao iniciar a coleta", tipo="error")
            finally:
                ocupado["coletar"] = False
                try:
                    btn_coletar.enable()
                except Exception:
                    pass

        async def andamento():
            """Relê o parcial/JSON e atualiza o rótulo (sem recarregar)."""
            try:
                _atualizar_estado()
                notificar("Andamento atualizado", tipo="positive")
            except Exception:
                log.exception("gest_cad_usuario: falha ao ler andamento")
                notificar("Erro inesperado ao ler andamento", tipo="error")

        def dispensar():
            """Remove a marca de coleta (quando já terminou ou travou)."""
            try:
                lock = os.path.join(_dir_modulo_gest(), "dados",
                                    ".coleta_kbp.lock")
                if os.path.exists(lock):
                    os.remove(lock)
                    notificar("Marca de coleta removida", tipo="positive")
                else:
                    notificar("Nenhuma coleta marcada", tipo="warning")
                _atualizar_estado()
            except Exception:
                log.exception("gest_cad_usuario: falha ao dispensar coleta")
                notificar("Erro inesperado ao dispensar", tipo="error")

        async def carregar():
            """Lê o JSON ou CSV escolhido e popula o banco (sem duplicar)."""
            from nicegui import run as _run
            if ocupado["carregar"]:
                return
            ocupado["carregar"] = True
            btn_carregar.disable()
            girando.visible = True
            try:
                escolha = str((formato.value or "JSON")).upper()
                base = os.path.join(_dir_modulo_gest(), "dados")
                caminho = os.path.join(
                    base, "funcionarios_detalhe.json"
                    if escolha == "JSON" else "funcionarios_detalhe.csv")

                def _executar():
                    fichas, comp, _fmt = gest.ler_arquivo_detalhe(caminho)
                    if not fichas:
                        return None, (f"Arquivo {escolha} ausente ou vazio — "
                                       "colete primeiro.")
                    return gest.carregar_detalhe_ficha(
                        fichas, ator, comp), ""
                resumo, erro = await _run.io_bound(_executar)
                if resumo is None:
                    notificar(erro, tipo="warning")
                    return
                try:
                    audit_log(ator, "gest_cad_usuario", "carga_detalhe",
                              f"{escolha}: {resumo.get('gravadas', 0)} "
                              f"gravadas, {resumo.get('inalteradas', 0)} "
                              f"inalteradas, {resumo.get('fundidos', 0)} "
                              f"fundidas, {resumo.get('separados', 0)} "
                              f"separadas")
                except Exception as e:
                    log.warning(f"audit_log falhou em gest carga detalhe: {e}")
                notificar(
                    f"Carga do {escolha}: {resumo.get('gravadas', 0)} "
                    f"gravadas, {resumo.get('inalteradas', 0)} inalteradas, "
                    f"{resumo.get('fundidos', 0)} fundidas por CPF, "
                    f"{resumo.get('separados', 0)} separadas; "
                    f"{len(resumo.get('erros', []))} erro(s).",
                    tipo="positive" if not resumo.get("erros") else "warning")
                _atualizar_estado()
            except Exception:
                log.exception("gest_cad_usuario: falha ao carregar detalhe")
                notificar("Erro inesperado ao carregar no banco", tipo="error")
            finally:
                ocupado["carregar"] = False
                girando.visible = False
                try:
                    btn_carregar.enable()
                except Exception:
                    pass

        btn_coletar.on_click(coletar)
        btn_andamento.on_click(andamento)
        btn_dispensar.on_click(dispensar)
        btn_carregar.on_click(carregar)

        # A atualização automática é o que tira a pessoa de clicar "Atualizar
        # andamento" a cada minuto durante 100 minutos. O relógio é de 15 s:
        # rápido o bastante para parecer vivo, lento o bastante para não
        # pesar. E SÓ redesenha enquanto existe captura — fora dela o timer
        # não faz nada.
        def _relogio_tick():
            try:
                status = _status_detalhe()
                rodando = bool(status.get("lock")) or bool(
                    (status.get("progresso") or {}).get("lidas"))
                if rodando:
                    _atualizar_estado()
            except Exception:
                pass

        ui.timer(15.0, _relogio_tick)

        rodape_salvar_restaurar(salvar, restaurar=resetar,
                                chave_modulo="usuarios",
                                data_testid="config-aplicar-detalhe")

def _url_diarias_efetiva():
    """O endereço de diárias que o coletor usa DE FATO (tela ou fábrica)."""
    try:
        from mod_tisosdocfly.bd_conexao import get_config
        da_tela = str(get_config("usuarios_diarias_url", "") or "").strip()
        if da_tela:
            return da_tela
        from mod_gest_cad_usuario import coleta_diarias as _col
        return str(getattr(_col, "URL_DIARIAS_PADRAO", "") or "").strip()
    except Exception:
        return ""


def _texto_status_diarias():
    """Totais por ano em uma frase (o "gastos 2025 e 2026" do painel)."""
    try:
        resumo = gest.resumo_diarias_anos() or {}
        anos = resumo.get("anos") or []
        if not anos:
            return "Ainda não coletado — a coleta roda após o dia 10."
        partes = []
        for item in anos:
            try:
                pago = ("R$ {:,.2f}".format(float(item.get("vl_pago") or 0))
                        .replace(",", "X").replace(".", ",").replace("X", "."))
                partes.append(f"{item.get('ano')}: {pago} "
                              f"({int(item.get('pessoas') or 0)} pessoas)")
            except Exception:
                continue
        coletado = str((anos[-1].get("coletado_em") or ""))[:10]
        texto = "Diárias por ano — " + "; ".join(partes) + "."
        if coletado:
            texto += f" Coletado em {coletado}."
        return texto
    except Exception:
        return "Estado indisponível."


def _card_diarias(ator):
    """Card das diárias: URL configurável, coleta mensal (dia 10+) e totais."""
    from mod_tisosdocfly.bd_conexao import get_config, set_config

    def _cfg(chave, padrao):
        try:
            valor = get_config(chave, padrao)
            return padrao if valor in (None, "") else valor
        except Exception:
            return padrao

    with card_admin("Diárias (despesas de viagem)", icone="flight",
                    chave_modulo="usuarios", grade=False, aberto=False):
        ui.label("Consolidado anual por favorecido, ligado pelo CPF parcial. "
                 "A coleta roda sozinha após o dia 10 de cada mês; o botão "
                 "força sem esperar.").classes("text-caption text-grey-6")
        inp_url = ui.input(
            "URL das diárias (usuarios_diarias_url)",
            value=str(_url_diarias_efetiva()),
        ).props("outlined dense").classes("w-full") \
            .props("data-testid=diarias-url") \
            .tooltip("Página de despesas por diárias do portal. O que aparece "
                     "aqui é o que o sistema usa: o valor da tela quando "
                     "existe, senão a fábrica commitada em coleta_diarias.py.")
        inp_elem = ui.input(
            "Elementos de diária (usuarios_diarias_elementos)",
            value=str(_cfg("usuarios_diarias_elementos",
                           "339014,335014")),
        ).props("outlined dense").classes("w-80") \
            .tooltip("Elementos de despesa que são diária no portal.")
        with ui.row().classes("w-full flex-wrap").style("gap: 0.5rem"):
            inp_min = ui.number(
                "Espera mínima entre leituras (s)",
                value=float(_cfg("usuarios_diarias_intervalo_min_s", 2.0)
                            or 2.0),
                min=0.1, max=3600, precision=1,
            ).props("outlined dense").classes("w-56") \
                .tooltip("Sorteada a cada página: intervalo fixo denuncia robô.")
            inp_max = ui.number(
                "Espera máxima entre leituras (s)",
                value=float(_cfg("usuarios_diarias_intervalo_max_s", 6.0)
                            or 6.0),
                min=0.1, max=3600, precision=1,
            ).props("outlined dense").classes("w-56") \
                .tooltip("Pode definir tempos maiores sem problema: a coleta "
                         "é mensal e o ritmo humano protege o servidor.")

        lbl_estado = ui.label(_texto_status_diarias()).classes("text-caption")

        # ============ ANDAMENTO VISÍVEL (barra + último coletado) ============
        # Igual ao card da ficha: a pergunta nos primeiros minutos é visual —
        # "já entrou?" e "o último foi quem?". A barra mostra o ano em curso
        # (lidas/total do ano); abaixo, o último favorecido gravado no banco.
        # Tudo escondido enquanto não há captura nenhuma.
        barra_progresso = ui.linear_progress(value=0.0).classes("w-full")
        caixa_visual = ui.column().classes("w-full gap-2")
        caixa_visual.visible = False
        with caixa_visual:
            with ui.row().classes("w-full items-center gap-4 flex-wrap"):
                lb_pct = ui.label("0%").classes("text-h6 font-bold text-primary")
                with ui.column().classes("gap-0"):
                    lb_lidas = ui.label("0").classes(
                        "text-h6 font-bold text-grey-9 leading-none")
                    ui.label("linhas no ano").classes(
                        "text-caption text-grey-6 leading-none")
                with ui.column().classes("gap-0"):
                    lb_total = ui.label("—").classes(
                        "text-h6 font-bold text-grey-9 leading-none")
                    ui.label("no ano").classes(
                        "text-caption text-grey-6 leading-none")
                with ui.column().classes("gap-0"):
                    lb_ano = ui.label("—").classes(
                        "text-h6 font-bold text-green-7 leading-none")
                    ui.label("ano em curso").classes(
                        "text-caption text-grey-6 leading-none")
            ui.separator().classes("my-1")
            caixa_ultimo = ui.row().classes("w-full items-center gap-2 flex-wrap")
            with caixa_ultimo:
                ui.icon("person", size="18px").classes("text-grey-6")
                ui.label("Último coletado:").classes(
                    "text-caption text-grey-6")
                lb_ultimo = ui.label("—").classes(
                    "text-body2 font-medium")
                ui.label("·").classes("text-grey-5")
                lb_ultimo_hora = ui.label("").classes(
                    "text-caption text-grey-6")
            ui.label("Atualiza sozinho enquanto a coleta roda.").classes(
                "text-caption text-grey-5")

        def _pintar_progresso(prog, ultimo_banco):
            """Redesenha barra, contadores e último coletado. Nunca levanta."""
            try:
                rodando = bool((prog or {}).get("rodando"))
                total = int((prog or {}).get("total_ano") or 0)
                lidas = int((prog or {}).get("lidas_ano") or 0)
                pct = (min(100.0, 100.0 * lidas / total) if total and lidas
                       else 0.0)
                visivel = bool(rodando or (ultimo_banco or {}).get("nome_portal"))
                barra_progresso.set_value(pct / 100.0 if visivel else 0.0)
                barra_progresso.visible = visivel
                caixa_visual.visible = visivel
                if not visivel:
                    return
                lb_lidas.text = f"{lidas}" if rodando else "—"
                lb_total.text = f"{total}" if total else "—"
                lb_pct.text = f"{pct:.1f}%"
                lb_pct.classes("text-h6 font-bold " +
                               ("text-green-7" if pct >= 100 and not rodando
                                else "text-primary"))
                lb_ano.text = str((prog or {}).get("ano") or
                                  (ultimo_banco or {}).get("ano") or "—")
                nome = ((prog or {}).get("ultimo_nome") or "").strip()
                hora = ((prog or {}).get("atualizado_em") or "").strip()
                if not nome:
                    nome = str((ultimo_banco or {}).get("nome_portal") or "—")
                    hora = str((ultimo_banco or {}).get("coletado_em")
                               or "")[11:16]
                    if (ultimo_banco or {}).get("ano"):
                        nome = (f"{nome} · diárias "
                                f"{ultimo_banco.get('ano')}")
                lb_ultimo.text = nome or "—"
                lb_ultimo_hora.text = f"às {hora}" if hora else ""
                caixa_ultimo.visible = True
            except Exception as e:
                log.warning(f"diarias: falha ao pintar progresso ({e})")

        def _atualizar_andamento():
            """Relê progresso + banco e redesenha (timer e botão usam)."""
            try:
                from mod_gest_cad_usuario import coleta_diarias as _col
                _pintar_progresso(_col.obter_progresso(),
                                  gest.ultima_diaria_coletada())
                lbl_estado.text = _texto_status_diarias()
            except Exception as e:
                log.warning(f"diarias: falha ao atualizar andamento ({e})")

        def salvar():
            """Grava URL + elementos + intervalos (vale sem restart)."""
            try:
                try:
                    minimo = max(0.1, float(inp_min.value or 2.0))
                    maximo = max(minimo, float(inp_max.value or 6.0))
                except (TypeError, ValueError):
                    notificar("Intervalo inválido (use números)", tipo="error")
                    return
                set_config("usuarios_diarias_url",
                           str(inp_url.value or "").strip().rstrip("/"))
                set_config("usuarios_diarias_elementos",
                           str(inp_elem.value or "").strip())
                set_config("usuarios_diarias_intervalo_min_s", minimo)
                set_config("usuarios_diarias_intervalo_max_s", maximo)
                try:
                    audit_log(ator, "gest_cad_usuario", "configuracao",
                              "coleta de diárias (URL + elementos + ritmo) "
                              "alterada")
                except Exception as e:
                    log.warning(f"audit_log falhou em diarias config: {e}")
                notificar("Configuração das diárias aplicada", tipo="positive")
                ui.timer(1.0, lambda: ui.navigate.reload(), once=True)
            except Exception:
                log.exception("gest_cad_usuario: falha ao salvar diarias")
                notificar("Erro inesperado ao salvar configuração", tipo="error")

        def resetar():
            """Volta fábrica: URL vazia + elementos + ritmo 2–6 s."""
            try:
                set_config("usuarios_diarias_url", "")
                set_config("usuarios_diarias_elementos", "339014,335014")
                set_config("usuarios_diarias_intervalo_min_s", 2.0)
                set_config("usuarios_diarias_intervalo_max_s", 6.0)
                try:
                    audit_log(ator, "gest_cad_usuario", "configuracao",
                              "coleta de diárias restaurada ao padrão")
                except Exception as e:
                    log.warning(f"audit_log falhou em diarias reset: {e}")
                notificar("Padrões restaurados", tipo="positive")
                ui.timer(1.0, lambda: ui.navigate.reload(), once=True)
            except Exception:
                log.exception("gest_cad_usuario: falha ao restaurar diarias")
                notificar("Erro inesperado ao restaurar configuração", tipo="error")

        ocupado = {"v": False}
        with ui.row().classes("w-full flex-wrap").style("gap: 0.5rem"):
            btn_coletar = botao(
                "Coletar diárias agora", icone="download", on_click=None,
                variante="solido", chave_modulo="usuarios")
            btn_estado = botao(
                "Atualizar andamento", icone="refresh", on_click=None,
                variante="contorno", chave_modulo="usuarios")
        if None in (btn_coletar, btn_estado):
            log.warning("gest diarias: fábrica de botões falhou; card parcial")
            return
        btn_coletar.props("data-testid=diarias-coletar")
        btn_estado.props("data-testid=diarias-andamento")
        girando = ui.spinner(size="lg")
        girando.visible = False

        async def coletar():
            """Roda a coleta de diárias em `io_bound` (nunca trava a tela)."""
            from nicegui import run as _run
            if ocupado["v"]:
                return
            ocupado["v"] = True
            btn_coletar.disable()
            girando.visible = True
            try:
                from mod_gest_cad_usuario import coleta_diarias as _col

                def _executar():
                    return _col.coletar_todas(forcar=True)
                resumo = await _run.io_bound(_executar)
                try:
                    audit_log(ator, "gest_cad_usuario", "coleta_diarias",
                              f"{resumo.get('coletadas', 0)} linha(s)")
                except Exception as e:
                    log.warning(f"audit_log falhou em diarias coleta: {e}")
                if resumo.get("coletadas"):
                    notificar(f"Diárias: {resumo['coletadas']} linha(s) "
                              f"coletada(s).", tipo="positive")
                else:
                    notificar(resumo.get("motivo") or "Nada coletado.",
                              tipo="warning")
                _atualizar_andamento()
            except Exception:
                log.exception("gest_cad_usuario: falha ao coletar diarias")
                notificar("Erro inesperado ao coletar diárias", tipo="error")
            finally:
                ocupado["v"] = False
                girando.visible = False
                try:
                    btn_coletar.enable()
                except Exception:
                    pass

        def andamento():
            """Relê progresso + totais sem recarregar a página."""
            try:
                _atualizar_andamento()
                notificar("Andamento atualizado", tipo="positive")
            except Exception:
                log.exception("gest_cad_usuario: falha ao ler diarias")
                notificar("Erro inesperado ao ler andamento", tipo="error")

        btn_coletar.on_click(coletar)
        btn_estado.on_click(andamento)

        # O relógio redesenha sozinho enquanto a coleta roda (2 s: rápido o
        # bastante para parecer vivo, lento o bastante para não pesar). Fora
        # da coleta ele pinta uma vez e cala — fora dela o timer não faz nada.
        def _relogio_diarias_tick():
            try:
                from mod_gest_cad_usuario import coleta_diarias as _col
                if bool((_col.obter_progresso() or {}).get("rodando")):
                    _atualizar_andamento()
            except Exception:
                pass

        ui.timer(2.0, _relogio_diarias_tick)
        _atualizar_andamento()

        rodape_salvar_restaurar(salvar, restaurar=resetar,
                                chave_modulo="usuarios",
                                data_testid="config-aplicar-diarias")
