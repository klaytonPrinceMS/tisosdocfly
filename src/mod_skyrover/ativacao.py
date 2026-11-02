"""Assistente de ativação/configuração do sistema no terminal (setup wizard).

EN — Interactive terminal wizard shown at startup. Press ENTER to boot with
    the default configuration; type "sim"/"s" to enter activation mode and
    choose the database backend (SQLite/PostgreSQL), OpenTelemetry (auto-
    installing Docker when missing on the detected OS) and the service ports
    (site, PostgreSQL, Grafana). Shows colored output and a progress bar.
PT — Assistente interativo no terminal exibido na inicialização. Aperte ENTER
    para subir com a configuração padrão; digite "sim"/"s" para entrar no
    modo de ativação e escolher o backend de banco (SQLite/PostgreSQL), o
    OpenTelemetry (instala Docker automaticamente quando ausente, conforme o
    SO detectado) e as portas dos serviços (site, PostgreSQL, Grafana). Usa
    texto colorido e barra de progresso.
"""
import concurrent.futures
import os
import re
import shlex
import sys
import time
import threading
import platform
import subprocess
import shutil

_TTY = sys.stdout.isatty() and sys.stdin.isatty()

# =============================================================================
# Cores de terminal via rich
# =============================================================================
# As cores são produzidas pelo `rich` (mesma biblioteca usada pelo `typer`),
# que detecta o terminal e gera os códigos ANSI corretos; em saída não
# interativa os textos saem SEM cor (logs/pipes ficam limpos).
import io as _io
from rich.console import Console as _ConsoleRich

_MAPA_RICH = {
    "verde": "green",
    "amarelo": "yellow",
    "azul": "blue",
    "vermelho": "red",
    "ciano": "cyan",
}


def _abre_fecha(estilo):
    """Renders a rich style and returns (open_code, close_code)."""
    buf = _io.StringIO()
    c = _ConsoleRich(file=buf, force_terminal=True, color_system="standard")
    c.print("X", style=estilo, end="")
    antes, _, depois = buf.getvalue().partition("X")
    return antes, depois


_ABRE = {}
_FECHA = {}
for _nome, _rich in _MAPA_RICH.items():
    _ABRE[_nome], _FECHA[_nome] = _abre_fecha(_rich)
    _ABRE[f"negrito_{_nome}"], _FECHA[f"negrito_{_nome}"] = _abre_fecha(
        "bold " + _rich)


def c(texto, cor="verde", negrito=False):
    """Returns the text styled with rich (ANSI no terminal, plano se não-TTY)."""
    if not _TTY:
        return texto
    chave = cor if not negrito else f"negrito_{cor}"
    return f"{_ABRE.get(chave, '')}{texto}{_FECHA.get(chave, '')}"


_VERSAO = "1.0.260908"

_console_out = _ConsoleRich()


def banner():
    """Prints the system banner (rich)."""
    _console_out.print("=" * 62, style="bold blue")
    _console_out.print(f"  SKYROVER MODULAR {_VERSAO} — PRINCE, K.B",
                       style="bold cyan")
    _console_out.print("  Assistente de inicialização / ativação", style="blue")
    _console_out.print("=" * 62, style="bold blue")


def barra(fracao, rotulo=""):
    """Renders a progress bar in the terminal (40 chars)."""
    if not _TTY:
        return
    fracao = max(0.0, min(1.0, fracao))
    larg = 40
    preenchido = int(fracao * larg)
    bar = "\u2588" * preenchido + "\u2591" * (larg - preenchido)
    sys.stdout.write(
        f"\r{_ABRE['azul']}[{bar}]{_FECHA['azul']} "
        f"{int(fracao * 100):3d}% {_ABRE['ciano']}{rotulo}{_FECHA['ciano']}")
    sys.stdout.flush()


def fim_barra():
    """Ends the current progress-bar line."""
    if _TTY:
        sys.stdout.write("\n")
        sys.stdout.flush()


def perguntar(texto, padrao="", validos=None, valido_num=False, faixa=None):
    """Asks a question and returns a normalized answer (default if empty).

    `faixa=(min, max)` restringe valores numéricos (ex.: portas 1–65535).
    ENTER devolve o padrão; resposta inválida REPETE a pergunta até uma
    resposta válida (mesmo padrão do prompt inicial do assistente)."""
    while True:
        try:
            resp = input(c(f"{texto}: ", "ciano")).strip()
        except (EOFError, KeyboardInterrupt):
            return padrao
        if not resp:
            return padrao
        if valido_num:
            try:
                n = int(resp)
            except ValueError:
                print(c("Valor inválido — digite um número.", "amarelo"))
                continue
            if faixa is not None and not (faixa[0] <= n <= faixa[1]):
                print(c(f"Valor fora da faixa {faixa[0]}–{faixa[1]} — "
                        "digite novamente.", "amarelo"))
                continue
            return str(n)
        if validos:
            r = resp.lower()
            if r in validos:
                return r
            print(c("Opção inválida — digite uma das opções válidas.",
                    "amarelo"))
            continue
        return resp


def _porta_valida(resp, padrao):
    """Normaliza uma porta digitada; vazio/fora da faixa → usa o padrão."""
    try:
        n = int(str(resp or "").strip())
    except ValueError:
        return padrao
    return n if 1 <= n <= 65535 else padrao


def _portas_livres(inicio, quantas=3, limite=50):
    """Returns `quantas` free ports near `inicio` (suggestion examples).

    Retorna portas livres próximas de `inicio` para sugerir ao usuário
    quando a porta padrão estiver em uso (ex.: 5432 ocupado → 5433, 5434...)."""
    livres = []
    p = max(1024, int(inicio or 5432))
    tentativas = 0
    while len(livres) < quantas and tentativas < limite:
        if _porta_livre(p):
            livres.append(p)
        p += 1
        tentativas += 1
    return livres


# =============================================================================
# Portas e serviços (scanner local — segurança/instalação)
# =============================================================================
_portas_scan_cache = None
_scan_lock = threading.Lock()


def _portas_em_uso_cached():
    """Ports+services via `port_scanner`, com cache por processo (lock).

    Escaneia UMA vez por execução e reutiliza nas perguntas — não repete o
    scan a cada prompt. Fail-soft: devolve {} em qualquer falha."""
    global _portas_scan_cache
    if _portas_scan_cache is not None:
        return _portas_scan_cache
    with _scan_lock:
        if _portas_scan_cache is not None:
            return _portas_scan_cache
        try:
            from mod_skyrover import port_scanner
            _portas_scan_cache = port_scanner.portas_com_servico()
        except Exception:
            _portas_scan_cache = {}
        return _portas_scan_cache


def _msg_porta_em_uso(porta):
    """Aviso completo de porta em uso: TODAS as portas ocupadas + serviço de
    cada uma (scanner local) e exemplos de portas livres."""
    em_uso = _portas_em_uso_cached()
    linhas = []
    for p in sorted(em_uso):
        if p != int(porta) or True:
            linhas.append(f"  {p}: {em_uso[p] or 'desconhecido'}")
    blocos = "\n".join(linhas) if linhas else "  (sem detalhes)"
    livres = ", ".join(str(p) for p in _portas_livres(porta)) or "—"
    return (f"A porta padrão {porta} está em uso. Portas em uso no servidor:\n"
            f"{blocos}\nPortas livres (exemplos): {livres}")


def _postgres_docker_ativo():
    """Host port of a running `skyrover_postgres` container (or None).

    Se o container do Postgres do sistema JÁ está rodando, devolve a porta
    publicada no host — o assistente apenas CONECTA (sem baixar/subir)."""
    if not docker_instalado():
        return None
    try:
        r = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                           capture_output=True, text=True, timeout=10)
        if "skyrover_postgres" not in (r.stdout or "").split():
            return None
        r2 = subprocess.run(["docker", "port", "skyrover_postgres"],
                            capture_output=True, text=True, timeout=10)
        m = re.search(r":(\d+)\s*$", (r2.stdout or "").strip())
        return int(m.group(1)) if m else 5432
    except Exception:
        return None


def _otel_docker_ativo():
    """True if the OTel LGTM stack containers are running."""
    if not docker_instalado():
        return False
    try:
        r = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                           capture_output=True, text=True, timeout=10)
        nomes = (r.stdout or "").split()
        return any(n in nomes for n in (
            "skyrover-grafana", "skyrover-loki", "skyrover-tempo",
            "skyrover-mimir", "skyrover-otel-collector"))
    except Exception:
        return False


# =============================================================================
# Detecção de serviços JÁ RODANDO (reuso sem pull)
# =============================================================================
# Antes de baixar/subir imagens, o assistente verifica as portas ocupadas no
# servidor (cache do scanner, `_portas_em_uso_cached`) e tenta IDENTIFICAR se
# algum serviço do sistema já está ativo nelas: PostgreSQL acessível com as
# credenciais do sistema e a stack OTel (grafana/loki/tempo/mimir/collector).
# Quando encontra, REUSA (apenas conecta) em vez de fazer pull/up inútil —
# o caso real: um Grafana já rodava na porta 3000 enquanto o assistente puxava
# loki/tempo/mimir à toa.

_cache_probe_postgres = None          # porta encontrada (ou None) — cache por execução
_cache_probe_postgres_pronto = False  # True quando o probe já rodou (evita re-scan)
_cache_deteccao_otel = None           # {serviço: porta} — cache por execução

_SERVICOS_OTEL = ("grafana", "loki", "tempo", "mimir", "collector")
_NOME_LEGIVEL_OTEL = {
    "grafana": "grafana",
    "loki": "loki",
    "tempo": "tempo",
    "mimir": "mimir",
    "collector": "otel-collector",
}


def _normalizar_portas(em_uso):
    """{int porta: nome} normalizado (aceita chaves int ou str, ignora inválidas)."""
    norm = {}
    for k, v in em_uso.items():
        try:
            norm[int(k)] = v
        except (TypeError, ValueError):
            continue
    return norm


def _probe_postgres_porta(porta, timeout=2):
    """True se um PostgreSQL aceita as credenciais do sistema na `porta`.

    Testa o DSN do sistema (`postgresql+psycopg2://skyrover:skyrover@localhost:
    PORT/postgres`) com `connect_timeout` curto (~2 s). Fail-soft: False em
    qualquer falha (conexão recusada, credenciais diferentes, banco ausente,
    psycopg2 não instalado)."""
    dsn = (f"postgresql+psycopg2://skyrover:skyrover@localhost:{int(porta)}"
           f"/postgres?connect_timeout={int(timeout)}")
    return _verificar_postgres(dsn)


def _detectar_postgres_rodando():
    """Porta de um PostgreSQL do sistema JÁ RODANDO em portas ocupadas (ou None).

    Varre as portas ocupadas (cache do scanner) e testa em CADA uma o DSN do
    sistema com timeout curto:
      - CONECTA → é o Postgres do sistema → REUSAR (devolve a porta);
      - não conecta (refused/creds diferentes) → ignora (ex.: Postgres nativo
        de outro usuário não é reutilizável).
    O resultado é cacheado por execução — o probe NÃO é repetido a cada
    chamada (usa o cache do scanner + cache do probe)."""
    global _cache_probe_postgres, _cache_probe_postgres_pronto
    if _cache_probe_postgres_pronto:
        return _cache_probe_postgres
    _cache_probe_postgres = None
    em_uso = _normalizar_portas(_portas_em_uso_cached())
    for porta in sorted(em_uso):
        if not (1024 <= porta <= 65535):
            continue
        if _probe_postgres_porta(porta):
            _cache_probe_postgres = int(porta)
            break
    _cache_probe_postgres_pronto = True
    return _cache_probe_postgres


def _portas_docker_servicos_otel():
    """{serviço: porta} dos containers `skyrover-*` ativos (via docker ps).

    Método (a) da detecção OTel: identifica grafana/loki/tempo/mimir/
    otel-collector pelo NOME do container e devolve a porta publicada no host."""
    if not docker_instalado():
        return {}
    mapa = {
        "skyrover-grafana": "grafana",
        "skyrover-loki": "loki",
        "skyrover-tempo": "tempo",
        "skyrover-mimir": "mimir",
        "skyrover-otel-collector": "collector",
    }
    try:
        r = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                           capture_output=True, text=True, timeout=10)
        nomes = (r.stdout or "").split()
    except Exception:
        return {}
    achados = {}
    for nome in nomes:
        if nome not in mapa:
            continue
        porta = None
        try:
            r2 = subprocess.run(["docker", "port", nome],
                                capture_output=True, text=True, timeout=10)
            m = re.search(r":(\d+)\s*$", (r2.stdout or "").strip())
            porta = int(m.group(1)) if m else None
        except Exception:
            porta = None
        if porta:
            achados[mapa[nome]] = porta
    return achados


def _servicos_por_nome(em_uso):
    """{serviço: porta} identificados pelo NOME do processo na porta ocupada.

    Método (b): o scanner (`ss`/`netstat`/`docker ps`) já nomeia o processo de
    cada porta — "grafana", "loki", "tempo", "mimir" e "otel"/"collector"."""
    achados = {}
    chaves = {
        "grafana": ("grafana",),
        "loki": ("loki",),
        "tempo": ("tempo",),
        "mimir": ("mimir",),
        "collector": ("otel", "collector"),
    }
    for porta, nome in sorted(em_uso.items()):
        nome = (nome or "").lower()
        for servico, palavras in chaves.items():
            if servico in achados:
                continue
            if any(p in nome for p in palavras):
                achados[servico] = int(porta)
                break
    return achados


def _probe_http(porta, caminho, timeout=1.5):
    """True se GET http://localhost:{porta}{caminho} responde 200 (fail-soft)."""
    try:
        import urllib.request
        r = urllib.request.urlopen(f"http://localhost:{int(porta)}{caminho}",
                                   timeout=timeout)  # nosec B310 — esquema http:// literal + porta em int(); nunca file:// nem entrada do usuário
        return r.status == 200
    except Exception:
        return False


def _probe_servicos_http(em_uso, ja_achados=None):
    """{serviço: porta} via probe HTTP (THREADS) nas portas ocupadas.

    Método (c), último recurso: para cada porta ocupada ainda não identificada
    testa, EM PARALELO (`concurrent.futures`), os endpoints HTTP dos serviços:
    grafana `GET /api/health`; loki/tempo/mimir `GET /ready` (ou /metrics). O
    otel-collector é gRPC (4317) e NÃO responde HTTP — fica para a detecção
    por container/nome. Timeouts curtos + fail-soft: nenhuma falha de rede
    quebra o fluxo."""
    ja_achados = ja_achados or {}
    alvos = sorted({p for p in em_uso
                    if 1024 <= p <= 65535 and p not in ja_achados.values()})
    if not alvos:
        return {}
    achados = {}
    portas_ready = []

    def testar(p):
        return p, _probe_http(p, "/api/health"), _probe_http(p, "/ready")

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(16, max(1, len(alvos)))) as ex:
        for p, health, ready in ex.map(testar, alvos):
            if health:
                achados["grafana"] = p
            if ready:
                portas_ready.append(p)
    # Desambigua /ready → loki/tempo/mimir: primeiro pelo NOME do processo na
    # porta (o scanner já nomeia), depois pela porta padrão, e por fim o que
    # sobrar em ordem crescente de porta.
    for p in sorted(portas_ready):
        nome = (em_uso.get(p) or "").lower()
        if "loki" in nome and "loki" not in achados:
            achados["loki"] = p
        elif "tempo" in nome and "tempo" not in achados:
            achados["tempo"] = p
        elif "mimir" in nome and "mimir" not in achados:
            achados["mimir"] = p
    for servico, porta_padrao in (("loki", 3100), ("tempo", 3200),
                                  ("mimir", 9009)):
        if servico not in achados and porta_padrao in portas_ready:
            achados[servico] = porta_padrao
    restantes = sorted(p for p in portas_ready if p not in achados.values())
    for servico, p in zip(("loki", "tempo", "mimir"), restantes):
        if servico not in achados:
            achados[servico] = p
    return achados


def _detectar_otel_rodando():
    """{serviço: porta} dos serviços OTel JÁ ATIVOS nas portas ocupadas.

    Ordem dos métodos: (a) containers `skyrover-*` via `docker ps`;
    (b) nome do serviço no scanner (`portas_com_servico`, contém "grafana"/
    "loki"/"tempo"/"mimir"/"otel"/"collector"); (c) probe HTTP em cada porta
    ocupada com timeout curto e THREADS. O otel-collector (gRPC 4317) é
    detectado por (a)/(b) — não responde HTTP. Resultado cacheado por
    execução; fail-soft: {} em qualquer falha (nunca quebra o fluxo)."""
    global _cache_deteccao_otel
    if _cache_deteccao_otel is not None:
        return _cache_deteccao_otel
    achados = {}
    try:
        achados.update(_portas_docker_servicos_otel())
        em_uso = _normalizar_portas(_portas_em_uso_cached())
        achados.update(_servicos_por_nome(em_uso))
        achados.update(_probe_servicos_http(em_uso, ja_achados=achados))
    except Exception:
        pass
    _cache_deteccao_otel = achados
    return _cache_deteccao_otel


def _formatar_achados_otel(achados):
    """'grafana=3000, loki=3100, ...' legível para a mensagem de reuso."""
    return ", ".join(
        f"{_NOME_LEGIVEL_OTEL.get(s, s)}={p}" for s, p in sorted(achados.items()))


# =============================================================================
# Configuração padrão
# =============================================================================

def _config_padrao():
    """Default configuration — boot simples, sem assistente.

    Subir SEM configurações = SQLite apenas, SEM Postgres, SEM OpenTelemetry e
    SEM documentação (boot rápido e autossuficiente). Postgres/OTel/docs só são
    trazidos quando o usuário entra no modo de ativação/configuração ou passa a
    flag correspondente.

    `docs_ativo` começa **False** (decisão do responsável, 02/10/2026). Antes a
    documentação subia sozinha a cada boot: um `mkdocs build` completo (subprocess
    de até 120 s) mais um servidor HTTP extra na porta 8001, para um servidor que
    ninguém pediu. Quem quiser liga com `--ativ-docs` (CLI) ou pelo interruptor
    em Configurações — o mesmo desenho de `--otel`/`--postgres`, e a porta já é
    configurável por `--porta-docs` nos dois casos."""
    return {
        "modo": "padrao",
        "banco_tipo": "sqlite",
        "postgres_url": ("postgresql+psycopg2://skyrover:skyrover"
                         "@localhost:5432/skyrover"),
        "otel_ativo": False,
        "subir_postgres": False,
        "docs_ativo": False,
        "porta_site": 8080,
        "porta_postgres": 5432,
        "porta_grafana": 3000,
        "porta_documentacao": 8001,  # porta do mkdocs (documentação, evita 8000 do snap)
    }


# =============================================================================
# Persistência do seletor de banco (antes do inicializar_bancos)
# =============================================================================

def _garantir_tb_config():
    """Creates the central SQLite file + tb_config if missing (pre-boot).

    Idempotente: executa CREATE TABLE IF NOT EXISTS mesmo quando o arquivo
    já existe (ex.: arquivo vazio de um boot interrompido). Sem isso, o
    `aplicar_banco` falhava com "no such table: tb_config" nesses casos.
    Conexão direta sqlite3 pré-boot (seletor de backend ainda não aplicado)
    com pragmas WAL+`synchronous=NORMAL`+`busy_timeout=5000` (mesmo padrão
    de `banco_conexao.conexao`). Fail-soft sem derrubar o wizard.
    """
    try:
        from mod_skyrover.repositorio import DB_PATH
        import sqlite3
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("CREATE TABLE IF NOT EXISTS tb_config ("
                         "chave TEXT PRIMARY KEY, valor TEXT NOT NULL)")
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as exc:
        try:
            from mod_skyrover import observabilidade
            observabilidade.get_logger("skyrover").exception(
                f"_garantir_tb_config: {exc}")
        except Exception:
            pass
        return False


def aplicar_banco(cfg):
    """Persists the backend selector (banco_tipo/postgres_url) pre-boot."""
    try:
        _garantir_tb_config()
        from mod_skyrover import banco_conexao as bc
        bc.definir_banco_tipo(cfg.get("banco_tipo", "sqlite"))
        bc.definir_postgres_url(cfg.get(
            "postgres_url",
            "postgresql+psycopg2://skyrover:skyrover@localhost:5432/skyrover"))
    except Exception as e:
        print(c(f"[setup] aviso ao aplicar banco: {e}", "amarelo"))


# =============================================================================
# Portas — edição best-effort dos compose
# =============================================================================

def _trocar_porta_compose(caminho, mapeamentos):
    """Best-effort: replaces `orig:cont` port mappings in a compose file."""
    try:
        if not os.path.exists(caminho):
            return False
        with open(caminho, "r", encoding="utf-8") as f:
            txt = f.read()
        for origem, destino in mapeamentos.items():
            txt = txt.replace(f'"{origem}:', f'"{destino}:')
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(txt)
        return True
    except Exception:
        return False


def aplicar_portas(cfg):
    """Applies the configured ports to the docker compose files (best-effort)."""
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets", "docker")
    _trocar_porta_compose(
        os.path.join(base, "compose.yml"),
        {"3000": str(cfg.get("porta_grafana", 3000))})
    pg = os.path.join(base, "postgres", "docker-compose.yml")
    if os.path.exists(pg):
        try:
            with open(pg, "r", encoding="utf-8") as f:
                txt = f.read()
            txt = re.sub(r'"\d+:5432"',
                         f'"{cfg.get("porta_postgres", 5432)}:5432"', txt)
            with open(pg, "w", encoding="utf-8") as f:
                f.write(txt)
        except Exception:
            pass


# =============================================================================
# Docker — detecção, instalação e stack OTel
# =============================================================================

def docker_instalado():
    """True if the Docker CLI is available."""
    return shutil.which("docker") is not None


def _tem_operador_shell(comando):
    """True if the string needs a shell (&&, ||, ;, pipes, redirections)."""
    return bool(re.search(r"&&|\|\||[;|><()]|`|\$\(", comando))


def _mascarar_comando(comando):
    """Mascara credenciais no comando exibido (a senha nunca aparece)."""
    txt = comando if isinstance(comando, str) else " ".join(comando)
    txt = re.sub(
        r"([^\s|&;<>]+):([^\s|&;<>]+)(\s*\|\s*chpasswd\b)",
        r"\1:***\3", txt, flags=re.IGNORECASE)
    txt = re.sub(r"(-p\s+)\S+", r"\1***", txt, flags=re.IGNORECASE)
    txt = re.sub(r"(password=)\S+", r"\1***", txt, flags=re.IGNORECASE)
    txt = re.sub(r":senha\S*", ":***", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\b(PASSWORD|SENHA)\b(?!\s*=)", "***", txt)
    return txt


def _cmd(comando, timeout=600, entrada=None):
    """Runs a command, streaming output to the terminal.

    Aceita uma lista de argumentos (shell=False, sem interpolação) ou uma
    string: sem operadores de shell roda via `shlex.split` como lista; com
    operadores mantém o comportamento legado (comandos estáticos, sem entrada
    do usuário — nunca interpolamos entrada do usuário em shell). Credenciais
    são mascaradas no print; `entrada` é enviada por stdin (a senha nunca vai
    no argv). Retorna True se o retorno for 0."""
    usar_shell = False
    if isinstance(comando, str):
        if _tem_operador_shell(comando):
            usar_shell = True
        else:
            comando = shlex.split(comando)
    print(c(f"\n$ {_mascarar_comando(comando)}", "azul"))
    try:
        r = subprocess.run(
            comando, shell=usar_shell, timeout=timeout,  # nosec B602 — `usar_shell` só é True para comandos ESTÁTICOS defined no próprio assistente (ver docstring); senha entra por stdin, nunca interpolada no argv
            input=(entrada.encode() if isinstance(entrada, str) else entrada))
        return r.returncode == 0
    except Exception as e:
        print(c(f"  falha ao executar: {e}", "vermelho"))
        return False


def instalar_docker():
    """Installs Docker on the detected OS (needs sudo/admin on most cases)."""
    so = platform.system()
    print(c(f"Sistema operacional detectado: {so}", "ciano", True))
    if not docker_instalado():
        barra(0.25, "Instalando Docker...")
        if so == "Linux":
            if shutil.which("apt-get"):
                _cmd("sudo apt-get update && sudo apt-get install -y docker.io")
            elif shutil.which("dnf"):
                _cmd("sudo dnf install -y docker")
            elif shutil.which("yum"):
                _cmd("sudo yum install -y docker")
            else:
                print(c("Gestor de pacotes não identificado — instale o Docker "
                        "manualmente (https://docs.docker.com/engine/install/).",
                        "amarelo"))
            _cmd("sudo systemctl enable --now docker")
        elif so == "Darwin":
            _cmd("brew install --cask docker")
        elif so == "Windows":
            _cmd("winget install -e --id Docker.DockerDesktop")
        else:
            print(c("SO não suportado para instalação automática — instale o "
                    "Docker manualmente.", "amarelo"))
        barra(0.6, "Docker instalado")
    else:
        barra(0.6, "Docker já disponível")
    # garante o serviço em execução
    if so == "Linux":
        _cmd("sudo systemctl start docker || true")
    barra(0.8, "Verificando Docker")
    if docker_instalado():
        ok = _cmd("docker info >/dev/null 2>&1 || "
                  "(sudo systemctl start docker >/dev/null 2>&1; docker info >/dev/null 2>&1)")
        barra(1.0, "Docker pronto")
        return ok
    print(c("Docker não ficou disponível — siga as instruções de instalação "
            "e rode novamente.", "vermelho"))
    return False


def _dir_docker():
    """Returns the absolute path of `assets/docker`."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets", "docker")


def _compose_cmd():
    """Returns the available docker compose command (plugin v2 or v1) or None."""
    if shutil.which("docker"):
        try:
            r = subprocess.run(["docker", "compose", "version"],
                               capture_output=True, timeout=10)
            if r.returncode == 0:
                return ["docker", "compose"]
        except Exception:
            pass
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return None


def instalar_docker_compose():
    """Installs the Docker Compose plugin when missing (best-effort, sudo)."""
    if _compose_cmd():
        return True
    so = platform.system()
    print(c("Docker Compose ausente — instalando...", "amarelo", True))
    if so == "Linux":
        if shutil.which("apt-get"):
            _cmd("sudo apt-get update && "
                 "sudo apt-get install -y docker-compose-plugin "
                 "docker-compose-v2 || sudo apt-get install -y docker-compose")
        elif shutil.which("dnf"):
            _cmd("sudo dnf install -y docker-compose-plugin")
        elif shutil.which("yum"):
            _cmd("sudo yum install -y docker-compose-plugin")
        else:
            print(c("Instale o Docker Compose manualmente: "
                    "https://docs.docker.com/compose/install/", "amarelo"))
            return False
    elif so == "Darwin":
        _cmd("brew install docker-compose")
    elif so == "Windows":
        _cmd("winget install -e --id Docker.DockerDesktop")  # Desktop inclui compose
    return _compose_cmd() is not None


def _porta_livre(porta):
    """True if the TCP port is free on localhost (not in use)."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", int(porta))) != 0
    except Exception:
        return False  # erro/porta inválida → assume ocupada (nunca "livre")


def _verificar_postgres(dsn):
    """True if the PostgreSQL DSN is reachable (psycopg2 connect).

    Remove o sufixo `+psycopg2` do esquema (SQLAlchemy) porque o psycopg2
    só entende `postgresql://` — era a causa de nunca confirmar a conexão."""
    try:
        import psycopg2
        d = (dsn or "").replace("postgresql+psycopg2://", "postgresql://")
        conn = psycopg2.connect(d)
        conn.close()
        return True
    except Exception:
        return False


def _servicos_otel_online(porta_grafana=3000):
    """True if the Grafana health endpoint answers (stack OTel online)."""
    try:
        import urllib.request
        r = urllib.request.urlopen(
            f"http://localhost:{porta_grafana}/api/health", timeout=3)  # nosec B310 — esquema http:// literal para localhost; nunca file://
        return r.status == 200
    except Exception:
        return False


def _terminal_disponivel():
    """Returns a command template that opens a new terminal running `{cmd}`
    (Linux: gnome-terminal (sintaxe `-- bash -c`), konsole/xfce4-terminal/
    xterm; Win: PowerShell; Mac: Terminal.app)."""
    so = platform.system()
    if so == "Linux":
        if shutil.which("gnome-terminal"):
            return "gnome-terminal -- bash -c '{cmd}; exec bash'"
        for t, tmpl in {
            "konsole": "konsole -e bash -c '{cmd}; exec bash'",
            "xfce4-terminal": "xfce4-terminal -e bash -c '{cmd}; exec bash'",
            "x-terminal-emulator": "x-terminal-emulator -e bash -c '{cmd}; exec bash'",
            "xterm": "xterm -e bash -c '{cmd}; exec bash'",
        }.items():
            if shutil.which(t):
                return tmpl
    elif so == "Darwin":
        return ('osascript -e \'tell app "Terminal" '
                'to do script "{cmd}"\'')
    elif so == "Windows":
        return 'start powershell -NoExit -Command "{cmd}"'
    return None


def abrir_terminal(comando):
    """Opens a new terminal window running `comando` (best-effort)."""
    t = _terminal_disponivel()
    if not t:
        return False
    _cmd(t.format(cmd=comando))
    return True


def _status_docker(prefixo=""):
    """Prints the running docker containers (live status during setup)."""
    if not docker_instalado():
        return 0
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}: {{.Status}}"],
            capture_output=True, text=True, timeout=10)
        linhas = [l for l in r.stdout.splitlines() if l.strip()]
        if linhas:
            print(c("  Containers Docker:", "ciano"))
            for l in linhas:
                visivel = (not prefixo) or (prefixo in l)
                print(("   " + c(l, "verde")) if visivel else "   " + l)
        return len(linhas)
    except Exception:
        return 0


def _wsl_distros():
    """Lists installed WSL distributions (Windows)."""
    try:
        r = subprocess.run(["wsl", "--list", "--quiet"],
                           capture_output=True, text=True, timeout=20)
        return [l.strip() for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        return []


def _validar_senha(senha):
    """True if the password has no shell metacharacters (safe on stdin)."""
    return not re.search(r"[;|&\n$'\"\\ ]", str(senha or ""))


def configurar_docker_windows(cfg=None):
    """Guides Windows: installs WSL (light distro preferred), asks the WSL
    user/password and installs Docker Desktop for the containers.

    Segurança: a distro é revalidada contra a whitelist {debian, ubuntu,
    alpine}; o usuário segue o regex Linux `^[a-z_][a-z0-9_-]{0,31}$`; a senha
    é validada contra metacharacteres de shell e NUNCA vai no argv do comando
    — é enviada por stdin ao `chpasswd` e mascarada no print do `_cmd`."""
    print(c("Configuração do Docker no Windows...", "amarelo", True))
    distros = _wsl_distros()
    if not distros:
        print(c("WSL não configurado — instalando uma distro leve dedicada...",
                "amarelo"))
        escolha = perguntar(
            "Distro WSL dedicada [debian/ubuntu/alpine] (padrão debian — "
            "leve)", "debian", validos={"debian", "ubuntu", "alpine"})
        if escolha not in {"debian", "ubuntu", "alpine"}:
            escolha = "debian"  # revalidação da whitelist antes do comando
        _cmd(["wsl", "--install", "-d", escolha])
    distros = _wsl_distros()
    if distros:
        distro = distros[0]
        usuario = "skyrover"
        while True:
            usuario = perguntar(f"Usuário do WSL ({distro}) (padrão skyrover)",
                                "skyrover")
            if re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", usuario):
                break
            print(c("Usuário inválido — use minúsculas, números, '_' ou '-' "
                    "(máx. 32). Tente novamente.", "amarelo"))
        senha = "skyrover"
        while True:
            senha = perguntar(f"Senha do WSL ({distro}) (padrão skyrover)",
                              "skyrover")
            if _validar_senha(senha):
                break
            print(c("Senha inválida — evite espaços e caracteres de shell "
                    "(; | & $ ' \" \\). Tente novamente.", "amarelo"))
        # cria o usuário na distro e o define como padrão; a senha vai por
        # stdin (nunca interpolada no argv nem no shell local)
        script_usuario = (
            f"useradd -m -s /bin/bash {usuario} && "
            f"echo '{usuario} ALL=(ALL) NOPASSWD:ALL' >> "
            f"/etc/sudoers.d/{usuario} && "
            "read -r linha && echo \"$linha\" | chpasswd")
        if not _cmd(["wsl", "-d", distro, "-u", "root", "--", "sh", "-c",
                     script_usuario], entrada=f"{usuario}:{senha}\n"):
            print(c("  Falha ao criar o usuário WSL — verifique manualmente "
                    "(WSL integrado ao Docker Desktop).", "vermelho"))
        _cmd(["wsl", "--set-default-user", distro, usuario])
    # Docker Desktop (inclui o engine + compose)
    if not docker_instalado():
        print(c("Instalando o Docker Desktop...", "amarelo"))
        _cmd("winget install -e --id Docker.DockerDesktop")
    print(c("Abra o Docker Desktop e ative a integração com o WSL "
            "(Settings → Resources → WSL integration) antes de continuar.",
            "amarelo"))


def _garantir_docker_compose():
    """Ensures Docker + Docker Compose are available (installing if needed)."""
    if not docker_instalado():
        if not instalar_docker():
            return None
    if _compose_cmd():
        return _compose_cmd()
    if platform.system() == "Windows":
        configurar_docker_windows()
    else:
        instalar_docker_compose()
    return _compose_cmd()


def _pre_pull(imagens):
    """Pulls Docker images explicitly so failures (ex.: no internet/air-gapped)
    are visible and clearly reported before `up -d`."""
    for img in imagens:
        print(c(f"  Baixando imagem {img}...", "amarelo"))
        ok = _cmd(["docker", "pull", img])
        if not ok:
            print(c(f"    Falha ao baixar {img}. Sem acesso à internet? "
                    "Carregue a imagem offline (docker load -i imagem.tar) "
                    "ou use imagens já presentes localmente.", "vermelho"))


# =============================================================================
# Espera adaptativa de subida de containers (race do pull no terminal)
# =============================================================================
# O assistente abre um TERMINAL separado que faz `pull && up -d && logs -f`.
# Enquanto o `docker pull` da imagem roda na outra janela (1–5 min na 1ª vez),
# o container nem existe — loops curtos e cegos (30×1 s) reportavam "porta não
# subiu" antes mesmo de o download terminar. Os helpers abaixo distinguem
# "pull em andamento", "container iniciando" e "pull falhou" para a espera
# ser generosa, mas com mensagens claras de falha (sem travar o assistente).

_ultimo_motivo = None  # motivo da última subida (para _executar_e_persistir)

_MOTIVOS = {
    "online": "serviço online",
    "timeout": "tempo limite esgotado — pull ainda em andamento?",
    "pull_falhou": "pull da imagem falhou (sem acesso à internet?)",
    "container_iniciando": "container iniciou mas não ficou acessível",
    "porta_ocupada": "porta já em uso",
    "sem_compose": "arquivo docker-compose ausente",
    "sem_docker_compose": "Docker Compose indisponível",
}


def _motivo_legivel(motivo):
    """Traduz o motivo da falha de subida do serviço para PT-BR claro."""
    return _MOTIVOS.get(motivo or "timeout", "falha desconhecida")


def _container_existe(nome):
    """True se um container com `nome` existe (parado OU rodando).

    Usa `docker ps -a` (inclui parados): o container só aparece DEPOIS que o
    pull terminou e o `up -d` o criou — é o indicador de progresso do pull."""
    if not docker_instalado():
        return False
    try:
        r = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10)
        return nome in (r.stdout or "").split()
    except Exception:
        return False


def _imagem_baixada(imagem):
    """True se a imagem Docker (ou o repositório dela) já está local.

    `postgres:16-alpine` casa exato; `grafana/grafana` casa o prefixo de
    `grafana/grafana:latest` (imagens `:latest` do compose OTel)."""
    if not docker_instalado() or not imagem:
        return False
    try:
        r = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
            capture_output=True, text=True, timeout=10)
        for linha in (r.stdout or "").split():
            if linha == imagem or linha.startswith(imagem + ":"):
                return True
    except Exception:
        pass
    return False


def _pull_em_andamento():
    """Best-effort: True se um `docker pull` ainda está rodando.

    O pull roda no terminal separado (ou no console principal no fallback);
    o `pgrep -f` detecta o processo. O pgrep só existe em Linux/macOS — em
    outros SO (ou em falha do pgrep) assume True (em andamento) para nunca
    marcar "pull falhou" por engano."""
    try:
        r = subprocess.run(["pgrep", "-f", r"docker.*pull"],
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return True


def _aguardar_container(container, timeout, verificar, imagem=None,
                        rotulo="serviço", passo=1.0):
    """Espera o container aparecer (pull em andamento) e ficar online.

    Espera ADAPTATIVA para serviços que sobem via `docker compose` num
    TERMINAL separado. Diferencia os estados:
      - pull em andamento: container NÃO existe no `docker ps -a` e um
        `docker pull` ainda roda → continua esperando até `timeout` (não
        desiste em 30 s como o loop antigo);
      - container iniciando: container JÁ existe (pull concluído, `up -d`
        rodou) mas o serviço ainda não responde → espera até `timeout`;
      - pull falhou: o pull parou sem a imagem/container chegarem (ex.: sem
        internet) → encerra ANTES do timeout com mensagem clara;
      - timeout: nada ficou online dentro do prazo generoso.

    Retorna True quando `verificar()` responde; senão False. O motivo da
    falha fica em `_ultimo_motivo` para o `_executar_e_persistir` avisar o
    usuário com informação útil (pull em andamento × pull falhou)."""
    global _ultimo_motivo
    _ultimo_motivo = None
    inicio = time.monotonic()
    ja_viu_pull = False
    while True:
        if verificar():
            barra(1.0, f"{rotulo} online")
            fim_barra()
            _ultimo_motivo = "online"
            return True
        decorrido = time.monotonic() - inicio
        if decorrido >= timeout:
            break
        pull_roda = _pull_em_andamento()
        if pull_roda:
            ja_viu_pull = True
        if _container_existe(container):
            estado = f"aguardando {rotulo} online (container presente)"
        elif pull_roda:
            estado = f"aguardando container ({rotulo}: pull em andamento)"
        elif not _imagem_baixada(imagem):
            if ja_viu_pull or decorrido >= 10:
                # O pull já rodou e parou (ou passou 10 s sem nenhum sinal) e
                # nada chegou → falha clara de rede/offline.
                barra(1.0, "pull falhou")
                fim_barra()
                print(c(f"  Pull da imagem {imagem or container} falhou — sem "
                        "acesso à internet? Carregue a imagem offline "
                        "(docker load -i imagem.tar).", "vermelho"))
                _ultimo_motivo = "pull_falhou"
                return False
            estado = "aguardando container (pull iniciando...)"
        else:
            estado = f"aguardando container ({rotulo}: iniciando...)"
        barra(0.5 + 0.5 * (decorrido / timeout), f"{rotulo}: {estado}")
        time.sleep(passo)
    fim_barra()
    if _container_existe(container):
        _ultimo_motivo = "container_iniciando"
    elif _pull_em_andamento():
        _ultimo_motivo = "timeout"  # pull ainda rodando além do prazo
    elif not _imagem_baixada(imagem):
        _ultimo_motivo = "pull_falhou"
    else:
        _ultimo_motivo = "timeout"
    return False


def iniciar_postgres(cfg):
    """Starts PostgreSQL (or REUSES an already-running container) and waits
    until it is online. O pull + up + logs rodam num TERMINAL próprio.

    REUSO ANTES DE QUALQUER PULL: primeiro o container `skyrover_postgres`
    ativo (`_postgres_docker_ativo`); depois o scan das portas ocupadas
    (`_detectar_postgres_rodando`) — se um PostgreSQL do sistema JÁ está
    rodando em alguma porta (ex.: 5432), apenas CONECTA (sem baixar/subir).
    Caso contrário abre um terminal que faz `pull && up -d && docker logs -f
    skyrover_postgres` (o usuário vê o pull e depois os logs).

    A espera é ADAPTATIVA: enquanto o pull da `postgres:16-alpine` roda no
    terminal separado (1–5 min na primeira vez), o container nem existe — o
    loop antigo (30×1 s) desistia antes de o download terminar. Aqui o
    `_aguardar_container` só reporta falha quando o container existir e ainda
    não conectar, após ~180 s, ou quando o pull claramente falhou (rede?)."""
    global _ultimo_motivo
    compose = os.path.join(_dir_docker(), "postgres", "docker-compose.yml")
    if not os.path.exists(compose):
        _ultimo_motivo = "sem_compose"
        return False
    # REUSO 1: container já ativo → apenas conecta
    porta_ativa = _postgres_docker_ativo()
    if porta_ativa is not None:
        cfg["porta_postgres"] = porta_ativa
        cfg["postgres_url"] = (
            f"postgresql+psycopg2://skyrover:skyrover"
            f"@localhost:{porta_ativa}/skyrover")
        print(c(f"  Container skyrover_postgres já ativo na porta {porta_ativa} "
                "— apenas conectando.", "verde"))
        ok = _verificar_postgres(cfg["postgres_url"])
        if ok:
            print(c("  PostgreSQL acessível (reuso de container).", "verde"))
            _ultimo_motivo = "online"
        else:
            _ultimo_motivo = "container_iniciando"
        return ok
    # REUSO 2: PostgreSQL do sistema JÁ rodando em alguma porta ocupada —
    # conecta ANTES de qualquer pull/up (nada de baixar imagem desnecessário).
    porta_detectada = _detectar_postgres_rodando()
    if porta_detectada is not None:
        cfg["porta_postgres"] = porta_detectada
        cfg["postgres_url"] = (
            f"postgresql+psycopg2://skyrover:skyrover"
            f"@localhost:{porta_detectada}/skyrover")
        print(c(f"  Serviço PostgreSQL já ativo na porta {porta_detectada} — "
                "apenas conectando (sem download).", "verde"))
        ok = _verificar_postgres(cfg["postgres_url"])
        if ok:
            print(c("  PostgreSQL acessível (reuso de serviço ativo).", "verde"))
            _ultimo_motivo = "online"
        else:
            _ultimo_motivo = "container_iniciando"
        return ok
    if not _porta_livre(cfg.get("porta_postgres", 5432)):
        _ultimo_motivo = "porta_ocupada"
        return False  # porta ocupada — o wizard pede outra porta
    cmd = _garantir_docker_compose()
    if not cmd:
        _ultimo_motivo = "sem_docker_compose"
        return False
    # `down` primeiro: recriação limpa quando a porta mudou (evita
    # "'ContainerConfig'" do docker-compose v1 ao reescrever o compose).
    _cmd(cmd + ["-f", compose, "down"])
    dir_pg = os.path.join(_dir_docker(), "postgres")
    comando_terminal = " && ".join([
        f"cd {dir_pg}",
        f"{' '.join(cmd)} -f docker-compose.yml pull",
        f"{' '.join(cmd)} -f docker-compose.yml up -d",
        "docker logs -f skyrover_postgres",
    ])
    terminal_aberto = abrir_terminal(comando_terminal)
    if not terminal_aberto:
        # Sem terminal disponível: pull + up no console principal.
        _pre_pull(["postgres:16-alpine"])
        _cmd(cmd + ["-f", compose, "up", "-d"])
        abrir_terminal(" ".join(cmd + ["-f", compose, "ps"]))
    porta = cfg.get("porta_postgres", 5432)
    dsn = cfg.get("postgres_url", "")
    # Pull no terminal separado → ~180 s generosos (download da 1ª vez leva
    # minutos); no fallback (console) o pull já terminou → mantém ~30 s.
    timeout = 180 if terminal_aberto else 30
    ok = _aguardar_container(
        "skyrover_postgres", timeout=timeout,
        verificar=lambda: _verificar_postgres(dsn),
        imagem="postgres:16-alpine",
        rotulo=f"PostgreSQL (porta {porta})",
        passo=1.0)
    if not ok:
        print(c(f"  PostgreSQL não ficou online na porta {porta} — "
                f"{_motivo_legivel(_ultimo_motivo)}.", "vermelho"))
    return ok


def _garantir_sdk_otel():
    """Garante o SDK OpenTelemetry instalado (instala via pip se ausente).

    Se `import opentelemetry` (api/sdk/exporter OTLP gRPC) falhar, instala os
    pacotes no interpretador atual e devolve True/False (fail-soft)."""
    try:
        import opentelemetry  # noqa: F401
        import opentelemetry.sdk  # noqa: F401
        import opentelemetry.exporter.otlp.proto.grpc  # noqa: F401
        return True
    except Exception:
        pass
    return _cmd([sys.executable, "-m", "pip", "install",
                 "opentelemetry-api", "opentelemetry-sdk",
                 "opentelemetry-exporter-otlp-proto-grpc"])


def iniciar_stack_otel(cfg=None):
    """Starts the OTel LGTM stack (or REUSES a running one), opens a terminal
    with the pull + logs and waits until Grafana is online.

    REUSO ANTES DE QUALQUER PULL: primeiro a stack por container
    (`_otel_docker_ativo`); depois a detecção nas portas ocupadas
    (`_detectar_otel_rodando`). O reuso por scan SÓ acontece quando a stack
    está COMPLETA (grafana+loki+tempo+mimir+collector) — se só parte existe
    (ex.: só grafana), avisa e segue para o pull dos serviços faltantes (a
    espera adaptativa lida com a duração do pull).

    A espera é ADAPTATIVA (como no Postgres): o pull das 5 imagens
    (grafana/loki/tempo/mimir + collector) pode levar vários minutos na
    primeira vez — espera o container `skyrover-grafana` aparecer (pull em
    andamento) e só falha no timeout generoso (~240 s) ou se o pull falhou."""
    global _ultimo_motivo
    if not _garantir_sdk_otel():
        print(c("  SDK OpenTelemetry indisponível — seguindo sem telemetria "
                "(o sistema roda normalmente).", "amarelo"))
        return False
    porta_grafana = (cfg or {}).get("porta_grafana", 3000)
    if _otel_docker_ativo():
        print(c("  Stack OpenTelemetry já ativa — apenas verificando o "
                "Grafana.", "verde"))
        ok = _servicos_otel_online(porta_grafana)
        if ok:
            print(c("  Grafana acessível (reuso de stack).", "verde"))
        return ok
    # REUSO por scan: serviços OTel já ativos nas portas ocupadas (sem pull).
    achados = _detectar_otel_rodando()
    if achados:
        faltantes = [s for s in _SERVICOS_OTEL if s not in achados]
        if not faltantes:
            # Stack COMPLETA → apenas conecta (verifica o Grafana e retorna).
            porta_gf = achados.get("grafana", porta_grafana)
            if cfg is not None:
                cfg["porta_grafana"] = porta_gf
            print(c(f"  Stack OpenTelemetry já ativa nas portas "
                    f"{_formatar_achados_otel(achados)} — apenas conectando "
                    "(sem download).", "verde"))
            ok = _servicos_otel_online(porta_gf)
            if ok:
                print(c("  Grafana acessível (reuso de stack ativa).", "verde"))
            _ultimo_motivo = "online" if ok else "container_iniciando"
            return ok
        # Stack INCOMPLETA → avisa e segue para o pull dos serviços faltantes.
        nomes_faltantes = ", ".join(
            _NOME_LEGIVEL_OTEL.get(s, s) for s in faltantes)
        print(c(f"  Grafana encontrado na porta {achados.get('grafana', '?')}, "
                f"mas a stack OTel está incompleta (faltam {nomes_faltantes}) "
                "— será feito o pull dos serviços faltantes.", "amarelo"))
    compose = os.path.join(_dir_docker(), "compose.yml")
    if not os.path.exists(compose):
        return False
    cmd = _garantir_docker_compose()
    if not cmd:
        return False
    dir_otel = _dir_docker()
    comando_terminal = " && ".join([
        f"cd {dir_otel}",
        f"{' '.join(cmd)} -f compose.yml pull",
        f"{' '.join(cmd)} -f compose.yml up -d",
        "docker logs -f skyrover-otel-collector",
    ])
    terminal_aberto = abrir_terminal(comando_terminal)
    if not terminal_aberto:
        _pre_pull(["grafana/grafana", "grafana/loki", "grafana/tempo",
                   "grafana/mimir", "otel/opentelemetry-collector-contrib"])
        _cmd(cmd + ["-f", compose, "up", "-d"])
        abrir_terminal(" ".join(cmd + ["-f", compose, "ps"]))
    # Pull no terminal separado → ~240 s generosos; fallback (console) o pull
    # já terminou → mantém ~80 s (40 × 2 s) como antes.
    timeout = 240 if terminal_aberto else 80
    ok = _aguardar_container(
        "skyrover-grafana", timeout=timeout,
        verificar=lambda: _servicos_otel_online(porta_grafana),
        imagem="grafana/grafana",
        rotulo=f"Stack OTel (Grafana porta {porta_grafana})",
        passo=2.0)
    if not ok:
        print(c(f"  Stack OpenTelemetry não ficou online — "
                f"{_motivo_legivel(_ultimo_motivo)}.", "vermelho"))
    return ok


# =============================================================================
# Assistente principal
# =============================================================================

def _escolha_1_enter(texto, rotulo_padrao, rotulo_1, padrao=""):
    """Pergunta binária estrita: '1' = {rotulo_1} | ENTER/0 = {rotulo_padrao}.

    SOMENTE '1' (ativa/configura) ou ENTER/0 (não) são aceitos — qualquer
    outra tecla (ex.: 's', 'sim', 'nao', 'postgres', 'x') REPETE a pergunta
    com aviso até uma entrada válida. Retorna "1" ou "". EOFError/
    KeyboardInterrupt devolvem `padrao` (fail-soft, sem loop infinito)."""
    aviso = (f"Opção inválida — digite 1 para {rotulo_1} ou apenas ENTER "
             f"para {rotulo_padrao}.")
    while True:
        try:
            resp = input(
                c(f"{texto} [1 = {rotulo_1} | ENTER/0 = {rotulo_padrao}]: ",
                  "ciano")).strip()
        except (EOFError, KeyboardInterrupt):
            return padrao
        if resp in ("", "0"):
            return ""
        if resp == "1":
            return "1"
        print(c(aviso, "amarelo"))


def _sim_nao(texto, padrao=False):
    """Pergunta sim/não com o MÍNIMO de teclas: '1' = ativa, ENTER/0 = não.

    SOMENTE '1' (ativa) ou ENTER/0 (não ativa) são aceitos — 'sim'/'s'/
    'nao'/'n' NÃO são aceitos e repetem a pergunta até uma entrada válida.
    Padrão `nao` — o usuário só digita 1 (e Enter) quando quer ativar."""
    return _escolha_1_enter(texto, "não ativar", "ativar",
                            padrao=("1" if padrao else "")) == "1"


def _confirmar_fallback_sqlite(motivo):
    """Avisa da falha do Postgres e pergunta se usa SQLite como fallback.

    No modo de ativação NÃO rebaixa para SQLite em silêncio: imprime o
    motivo em vermelho e retorna `True` só se o usuário confirmar
    explicitamente (1 = sim; ENTER/0 mantém o backend escolhido)."""
    print(c(f"  {motivo}", "vermelho", True))
    return _sim_nao("  Usar SQLite como fallback?")


# =============================================================================
# Scripts utilitários acionados por flag — `--depencias` / `--popular`
# =============================================================================
# Layout `src/` (AGENTS.md §2.2): `__file__` é `<raiz>/src/mod_skyrover/
# ativacao.py`, então dois `dirname` dão `src/` (onde ficam os `mod_*`) e
# três dão a RAIZ (onde mora `instalar_externos.py`, o companion do Poetry
# — AGENTS.md §6). Nada aqui é derivado de `__file__` "do jeito antigo":
# com o código em `src/`, um `dirname` a menos aponta para a pasta errada
# e o script simplesmente não existe.
DIR_SRC_ATIVACAO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_PROJETO_ATIVACAO = os.path.dirname(DIR_SRC_ATIVACAO)

SCRIPT_DEPENDENCIAS = os.path.join(DIR_PROJETO_ATIVACAO, "instalar_externos.py")
SCRIPT_COLETA_KBP = os.path.join(
    DIR_SRC_ATIVACAO, "mod_gest_cad_usuario", "coleta_kbp.py")

# Download do Chromium (~150 MB) em link lento passa de 10 min; o prazo é
# generoso DE PROPÓSITO — matar a instalação no meio deixa o Playwright com
# navegador pela metade, que é pior do que não ter.
TEMPO_LIMITE_DEPENDENCIAS = 3600

# O coletor é lento de propósito: uma ficha por vez, com pausa sorteada
# entre elas (`_esperar`, faixa 2–6 s no `fonte_folha.json`/`tb_config`).
ARQUIVO_LOG_COLETA = "coleta_kbp.log"


def _ambiente_com_src():
    """Devolve `os.environ` com `src/` no PYTHONPATH.

    O coletor importa `mod_skyrover.bd_conexao` para ler a `tb_config`
    central — é de lá que saem a URL do portal e a faixa de ritmo, não do
    `fonte_folha.json` (decisão de 04/10/2026). Rodado como SUBPROCESS ele
    não herda o `sys.path` que o servidor monta no boot, e sem esta entrada
    a leitura da `tb_config` degrada em silêncio para o arquivo de
    configuração — que é o modo de o sistema "rodar" e pegar o ritmo errado.
    """
    env = dict(os.environ)
    partes = [p for p in (env.get("PYTHONPATH") or "").split(os.pathsep) if p]
    if DIR_SRC_ATIVACAO not in partes:
        partes.insert(0, DIR_SRC_ATIVACAO)
    env["PYTHONPATH"] = os.pathsep.join(partes)
    return env


def _pasta_logs():
    """`logs/` do projeto (observabilidade), com queda para a raiz."""
    try:
        from mod_skyrover import observabilidade
        pasta = getattr(observabilidade, "LOG_DIR", "")
        if pasta and os.path.isdir(pasta):
            return pasta
    except Exception:
        pass
    return os.path.join(DIR_PROJETO_ATIVACAO, "logs")


def instalar_dependencias_externas(caminho=None):
    """Roda `instalar_externos.py` — o que o Poetry NÃO resolve.

    Os binários do Playwright (Chromium) e os binários Go `gitleaks`/`k6`
    não são wheels: viram um passo de instalação, não uma dependência. O
    script é o companion do Poetry (AGENTS.md §6) e roda AQUI, ANTES do
    boot — quem passou `--depencias` quer as dependências prontas, e subir o
    servidor antes só faria os testes E2E falharem por navegador ausente.

    Bloqueante de propósito: roda como SUBPROCESSO (nada trava o event-loop
    enquanto o Chromium baixa), com prazo generoso. Devolve True/False — a
    falha NÃO derruba o boot, quem chamou continua subindo sem os extras."""
    caminho = caminho or SCRIPT_DEPENDENCIAS
    if not os.path.isfile(caminho):
        print(c(f"[setup] installer de dependências não encontrado: {caminho}",
                "vermelho"))
        return False
    comando = [sys.executable, caminho]
    print(c("\n===== DEPENDÊNCIAS EXTERNAS (Poetry não resolve) =====",
            "ciano", True))
    print(c(f"$ {' '.join(comando)}", "azul"))
    try:
        # `sys.executable`, nunca `python`: o ambiente é in-project
        # (AGENTS.md §6) e `python` puro pode apontar para outro Python.
        r = subprocess.run(comando, timeout=TEMPO_LIMITE_DEPENDENCIAS,
                           env=_ambiente_com_src())
        ok = r.returncode == 0
    except subprocess.TimeoutExpired:
        print(c(f"[setup] instalação excedeu "
                f"{TEMPO_LIMITE_DEPENDENCIAS // 60} min e foi interrompida — "
                "o Playwright pode ter ficado com navegador incompleto.",
                "vermelho"))
        return False
    except Exception as e:
        print(c(f"[setup] falha ao instalar dependências externas: {e}",
                "vermelho"))
        return False
    if ok:
        print(c("Dependências externas prontas — continuando o boot.", "verde"))
    else:
        print(c("Instalação das dependências externas terminou com erro — "
                "o boot continua (testes E2E podem não ter navegador).",
                "amarelo"))
    return ok


def liberar_firewall(porta=8080):
    """Cria a regra de entrada do Firewall do Windows para o site (rede local).

    EN: Creates the Windows Firewall inbound rule for the site port (LAN
    only). Requires an elevated terminal; without it, warns and returns
    False. Never raises — failure keeps the boot going without the rule.

    PT-BR: Sem regra de entrada, o servidor responde em `localhost` mas a
    máquina vizinha não alcança a porta: o Firewall barra. Esta função cria
    (via `netsh`, idempotente — apaga a regra antiga de mesmo nome antes)
    `Skyrover Modular (site <porta>)`: TCP na porta do site, SÓ nos perfis
    privada e doméstica/corporativa (`profile=private,domain`, nunca
    pública) e SÓ para o interpretador que está rodando o servidor
    (`sys.executable`, o Python do venv do Poetry). Fora do Windows, avisa
    e devolve False. Devolve True quando a regra está ativa.
    """
    try:
        porta = int(porta) or 8080
    except Exception:
        porta = 8080
    nome = f"Skyrover Modular (site {porta})"
    if os.name != "nt":
        print(f"[firewall] Só Windows: regra '{nome}' não aplicada "
              f"(sistema atual: {os.name}) — o boot segue.", flush=True)
        return False
    try:
        import ctypes
        eh_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        eh_admin = False
    if not eh_admin:
        print("[firewall] Sem privilégio de administrador — feche, abra o "
              "terminal COMO ADMINISTRADOR e rode de novo: "
              "`poetry run python main.py --liberarFirewall`. O boot segue "
              "sem a regra.", flush=True)
        return False
    try:
        bin_python = sys.executable or ""
    except Exception:
        bin_python = ""
    try:
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule",
             f"name={nome}"],
            capture_output=True, text=True, timeout=60)
        comando = ["netsh", "advfirewall", "firewall", "add", "rule",
                   f"name={nome}", "dir=in", "action=allow", "protocol=TCP",
                   f"localport={porta}", "profile=private,domain"]
        if bin_python and os.path.isfile(bin_python):
            comando.append(f"program={bin_python}")
        r = subprocess.run(comando, capture_output=True, text=True,
                           timeout=60)
        if r.returncode == 0:
            print(f"[firewall] Regra '{nome}' ativa: TCP {porta} liberado na "
                  f"rede local (privada/doméstica) para "
                  f"{bin_python or 'todo programa'}.", flush=True)
            return True
        detalhe = (r.stderr or r.stdout or "").strip()
        print(f"[firewall] netsh devolveu {r.returncode}"
              f"{(': ' + detalhe) if detalhe else ''} — o boot segue sem a "
              "regra.", flush=True)
        return False
    except Exception as e:
        print(f"[firewall] Não foi possível criar a regra ({e}) — o boot "
              "segue sem ela.", flush=True)
        return False


def liberar_antivirus(pasta=None):
    """Isenta a pasta do sistema da fiscalização do Antivírus/Defender.

    EN: Adds the hosting folder (e.g. `C:\\skyrover`) to the Defender path
    exclusion list. Requires an elevated terminal; without it, warns and
    returns False. Never raises — failure keeps the boot going.

    PT-BR: O Defender fiscaliza cada leitura/escrita — banco, logs, coleta.
    Com o sistema hospedado em pasta como `C:\\skyrover`, a isenção do
    caminho tira essa fiscalização. `pasta` vazia = a RAIZ onde o sistema
    está hospedado (`DIR_PROJETO_ATIVACAO`). Usa `Add-MpPreference
    -ExclusionPath` (idempotente: repetir não duplica) e confere com
    `Get-MpPreference`. Devolve True com a pasta isenta.
    """
    try:
        pasta = os.path.abspath(pasta or DIR_PROJETO_ATIVACAO)
    except Exception:
        pasta = DIR_PROJETO_ATIVACAO
    if os.name != "nt":
        print(f"[antivirus] Só Windows: pasta '{pasta}' não isenta "
              f"(sistema atual: {os.name}) — o boot segue.", flush=True)
        return False
    try:
        import ctypes
        eh_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        eh_admin = False
    if not eh_admin:
        print("[antivirus] Sem privilégio de administrador — feche, abra o "
              "terminal COMO ADMINISTRADOR e rode de novo: "
              "`poetry run python main.py --liberarAntivirus`. O boot segue "
              "sem a isenção.", flush=True)
        return False
    if not os.path.isdir(pasta):
        print(f"[antivirus] Pasta inexistente: '{pasta}' — nada a isentar.",
              flush=True)
        return False
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"Add-MpPreference -ExclusionPath '{pasta}'"],
            capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            detalhe = (r.stderr or r.stdout or "").strip()
            print(f"[antivirus] Defender devolveu {r.returncode}"
                  f"{(': ' + detalhe) if detalhe else ''} — o boot segue "
                  "sem a isenção.", flush=True)
            return False
        v = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-MpPreference | Select-Object -ExpandProperty ExclusionPath"],
            capture_output=True, text=True, timeout=120)
        isenta = pasta.lower() in (v.stdout or "").lower()
        if isenta:
            print(f"[antivirus] Pasta isenta da fiscalização: '{pasta}'.",
                  flush=True)
        else:
            print(f"[antivirus] Exclusão enviada, mas '{pasta}' não aparece "
                  "na lista do Defender — confira com Get-MpPreference.",
                  flush=True)
        return isenta
    except Exception as e:
        print(f"[antivirus] Não foi possível isentar a pasta ({e}) — o boot "
              "segue sem a isenção.", flush=True)
        return False


def popular_dados_servidores(caminho=None, argumentos=None):
    """Dispara `coleta_kbp.py --atualizar` em SEGUNDO PLANO; devolve o Popen.

    `--atualizar` é o que dá sentido à chamada: sem ele o coletor reaproveita
    o `dados/funcionarios_detalhe.json` já existente e apenas regrava os CSVs
    a partir dele — isto é, não popula nada. Com ele, busca a folha do mês.

    Por que SEGUNDO PLANO e não em primeiro plano: a folha inteira leva
    ~80 min, com pausa sorteada entre fichas (2–6 s) justamente para não
    parecer robô e não martelar o portal. Rodando como subprocess em
    sessão própria ela não escreve no banco (só em `dados/`) e não segura o
    servidor — mas também não pode COMEÇAR antes de o servidor existir: o
    pedido é "primeiro o sistema no ar, depois popula". Por isso esta função
    NÃO decide a hora; quem chama decide (ver `app.on_startup` no `main.py`).

    `start_new_session=True` desliga o processo do grupo do terminal: o
    Ctrl+C que derruba o servidor não leva a coleta junto, que tem o
    `funcionarios_detalhe.parcial.json` para retomar de onde parou."""
    caminho = caminho or SCRIPT_COLETA_KBP
    if argumentos is None:
        argumentos = ("--atualizar",)
    if not os.path.isfile(caminho):
        print(c(f"[popular] coletor não encontrado: {caminho}", "vermelho"))
        return None
    comando = [sys.executable, caminho] + [str(a) for a in argumentos]
    try:
        pasta = _pasta_logs()
        os.makedirs(pasta, exist_ok=True)
        # A saída vai para arquivo em vez de herdar o terminal: são ~80 min
        # de progresso do coletor misturados com o log do servidor, e o que
        # se quer observar é um dos dois por vez (`tail -f`).
        destino = os.path.join(pasta, ARQUIVO_LOG_COLETA)
        saida = open(destino, "a", encoding="utf-8")
    except Exception as e:
        print(c(f"[popular] sem arquivo de log ({e}) — indo para o terminal",
                "amarelo"))
        destino = saida = None
    try:
        proc = subprocess.Popen(
            comando, env=_ambiente_com_src(),
            stdout=saida or subprocess.DEVNULL,
            stderr=subprocess.STDOUT if saida else subprocess.DEVNULL,
            start_new_session=True)
    except Exception as e:
        print(c(f"[popular] falha ao iniciar a coleta: {e}", "vermelho"))
        return None
    finally:
        # O `Popen` duplicou o descritor para o filho; o do pai não é mais
        # usado e ficaria aberto a vida inteira do servidor.
        if saida is not None:
            try:
                saida.close()
            except Exception:
                pass
    print(c(f"[popular] Coleta dos dados dos servidores iniciada em segundo "
            f"plano (PID {proc.pid}) — o sistema segue no ar normalmente.",
            "verde"))
    if destino:
        print(c(f"[popular] Acompanhe em: {destino}", "ciano"))
    return proc


# =============================================================================
# Argumentos de linha de comando (Typer)
# =============================================================================

def config_persistida():
    """Loads the persisted boot config from tb_config (no prompts).

    Carrega a configuração persistida em tb_config (banco_tipo,
    postgres_url, otel_ativo, portas) e completa com os padrões de
    _config_padrao() quando a chave ainda não existe (primeira execução).
    Usado por `python main.py` sem argumentos — sobe direto com o que já
    está configurado, sem perguntas."""
    base = _config_padrao()
    try:
        from mod_skyrover.bd_conexao import get_config as _gc
        # banco
        bt = (_gc("banco_tipo", base["banco_tipo"]) or base["banco_tipo"]).strip().lower()
        base["banco_tipo"] = bt if bt in ("sqlite", "postgres") else "sqlite"
        base["subir_postgres"] = base["banco_tipo"] == "postgres"
        pg_url = (_gc("postgres_url", base["postgres_url"]) or base["postgres_url"]).strip()
        if pg_url:
            base["postgres_url"] = pg_url
            m = re.search(r":(\d+)/", pg_url)
            if m:
                try:
                    base["porta_postgres"] = _porta_valida(m.group(1), base["porta_postgres"])
                except Exception:
                    pass
        # otel — em modo direto nunca tenta OTel; só via --config/--activ-otel
        base["otel_ativo"] = False
        base["subir_postgres"] = False
        # docs (24/10/2026) — LIGADA por padrão neste caminho.
        #
        # Este é o caminho de `python main.py` SEM argumentos: sobe direto com o
        # que está persistido. A documentação AGORA SOBE por padrão (inversão
        # pedida em 24/10/2026). O interruptor `docs_ativo` do banco continua
        # NÃO sendo consultado aqui de propósito: se fosse, um interruptor
        # ligado uma vez passaria a subir o mkdocs em todo boot seguinte sem
        # flag nenhuma — mas agora o padrão é LIGADO, então o comportamento
        # esperado é subir. A flag `--desativ-docs` / `--no-docs` desliga no
        # boot; o interruptor da tela de Configurações continua valendo para
        # o botão "Reconstruir documentação".
        base["docs_ativo"] = True
    except Exception:
        pass
    return base


def _cli_app():
    """Builds the Typer app with the boot options (help em PT-BR).

    `python main.py --help` explica cada chamada. Sem argumentos, sobe
    direto com a configuração persistida. `--config` abre o assistente
    interativo."""
    import typer
    cli = typer.Typer(
        add_completion=False,
        help="Skyrover Modular — inicialização do sistema.\n\n"
             "Sem argumentos, sobe direto com a configuração persistida "
             "(modo padrão). Use --config para abrir o assistente interativo "
             "(ENTER = básico SQLite; 1 + ENTER = configurar) ou passe "
             "--postgres/--otel/--porta* para configurar direto.")

    @cli.callback(invoke_without_command=True)
    def _root(
        # --- configuração (assistente) ---
        config: bool = typer.Option(
            False, "--config", "-c",
            help="Abre o assistente interativo de configuração (otel, "
                 "postgres e portas). Sem a flag, 'python main.py' sobe direto "
                 "no modo padrão com a configuração já persistida."),
        # --- ativação de serviços (docker) — Opção C: prefixo --ativ- ---
        otel: bool = typer.Option(
            False, "--ativ-otel", "--otel", "-o",
            help="Ativa o OpenTelemetry (Grafana+Loki+Tempo+Mimir)."),
        postgres: bool = typer.Option(
            False, "--ativ-postgres", "--ativ-postgress", "--postgres", "-p",
            help="Usa PostgreSQL (sobe o container) em vez do SQLite."),
        docs: bool = typer.Option(
            True, "--ativ-docs", "--docs", "-w",
            help="Sobe a documentação MkDocs (build + servidor). ATIVADA por padrão."),
        desativ_docs: bool = typer.Option(
            False, "--desativ-docs", "--no-docs",
            help="Desativa a documentação MkDocs (não monta nem serve). "
                 "A documentação é ATIVADA por padrão; use esta flag para desligar."),
        # --- portas (agrupadas, em ordem alfabética, prefixo --porta-) ---
        portadocumentacao: int = typer.Option(
            8001, "--porta-docs", "--portadocumentacao", "-d",
            help="Porta da documentação (mkdocs; padrão 8001), separada do site."),
        portapostgres: int = typer.Option(
            5432, "--porta-db", "--portapostgres", "-k",
            help="Porta do PostgreSQL (padrão 5432). A 5432 costuma estar "
                 "ocupada por um Postgres nativo — use outra, ex.: 5444."),
        portasite: int = typer.Option(
            8080, "--porta-site", "--portasite", "-s",
            help="Porta do site/aplicação (padrão 8080)."),
        portatelemetria: int = typer.Option(
            3000, "--porta-grafana", "--portatelemetria", "-t",
            help="Porta do painel Grafana/telemetria (padrão 3000)."),
        # --- utilitários ---
        scan_ports: bool = typer.Option(
            False, "--scan-ports", "-S",
            help="Lista as portas em uso no servidor e o serviço de cada uma "
                 "(segurança/instalação) e encerra."),
        dependencias: bool = typer.Option(
            False, "--depencias", "--dependencias", "-D",
            help="Roda o instalar_externos.py (navegadores do Playwright, "
                 "gitleaks, k6 — o que o Poetry não resolve) e segue para o "
                 "boot. Para emendar: python main.py --depencias --postgres."),
        popular: bool = typer.Option(
            False, "--popular", "--popular-dados", "-b",
            help="Sobe o sistema e, só depois que ele está no ar, roda o "
                 "coleta_kbp.py --atualizar em segundo plano para popular os "
                 "dados dos servidores (ritmo lento e espaçado, sem travar o "
                 "servidor)."),
        liberarfirewall: bool = typer.Option(
            False, "--liberar-firewall", "--liberarFirewall", "-F",
            help="Cria a regra de entrada do Firewall do Windows para a "
                 "porta do site (só rede privada/doméstica, nunca pública). "
                 "Exige terminal COMO ADMINISTRADOR; sem ele, avisa e segue "
                 "o boot. O canônico é --liberar-firewall; --liberarFirewall "
                 "e -F são apelidos."),
        liberarantivirus: bool = typer.Option(
            False, "--liberar-antivirus", "--liberarAntivirus", "-A",
            help="Isenta a pasta onde o sistema está hospedado (ex.: "
                 "C:\\skyrover) da fiscalização do Antivírus/Defender "
                 "(exclusão de caminho). Exige terminal COMO ADMINISTRADOR; "
                 "sem ele, avisa e segue o boot. O canônico é "
                 "--liberar-antivirus; --liberarAntivirus e -A são apelidos."),
        servidorreal: bool = typer.Option(
            False, "--servidor-real", "--servidorReal", "-R",
            help="Expõe o site para toda a rede (bind 0.0.0.0). Sem a flag, "
                 "o servidor escuta só em 127.0.0.1 (este PC)."),
    ):
        """Inicializa a Skyrover Modular."""
        pass

    return cli


def cli_opcoes(args=None):
    """Parses the CLI options with Typer; returns a dict of the values.

    `--help` mostra a explicação de cada chamada e encerra. Valores fora da
    faixa de porta caem no padrão (`_porta_valida`)."""
    import click
    from typer.main import get_command
    args = list(args if args is not None else sys.argv[1:])
    cmd = get_command(_cli_app())
    try:
        ctx = cmd.make_context("main", args)
    except click.exceptions.Exit as e:
        raise SystemExit(getattr(e, "exit_code", 0) or 0)
    except click.ClickException as e:
        e.show()
        raise SystemExit(getattr(e, "exit_code", 1) or 1)
    p = ctx.params
    if bool(p.get("scan_ports", False)):
        from mod_skyrover import port_scanner
        print(port_scanner.resumo_portas())
        raise SystemExit(0)
    return {
        "postgres": bool(p.get("postgres", False)),
        "portapostgres": _porta_valida(p.get("portapostgres", 5432), 5432),
        "otel": bool(p.get("otel", False)),
        "docs": bool(p.get("docs", False)),
        "portatelemetria": _porta_valida(p.get("portatelemetria", 3000), 3000),
        "portasite": _porta_valida(p.get("portasite", 8080), 8080),
        "portadocumentacao": _porta_valida(
            p.get("portadocumentacao", 8001), 8001),
        "config": bool(p.get("config", False)),
        # Flags de utilitário: NÃO entram em `config_do_cli` (que monta o
        # boot), e sim disparam scripts. O `main.py` as retira do dict antes
        # do `config_do_cli(**opts)` — por isso ficam aqui, no mesmo parse.
        "depencias": bool(p.get("dependencias", False)),
        "popular": bool(p.get("popular", False)),
        "liberarfirewall": bool(p.get("liberarfirewall", False)),
        "liberarantivirus": bool(p.get("liberarantivirus", False)),
        "servidorreal": bool(p.get("servidorreal", False)),
        "desativ_docs": bool(p.get("desativ_docs", False)),
    }


def config_do_cli(postgres=False, portapostgres=5432, otel=False, docs=True,
                  portatelemetria=3000, portasite=8080, portadocumentacao=8001,
                  desativ_docs=False):
    """Builds the boot config from the CLI options (skips the wizard).

    Monta a config a partir dos argumentos de linha de comando: `--postgres`,
    `--otel` ativam os serviços; `--portasite` define o site (8080) e
    `--porta-docs` define a porta da documentação (mkdocs, 8001).
    A documentação é ATIVADA por padrão; `--desativ-docs` / `--no-docs` desliga."""
    cfg = _config_padrao()
    cfg["modo"] = "ativacao"
    cfg["banco_tipo"] = "postgres" if postgres else "sqlite"
    cfg["subir_postgres"] = bool(postgres)
    # docs_ativo = True por padrão, a menos que --desativ-docs seja passado
    cfg["docs_ativo"] = bool(docs) and not bool(desativ_docs)
    cfg["porta_postgres"] = _porta_valida(portapostgres, 5432)
    cfg["postgres_url"] = (f"postgresql+psycopg2://skyrover:skyrover"
                           f"@localhost:{cfg['porta_postgres']}/skyrover")
    cfg["otel_ativo"] = bool(otel)
    cfg["porta_grafana"] = _porta_valida(portatelemetria, 3000)
    cfg["porta_site"] = _porta_valida(portasite, 8080)
    cfg["porta_documentacao"] = _porta_valida(portadocumentacao, 8001)
    return cfg


def iniciar(cli_cfg=None):
    """Main entry: shows the banner + initial prompt, returns the config dict.

    ENTER (ou não-TTY) → configuração padrão: SQLite apenas, sem Postgres e
    sem OpenTelemetry (boot simples e autossuficiente). '1' + ENTER → modo de
    ativação. Com `cli_cfg` (argumentos de linha de comando via Typer), sobe
    direto com a configuração informada, sem assistente."""
    if cli_cfg is not None:
        print(c("Configuração via linha de comando — sem assistente.", "ciano", True))
        _executar_e_persistir(cli_cfg)
        return cli_cfg
    banner()
    if not _TTY:
        print(c("Terminal não interativo — usando SQLite (configuração "
                "padrão, sem Postgres/OTel).", "amarelo"))
        return _config_padrao()
    while True:
        try:
            resp = input(c("\nPressione ENTER para entrar no modo BÁSICO — Banco "
                           "SQLite, sem Grafana\n"
                           "Pressione 1 + ENTER para configurar estes itens\n> ",
                           "ciano")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return _config_padrao()
        if resp == "":
            return _config_padrao()
        if resp == "1":
            break
        print(c("Opção inválida — pressione apenas ENTER (básico) ou "
                "1 + ENTER (configurar).", "amarelo"))

    print(c("\n===== MODO DE ATIVAÇÃO / CONFIGURAÇÃO =====", "ciano", True))
    cfg = _config_padrao()
    cfg["modo"] = "ativacao"
    print(c("Tudo será instalado e configurado automaticamente (Docker, "
            "PostgreSQL, OpenTelemetry).", "verde"))
    print(c("Responda as perguntas ou pressione ENTER para o padrão.", "verde"))

    # 1) Banco de dados — ENTER = SQLite (serviços desativados) | 1 = PostgreSQL
    bt = _escolha_1_enter("Banco de dados", "SQLite (básico)", "PostgreSQL")
    if bt == "1":
        cfg["banco_tipo"] = "postgres"
        # 2) Serviços — padrão ATIVO no modo PostgreSQL; porta só se ativar
        print(c("\nAtivação dos serviços (independentes entre si):", "ciano", True))
        subir_pg = _sim_nao("Subir/ativar o PostgreSQL (container)?")
        cfg["subir_postgres"] = subir_pg
        if cfg["subir_postgres"]:
            porta_pg_def = 5432
            if not _porta_livre(porta_pg_def):
                print(c(_msg_porta_em_uso(porta_pg_def), "amarelo"))
            resp_porta_pg = perguntar(
                f"  Porta do PostgreSQL (padrão {porta_pg_def})",
                str(porta_pg_def), valido_num=True, faixa=(1, 65535))
            cfg["porta_postgres"] = _porta_valida(resp_porta_pg, porta_pg_def)
            cfg["postgres_url"] = (
                f"postgresql+psycopg2://skyrover:skyrover"
                f"@localhost:{cfg['porta_postgres']}/skyrover")
        subir_otel = _sim_nao(
            "Subir/ativar o OpenTelemetry (Grafana+Loki+Tempo+Mimir)?")
        cfg["otel_ativo"] = subir_otel
        if cfg["otel_ativo"]:
            porta_gf_def = 3000
            if not _porta_livre(porta_gf_def):
                print(c(_msg_porta_em_uso(porta_gf_def), "amarelo"))
            resp_porta_grafana = perguntar(
                f"  Porta do Grafana (painel da telemetria) (padrão "
                f"{porta_gf_def})",
                str(porta_gf_def), valido_num=True, faixa=(1, 65535))
            cfg["porta_grafana"] = _porta_valida(resp_porta_grafana, porta_gf_def)
    else:
        # ENTER (SQLite) — serviços DESATIVADOS (sem perguntas)
        cfg["banco_tipo"] = "sqlite"
        cfg["subir_postgres"] = False
        cfg["otel_ativo"] = False

    # 3) Porta do SITE e da DOCUMENTAÇÃO (mkdocs) — sempre necessárias
    cfg["porta_site"] = _porta_valida(perguntar(
        "Porta do SITE (aplicação) (padrão 8080)", "8080", valido_num=True,
        faixa=(1, 65535)), 8080)
    cfg["porta_documentacao"] = _porta_valida(perguntar(
        "Porta da DOCUMENTAÇÃO (mkdocs) (padrão 8000)", "8000",
        valido_num=True, faixa=(1, 65535)), 8000)

    # 4) Execução — sobe os serviços escolhidos e aguarda ficarem online
    _executar_e_persistir(cfg)
    return cfg


def _executar_e_persistir(cfg):
    """Starts the chosen services, persists the config and prints the summary.

    Sobe PostgreSQL/OpenTelemetry conforme `cfg`, aplica as portas nos
    compose, persiste `banco_tipo`/`postgres_url`/`otel_ativo` e imprime o
    resumo. Usado pelo assistente interativo E pelos argumentos de CLI."""
    try:
        if cfg["subir_postgres"]:
            print(c("\nSubindo PostgreSQL...", "amarelo", True))
            ok_pg = False
            tentativas = 0
            if not _porta_livre(cfg["porta_postgres"]):
                resp = perguntar(
                    f"  A porta {cfg['porta_postgres']} já está em uso "
                    "(Postgres nativo ou outro serviço). Informar OUTRA "
                    "porta, ou ENTER para usar SQLite: ", "", valido_num=True,
                    faixa=(1, 65535))
                if not resp:
                    ok_pg = False
                else:
                    cfg["porta_postgres"] = _porta_valida(
                        resp, cfg["porta_postgres"])
                    cfg["postgres_url"] = (
                        f"postgresql+psycopg2://skyrover:skyrover"
                        f"@localhost:{cfg['porta_postgres']}/skyrover")
                    aplicar_portas(cfg)
            while not ok_pg and tentativas < 5:
                ok_pg = iniciar_postgres(cfg)
                if not ok_pg:
                    resp = perguntar(
                        f"  PostgreSQL não subiu na porta {cfg['porta_postgres']} "
                        f"({_motivo_legivel(_ultimo_motivo)}). Informar OUTRA "
                        "porta, ou ENTER para usar SQLite: ",
                        "", valido_num=True, faixa=(1, 65535))
                    if not resp:
                        break
                    cfg["porta_postgres"] = _porta_valida(
                        resp, cfg["porta_postgres"])
                    cfg["postgres_url"] = (
                        f"postgresql+psycopg2://skyrover:skyrover"
                        f"@localhost:{cfg['porta_postgres']}/skyrover")
                    aplicar_portas(cfg)
                tentativas += 1
            if not ok_pg:
                if _confirmar_fallback_sqlite(
                        "PostgreSQL não ficou acessível "
                        f"({_motivo_legivel(_ultimo_motivo)})."):
                    cfg["banco_tipo"] = "sqlite"
                    cfg["subir_postgres"] = False
                    print(c("  SQLite selecionado como fallback.", "amarelo"))
                else:
                    print(c("  Mantido PostgreSQL — verifique o container "
                            "antes de subir o sistema.", "amarelo"))
        elif cfg["banco_tipo"] == "postgres":
            if not _verificar_postgres(cfg["postgres_url"]):
                if _confirmar_fallback_sqlite(
                        "Sem PostgreSQL acessível (container não iniciado)."):
                    cfg["banco_tipo"] = "sqlite"
                    print(c("  SQLite selecionado como fallback.", "amarelo"))
                else:
                    print(c("  Mantido PostgreSQL — inicie o container antes "
                            "de subir o sistema.", "amarelo"))
        if cfg["otel_ativo"]:
            print(c("\nSubindo OpenTelemetry...", "amarelo", True))
            iniciar_stack_otel(cfg)
    except KeyboardInterrupt:
        print(c("\nInterrompido pelo usuário — continuando com SQLite e sem "
                "telemetria.", "amarelo", True))
        cfg["banco_tipo"] = "sqlite"
        cfg["subir_postgres"] = False
        cfg["otel_ativo"] = False

    # 5) Persiste e aplica portas
    aplicar_banco(cfg)
    aplicar_portas(cfg)
    # Persiste a escolha do OTel — a opção "nao" sobrevive ao restart
    # (o main.py consulta get_config("otel_ativo", "1") == "1").
    try:
        from mod_skyrover.bd_conexao import set_config
        set_config("otel_ativo", "1" if cfg.get("otel_ativo") else "0")
    except Exception as e:
        print(c(f"[setup] aviso ao persistir otel_ativo: {e}", "amarelo"))
    print(c("\nResumo:", "ciano", True))
    print(f"  Banco:            {cfg['banco_tipo']}")
    print(f"  Subir PostgreSQL: {'sim' if cfg.get('subir_postgres') else 'não'}")
    if cfg.get("subir_postgres"):
        print(f"  Porta PostgreSQL: {cfg['porta_postgres']}")
    print(f"  OpenTelemetry:    {'sim' if cfg['otel_ativo'] else 'não'}")
    if cfg.get("otel_ativo"):
        print(f"  Porta Grafana:    {cfg['porta_grafana']}")
    print(f"  Porta do site:    {cfg['porta_site']}")
    print(f"  Porta doc (mkdocs): {cfg.get('porta_documentacao', 8000)}")
    print(c("\nServiços prontos — inicializando os bancos de dados e subindo "
            "o sistema (pode levar alguns minutos na primeira vez)...",
            "amarelo", True))
    return cfg


def progresso_boot(passos):
    """Runs a list of (nome, callable) boot steps with a progress bar."""
    total = len(passos)
    for i, (nome, fn) in enumerate(passos, start=1):
        barra(i / total, nome)
        try:
            fn()
        except Exception as e:
            fim_barra()
            print(c(f"  [boot] falha em '{nome}': {e}", "vermelho"))
    fim_barra()