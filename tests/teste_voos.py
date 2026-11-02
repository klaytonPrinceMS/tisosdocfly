# -*- coding: utf-8 -*-
"""Prova a Onda 1 do núcleo: cliente → propriedade → voo → mídia → laudo.

O que este teste garante: o schema idempotente nasce no boot, o fluxo de
cadastro funciona por funções, o upload grava arquivo com SHA-256/nome
seguro e o laudo base é criado e listado. Não passa pela UI.
"""
import hashlib
import os
import re
import sys
import unittest
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, RAIZ)

os.environ.setdefault("SKYROVER_DIR_BANCO", "/tmp/opencode/bd_core")
os.environ.setdefault("SKYROVER_DIR_MIDIA", "/tmp/opencode/midia_core")
os.environ.setdefault("SKYROVER_FORCE_SQLITE", "1")
os.environ.setdefault("SKYROVER_QA_SEM_TROCA", "1")

from mod_skyrover.bd_criador import inicializar_bancos
from mod_skyrover.bd_conexao import get_connection
from mod_skyrover import voos

SUFIXO = datetime.now().strftime("%Y%m%d%H%M%S%f")
NOME_CLIENTE = f"Cliente Onda1 {SUFIXO}"
NOME_PROPRIEDADE = f"Propriedade Onda1 {SUFIXO}"


class TestVoosOnda1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inicializar_bancos()
        cls.cliente_id = voos.criar_cliente(
            NOME_CLIENTE, documento="DOC-FICTICIO-0001",
            email="cliente.teste@example.invalid",
            telefone="(00) 00000-0000", ator="teste_voos")
        cls.propriedade_id = voos.criar_propriedade(
            cls.cliente_id, NOME_PROPRIEDADE,
            endereco="Endereço fictício, 100",
            geometria="POLYGON((0 0, 1 0, 1 1, 0 0))",
            ator="teste_voos")
        cls.voo_id = voos.criar_voo(
            cls.cliente_id, cls.propriedade_id,
            data_voo="2026-11-02", piloto="Piloto Fictício",
            drone="Skyrover X1", gsd_cm=2.5, ator="teste_voos")

    @classmethod
    def tearDownClass(cls):
        """Remove os registros e a pasta de mídia criados pelo teste."""
        try:
            conn = get_connection()
            try:
                for sql, params in (
                        ("DELETE FROM tb_arquivos_midia WHERE voo_id=?",
                         (cls.voo_id,)),
                        ("DELETE FROM tb_capturas WHERE voo_id=?",
                         (cls.voo_id,)),
                        ("DELETE FROM tb_laudos WHERE voo_id=?",
                         (cls.voo_id,)),
                        ("DELETE FROM tb_voos WHERE id=?", (cls.voo_id,)),
                        ("DELETE FROM tb_propriedades WHERE id=?",
                         (cls.propriedade_id,)),
                        ("DELETE FROM tb_clientes WHERE id=?",
                         (cls.cliente_id,))):
                    conn.execute(sql, params)
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass
        try:
            import shutil
            shutil.rmtree(voos.diretorio_midia(cls.voo_id), ignore_errors=True)
        except Exception:
            pass

    def test_01_schema_criado(self):
        conn = get_connection()
        try:
            nomes = {linha[0] for linha in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        finally:
            conn.close()
        for tabela in ("tb_clientes", "tb_propriedades", "tb_voos",
                       "tb_capturas", "tb_arquivos_midia", "tb_laudos"):
            self.assertIn(tabela, nomes)

    def test_02_cliente_propriedade_voo(self):
        self.assertIsNotNone(self.cliente_id)
        self.assertIsNotNone(self.propriedade_id)
        self.assertIsNotNone(self.voo_id)

        cliente = voos.obter_cliente(self.cliente_id)
        self.assertEqual(cliente["nome"], NOME_CLIENTE)
        self.assertEqual(cliente["documento"], "DOC-FICTICIO-0001")

        propriedade = voos.obter_propriedade(self.propriedade_id)
        self.assertEqual(propriedade["nome"], NOME_PROPRIEDADE)
        self.assertEqual(propriedade["cliente_id"], self.cliente_id)

        voo = voos.obter_voo(self.voo_id)
        self.assertEqual(voo["cliente_nome"], NOME_CLIENTE)
        self.assertEqual(voo["propriedade_nome"], NOME_PROPRIEDADE)
        self.assertEqual(voo["status"], "rascunho")

        achados = voos.listar_voos(busca=NOME_PROPRIEDADE)
        self.assertTrue(achados)
        self.assertEqual(achados[0]["id"], self.voo_id)

    def test_03_salvar_midia_com_hash(self):
        conteudo = b"conteudo-ficticio-de-foto-do-voo-onda-1" * 4
        esperado = hashlib.sha256(conteudo).hexdigest()
        resultado = voos.salvar_arquivo_midia(
            self.voo_id, "Foto Aérea (1).JPG", conteudo,
            mime="image/jpeg", ator="teste_voos")
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["hash_sha256"], esperado)
        self.assertEqual(resultado["tamanho_bytes"], len(conteudo))
        self.assertIsNotNone(resultado["captura_id"])
        self.assertTrue(re.fullmatch(r"[a-z0-9._-]+",
                                     resultado["nome_seguro"]))
        self.assertTrue(os.path.isfile(resultado["caminho"]))

        midias = voos.listar_midias_do_voo(self.voo_id)
        self.assertEqual(len(midias), 1)
        self.assertEqual(midias[0]["hash_sha256"], esperado)
        self.assertEqual(midias[0]["tamanho_bytes"], len(conteudo))

    def test_04_criar_laudo_base_e_listar(self):
        laudo_id = voos.criar_laudo_base(self.voo_id, ator="teste_voos")
        self.assertIsNotNone(laudo_id)

        laudos = voos.listar_laudos(voo_id=self.voo_id)
        self.assertEqual(len(laudos), 1)
        laudo = laudos[0]
        self.assertEqual(laudo["id"], laudo_id)
        self.assertEqual(laudo["status"], "base")
        self.assertIn(NOME_CLIENTE, laudo["resumo"])
        self.assertIn(NOME_PROPRIEDADE, laudo["resumo"])
        self.assertIn("fotos: 1", laudo["resumo"])

        todos = voos.listar_laudos()
        self.assertTrue(any(item["id"] == laudo_id for item in todos))

        voo = voos.obter_voo(self.voo_id)
        self.assertEqual(voo["status"], "laudo_gerado")


if __name__ == "__main__":
    unittest.main(verbosity=2)
