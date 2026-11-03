# -*- coding: utf-8 -*-
"""Prova o MVP da onda 5b: Defesa Civil, Inspeção Industrial e Eventos.

O que este teste garante: cada módulo tem banco próprio, cria/lista análise,
registra ocorrência, marca revisão humana e conclui o laudo; cliente,
propriedade e voo vêm da API pública de `mod_tisosdocfly.voos`; o schema de cada
banco existe de fato em SQLite. Não garante IA, geoprocessamento nem PDF.
"""
import os
import sqlite3
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
os.environ.setdefault("TISOSDOCFLY_DIR_BANCO", "/tmp/opencode/bd_onda5b")
os.environ.setdefault("TISOSDOCFLY_QA_SEM_TROCA", "1")

from mod_tisosdocfly.bd_conexao import init_db as init_central
from mod_tisosdocfly.bd_manipulador import garantir_rastreabilidade
from mod_tisosdocfly import voos
from mod_defesa_civil import bd_manipulador as defesa_civil
from mod_inspecao_industrial import bd_manipulador as inspecao
from mod_eventos import bd_manipulador as eventos

MODULOS = (defesa_civil, inspecao, eventos)


class TestModulosOnda5B(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Só o schema central (voos/auditoria) e os três bancos desta onda:
        # o teste não depende de módulos de outras ondas.
        init_central()
        garantir_rastreabilidade()
        falhas = [m.CHAVE_MODULO for m in MODULOS if not m.init_db()]
        if falhas:
            raise RuntimeError(f"init_db falhou: {', '.join(falhas)}")
        cls.cliente_id = voos.criar_cliente(
            "Cliente Onda 5B", documento="000", ator="teste")
        cls.propriedade_id = voos.criar_propriedade(
            cls.cliente_id, "Propriedade Onda 5B", ator="teste")
        cls.voo_id = voos.criar_voo(
            cls.cliente_id, cls.propriedade_id,
            data_voo="2026-11-02", piloto="Piloto Teste",
            drone="Drone Modelo Ficticio", ator="teste")

    def test_defesa_civil_crud(self):
        ok, aid = defesa_civil.criar_analise(
            "teste", self.voo_id, local="Bairro das Palmeiras",
            tipo="enchente", resumo="Voo pós-chuva")
        self.assertTrue(ok, aid)
        self.assertIsNotNone(defesa_civil.obter_analise(aid))
        self.assertTrue(defesa_civil.listar_analises("Palmeiras"))

        ok, oid = defesa_civil.adicionar_ocorrencia(
            "teste", aid, "via_bloqueada", "alta", 120.5, 0.91, 0,
            "Rua principal alagada")
        self.assertTrue(ok, oid)
        ocorrencias = defesa_civil.listar_ocorrencias(aid)
        self.assertEqual(len(ocorrencias), 1)
        self.assertEqual(ocorrencias[0][2], "via_bloqueada")
        self.assertEqual(ocorrencias[0][3], "alta")

        self.assertTrue(defesa_civil.marcar_revisao(oid, True))
        revisada = defesa_civil.listar_ocorrencias(aid)[0]
        self.assertEqual(int(revisada[6]), 1)

        ok, _ = defesa_civil.atualizar_status(
            aid, "concluido", "Laudo de defesa civil pronto")
        self.assertTrue(ok)
        self.assertEqual(defesa_civil.obter_analise(aid)[6], "concluido")
        r = defesa_civil.resumo()
        self.assertGreaterEqual(r["total"], 1)
        self.assertGreaterEqual(r["concluido"], 1)
        self.assertGreaterEqual(r["ocorrencias"], 1)

    def test_inspecao_industrial_crud(self):
        ok, aid = inspecao.criar_analise(
            "teste", self.voo_id, ativo="TQ-202", tipo="tanque",
            resumo="Inspeção de tanque de processo")
        self.assertTrue(ok, aid)
        self.assertIsNotNone(inspecao.obter_analise(aid))
        self.assertTrue(inspecao.listar_analises("TQ-202"))

        ok, oid = inspecao.adicionar_ocorrencia(
            "teste", aid, "corrosao", "critica", 3.2, 0.88, 0,
            "Corrosão na base do tanque")
        self.assertTrue(ok, oid)
        ocorrencias = inspecao.listar_ocorrencias(aid)
        self.assertEqual(len(ocorrencias), 1)
        self.assertEqual(ocorrencias[0][2], "corrosao")
        self.assertEqual(ocorrencias[0][3], "critica")

        self.assertTrue(inspecao.marcar_revisao(oid, True))
        self.assertEqual(
            int(inspecao.listar_ocorrencias(aid)[0][6]), 1)

        ok, _ = inspecao.atualizar_status(
            aid, "concluido", "Laudo de inspeção pronto")
        self.assertTrue(ok)
        self.assertEqual(inspecao.obter_analise(aid)[6], "concluido")
        r = inspecao.resumo()
        self.assertGreaterEqual(r["total"], 1)
        self.assertGreaterEqual(r["concluido"], 1)
        self.assertGreaterEqual(r["ocorrencias"], 1)

    def test_eventos_crud(self):
        ok, aid = eventos.criar_analise(
            "teste", self.voo_id, evento="Festa da Cidade",
            tipo="multidao", publico_estimado=4800,
            resumo="Voo sobre o evento")
        self.assertTrue(ok, aid)
        self.assertIsNotNone(eventos.obter_analise(aid))
        self.assertTrue(eventos.listar_analises("Festa da Cidade"))

        ok, oid = eventos.adicionar_ocorrencia(
            "teste", aid, "saida_emergencia", "alta", 350, 0.79, 0,
            "Saída secundária obstruída")
        self.assertTrue(ok, oid)
        ocorrencias = eventos.listar_ocorrencias(aid)
        self.assertEqual(len(ocorrencias), 1)
        self.assertEqual(ocorrencias[0][2], "saida_emergencia")
        self.assertEqual(int(ocorrencias[0][4]), 350)

        self.assertTrue(eventos.marcar_revisao(oid, True))
        self.assertEqual(int(eventos.listar_ocorrencias(aid)[0][6]), 1)

        ok, _ = eventos.atualizar_status(
            aid, "concluido", "Laudo de evento pronto")
        self.assertTrue(ok)
        self.assertEqual(eventos.obter_analise(aid)[7], "concluido")
        r = eventos.resumo()
        self.assertGreaterEqual(r["total"], 1)
        self.assertGreaterEqual(r["concluido"], 1)
        self.assertGreaterEqual(r["ocorrencias"], 1)

    def test_schema_de_cada_banco(self):
        base = os.environ["TISOSDOCFLY_DIR_BANCO"]
        esperado = {
            "db_mod_defesa_civil.db": (
                "tb_defesa_civil_analise", "tb_defesa_civil_ocorrencia"),
            "db_mod_inspecao_industrial.db": (
                "tb_inspecao_analise", "tb_inspecao_ocorrencia"),
            "db_mod_eventos.db": (
                "tb_eventos_analise", "tb_eventos_ocorrencia"),
        }
        for arquivo, tabelas in esperado.items():
            caminho = os.path.join(base, arquivo)
            self.assertTrue(os.path.isfile(caminho), arquivo)
            conn = sqlite3.connect(caminho)
            try:
                nomes = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                for tabela in tabelas:
                    self.assertIn(tabela, nomes, f"{arquivo}:{tabela}")
                    colunas = {r[1] for r in conn.execute(
                        f"PRAGMA table_info({tabela})")}
                    self.assertIn("id", colunas)
                    self.assertIn("voo_id" if tabela.endswith("_analise")
                                  else "analise_id", colunas)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
