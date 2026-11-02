# -*- coding: utf-8 -*-
"""Prova o contrato de autenticação e o seed de QA.

O que este teste garante: `master/master` autentica e exige troca de senha e
credenciais; `qacomum/123456` e `qamaster/123456` autenticam sem troca
forçada; senha errada é recusada. Não garante nada sobre telas ou sessões.
"""
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
os.environ.setdefault("SKYROVER_DIR_BANCO", os.path.join(
    RAIZ, "tests", "_bd_teste"))
os.environ.setdefault("SKYROVER_QA_SEM_TROCA", "1")

from mod_skyrover.bd_criador import inicializar_bancos
from mod_skyrover import autenticacao


class TestFluxoAutenticacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inicializar_bancos()

    def test_master_autentica_e_exige_troca(self):
        ok, perfil, nome = autenticacao.autenticar(
            "master", "master", com_login_canonico=True)
        self.assertTrue(ok)
        self.assertEqual(perfil, "administrador_geral")
        self.assertEqual(nome, "master")
        self.assertTrue(autenticacao.precisa_trocar_senha("master"))
        self.assertTrue(autenticacao.precisa_trocar_credenciais("master"))

    def test_qacomum_autentica_sem_troca(self):
        ok, perfil, nome = autenticacao.autenticar(
            "qacomum", "123456", com_login_canonico=True)
        self.assertTrue(ok)
        self.assertEqual(perfil, "comum")
        self.assertEqual(nome, "qacomum")
        self.assertFalse(autenticacao.precisa_trocar_senha("qacomum"))

    def test_qamaster_autentica_sem_troca(self):
        ok, perfil, nome = autenticacao.autenticar(
            "qamaster", "123456", com_login_canonico=True)
        self.assertTrue(ok)
        self.assertEqual(perfil, "administrador_geral")
        self.assertFalse(autenticacao.precisa_trocar_senha("qamaster"))

    def test_senha_errada_e_recusada(self):
        ok, _msg, _nome = autenticacao.autenticar(
            "qacomum", "senha-errada", com_login_canonico=True)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
