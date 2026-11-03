"""Central T! SOS DocFly observability (loguru).

Observabilidade central do T! SOS DocFly (loguru).

Logs de erro / debug / info gravados em arquivo com:
  - rotação configurável (tempo, ex.: "1 month", ou tamanho, ex.: "50 MB");
  - retenção configurável (padrão "4 months") — arquivos rotacionados são
    compactados em .zip e mantidos até o prazo de retenção;
  - nível configurável (DEBUG/INFO/WARNING/ERROR);
  - opção de limpeza total dos logs.

Todas as opções vivem em tb_config (área de administração do módulo T! SOS DocFly):
  log_ativo, log_nivel, log_rotacao, log_retencao, log_console
  (auto/sempre/nunca), log_otel_envio, log_otel_nivel.
"""
import os
import sys
import glob
import time

from loguru import logger

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # src/
DIR_PROJETO = os.path.dirname(BASE_DIR)                                  # raiz do repositório

# Logs ficam na MESMA pasta do programa (onde main.py ou o executável roda),
# nunca em pasta temporária. Usa o diretório do entrypoint (sys.argv[0]);
# se indisponível, cai no diretório do projeto. Compatível com auto-py-to-exe.
def _pasta_programa():
    try:
        if getattr(sys, "frozen", False):  # PyInstaller / auto-py-to-exe
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    except Exception:
        return DIR_PROJETO


LOG_DIR = os.path.join(_pasta_programa(), "logs")

# Chaves de configuração (tb_config central)
CFG_ATIVO = "log_ativo"
CFG_NIVEL = "log_nivel"
CFG_ROTACAO = "log_rotacao"
CFG_RETENCAO = "log_retencao"
CFG_CONSOLE = "log_console"
CFG_OTEL_ENVIO = "log_otel_envio"
CFG_OTEL_NIVEL = "log_otel_nivel"

DEFAULTS = {
    CFG_ATIVO: "1",
    CFG_NIVEL: "INFO",
    CFG_ROTACAO: "1 month",
    CFG_RETENCAO: "4 months",
    CFG_CONSOLE: "auto",
    CFG_OTEL_ENVIO: "1",
    CFG_OTEL_NIVEL: "DEBUG",
}

_sinks = []
# O retrato da configuração que os sinks ATUAIS representam. `None` = ainda
# não configurado (o guarda de `configurar()` monta do primeiro uso).
_assinatura_aplicada = None

# Módulos com arquivo de log próprio (separação por módulo)
MODULOS = ["gest_cad_usuario", "blog", "edit_pdf",
           "renomear_empenho", "auditoria", "solicita_impressao"]

_FMT = ("{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{module}:{function}:{line} | {message}")

# Formato COLORIDO para o CONSOLE (loguru coloriza as tags <level>/<green>/<cyan>).
# Os arquivos continuam com `_FMT` (sem códigos ANSI), para não poluir os logs.
_FMT_COLOR = ("<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
              "<level>{level: <8}</level> | "
              "<cyan>{module}:{function}:{line}</cyan> | "
              "{message}")


def _obter(chave, padrao):
    try:
        from mod_tisosdocfly.bd_conexao import get_config
        return get_config(chave, padrao)
    except Exception:
        return padrao


def _console_valido(v):
    """Validates the console mode (auto/sempre/nunca), defaulting to auto.

    Valida o modo do console (auto/sempre/nunca); padrão `auto`."""
    v = (v or "auto").strip().lower()
    return v if v in ("auto", "sempre", "nunca") else "auto"


def _nivel_valido(v):
    v = (v or "INFO").upper()
    return v if v in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL") else "INFO"


def _assinatura_config():
    """Retrato exato dos ajustes que determinam os sinks.

    Existe para o guarda de `configurar()`: sem ela, não há como saber se os
    sinks já estão certos, e a única forma de garantir é reconstruir — que é
    o que multiplicava os avisos.
    """
    return (
        _obter(CFG_ATIVO, "1"),
        _obter(CFG_NIVEL, "INFO"),
        _obter(CFG_ROTACAO, "1 month"),
        _obter(CFG_RETENCAO, "4 months"),
        _console_valido(_obter(CFG_CONSOLE, "auto")),
        _obter(CFG_OTEL_ENVIO, "1"),
        _obter(CFG_OTEL_NIVEL, "DEBUG"),
        _nivel_valido(_obter(CFG_OTEL_NIVEL, "DEBUG")),
        tuple(MODULOS),
    )


def configurar(forcar=False):
    """(Re)configura os sinks do loguru conforme tb_config.

    - Arquivo core (tisosdocfly_*.log) para logs do sistema sem módulo explícito.
    - Um arquivo por módulo (ex.: solicita_impressao_*.log) para separação.
    - Console (terminal) conforme `log_console`: `auto` (só via python,
      nunca no executável congelado), `sempre` ou `nunca` (só arquivo).
    - Bridge loguru→OTel (Loki) conforme `log_otel_envio`/`log_otel_nivel`.

    **POR QUE EXISTE O GUARDA (10/10/2026).** `configurar()` era chamada DUAS
    vezes no boot (`main.py`, no módulo e de novo no bloco `__main__`), e cada
    chamada reconstruía os 7 sinks. Com `enqueue=True`, cada sink criava uma
    fila de `multiprocessing` — e o Python reclamava de 56 semáforos
    "vazados" no encerramento, **duas vezes o necessário**.

    O aviso em si é cosmético: o SO descarta a fila quando o processo morre e
    nenhum log se perde. O que não era aceitável era a multiplicação — e a
    tela de administração chama `configurar()` de novo toda vez que o
    administrador mexe no nível do log, somando outro lote a cada vez.

    Então: se a configuração não mudou, esta função não reconstrói nada.
    `forcar=True` ignora o guarda (usado quando se quer um log novo de fato).

    E em 10/10/2026 os sinks passaram a `enqueue=False`, que zera os
    semáforos na origem — ver o comentário no `_add`.
    """
    global _sinks, _sink_otel_loguru, _assinatura_aplicada
    try:
        if not forcar:
            try:
                if _assinatura_aplicada == _assinatura_config():
                    return
            except Exception:
                pass  # sem tb_config ainda: segue e monta do zero
        logger.remove()  # remove tudo (inclusive o stderr padrão do loguru)
        _sinks = []
        _sink_otel_loguru = None
        if _obter(CFG_ATIVO, "1") != "1":
            return
        os.makedirs(LOG_DIR, exist_ok=True)
        nivel = _nivel_valido(_obter(CFG_NIVEL, "INFO"))
        rotacao = _obter(CFG_ROTACAO, "1 month") or "1 month"
        retencao = _obter(CFG_RETENCAO, "4 months") or "4 months"

        def _add(nome_arquivo, filtro):
            sid = logger.add(
                os.path.join(LOG_DIR, nome_arquivo),
                level=nivel,
                rotation=rotacao,
                retention=retencao,
                compression="zip",
                encoding="utf-8",
                # `enqueue=False` — medido em 10/10/2026.
                #
                # `enqueue=True` cria uma fila de `multiprocessing` por sink
                # (Lock + Event + Semaphore). Contando os registros no
                # `resource_tracker`: 7 sinks com `enqueue=True` = **56
                # semáforos**; os mesmos 7 com `enqueue=False` = **0**. E o
                # aviso "N leaked semaphore objects" no encerramento era
                # exatamente esse número — 56 — e aparecia a cada `Ctrl+C`.
                #
                # A fila só pagaria se houvesse log vindo de OUTRO PROCESSO
                # para estes sinks, e não há: a coleta (`coleta_kbp.py`) roda
                # como processo separado, com logger próprio e `enqueue=False`
                # (é o que garante a linha na tela imediatamente). Os
                # `subprocess.Popen` do projeto usam o padrão `close_fds=True`,
                # então o filho não herda o fd do log — fork não duplica
                # escrita. Entre threads, o loguru tem lock próprio.
                #
                # O único custo é a rotação: `compression="zip"` roda na
                # chamada que dispara a rotação, e bloqueia a thread por
                # alguns milissegundos — **uma vez por mês**, com
                # `rotation="1 month"`. Trocar 56 avisos de encerramento por
                # um engasgo mensal de poucos milissegundos é troca boa.
                enqueue=False,
                backtrace=True,
                diagnose=True,
                format=_FMT,
                filter=filtro,
            )
            _sinks.append(sid)

        # Core: TUDO que não tem arquivo próprio.
        #
        # A regra é "quem não tem sink dedicado vai para o core", e não "quem
        # não tem módulo vai para o core". A diferença é que a segunda regra
        # FAZ DESAPARECER log, e desaparecer é o pior defeito que um logger
        # pode ter: o servidor trava, o operador fecha o terminal, e o
        # diagnóstico foi embora com ele.
        #
        # DOIS defeitos medidos que isso resolve (ambos pré-existentes):
        #
        # 1. `get_logger("tisosdocfly")` — que é como o boot e o shutdown
        #    chamam — marca `modulo="tisosdocfly"`, e "tisosdocfly" não está em
        #    `MODULOS`. O filtro era só `not extra.get("modulo")`, então o core
        #    rejeitava E nenhum sink de módulo casava. As linhas "sinal
        #    recebido (2) — encerrando" e "atexit: encerrando processo"
        #    nunca chegaram a arquivo nenhum.
        #
        # 2. Nove módulos não estão em `MODULOS` e somavam **1.581** chamadas
        #    de `get_logger` que iam só para o console (medido em 11/10/2026):
        #    `lista_telefonica` com 1.523, `hora_certa` 18, `tecnico` 11,
        #    `filas` 8, `dados_abertos` 6, `agregador_noticias` 6, `estoque` 3,
        #    `os` 3, `agregador_noticia` 1. Confirmado com
        #    `get_logger('lista_telefonica')`: aparece no console e em NENHUM
        #    arquivo.
        #
        # Por que o core e não criar os 9 sinks: o problema é a mensagem sumir,
        # não ela ir para o arquivo do sistema. Acrescentar um módulo em
        # `MODULOS` continua sendo o caminho para ter arquivo próprio — e
        # quando isso acontecer, o filtro passa a tirá-lo do core
        # automaticamente, sem editar esta linha.
        _add("tisosdocfly_{time:YYYY-MM-DD}.log",
             lambda r: (not r["extra"].get("modulo")
                        or r["extra"].get("modulo") not in MODULOS))
        # Um arquivo dedicado por módulo
        for m in MODULOS:
            _add(f"{m}_{{time:YYYY-MM-DD}}.log",
                 (lambda r, m=m: r["extra"].get("modulo") == m))

        # Console: auto = só via terminal (nunca no executável congelado);
        # sempre/nunca forçam com/sem console (só arquivo quando nunca).
        modo_console = _console_valido(_obter(CFG_CONSOLE, "auto"))
        console = "nao"
        if modo_console == "sempre" or (
                modo_console == "auto" and not getattr(sys, "frozen", False)):
            logger.add(sys.stderr, level=nivel, format=_FMT_COLOR,
                       filter=lambda r: True)
            console = "sim"

        # Bridge: roteia logs do loguru para o OpenTelemetry (→ Loki via collector).
        # loguru aceita instâncias de logging.Handler como sink: cada record é
        # convertido e enviado ao LoggerProvider OTel. Sem isso, logs via loguru()
        # (o que o app usa) NUNCA chegam ao Loki — ficam presos no arquivo/console.
        # `log_otel_envio=0` mantém o log só local; `log_otel_nivel` filtra o envio.
        envio_otel = _obter(CFG_OTEL_ENVIO, "1") == "1"
        nivel_otel = _nivel_valido(_obter(CFG_OTEL_NIVEL, "DEBUG"))
        if envio_otel and _sink_otel_loguru is None:
            try:
                from mod_tisosdocfly.otel_integracao import (
                    OTEL_AVAILABLE, obter_handler_log,
                )
                _h = obter_handler_log()
                if OTEL_AVAILABLE and _h:
                    logger.add(_h, level=nivel_otel)
                    _sink_otel_loguru = _h
            except Exception as e:
                print(f"[observabilidade] falha ao bridge OTel loguru: {e}")

        logger.info(f"Observabilidade ativa | nivel={nivel} rotacao={rotacao} "
                    f"retencao={retencao} | console={console} "
                    f"otel_envio={'sim' if envio_otel else 'nao'} "
                    f"otel_nivel={nivel_otel}")
        try:
            _assinatura_aplicada = _assinatura_config()
        except Exception:
            _assinatura_aplicada = None
    except Exception as e:
        # Nunca deixar o log quebrar o boot do sistema
        print(f"[observabilidade] falha ao configurar logger: {e}")


def limpar_todos():
    """Remove TODOS os arquivos de log (ativos e compactados em .zip)."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        removidos = 0
        for pad in ("*.log", "*.log.zip", "*.log.*.zip"):
            for f in glob.glob(os.path.join(LOG_DIR, pad)):
                try:
                    os.remove(f)
                    removidos += 1
                except OSError:
                    pass
        return True, f"{removidos} arquivo(s) de log removido(s)"
    except Exception as e:
        return False, str(e)


def formatar_tamanho(tamanho_kb):
    """Formata KB em 'X KB' ou 'Y.Y MB' (puro, testável)."""
    try:
        kb = float(tamanho_kb or 0)
    except (TypeError, ValueError):
        kb = 0.0
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB"
    return f"{max(1, round(kb))} KB"


def listar_logs():
    """Lista os arquivos de log com tamanho e marca de uso.

    Retorna `[(arquivo, tamanho_kb, data_hora, em_uso)]` do mais recente
    ao mais antigo, incluindo compactados (`.zip`). Marca `em_uso=True`
    nos `.log` com a data de hoje (sinks ativos do loguru). Fail-soft:
    erro devolve `[]`. Usada no card "Observabilidade e logs".
    """
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        hoje = time.strftime("%Y-%m-%d")
        achados = []
        for pad in ("*.log", "*.log.zip", "*.log.*.zip"):
            for caminho in glob.glob(os.path.join(LOG_DIR, pad)):
                try:
                    nome = os.path.basename(caminho)
                    kb = max(1, round(os.path.getsize(caminho) / 1024))
                    dh = time.strftime("%Y-%m-%d %H:%M",
                                       time.localtime(os.path.getmtime(caminho)))
                    em_uso = (nome.endswith(".log") and hoje in nome)
                    achados.append((nome, kb, dh, em_uso, os.path.getmtime(caminho)))
                except OSError:
                    continue
        achados.sort(key=lambda r: r[4], reverse=True)
        return [(nome, kb, dh, em_uso) for nome, kb, dh, em_uso, _ in achados]
    except Exception:
        return []


def gerar_logs_teste_niveis():
    """Emits one log per level (DEBUG/INFO/WARNING/ERROR) for admin verification.

    Emite um registro de log em cada um dos 4 níveis do loguru com a descrição
    "Gestão de nível de logs". Serve ao administrador que acabou de salvar as
    configurações de observabilidade: no terminal/console aparecem os níveis
    permitidos, e no ARQUIVO apenas os eventos do NÍVEL MÍNIMO para cima são
    gravados — provando que o filtro de nível está ativo e que a cadeia
    arquivo/rotação/retenção está funcionando."""
    try:
        logger.debug("Gestão de nível de logs — teste de nível DEBUG")
        logger.info("Gestão de nível de logs — teste de nível INFO")
        logger.warning("Gestão de nível de logs — teste de nível WARNING")
        logger.error("Gestão de nível de logs — teste de nível ERROR")
    except Exception as e:
        # Última saída caso o loguru falhe (sink quebrado, disco etc.): print
        # no terminal garante que algo foi gravado.
        print(f"[observabilidade] falha ao gerar logs de teste por nível: {e}")


def _mostrar_no_terminal(titulo, tipo=None, valor=None, tb=None):
    """EN: Prints the traceback to the terminal (dev visibility).
    PT-BR: Imprime o traceback no terminal (visibilidade em desenvolvimento).
    Nunca levanta exceção."""
    try:
        import traceback
        print(f"\n[ERRO] {titulo}", file=sys.stderr, flush=True)
        try:
            if tipo is not None or valor is not None or tb is not None:
                traceback.print_exception(tipo, valor, tb)
            else:
                traceback.print_exc()
        except Exception:
            pass
        try:
            sys.stderr.flush()
        except Exception:
            pass
    except Exception:
        pass


def instalar_excepthook():
    """Captures EVERY unhandled exception: log file + terminal.

    Rede global de segurança (última linha após os try/except por função
    do §3.2): thread principal (`sys.excepthook`), threads filhas
    (`threading.excepthook`) e loop assíncrono. Tudo é registrado no log
    (loguru, com traceback) E impresso no terminal (stderr) — em
    desenvolvimento nenhuma exceção passa silenciosa. Nunca levanta exceção."""
    try:
        import threading as _th
        import traceback as _tb_mod  # noqa: F401 (garante stderr formatado)
    except Exception:
        _th = None

    def hook(tipo, valor, tb):
        try:
            logger.opt(exception=(tipo, valor, tb)).error("Exceção não tratada")
        except Exception as _e_log:
            try:
                print(f"[observabilidade] falha ao logar exceção: {_e_log}")
            except Exception:
                pass
        _mostrar_no_terminal("Exceção não tratada (thread principal)", tipo, valor, tb)

    def hook_thread(args):
        try:
            logger.opt(exception=(args.exc_type, args.exc_value,
                                  args.exc_traceback)).error(
                f"Exceção não tratada em thread ({args.thread})")
        except Exception as _e_log:
            try:
                print(f"[observabilidade] falha ao logar exceção de thread: {_e_log}")
            except Exception:
                pass
        _mostrar_no_terminal(
            f"Exceção não tratada em thread ({getattr(args, 'thread', '?')})",
            getattr(args, "exc_type", None),
            getattr(args, "exc_value", None),
            getattr(args, "exc_traceback", None))

    def hook_async(loop, contexto):
        try:
            exc = contexto.get("exception")
            if exc is not None:
                logger.opt(exception=exc).error(
                    f"Exceção em loop assíncrono: {contexto.get('message')}")
            else:
                logger.error(
                    f"Exceção em loop assíncrono: {contexto.get('message')}")
        except Exception as _e_log:
            try:
                print(f"[observabilidade] falha ao logar exceção assíncrona: {_e_log}")
            except Exception:
                pass
        try:
            print(f"\n[ERRO] Exceção em loop assíncrono: "
                  f"{contexto.get('message')}", file=sys.stderr, flush=True)
            exc = contexto.get("exception")
            if exc is not None:
                import traceback
                traceback.print_exception(type(exc), exc, exc.__traceback__)
                sys.stderr.flush()
        except Exception:
            pass

    try:
        sys.excepthook = hook
    except Exception as _e:
        try:
            print(f"[observabilidade] falha ao instalar sys.excepthook: {_e}")
        except Exception:
            pass
    try:
        if _th is not None and hasattr(_th, "excepthook"):
            _th.excepthook = hook_thread
    except Exception as _e:
        try:
            print(f"[observabilidade] falha ao instalar threading.excepthook: {_e}")
        except Exception:
            pass
    try:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            try:
                loop.set_exception_handler(hook_async)
            except Exception:
                pass
    except Exception:
        pass
    try:
        print("[observabilidade] rede global de exceções ativa "
              "(log + terminal: principal, threads, asyncio)")
    except Exception:
        pass


def registrar_excecoes_nicegui(app):
    """Logs NiceGUI page-handler exceptions to file + terminal.

    Registra o handler global do NiceGUI (`app.on_exception`): exceções em
    handlers de página (ex.: diálogos, on_click) são logadas com traceback
    e impressas no terminal. Sem isso, o navegador só mostra "disconnected"
    sem causa visível. Fail-soft: sem NiceGUI/app válido, só avisa."""
    try:
        if app is None or not hasattr(app, "on_exception"):
            try:
                print("[observabilidade] app NiceGUI sem on_exception — "
                      "exceções de página sem rede global")
            except Exception:
                pass
            return False

        def _ao_erro_nicegui(exc):
            try:
                logger.opt(exception=exc).error("Exceção em handler NiceGUI")
            except Exception as _e_log:
                try:
                    print(f"[observabilidade] falha ao logar exceção NiceGUI: {_e_log}")
                except Exception:
                    pass
            try:
                _mostrar_no_terminal(
                    "Exceção em handler NiceGUI (página/diálogo)",
                    type(exc), exc,
                    getattr(exc, "__traceback__", None))
            except Exception:
                pass

        app.on_exception(_ao_erro_nicegui)
        try:
            print("[observabilidade] rede NiceGUI ativa "
                  "(handlers de página: log + terminal)")
        except Exception:
            pass
        return True
    except Exception as _e:
        try:
            print(f"[observabilidade] falha ao registrar exceções NiceGUI: {_e}")
        except Exception:
            pass
        return False


def get_logger(modulo=None):
    """Retorna o logger. Se `modulo` for informado, o registro é marcado para
    ir também ao arquivo dedicado daquele módulo (ex.: solicita_impressao_*.log)."""
    if modulo:
        return logger.bind(modulo=modulo)
    return logger
