"""Captcha local — desafio matemático em imagem, sem serviço externo.

EN: Local CAPTCHA — math challenge rendered as an image, no external service.

Tudo aqui é biblioteca padrão + Pillow (já dependência do projeto): o
desafio é "quanto é A+B?" desenhado num PNG com ruído, e a resposta mora
só na memória do servidor, com expiração — nunca no HTML, no cookie nem
na URL. Bot que lê o DOM vê só pixels.

Uso (24/10/2026, pós-pentest): o login de `main.py` passa a exigir o
captcha quando o IP acumula `captcha_apos_falhas` falhas recentes
(padrão 3, configurável na `tb_config` central). Erro de digitação
isolado nunca vê captcha; rajada de tentativas sempre vê.
"""

import io
import secrets
import threading
import time

JANELA_RESPOSTA_SEG = 300  # 5 min: desafio não resolvido expira e some

_desafios = {}  # ip -> (resposta: str, expira_em: float)
_trava = threading.Lock()


def _config(chave, padrao):
    """Lê a `tb_config` central sem importar o mundo (fail-soft)."""
    try:
        from mod_skyrover.bd_conexao import get_config
        return get_config(chave, padrao)
    except Exception:
        return padrao


def limite_falhas() -> int:
    """Falhas recentes do IP que passam a exigir captcha (padrão 3)."""
    try:
        return max(1, int(_config("captcha_apos_falhas", "3")))
    except Exception:
        return 3


def _desenhar(pergunta: str) -> bytes:
    """Renderiza a pergunta num PNG com ruído. Devolve os bytes."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        fonte = ImageFont.load_default(size=34)
        largura, altura = 240, 80
        img = Image.new("RGB", (largura, altura), "white")
        pincel = ImageDraw.Draw(img)
        # Ruído cosmético com `secrets` (sem `random`: B311 — mesmo o ruído
        # usa CSPRNG para não haver nenhum PRNG previsível neste arquivo).
        for _ in range(6):  # linhas de ruído
            x1, y1 = secrets.randbelow(largura + 1), secrets.randbelow(altura + 1)
            x2, y2 = secrets.randbelow(largura + 1), secrets.randbelow(altura + 1)
            pincel.line([x1, y1, x2, y2], fill=(200, 200, 200), width=1)
        for _ in range(120):  # pontos de ruído
            pincel.point((secrets.randbelow(largura + 1), secrets.randbelow(altura + 1)),
                         fill=(180, 180, 180))
        caixa = pincel.textbbox((0, 0), pergunta, font=fonte)
        pincel.text(((largura - (caixa[2] - caixa[0])) / 2,
                     (altura - (caixa[3] - caixa[1])) / 2 - 4),
                    pergunta, fill=(20, 20, 20), font=fonte)
        for _ in range(3):  # traços sobre o texto
            y = 10 + secrets.randbelow(max(1, altura - 19))
            pincel.line([0, y, largura, y + secrets.randbelow(13) - 6],
                        fill=(150, 150, 150), width=1)
        saida = io.BytesIO()
        img.save(saida, format="PNG")
        return saida.getvalue()
    except Exception:
        return b""


def gerar_para(ip: str):
    """Cria um desafio para o IP. Devolve (png_bytes, pergunta_texto).

    A resposta fica SÓ no servidor (`_desafios`), com expiração. O texto
    da pergunta volta junto para o `alt` acessível da imagem — ler o alt
    não entrega a resposta, que é o RESULTADO da conta, não a pergunta.
    """
    try:
        ip = (ip or "").strip()
        if not ip:
            return b"", ""
        # Números do desafio com CSPRNG (`secrets`): `random` aqui permitiria
        # prever o desafio e automatizar o bypass do captcha (B311).
        a = 10 + secrets.randbelow(40)
        b = 10 + secrets.randbelow(40)
        pergunta = f"{a} + {b} = ?"
        png = _desenhar(pergunta)
        if not png:
            return b"", ""
        with _trava:
            _desafios[ip] = (str(a + b),
                             time.monotonic() + JANELA_RESPOSTA_SEG)
        return png, pergunta
    except Exception:
        return b"", ""


def verificar(ip: str, resposta: str) -> bool:
    """Confere a resposta. Consome o desafio em qualquer caso (sem replay).

    Sem desafio pendente ou expirado, devolve False — falhar fechado aqui
    nunca trava login legítimo, porque o login gera outro desafio.
    """
    try:
        ip = (ip or "").strip()
        with _trava:
            esperado, expira = _desafios.pop(ip, (None, 0))
        if esperado is None:
            return False
        if time.monotonic() > expira:
            return False
        return (resposta or "").strip() == esperado
    except Exception:
        return False


def limpar_expirados() -> int:
    """Remove desafios vencidos. Devolve quantos saíram."""
    try:
        agora = time.monotonic()
        with _trava:
            vencidos = [ip for ip, (_, exp) in _desafios.items()
                        if agora > exp]
            for ip in vencidos:
                _desafios.pop(ip, None)
        return len(vencidos)
    except Exception:
        return 0
