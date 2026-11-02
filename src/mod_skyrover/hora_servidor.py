"""Hora do servidor com sincronização opcional via NTP.br (RFC 5905).

EN — Provides the system's date/time source of truth. The current date and
every persisted timestamp MUST come from the SERVER, never from the client
browser or any other place. When the server has internet access, the time is
synchronized against NTP.br servers (a.ntp.br / b.ntp.br / c.ntp.br); when
offline (or NTP is disabled), it falls back to the server's own clock.

PT-BR — Fonte da verdade de data/hora do sistema. A data atual e de gravação
devem vir SEMPRE do servidor (nunca do navegador/cliente). Com acesso à
internet, a hora é sincronizada com os servidores NTP.br (a/b/c.ntp.br);
sem internet (ou com NTP desativado na configuração), usa o relógio do
próprio servidor. O offset NTP é cacheador por alguns segundos para evitar
consultas excessivas.
"""

import datetime as _dt
import socket as _socket
import struct as _struct
import threading as _threading
import time as _time

# ================= CONFIGURAÇÃO =================
# Chave em tb_config (módulo skyrover) para ativar/desativar a sincronização NTP.
CHAVE_NTP_ATIVO = "hora_ntp_ativa"
# Servidores NTP do Brasil (NTP.br). Caso os três falhem, usa-se o relógio local.
SERVIDORES_NTP = ("a.ntp.br", "b.ntp.br", "c.ntp.br")
# Tempo máximo de espera por resposta NTP (segundos).
TIMEOUT_NTP = 2
# Validade do offset cacheador (segundos): evita consultar NTP a cada chamada.
CACHE_OFFSET_SEGUNDOS = 60
# Porta padrão do protocolo NTP.
PORTA_NTP = 123

# ================= ESTADO (cache + lock) =================
_offset_cache = None      # (timestamp_gravado, offset_em_segundos) ou None
_lock = _threading.Lock()
_servidor_offline = None  # timestamp da última tentativa de NTP (para não repetir)


def _log():
    """Central logger (loguru) for execution observability.

    Logger central (loguru) para observabilidade de execução."""
    from mod_skyrover import observabilidade
    return observabilidade.get_logger("skyrover")


def _ler_ntp_ativa():
    """Reads from tb_config whether NTP sync is active (default 1 = active).

    Lê de tb_config se a sincronização NTP está ativa (default 1 = ativa).
    Falha de leitura cai no padrão ativo (fail-soft — nunca derruba a hora)."""
    try:
        from mod_skyrover.bd_conexao import get_config
        return (get_config(CHAVE_NTP_ATIVO, "1") or "1") == "1"
    except Exception as e:
        _log().warning(f"falha ao ler hora_ntp_ativa: {e}")
        return True


def _obter_offset_ntp():
    """Queries NTP.br (UDP) and returns the offset in seconds; None on failure.

    Monta o pacote NTP v3 cliente→servidor, envia via UDP para cada servidor
    NTP.br e calcula a diferença entre o tempo de resposta do servidor e o
    relógio local. Retorna None se nenhum servidor responder no timeout."""
    try:
        pacote = b"\x1b" + 47 * b"\0"  # LI=0 VN=3 Mode=3 (client)
        melhor = None
        for host in SERVIDORES_NTP:
            try:
                t0 = _time.time()
                sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
                sock.settimeout(TIMEOUT_NTP)
                sock.sendto(pacote, (host, PORTA_NTP))
                dados, _ = sock.recvfrom(48)
                sock.close()
                t1 = _time.time()
                if len(dados) >= 40:
                    tx = _struct.unpack("!I", dados[40:44])[0]
                    frac = _struct.unpack("!I", dados[44:48])[0]
                    tempo_servidor = tx + frac / 2.0 ** 32 - 2208988800.0  # era 1900→1970
                    # Offset = ((t1 - t0)/2) - (tempo_servidor - t0)  (aproximado)
                    offset = ((t1 - t0) / 2) - (tempo_servidor - t0)
                    melhor = offset
                    break
            except Exception:
                continue
        return melhor
    except Exception as e:
        _log().warning(f"falha ao consultar NTP.br: {e}")
        return None


def offset_ntp():
    """Returns the NTP offset in seconds (cached), 0 when unavailable.

    Usa o cache por alguns segundos e só consulta NTP.br quando o cache expira
    (ou após uma falha, aguardando um intervalo para não martelar a rede)."""
    global _offset_cache, _servidor_offline
    try:
        agora = _time.time()
        with _lock:
            if _offset_cache and (agora - _offset_cache[0]) < CACHE_OFFSET_SEGUNDOS:
                return _offset_cache[1]
            # Após falha, aguarda um intervalo antes de tentar de novo
            if _servidor_offline and (agora - _servidor_offline) < CACHE_OFFSET_SEGUNDOS:
                return 0
            if not _ler_ntp_ativa():
                _offset_cache = (agora, 0)
                return 0
            off = _obter_offset_ntp()
            if off is None:
                _servidor_offline = agora
                _offset_cache = (agora, 0)
                return 0
            _offset_cache = (agora, off)
            _servidor_offline = None
            return off
    except Exception as e:
        _log().exception(f"falha ao calcular offset NTP: {e}")
        return 0


def hora_servidor():
    """Returns the server's current datetime (NTP-corrected when available).

    A hora retornada é SEMPRE a do servidor (offset NTP quando disponível),
    nunca a do cliente. Usada para o carimbo de tempo atual e de gravação."""
    try:
        return _dt.datetime.now() + _dt.timedelta(seconds=offset_ntp())
    except Exception as e:
        _log().exception(f"falha ao obter hora do servidor: {e}")
        return _dt.datetime.now()


def hora_servidor_str(formato="%Y-%m-%d %H:%M:%S"):
    """Returns the server time as a string in the given format.

    Retorna a hora do servidor como string no formato informado."""
    try:
        return hora_servidor().strftime(formato)
    except Exception as e:
        _log().exception(f"falha ao formatar hora do servidor: {e}")
        return _dt.datetime.now().strftime(formato)


def definir_ntp_ativa(valor):
    """Persists in tb_config whether NTP sync is active (1/0).

    Persiste em tb_config se a sincronização NTP está ativa (1/0)."""
    try:
        from mod_skyrover.bd_conexao import set_config
        set_config(CHAVE_NTP_ATIVO, "1" if valor else "0")
    except Exception as e:
        _log().exception(f"falha ao gravar hora_ntp_ativa: {e}")