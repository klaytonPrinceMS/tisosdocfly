"""Skyrover module settings screen (main module) — admin_geral only.

Tela de configurações do módulo Skyrover, organizada no padrão menu_mod
(abas, como na Gestão de Usuários):

| Aba             | Conteúdo                                              |
|-----------------|-------------------------------------------------------|
| Config          | Configurações de cores + prévia, textos, gerais (RF-57), ícones |
| E-mail          | SMTP (RF-58)                                          |
| Módulo          | Páginas (nome/ícone/ativa) + registro de módulos      |
| Observabilidade | Logs loguru + OTel/Grafana (endpoint, console, Loki) |
| Documentação    | Rebuild MkDocs /documentacao                          |

Padrão de exibição (igual aos demais módulos): CADA card é recolhível
(`ui_comum.card_admin`) e tem seu rodapé PADRÃO de 2 botões —
"Restaurar padrão" e "Aplicar" — tratando EXCLUSIVAMENTE do card em
questão. Não há mais botão "APLICAR" geral na barra de abas. Ao apertar
"Aplicar", as alterações do card são gravadas, aguarda-se 1 segundo e a
página é recarregada. O card "Configurações de cores" mantém a prévia ao
vivo (padrão do Skyrover), assim como os campos de cores.
"""
import sys, os, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from collections import Counter

from nicegui import ui

from mod_skyrover.bd_conexao import get_config, set_config, PADRAO_CONFIG
from mod_skyrover.bd_manipulador import audit_log
from mod_skyrover import autenticacao, documentacao
from mod_skyrover import ui_comum
from mod_skyrover.tema_modulo import (
    btn_cls as _btn_cls_tema, btn_style as _btn_style_tema,
    titulo_cartao as _titulo_cartao, notificar,
)

CORES_PRESET = [ui_comum.CORES[k] for k in ("primaria", "info", "sucesso",
                                            "destaque", "perigo", "alerta",
                                            "cinza_escuro")]

# Módulos indispensáveis ao funcionamento do sistema: permitem renomear/ícone,
# mas NUNCA podem ser desativados (relevante para a navegação/segurança).
# Espelha `autenticacao.MODULOS_INDISPENSAVEIS` (manter sincronizado).
#
# 02/10/2026 — caiu o `blog`. A entrega sobe com tudo desligado e quem liga é
# o `master`; blog é conteúdo, não mecanismo. Quem não publica continua com um
# sistema íntegro, e quem publica liga o blog como liga qualquer outro módulo.
# (07/10) entra o `hora_certa`: hora oficial é mecanismo, não conteúdo.
MODULOS_INDISPENSAVEIS = {"auditoria", "usuarios", "hora_certa"}

# Como um módulo nasce na instalação nova (espelha a regra da semente em
# `autenticacao._garantir_tb_modulos`). Usado pelo "Restaurar padrão": restaurar
# é voltar ao que o CÓDIGO entrega, e o que o código entrega é desligado.
NATIVOS_NASCEM_LIGADOS = MODULOS_INDISPENSAVEIS

# Ícones Material comuns oferecidos no seletor visual de ícones de módulos.
ICONES_COMUNS = [
    "article", "people", "manage_accounts", "history", "folder_open", "print",
    "picture_as_pdf", "extension", "home", "settings", "menu_book", "dashboard",
    "description", "list", "tune", "mail", "query_stats", "hub", "apartment",
    "domain", "blog", "edit", "lock", "save", "restore", "add_circle",
    "link_off", "delete_forever", "open_in_new", "info", "settings_applications",
]

# Teto de LINHAS de vínculo órfão materializadas na tela (03/10/2026).
#
# Não é afordância estética: é o que impede o travamento do WebSocket. A
# versão anterior desenhava um `ui.grid` + 4 filhos por vínculo dentro do
# event-loop, e com a entrega subindo (11 dos 13 módulos desligados) são
# ~9.350 linhas — ~27 mil componentes numa requisição só, o que derrubava a
# conexão ("sistema desconectado") a cada abertura de /configuracoes. O
# TOTAL sempre aparece no texto acima da lista; isto limita só quantas linhas
# o administrador consegue inspecionar. Suba com `LIMITE_ORFAOS_RENDER`.
LIMITE_ORFAOS_RENDER = 100

# Colunas do grid de módulos — compartilhadas entre cabeçalho e linhas.
# Em desktop (lg:) 6 colunas explícitas; em sm/md, 2 colunas empilhadas
# (cada _campo_empilhado já coloca label acima do input).
COLUNAS_MODULOS = (
    "grid-cols-1 sm:grid-cols-2 lg:grid-cols-[56px_minmax(12ch,1fr)"
    "_minmax(22ch,1fr)_minmax(22ch,1fr)_minmax(20ch,1fr)_150px]"
)

BASE_DIR_MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raiz do projeto


# ------------------------------------------------------------------
# Helpers de campo empilhado — usados em TODAS as abas (Config, E-mail,
# Observabilidade, Módulo) para manter consistência visual.
# ------------------------------------------------------------------
def _campo_empilhado(label, valor, readonly=False, tooltip=None):
    """Label stacked above an input that fills its grid column.

    Rótulo acima do input (empilhado); o input ocupa a largura da
    coluna do grid até o máximo de ~30ch (encolhe em telas menores).
    label em `text-caption text-grey-7`. Retorna o `ui.input` criado."""
    with ui.column().classes("min-w-0").style("gap: 0.25rem"):
        ui.label(label).classes("text-caption text-grey-7")
        inp = ui.input(value=valor) \
            .props("dense outlined" + (" readonly" if readonly else "")) \
            .classes("w-full max-w-[30ch]")
        if tooltip:
            inp.tooltip(tooltip)
        return inp


def _botao_padrao(rotulo=None, *, tipo="primario", icone=None, tooltip=None,
                  on_click=None, color=None):
    """Compatibility alias delegating to the central `ui_comum.botao` factory.

    EN: kept for `tests/verifica_ui_comum.py` (delegation proof); production
    code calls `ui_comum.botao`/`botao_icone` directly.

    PT-BR: mantido para o `tests/verifica_ui_comum.py` (prova de delegação);
    o código de produção chama `ui_comum.botao`/`botao_icone` direto (sem
    intermediário). Delega o corpo à fábrica central, preservando a
    equivalência byte-a-byte das variantes (`tipo` = `variante` de
    `ui_comum.botao`; `color` = `cor`). Retorna o `ui.button` criado.
    """
    return ui_comum.botao(rotulo, variante=tipo, icone=icone, tooltip=tooltip,
                          on_click=on_click, cor=color, chave_modulo="skyrover")


def _campo_icone(valor_inicial):
    """Material icon free-text input (fills column) with a picker above.

    Campo livre de ícone Material Icons que preenche a coluna do
    grid (máx. ~30ch) com pré-visualização viva. O seletor visual
    (botão `grid_view` + menu com `ICONES_COMUNS`) fica empilhado
    ACIMA do input. Retorna o `ui.input` cujo `.value` é o nome
    do ícone."""
    with ui.column().classes("min-w-0").style("gap: 0.25rem"):
        with ui.row().classes("items-center").style("gap: 0.25rem"):
            with ui.menu() as menu:
                with ui.grid(columns="repeat(6, 1fr)").classes("p-1").style("gap: 0.25rem"):
                    for nome_icone in ICONES_COMUNS:
                        ui_comum.botao_icone(nome_icone,
                                             on_click=lambda _, n=nome_icone: (
                                                 inp.set_value(n), menu.close()),
                                             tooltip=nome_icone,
                                             chave_modulo="skyrover")
            ui_comum.botao_icone("grid_view", on_click=menu.open,
                                 tooltip="Escolher ícone de uma lista",
                                 chave_modulo="skyrover")
            prev = ui.icon(valor_inicial or "extension").classes(
                "text-primary text-2xl shrink-0")
        inp = ui.input(value=valor_inicial) \
            .props("dense outlined").classes("w-full max-w-[30ch]") \
            .tooltip("Nome do ícone Material Icons — aparece no menu")
        inp.on_value_change(
            lambda e: prev.set_text((e.value or "extension").strip() or "extension"))
    return inp


def mostrar_tela(user_nome: str, perfil_global: str = ""):
    """Renders the /configuracoes screen (5 tabs, per-card Restaurar/Aplicar).

    Renderiza a tela de configurações do módulo Skyrover, restrita ao
    administrador geral. Monta a barra de abas (Config, E-mail, Módulo,
    Observabilidade e Documentação) SEM botão geral de salvar. Cada card
    é recolhível (`ui_comum.card_admin`) e traz o rodapé padrão de 2
    botões — "Restaurar padrão" e "Aplicar" — exclusivos do card: o
    "Aplicar" grava somente os campos daquele card, aguarda 1 segundo e
    recarrega a página (`_aplicar_card`)."""
    if perfil_global != "administrador_geral" and \
            autenticacao.perfil_global_de(user_nome) != "administrador_geral":
        ui.label("Área de configuração restrita ao administrador geral.") \
            .classes("text-h6 text-negative q-pa-xl")
        return

    def confirmar(rotulo, acao):
        """Confirmation dialog for destructive local restores.

        Diálogo de confirmação para restaurações (ação destrutiva local),
        montado via a classe `Dialogo` (pilotagem do padrão em classes —
        saída byte-idêntica a `dialogo_card`)."""
        with ui_comum.Dialogo(largura="", max_altura=False) as (dlg, card):
            _titulo_cartao(f"Restaurar padrão — {rotulo}?")
            ui.label("Os valores codificados originalmente serão reaplicados e as "
                     "alterações salvas neste item serão perdidas.").classes(
                "text-caption text-grey-7")
            with ui.row().classes("w-full justify-center items-center").style("gap: 0.5rem"):
                ui_comum.botao("Cancelar", variante="neutro",
                               on_click=dlg.close, chave_modulo="skyrover")
                ui_comum.botao("Restaurar", variante="primario", icone="restore",
                               on_click=lambda: (dlg.close(), acao()),
                               chave_modulo="skyrover")
        dlg.open()

    def restaurar_grupo(defaults, rotulo, campos=None, pos_acao=None):
        """Restores a config group to its coded defaults and audits.

        Restaura as chaves de um grupo de `tb_config` para os padrões
        codificados (PADRAO_CONFIG ou valores fixos do sistema), registra
        auditoria e notifica. `campos` (opcional) é uma lista de
        (input, chave_estado, valor) cujos `.value` e `estado_campos`
        são atualizados; `pos_acao` (opcional) roda após a gravação
        (ex.: reagendar backups, reconfigurar observabilidade)."""
        for k, v in defaults.items():
            set_config(k, v)
        if campos:
            for inp, chave_estado, valor in campos:
                inp.set_value(valor)
                estado_campos[chave_estado] = valor
        audit_log(user_nome, "skyrover", "config_restaurada",
                  f"padrões restaurados: {rotulo}")
        if pos_acao:
            pos_acao()
        notificar(f"Padrão restaurado ({rotulo})", tipo="positive")

    def _reagendar_backups(horas):
        """Reapplies the backup interval to every live module job.

        Reagenda o job vivo de backup de cada módulo com o novo
        intervalo (falhas individuais são ignoradas)."""
        from mod_skyrover import rotinas as _rot
        for chave in _rot.MAPA_BACKUPS:
            try:
                _rot.reagendar_backup(chave, horas)
            except Exception:
                pass

    ui.colors(primary=get_config("cor_principal", PADRAO_CONFIG["cor_principal"]))

    # ---- estado dos campos (lido pelos "Aplicar" de cada card) ----
    estado_campos = {}
    _sujo = set()  # chaves efetivamente editadas pelo usuário (não semeadas)
    _alerta_restart_dado = {"sim": False}

    def _alertar_restart():
        """Warns once per page load that a server restart may be needed.

        Avisa uma única vez por carregamento da página: ao trocar uma cor,
        clique APLICAR do card de Cores; se alguma área não refletir,
        reinicie o servidor."""
        if _alerta_restart_dado["sim"]:
            return
        _alerta_restart_dado["sim"] = True
        notificar("Cor alterada — clique APLICAR do card de Cores; se "
                  "alguma área não refletir a nova cor, reinicie o "
                  "servidor.",
                  tipo="warning")

    def _mudou_cor(chave_estado, valor):
        """Color field change: state + preview refresh + restart alert.

        Mudança de campo de cor: atualiza o estado, alerta sobre chaves que
        exigem restart (endpoint/OTel) e atualiza a prévia ao vivo."""
        estado_campos[chave_estado] = valor
        _sujo.add(chave_estado)
        _alertar_restart()
        _refresh_previa()

    def _mudou(chave_estado, valor):
        """Field change: state + live preview refresh (no restart alert).

        Mudança de campo não-cor: atualiza o estado e a prévia ao vivo."""
        estado_campos[chave_estado] = valor
        _sujo.add(chave_estado)
        _refresh_previa()

    def _refresh_previa():
        """Refreshes the live preview if already rendered (order-independent).

        Atualiza a prévia se já renderizada; silenciosa caso contrário
        (permite campos definidos depois da prévia)."""
        try:
            previa.refresh()
        except Exception:
            pass

    def _prev(chave_estado, chave_config, padrao=""):
        """Live preview value: unsaved field state, else saved config.

        Valor da prévia: estado não salvo do campo, ou o vigente no banco."""
        try:
            v = estado_campos.get(chave_estado, None)
            if v is None:
                v = get_config(chave_config, padrao)
        except Exception:
            v = padrao
        return (v or padrao or "").strip() or (padrao or "")

    def _v(chave_estado, chave_config, padrao=""):
        """Field value that never blanks untouched settings (anti-zeramento).

        Valor do campo que nunca zera: se o campo não passou pelo estado
        (card não editado), mantém o valor vigente no banco; se o usuário
        limpou de propósito, grava "" (limpeza intencional continua
        possível)."""
        if chave_estado in estado_campos and estado_campos[chave_estado] is not None:
            return estado_campos[chave_estado]
        try:
            return get_config(chave_config, padrao)
        except Exception:
            return padrao

    def _aplicar_cor(chave_estado, chave_config):
        """Color value for 'Aplicar': edited-empty coerces to the system default.

        Valor de cor para o Aplicar: se o campo foi editado para vazio, grava
        o padrão (PADRAO_CONFIG); se intocado, preserva o valor vigente no
        banco (mesmo quando "" — anti-zeramento)."""
        v = (_v(chave_estado, chave_config,
                PADRAO_CONFIG.get(chave_config, "")) or "").strip()
        if chave_estado in _sujo and not v:
            v = PADRAO_CONFIG.get(chave_config, "")
        return v

    def _reload_apos():
        """Reloads the page after 1 second (per-card 'Aplicar' standard).

        Recarrega a página após 1 segundo — padrão do botão "Aplicar" de
        cada card (grava, aguarda 1s e recarrega)."""
        ui.timer(1.0, lambda: ui.navigate.reload(), once=True)

    def _aplicar_card(rotulo, audit_desc, salvar_fn, msg=None, extra_msg=""):
        """Runs a per-card save, audits, notifies and reloads after 1s.

        Grava EXCLUSIVAMENTE os campos do card em questão (`salvar_fn`),
        registra auditoria `config_alterada`, notifica o resultado e
        recarrega a página após 1 segundo. `extra_msg` (opcional) é
        anexado à notificação. Falha registra loguru e notifica negativo,
        sem recarregar."""
        try:
            salvar_fn()
        except Exception:
            from mod_skyrover import observabilidade as _obs
            _obs.get_logger("skyrover").exception(
                f"falha ao aplicar card '{rotulo}'")
            notificar(f"Erro ao aplicar {rotulo}", tipo="negative")
            return
        try:
            audit_log(user_nome, "skyrover", "config_alterada", audit_desc)
        except Exception:
            pass
        msg_final = msg or f"{rotulo} aplicado — recarregando…"
        if extra_msg:
            msg_final += f" {extra_msg}"
        notificar(msg_final, tipo="positive")
        _reload_apos()

    _estado_aplicar = {"ocupado": False, "reload_agendado": False}

    def _pode_escrever() -> bool:
        """Gate DDD: só administrador_geral aplica (dupla camada com a guarda da rota)."""
        try:
            return autenticacao.perfil_global_de(user_nome) == "administrador_geral"
        except Exception:
            return False

    async def _aplicar_card_async(rotulo, audit_desc, salvar_fn, msg=None,
                                  extra_msg="", recarregar=True):
        """Versão assíncrona do Aplicar: não bloqueia o event-loop (sem disconnect).

        Executa `salvar_fn` em `run.io_bound` (thread), com trava de
        reentrância (`ocupado`), spinner de progresso e reload único
        (`reload_agendado`). Mantém `_aplicar_card` síncrono legado para
        compatibilidade dos testes estáticos.
        """
        from nicegui import run as _run
        if not _pode_escrever():
            notificar("Sem permissão — só administrador geral aplica.",
                      tipo="negative")
            return
        if _estado_aplicar["ocupado"]:
            notificar("Aguarde a operação em andamento…", tipo="warning")
            return
        _estado_aplicar["ocupado"] = True
        _status = ui.row().classes("w-full items-center justify-center") \
            .style("gap: 0.5rem")
        with _status:
            ui.spinner(size="lg").props(f"aria-label=Aplicando {rotulo}")
            ui.label(f"Aplicando {rotulo}…").classes("text-caption text-grey-7")
        try:
            await _run.io_bound(salvar_fn)
        except Exception:
            from mod_skyrover import observabilidade as _obs
            _obs.get_logger("skyrover").exception(
                f"falha ao aplicar card '{rotulo}'")
            try:
                _status.clear()
            except Exception:
                pass
            _estado_aplicar["ocupado"] = False
            notificar(f"Erro ao aplicar {rotulo}", tipo="negative")
            return
        try:
            audit_log(user_nome, "skyrover", "config_alterada", audit_desc)
        except Exception:
            pass
        msg_final = msg or f"{rotulo} aplicado — recarregando…"
        if extra_msg:
            msg_final += f" {extra_msg}"
        notificar(msg_final, tipo="positive")
        try:
            _status.clear()
        except Exception:
            pass
        _estado_aplicar["ocupado"] = False
        if recarregar:
            _reload_apos()

    def _aplicar_card_sem_reload(rotulo, audit_desc, salvar_fn):
        """Aplicar síncrono sem reload (ex.: Banco exige restart do servidor)."""
        try:
            salvar_fn()
        except Exception:
            from mod_skyrover import observabilidade as _obs2
            _obs2.get_logger("skyrover").exception(
                f"falha ao aplicar card '{rotulo}'")
            notificar(f"Erro ao aplicar {rotulo}", tipo="negative")
            return
        try:
            audit_log(user_nome, "skyrover", "config_alterada", audit_desc)
        except Exception:
            pass
        notificar("Banco de dados atualizado — REINICIE o servidor para aplicar.",
                  tipo="warning", close_button="Fechar")

    def aplicar_cores():
        """Applies ONLY the 'Configurações de cores' card fields.

        Grava exclusivamente as chaves do card de cores (cor principal,
        fundo das páginas, botões do sistema, tamanho, título, fundo e
        texto dos cards)."""
        set_config("cor_principal", _aplicar_cor("cor", "cor_principal"))
        set_config("cor_fundo", _aplicar_cor("fundo", "cor_fundo"))
        set_config("skyrover_cor_botao", _aplicar_cor("btn_cor", "skyrover_cor_botao"))
        set_config("skyrover_cor_texto_botao", _aplicar_cor("btn_cor_texto", "skyrover_cor_texto_botao"))
        _tam_btn = (_v("btn_tamanho", "skyrover_btn_tamanho", "medium") or "medium").strip().lower()
        set_config("skyrover_btn_tamanho",
                   _tam_btn if _tam_btn in ("small", "medium", "large") else "medium")
        set_config("skyrover_cor_titulo", _aplicar_cor("btn_cor_titulo", "skyrover_cor_titulo"))
        set_config("skyrover_cor_fundo_card", _aplicar_cor("card_fundo", "skyrover_cor_fundo_card"))
        set_config("skyrover_cor_texto_card", _aplicar_cor("card_texto", "skyrover_cor_texto_card"))

    def aplicar_textos():
        """Applies ONLY the 'Textos fixos' card fields."""
        for k in ("texto_login_titulo", "texto_login_subtitulo", "texto_login_hint",
                  "texto_home_saudacao", "texto_home_subtitulo", "texto_rodape"):
            set_config(k, _v(k, k, ""))
        set_config("titulo_sistema",
                   ((_v("titulo", "titulo_sistema", PADRAO_CONFIG["titulo_sistema"]) or "").strip())
                   or PADRAO_CONFIG["titulo_sistema"])

    def aplicar_gerais():
        """Applies ONLY the 'Configurações gerais' card (reagenda backups)."""
        try:
            horas = max(1, int((_v("backup_interval_hours", "backup_interval_hours", "12") or "12").strip() or 12))
        except (TypeError, ValueError):
            horas = 12
        set_config("backup_interval_hours", str(horas))
        try:
            _sessao = max(1, int((_v("sessao_retencao", "sessao_retencao", "50") or "50").strip() or 50))
        except (TypeError, ValueError):
            _sessao = 50
        set_config("sessao_retencao", str(_sessao))
        try:
            _aviso_seg = int((_v("aviso_timeout", "notificacao_timeout", "20") or "20").strip() or 20)
        except (TypeError, ValueError):
            _aviso_seg = 20
        # `max(10, …)` e não `max(1, …)`: o piso de 10 segundos é do
        # responsável (04/10/2026) e vale para o que se GRAVA também. Sem
        # isso, o painel aceitaria 1s, gravaria por cima, e o
        # `tema_modulo.notificacao_timeout` cortaria de volta só na leitura —
        # o valor ficaria mentindo no banco, e a próxima vez que este card
        # abrisse mostraria um número que o sistema não usa.
        set_config("notificacao_timeout", str(min(30, max(10, _aviso_seg))))
        _reagendar_backups(horas)

    def aplicar_icones():
        """Applies ONLY the 'Ícones' card (ícone do sistema)."""
        set_config("icone_sistema",
                   ((_v("icone", "icone_sistema", PADRAO_CONFIG["icone_sistema"]) or "").strip())
                   or PADRAO_CONFIG["icone_sistema"])

    def aplicar_smtp():
        """Applies ONLY the 'E-mail / SMTP' card."""
        for k in ("smtp_servidor", "smtp_porta", "smtp_usuario", "smtp_senha", "smtp_de"):
            set_config(k, _v(k, k, ""))
        set_config("smtp_tls", "1" if estado_campos.get("smtp_tls") else "0")

    def aplicar_obs():
        """Applies ONLY the 'Observabilidade e logs' card + reconfigures.

        Grava as chaves `log_*` e reconfigura a observabilidade; gera logs
        de teste apenas se o nível mínimo ou o nível do envio Loki
        mudaram."""
        from mod_skyrover import observabilidade
        _nivel_antes = (get_config("log_nivel", "INFO") or "INFO").upper()
        _otel_antes = (get_config("log_otel_nivel", "DEBUG") or "DEBUG").upper()
        set_config("log_ativo", "1" if estado_campos.get("log_ativo") else "0")
        set_config("log_nivel", (_v("log_nivel", "log_nivel", "INFO") or "INFO").upper())
        set_config("log_rotacao", (_v("log_rotacao", "log_rotacao", "1 month") or "1 month").strip())
        set_config("log_retencao", (_v("log_retencao", "log_retencao", "4 months") or "4 months").strip())
        set_config("log_console", (_v("log_console", "log_console", "auto") or "auto").strip().lower())
        set_config("log_otel_envio", "1" if estado_campos.get("log_otel_envio") else "0")
        set_config("log_otel_nivel", (_v("log_otel_nivel", "log_otel_nivel", "DEBUG") or "DEBUG").upper())
        observabilidade.configurar()
        _nivel_depois = (get_config("log_nivel", "INFO") or "INFO").upper()
        _otel_depois = (get_config("log_otel_nivel", "DEBUG") or "DEBUG").upper()
        if _nivel_depois != _nivel_antes or _otel_depois != _otel_antes:
            observabilidade.gerar_logs_teste_niveis()

    def aplicar_otel():
        """Applies ONLY the 'Telemetria OTel' card."""
        set_config("otel_ativo", "1" if estado_campos.get("otel_ativo") else "0")
        set_config("otel_endpoint", (_v("otel_endpoint", "otel_endpoint", "localhost:4317") or "localhost:4317").strip())
        set_config("otel_auto_start_stack", "1" if estado_campos.get("otel_auto_start_stack") else "0")
        set_config("grafana_url",
                   (_v("grafana_url", "grafana_url", "http://localhost:3000") or "http://localhost:3000").strip().rstrip("/"))

    def aplicar_paginas():
        """Applies ONLY the 'Páginas do sistema' card (nome/ícone/ativo/URL)."""
        avisos = []
        urls_alteradas = 0
        n = 0
        for chave, (inp_n, inp_i, sw_a) in estado_campos.get("paginas", {}).items():
            conn = autenticacao.get_connection()
            try:
                ativo = 1 if chave in MODULOS_INDISPENSAVEIS else (1 if sw_a.value else 0)
                conn.execute(
                    "UPDATE tb_modulos SET nome=?, icone=?, ativo=? WHERE chave=?",
                    ((inp_n.value or "").strip() or chave,
                     (inp_i.value or "").strip() or "extension",
                     ativo, chave))
                conn.commit()
            finally:
                conn.close()
            n += 1
        for chave, inp_url in estado_campos.get("urls", {}).items():
            nova_rota = (inp_url.value or "").strip()
            if not nova_rota:
                continue
            conn = autenticacao.get_connection()
            try:
                row = conn.execute(
                    "SELECT rota FROM tb_modulos WHERE chave=?", (chave,)).fetchone()
                rota_vigente = row[0] if row else None
            finally:
                conn.close()
            if rota_vigente and nova_rota != rota_vigente:
                ok, msg = autenticacao.alterar_rota_modulo(user_nome, chave, nova_rota)
                if ok:
                    urls_alteradas += 1
                else:
                    avisos.append(msg)
        extra = f"{n} página(s) aplicada(s)."
        if urls_alteradas:
            extra += f" {urls_alteradas} URL(s) alterada(s)."
        if avisos:
            extra += " Avisos: " + " | ".join(avisos)
        return extra

    def _aplicar_paginas():
        """Applies the 'Páginas do sistema' card (with warnings) + reload.

        Grava as páginas via `aplicar_paginas` e notifica com avisos de
        URL não alterada; recarrega após 1s."""
        try:
            extra = aplicar_paginas()
        except Exception:
            from mod_skyrover import observabilidade as _obs
            _obs.get_logger("skyrover").exception("falha ao aplicar páginas")
            notificar("Erro ao aplicar Páginas do sistema", tipo="negative")
            return
        try:
            audit_log(user_nome, "skyrover", "config_alterada", "páginas aplicadas")
        except Exception:
            pass
        notificar(f"Páginas aplicadas — {extra}", tipo="positive",
                  multi_line=("Avisos:" in extra),
                  close_button="Fechar" if "Avisos:" in extra else False)
        _reload_apos()

    async def _aplicar_paginas_async():
        """Versão assíncrona: grava páginas em io_bound, reload único."""
        from nicegui import run as _run_pag
        if not _pode_escrever():
            notificar("Sem permissão — só administrador geral aplica.",
                      tipo="negative")
            return
        if _estado_aplicar["ocupado"]:
            notificar("Aguarde a operação em andamento…", tipo="warning")
            return
        _estado_aplicar["ocupado"] = True
        _pag_status = ui.row().classes("w-full items-center justify-center") \
            .style("gap: 0.5rem")
        with _pag_status:
            ui.spinner(size="lg").props("aria-label=Aplicando páginas")
            ui.label("Aplicando páginas…").classes("text-caption text-grey-7")
        try:
            extra = await _run_pag.io_bound(aplicar_paginas)
        except Exception:
            from mod_skyrover import observabilidade as _obs
            _obs.get_logger("skyrover").exception("falha ao aplicar páginas")
            try:
                _pag_status.clear()
            except Exception:
                pass
            _estado_aplicar["ocupado"] = False
            notificar("Erro ao aplicar Páginas do sistema", tipo="negative")
            return
        try:
            audit_log(user_nome, "skyrover", "config_alterada", "páginas aplicadas")
        except Exception:
            pass
        notificar(f"Páginas aplicadas — {extra}", tipo="positive",
                  multi_line=("Avisos:" in extra),
                  close_button="Fechar" if "Avisos:" in extra else False)
        try:
            _pag_status.clear()
        except Exception:
            pass
        _estado_aplicar["ocupado"] = False
        _reload_apos()


    with ui.column().classes("w-full p-6").style("gap: 1rem"):
        with ui.row().classes("w-full items-center justify-between flex-nowrap "
                              "bg-white rounded-lg shadow-sm px-3 py-1").style("gap: 1rem"):
            with ui.tabs().props("dense inline-label").classes("min-w-0 overflow-x-auto") as tabs:
                tab_geral = ui.tab("Config", icon="tune")
                tab_email = ui.tab("E-mail", icon="mail")
                tab_mod = ui.tab("Módulo", icon="extension")
                tab_obs = ui.tab("Observabilidade", icon="query_stats")
                tab_docs = ui.tab("Documentação", icon="menu_book")

        with ui.tab_panels(tabs, value=tab_geral).classes("w-full bg-transparent"):

            # ============================================================
            # ABA: CONFIG — texto e cor
            # ============================================================
            with ui.tab_panel(tab_geral):
                with ui_comum.card_admin("Configurações de cores", icone="palette",
                                         chave_modulo="skyrover", grade=False,
                                         aberto=False):
                    ui.label("Cor principal, fundo das páginas, botões do sistema "
                             "(fundo/texto/tamanho) e fundo/texto dos cards. "
                             "Tudo vale sem reiniciar após Aplicar.").classes(
                        "text-caption text-grey-7 max-w-3xl -mt-2")

                    # Pré-visualização única (ao vivo, antes de salvar).
                    # Lê do estado (com fallback ao banco): independe da ordem
                    # dos cards, pois Textos/Ícones podem vir depois daqui.
                    @ui.refreshable
                    def previa():
                        """Live preview of the system header/card/buttons.

                        Prévia ao vivo do card "Configurações de cores":
                        barra do sistema (ícone + nome sobre a cor
                        principal), card de exemplo (fundo/texto/título) e
                        botões (sólido + contorno), lendo o estado pendente
                        com fallback ao banco (`_prev`)."""
                        cor = _prev("cor", "cor_principal",
                                    PADRAO_CONFIG["cor_principal"])
                        fundo = _prev("fundo", "cor_fundo",
                                      PADRAO_CONFIG["cor_fundo"])
                        ico = _prev("icone", "icone_sistema", "hub")
                        nom = _prev("titulo", "titulo_sistema", "SKYROVER")
                        c_btn = _prev("btn_cor", "skyrover_cor_botao",
                                      PADRAO_CONFIG["skyrover_cor_botao"])
                        c_txt = _prev("btn_cor_texto", "skyrover_cor_texto_botao",
                                      PADRAO_CONFIG["skyrover_cor_texto_botao"])
                        c_tam = _prev("btn_tamanho", "skyrover_btn_tamanho", "medium")
                        c_tit = _prev("btn_cor_titulo", "skyrover_cor_titulo",
                                      PADRAO_CONFIG["skyrover_cor_titulo"])
                        c_fundo = _prev("card_fundo", "skyrover_cor_fundo_card",
                                        PADRAO_CONFIG["skyrover_cor_fundo_card"])
                        c_texto = _prev("card_texto", "skyrover_cor_texto_card", "")
                        with ui.element("div").classes("rounded-lg w-full overflow-hidden") \
                                .style(f"background:{fundo}"):
                            with ui.row().classes("items-center px-4 py-2 w-full") \
                                    .style(f"background:{cor}; gap: 0.5rem"):
                                ui.icon(ico).style(f"color:{c_txt}")
                                ui.label(nom).classes("font-bold").style(f"color:{c_txt}")
                            with ui.element("div").classes("w-full") \
                                    .style("padding:0.75rem"):
                                with ui.element("div").classes("rounded-lg w-full") \
                                        .style(f"background:{c_fundo};"
                                               + (f"color:{c_texto};" if c_texto else "")
                                               + "padding:0.75rem"):
                                    ui.label("Exemplo de card") \
                                        .style(f"color:{c_tit};font-weight:700")
                                    ui.label("Texto apresentado nos cards.")
                                    with ui.row().classes("items-center flex-wrap") \
                                            .style("gap: 0.5rem"):
                                        ui.button("Botão exemplo", icon="info") \
                                            .props("unelevated no-caps") \
                                            .classes(_btn_cls_tema(c_tam)) \
                                            .style(_btn_style_tema(c_btn, c_txt))
                                        ui.button("Contorno", icon="open_in_new") \
                                            .props("outline no-caps") \
                                            .classes(_btn_cls_tema(c_tam)) \
                                            .style(f"color:{c_btn};border-color:{c_btn};")

                    previa()
                    # Refresh registrado em cada campo via _mudou/_mudou_cor
                    # (vale para campos de qualquer card, antes ou depois).

                    with ui.grid().classes("w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-4").style("gap: 1.25rem"):
                        f_cor = ui_comum.campo_cor(
                            "Cor primária (menus e destaques)",
                            chave="cor_principal",
                            padrao=PADRAO_CONFIG["cor_principal"],
                            ao_mudar=lambda e: _mudou_cor("cor", e.value))
                        f_fundo = ui_comum.campo_cor(
                            "Cor de fundo das páginas",
                            chave="cor_fundo",
                            padrao=PADRAO_CONFIG["cor_fundo"],
                            ao_mudar=lambda e: _mudou_cor("fundo", e.value))
                        b_cor = ui_comum.campo_cor(
                            "Cor geral do módulo",
                            chave="skyrover_cor_botao",
                            padrao=PADRAO_CONFIG["skyrover_cor_botao"],
                            ao_mudar=lambda e: _mudou_cor("btn_cor", e.value))
                        b_cor_txt = ui_comum.campo_cor(
                            "Cor do texto do módulo",
                            chave="skyrover_cor_texto_botao",
                            padrao=PADRAO_CONFIG["skyrover_cor_texto_botao"],
                            ao_mudar=lambda e: _mudou_cor("btn_cor_texto", e.value))
                        t_cor_tit = ui_comum.campo_cor(
                            "Cor dos títulos dos cards",
                            chave="skyrover_cor_titulo",
                            padrao=PADRAO_CONFIG["skyrover_cor_titulo"],
                            ao_mudar=lambda e: _mudou_cor("btn_cor_titulo", e.value))
                        cf_fundo = ui_comum.campo_cor(
                            "Cor de fundo dos cards",
                            chave="skyrover_cor_fundo_card",
                            padrao=PADRAO_CONFIG["skyrover_cor_fundo_card"],
                            ao_mudar=lambda e: _mudou_cor("card_fundo", e.value))
                        b_tam = ui_comum.campo_selecao(
                            "Tamanho dos botões",
                            {"small": "Pequeno", "medium": "Médio",
                             "large": "Grande"},
                            chave="skyrover_btn_tamanho", padrao="medium",
                            props="dense outlined",
                            ao_mudar=lambda e: _mudou("btn_tamanho", e.value))
                        cf_texto = ui_comum.campo_cor(
                            "Cor do texto dos cards (vazio = herda)",
                            chave="skyrover_cor_texto_card",
                            ao_mudar=lambda e: _mudou_cor("card_texto", e.value))

                    # Garante que os valores atuais já entrem no estado sem mexer
                    estado_campos["btn_cor"] = b_cor.value
                    estado_campos["btn_cor_texto"] = b_cor_txt.value
                    estado_campos["btn_tamanho"] = b_tam.value
                    estado_campos["btn_cor_titulo"] = t_cor_tit.value
                    estado_campos["card_fundo"] = cf_fundo.value
                    estado_campos["card_texto"] = cf_texto.value

                    # Garante que os valores atuais já entrem no estado sem o usuário mexer
                    estado_campos["cor"] = f_cor.value
                    estado_campos["fundo"] = f_fundo.value

                    ui_comum.rodape_salvar_restaurar(
                        salvar=lambda: _aplicar_card(
                            "Cores", "cores aplicadas (Config)", aplicar_cores),
                        restaurar=lambda: confirmar(
                            "aparência (cores, botões e cards)",
                            lambda: restaurar_grupo(
                                {"cor_principal": PADRAO_CONFIG["cor_principal"],
                                 "cor_fundo": PADRAO_CONFIG["cor_fundo"],
                                 "skyrover_cor_botao":
                                 PADRAO_CONFIG["skyrover_cor_botao"],
                                 "skyrover_cor_texto_botao":
                                 PADRAO_CONFIG["skyrover_cor_texto_botao"],
                                 "skyrover_btn_tamanho":
                                 PADRAO_CONFIG["skyrover_btn_tamanho"],
                                 "skyrover_cor_titulo":
                                 PADRAO_CONFIG["skyrover_cor_titulo"],
                                 "skyrover_cor_fundo_card":
                                 PADRAO_CONFIG["skyrover_cor_fundo_card"],
                                 "skyrover_cor_texto_card":
                                 PADRAO_CONFIG["skyrover_cor_texto_card"]},
                                "aparência",
                                campos=[
                                    (f_cor, "cor", PADRAO_CONFIG["cor_principal"]),
                                    (f_fundo, "fundo", PADRAO_CONFIG["cor_fundo"]),
                                    (b_cor, "btn_cor",
                                     PADRAO_CONFIG["skyrover_cor_botao"]),
                                    (b_cor_txt, "btn_cor_texto",
                                     PADRAO_CONFIG["skyrover_cor_texto_botao"]),
                                    (b_tam, "btn_tamanho",
                                     PADRAO_CONFIG["skyrover_btn_tamanho"]),
                                    (t_cor_tit, "btn_cor_titulo",
                                     PADRAO_CONFIG["skyrover_cor_titulo"]),
                                    (cf_fundo, "card_fundo",
                                     PADRAO_CONFIG["skyrover_cor_fundo_card"]),
                                     (cf_texto, "card_texto",
                                      PADRAO_CONFIG["skyrover_cor_texto_card"])])),
                        chave_modulo="skyrover",
                        data_testid="config-aplicar-cores")

                # ---- Textos fixos ----
                with ui_comum.card_admin("Textos fixos exibidos aos usuários",
                                         icone="text_fields",
                                         chave_modulo="skyrover", grade=False,
                                         aberto=False):
                    ui.label("Personalize as mensagens da tela de login, da página inicial "
                             "e do rodapé.").classes(
                        "text-caption text-grey-7 max-w-3xl -mt-2")

                    f_titulo = ui_comum.campo_texto(
                        "Nome do sistema no cabeçalho",
                        chave="titulo_sistema", padrao="SKYROVER",
                        tooltip="Texto que aparece no topo de cada página",
                        ao_mudar=lambda e: _mudou("titulo", e.value))

                    with ui.grid().classes("w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-3").style("gap: 1.25rem"):
                        t_login = ui_comum.campo_texto(
                            "Título da tela de login",
                            chave="texto_login_titulo",
                            padrao="SKYROVER Básica",
                            ao_mudar=lambda e: _mudou(
                                "texto_login_titulo", e.value))
                        t_sub = ui_comum.campo_texto(
                            "Subtítulo da tela de login",
                            chave="texto_login_subtitulo",
                            ao_mudar=lambda e: _mudou(
                                "texto_login_subtitulo", e.value))
                        t_hint = ui_comum.campo_texto(
                            "Ajuda abaixo do botão Entrar (login)",
                            chave="texto_login_hint",
                            ao_mudar=lambda e: _mudou(
                                "texto_login_hint", e.value))
                        t_saud = ui_comum.campo_texto(
                            "Saudação da página inicial",
                            chave="texto_home_saudacao", padrao="Olá",
                            ao_mudar=lambda e: _mudou(
                                "texto_home_saudacao", e.value))
                        t_homesub = ui_comum.campo_texto(
                            "Frase abaixo da saudação (página inicial)",
                            chave="texto_home_subtitulo",
                            ao_mudar=lambda e: _mudou(
                                "texto_home_subtitulo", e.value))
                        t_rodape = ui_comum.campo_texto(
                            "Texto do rodapé (versão anexada automaticamente)",
                            chave="texto_rodape", padrao="uso interno",
                            ao_mudar=lambda e: _mudou(
                                "texto_rodape", e.value))

                    # Garante que os valores atuais já entrem no estado sem o usuário mexer
                    estado_campos["titulo"] = f_titulo.value
                    estado_campos["texto_login_titulo"] = t_login.value
                    estado_campos["texto_login_subtitulo"] = t_sub.value
                    estado_campos["texto_login_hint"] = t_hint.value
                    estado_campos["texto_home_saudacao"] = t_saud.value
                    estado_campos["texto_home_subtitulo"] = t_homesub.value
                    estado_campos["texto_rodape"] = t_rodape.value

                    ui_comum.rodape_salvar_restaurar(
                        salvar=lambda: _aplicar_card(
                            "Textos fixos", "textos fixos aplicados", aplicar_textos),
                        restaurar=lambda: confirmar(
                            "textos fixos",
                            lambda: restaurar_grupo(
                                {"texto_login_titulo":
                                 PADRAO_CONFIG["texto_login_titulo"],
                                 "texto_login_subtitulo":
                                 PADRAO_CONFIG["texto_login_subtitulo"],
                                 "texto_login_hint":
                                 PADRAO_CONFIG["texto_login_hint"],
                                 "texto_home_saudacao":
                                 PADRAO_CONFIG["texto_home_saudacao"],
                                 "texto_home_subtitulo":
                                 PADRAO_CONFIG["texto_home_subtitulo"],
                                 "texto_rodape": PADRAO_CONFIG["texto_rodape"],
                                 "titulo_sistema": PADRAO_CONFIG["titulo_sistema"]},
                                "textos",
                                campos=[
                                    (f_titulo, "titulo",
                                     PADRAO_CONFIG["titulo_sistema"]),
                                    (t_login, "texto_login_titulo",
                                     PADRAO_CONFIG["texto_login_titulo"]),
                                    (t_sub, "texto_login_subtitulo",
                                     PADRAO_CONFIG["texto_login_subtitulo"]),
                                    (t_hint, "texto_login_hint",
                                     PADRAO_CONFIG["texto_login_hint"]),
                                    (t_saud, "texto_home_saudacao",
                                     PADRAO_CONFIG["texto_home_saudacao"]),
                                    (t_homesub, "texto_home_subtitulo",
                                     PADRAO_CONFIG["texto_home_subtitulo"]),
                                    (t_rodape, "texto_rodape",
                                     PADRAO_CONFIG["texto_rodape"])])),
                        chave_modulo="skyrover",
                        data_testid="config-aplicar-textos")

                # ---- Configurações gerais (RF-57) ----
                inp_gerais = {}

                def _campo_backup():
                    inp = ui_comum.campo_texto(
                        "Intervalo de backup (horas)",
                        chave="backup_interval_hours",
                        padrao=PADRAO_CONFIG["backup_interval_hours"],
                        ao_mudar=lambda e: estado_campos.update(
                            backup_interval_hours=e.value))
                    inp_gerais["backup"] = inp
                    return inp

                def _campo_sessao():
                    inp = ui_comum.campo_texto(
                        "Retenção de sessão (dias)",
                        chave="sessao_retencao",
                        padrao=PADRAO_CONFIG["sessao_retencao"],
                        ao_mudar=lambda e: estado_campos.update(
                            sessao_retencao=e.value))
                    inp_gerais["sessao"] = inp
                    return inp

                def _campo_aviso():
                    inp = ui_comum.campo_texto(
                        "Tempo de exibição dos avisos (segundos)",
                        chave="notificacao_timeout",
                        padrao=PADRAO_CONFIG["notificacao_timeout"],
                        tooltip="10 a 30 segundos (padrão "
                                f"{PADRAO_CONFIG['notificacao_timeout']}). Vale para os avisos "
                                "(toasts) de todo o sistema, incluindo boas-vindas. "
                                "Abaixo de 10 o aviso some antes de ser lido.",
                        ao_mudar=lambda e: estado_campos.update(
                            aviso_timeout=e.value))
                    inp_gerais["aviso"] = inp
                    return inp

                with ui_comum.card_admin("Configurações gerais do sistema", icone="settings",
                        chave_modulo="skyrover", grade=False, aberto=False):
                    ui.label("Intervalo de backup, retenção de sessão "
                             "e pasta raiz dos arquivos.").classes(
                        "text-caption text-grey-7 max-w-3xl -mt-2")
                    with ui.grid().classes(
                            "w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-3") \
                            .style("gap: 1.25rem"):
                        _campo_backup()
                        _campo_sessao()
                        _campo_aviso()
                        ui_comum.campo_texto(
                            "Pasta raiz dos arquivos (BASE_DIR)",
                            valor=os.path.dirname(os.path.dirname(
                                os.path.abspath(__file__))),
                            props="outlined dense readonly",
                            tooltip="Diretório raiz do sistema (somente leitura)")

                    estado_campos["backup_interval_hours"] = \
                        inp_gerais["backup"].value
                    estado_campos["sessao_retencao"] = \
                        inp_gerais["sessao"].value
                    estado_campos["aviso_timeout"] = inp_gerais["aviso"].value

                    ui_comum.rodape_salvar_restaurar(
                        salvar=lambda: _aplicar_card(
                            "Configurações gerais",
                            "configurações gerais aplicadas", aplicar_gerais),
                        restaurar=lambda: confirmar(
                            "configurações gerais",
                            lambda: restaurar_grupo(
                                  {"backup_interval_hours":
                                       PADRAO_CONFIG["backup_interval_hours"],
                                   "sessao_retencao":
                                       PADRAO_CONFIG["sessao_retencao"],
                                   "notificacao_timeout":
                                       PADRAO_CONFIG["notificacao_timeout"]},
                                  "configurações gerais",
                                  campos=[(inp_gerais["backup"],
                                           "backup_interval_hours",
                                           PADRAO_CONFIG["backup_interval_hours"]),
                                          (inp_gerais["sessao"],
                                           "sessao_retencao",
                                           PADRAO_CONFIG["sessao_retencao"]),
                                          (inp_gerais["aviso"],
                                           "aviso_timeout",
                                           PADRAO_CONFIG["notificacao_timeout"])],
                                pos_acao=lambda: _reagendar_backups(
                                    int(PADRAO_CONFIG["backup_interval_hours"])))),
                        chave_modulo="skyrover",
                        data_testid="config-aplicar-gerais")

                # ---- Ícones: aba do navegador + identidade do sistema ----
                with ui_comum.card_admin("Ícones", icone="image",
                                         chave_modulo="skyrover", grade=False,
                                         aberto=False):
                    ui.label("Ícone da aba do navegador (favicon .ico) e ícone "
                             "Material do sistema.").classes(
                        "text-caption text-grey-7 max-w-3xl -mt-2")
                    import nicegui as _nicegui_pkg
                    fav_path = os.path.join(BASE_DIR_MOD, "assets", "favicon_atual.ico")
                    fav_padrao = os.path.join(os.path.dirname(_nicegui_pkg.__file__),
                                              "static", "favicon.ico")

                    async def receber_ico(e):
                        """Receives the uploaded .ico file, validates it and applies it as the browser tab icon.

                        Callback do `ui.upload` do card "Ícones": valida a extensão
                        `.ico` e o tamanho (vazio ou > 1 MB são recusados), grava o
                        conteúdo em `assets/favicon_atual.ico`, marca `favicon_custom=1`
                        em `tb_config`, registra auditoria `config_alterada` e notifica
                        o usuário (Ctrl+F5 para vencer o cache da aba).
                        """
                        nome = (e.file.name or "").lower()
                        if not nome.endswith(".ico"):
                            notificar("Envie um arquivo .ico", tipo="negative")
                            return
                        conteudo = await e.file.read()
                        if not conteudo or len(conteudo) > 1 * 1024 * 1024:
                            notificar("Arquivo vazio ou maior que 1 MB", tipo="negative")
                            return
                        with open(fav_path, "wb") as fh:
                            fh.write(conteudo)
                        set_config("favicon_custom", "1")
                        audit_log(user_nome, "skyrover", "config_alterada",
                                  f"favicon enviado ({nome}, {len(conteudo)} bytes)")
                        notificar("Favicon aplicado — recarregue a aba com Ctrl+F5",
                                  tipo="positive")

                    def remover_fav():
                        """Restores the default NiceGUI favicon as the browser tab icon.

                        Callback do "Restaurar padrão" do card "Ícones" (via `pos_acao`
                        de `restaurar_grupo`): copia o favicon nativo do NiceGUI para
                        `assets/favicon_atual.ico`, marca `favicon_custom=0` em
                        `tb_config`, registra auditoria `config_restaurada` e notifica
                        o usuário (Ctrl+F5 na aba).
                        """
                        shutil.copy2(fav_padrao, fav_path)
                        set_config("favicon_custom", "0")
                        audit_log(user_nome, "skyrover", "config_restaurada",
                                  "favicon voltou ao padrão NiceGUI")
                        notificar("Ícone padrão restaurado — Ctrl+F5 na aba", tipo="positive")

                    with ui.grid().classes(
                            "w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-3") \
                            .style("gap: 1.25rem"):
                        f_icone = ui_comum.campo_texto(
                            "Ícone do sistema (nome Material)",
                            chave="icone_sistema", padrao="hub",
                            tooltip="ex.: hub, apartment, domain",
                            ao_mudar=lambda e: _mudou("icone", e.value)) \
                            .classes("self-center")
                        ui.upload(on_upload=receber_ico, auto_upload=True) \
                            .props('accept=".ico,image/x-icon" '
                                   'label="Enviar arquivo .ico" '
                                   'flat dense color=primary') \
                            .classes("w-full self-center") \
                            .tooltip("Substitui o ícone da aba do navegador "
                                     "(favicon) — extensão .ico, até 1 MB")

                    # Garante que os valores atuais já entrem no estado sem mexer
                    estado_campos["icone"] = f_icone.value

                    ui_comum.rodape_salvar_restaurar(
                        salvar=lambda: _aplicar_card(
                            "Ícones", "ícones aplicados", aplicar_icones),
                        restaurar=lambda: confirmar(
                            "ícones (sistema + aba do navegador)",
                            lambda: restaurar_grupo(
                                {"icone_sistema": PADRAO_CONFIG["icone_sistema"]},
                                "ícones",
                                campos=[(f_icone, "icone",
                                         PADRAO_CONFIG["icone_sistema"])],
                                pos_acao=remover_fav)),
                        chave_modulo="skyrover",
                        data_testid="config-aplicar-icones")

                # ---- Banco de dados (SQLite / PostgreSQL) ----
                with ui_comum.card_admin("Banco de dados — SQLite ou PostgreSQL",
                                     icone="storage",
                                     chave_modulo="skyrover", grade=False,
                                     aberto=False):
                    ui.label(
                        "SQLite é o padrão (um arquivo por módulo, zero "
                        "dependências extras). PostgreSQL é opcional: suba o "
                        "container em assets/docker/postgres e marque "
                        "'PostgreSQL' abaixo. APÓS REINICIAR o servidor, todos "
                        "os módulos passam a usar o banco `skyrover` do "
                        "PostgreSQL (um schema por módulo), mantendo o mesmo "
                        "esquema e isolamento.").classes(
                        "text-caption text-grey-7 max-w-3xl -mt-2")
                    from mod_skyrover.banco_conexao import config_backend, salvar_backend
                    _backend = config_backend()
                    sel_banco = ui_comum.campo_selecao(
                        "Tipo de banco de dados", valor=_backend["banco_tipo"],
                        opcoes={"sqlite": "SQLite (padrão)",
                                "postgres": "PostgreSQL"},
                        ao_mudar=lambda e: _mudou("banco_tipo", e.value))
                    inp_pg_url = ui_comum.campo_texto(
                        "DSN PostgreSQL (postgresql+psycopg2://usuário:senha@host:5432/skyrover)",
                        valor=_backend["postgres_url"])

                    def aplicar_banco():
                        salvar_backend(sel_banco.value or "sqlite",
                                       inp_pg_url.value or "")

                    def _salvar_banco_sem_reload():
                        aplicar_banco()
                        notificar(
                            "Banco de dados atualizado — REINICIE o servidor "
                            "para aplicar (as conexões ativas seguem no "
                            "backend anterior).", tipo="warning",
                            close_button="Fechar")

                    ui_comum.rodape_salvar_restaurar(
                        salvar=lambda: _aplicar_card_sem_reload(
                            "Banco de dados", "config_banco",
                            aplicar_banco),
                        chave_modulo="skyrover",
                        data_testid="config-aplicar-banco")

            # ============================================================
            # ABA: E-MAIL / SMTP
            # ============================================================
            with ui.tab_panel(tab_email):
                from mod_skyrover import email_util

                with ui_comum.card_admin("E-mail / SMTP (envio de documentos)",
                                     icone="mail",
                                     chave_modulo="skyrover", grade=False,
                                     aberto=False):
                    ui.label("Credenciais do servidor de saída usadas para enviar empenhos "
                             "renomeados por e-mail.").classes(
                        "text-caption text-grey-7 max-w-3xl -mt-2")

                    with ui.grid().classes("w-full grid-cols-1 sm:grid-cols-2").style("gap: 1.25rem"):
                        sm_serv = _campo_empilhado(
                            "Servidor SMTP", get_config("smtp_servidor", "")) \
                            .on_value_change(lambda e: estado_campos.update(
                                smtp_servidor=e.value))
                        sm_port = _campo_empilhado(
                            "Porta", get_config("smtp_porta", "587")) \
                            .on_value_change(lambda e: estado_campos.update(
                                smtp_porta=e.value))
                        sm_user = _campo_empilhado(
                            "Usuário / login", get_config("smtp_usuario", "")) \
                            .on_value_change(lambda e: estado_campos.update(
                                smtp_usuario=e.value))
                        sm_de = _campo_empilhado(
                            "Remetente (De)", get_config("smtp_de", "")) \
                            .on_value_change(lambda e: estado_campos.update(
                                smtp_de=e.value))
                        sm_senha = _campo_empilhado(
                            "Senha", get_config("smtp_senha", ""),
                            tooltip="Senha do servidor SMTP") \
                            .props("password password_toggle_button") \
                            .on_value_change(lambda e: estado_campos.update(
                                smtp_senha=e.value))
                        with ui.column().classes("min-w-0").style("gap: 0.25rem"):
                            ui.label("Criptografia").classes("text-caption text-grey-7")
                            sm_tls = ui.switch(
                                "Usar TLS (STARTTLS)",
                                value=get_config("smtp_tls", "1") == "1") \
                                .props("dense") \
                                .on_value_change(
                                    lambda e: estado_campos.update(smtp_tls=e.value))

                    # Garante que os valores atuais já entrem no estado sem o usuário mexer
                    estado_campos["smtp_servidor"] = sm_serv.value
                    estado_campos["smtp_porta"] = sm_port.value
                    estado_campos["smtp_usuario"] = sm_user.value
                    estado_campos["smtp_senha"] = sm_senha.value
                    estado_campos["smtp_de"] = sm_de.value
                    estado_campos["smtp_tls"] = sm_tls.value

                    async def testar_smtp():
                        from nicegui import run as _run_smtp
                        _smtp_status = ui.row().classes("w-full items-center justify-center") \
                            .style("gap: 0.5rem")
                        with _smtp_status:
                            ui.spinner(size="lg").props("aria-label=Testando SMTP")
                            ui.label("Testando conexão SMTP…").classes("text-caption text-grey-7")
                        try:
                            set_config("smtp_servidor", sm_serv.value or "")
                            set_config("smtp_porta", sm_port.value or "587")
                            set_config("smtp_usuario", sm_user.value or "")
                            set_config("smtp_senha", sm_senha.value or "")
                            set_config("smtp_de", sm_de.value or "")
                            set_config("smtp_tls", "1" if sm_tls.value else "0")
                            ok, msg = await _run_smtp.io_bound(email_util.testar_conexao)
                        finally:
                            try:
                                _smtp_status.clear()
                            except Exception:
                                pass
                        notificar(msg, tipo="positive" if ok else "negative",
                                  multi_line=True, close_button="Fechar")

                    ui_comum.rodape_salvar_restaurar(
                        salvar=lambda: _aplicar_card(
                            "E-mail / SMTP", "SMTP aplicado", aplicar_smtp),
                        restaurar=lambda: confirmar(
                            "e-mail / SMTP",
                            lambda: restaurar_grupo(
                                {"smtp_servidor": "", "smtp_porta": "587",
                                 "smtp_usuario": "", "smtp_senha": "",
                                 "smtp_de": "", "smtp_tls": "1"},
                                "e-mail / SMTP",
                                campos=[(sm_serv, "smtp_servidor", ""),
                                        (sm_port, "smtp_porta", "587"),
                                        (sm_user, "smtp_usuario", ""),
                                        (sm_senha, "smtp_senha", ""),
                                        (sm_de, "smtp_de", "")],
                                pos_acao=lambda: (
                                    sm_tls.set_value(True),
                                    estado_campos.update(smtp_tls=True)))),
                        acoes_extra=[("Testar conexão SMTP", "mail", testar_smtp)],
                        chave_modulo="skyrover",
                        data_testid="config-aplicar-smtp")

            # ============================================================
            # ABA: OBSERVABILIDADE / LOGS
            # ============================================================
            with ui.tab_panel(tab_obs):
                with ui_comum.card_admin("Observabilidade e logs (loguru)",
                                     icone="query_stats",
                                     chave_modulo="skyrover", grade=False,
                                     aberto=False):
                    ui.label("Logs de erro/debug/info em arquivo, com rotação (tempo ou "
                             "tamanho) e retenção configurável. Arquivos rotacionados são "
                             "compactados em .zip e mantidos até o prazo de retenção.").classes(
                        "text-caption text-grey-7 max-w-3xl -mt-2")

                    with ui.grid().classes("w-full grid-cols-1 sm:grid-cols-2").style("gap: 1.25rem"):
                        with ui.column().classes("min-w-0").style("gap: 0.25rem"):
                            ui.label("Ativação").classes("text-caption text-grey-7")
                            sw_ativo = ui.switch(
                                "Logs ativos",
                                value=get_config("log_ativo", "1") == "1") \
                                .props("dense")
                        sel_nivel = ui_comum.campo_selecao(
                            "Nível mínimo",
                            {"DEBUG": "DEBUG", "INFO": "INFO",
                             "WARNING": "WARNING", "ERROR": "ERROR"},
                            chave="log_nivel", padrao="INFO",
                            props="dense outlined",
                            tooltip="DEBUG, INFO, WARNING ou ERROR")
                        inp_rot = _campo_empilhado(
                            "Rotação (tempo ou tamanho)",
                            get_config("log_rotacao", "1 month"),
                            tooltip="Ex.: '1 month' (tempo) ou '50 MB' (tamanho). "
                                    "Padrão '1 month'.")
                        inp_ret = _campo_empilhado(
                            "Retenção dos arquivos compactados (.zip)",
                            get_config("log_retencao", "4 months"),
                            tooltip="Ex.: '4 months' (padrão). Arquivos .zip "
                                    "mantidos até o prazo.")
                        sel_console = ui_comum.campo_selecao(
                            "Destino do console (terminal)",
                            {"auto": "auto (só via python)",
                             "sempre": "sempre (arquivo + terminal)",
                             "nunca": "nunca (só arquivo)"},
                            chave="log_console", padrao="auto",
                            props="dense outlined",
                            tooltip="auto: console só rodando via python; "
                                    "sempre/nunca forçam com/sem terminal")
                        sel_otel_nivel = ui_comum.campo_selecao(
                            "Nível do envio ao Loki (OTel)",
                            {"DEBUG": "DEBUG", "INFO": "INFO",
                             "WARNING": "WARNING", "ERROR": "ERROR"},
                            chave="log_otel_nivel", padrao="DEBUG",
                            props="dense outlined",
                            tooltip="Nível mínimo enviado ao Loki via OTel")

                    with ui.row().classes("w-full items-center").style("gap: 1.25rem"):
                        sw_otel_envio = ui.switch(
                            "Enviar logs ao Loki (OTel)",
                            value=get_config("log_otel_envio", "1") == "1") \
                            .props("dense") \
                            .tooltip("Desligado = log fica só em arquivo/console")

                    # Garante que os valores já entrem no estado mesmo sem o usuário mexer
                    estado_campos["log_ativo"] = sw_ativo.value
                    estado_campos["log_nivel"] = sel_nivel.value
                    estado_campos["log_rotacao"] = inp_rot.value
                    estado_campos["log_retencao"] = inp_ret.value
                    estado_campos["log_console"] = sel_console.value
                    estado_campos["log_otel_envio"] = sw_otel_envio.value
                    estado_campos["log_otel_nivel"] = sel_otel_nivel.value
                    sw_ativo.on_value_change(
                        lambda e: estado_campos.update(log_ativo=e.value))
                    sel_nivel.on_value_change(
                        lambda e: estado_campos.update(log_nivel=e.value))
                    inp_rot.on_value_change(
                        lambda e: estado_campos.update(log_rotacao=e.value))
                    inp_ret.on_value_change(
                        lambda e: estado_campos.update(log_retencao=e.value))
                    sel_console.on_value_change(
                        lambda e: estado_campos.update(log_console=e.value))
                    sw_otel_envio.on_value_change(
                        lambda e: estado_campos.update(log_otel_envio=e.value))
                    sel_otel_nivel.on_value_change(
                        lambda e: estado_campos.update(log_otel_nivel=e.value))

                    def limpar_logs():
                        from mod_skyrover import observabilidade as _obs
                        ok, msg = _obs.limpar_todos()
                        notificar(msg, tipo="positive" if ok else "negative")
                        audit_log(user_nome, "skyrover", "logs_limpos", msg)
                        _obs.get_logger().warning(
                            f"logs limpos manualmente por {user_nome}: {msg}")

                    def _reconfigurar_obs():
                        """Reapplies the observability config after a restore.

                        Reaplica a configuração da observabilidade (ativação,
                        nível, rotação e retenção) após restaurar os padrões."""
                        from mod_skyrover import observabilidade as _obs
                        _obs.configurar()

                    ui_comum.rodape_salvar_restaurar(
                        salvar=lambda: _aplicar_card(
                            "Observabilidade", "observabilidade aplicada",
                            aplicar_obs),
                        restaurar=lambda: confirmar(
                            "observabilidade / logs",
                            lambda: restaurar_grupo(
                                {"log_ativo": "1", "log_nivel": "INFO",
                                 "log_rotacao": "1 month", "log_retencao": "4 months",
                                 "log_console": "auto", "log_otel_envio": "1",
                                 "log_otel_nivel": "DEBUG"},
                                "observabilidade / logs",
                                campos=[(sw_ativo, "log_ativo", True),
                                        (sel_nivel, "log_nivel", "INFO"),
                                        (inp_rot, "log_rotacao", "1 month"),
                                        (inp_ret, "log_retencao", "4 months"),
                                        (sel_console, "log_console", "auto"),
                                        (sw_otel_envio, "log_otel_envio", True),
                                        (sel_otel_nivel, "log_otel_nivel", "DEBUG")],
                                pos_acao=lambda: _reconfigurar_obs())),
                        acoes_extra=[("Limpar TODOS os logs", "delete_forever",
                                      lambda: confirmar(
                                          "LIMPEZA TOTAL dos logs", limpar_logs),
                                      None, "perigo")],
                        chave_modulo="skyrover",
                        data_testid="config-aplicar-obs")

                with ui_comum.card_admin(
                        "Telemetria OTel — stack local ou servidor dedicado",
                        icone="hub", chave_modulo="skyrover", grade=False,
                        aberto=False):
                    ui.label("Aponte o endpoint para um servidor dedicado de "
                             "observabilidade (host:porta OTLP/gRPC) ou use a stack "
                             "local via Docker. Mudanças aqui exigem REINICIAR o "
                             "sistema.").classes(
                        "text-caption text-grey-7 max-w-3xl -mt-2")

                    with ui.grid().classes("w-full grid-cols-1 sm:grid-cols-2").style("gap: 1.25rem"):
                        with ui.column().classes("min-w-0").style("gap: 0.25rem"):
                            ui.label("Telemetria").classes("text-caption text-grey-7")
                            sw_otel_ativo = ui.switch(
                                "Telemetria OTel ativa",
                                value=get_config("otel_ativo", "1") == "1") \
                                .props("dense")
                        with ui.column().classes("min-w-0").style("gap: 0.25rem"):
                            ui.label("Gerência da stack").classes(
                                "text-caption text-grey-7")
                            sw_otel_auto = ui.switch(
                                "Subir stack local (Docker)",
                                value=get_config("otel_auto_start_stack", "1") == "1") \
                                .props("dense") \
                                .tooltip("Ligado = `compose up` local; desligado = "
                                         "usa servidor remoto sem Docker")
                        inp_otel_ep = _campo_empilhado(
                            "Endpoint OTLP (host:porta)",
                            get_config("otel_endpoint", "localhost:4317"),
                            tooltip="Ex.: 'localhost:4317' (local) ou "
                                    "'10.0.0.20:4317' (servidor dedicado). "
                                    "Env OTEL_ENDPOINT tem prioridade.")
                        inp_grafana_url = _campo_empilhado(
                            "URL do Grafana",
                            get_config("grafana_url", "http://localhost:3000"),
                            tooltip="Ex.: 'http://localhost:3000' ou "
                                    "'http://10.0.0.20:3000'. Env GRAFANA_URL "
                                    "tem prioridade.")

                    # Garante que os valores já entrem no estado mesmo sem o usuário mexer
                    estado_campos["otel_ativo"] = sw_otel_ativo.value
                    estado_campos["otel_endpoint"] = inp_otel_ep.value
                    estado_campos["otel_auto_start_stack"] = sw_otel_auto.value
                    estado_campos["grafana_url"] = inp_grafana_url.value
                    sw_otel_ativo.on_value_change(
                        lambda e: estado_campos.update(otel_ativo=e.value))
                    inp_otel_ep.on_value_change(
                        lambda e: estado_campos.update(otel_endpoint=e.value))
                    sw_otel_auto.on_value_change(
                        lambda e: estado_campos.update(otel_auto_start_stack=e.value))
                    inp_grafana_url.on_value_change(
                        lambda e: estado_campos.update(grafana_url=e.value))

                    ui_comum.rodape_salvar_restaurar(
                        salvar=lambda: _aplicar_card(
                            "Telemetria OTel", "telemetria OTel aplicada",
                            aplicar_otel),
                        restaurar=lambda: confirmar(
                            "telemetria OTel",
                            lambda: restaurar_grupo(
                                {"otel_ativo": "1",
                                 "otel_endpoint": "localhost:4317",
                                 "otel_auto_start_stack": "1",
                                 "grafana_url": "http://localhost:3000"},
                                "telemetria OTel",
                                campos=[(sw_otel_ativo, "otel_ativo", True),
                                        (inp_otel_ep, "otel_endpoint",
                                         "localhost:4317"),
                                        (sw_otel_auto, "otel_auto_start_stack", True),
                                        (inp_grafana_url, "grafana_url",
                                         "http://localhost:3000")])),
                        chave_modulo="skyrover",
                        data_testid="config-aplicar-otel")

            # ============================================================
            # ABA: DOCUMENTAÇÃO
            # ============================================================
            with ui.tab_panel(tab_docs):
                with ui_comum.card_admin("Documentação", icone="menu_book",
                                         chave_modulo="skyrover", grade=False,
                                         aberto=False):
                    ui.label("Reconstrói a documentação MkDocs do projeto e a publica em "
                             "/documentacao (mesmo endereço/porta do sistema, nova aba). "
                             "Edições em docs/*.md valem após reconstruir. "
                             "Desde 02/10/2026 a documentação NÃO sobe sozinha no boot: "
                             "para tê-la na porta própria, suba com `--ativ-docs` "
                             "(ou `--porta-docs N --ativ-docs`).") \
                        .classes("text-caption text-grey-7 max-w-3xl -mt-2")

                    async def reconstruir_docs():
                        from nicegui import run as _run_docs
                        if not _pode_escrever():
                            notificar("Sem permissão — só administrador geral aplica.",
                                      tipo="negative")
                            return
                        _docs_status = ui.row().classes("w-full items-center justify-center") \
                            .style("gap: 0.5rem")
                        with _docs_status:
                            ui.spinner(size="lg").props("aria-label=Reconstruindo documentação")
                            ui.label("Reconstruindo documentação… (até 2 min, sem travar a tela)").classes("text-caption text-grey-7")
                        try:
                            ok, msg = await _run_docs.io_bound(documentacao.reconstruir)
                        finally:
                            try:
                                _docs_status.clear()
                            except Exception:
                                pass
                        if ok:
                            try:
                                audit_log(user_nome, "skyrover", "documentacao_reconstruida",
                                          msg[:200])
                            except Exception:
                                pass
                        notificar(msg, tipo="positive" if ok else "negative",
                                  multi_line=True, close_button="Fechar")

                    with ui.row().classes("w-full items-center justify-center flex-wrap") \
                            .style("gap: 0.5rem"):
                        ui_comum.botao("Reconstruir documentação", variante="primario",
                                             icone="menu_book", on_click=reconstruir_docs,
                                             chave_modulo="skyrover") \
                            .props("data-testid=config-reconstruir-docs")
                        ui_comum.botao_icone("open_in_new",
                                             on_click=lambda: ui.navigate.to(
                                                 "/documentacao", new_tab=True),
                                             tooltip="Abrir a documentação em nova aba",
                                             chave_modulo="skyrover")

            # ============================================================
            # ABA: MÓDULO
            # ============================================================
            with ui.tab_panel(tab_mod):
                # ---- Páginas do sistema (nome e ícone) ----
                with ui_comum.card_admin("Páginas do sistema — como aparecem no menu",
                                     icone="extension",
                                     chave_modulo="skyrover", grade=False,
                                     aberto=False):
                    ui.label("Edite o nome exibido (menu lateral e título do cabeçalho), a URL "
                             "da página (slug), o ícone (Material Icons) e a ORDEM de cada "
                             "página usando as setas ↑/↓ (a ordem é salva imediatamente). "
                             "Auditoria e Usuários são INDISPENSÁVEIS ao funcionamento do "
                             "sistema: podem ser reordenados, mas não desativados.").classes(
                        "text-caption text-grey-7 max-w-3xl -mt-2")

                    modulos_ordenados = list(autenticacao.modulos_registrados())
                    campos = {}
                    estado_campos["paginas"] = campos  # lido pelo APLICAR
                    campos_url = {}
                    estado_campos["urls"] = campos_url  # lido pelo APLICAR (URLs)

                    container_modulos = ui.column().classes("w-full")

                    def refresh_modulos():
                        """Rebuilds the ordered module list (after a reorder).

                        Remonta a lista ÚNICA de módulos na ordem vigente de
                        `tb_modulos.ordem`, recriando os campos de edição e os
                        botões ↑/↓. Mantém `estado_campos["paginas"]` e
                        `estado_campos["urls"]` apontando para os mesmos dicts
                        `campos`/`campos_url` (contrato do APLICAR).
                        Em falha, registra loguru e notifica o usuário."""
                        nonlocal modulos_ordenados
                        try:
                            container_modulos.clear()
                            modulos_ordenados = list(autenticacao.modulos_registrados())
                            campos.clear()
                            campos_url.clear()
                            with container_modulos:
                                # Cabeçalho de colunas — oculto em sm/md (cada célula
                                # já tem label via _campo_empilhado)
                                with ui.grid().classes(
                                        COLUNAS_MODULOS + " w-full bg-grey-1 rounded-lg "
                                        "px-3 py-2 text-caption font-bold text-grey-8 "
                                        "items-start hidden lg:grid"
                                ).style("gap: 0.75rem"):
                                    ui.label("#").classes("text-center").tooltip(
                                        "Posição no menu — use ↑/↓ para reordenar")
                                    ui.label("Página (chave)").tooltip(
                                        "Identificador interno do módulo")
                                    ui.label("Nome exibido (menu e título)").tooltip(
                                        "Texto que aparece no menu lateral e no título do cabeçalho")
                                    ui.label("URL da página").tooltip(
                                        "Slug da rota — ex.: /renomear-empenho → /renomeador")
                                    ui.label("Ícone (Material Icons)").tooltip(
                                        "Nome do ícone Material. Digite ou escolha na lista "
                                        "(ex.: people, article, history)")
                                    ui.label("Situação")

                                for idx, (chave, nome, icone, rota, ativo) in enumerate(modulos_ordenados):
                                    is_indisp = chave in MODULOS_INDISPENSAVEIS
                                    with ui.grid().classes(
                                            COLUNAS_MODULOS + " w-full bg-white border "
                                            "border-grey-2 rounded-lg px-3 py-2 items-center "
                                            "hover:shadow-sm"
                                            + (" border-amber-200 bg-amber-50/40"
                                               if is_indisp else "")
                                    ).style("gap: 0.75rem"):
                                        # Coluna de ordem: posição + setas ↑/↓
                                        with ui.column().classes("items-center").style("gap: 0.1rem"):
                                            ui.label(str(idx + 1)).classes(
                                                "text-caption font-bold text-grey-8")
                                            with ui.row().classes("items-center").style("gap: 0.1rem"):
                                                ui_comum.botao_icone("arrow_upward",
                                                                     on_click=lambda _, i=idx: _mover(i, -1),
                                                                     tooltip="Mover para cima",
                                                                     chave_modulo="skyrover")
                                                ui_comum.botao_icone("arrow_downward",
                                                                     on_click=lambda _, i=idx: _mover(i, 1),
                                                                     tooltip="Mover para baixo",
                                                                     chave_modulo="skyrover")
                                        _campo_empilhado("Página (chave)", chave, readonly=True)
                                        inp_n = _campo_empilhado(
                                            "Nome exibido", nome,
                                            tooltip="Usado no menu lateral e no cabeçalho ao entrar na página")
                                        inp_url = _campo_empilhado(
                                            "URL da página", rota,
                                            tooltip="Slug da rota — ex.: /renomear-empenho → /renomeador")
                                        inp_i = _campo_icone(icone)
                                        if is_indisp:
                                            with ui.row().classes("items-center").style("gap: 0.25rem"):
                                                ui.icon("lock", size="sm").classes("text-amber-7").tooltip(
                                                    "Sempre ativo — não pode ser desativado")
                                            sw = ui.switch(value=True).props("dense disabled").classes("hidden")
                                        else:
                                            with ui.column().classes("items-start").style("gap: 0.25rem"):
                                                ui.label("Ativo").classes("text-caption text-grey-7")
                                                sw = ui.switch(value=bool(ativo)).props("dense color=primary")
                                        campos[chave] = (inp_n, inp_i, sw)
                                        campos_url[chave] = inp_url
                        except Exception:
                            from mod_skyrover import observabilidade
                            observabilidade.get_logger("skyrover").exception(
                                "falha ao remontar a lista de módulos")
                            notificar("Erro ao recarregar a lista de módulos.",
                                      tipo="negative")

                    def _mover(idx, direcao):
                        """Moves a module up/down in the display order and persists.

                        Troca o módulo da posição `idx` com o vizinho na direção
                        `direcao` (-1 sobe, +1 desce), grava a nova ordem via
                        `autenticacao.reordenar_modulos` e remonta a lista.
                        Edições ainda não salvas (nome/ícone/ativo/url) são
                        preservadas entre a remontagem. Em falha, registra
                        loguru e notifica o usuário."""
                        try:
                            novo_idx = idx + direcao
                            if novo_idx < 0 or novo_idx >= len(modulos_ordenados):
                                return
                            # Preserva edições pendentes antes de remontar a lista
                            pendentes = {chave: (inp_n.value, inp_i.value, sw.value)
                                         for chave, (inp_n, inp_i, sw) in campos.items()}
                            pendentes_url = {chave: inp_u.value
                                             for chave, inp_u in campos_url.items()}
                            modulos_ordenados[idx], modulos_ordenados[novo_idx] = \
                                modulos_ordenados[novo_idx], modulos_ordenados[idx]
                            chaves = [m[0] for m in modulos_ordenados]
                            ok, msg = autenticacao.reordenar_modulos(user_nome, chaves)
                            notificar(msg, tipo="positive" if ok else "negative")
                            refresh_modulos()
                            for chave, (nome_val, icone_val, ativo_val) in pendentes.items():
                                if chave in campos:
                                    campos[chave][0].value = nome_val
                                    campos[chave][1].value = icone_val
                                    campos[chave][2].value = ativo_val
                            for chave, url_val in pendentes_url.items():
                                if chave in campos_url:
                                    campos_url[chave].value = url_val
                        except Exception:
                            from mod_skyrover import observabilidade
                            observabilidade.get_logger("skyrover").exception(
                                "falha ao mover módulo na lista de páginas")
                            notificar("Erro ao reordenar módulos.", tipo="negative")

                    refresh_modulos()

                    def restaurar_paginas_padrao():
                        """Native pages return to coded name/icon/route, are
                        reset to the SHIPPED on/off state and reordered to the
                        MODULOS_SISTEMA sequence.

                        Páginas NATIVAS voltam ao nome/ícone/rota codificados e
                        ao estado de LIGADO/DESLIGADO com que o sistema é
                        entregue — a saber, ligadas só as indispensáveis
                        (`NATIVOS_NASCEM_LIGADOS`), desligadas as demais
                        (02/10/2026) —, na ordem original de `MODULOS_SISTEMA`;
                        módulos criados pelo administrador permanecem intocados
                        (renumerados após os nativos, em ordem alfabética).

                        Restaurar NÃO religa tudo de uma vez, e essa é a diferença
                        que importa: o botão se chama restaurar, não "ativar
                        todos". Quem restaura está devolvendo a tela ao padrão, e
                        o
                        padrão passou a ser desligado; se ele quer o município inteiro ligado,
                        liga módulo a módulo, que é a decisão que o botão serve
                        para permitir.
                        Em falha, registra loguru e notifica o usuário."""
                        try:
                            from mod_skyrover import rotas_modulos
                            for chave, nome, icone, rota in autenticacao.MODULOS_SISTEMA:
                                _ativo = 1 if chave in NATIVOS_NASCEM_LIGADOS else 0
                                conn = autenticacao.get_connection()
                                try:
                                    conn.execute(
                                        "UPDATE tb_modulos SET nome=?, icone=?, rota=?, ativo=? "
                                        "WHERE chave=? AND nativo=1",
                                        (nome, icone, rota, _ativo, chave))
                                    conn.commit()
                                finally:
                                    conn.close()
                                # Re-registra a rota nativa ao vivo (idempotente)
                                rotas_modulos.registrar_modulo(chave, rota)
                            # Restaura a ordem nativa e renumera os não-nativos depois
                            conn = autenticacao.get_connection()
                            try:
                                for idx, (chave, _, _, _) in enumerate(
                                        autenticacao.MODULOS_SISTEMA, start=1):
                                    conn.execute(
                                        "UPDATE tb_modulos SET ordem=? WHERE chave=? AND nativo=1",
                                        (idx, chave))
                                _cur_max = conn.execute(
                                    "SELECT COALESCE(MAX(ordem), 0) FROM tb_modulos WHERE nativo=1")
                                max_nativo = _cur_max.fetchone()[0]
                                _cur_nativos = conn.execute(
                                    "SELECT chave FROM tb_modulos WHERE nativo=0 ORDER BY nome")
                                for i, (chave,) in enumerate(_cur_nativos.fetchall()):
                                    conn.execute(
                                        "UPDATE tb_modulos SET ordem=? WHERE chave=?",
                                        (max_nativo + i + 1, chave))
                                conn.commit()
                            finally:
                                conn.close()
                            audit_log(user_nome, "skyrover", "config_restaurada",
                                      "páginas nativas restauradas")
                            notificar("Páginas nativas restauradas ao padrão — recarregue com F5",
                                      tipo="positive")
                        except Exception:
                            from mod_skyrover import observabilidade
                            observabilidade.get_logger("skyrover").exception(
                                "falha ao restaurar páginas nativas ao padrão")
                            notificar("Erro ao restaurar páginas nativas.", tipo="negative")

                    ui_comum.rodape_salvar_restaurar(
                        salvar=_aplicar_paginas,
                        restaurar=lambda: confirmar(
                            "nomes, URLs, ícones e ordem das páginas",
                            restaurar_paginas_padrao),
                        chave_modulo="skyrover",
                        data_testid="config-aplicar-paginas")

                # ---- Registro de módulos e vínculos órfãos ----
                from mod_gest_cad_usuario import bd_manipulador as gest_usuarios

                with ui_comum.card_admin("Registro de módulos e vínculos órfãos",
                                         icone="hub",
                                         chave_modulo="skyrover", grade=False,
                                         aberto=False):
                    ui.label("Todo módulo registrado aqui passa a aparecer automaticamente nas telas "
                             "de criação/edição de usuários e nos menus — inclusive módulos futuros. "
                             "Vínculos apontando para módulos inexistentes ficam destacados abaixo "
                             "para manutenção ou exclusão.").classes(
                        "text-caption text-grey-7 max-w-3xl -mt-2")

                    box_orfaos = ui.column().classes("w-full -mt-2").style("gap: 1rem")

                    def refresh_orfaos():
                        """Rebuilds the orphan-links panel (register new module + orphans).

                        Recarrega o painel de vínculos órfãos: re-lista os órfãos e
                        remonta a expansão "Registrar novo módulo (futuro)" e a lista
                        de vínculos sem módulo correspondente."""
                        box_orfaos.clear()
                        # `chaves_registradas` e `chaves_ativas` são coisas
                        # diferentes: a primeira é a lista do que EXISTE no
                        # registro, a segunda é o que está LIGADO. Confundir as
                        # duas é o que classificava vínculo de módulo desligado
                        # como órfão — na entrega (11 dos 13 módulos desligados)
                        # foram ~9.400 linhas, e a tela materializava ~27 mil
                        # componentes, derrubando o WebSocket ("sistema
                        # desconectado") a cada abertura de /configuracoes.
                        _registradas = [c for c, _n, _i, _r, _a in
                                        autenticacao.modulos_registrados()]
                        _class = gest_usuarios.classificar_vinculos(
                            autenticacao.chaves_ativas(), _registradas)
                        inativos = _class["inativos"]
                        orfaos = _class["orfaos"]
                        # O detalhamento por módulo sai das listas JÁ
                        # materializadas, e não de `contagem_por_modulo`: aquele
                        # contador soma inativos E órfãos, então listá-lo no texto
                        # dos desligados colocaria um módulo inexistente na linha
                        # "DESLIGADO" — e o número mostrado não fecharia com o
                        # total.
                        _detalhe_inativos = Counter(m for _u, m, _p in inativos)
                        _detalhe_orfaos = Counter(m for _u, m, _p in orfaos)
                        with box_orfaos:
                            # --- registrar novo módulo ---
                            with ui.expansion("Registrar novo módulo (futuro)",
                                              icon="add_circle_outline").classes("w-full"):
                                n_ativo = {"valor": False}
                                with ui.row().classes("w-full flex-wrap items-end").style("gap: 0.5rem"):
                                    n_chave = ui_comum.campo_texto(
                                        "Chave única *",
                                        placeholder="ex.: folha_ponto",
                                        props="outlined dense", largura="")
                                    n_nome = ui_comum.campo_texto(
                                        "Nome exibido *",
                                        placeholder="ex.: Folha de Ponto",
                                        props="outlined dense", largura="")
                                    n_icone = _campo_icone("extension")
                                    n_rota = ui_comum.campo_texto(
                                        "Rota", placeholder="# ou /rota-futura",
                                        props="outlined dense",
                                        largura="max-w-[180px]")
                                    ui.switch("Já em funcionamento",
                                              on_change=lambda e: n_ativo.update(valor=bool(e.value))) \
                                        .tooltip("Marque só se a rota/página já existe no main.py")

                                    def registrar():
                                        """Registers a new (future) module via autenticacao.registrar_modulo.

                                        Cadastra um módulo novo com chave/nome/ícone/rota e notifica o
                                        resultado; em sucesso limpa os campos do formulário."""
                                        ok, msg = autenticacao.registrar_modulo(
                                            user_nome, n_chave.value, n_nome.value,
                                            n_icone.value or "extension", n_rota.value or "#",
                                            ativo=n_ativo["valor"])
                                        notificar(msg, tipo="positive" if ok else "negative")
                                        if ok:
                                            n_chave.value = n_nome.value = ""
                                            n_rota.value = "#"

                                    ui_comum.botao("Registrar", variante="primario",
                                                     icone="add_circle",
                                                     on_click=registrar,
                                                     chave_modulo="skyrover")

                            ui.separator()
                            # --- vínculos por módulo ---
                            # 03/10/2026: a lista deixou de ser "tudo que não está
                            # ATIVO". Módulo DESLIGADO não é órfão — é o estado
                            # esperado, e o vínculo reaparece sozinho quando o módulo
                            # é ligado. Só o que não está REGISTRADO é órfão de
                            # verdade, e só esse admite exclusão.
                            _titulo_cartao("Vínculos por módulo")
                            if not orfaos and not inativos:
                                ui.label("Nenhum vínculo sem módulo correspondente — "
                                         "base consistente.").props(
                                    "data-testid=config-orfaos-vazio")

                            if inativos:
                                # A contagem vem do banco: o número real sem
                                # materializar as linhas na tela.
                                _por_mod = ", ".join(
                                    f"{m} ({n})" for m, n in sorted(
                                        _detalhe_inativos.items(),
                                        key=lambda kv: (-kv[1], kv[0])))
                                ui.label(
                                    f"{len(inativos)} vínculo(s) apontam para módulo "
                                    f"DESLIGADO — estado esperado, não defeito: o vínculo "
                                    f"volta sozinho quando o módulo for ligado. "
                                    f"Por módulo: {_por_mod}."
                                ).classes("text-caption text-grey-7").props(
                                    "data-testid=config-orfaos-inativos")

                            if orfaos:
                                _mods_orfaos = ", ".join(
                                    f"{m} ({n})" for m, n in sorted(
                                        _detalhe_orfaos.items(),
                                        key=lambda kv: (-kv[1], kv[0])))
                                ui.label(
                                    f"{len(orfaos)} vínculo(s) apontam para módulo que NÃO "
                                    f"EXISTE no registro — órfãos de verdade, e estes "
                                    f"podem ser excluídos. Chaves: {_mods_orfaos}."
                                ).classes("text-caption text-orange-8").props(
                                    "data-testid=config-orfaos-orfaos")
                                with ui.grid(columns="1fr 1fr 0.8fr auto").classes(
                                        "w-full bg-orange-1 rounded-lg px-3 py-2 text-caption "
                                        "font-bold text-orange-10 border border-orange-6"):
                                    for c in ("Usuário", "Módulo inexistente", "Papel", ""):
                                        ui.label(c)
                                # Teto de renderização: a contagem é o dado; a lista é
                                # só para inspecionar os primeiros.
                                _limite_orfaos = LIMITE_ORFAOS_RENDER
                                _visiveis = orfaos[:_limite_orfaos]
                                for u, m, p in _visiveis:
                                    with ui.grid(columns="1fr 1fr 0.8fr auto").classes(
                                            "w-full border-b border-orange-3 bg-orange-1/60 px-3 py-1.5 items-center").props(
                                            "data-testid=config-orfaos-linha"):
                                        ui.label(u)
                                        ui.badge(m, color="orange-2").props("text-color=orange-10 outline dense")
                                        ui.label(p).classes("text-caption")
                                        _btn = ui_comum.botao_icone("link_off",
                                                              on_click=lambda _, uu=u, mm=m: (
                                                                  gest_usuarios.remover_acesso(user_nome, uu, mm),
                                                                  refresh_orfaos()),
                                                              tooltip="Excluir permissão órfã",
                                                              cor="red-8",
                                                              chave_modulo="skyrover")
                                        if _btn is not None:
                                            _btn.props("data-testid=config-orfaos-excluir")
                                if len(orfaos) > _limite_orfaos:
                                    ui.label(
                                        f"Mostrando {len(_visiveis)} de {len(orfaos)} — "
                                        f"a contagem acima é o total real."
                                    ).classes("text-caption text-grey-7").props(
                                        "data-testid=config-orfaos-limite")

                    refresh_orfaos()
