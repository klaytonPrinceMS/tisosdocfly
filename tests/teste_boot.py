# -*- coding: utf-8 -*-
"""Prova que o boot cria os dois bancos e as contas de fábrica.

O que este teste garante: `inicializar_bancos()` cria o schema central, o
schema de usuários e o seed `master`/`qacomum`/`qamaster`, e a auditoria
central grava. Não garante nada sobre telas.
"""
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
os.environ.setdefault("TISOSDOCFLY_DIR_BANCO", os.path.join(
    RAIZ, "tests", "_bd_teste"))
os.environ.setdefault("TISOSDOCFLY_QA_SEM_TROCA", "1")

from mod_tisosdocfly.bd_criador import inicializar_bancos
from mod_tisosdocfly.bd_manipulador import audit_log
from mod_tisosdocfly.bd_conexao import get_connection
from mod_tisosdocfly.repositorio import MODULOS_BD
from mod_gest_cad_usuario import bd_manipulador as gest


class TestBoot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inicializar_bancos()

    def test_cria_os_bancos_dos_modulos(self):
        self.assertEqual(set(MODULOS_BD), {
            "tisosdocfly", "usuarios", "agro", "vistoria_predial",
            "seguranca", "ambiental", "obras", "mapeamento",
            "defesa_civil", "inspecao_industrial", "eventos",
            "perimetro"})
        for arquivo in MODULOS_BD.values():
            caminho = os.path.join(
                os.environ["TISOSDOCFLY_DIR_BANCO"], arquivo)
            self.assertTrue(os.path.isfile(caminho), caminho)

    def test_seed_das_tres_contas(self):
        for login in ("master", "qacomum", "qamaster"):
            linha = gest.obter_usuario(login)
            self.assertIsNotNone(linha, login)
            self.assertEqual(linha[1], login)

    def test_auditoria_central_grava(self):
        audit_log("teste", "tisosdocfly", "teste_boot", "linha de teste")
        conn = get_connection()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM tb_auditoria "
                "WHERE acao='teste_boot'").fetchone()[0]
        finally:
            conn.close()
        self.assertGreaterEqual(total, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
