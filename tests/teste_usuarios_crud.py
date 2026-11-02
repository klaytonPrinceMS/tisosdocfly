# -*- coding: utf-8 -*-
"""Prova o CRUD essencial de usuários, sem passar pela UI.

O que este teste garante: criar, buscar, bloquear e excluir definitivamente
funcionam, e a conta criada aparece na busca. Não garante permissões de tela.
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
from mod_gest_cad_usuario import bd_manipulador as gest

LOGIN = "teste_skyrover_crud"


class TestUsuariosCrud(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inicializar_bancos()
        gest.excluir_usuario_definitivo("master", LOGIN)

    @classmethod
    def tearDownClass(cls):
        gest.excluir_usuario_definitivo("master", LOGIN)

    def test_01_criar_e_obter(self):
        ok, msg = gest.criar_usuario(
            "master", LOGIN, "SenhaTeste123", perfil="comum",
            nome_completo="Teste Skyrover", exigir_telefone=False)
        self.assertTrue(ok, msg)
        linha = gest.obter_usuario(LOGIN)
        self.assertIsNotNone(linha)
        self.assertEqual(linha[1], LOGIN)
        self.assertEqual(linha[5], "comum")

    def test_02_busca_encontra(self):
        gest.criar_usuario(
            "master", LOGIN, "SenhaTeste123", perfil="comum",
            nome_completo="Teste Skyrover", exigir_telefone=False)
        resultado = gest.buscar_usuarios(termo=LOGIN)
        if isinstance(resultado, tuple):
            resultado = resultado[0]
        nomes = [r[1] if isinstance(r, (tuple, list)) else r
                 for r in resultado]
        self.assertIn(LOGIN, nomes)

    def test_03_bloquear_e_desbloquear(self):
        gest.criar_usuario(
            "master", LOGIN, "SenhaTeste123", perfil="comum",
            nome_completo="Teste Skyrover", exigir_telefone=False)
        ok, msg = gest.bloquear_usuario("master", LOGIN, True)
        self.assertTrue(ok, msg)
        self.assertEqual(gest.obter_usuario(LOGIN)[6], 0)
        ok, msg = gest.bloquear_usuario("master", LOGIN, False)
        self.assertTrue(ok, msg)
        self.assertEqual(gest.obter_usuario(LOGIN)[6], 1)

    def test_04_excluir_definitivo(self):
        gest.criar_usuario(
            "master", LOGIN, "SenhaTeste123", perfil="comum",
            nome_completo="Teste Skyrover", exigir_telefone=False)
        ok, msg = gest.excluir_usuario_definitivo("master", LOGIN)
        self.assertTrue(ok, msg)
        self.assertIsNone(gest.obter_usuario(LOGIN))


if __name__ == "__main__":
    unittest.main(verbosity=2)
