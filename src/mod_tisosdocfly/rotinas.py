"""Automatic system routines: database backups and editorPDF cleanup.

Rotinas automáticas do sistema: backup de bancos e limpeza do editorPDF."""
import os
import shutil
import sqlite3
import time
from datetime import datetime

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # src/ — código e assets
DIR_PROJETO = os.path.dirname(BASE_DIR)                                  # raiz — backup/, logs/, bancos
PASTA_BACKUP = os.path.join(DIR_PROJETO, "backup")
PASTA_EDITOR_PDF = os.path.join(BASE_DIR, "mod_edit_pdf", "editorPDF")

# Mapeamento chave do módulo -> arquivo de banco gerenciado por ele
# Agregador de Notícias NÃO possui backup (banco reciclado diariamente)
MAPA_BACKUPS = {
    "tisosdocfly": ("db_mod_tisosdocfly.db", "T! SOS DocFly (central)"),
    "usuarios": ("db_mod_gest_cad_usuario.db", "Usuários"),
    "blog": ("db_mod_blog.db", "Blog"),
    "auditoria": ("db_mod_auditoria.db", "Auditoria"),
    "editar_pdf": ("db_mod_edit_pdf.db", "Editor PDF"),
    "empenhos": ("db_mod_renomear_empenho.db", "Empenhos"),
    "solicita_impressao": ("db_mod_solicita_impressao.db", "Solicitacao de Impressao"),
    "tecnico": ("db_mod_tecnico.db", "Técnico"),
    "filas": ("db_mod_filas.db", "Filas"),
    "lista_telefonica": ("db_mod_lista_telefonica.db", "Lista Telefônica"),
    "os": ("db_mod_os.db", "Ordens de Serviço"),
    "estoque": ("db_mod_estoque.db", "Estoque"),
    "hora_certa": ("db_mod_hora_certa.db", "Hora Certa"),
    "dados_abertos": ("db_mod_dados_abertos.db", "Dados Abertos"),
    "agregador_noticias": ("db_mod_agregador_noticias.db", "Agregador de Noticias"),
    "zap": ("db_mod_zap.db", "WhatsApp (Zap)"),
    "video": ("db_mod_video.db", "Videos"),
}

_agendador = None  # referência global para reagendamento em tempo de execução


def painel_backup(usuario: str, chave_modulo: str):
    """Renders the backup management panel for a module inside its administration page.

    Shows: current interval, last backup time, save interval button, run backup now
    button, and the list of retained backups. Used by all module telas_administracao.py
    files to expose backup configuration to the module admin.

    Args:
        usuario: Nome do usuário que está gerenciando (para auditoria).
        chave_modulo: Chave do módulo (ex: "blog", "auditoria", "editar_pdf").
    """
    from nicegui import ui
    from mod_tisosdocfly.bd_conexao import set_config
    from mod_tisosdocfly.tema_modulo import botao as _botao_tema, ler_tema as _ler_tema
    from mod_tisosdocfly.bd_manipulador import audit_log

    if chave_modulo not in MAPA_BACKUPS:
        return
    _arquivo, nome_amigavel = MAPA_BACKUPS[chave_modulo]

    # O "detalhe de cor" (borda lateral esquerda) acompanha a cor geral do
    # módulo (<prefixo>_cor_botao); sem tema lido, cai no cinza padrão.
    try:
        cor_borda = _ler_tema(chave_modulo).get("cor_botao", "") or ""
    except Exception:
        cor_borda = ""
    cor_borda = cor_borda or "#607D8B"

    with ui.card().classes("w-full border-l-4").style(
            f"border-left-color:{cor_borda}"):
        with ui.card_section().classes("gap-3 w-full"):
            ui.label("Backup do banco de dados").classes("text-h6 font-bold")
            with ui.row().classes("w-full items-center flex-wrap").style(
                    "gap: 0.5rem"):
                ui.label(f"Banco: {_arquivo}").classes("text-caption text-grey-7")
                ultima = listar_backups(chave_modulo)[:1]
                if ultima:
                    quando = ultima[0][2]
                    ui.badge(f"Última cópia: {quando}",
                             color="blue-2").props("outline dense text-color=blue-9")

            with ui.row().classes("w-full items-end flex-wrap").style("gap: 0.5rem"):
                inp_horas = ui.number(
                    "Intervalo automático (horas)",
                    value=intervalo_backup(chave_modulo), min=1, max=720,
                    precision=0,
                ).props("outlined dense").classes("w-40")

                async def salvar_intervalo():
                    from nicegui import run as _run_rot
                    from mod_tisosdocfly.tema_modulo import notificar as _notificar
                    def _gravar():
                        h = max(1, int(inp_horas.value or 12))
                        set_config(f"backup_horas:{chave_modulo}", h)
                        reagendar_backup(chave_modulo, h)
                        return h
                    try:
                        h = await _run_rot.io_bound(_gravar)
                    except Exception:
                        _notificar("Erro ao salvar intervalo", tipo="negative")
                        return
                    try:
                        audit_log(usuario, "tisosdocfly", "config_alterada",
                                  f"backup_horas:{chave_modulo}={h}h")
                    except Exception:
                        pass
                    _notificar(f"Intervalo salvo: {h}h (aplicado sem reiniciar)",
                               tipo="positive")

                _botao_tema("Salvar intervalo", on_click=salvar_intervalo)

                async def rodar_agora():
                    from nicegui import run as _run_rot2
                    from mod_tisosdocfly.tema_modulo import notificar as _notificar2
                    _bk_status = ui.row().classes("w-full items-center justify-center") \
                        .style("gap: 0.5rem")
                    with _bk_status:
                        ui.spinner(size="lg").props("aria-label=Gerando backup")
                        ui.label("Gerando cópia…").classes("text-caption text-grey-7")
                    try:
                        gerado = await _run_rot2.io_bound(lambda: backup_modulo(chave_modulo))
                    finally:
                        try:
                            _bk_status.clear()
                        except Exception:
                            pass
                    if gerado:
                        try:
                            audit_log(usuario, "tisosdocfly", "backup_manual",
                                      f"módulo={chave_modulo} arquivo={gerado}")
                        except Exception:
                            pass
                        _notificar2(f"Cópia gerada: {gerado}", type="positive")
                        try:
                            grade.refresh()
                        except Exception:
                            pass
                    else:
                        _notificar2("Falha ao gerar a cópia", type="negative")

                _botao_tema("Fazer backup agora", icone="backup",
                           on_click=rodar_agora)

            ui.separator()
            ui.label("Cópias retidas (máximo 10)").classes(
                "text-subtitle2 font-bold text-grey-8")

            @ui.refreshable
            def grade():
                linhas = listar_backups(chave_modulo)
                if not linhas:
                    ui.label("Nenhuma cópia retida até o momento.") \
                        .classes("text-caption text-grey-6")
                    return
                with ui.grid(columns="1fr auto auto").classes(
                        "w-full bg-grey-1 rounded px-3 py-1.5 "
                        "text-caption font-bold text-grey-8"):
                    for c in ("Arquivo", "Tamanho", "Data/hora"):
                        ui.label(c)
                for arq, kb, quando in linhas:
                    with ui.grid(columns="1fr auto auto") \
                            .classes("w-full text-caption"):
                        ui.label(arq)
                        ui.label(f"{kb} KB")
                        ui.label(quando)

            grade()


def intervalo_backup(chave, default="12"):
    """Intervalo em horas configurado para o módulo (tb_config)."""
    from mod_tisosdocfly.bd_conexao import get_config
    try:
        return max(1, int(get_config(f"backup_horas:{chave}", default)))
    except (TypeError, ValueError):
        return int(default)


def intervalo_monitor_empenho(default=600):
    """Intervalo (segundos) do monitor automático de empenhos (RF-40).

    Padrão 600 s (10 min) na fase de desenvolvimento; o usuário ajusta na
    tela do módulo. Configurável via tb_config
    'empenhos_monitor_intervalo_seg' sem restart.
    """
    from mod_tisosdocfly.bd_conexao import get_config
    try:
        return max(1, int(get_config("empenhos_monitor_intervalo_seg", default)))
    except (TypeError, ValueError):
        return int(default)


def reagendar_monitor_empenho(segundos):
    """Aplica novo intervalo ao job de monitor de empenhos (sem restart)."""
    segundos = max(1, int(segundos))
    if _agendador is None:
        return False
    try:
        _agendador.reschedule_job("monitor_empenho", trigger="interval", seconds=segundos)
        return True
    except Exception:
        return False


def renomeacao_automatica_empenho_ativa(default="1"):
    """Indica se o monitor automático pode renomear empenhos.

    Chave tb_config 'empenhos_renomeacao_automatica' ("1"/"0", padrão "1").
    Com "0", o job automático pula a varredura — a renomeação manual
    (botão "Processar pasta agora", fila, revisão) continua funcionando.
    """
    from mod_tisosdocfly.bd_conexao import get_config
    try:
        return str(get_config("empenhos_renomeacao_automatica", default)).strip() != "0"
    except Exception:
        return True


def _job_monitor_empenho():
    """Varredura automática da pasta monitorada de empenhos (RF-40)."""
    try:
        if not renomeacao_automatica_empenho_ativa():
            return
        from mod_renomear_empenho.bd_manipulador import rodar_monitor
        rodar_monitor("sistema")
    except Exception as ex:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger("renomear_empenho").error(f"monitor_empenho falhou: {ex}")
        except Exception:
            pass


def _job_agregador_coleta():
    """Coleta do Agregador de Notícias (scrapy-like) — intervalo 1h–6,5 dias."""
    try:
        from mod_agregador_noticias.bd_manipulador import coletar_todas, habilitado
        if not habilitado():
            return
        coletar_todas(ator="sistema")
    except Exception as ex:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger("agregador_noticias").warning(f"coleta agregador falhou: {ex}")
        except Exception:
            pass


def _job_agregador_reinicio():
    """Reinício diário do Agregador — zera todas as notícias às horas da manhã."""
    try:
        from mod_agregador_noticias.bd_manipulador import reiniciar_banco
        reiniciar_banco(ator="sistema")
    except Exception as ex:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger("agregador_noticias").warning(f"reinício agregador falhou: {ex}")
        except Exception:
            pass


def reconfigurar_agregador_noticias():
    """Reaplica intervalo e hora do agregador sem restart."""
    if _agendador is None:
        return False
    try:
        from mod_agregador_noticias.bd_manipulador import intervalo_min, habilitado, obter_hora_reinicio
        # coleta
        if not habilitado():
            try:
                _agendador.pause_job("agregador_coleta")
            except Exception:
                pass
        else:
            try:
                _agendador.resume_job("agregador_coleta")
            except Exception:
                pass
            mins = intervalo_min()
            _agendador.reschedule_job("agregador_coleta", trigger="interval", minutes=mins)
        # reinício diário
        try:
            hora_str = obter_hora_reinicio()
            h, m = map(int, hora_str.split(":"))
            from apscheduler.triggers.cron import CronTrigger
            _agendador.reschedule_job("agregador_reinicio", trigger=CronTrigger(hour=h, minute=m))
        except Exception:
            pass
        return True
    except Exception:
        return False


REPETICOES_AGENDA = ("horaria", "diaria", "semanal", "mensal",
                     "2dias", "2semanas", "2meses",
                     "3dias", "3semanas", "3meses",
                     "4dias", "4semanas", "4meses", "anual")
# Espelho de `mod_hora_certa.bd_manipulador.REPETICOES_AGENDA` (a fonte
# canônica da validação; aqui só o motor precisa conhecer os nomes).
# Novas chaves exigem ramo novo em `construir_trigger_agenda` abaixo.


def _job_verificar_hora():
    """Verificação NTP agendada do Hora Certa (mesma do botão Sincronizar)."""
    try:
        from mod_hora_certa import bd_manipulador as _hc
        _hc.verificar_sincronizacao(ator="sistema")
    except Exception as ex:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger("hora_certa").warning(
                f"verificação NTP agendada falhou: {ex}")
        except Exception:
            pass


def _job_limpeza_solicita_agenda():
    """Limpeza agendada da Solicitação de Impressão (mesma do job de 1 min)."""
    try:
        from mod_solicita_impressao.bd_manipulador import \
            expirar_rascunhos_e_impressos
        expirar_rascunhos_e_impressos()
    except Exception as ex:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger("solicita_impressao").warning(
                f"limpeza agendada falhou: {ex}")
        except Exception:
            pass


def _job_limpeza_pdf_agenda():
    """Limpeza agendada do Editor de PDF (mesma do job de 1 min)."""
    try:
        from mod_edit_pdf.bd_manipulador import expirar_antigos, cfg_expiracao_min
        expirar_antigos(minutos=cfg_expiracao_min())
    except Exception as ex:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger("editar_pdf").warning(
                f"limpeza agendada falhou: {ex}")
        except Exception:
            pass


def _job_limpeza_video_agenda():
    """Limpeza agendada da Biblioteca de Vídeos (mesma do job de 1 min)."""
    try:
        from mod_video.bd_manipulador import expirar_antigos, cfg_expiracao_min
        expirar_antigos(minutos=cfg_expiracao_min())
    except Exception as ex:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger("video").warning(
                f"limpeza agendada falhou: {ex}")
        except Exception:
            pass


def _job_blog_manutencao_agenda():
    """Manutenção agendada do Blog: expira imagens órfãs (tempo do card)."""
    try:
        from mod_blog.bd_manipulador import expirar_imagens_orfas
        expirar_imagens_orfas()
    except Exception as ex:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger("blog").warning(
                f"manutenção agendada falhou: {ex}")
        except Exception:
            pass


def _job_backup_modulo_agenda(modulo):
    """Backup agendado de UM módulo (mesmo do job por intervalo)."""
    try:
        backup_modulo(modulo)
    except Exception as ex:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger("tisosdocfly").warning(
                f"backup agendado [{modulo}] falhou: {ex}")
        except Exception:
            pass


def _acao_agenda(chave):
    """Ação principal do card para o agendamento por data (ou None)."""
    try:
        acoes = {"hora": _job_verificar_hora,
                 "agregador_noticias": _job_agregador_coleta,
                 "empenhos": _job_monitor_empenho,
                 "folha": _job_carga_folha,
                 "auditoria": _job_poda_auditoria,
                 "backup": backup_bancos,
                 "solicita_impressao": _job_limpeza_solicita_agenda,
                 "editar_pdf": _job_limpeza_pdf_agenda,
                 "video": _job_limpeza_video_agenda,
                 "dados_abertos": _job_coleta_dados_abertos,
                 "blog": _job_blog_manutencao_agenda}
        if (chave or "") in acoes:
            return acoes[chave]
        if str(chave or "").startswith("backup_"):
            _mod = str(chave)[len("backup_"):]
            if _mod in MAPA_BACKUPS:
                return lambda _m=_mod: _job_backup_modulo_agenda(_m)
        return None
    except Exception:
        return None


def construir_trigger_agenda(data_str, hora_str, repeticao):
    """Monta (trigger, início) da agenda — âncora na data inicial.

    EN: Builds the (trigger, start) pair — anchored on the start date.
    Semanal repete no mesmo dia da semana da data, mensal no mesmo dia,
    anual no mesmo dia e mês. `horaria` dispara todo os dias a cada hora
    no minuto escolhido; `Ndias`/`Nsemanas` usam intervalo a partir do
    início; `Nmeses` usa `month='*/N'` (mesmo dia). Dia 29–31 no
    mensal/anual pula o mês curto (é o APScheduler, não decisão nossa).
    Devolve (None, None) se inválido.
    """
    try:
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
        rep = (repeticao or "diaria").strip().lower()
        if rep not in REPETICOES_AGENDA:
            rep = "diaria"
        ancora = datetime.strptime(
            (data_str or "").strip(), "%Y-%m-%d")
        try:
            h, m = map(int, (hora_str or "08:00").strip().split(":"))
        except (TypeError, ValueError):
            h, m = 8, 0
        if not (0 <= h <= 23 and 0 <= m <= 59):
            h, m = 8, 0
        inicio = ancora.replace(hour=h, minute=m, second=0, microsecond=0)
        if rep == "horaria":
            trig = CronTrigger(minute=m)
        elif rep == "diaria":
            trig = CronTrigger(hour=h, minute=m)
        elif rep == "semanal":
            trig = CronTrigger(day_of_week=ancora.weekday(),
                               hour=h, minute=m)
        elif rep == "mensal":
            trig = CronTrigger(day=ancora.day, hour=h, minute=m)
        elif rep in ("2dias", "3dias", "4dias"):
            trig = IntervalTrigger(days=int(rep[0]))
        elif rep in ("2semanas", "3semanas", "4semanas"):
            trig = IntervalTrigger(weeks=int(rep[0]))
        elif rep in ("2meses", "3meses", "4meses"):
            trig = CronTrigger(month=f"*/{rep[0]}", day=ancora.day,
                               hour=h, minute=m)
        else:
            trig = CronTrigger(month=ancora.month, day=ancora.day,
                               hour=h, minute=m)
        return trig, inicio
    except Exception:
        return None, None


def reconfigurar_agenda(chave):
    """(Re)aplica o agendamento por data do card. Data vazia = job removido."""
    try:
        from mod_tisosdocfly.bd_conexao import get_config
        data = (get_config(f"agenda_data:{chave}", "") or "").strip()
        _id = f"agenda:{chave}"
        if _agendador is not None:
            try:
                _agendador.remove_job(_id)
            except Exception:
                pass
        else:
            return False
        if not data:
            return True
        hora = (get_config(f"agenda_hora:{chave}", "08:00") or "08:00")
        rep = (get_config(f"agenda_repeticao:{chave}", "diaria")
               or "diaria")
        trig, inicio = construir_trigger_agenda(data, hora, rep)
        acao = _acao_agenda(chave)
        if trig is None or acao is None:
            return False
        try:
            _agendador.add_job(acao, trig, id=_id, start_date=inicio,
                               replace_existing=True)
        except Exception:
            return False
        return True
    except Exception:
        return False


def _cfg_int(chave, padrao, minimo=None, maximo=None):
    """Inteiro de `tb_config`, com limites. Cai no padrão se não der.

    O piso e o teto não são vaidade: um `carga_folha_hora` digitado como `99`
    faria o `CronTrigger` receber uma hora impossível e o APScheduler recusar o
    job no boot — derrubando os outros jobs do agendador junto, porque a falha
    acontece na hora de registrar, não na de executar.
    """
    try:
        from mod_tisosdocfly.bd_conexao import get_config
        valor = int(get_config(chave, str(padrao)))
    except Exception:
        valor = padrao
    if minimo is not None:
        valor = max(minimo, valor)
    if maximo is not None:
        valor = min(maximo, valor)
    return valor


def reagendar_carga_folha(hora, minuto=0):
    """Aplica novo horário à carga da folha (sem restart).

    EN: Reschedules the payroll load job. PT-BR: Reagenda a carga da folha.
    Segue o padrão de `reagendar_monitor_empenho`: `reschedule_job` com
    `CronTrigger` novo. O Hora Certa chama depois de gravar `carga_folha_hora`
    e `carga_folha_minuto` — sem isto, mudar o horário no card só valeria no
    próximo restart.
    """
    try:
        hora = max(0, min(23, int(hora)))
        minuto = max(0, min(59, int(minuto)))
    except (TypeError, ValueError):
        return False
    if _agendador is None:
        return False
    try:
        from apscheduler.triggers.cron import CronTrigger
        _agendador.reschedule_job("carga_folha",
                                  trigger=CronTrigger(hour=hora, minute=minuto))
        return True
    except Exception:
        return False


def reagendar_coleta_dados_abertos():
    """Reaplica dia/hora da coleta PortalFácil sem restart.

    Lê `coleta_api_dia` (1–28), `coleta_api_hora` (0–23) e
    `coleta_api_minuto` (0–59) do `tb_config` central. O admin chama depois
    de gravar — sem isto, mudar a agenda no card só valeria no próximo
    restart. Segue o padrão de `reagendar_carga_folha`.
    """
    if _agendador is None:
        return False
    try:
        from apscheduler.triggers.cron import CronTrigger
        _agendador.reschedule_job(
            "coleta_dados_abertos",
            trigger=CronTrigger(
                day=_cfg_int("coleta_api_dia", 5, 1, 28),
                hour=_cfg_int("coleta_api_hora", 4, 0, 23),
                minute=_cfg_int("coleta_api_minuto", 0, 0, 59)))
        return True
    except Exception:
        return False


def _job_coleta_dados_abertos():
    """Coleta PortalFácil (receitas, despesas, pagamentos, contratos, extras).

    Roda 1x/mês (dia/hora em `coleta_api_dia/hora/minuto`, padrão dia 5 às
    4h). Passa pelo distribuidor (`coletar_ponto`): uma coleta por vez, e
    cada ponto decide sozinho via `deve_coletar` (janela ou portal
    atualizado) e `api_ativa` — o job só orquestra e registra. Nunca
    levanta: ponto que falha entra no log e os demais seguem.
    """
    try:
        from mod_dados_abertos import coleta_api as _miolo_job
    except Exception:
        return
    _totais = {}
    for _ponto in ("receitas", "despesas", "pagamentos", "contratos",
                   "extras"):
        try:
            _rel = _miolo_job.coletar_ponto(_ponto, forcar=False)
        except Exception as ex:
            _totais[_ponto] = f"erro: {ex}"
            continue
        try:
            _totais[_ponto] = int((_rel or {}).get("coletadas") or 0)
        except Exception:
            _totais[_ponto] = 0
    try:
        from mod_tisosdocfly import observabilidade
        observabilidade.get_logger("tisosdocfly").info(
            f"coleta_dados_abertos: {_totais}")
    except Exception:
        pass


def _job_carga_folha():
    """Carga da folha de servidores — uma vez por dia, de madrugada.

    É o job mais "não" deste arquivo: ele existe para ficar PARADO na maior
    parte do tempo. Desligado por padrão (`fonte_folha.json` com
    `ativo: false`), age só sobre arquivo novo, nunca sobrescreve cadastro
    existente e nunca apaga nada. Três camadas de proteção, todas dentro de
    `carga_folha.carga_automatica()`; aqui está só o registro do resultado.
    """
    try:
        from mod_gest_cad_usuario.carga_folha import carga_automatica
        rel = carga_automatica()
    except Exception as ex:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger("tisosdocfly").error(
                f"carga_folha falhou: {ex}")
        except Exception:
            pass
        return
    try:
        log = observabilidade.get_logger("tisosdocfly")
    except Exception:
        return
    if not rel.get("rodou"):
        # Só vale logar quando a fonte está LIGADA: desligada, isto aqui é o
        # silêncio normal de um sistema que ninguém pediu para popular.
        if "desativada" not in (rel.get("motivo") or ""):
            log.info(f"carga_folha: {rel.get('motivo') or 'sem motivo'}")
        return
    log.info(
        f"carga_folha ({rel.get('origem', '?')}, competência "
        f"{rel.get('competencia') or '?'}): {rel.get('criados', 0)} criado(s), "
        f"{rel.get('marcados', 0)} marcado(s) para confirmar, "
        f"{rel.get('bloqueados', 0)} bloqueado(s), "
        f"{rel.get('total', 0)} servidor(es) na folha")
    for erro in (rel.get("erros") or [])[:5]:
        log.error(f"carga_folha: {erro}")


def _job_poda_auditoria():
    """Poda diária do banco exclusivo de auditoria (db_mod_auditoria.db).

    Remove das tabelas por módulo os registros mais antigos que o prazo de
    retenção configurado (auditoria_retencao_dias, default 90), para
    conformidade LGPD sem acúmulo indefinido.
    """
    removidos = 0
    try:
        from mod_tisosdocfly.bd_conexao import get_config
        from mod_auditoria.bd_manipulador import podar_registros
        try:
            dias = max(1, int(get_config("auditoria_retencao_dias", "90")))
        except (TypeError, ValueError):
            dias = 90
        try:
            removidos = podar_registros(dias)
        except Exception:
            removidos = 0
        if removidos:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger("tisosdocfly").info(
                f"poda auditoria: {removidos} registro(s) removidos | retenção {dias} dias")
    except Exception as ex:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger().error(f"poda_auditoria falhou: {ex}")
        except Exception:
            pass
    return removidos


def backup_bancos():
    """Copia TODOS os db_*.db para /backup com timestamp."""
    os.makedirs(PASTA_BACKUP, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    copiados = []
    for f in os.listdir(DIR_PROJETO):
        if f.startswith("db_") and f.endswith(".db"):
            origem = os.path.join(DIR_PROJETO, f)
            destino = os.path.join(PASTA_BACKUP, f"{stamp}_{f}")
            try:
                shutil.copy2(origem, destino)
                copiados.append(f)
            except Exception:
                pass
    _podar_backups()
    return copiados


def backup_modulo(chave):
    """Backup SOMENTE do banco do módulo. Retorna o nome do arquivo gerado ou None."""
    info = MAPA_BACKUPS.get(chave)
    if not info:
        return None
    arquivo = info[0]
    origem = os.path.join(DIR_PROJETO, arquivo)
    if not os.path.exists(origem):
        return None
    try:
        try:
            _con = sqlite3.connect(origem, timeout=10)
            try:
                _con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                _con.close()
        except Exception:
            pass
        os.makedirs(PASTA_BACKUP, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = os.path.join(PASTA_BACKUP, f"{stamp}_{arquivo}")
        shutil.copy2(origem, destino)
    except OSError:
        return None
    _podar_backups()
    return os.path.basename(destino)


def _podar_backups(manter=10):
    """Retém apenas os N backups mais recentes por banco de dados."""
    try:
        por_base = {}
        for f in sorted(os.listdir(PASTA_BACKUP)):
            nome_base = "_".join(f.split("_")[2:])
            por_base.setdefault(nome_base, []).append(f)
        for base, arquivos in por_base.items():
            for antigo in arquivos[:-manter]:
                os.remove(os.path.join(PASTA_BACKUP, antigo))
    except Exception:
        pass


def restaurar_backup(chave, arquivo, ator="sistema"):
    """Restaura o banco do módulo a partir de uma cópia retida.

    Só no modo SQLite (PostgreSQL usa o próprio backup/restore do
    banco): valida que o arquivo está entre as cópias retidas do módulo
    (sem `..`, sem barra — anti path traversal), preserva o banco atual
    numa cópia `pre-restore_*`, faz checkpoint do WAL e troca o arquivo
    de forma atômica (`os.replace`). Devolve (ok, mensagem); nunca
    levanta.
    """
    try:
        from mod_tisosdocfly.bd_manipulador import audit_log
    except Exception:
        audit_log = None
    try:
        if chave not in MAPA_BACKUPS:
            return False, "Módulo sem backup configurado"
        try:
            from mod_tisosdocfly.banco_conexao import sgbd_ativo
            if sgbd_ativo() == "postgres":
                return False, "Restauração disponível só no modo SQLite"
        except Exception:
            pass
        nome = os.path.basename(str(arquivo or ""))
        original = str(arquivo or "")
        if (not nome or nome in (".", "..") or "/" in original
                or "\\" in original or original != nome):
            return False, "Arquivo inválido"
        try:
            retidas = [a for a, _, _ in listar_backups(chave)]
        except Exception:
            retidas = []
        if nome not in retidas:
            return False, "Cópia não encontrada entre as retidas"
        sufixo = MAPA_BACKUPS[chave][0]
        if not nome.endswith(sufixo):
            return False, "Cópia não pertence a este módulo"
        origem = os.path.join(PASTA_BACKUP, nome)
        if not os.path.isfile(origem):
            return False, "Cópia não encontrada"
        from mod_tisosdocfly.repositorio import caminho_db
        vivo = caminho_db(chave)
        try:
            if os.path.isfile(vivo):
                _con = sqlite3.connect(vivo, timeout=10)
                try:
                    _con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    try:
                        _con.close()
                    except Exception:
                        pass
            os.makedirs(PASTA_BACKUP, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(vivo, os.path.join(
                PASTA_BACKUP, f"pre-restore_{stamp}_{sufixo}"))
        except Exception as ex:
            try:
                from mod_tisosdocfly import observabilidade
                observabilidade.get_logger("tisosdocfly").warning(
                    f"restaurar_backup[{chave}]: sem preservar o atual ({ex})")
            except Exception:
                pass
            return False, f"não foi possível preservar o banco atual: {ex}"
        try:
            shutil.copy2(origem, vivo)
            for _ext in ("-wal", "-shm"):
                try:
                    os.remove(vivo + _ext)
                except OSError:
                    pass
        except Exception as ex:
            return False, f"não foi possível restaurar: {ex}"
        _podar_backups()
        try:
            if audit_log is not None:
                audit_log(ator or "sistema", "tisosdocfly", "backup_restaurado",
                          f"módulo={chave} arquivo={nome}")
        except Exception:
            pass
        return True, "Backup restaurado — vale nas próximas operações"
    except Exception as ex:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger("tisosdocfly").exception(
                f"restaurar_backup[{chave}] falhou: {ex}")
        except Exception:
            pass
        return False, f"não foi possível restaurar: {ex}"


def restaurar_backup_arquivo(chave, nome_original, conteudo, ator="sistema"):
    """Restaura o banco do módulo a partir de um arquivo enviado pelo PC.

    Aceita só o formato gerado pelo backup do próprio módulo
    (`*{sufixo}`, ex.: `20260101_060000_db_mod_blog.db`): valida o nome,
    o cabeçalho SQLite e a integridade (`PRAGMA quick_check`), guarda o
    arquivo entre as cópias retidas e delega a troca à
    `restaurar_backup` (que preserva o banco atual em `pre-restore_*` e
    audita). Só no modo SQLite. Devolve (ok, mensagem); nunca levanta.
    """
    try:
        if chave not in MAPA_BACKUPS:
            return False, "Módulo sem backup configurado"
        try:
            from mod_tisosdocfly.banco_conexao import sgbd_ativo
            if sgbd_ativo() == "postgres":
                return False, "Restauração disponível só no modo SQLite"
        except Exception:
            pass
        sufixo = MAPA_BACKUPS[chave][0]
        original = str(nome_original or "")
        base = os.path.basename(original)
        if (not base or base in (".", "..") or "/" in original
                or "\\" in original or original != base):
            return False, "Arquivo inválido"
        if not base.endswith(sufixo):
            return False, ("O arquivo deve ser do formato deste módulo "
                           f"(*{sufixo})")
        try:
            dados = bytes(conteudo or b"")
        except Exception:
            dados = b""
        if not dados:
            return False, "Arquivo vazio"
        if len(dados) > 256 * 1024 * 1024:
            return False, "Arquivo maior que 256 MB"
        if dados[:16] != b"SQLite format 3\x00":
            return False, "Não é um banco SQLite válido"
        try:
            os.makedirs(PASTA_BACKUP, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            nome = f"{stamp}_upload_{sufixo}"
            destino = os.path.join(PASTA_BACKUP, nome)
            import tempfile as _tf
            _fd, _tmp = _tf.mkstemp(prefix="upload_bk_", dir=PASTA_BACKUP)
            try:
                with os.fdopen(_fd, "wb") as _fh:
                    _fh.write(dados)
                _con = sqlite3.connect(_tmp, timeout=10)
                try:
                    _row = _con.execute("PRAGMA quick_check").fetchone()
                finally:
                    try:
                        _con.close()
                    except Exception:
                        pass
                if not _row or str(_row[0]).lower() != "ok":
                    return False, "Banco com falha de integridade"
                shutil.copy2(_tmp, destino)
            finally:
                try:
                    os.remove(_tmp)
                except OSError:
                    pass
        except Exception as ex:
            return False, f"não foi possível validar o arquivo: {ex}"
        return restaurar_backup(chave, nome, ator=ator)
    except Exception as ex:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger("tisosdocfly").exception(
                f"restaurar_backup_arquivo[{chave}] falhou: {ex}")
        except Exception:
            pass
        return False, f"não foi possível restaurar: {ex}"


def listar_backups(chave=None):
    """[(arquivo, tamanho_kb, data_hora)] do mais recente ao mais antigo;
    com chave, filtra pelo banco daquele módulo."""
    if not os.path.isdir(PASTA_BACKUP):
        return []
    sufixo = MAPA_BACKUPS[chave][0] if chave in MAPA_BACKUPS else None
    saida = []
    for f in sorted(os.listdir(PASTA_BACKUP), reverse=True):
        if sufixo and not f.endswith(sufixo):
            continue
        caminho = os.path.join(PASTA_BACKUP, f)
        try:
            kb = max(1, round(os.path.getsize(caminho) / 1024))
            quando = datetime.fromtimestamp(os.path.getmtime(caminho)).strftime("%d/%m %H:%M")
            saida.append((f, kb, quando))
        except OSError:
            continue
    return saida


# ================== AGENDADOR DINÂMICO ==================

def iniciar_agendador():
    """Um job de backup POR módulo (intervalo individual) + limpeza do editorPDF."""
    global _agendador
    if _agendador is not None:
        return _agendador
    from apscheduler.schedulers.background import BackgroundScheduler

    sched = BackgroundScheduler(daemon=True)

    def _job_backup(chave):
        backup_modulo(chave)

    def _job_todos():
        for chave in MAPA_BACKUPS:
            backup_modulo(chave)

    def _job_cleanup_blog_imagens():
        """Blog: a cada 1 min remove imagens do editor não concretizadas.

        Imagens enviadas e não usadas em postagem em até 5 min (`expirar_imagens_orfas`).
        """
        try:
            from mod_blog.bd_manipulador import expirar_imagens_orfas
            expirar_imagens_orfas()
        except Exception as ex:
            try:
                from mod_tisosdocfly import observabilidade
                observabilidade.get_logger().error(f"cleanup_blog_imagens falhou: {ex}")
            except Exception:
                pass

    for chave in MAPA_BACKUPS:
        sched.add_job(_job_backup, "interval", args=[chave],
                      hours=intervalo_backup(chave), id=f"backup:{chave}")
    def _job_cleanup_pdfs():
        """Expiração do editorPDF a cada 1 min (sem depender de login).
        Usa a rotina do módulo dono (remove disco + inativa BD + devolve cota)
        com o tempo configurável via `editar_pdf_expiracao_min`; em caso de falha de
        import, cai no fallback que só limpa o disco."""
        try:
            from mod_edit_pdf.bd_manipulador import expirar_antigos, cfg_expiracao_min
            expirar_antigos(minutos=cfg_expiracao_min())
        except Exception as ex:
            try:
                from mod_tisosdocfly import observabilidade
                observabilidade.get_logger().error(f"cleanup_pdf falhou: {ex}")
            except Exception:
                pass
            limpar_editor_pdf(minutos=10)

    def _job_cleanup_videos():
        """Expiração do stage de vídeos a cada 1 min (sem depender de login).
        Usa a rotina do módulo dono (remove do disco + marca expirado) com o
        tempo configurável via `video_expiracao_min`. Publicado (biblioteca)
        nunca expira."""
        try:
            from mod_video.bd_manipulador import expirar_antigos, cfg_expiracao_min
            expirar_antigos(minutos=cfg_expiracao_min())
        except Exception as ex:
            try:
                from mod_tisosdocfly import observabilidade
                observabilidade.get_logger().error(f"cleanup_video falhou: {ex}")
            except Exception:
                pass

    def _job_reconciliar_impressao():
        """Reconcilia impressões iniciadas e nunca confirmadas (1x/hora).

        Roda separado do cleanup de 1 min porque o prazo é em HORAS — sem
        isso, cada minuto varria a tabela inteira à toa."""
        try:
            from mod_solicita_impressao.bd_manipulador import reconciliar_impressoes_iniciadas
            reconciliar_impressoes_iniciadas(horas=24)
        except Exception as ex:
            try:
                from mod_tisosdocfly import observabilidade
                observabilidade.get_logger().error(f"reconciliar_impressao falhou: {ex}")
            except Exception:
                pass

    def _job_cleanup_solicita():
        """Solicitação de Impressão: a cada 1 min remove rascunhos não confirmados
        (prazo tempo_expira_rascunho_min) e arquivos de solicitações impressas já
        vencidos (prazo tempo_exclui_impresso_min).

        Também reconcilia pedidos que INICIARAM impressão e nunca foram
        confirmados: sem isso a cota nunca era descontada e o PDF ficava órfão
        no servidor. Roda 1x/hora (o prazo de reconciliação é em horas)."""
        try:
            from mod_solicita_impressao.bd_manipulador import expirar_rascunhos_e_impressos
            expirar_rascunhos_e_impressos()
        except Exception as ex:
            try:
                from mod_tisosdocfly import observabilidade
                observabilidade.get_logger().error(f"cleanup_solicita falhou: {ex}")
            except Exception:
                pass

    sched.add_job(_job_cleanup_pdfs, "interval", minutes=1, id="cleanup_pdf")
    sched.add_job(_job_cleanup_videos, "interval", minutes=1, id="cleanup_video")
    sched.add_job(_job_cleanup_solicita, "interval", minutes=1, id="cleanup_solicita")
    sched.add_job(_job_reconciliar_impressao, "interval", hours=1, id="reconciliar_impressao")
    sched.add_job(_job_cleanup_blog_imagens, "interval", minutes=1, id="cleanup_blog_imagens")
    sched.add_job(_job_poda_auditoria, "interval", hours=24, id="poda_auditoria")
    sched.add_job(_job_monitor_empenho, "interval", seconds=intervalo_monitor_empenho(),
                  id="monitor_empenho")
    # Agregador de Notícias — coleta AUTOMÁTICA com intervalo 1h–6,5 dias e reinício diário às horas da manhã (zerar tudo)
    try:
        from mod_agregador_noticias.bd_manipulador import intervalo_min, habilitado, obter_hora_reinicio
        _int_ag = intervalo_min() if habilitado() else 60
        _hora_ag = obter_hora_reinicio()
        _h_ag, _m_ag = map(int, _hora_ag.split(":"))
    except Exception:
        _int_ag = 60
        _h_ag, _m_ag = 6, 0
    sched.add_job(_job_agregador_coleta, "interval", minutes=_int_ag, id="agregador_coleta")
    from apscheduler.triggers.cron import CronTrigger
    sched.add_job(_job_agregador_reinicio, CronTrigger(hour=_h_ag, minute=_m_ag), id="agregador_reinicio")
    # Folha de servidores — diária, de madrugada. Registrada SEMPRE (mesmo
    # desligada): o job sai em segundos quando a fonte está desligada, e
    # tê-lo agendado de antemão faz o cadastro de um município novo valer no
    # dia em que a fonte for ligada, sem precisar reiniciar o servidor.
    sched.add_job(_job_carga_folha,
                  CronTrigger(hour=_cfg_int("carga_folha_hora", 3, 0, 23),
                              minute=_cfg_int("carga_folha_minuto", 0, 0, 59)),
                  id="carga_folha")
    # PortalFácil (Dados Abertos) — 1x/mês, dia/hora configuráveis no painel
    # /admin/dados_abertos (padrão dia 5 às 4h). Registrado SEMPRE: cada ponto
    # sai em segundos fora da janela ou com o card desligado, e tê-lo
    # agendado faz a agenda do administrador valer sem restart.
    sched.add_job(_job_coleta_dados_abertos,
                  CronTrigger(day=_cfg_int("coleta_api_dia", 5, 1, 28),
                              hour=_cfg_int("coleta_api_hora", 4, 0, 23),
                              minute=_cfg_int("coleta_api_minuto", 0, 0, 59)),
                  id="coleta_dados_abertos")
    # Agendas por data dos cards do Hora Certa (24/10/2026): só o card com
    # data preenchida ganha o job `agenda:<chave>`; vazio = sem job.
    try:
        from mod_tisosdocfly.bd_conexao import get_config as _get_ag
        for _ch_ag in ("hora", "agregador_noticias", "empenhos", "folha",
                       "auditoria", "solicita_impressao",
                       "editar_pdf", "video", "dados_abertos", "blog",
                       *tuple(f"backup_{_m}" for _m in MAPA_BACKUPS)):
            try:
                _dt_ag = (_get_ag(f"agenda_data:{_ch_ag}", "") or "").strip()
                if not _dt_ag:
                    continue
                _hr_ag = (_get_ag(f"agenda_hora:{_ch_ag}", "08:00")
                          or "08:00")
                _rp_ag = (_get_ag(f"agenda_repeticao:{_ch_ag}", "diaria")
                          or "diaria")
                _tr_ag, _in_ag = construir_trigger_agenda(
                    _dt_ag, _hr_ag, _rp_ag)
                _ac_ag = _acao_agenda(_ch_ag)
                if _tr_ag is None or _ac_ag is None:
                    continue
                sched.add_job(_ac_ag, _tr_ag, id=f"agenda:{_ch_ag}",
                              start_date=_in_ag)
            except Exception:
                pass
    except Exception:
        pass
    sched.start()
    _agendador = sched
    return sched


def encerrar_agendador():
    """Para o agendador de forma ordenada (idempotente, fail-soft).

    Desliga o `BackgroundScheduler` sem aguardar jobs em curso
    (`wait=False` para não travar o encerramento) e limpa a referência
    global — uma nova chamada a `iniciar_agendador()` recria tudo.
    Usada no shutdown gracioso (`main.py::_encerrar`).
    """
    global _agendador
    sched, _agendador = _agendador, None
    if sched is None:
        return False
    try:
        sched.shutdown(wait=False)
    except Exception:
        try:
            from mod_tisosdocfly import observabilidade
            observabilidade.get_logger().warning(
                "encerrar_agendador: falha no shutdown")
        except Exception:
            pass
    return True


def reagendar_backup(chave, horas):
    """Aplica novo intervalo ao job vivo do módulo (sem restart)."""
    horas = max(1, int(horas))
    if _agendador is None:
        return False
    try:
        _agendador.reschedule_job(f"backup:{chave}", trigger="interval", hours=horas)
        return True
    except Exception:
        return False


def limpar_editor_pdf(minutos=10):
    """Remove arquivos do editorPDF mais antigos que N minutos."""
    removidos = 0
    agora = time.time()
    limite = minutos * 60
    if not os.path.isdir(PASTA_EDITOR_PDF):
        return 0
    for root, _dirs, files in os.walk(PASTA_EDITOR_PDF):
        for f in files:
            caminho = os.path.join(root, f)
            try:
                if agora - os.path.getmtime(caminho) > limite:
                    os.remove(caminho)
                    removidos += 1
            except Exception:
                pass
    return removidos
