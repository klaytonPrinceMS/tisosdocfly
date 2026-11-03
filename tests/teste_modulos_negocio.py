# -*- coding: utf-8 -*-
"""Prova o MVP dos três módulos de negócio, com banco próprio.

O que este teste garante: `inicializar_bancos()` cria os bancos de agro,
vistoria predial e segurança; cada módulo cria/lista sua análise, registra uma
ocorrência/patologia e conclui o laudo; os bancos são independentes e o núcleo
de voos é usado pela API pública. Não garante IA nem análise de imagem.
"""
import os
import sqlite3
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
os.environ.setdefault("TISOSDOCFLY_DIR_BANCO", "/tmp/opencode/bd_modulos")
os.environ.setdefault("TISOSDOCFLY_QA_SEM_TROCA", "1")

from mod_tisosdocfly.bd_criador import inicializar_bancos
from mod_tisosdocfly import voos
from mod_tisosdocfly.repositorio import MODULOS_BD
from mod_agro import bd_manipulador as agro
from mod_vistoria_predial import bd_manipulador as vistoria
from mod_seguranca import bd_manipulador as seguranca


class TestModulosNegocio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inicializar_bancos()
        cls.cliente_id = voos.criar_cliente(
            "Cliente Teste", documento="000", ator="teste")
        cls.propriedade_id = voos.criar_propriedade(
            cls.cliente_id, "Propriedade Teste", ator="teste")
        cls.voo_id = voos.criar_voo(
            cls.cliente_id, cls.propriedade_id,
            data_voo="2026-11-02", piloto="Piloto Teste",
            drone="Drone Modelo Ficticio", ator="teste")

    def test_bancos_independentes(self):
        self.assertEqual(set(MODULOS_BD), {
            "tisosdocfly", "usuarios", "agro", "vistoria_predial",
            "seguranca", "ambiental", "obras", "mapeamento",
            "defesa_civil", "inspecao_industrial", "eventos",
            "perimetro"})
        base = os.environ["TISOSDOCFLY_DIR_BANCO"]
        for arquivo in ("db_mod_agro.db", "db_mod_vistoria_predial.db",
                        "db_mod_seguranca.db"):
            self.assertTrue(os.path.isfile(os.path.join(base, arquivo)),
                            arquivo)

    def test_agro_crud(self):
        ok, aid = agro.criar_analise(
            "teste", self.voo_id, talhao="T1", cultura="soja",
            indice="NDVI", area_ha=12.5, resultado="Estresse leve")
        self.assertTrue(ok, aid)
        self.assertTrue(agro.listar_analises("T1"))
        ok, oid = agro.adicionar_ocorrencia(
            "teste", aid, "estresse_metabolico", "media", 100, 0.82)
        self.assertTrue(ok, oid)
        self.assertEqual(len(agro.listar_ocorrencias(aid)), 1)
        ok, _ = agro.atualizar_status(aid, "concluido", "Laudo pronto")
        self.assertTrue(ok)
        self.assertGreaterEqual(agro.resumo()["concluido"], 1)

        # Pecuária (Embrapa, 2024): rebanho/pastagem com contagem declarada.
        ok, rid = agro.criar_analise(
            "teste", self.voo_id, talhao="Piquete 3", cultura="pastagem",
            tipo_analise="rebanho", cabecas_estimadas=120,
            area_pastagem_ha=45.5, finalidade="seguro_agricola",
            perda_estimada_pct=8.5, area_afetada_ha=3.2,
            resultado="Contagem revisada em campo")
        self.assertTrue(ok, rid)
        linha = agro.obter_analise(rid)
        self.assertEqual(linha[13], "rebanho")
        self.assertEqual(linha[14], 120)
        self.assertAlmostEqual(float(linha[15]), 45.5)
        self.assertEqual(linha[16], "seguro_agricola")
        self.assertAlmostEqual(float(linha[17]), 8.5)
        self.assertAlmostEqual(float(linha[18]), 3.2)
        ok, oid = agro.adicionar_ocorrencia(
            "teste", rid, "contagem_gado", "baixa", 0, 0.99, 1,
            "120 cabeças contadas na imagem e conferidas em campo")
        self.assertTrue(ok, oid)
        self.assertGreaterEqual(agro.resumo()["cabecas"], 120)

    def test_vistoria_crud(self):
        ok, vid = vistoria.criar_vistoria(
            "teste", self.voo_id, imovel="Rua A, 100", tipo="fachada")
        self.assertTrue(ok, vid)
        self.assertTrue(vistoria.listar_vistorias("Rua A"))
        ok, pid = vistoria.adicionar_patologia(
            "teste", vid, "trinca", "alta", 2.4, "Fissura na fachada")
        self.assertTrue(ok, pid)
        self.assertEqual(len(vistoria.listar_patologias(vid)), 1)
        ok, _ = vistoria.atualizar_status(vid, "concluido", "Laudo pronto")
        self.assertTrue(ok)
        self.assertGreaterEqual(vistoria.resumo()["concluido"], 1)

    def test_seguranca_crud(self):
        ok, sid = seguranca.criar_analise(
            "teste", self.voo_id, tipo="aglomeracao", nivel_risco="alto")
        self.assertTrue(ok, sid)
        self.assertTrue(seguranca.listar_analises("aglomeracao"))
        ok, oid = seguranca.adicionar_ocorrencia(
            "teste", sid, "aglomeracao", 42, 0.77, 0,
            "Ponto de alta densidade")
        self.assertTrue(ok, oid)
        self.assertEqual(len(seguranca.listar_ocorrencias(sid)), 1)
        self.assertTrue(seguranca.marcar_revisao(oid, True))
        self.assertEqual(seguranca.resumo()["pendentes_revisao"], 0)
        ok, _ = seguranca.atualizar_status(sid, "concluido", "Triagem pronta")
        self.assertTrue(ok)

    def test_schema_de_cada_banco(self):
        base = os.environ["TISOSDOCFLY_DIR_BANCO"]
        esperado = {
            "db_mod_agro.db": ("tb_agro_analise", "tb_agro_ocorrencia"),
            "db_mod_vistoria_predial.db": (
                "tb_vistoria", "tb_vistoria_patologia"),
            "db_mod_seguranca.db": (
                "tb_seguranca_analise", "tb_seguranca_ocorrencia"),
        }
        for arquivo, tabelas in esperado.items():
            conn = sqlite3.connect(os.path.join(base, arquivo))
            try:
                nomes = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
            finally:
                conn.close()
            for tabela in tabelas:
                self.assertIn(tabela, nomes, f"{arquivo}:{tabela}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
