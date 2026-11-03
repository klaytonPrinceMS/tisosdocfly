# -*- coding: utf-8 -*-
"""Current HTTP request context (LGPD traceability).

Contexto da requisição HTTP corrente (rastreabilidade LGPD).

Lê o ContextVar nativo do NiceGUI (nicegui.storage.request_contextvar),
que o próprio framework popula na construção da página E restaura antes
de cada callback de evento — então IP/User-Agent ficam disponíveis tanto
no render quanto dentro de on_click/registrar_login, sem tocar nas
assinaturas das páginas. Fora do servidor (QA, agendador) devolve vazio.
"""
import contextvars
import re

_RE_CHROME = re.compile(r"Chrome/(\d+)")
_RE_FIREFOX = re.compile(r"Firefox/(\d+)")
_RE_EDGE = re.compile(r"Edg(e|A|iOS)?/(\d+)")
_RE_SAFARI = re.compile(r"Version/(\d+).*Safari")
_RE_OPERA = re.compile(r"(OPR|Opera)/(\d+)")

_VAZIO = {"ip": None, "ua": None}

# caminho de injeção explícita (QA / integrações) — tem prioridade sobre o NiceGUI
_override = contextvars.ContextVar("ctx_rastreio_override", default=None)


def _request():
    try:
        from nicegui.storage import request_contextvar
        return request_contextvar.get()
    except Exception:
        return None


def _extrair(request):
    info = {"ip": None, "ua": None}
    if request is None:
        return info
    try:
        if getattr(request, "client", None):
            # atrás de proxy reverso usa X-Forwarded-For quando existir
            fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            info["ip"] = fwd or (request.client.host or None)
        info["ua"] = (request.headers.get("user-agent") or "")[:400]
    except Exception:
        pass
    return info


def capturar_contexto(request=None):
    """Com request explícito: fixa o contexto (QA/integrações).
    Sem request: apenas retorna o estado atual (resolução é preguiçosa)."""
    if request is not None:
        _override.set(_extrair(request))
    return _info()


def limpar_contexto():
    """Remove override — volta a ler o ContextVar do NiceGUI."""
    _override.set(None)


def _info():
    over = _override.get()
    if isinstance(over, dict):
        return dict(over)
    request = _request()
    return _extrair(request)


def contexto_atual():
    """{ip, ua} da requisição corrente ou {ip: None, ua: None}."""
    return _info()


def rotulo_dispositivo(ua):
    """Rótulo legível do User-Agent: 'Chrome 126 · Windows', 'Safari · iOS'..."""
    if not ua:
        return None
    try:
        navegador = None
        m = _RE_EDGE.search(ua)
        if m:
            navegador = f"Edge {m.group(2)}"
        elif _RE_OPERA.search(ua):
            navegador = "Opera"
        elif _RE_CHROME.search(ua):
            navegador = f"Chrome {_RE_CHROME.search(ua).group(1)}"
        elif _RE_FIREFOX.search(ua):
            navegador = f"Firefox {_RE_FIREFOX.search(ua).group(1)}"
        elif _RE_SAFARI.search(ua):
            navegador = f"Safari {_RE_SAFARI.search(ua).group(1)}"
        else:
            navegador = "Navegador desconhecido"

        sistema = "Desconhecido"
        baixo = ua.lower()
        ordem = [
            ("windows nt 10", "Windows 10/11"), ("windows", "Windows"),
            ("android", "Android"), ("iphone", "iPhone/iPad"),
            ("ipad", "iPhone/iPad"), ("mac os x", "macOS"), ("cros", "ChromeOS"),
            ("linux", "Linux"),
        ]
        for chave, rot in ordem:
            if chave in baixo:
                sistema = rot
                break
        extra = " (mobile)" if ("mobile" in baixo or "android" in baixo) else ""
        return f"{navegador} · {sistema}{extra}"
    except Exception:
        return "User-Agent não interpretado"


def mac_best_effort(ip):
    """Resolve MAC via ARP para IPs da mesma sub-rede (best-effort).

    HTTP não expõe MAC remoto; funciona só quando o cliente está na LAN
    direta do servidor. Qualquer falha retorna None silenciosamente.
    """
    if not ip or not ip.startswith("192.168.") or ip == "192.168.0.1":
        return None
    import subprocess
    try:
        subprocess.run(["ping", "-c1", "-W1", ip],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=3)
        saida = subprocess.run(["ip", "neigh", "show", ip],
                               capture_output=True, text=True, timeout=2)
        tokens = saida.stdout.split()
        for i, parte in enumerate(tokens):
            if parte.lower() == "lladdr" and i + 1 < len(tokens):
                return tokens[i + 1]
    except Exception:
        pass
    return None
