"""Grafana credentials sync with Skyrover database.

Sincroniza as credenciais do usuário master da Skyrover com o Grafana.

Author: Administrador do sistema
Date: 2026-09-04
"""
import os
import sys
import subprocess
import json
from typing import Optional, Tuple

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CFG_GRAFANA_URL = "grafana_url"
DEFAULT_GRAFANA_URL = "http://localhost:3000"

# Esquemas aceitos na URL do Grafana. Sem esta trava, `GRAFANA_URL=file://...`
# faria `_url.urlopen()` abrir ARQUIVO LOCAL em vez de HTTP (alerta bandit B310).
_SCHEMAS_GRAFANA = ("http://", "https://")


def _url_grafana_valida(cand: str) -> bool:
    """True se `cand` é uma URL http(s) absoluta (rejeita file:// e afins)."""
    try:
        return bool(cand) and cand.strip().lower().startswith(_SCHEMAS_GRAFANA)
    except Exception:
        return False


def obter_grafana_url():
    """Resolves the Grafana base URL (env GRAFANA_URL wins over tb_config).

    Resolve a URL base do Grafana: env tem prioridade, depois `tb_config`
    (`grafana_url`), depois o padrão local. Valor fora de http(s) é
    IGNORADO (cai no padrão) — nunca abrimos esquema `file://`/custom."""
    try:
        env = (os.getenv("GRAFANA_URL") or "").strip().rstrip("/")
        if env:
            return env if _url_grafana_valida(env) else DEFAULT_GRAFANA_URL
        from mod_skyrover.bd_conexao import get_config
        cfg = ((get_config(CFG_GRAFANA_URL, DEFAULT_GRAFANA_URL)
                or DEFAULT_GRAFANA_URL).strip().rstrip("/")
               or DEFAULT_GRAFANA_URL)
        return cfg if _url_grafana_valida(cfg) else DEFAULT_GRAFANA_URL
    except Exception:
        return DEFAULT_GRAFANA_URL


def _run_command(cmd: list, timeout: int = 10) -> Tuple[int, str, str]:
    """Execute a command and return returncode, stdout, stderr.

    Executa em thread separada com deadline rígido: mesmo que o processo
    deixe um descendente segurando o pipe (comum no CLI do Docker), o boot
    nunca trava — após `timeout` retorna (-1, "", "Command timed out").
    """
    import threading

    resultado = {}

    def _executar():
        try:
            p = subprocess.run(cmd, capture_output=True, text=True)
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


def obter_senha_master() -> Optional[str]:
    """Get master user password from Skyrover database.

    Obtém a senha do usuário master do banco de dados da Skyrover.
    """
    try:
        # A tabela tb_usuarios fica no banco do módulo mod_gest_cad_usuario
        from mod_gest_cad_usuario.bd_manipulador import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # Verifica se o usuário master existe (idempotente)
        cursor.execute(
            "SELECT user_nome FROM tb_usuarios WHERE user_nome = 'master'"
        )
        result = cursor.fetchone()
        conn.close()

        if result:
            # A senha real é um hash bcrypt; o Grafana usa a mesma senha
            # padrão "master". Retorna "master" (password padrão de seed).
            return "master"

        return None
    except Exception as e:
        print(f"[grafana-sync] Error getting master password: {e}")
        return None


def grafana_rodando() -> bool:
    """Check if Grafana container is running.

    Verifica se o container do Grafana está rodando.
    """
    returncode, stdout, _ = _run_command(
        ["docker", "inspect", "--format", "{{.State.Running}}", "skyrover-grafana"],
        timeout=5
    )
    return returncode == 0 and "true" in stdout.lower()


def grafana_aguardar_pronto(limite: int = 150) -> bool:
    """Wait until the Grafana HTTP API is ready.

    Aguarda o Grafana responder no /api/health. Evita chamar o CLI de reset
    durante a migração inicial do banco: em instalação limpa isso corrompia o
    SQLite com SQLITE_BUSY (migração renomear coluna dava "duplicate column").
    """
    import time as _time
    import urllib.request as _url

    inicio = _time.time()
    base = obter_grafana_url()
    while _time.time() - inicio < limite:
        try:
            with _url.urlopen(f"{base}/api/health", timeout=3) as resp:  # nosec B310 — `base` vem de obter_grafana_url(), que só devolve http(s) (file:///custom caem no padrão)
                if resp.status == 200:
                    return True
        except Exception:
            pass
        _time.sleep(2)
    return False


def _api_autorizada(senha: str) -> Optional[bool]:
    """Check if basic auth master:<senha> works on the Grafana API.

    Retorna True se a API aceita master/senha, False se 401, None em erro.
    """
    import base64 as _b64
    import urllib.error as _urlerr
    import urllib.request as _url

    token = _b64.b64encode(f"master:{senha}".encode()).decode()
    requisicao = _url.Request(
        f"{obter_grafana_url()}/api/org",
        headers={"Authorization": f"Basic {token}"},
    )
    try:
        with _url.urlopen(requisicao, timeout=5) as resp:  # nosec B310 — `requisicao` herda a base de obter_grafana_url(), validada como http(s)
            return resp.status == 200
    except _urlerr.HTTPError as e:
        return False if e.code == 401 else None
    except Exception:
        return None


def atualizar_senha_grafana(nova_senha: str) -> Tuple[bool, str]:
    """Update Grafana admin password via Grafana CLI (only when healthy).

    Atualiza a senha do admin via CLI somente depois que o Grafana está pronto,
    evitando corrida com a migração inicial do banco (SQLITE_BUSY).
    """
    if not grafana_rodando():
        return False, "Grafana container not running"

    if not grafana_aguardar_pronto(limite=150):
        return False, "Grafana demorou demais para ficar pronto (health check)"

    try:
        # Reset admin password using Grafana CLI (confiável no Grafana 13+)
        returncode, stdout, stderr = _run_command(
            ["docker", "exec", "skyrover-grafana", "grafana", "cli",
             "admin", "reset-admin-password", nova_senha],
            timeout=30
        )
        if returncode == 0:
            return True, f"Senha do grafana atualizada para '{nova_senha}'"
        else:
            return False, (stderr or stdout or "Falha ao resetar senha").strip()
    except Exception as e:
        return False, str(e)


def sincronizar_credenciais() -> Tuple[bool, str]:
    """Sync Skyrover master credentials with Grafana.

    Sincroniza as credenciais do master da Skyrover com o Grafana. Aguarda o
    Grafana ficar pronto e prefere validar via API (sem corrida de escrita no
    banco); só usa o CLI de reset se a senha atual não for aceita.
    """
    # Get master password from Skyrover
    senha_master = obter_senha_master()

    if not senha_master:
        return False, "Could not get master password from Skyrover"

    if not grafana_rodando():
        return False, "Grafana not running"

    if not grafana_aguardar_pronto(limite=150):
        return False, "Grafana demorou demais para ficar pronto (health check)"

    # Se a API já aceita master/senha, não toca no banco (evita SQLITE_BUSY).
    ja_sincronizada = _api_autorizada(senha_master)
    if ja_sincronizada is True:
        return True, f"Grafana credentials synced: master/{senha_master}"

    # Fallback: CLI reset (agora o Grafana já migrou, sem corrida).
    sucesso, msg = atualizar_senha_grafana(senha_master)
    if sucesso:
        return True, f"Grafana credentials synced: master/{senha_master}"
    return False, f"Failed to update Grafana: {msg}"


def obter_status_grafana() -> dict:
    """Get Grafana status information.

    Retorna informações de status do Grafana.
    """
    return {
        "rodando": grafana_rodando(),
        "url": obter_grafana_url(),
        "usuario": "master",
        "senha": "master"
    }


if __name__ == "__main__":
    print("=== Grafana Credentials Sync ===")
    status = obter_status_grafana()
    print(f"Grafana running: {status['rodando']}")
    print(f"URL: {status['url']}")
    print(f"Username: {status['usuario']}")
    print(f"Password: {status['senha']}")
    print("="*40)