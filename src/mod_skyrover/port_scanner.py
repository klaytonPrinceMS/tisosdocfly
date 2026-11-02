"""Threaded localhost port scanner + service identification.

Scanner de portas locais usando THREADS para agilizar, e identificação dos
serviços que escutam em cada porta. Apenas 127.0.0.1 — varredura LOCAL (a
máquina do instalador), sem atingir redes externas nem legislação de
segurança da informação.

EN: Threaded localhost port scanner with service identification. Local only.
"""
import concurrent.futures
import os
import platform
import re
import socket
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PORTA_MIN = 1
PORTA_MAX = 65535
_THREADS = 250
_TIMEOUT = 0.05


def escanear_portas(host="127.0.0.1", inicio=PORTA_MIN, fim=PORTA_MAX,
                    threads=_THREADS, timeout=_TIMEOUT):
    """Returns sorted LISTEN ports via a threaded socket scan.

    Varre `inicio..fim` em 127.0.0.1 com um thread pool e timeout curto por
    conexão. Uso local apenas (nunca varre redes externas)."""
    abertas = []

    def testar(p):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                return p if s.connect_ex((host, p)) == 0 else None
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, threads)) as ex:
        for r in ex.map(testar, range(max(1, int(inicio)), int(fim) + 1)):
            if r is not None:
                abertas.append(r)
    return sorted(abertas)


def _executar(lista, timeout=8):
    """Runs a command and returns stdout (empty on any failure)."""
    try:
        r = subprocess.run(lista, capture_output=True, text=True, timeout=timeout)
        return r.stdout or ""
    except Exception:
        return ""


def _portas_por_ss_linux():
    """Ports + process names via `ss -ltnp` (instantâneo e autoritativo)."""
    saida = _executar(["ss", "-ltnp"])
    result = {}
    for linha in saida.splitlines():
        m = re.search(r":(\d+)\s", linha)
        if not m:
            continue
        porta = int(m.group(1))
        serv = "desconhecido"
        u = re.search(r'users:\(\("([^"]+)"', linha)
        if u:
            serv = u.group(1)
        result[porta] = serv
    return result


def _portas_por_lsof():
    """Fallback via `lsof -iTCP -sTCP:LISTEN`."""
    saida = _executar(["lsof", "-iTCP", "-sTCP:LISTEN", "-P", "-n"])
    result = {}
    for linha in saida.splitlines():
        cols = linha.split()
        if len(cols) < 9 or cols[0] == "COMMAND":
            continue
        m = re.search(r":(\d+)$", cols[8])
        if m:
            result[int(m.group(1))] = cols[0]
    return result


def _portas_por_netstat_windows():
    """Ports + process names via `netstat -ano` + `tasklist` (Windows)."""
    saida = _executar(["netstat", "-ano", "-p", "tcp"])
    pids = {}
    for linha in saida.splitlines():
        m = re.search(r":(\d+)\s+\S+\s+LISTENING\s+(\d+)", linha)
        if m:
            pids[int(m.group(1))] = m.group(2)
    result = {}
    for porta, pid in pids.items():
        saida_t = _executar(["tasklist", "/FI", f"PID eq {pid}",
                             "/FO", "CSV", "/NH"])
        m = re.search(r'"([^"]+)"', saida_t)
        result[porta] = m.group(1) if m else "desconhecido"
    return result


def _portas_docker():
    """Container ports → container name (docker-proxy roda como root; o `ss`
    sem sudo não mostra, mas o `docker ps` mapeia porta → nome do container)."""
    saida = _executar(["docker", "ps", "--format", "{{.Names}}\t{{.Ports}}"])
    result = {}
    for linha in saida.splitlines():
        partes = linha.split("\t")
        if len(partes) != 2:
            continue
        nome, portas = partes
        for p in re.findall(r"0\.0\.0\.0:(\d+)->", portas) + \
                  re.findall(r"\[::\]:(\d+)->", portas):
            result[int(p)] = nome
    return result


def portas_com_servico():
    """dict {porta: servico} of local LISTEN ports (prioriza ss/netstat).

    Linux: `ss -ltnp` (rápido) enriquecido com `docker ps` (containers como
    root); fallback `lsof`; último recurso o scanner com threads. Windows:
    `netstat -ano` + `tasklist`. Processos de outros usuários sem permissão
    aparecem como "desconhecido"."""
    so = platform.system()
    if so == "Windows":
        res = _portas_por_netstat_windows()
    else:
        res = _portas_por_ss_linux()
        if not res:
            res = _portas_por_lsof()
    for p, nome in _portas_docker().items():
        res[p] = nome
    if res:
        return res
    abertas = escanear_portas()
    return {p: "desconhecido" for p in abertas}


def resumo_portas():
    """PT-BR summary of open ports and services (for the console)."""
    try:
        em_uso = portas_com_servico()
    except Exception:
        em_uso = {}
    if not em_uso:
        return "Nenhuma porta LISTEN detectada (ou sem permissão)."
    linhas = "  " + "\n  ".join(
        f"{p}: {s}" for p, s in sorted(em_uso.items()))
    return f"Portas em uso no servidor:\n{linhas}"


if __name__ == "__main__":
    print(resumo_portas())