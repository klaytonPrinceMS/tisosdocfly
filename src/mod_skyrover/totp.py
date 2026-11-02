"""Segundo fator TOTP local (RFC 6238) — sem serviço externo.

EN: Local TOTP second factor (RFC 6238) — no external service.

Compatível com qualquer app autenticador (Google/Microsoft Authenticator,
Authy, andOTP): o segredo é gerado aqui com `secrets`, o usuário cadastra
digitando o código ou a URI `otpauth://`, e a conferência usa só
`hmac`+`hashlib` da biblioteca padrão. Nenhum pacote novo, nenhum
telefonema para fora.

O segredo mora na `tb_config` CENTRAL (`totp_segredo:<login>`), ao lado
das outras chaves do módulo — o rodapé lê a versão de lá pelo mesmo
caminho, e a ativação/desativação entra no `audit_log` como qualquer
evento de conta. Opt-in por usuário: quem não ativa continua entrando
só com a senha, e o login pede o código SÓ de quem ativou.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import threading
import time

PASSO_SEG = 30
DIGITOS = 6
JANELA_PASSOS = 1  # aceita ±1 passo (relógio do celular adiantado/atrasado)
PENDENCIA_SEG = 600  # 10 min para confirmar a ativação com um código

_pendentes = {}  # login -> (segredo_b32: str, expira_em: float)
_trava = threading.Lock()


def _normalizar(segredo_b32: str) -> bytes:
    """Base32 (sem/maiúsculas/espaços) -> bytes. Levanta se inválido."""
    limpo = "".join((segredo_b32 or "").split()).upper()
    faltam = (-len(limpo)) % 8
    return base64.b32decode(limpo + ("=" * faltam))


def novo_segredo() -> str:
    """Gera um segredo novo (160 bits, base32 sem `=`)."""
    try:
        return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    except Exception:
        return ""


def codigo(segredo_b32: str, quando=None) -> str:
    """O código de 6 dígitos válido no instante `quando` (padrão: agora)."""
    try:
        chave = _normalizar(segredo_b32)
        instante = int(time.time() if quando is None else quando)
        contador = instante // PASSO_SEG
        mac = hmac.new(chave, struct.pack(">Q", contador),
                       hashlib.sha1).digest()
        desloc = mac[-1] & 0x0F
        numero = struct.unpack(">I", mac[desloc:desloc + 4])[0] & 0x7FFFFFFF
        return str(numero % (10 ** DIGITOS)).zfill(DIGITOS)
    except Exception:
        return ""


def verificar(segredo_b32: str, tentativa: str) -> bool:
    """Confere o código aceitando ±1 passo de relógio. Sem vazamento: bool."""
    try:
        tentativa = "".join((tentativa or "").split())
        if not tentativa.isdigit() or len(tentativa) != DIGITOS:
            return False
        agora = int(time.time())
        for desloc in range(-JANELA_PASSOS, JANELA_PASSOS + 1):
            if hmac.compare_digest(
                    codigo(segredo_b32, agora + desloc * PASSO_SEG),
                    tentativa):
                return True
        return False
    except Exception:
        return False


def uri_ativacao(segredo_b32: str, login: str,
                 emissor: str = "SKYROVER") -> str:
    """URI `otpauth://` para cadastrar digitando/copiando no app."""
    try:
        return (f"otpauth://totp/{emissor}:{login}"
                f"?secret={segredo_b32}&issuer={emissor}"
                f"&algorithm=SHA1&digits={DIGITOS}&period={PASSO_SEG}")
    except Exception:
        return ""


def _chave(login: str) -> str:
    return f"totp_segredo:{(login or '').strip()}"


def tem_segredo(login: str) -> bool:
    """True se o usuário ativou o segundo fator."""
    try:
        from mod_skyrover.repositorio import Repositorio
        with Repositorio() as repo:
            return bool((repo.obter_config(_chave(login), "") or "").strip())
    except Exception:
        return False


def _obter(login: str) -> str:
    try:
        from mod_skyrover.repositorio import Repositorio
        with Repositorio() as repo:
            return (repo.obter_config(_chave(login), "") or "").strip()
    except Exception:
        return ""


def iniciar_ativacao(login: str) -> str:
    """Gera o segredo pendente (10 min para confirmar com um código)."""
    try:
        login = (login or "").strip()
        if not login:
            return ""
        segredo = novo_segredo()
        if not segredo:
            return ""
        with _trava:
            _pendentes[login] = (segredo, time.monotonic() + PENDENCIA_SEG)
        return segredo
    except Exception:
        return ""


def segredo_pendente(login: str) -> str:
    """O segredo ainda não confirmado, ou '' se expirou."""
    try:
        with _trava:
            segredo, expira = _pendentes.get((login or "").strip(),
                                             ("", 0))
        if not segredo or time.monotonic() > expira:
            with _trava:
                _pendentes.pop((login or "").strip(), None)
            return ""
        return segredo
    except Exception:
        return ""


def confirmar_ativacao(login: str, tentativa: str) -> bool:
    """O código do app bate com o pendente? Persiste e audita."""
    try:
        login = (login or "").strip()
        segredo = segredo_pendente(login)
        if not segredo or not verificar(segredo, tentativa):
            return False
        from mod_skyrover.repositorio import Repositorio
        with Repositorio() as repo:
            repo.definir_config(_chave(login), segredo)
        with _trava:
            _pendentes.pop(login, None)
        try:
            from mod_skyrover.bd_manipulador import audit_log
            audit_log(login, "skyrover", "totp_ativar",
                      "Segundo fator (TOTP) ativado")
        except Exception:
            pass
        return True
    except Exception:
        return False


def desativar(login: str) -> bool:
    """Remove o segundo fator. Audita como evento de conta."""
    try:
        login = (login or "").strip()
        if not login:
            return False
        from mod_skyrover.repositorio import Repositorio
        with Repositorio() as repo:
            repo.definir_config(_chave(login), "")
        try:
            from mod_skyrover.bd_manipulador import audit_log
            audit_log(login, "skyrover", "totp_desativar",
                      "Segundo fator (TOTP) desativado")
        except Exception:
            pass
        return True
    except Exception:
        return False
