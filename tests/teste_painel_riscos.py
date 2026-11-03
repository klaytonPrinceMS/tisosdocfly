# -*- coding: utf-8 -*-
"""Prova o painel de riscos (agregação por API pública, sem cross-query).

Cria uma análise na Defesa Civil, chama `coletar()` e confere que o total do
módulo aparece no resumo. Não testa a tela.
"""
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
os.environ.setdefault("TISOSDOCFLY_DIR_BANCO", "/tmp/opencode/bd_riscos")
os.environ.setdefault("TISOSDOCFLY_DIR_MIDIA", "/tmp/opencode/bd_riscos/midia")
os.environ.setdefault("TISOSDOCFLY_QA_SEM_TROCA", "1")

from mod_tisosdocfly.bd_criador import inicializar_bancos
from mod_tisosdocfly import voos
from mod_tisosdocfly.painel_riscos import coletar
from mod_defesa_civil import bd_manipulador as dc


class TestPainelRiscos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inicializar_bancos()
        cls.cliente = voos.criar_cliente("Cliente Risco", ator="teste")
        cls.prop = voos.criar_propriedade(
            cls.cliente, "Área de Risco", ator="teste")
        cls.voo = voos.criar_voo(
            cls.cliente, cls.prop, data_voo="2026-11-02", ator="teste")

    def test_coleta_todos_os_modulos(self):
        dados = coletar()
        self.assertEqual(len(dados["modulos"]), 6)
        chaves = {m["chave"] for m in dados["modulos"]}
        self.assertEqual(chaves, {
            "defesa_civil", "ambiental", "obras", "seguranca",
            "inspecao_industrial", "perimetro"})
        self.assertIn("total_analises", dados)

    def test_reflete_analise_da_defesa_civil(self):
        dc.init_db()
        ok, aid = dc.criar_analise(
            "teste", self.voo, local="Encosta", tipo="deslizamento",
            resumo="Vistoria de risco")
        self.assertTrue(ok, aid)
        dados = coletar()
        item = next(m for m in dados["modulos"]
                    if m["chave"] == "defesa_civil")
        self.assertGreaterEqual(item["total"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
