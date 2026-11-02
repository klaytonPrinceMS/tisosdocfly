"""Docker and OTel detection module for Skyrover Modular.

This module detects if Docker is available and manages the OTel LGTM stack
(Grafana + Loki + Tempo + Mimir + OpenTelemetry Collector).

Modulo de deteccao Docker e integracao OTel para a Skyrover Modular.

Author: Administrador do sistema
Date: 2026-09-04
"""
import os
import sys
import subprocess
import platform
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# =============================================================================
# Docker Detection
# =============================================================================

def _run_command(cmd: list, timeout: int = 10, cwd: Optional[str] = None) -> Tuple[int, str, str]:
    """Execute a command and return returncode, stdout, stderr.

    Executa em thread separada com deadline rígido: mesmo que o processo
    (ex.: CLI Python do docker-compose v1) deixe um descendente segurando o
    pipe, o boot nunca trava — após `timeout` retorna (-1, "", "timed out").
    """
    import threading

    resultado = {}

    def _executar():
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
            resultado["rc"] = p.returncode
            resultado["out"] = p.stdout
            resultado["err"] = p.stderr
        except FileNotFoundError:
            resultado["rc"] = -1
            resultado["out"] = ""
            resultado["err"] = f"Command not found: {cmd[0]}"
        except Exception as e:
            resultado["rc"] = -1
            resultado["out"] = ""
            resultado["err"] = str(e)

    t = threading.Thread(target=_executar, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return -1, "", "Command timed out"
    return (resultado.get("rc", -1), resultado.get("out", ""),
            resultado.get("err", ""))


def docker_disponivel() -> bool:
    """Check if Docker is available on the system.

    Verifica se o Docker esta disponivel no sistema.
    """
    returncode, stdout, stderr = _run_command(["docker", "info"], timeout=5)
    return returncode == 0


def docker_desktop_ativo() -> bool:
    """Check if Docker Desktop is active (Windows/Mac).

    Verifica se o Docker Desktop esta ativo (Windows/Mac).
    """
    system = platform.system()
    if system in ["Windows", "Darwin"]:
        return docker_disponivel()
    return False


def docker_compose_disponivel() -> bool:
    """Check if Docker Compose is available.

    Verifica se o Docker Compose esta disponivel.
    """
    # Try docker compose (v2)
    returncode, _, _ = _run_command(["docker", "compose", "version"], timeout=5)
    if returncode == 0:
        return True
    
    # Try docker-compose (v1)
    returncode, _, _ = _run_command(["docker-compose", "version"], timeout=5)
    return returncode == 0


def linux_com_docker() -> bool:
    """Check if running on Linux with Docker available.

    Verifica se esta rodando no Linux com Docker disponivel.
    """
    return platform.system() == "Linux" and docker_disponivel()


# =============================================================================
# OTel Stack Management
# =============================================================================

def _get_compose_path() -> Optional[str]:
    """Get the path to docker-compose.yml.

    Retorna o caminho para o docker-compose.yml.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for candidate in (
        os.path.join(base_dir, "assets", "docker", "compose.yml"),
        os.path.join(base_dir, "docker", "compose.yml"),  # legado
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def _compose_command() -> Optional[list]:
    """Get the appropriate docker compose command.

    Retorna o comando apropriado para docker compose.
    """
    # Try docker compose (v2)
    returncode, _, _ = _run_command(["docker", "compose", "version"], timeout=5)
    if returncode == 0:
        return ["docker", "compose"]
    
    # Try docker-compose (v1) — o binário é um app Python e pode demorar
    # alguns segundos; deadline rígido em thread evita travar o boot.
    returncode, _, _ = _run_command(["docker-compose", "version"], timeout=15)
    if returncode == 0:
        return ["docker-compose"]
    
    return None


def otel_stack_rodando() -> bool:
    """Check if the OTel LGTM stack is running.

    Verifica se a stack OTel LGTM esta rodando.
    """
    compose_path = _get_compose_path()
    if not compose_path:
        return False
    
    compose_cmd = _compose_command()
    if not compose_cmd:
        return False
    
    compose_dir = os.path.dirname(compose_path)
    returncode, stdout, _ = _run_command(
        compose_cmd + ["ps", "--format", "json"],
        timeout=10,
        cwd=compose_dir
    )
    
    if returncode == 0 and stdout.strip():
        # Check if any service is running
        import json
        for line in stdout.strip().split("\n"):
            try:
                service = json.loads(line)
                if service.get("State") == "running":
                    return True
            except json.JSONDecodeError:
                continue
    
    # Fallback: consulta `docker ps` diretamente pelos nomes dos serviços
    # (não depende do `docker-compose ps --format json`, que varia por versão).
    _SERVICOS = ["skyrover-grafana", "skyrover-loki", "skyrover-tempo",
                 "skyrover-mimir", "skyrover-otel-collector"]
    for nome in _SERVICOS:
        rc, saida, _ = _run_command(
            ["docker", "ps", "--format", "{{.Names}}", "--filter",
             f"name={nome}"], timeout=10)
        if rc == 0 and nome in saida:
            return True
    
    return False


def iniciar_otel_stack() -> Tuple[bool, str]:
    """Start the OTel LGTM stack.

    Inicia a stack OTel LGTM.
    Retorna (sucesso, mensagem).
    """
    compose_path = _get_compose_path()
    if not compose_path:
        return False, "compose.yml not found in docker/ folder"
    
    compose_cmd = _compose_command()
    if not compose_cmd:
        return False, "Docker Compose not available"
    
    compose_dir = os.path.dirname(compose_path)
    
    logger.info(f"Starting OTel LGTM stack from {compose_dir}")
    
    returncode, stdout, stderr = _run_command(
        compose_cmd + ["up", "-d"],
        timeout=60,
        cwd=compose_dir
    )
    
    if returncode == 0:
        logger.info("OTel LGTM stack started successfully")
        return True, "OTel stack started"
    else:
        error_msg = stderr or stdout or "Unknown error"
        logger.error(f"Failed to start OTel stack: {error_msg}")
        return False, f"Failed to start: {error_msg}"


def parar_otel_stack() -> Tuple[bool, str]:
    """Stop the OTel LGTM stack.

    Para a stack OTel LGTM.
    Retorna (sucesso, mensagem).
    """
    compose_path = _get_compose_path()
    if not compose_path:
        return False, "compose.yml not found"
    
    compose_cmd = _compose_command()
    if not compose_cmd:
        return False, "Docker Compose not available"
    
    compose_dir = os.path.dirname(compose_path)
    
    logger.info("Stopping OTel LGTM stack")
    
    returncode, stdout, stderr = _run_command(
        compose_cmd + ["down"],
        timeout=60,
        cwd=compose_dir
    )
    
    if returncode == 0:
        logger.info("OTel LGTM stack stopped")
        return True, "OTel stack stopped"
    else:
        error_msg = stderr or stdout or "Unknown error"
        logger.error(f"Failed to stop OTel stack: {error_msg}")
        return False, f"Failed to stop: {error_msg}"


def status_otel_stack() -> dict:
    """Get status of all OTel stack services.

    Retorna o status de todos os servicos da stack OTel.
    """
    compose_path = _get_compose_path()
    if not compose_path:
        return {"error": "compose.yml not found"}
    
    compose_cmd = _compose_command()
    if not compose_cmd:
        return {"error": "Docker Compose not available"}
    
    compose_dir = os.path.dirname(compose_path)
    
    returncode, stdout, stderr = _run_command(
        compose_cmd + ["ps", "--format", "json"],
        timeout=10,
        cwd=compose_dir
    )
    
    if returncode != 0:
        return {"error": stderr or "Failed to get status"}
    
    services = {}
    import json
    for line in stdout.strip().split("\n"):
        if not line:
            continue
        try:
            service = json.loads(line)
            name = service.get("Service", "unknown")
            services[name] = {
                "state": service.get("State", "unknown"),
                "health": service.get("Health", "unknown"),
                "ports": service.get("Publishers", [])
            }
        except json.JSONDecodeError:
            continue
    
    return services


# =============================================================================
# Auto-start Logic
# =============================================================================

def auto_iniciar_otel() -> bool:
    """Auto-start OTel stack if Docker is available.

    Auto-inicia a stack OTel se o Docker estiver disponivel.
    Retorna True se a stack foi iniciada ou ja estava rodando.
    """
    if not docker_disponivel():
        logger.info("Docker not available, skipping OTel stack")
        return False
    
    if otel_stack_rodando():
        logger.info("OTel stack already running")
        return True
    
    # Try to start the stack
    success, message = iniciar_otel_stack()
    if success:
        logger.info(f"OTel stack auto-started: {message}")
    else:
        logger.warning(f"Failed to auto-start OTel stack: {message}")
    
    return success


# =============================================================================
# Convenience Functions
# =============================================================================

def get_otel_info() -> dict:
    """Get comprehensive info about OTel availability.

    Retorna informacoes completas sobre a disponibilidade do OTel.
    """
    return {
        "docker_disponivel": docker_disponivel(),
        "docker_desktop": docker_desktop_ativo(),
        "docker_compose": docker_compose_disponivel(),
        "linux": platform.system() == "Linux",
        "compose_path": _get_compose_path(),
        "stack_rodando": otel_stack_rodando() if docker_disponivel() else False,
        "services": status_otel_stack() if docker_disponivel() else {}
    }


def print_otel_info():
    """Print OTel info to console.

    Imprime informacoes do OTel no console.
    """
    info = get_otel_info()
    
    print("\n=== OTel LGTM Stack Info ===")
    print(f"Docker available: {info['docker_disponivel']}")
    print(f"Docker Desktop: {info['docker_desktop']}")
    print(f"Docker Compose: {info['docker_compose']}")
    print(f"Linux: {info['linux']}")
    print(f"Compose path: {info['compose_path'] or 'Not found'}")
    print(f"Stack running: {info['stack_rodando']}")
    
    if info['services']:
        print("\nServices:")
        for name, status in info['services'].items():
            print(f"  {name}: {status.get('state', 'unknown')}")
    
    print("===========================\n")


if __name__ == "__main__":
    print_otel_info()