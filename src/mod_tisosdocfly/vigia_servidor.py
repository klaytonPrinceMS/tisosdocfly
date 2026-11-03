"""EN: Keeps the tisosdocfly server alive. Restarts it if the port goes quiet.

WHY THIS EXISTS (01/10/2026)
    The tisosdocfly is started by a launcher that DETACHES the Python process
    (`start /min cmd /c ...` in `iniciar.bat`), so the launcher's shell can be
    closed and the server keeps running. That is right for a person at the
    machine. But it also means nothing anywhere is responsible for the server
    after it starts: a crash, a forced "End task" in the Task Manager, or a
    logoff that takes the child process with it leaves the tisosdocfly DOWN, and
    the only trace is an absent window.

    This is that missing supervisor. It does not start the tisosdocfly, it only
    watches it.

WHAT IT DOES, AND WHAT IT DELIBERATELY DOES NOT
    Every `INTERVALO_S` it asks a single question: is something listening on
    `localhost:8080`? If yes, it sleeps and asks again. If no, it starts the
    server with the same environment `iniciar.bat` sets, logs it, and goes
    back to watching.

    It does NOT kill anything. A restart loop that also kills "unhealthy"
    processes is a loop that turns one bad probe into an outage. It never
    touches a process it did not start, and it never touches the databases.

USAGE
    Start it once, detached, and leave it:
        .venv/Scripts/python mod_tisosdocfly/vigia_servidor.py

    Stop it: end the process whose command line contains `vigia_servidor.py`.
    (It holds no port and no lock, so stopping it never affects the server.)

PT-BR: Mantem o servidor da tisosdocfly no ar. Reinicia se a porta ficar muda.

Por que existe: `iniciar.bat` solta o processo do Python, o que e correto para
quem esta na maquina — mas significa que, depois que o servidor sobe, nada e
responsavel por ele. Uma queda, um "Finalizar tarefa" ou um logout que leva o
filho junto deixam a tisosdocfly FORA e a unica pista e uma janela que nao existe.
Esta e a supervision que faltava. Nao inicia o servidor: apenas vigia.

O que NAO faz, de proposito: nao mata nada. Um laco que reinicia e tambem
"enferruja" processos e um laco que transforma uma sondagem ruim em queda. Ele
nunca toca em processo que nao iniciou, e nunca toca nos bancos.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # src/ — código
DIR_PROJETO = os.path.dirname(RAIZ)                                  # raiz — logs/, .venv/, main.py
PORTA = int(os.environ.get("TISOSDOCFLY_PORTA", "8080"))
HOST = "127.0.0.1"
INTERVALO_S = float(os.environ.get("TISOSDOCFLY_VIGIA_INTERVALO", "20"))
ARQUIVO_LOG = os.path.join(DIR_PROJETO, "logs", "vigia_servidor.log")

# O mesmo ambiente que o `iniciar.bat` monta: SQLite e sem OTel, para o
# servidor subir sem depender de Docker/Postgres/Grafana. Copiar as variaveis
# aqui e o que faz a supervision NAO mudar o modo de execucao do sistema.
AMBIENTE = dict(os.environ)
AMBIENTE["TISOSDOCFLY_FORCE_SQLITE"] = "1"
AMBIENTE["TISOSDOCFLY_SEM_OTEL"] = "1"

_PYTHON = os.path.join(DIR_PROJETO, ".venv", "Scripts", "python.exe")
if not os.path.exists(_PYTHON):
    _PYTHON = sys.executable


def _log(mensagem: str) -> None:
    """Escreve no log da vigia e no console, com hora."""
    linha = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {mensagem}"
    try:
        print(linha, flush=True)
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(ARQUIVO_LOG), exist_ok=True)
        with open(ARQUIVO_LOG, "a", encoding="utf-8") as fh:
            fh.write(linha + "\n")
    except Exception:
        pass


def servidor_responde() -> bool:
    """Diz se alguém está escutando na porta do servidor.

    Pergunta ao SOCKET, e não a uma URL: o `/login` pode responder 500 com o
    servidor no ar, e uma vigia que tratasse isso como queda reiniciaria o
    servidor a cada erro de tela — que é o oposto de vigiar.
    """
    try:
        with socket.create_connection((HOST, PORTA), timeout=3):
            return True
    except OSError:
        return False


def iniciar_servidor() -> None:
    """Sobe o servidor, destacado, com o mesmo ambiente do `iniciar.bat`."""
    _log(f"porta {PORTA} muda — iniciando o servidor")
    try:
        subprocess.Popen(
            [_PYTHON, "main.py"],
            # `main.py` mora na RAIZ do repositório (AGENTS.md §2.2), e é de lá
            # que ele acha `src/`. Com `cwd=RAIZ` (que agora é `src/`) o
            # servidor subiria sem o próprio arquivo.
            cwd=DIR_PROJETO,
            env=AMBIENTE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # Novo grupo de processos: o servidor nao recebe o Ctrl+C desta
            # vigia, e encerrar a vigia nao leva o servidor junto.
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                          if os.name == "nt" else 0),
            start_new_session=(os.name != "nt"),
        )
        _log("servidor iniciado (pid nao rastreado: e proposital)")
    except Exception as exc:
        _log(f"falha ao iniciar o servidor: {type(exc).__name__}: {exc}")


def main() -> int:
    _log(f"vigia do servidor no ar — porta {HOST}:{PORTA}, checando a cada "
         f"{INTERVALO_S:.0f}s")
    _log("para encerrar a vigia, finalize o processo 'vigia_servidor.py'; "
         "o servidor continua no ar")
    reinicios = 0
    while True:
        if servidor_responde():
            if reinicios:
                _log(f"servidor de volta no ar ({reinicios} reinicio(s) "
                     f"nesta sessao)")
                reinicios = 0
        else:
            reinicios += 1
            iniciar_servidor()
            # Espera o servidor subir antes de sondar de novo, senao o laco
            # dispara varios reinicios seguidos enquanto o boot ainda roda — e
            # o boot desta instalacao pode levar minutos na primeira carga.
            time.sleep(60)
        time.sleep(INTERVALO_S)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        _log("vigia encerrada pelo teclado")
        sys.exit(0)
    except Exception as exc:  # pragma: no cover
        _log(f"vigia morreu: {type(exc).__name__}: {exc}")
        sys.exit(1)