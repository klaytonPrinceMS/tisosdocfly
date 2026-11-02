# -*- coding: utf-8 -*-
"""Prova o módulo Perímetro com banco próprio (db_mod_perimetro.db).

O que este teste garante: schema SQLite portável e idempotente; criação,
listagem, obtenção e conclusão de auditoria; achados com revisão humana;
importação de varredura RF com BSSID apenas em hash SHA-256; resumo por
severidade e indicadores RF. Não sobe servidor nem roda a suíte completa.
"""
import hashlib
import os
import sqlite3
import sys
import time
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
os.environ.setdefault("SKYROVER_DIR_BANCO", "/tmp/opencode/bd_perimetro")
os.environ.setdefault("SKYROVER_DIR_MIDIA", "/tmp/opencode/midia_perimetro")
os.environ.setdefault("SKYROVER_QA_SEM_TROCA", "1")
os.environ["SKYROVER_FORCE_SQLITE"] = "1"

from mod_skyrover import repositorio

# Defensivo: a chave já está em MODULOS_BD; o setdefault mantém o teste
# standalone mesmo se o módulo for movido ou a integração for revertida.
repositorio.MODULOS_BD.setdefault("perimetro", "db_mod_perimetro.db")

from mod_skyrover.bd_criador import inicializar_bancos
from mod_skyrover import voos
from mod_perimetro import bd_manipulador as bd


class TestPerimetro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inicializar_bancos()
        assert bd.init_db(), "init_db do Perímetro falhou"
        cls.cliente_id = voos.criar_cliente(
            "Cliente Perimetro Teste", documento="000", ator="teste")
        cls.propriedade_id = voos.criar_propriedade(
            cls.cliente_id, "Propriedade Perimetro Teste", ator="teste")
        cls.voo_id = voos.criar_voo(
            cls.cliente_id, cls.propriedade_id,
            data_voo="2026-11-02", piloto="Piloto Teste",
            drone="Skyrover X1", ator="teste")
        cls.marca = f"Teste {time.time_ns()}"

    def _nova_auditoria(self, tipo="perimetro"):
        ok, aid = bd.criar_auditoria(
            "teste", self.voo_id, local=f"{self.marca} · sede",
            tipo=tipo, resumo="Escopo de teste")
        self.assertTrue(ok, aid)
        self.assertIsInstance(aid, int)
        return aid

    def test_init_idempotente_e_conexao(self):
        self.assertTrue(bd.init_db())
        self.assertTrue(bd.init_db())
        conn = bd.get_connection()
        self.assertIsNotNone(conn)
        try:
            conn.execute("SELECT 1 FROM tb_perimetro_auditoria LIMIT 1")
        finally:
            conn.close()

    def test_criar_listar_obter_e_status(self):
        aid = self._nova_auditoria()
        encontradas = bd.listar_auditorias(self.marca)
        self.assertTrue(encontradas)
        self.assertIn(aid, [linha[0] for linha in encontradas])
        linha = bd.obter_auditoria(aid)
        self.assertIsNotNone(linha)
        self.assertEqual(linha[1], self.voo_id)
        self.assertEqual(linha[2], self.cliente_id)
        self.assertEqual(linha[3], self.propriedade_id)
        self.assertEqual(linha[5], "perimetro")
        self.assertEqual(linha[6], "rascunho")

        ok, msg = bd.atualizar_status(aid, "em_revisao")
        self.assertTrue(ok, msg)
        self.assertEqual(bd.obter_auditoria(aid)[6], "em_revisao")
        ok, msg = bd.atualizar_status(aid, "concluido", "Laudo concluído")
        self.assertTrue(ok, msg)
        self.assertEqual(bd.obter_auditoria(aid)[6], "concluido")
        self.assertEqual(bd.obter_auditoria(aid)[7], "Laudo concluído")

        ok, msg = bd.atualizar_status(aid, "invalido")
        self.assertFalse(ok)
        self.assertEqual(msg, "Status inválido")

    def test_validacoes_de_criacao(self):
        ok, msg = bd.criar_auditoria("teste", None)
        self.assertFalse(ok)
        self.assertEqual(msg, "Selecione um voo")
        ok, msg = bd.criar_auditoria("teste", self.voo_id, tipo="invalido")
        self.assertFalse(ok)
        self.assertEqual(msg, "Tipo de auditoria inválido")
        ok, msg = bd.adicionar_achado("teste", 1, "classe_invalida")
        self.assertFalse(ok)
        self.assertEqual(msg, "Classe inválida")

    def test_achados_e_revisao_humana(self):
        aid = self._nova_auditoria()
        antes = bd.resumo()
        ok, achado_id = bd.adicionar_achado(
            "teste", aid, "ponto_cego_camera", "alta", 0.81, 0,
            "Câmera 3 sem alcance no canto nordeste", -23.501, -46.602)
        self.assertTrue(ok, achado_id)
        achados = bd.listar_achados(aid)
        self.assertEqual(len(achados), 1)
        linha = achados[0]
        self.assertEqual(linha[2], "ponto_cego_camera")
        self.assertEqual(linha[3], "alta")
        self.assertAlmostEqual(float(linha[4]), 0.81)
        self.assertEqual(linha[5], 0)
        self.assertAlmostEqual(float(linha[7]), -23.501)
        self.assertAlmostEqual(float(linha[8]), -46.602)

        depois = bd.resumo()
        self.assertEqual(depois["achados"], antes["achados"] + 1)
        self.assertEqual(depois["alta"], antes["alta"] + 1)
        self.assertGreaterEqual(depois["pendentes_revisao"],
                                antes["pendentes_revisao"] + 1)

        self.assertTrue(bd.marcar_revisao(achado_id, True))
        self.assertEqual(bd.listar_achados(aid)[0][5], 1)
        final = bd.resumo()
        self.assertEqual(final["pendentes_revisao"],
                         depois["pendentes_revisao"] - 1)

    def test_importar_rf_sem_bssid_cru(self):
        aid = self._nova_auditoria(tipo="rf")
        antes = bd.resumo()
        registros = [
            {"ssid": "RedeTeste-A", "bssid": "AA:BB:CC:DD:EE:20",
             "canal": 6, "rssi": -45, "seguranca": "aberta",
             "fora_perimetro": 1, "latitude": -23.5, "longitude": -46.6},
            {"ssid": "RedeTeste-B", "bssid": "AA:BB:CC:DD:EE:21",
             "canal": 36, "rssi": -70, "seguranca": "WPA2"},
        ]
        ok, importados = bd.importar_rf("teste", aid, registros)
        self.assertTrue(ok, importados)
        self.assertEqual(importados, 2)

        redes = bd.listar_rf(aid)
        self.assertEqual(len(redes), 2)
        primeira = redes[0]
        self.assertEqual(primeira[2], "RedeTeste-A")
        self.assertEqual(
            primeira[3],
            hashlib.sha256(b"aa:bb:cc:dd:ee:20").hexdigest())
        self.assertEqual(len(primeira[3]), 64)
        self.assertEqual(primeira[4], "2.4GHz")
        self.assertEqual(primeira[7], "aberta")
        self.assertEqual(primeira[8], 1)
        self.assertEqual(primeira[9], "critico")
        self.assertNotIn("AA:BB:CC:DD:EE:20", str(primeira))
        self.assertNotIn("AA:BB:CC:DD:EE:21", str(redes[1]))

        depois = bd.resumo()
        self.assertEqual(depois["rf_total"], antes["rf_total"] + 2)
        self.assertEqual(depois["rf_abertas"], antes["rf_abertas"] + 1)
        self.assertEqual(depois["fora_perimetro"],
                         antes["fora_perimetro"] + 1)

        ok, msg = bd.importar_rf("teste", aid, [{}])
        self.assertFalse(ok)
        self.assertEqual(msg, "Nenhum registro RF válido")

    def test_adicionar_rf_normaliza_bruto(self):
        aid = self._nova_auditoria(tipo="rf")
        ok, rid = bd.adicionar_rf(
            "teste", aid,
            {"ssid": "RedeDireta", "bssid": "AA-BB-CC-DD-EE-22",
             "banda": "5GHz", "canal": 44, "rssi": -55,
             "seguranca": "WEP"})
        self.assertTrue(ok, rid)
        linha = bd.listar_rf(aid)[0]
        self.assertEqual(linha[3],
                         hashlib.sha256(b"aa:bb:cc:dd:ee:22").hexdigest())
        self.assertEqual(linha[7], "wep")
        self.assertEqual(linha[9], "alto")

    def test_schema_sqlite(self):
        caminho = repositorio.caminho_db("perimetro")
        self.assertTrue(os.path.isfile(caminho), caminho)
        self.assertTrue(caminho.endswith("db_mod_perimetro.db"), caminho)
        esperado = {
            "tb_perimetro_auditoria": {
                "id", "voo_id", "cliente_id", "propriedade_id", "local",
                "tipo", "status", "resumo", "criado_por", "criado_em"},
            "tb_perimetro_achado": {
                "id", "auditoria_id", "classe", "severidade", "confianca",
                "revisao_humana", "evidencia", "latitude", "longitude",
                "criado_em"},
            "tb_perimetro_rf": {
                "id", "auditoria_id", "ssid", "bssid_hash", "banda",
                "canal", "rssi", "seguranca", "fora_perimetro", "risco",
                "evidencia", "criado_em"},
        }
        conn = sqlite3.connect(caminho)
        try:
            for tabela, colunas in esperado.items():
                info = conn.execute(
                    f"PRAGMA table_info({tabela})").fetchall()
                nomes = {linha[1] for linha in info}
                self.assertEqual(colunas, nomes, tabela)
            tipos = {linha[1]: linha[2] for linha in conn.execute(
                "PRAGMA table_info(tb_perimetro_rf)").fetchall()}
            self.assertEqual(tipos["fora_perimetro"], "INTEGER")
        finally:
            conn.close()

    def test_resumo_completo(self):
        r = bd.resumo()
        for chave in ("total", "rascunho", "em_revisao", "concluido",
                      "achados", "baixa", "media", "alta", "critica",
                      "pendentes_revisao", "rf_total", "rf_abertas",
                      "fora_perimetro"):
            self.assertIn(chave, r)
            self.assertGreaterEqual(int(r[chave]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
