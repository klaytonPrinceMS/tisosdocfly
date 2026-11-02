"""EN: Shared login helper for the QA Playwright tests.

PT-BR: Auxiliar de login compartilhado pelos testes Playwright.

No Skyrover as contas `qacomum` e `qamaster` nascem SEM troca forçada
(decisão do seed), então o login de QA é direto. Se o ambiente tiver
`SKYROVER_QA_SEM_TROCA` desligado e a troca aparecer, o helper conclui a
troca com a mesma senha de origem e segue.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_URL = os.environ.get("SKYROVER_BASE_URL", "http://localhost:8080")
QA_USUARIO = "qamaster"
QA_SENHA = "123456"
QA_SENHA_NOVA = "Skyrover@2026"
ROTA_TROCA = "/troca-obrigatoria"


def _troca_visivel(page) -> bool:
    """Diz se a tela de troca obrigatória está aberta."""
    try:
        if ROTA_TROCA in (page.url or ""):
            return True
        return page.get_by_role("button", name="Alterar senha").count() > 0
    except Exception:
        return False


def concluir_troca(page, senha_atual: str, senha_nova: str = QA_SENHA_NOVA):
    """Preenche os campos da troca obrigatória, quando ela aparecer."""
    try:
        page.get_by_test_id("troca-senha-atual").fill(senha_atual)
        page.get_by_test_id("troca-senha-nova").fill(senha_nova)
        page.get_by_role("button", name="Alterar senha").click()
        page.wait_for_timeout(1200)
    except Exception:
        pass


def zerar_forcar_troca(usuario: str = QA_USUARIO) -> bool:
    """Desliga a troca obrigatória do usuário de QA (idempotente)."""
    try:
        raiz = Path(__file__).resolve().parents[1]
        for alvo in (str(raiz / "src"), str(raiz)):
            if alvo not in sys.path:
                sys.path.insert(0, alvo)
        from mod_skyrover import autenticacao
        autenticacao.marcar_trocar_senha(usuario, forcar=False)
        return True
    except Exception:
        return False
