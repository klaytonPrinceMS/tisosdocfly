"""T! SOS DocFly SMTP email utility (RF-58).

Utilitário de e-mail SMTP da T! SOS DocFly (RF-58).

Configurações persistidas em `tb_config` (chaves `smtp_*`):
    smtp_servidor, smtp_porta, smtp_usuario, smtp_senha, smtp_tls, smtp_de.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from mod_tisosdocfly.bd_conexao import get_config
from mod_tisosdocfly import observabilidade

_log = observabilidade.get_logger("email")


def _cfg():
    return {
        "servidor": (get_config("smtp_servidor", "") or "").strip(),
        "porta": int((get_config("smtp_porta", "587") or 587) or 587),
        "usuario": (get_config("smtp_usuario", "") or "").strip(),
        "senha": get_config("smtp_senha", "") or "",
        "tls": (get_config("smtp_tls", "1") or "1") == "1",
        "de": (get_config("smtp_de", "") or "").strip()
        or (get_config("smtp_usuario", "") or "").strip(),
    }


def enviar_email(destinatario, assunto, corpo, anexos=None, html=False):
    """Envia e-mail via SMTP configurado. Retorna (ok, msg)."""
    cfg = _cfg()
    if not cfg["servidor"] or not cfg["usuario"]:
        return False, "SMTP não configurado"
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders

    msg = MIMEMultipart()
    msg["From"] = cfg["de"]
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo, "html" if html else "plain", "utf-8"))
    for a in (anexos or []):
        if a and os.path.exists(a):
            part = MIMEBase("application", "octet-stream")
            with open(a, "rb") as f:
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition",
                            f"attachment; filename={os.path.basename(a)}")
            msg.attach(part)
    try:
        with smtplib.SMTP(cfg["servidor"], cfg["porta"], timeout=15) as s:
            if cfg["tls"]:
                s.starttls()
            if cfg["senha"]:
                s.login(cfg["usuario"], cfg["senha"])
            s.sendmail(cfg["de"], [destinatario], msg.as_string())
        _log.info(f"e-mail enviado para {destinatario}: {assunto}")
        return True, "E-mail enviado"
    except Exception as e:
        _log.warning(f"falha ao enviar e-mail: {e}")
        return False, str(e)


def testar_conexao():
    """Testa a conexão/autenticação SMTP sem enviar mensagem. Retorna (ok, msg)."""
    cfg = _cfg()
    if not cfg["servidor"]:
        return False, "Servidor não informado"
    import smtplib
    try:
        with smtplib.SMTP(cfg["servidor"], cfg["porta"], timeout=15) as s:
            if cfg["tls"]:
                s.starttls()
            if cfg["senha"]:
                s.login(cfg["usuario"], cfg["senha"])
        return True, "Conexão SMTP OK"
    except Exception as e:
        _log.warning(f"teste SMTP falhou: {e}")
        return False, str(e)
