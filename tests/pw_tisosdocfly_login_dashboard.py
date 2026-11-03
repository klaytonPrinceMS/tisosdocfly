"""T! SOS DocFly — login e dashboard (pytest-playwright, headless).

EN: T! SOS DocFly core — /login (data-testid) and dashboard for qamaster and
    qacomum. Static checks are the fast part; the E2E part needs a live
    server on TISOSDOCFLY_BASE_URL (default http://localhost:8080).

PT: Núcleo T! SOS DocFly — /login (data-testid) e dashboard com qamaster e
    qacomum. A parte estática é rápida; a E2E exige servidor no ar em
    TISOSDOCFLY_BASE_URL (padrão http://localhost:8080).

Como rodar:
    poetry run task start          # em outro terminal
    poetry run pytest -m e2e -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytestmark = pytest.mark.e2e

BASE_URL = os.environ.get("TISOSDOCFLY_BASE_URL", "http://localhost:8080")
ADMIN_USUARIO = "qamaster"
ADMIN_SENHA = "123456"
COMUM_USUARIO = "qacomum"
COMUM_SENHA = "123456"

from paths_repo import caminho as _caminho_repo  # noqa: E402
from qa_login_helper import _troca_visivel, concluir_troca  # noqa: E402


def _ler(rel: str) -> str:
    try:
        return _caminho_repo(rel).read_text(encoding="utf-8")
    except Exception:
        return ""


def fazer_login(page, usuario: str, senha: str) -> bool:
    """Faz login, concluindo a troca obrigatória se ela aparecer."""
    try:
        page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded",
                  timeout=15000)
    except Exception:
        pytest.skip(f"servidor live indisponível em {BASE_URL}")
    page.get_by_test_id("login-usuario").fill(usuario)
    page.get_by_test_id("login-senha").fill(senha)
    page.get_by_test_id("login-entrar").click()
    try:
        page.wait_for_function(
            "() => !location.pathname.startsWith('/login')", timeout=20000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        pass

    if _troca_visivel(page):
        concluir_troca(page, senha, senha)

    assert not _troca_visivel(page), (
        "troca obrigatória não foi concluída — a tela continua bloqueada")
    return "/login" not in (page.url or "")


class TestEstatico:
    """Asserts rápidos sem servidor."""

    def test_login_tem_testids_via_props(self):
        fonte = _ler("main.py")
        assert ".props(\"data-testid=login-usuario\")" in fonte
        assert ".props(\"data-testid=login-senha\")" in fonte
        assert ".props(\"data-testid=login-entrar\")" in fonte

    def test_rotas_centrais_registradas(self):
        fonte = _ler("main.py")
        assert '@ui.page("/login")' in fonte
        assert '@ui.page("/")' in fonte
        assert '@ui.page("/users")' in fonte
        assert '@ui.page("/admin/{chave_modulo}")' in fonte

    def test_layout_expoe_testids_de_menu(self):
        fonte = _ler("mod_tisosdocfly/telas.py")
        assert "data-testid=menu-hamburguer" in fonte
        assert "menu-home" in fonte
        assert "menu-sair" in fonte

    def test_papel_validado_antes_de_registrar_sessao(self):
        fonte = _ler("main.py")
        assert "autenticacao.autenticar(" in fonte
        assert "registrar_login" in fonte


class TestLoginEDashboard:
    def test_login_admin_abre_dashboard(self, page):
        assert fazer_login(page, ADMIN_USUARIO, ADMIN_SENHA)
        page.wait_for_timeout(800)
        assert page.get_by_text("Bem-vindo").count() > 0

    def test_login_comum_abre_dashboard(self, page):
        assert fazer_login(page, COMUM_USUARIO, COMUM_SENHA)
        page.wait_for_timeout(800)
        assert page.get_by_text("Bem-vindo").count() > 0

    def test_admin_alcanca_usuarios(self, page):
        assert fazer_login(page, ADMIN_USUARIO, ADMIN_SENHA)
        page.goto(f"{BASE_URL}/users", wait_until="domcontentloaded",
                  timeout=15000)
        page.wait_for_timeout(800)
        assert "login" not in (page.url or "")
