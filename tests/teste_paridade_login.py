# -*- coding: utf-8 -*-
"""Prova que o login e a troca de senha mantêm o padrão da intranet.

O que este teste garante: o padrão visual do login continua o WhatsApp
(`verde`), a tela de login usa `preview_estilos.tela_login` (o mesmo invólucro
do núcleo original), a tela de troca obrigatória mantém os três campos de
senha e o `master` vê a lista de regras de senha. Não é teste de pixel; é
guarda contra reimplementação acidental.
"""
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, os.path.join(RAIZ, "tests"))
os.environ.setdefault("TISOSDOCFLY_DIR_BANCO", os.path.join(
    RAIZ, "tests", "_bd_teste"))

from paths_repo import caminho  # noqa: E402
from mod_tisosdocfly import politica_senha, preview_estilos  # noqa: E402


def _ler(rel: str) -> str:
    return caminho(rel).read_text(encoding="utf-8")


class TestParidadeLogin(unittest.TestCase):
    def test_padrao_login_whatsapp(self):
        self.assertEqual(preview_estilos.PADRAO_LOGIN, "verde")

    def test_login_usa_o_mesmo_involucro_do_nucleo(self):
        fonte = _ler("main.py")
        self.assertIn("_pv.tela_login(", fonte)
        self.assertIn('titulo_caixa="T! SOS DOCFLY"', fonte)
        self.assertIn("PADRAO_LOGIN", fonte)
        self.assertIn('data-testid=login-usuario', fonte)
        self.assertIn('data-testid=login-senha', fonte)
        self.assertIn('data-testid=login-entrar', fonte)

    def test_troca_obrigatoria_tem_tres_senhas(self):
        fonte = _ler("mod_tisosdocfly/telas.py")
        self.assertIn("_formulario_troca_credenciais", fonte)
        self.assertIn("_formulario_troca_senha", fonte)
        self.assertIn('"Senha atual"', fonte)
        self.assertIn('"Nova senha', fonte)
        self.assertIn('"Confirmar nova senha"', fonte)

    def test_master_ve_as_regras_de_senha(self):
        fonte = _ler("mod_tisosdocfly/telas.py")
        self.assertIn("_eh_credenciais", fonte)
        self.assertIn("politica_senha.regras_para_tela()", fonte)
        regras = politica_senha.regras_para_tela()
        self.assertIn("barra de força", regras)
        self.assertIn("caractere especial", regras)

    def test_css_do_padrao_verde_presente(self):
        css = _ler("assets/css/preview-estilos-v1.css")
        self.assertIn(".pe-verde", css)
        self.assertIn("preview-entrar", css)


if __name__ == "__main__":
    unittest.main(verbosity=2)
