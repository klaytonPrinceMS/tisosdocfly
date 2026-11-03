# -*- coding: utf-8 -*-
"""Prova o MVP dos módulos Ambiental, Obras e Mapeamento com banco próprio.

EN: Exercises the full CRUD, conclusion and schema of the three Onda 5A
modules using an isolated database directory.

PT-BR: O que este teste garante: cliente/propriedade/voo são criados pela API
pública do núcleo; cada módulo cria/lista sua análise, registra uma
ocorrência/produto, conclui o laudo e expõe resumo e schema no banco próprio.
Não garante IA, geoprocessamento nem geração de PDF.
"""
import os
import sqlite3
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
os.environ.setdefault("TISOSDOCFLY_DIR_BANCO", "/tmp/opencode/bd_onda5a")
os.environ.setdefault("TISOSDOCFLY_QA_SEM_TROCA", "1")
os.environ.setdefault("TISOSDOCFLY_FORCE_SQLITE", "1")

from mod_tisosdocfly import voos
from mod_tisosdocfly.bd_conexao import init_db as init_central
from mod_tisosdocfly.bd_manipulador import garantir_rastreabilidade
from mod_ambiental import bd_manipulador as ambiental
from mod_obras import bd_manipulador as obras
from mod_mapeamento import bd_manipulador as mapeamento


class TestModulosOnda5A(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_central()
        garantir_rastreabilidade()
        for modulo in (ambiental, obras, mapeamento):
            assert modulo.init_db(), modulo.CHAVE_MODULO
        cls.cliente_id = voos.criar_cliente(
            "Cliente Onda 5A", documento="000", ator="teste")
        assert cls.cliente_id, "cliente de teste não criado"
        cls.propriedade_id = voos.criar_propriedade(
            cls.cliente_id, "Propriedade Onda 5A", ator="teste")
        assert cls.propriedade_id, "propriedade de teste não criada"
        cls.voo_id = voos.criar_voo(
            cls.cliente_id, cls.propriedade_id, data_voo="2026-11-02",
            piloto="Piloto Teste", drone="Drone Modelo Ficticio", gsd_cm=2.5,
            ator="teste")
        assert cls.voo_id, "voo de teste não criado"

    def test_ambiental_crud(self):
        ok, aid = ambiental.criar_analise(
            "teste", self.voo_id, area=12.5, tipo="desmatamento",
            resumo="Polígono de teste")
        self.assertTrue(ok, aid)
        self.assertIsInstance(aid, int)
        linha = ambiental.obter_analise(aid)
        self.assertIsNotNone(linha)
        self.assertEqual(linha[1], self.voo_id)
        self.assertEqual(linha[2], self.cliente_id)
        self.assertEqual(linha[3], self.propriedade_id)
        self.assertAlmostEqual(float(linha[4]), 12.5)
        self.assertEqual(linha[5], "desmatamento")
        self.assertEqual(linha[6], "rascunho")
        self.assertIn(aid, [r[0] for r in ambiental.listar_analises(
            "desmatamento")])

        ok, oid = ambiental.adicionar_ocorrencia(
            "teste", aid, "desmatamento", "alta", 1500, 0.91, 0,
            "Comparativo antes/depois")
        self.assertTrue(ok, oid)
        ocorrencias = ambiental.listar_ocorrencias(aid)
        self.assertEqual(len(ocorrencias), 1)
        self.assertEqual(ocorrencias[0][2], "desmatamento")
        self.assertEqual(ocorrencias[0][3], "alta")
        self.assertAlmostEqual(float(ocorrencias[0][4]), 1500.0)
        self.assertEqual(ocorrencias[0][6], 0)

        self.assertTrue(ambiental.marcar_revisao(oid, True))
        self.assertEqual(ambiental.listar_ocorrencias(aid)[0][6], 1)
        self.assertEqual(ambiental.resumo()["pendentes_revisao"], 0)

        ok, _ = ambiental.atualizar_status(aid, "em_revisao")
        self.assertTrue(ok)
        self.assertEqual(ambiental.obter_analise(aid)[6], "em_revisao")
        ok, _ = ambiental.atualizar_status(
            aid, "concluido", "Laudo ambiental concluído")
        self.assertTrue(ok)
        self.assertEqual(ambiental.obter_analise(aid)[6], "concluido")
        self.assertEqual(ambiental.obter_analise(aid)[7],
                         "Laudo ambiental concluído")
        r = ambiental.resumo()
        self.assertGreaterEqual(r["total"], 1)
        self.assertGreaterEqual(r["concluido"], 1)
        self.assertGreaterEqual(r["ocorrencias"], 1)

    def test_obras_crud(self):
        ok, aid = obras.criar_analise(
            "teste", self.voo_id, obra="Bloco A", etapa="estrutura",
            progresso_pct=42.5, resumo="Laje do 2º pavimento")
        self.assertTrue(ok, aid)
        self.assertIsInstance(aid, int)
        linha = obras.obter_analise(aid)
        self.assertIsNotNone(linha)
        self.assertEqual(linha[1], self.voo_id)
        self.assertEqual(linha[2], self.cliente_id)
        self.assertEqual(linha[3], self.propriedade_id)
        self.assertEqual(linha[4], "Bloco A")
        self.assertEqual(linha[5], "estrutura")
        self.assertAlmostEqual(float(linha[6]), 42.5)
        self.assertEqual(linha[7], "rascunho")
        self.assertIn(aid, [r[0] for r in obras.listar_analises("Bloco A")])

        ok, oid = obras.adicionar_ocorrencia(
            "teste", aid, "atraso", "media", 0, 0.84, 1,
            "Concreto entregue com atraso")
        self.assertTrue(ok, oid)
        ocorrencias = obras.listar_ocorrencias(aid)
        self.assertEqual(len(ocorrencias), 1)
        self.assertEqual(ocorrencias[0][2], "atraso")
        self.assertEqual(ocorrencias[0][3], "media")
        self.assertEqual(ocorrencias[0][6], 1)

        ok, _ = obras.atualizar_status(
            aid, "concluido", "Laudo de obra concluído")
        self.assertTrue(ok)
        self.assertEqual(obras.obter_analise(aid)[7], "concluido")
        r = obras.resumo()
        self.assertGreaterEqual(r["total"], 1)
        self.assertGreaterEqual(r["concluido"], 1)
        # O resumo é GLOBAL e a suíte compartilha o banco entre execuções;
        # o progresso da linha criada já foi conferido acima (42.5).
        self.assertGreaterEqual(r["progresso_medio"], 0)

    def test_mapeamento_crud(self):
        ok, aid = mapeamento.criar_analise(
            "teste", self.voo_id, area_ha=25.4, gsd_cm=2.5,
            tipo="ortomosaico", resumo="Voo de cobertura total")
        self.assertTrue(ok, aid)
        self.assertIsInstance(aid, int)
        linha = mapeamento.obter_analise(aid)
        self.assertIsNotNone(linha)
        self.assertEqual(linha[1], self.voo_id)
        self.assertEqual(linha[2], self.cliente_id)
        self.assertEqual(linha[3], self.propriedade_id)
        self.assertAlmostEqual(float(linha[4]), 25.4)
        self.assertAlmostEqual(float(linha[5]), 2.5)
        self.assertEqual(linha[6], "ortomosaico")
        self.assertEqual(linha[7], "rascunho")
        self.assertIn(aid, [r[0] for r in mapeamento.listar_analises(
            "ortomosaico")])

        ok, pid = mapeamento.adicionar_produto(
            "teste", aid, "ortomosaico_voo.tif", "geotiff",
            "/tmp/opencode/produtos/ortomosaico_voo.tif", "a" * 64, 0.95)
        self.assertTrue(ok, pid)
        produtos = mapeamento.listar_produtos(aid)
        self.assertEqual(len(produtos), 1)
        self.assertEqual(produtos[0][2], "ortomosaico_voo.tif")
        self.assertEqual(produtos[0][3], "geotiff")
        self.assertEqual(produtos[0][5], "a" * 64)
        self.assertAlmostEqual(float(produtos[0][6]), 0.95)

        ok, _ = mapeamento.atualizar_status(
            aid, "concluido", "Laudo de mapeamento concluído")
        self.assertTrue(ok)
        self.assertEqual(mapeamento.obter_analise(aid)[7], "concluido")
        r = mapeamento.resumo()
        self.assertGreaterEqual(r["total"], 1)
        self.assertGreaterEqual(r["concluido"], 1)
        self.assertGreaterEqual(r["produtos"], 1)

    def test_schema_de_cada_banco(self):
        base = os.environ["TISOSDOCFLY_DIR_BANCO"]
        esperado = {
            "db_mod_ambiental.db": {
                "tb_ambiental_analise": {
                    "id", "voo_id", "cliente_id", "propriedade_id", "area",
                    "tipo", "status", "resumo", "criado_por", "criado_em",
                },
                "tb_ambiental_ocorrencia": {
                    "id", "analise_id", "classe", "severidade", "area_m2",
                    "confianca", "revisao_humana", "evidencia", "criado_em",
                },
            },
            "db_mod_obras.db": {
                "tb_obras_analise": {
                    "id", "voo_id", "cliente_id", "propriedade_id", "obra",
                    "etapa", "progresso_pct", "status", "resumo",
                    "criado_por", "criado_em",
                },
                "tb_obras_ocorrencia": {
                    "id", "analise_id", "classe", "severidade", "area_m2",
                    "confianca", "revisao_humana", "evidencia", "criado_em",
                },
            },
            "db_mod_mapeamento.db": {
                "tb_mapeamento_analise": {
                    "id", "voo_id", "cliente_id", "propriedade_id",
                    "area_ha", "gsd_cm", "tipo", "status", "resumo",
                    "criado_por", "criado_em",
                },
                "tb_mapeamento_produto": {
                    "id", "analise_id", "nome", "tipo", "caminho",
                    "hash_sha256", "confianca", "criado_em",
                },
            },
        }
        for arquivo, tabelas in esperado.items():
            caminho = os.path.join(base, arquivo)
            self.assertTrue(os.path.isfile(caminho), arquivo)
            conn = sqlite3.connect(caminho)
            try:
                nomes = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                for tabela, colunas in tabelas.items():
                    self.assertIn(tabela, nomes, f"{arquivo}:{tabela}")
                    existentes = {r[1] for r in conn.execute(
                        f"PRAGMA table_info({tabela})")}
                    self.assertTrue(colunas.issubset(existentes),
                                    f"{arquivo}:{tabela} -> "
                                    f"{colunas - existentes}")
            finally:
                conn.close()

    def test_referencias_ao_voo(self):
        """Cada banco guarda só IDs e nenhum cruza com o banco do núcleo."""
        base = os.environ["TISOSDOCFLY_DIR_BANCO"]
        amostras = (
            ("db_mod_ambiental.db", "tb_ambiental_analise",
             ambiental.criar_analise(
                 "teste", self.voo_id, area=1, tipo="outro")),
            ("db_mod_obras.db", "tb_obras_analise",
             obras.criar_analise("teste", self.voo_id, obra="Amostra")),
            ("db_mod_mapeamento.db", "tb_mapeamento_analise",
             mapeamento.criar_analise(
                 "teste", self.voo_id, area_ha=1, gsd_cm=1,
                 tipo="outro")),
        )
        for arquivo, tabela, (ok, analise_id) in amostras:
            self.assertTrue(ok, f"{arquivo}: {analise_id}")
            conn = sqlite3.connect(os.path.join(base, arquivo))
            try:
                linhas = conn.execute(
                    f"SELECT voo_id, cliente_id, propriedade_id "
                    f"FROM {tabela} WHERE id=?", (analise_id,)).fetchall()
            finally:
                conn.close()
            self.assertEqual(len(linhas), 1, arquivo)
            voo_id, cliente_id, propriedade_id = linhas[0]
            self.assertEqual(int(voo_id), self.voo_id)
            self.assertEqual(int(cliente_id), self.cliente_id)
            self.assertEqual(int(propriedade_id), self.propriedade_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
