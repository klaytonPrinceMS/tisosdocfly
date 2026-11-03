# -*- coding: utf-8 -*-
"""Prova o tipo de conta e o vínculo com cliente no cadastro de usuários.

O que este teste garante:

- a migração idempotente cria `user_tipo` e `cliente_id` em `tb_usuarios`;
- o seed `master`/`qacomum`/`qamaster` continua nascendo como `interno`;
- criar conta `cliente` grava o `cliente_id`, força perfil global `comum`
  e NÃO concede acesso ao módulo administrativo `usuarios`;
- `obter_usuario` e `listar_usuarios` devolvem os dois campos ao final da
  tupla, sem deslocar os índices históricos;
- rodar `init_db` duas vezes não altera o schema nem os dados.

Não passa pela UI e usa banco isolado por `TISOSDOCFLY_DIR_BANCO`.
"""
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, RAIZ)
os.environ.setdefault("TISOSDOCFLY_DIR_BANCO", "/tmp/opencode/bd_users")
os.environ.setdefault("TISOSDOCFLY_QA_SEM_TROCA", "1")

from mod_tisosdocfly.bd_criador import inicializar_bancos
from mod_gest_cad_usuario import bd_manipulador as gest

LOGIN_CLIENTE = "teste_tisosdocfly_cliente"
LOGIN_INTERNO = "teste_tisosdocfly_interno"
SENHA = "SenhaTeste123"


def _colunas_usuarios():
    """Colunas de `tb_usuarios` (funciona em SQLite e no proxy PostgreSQL)."""
    conn = gest.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(tb_usuarios)")
        return tuple(r[1] for r in (cur.fetchall() or ()))
    finally:
        conn.close()


class TestUsuarioCliente(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inicializar_bancos()
        gest.init_db()

    def setUp(self):
        gest.excluir_usuario_definitivo("master", LOGIN_CLIENTE)
        gest.excluir_usuario_definitivo("master", LOGIN_INTERNO)
        # Perfil administrativo de propósito: o backend deve rebaixar para
        # `comum` porque o tipo é `cliente`.
        ok, msg = gest.criar_usuario(
            "master", LOGIN_CLIENTE, SENHA,
            perfil="administrador_geral",
            nome_completo="Cliente Fictício de Teste",
            exigir_telefone=False,
            tipo_conta="cliente", cliente_id=77)
        self.assertTrue(ok, msg)

    def tearDown(self):
        gest.excluir_usuario_definitivo("master", LOGIN_CLIENTE)
        gest.excluir_usuario_definitivo("master", LOGIN_INTERNO)

    def test_01_migracao_cria_colunas(self):
        colunas = _colunas_usuarios()
        self.assertIn("user_tipo", colunas)
        self.assertIn("cliente_id", colunas)

    def test_02_seed_continua_interno(self):
        for login in ("master", "qacomum", "qamaster"):
            linha = gest.obter_usuario(login)
            self.assertIsNotNone(linha, f"seed ausente: {login}")
            self.assertEqual(linha[10], "interno", login)

    def test_03_cliente_nao_recebe_perfil_nem_acesso_admin(self):
        linha = gest.obter_usuario(LOGIN_CLIENTE)
        self.assertIsNotNone(linha)
        self.assertEqual(linha[10], "cliente")
        self.assertEqual(linha[11], 77)
        self.assertEqual(linha[5], "comum")
        chaves = [a[0] for a in gest.listar_acessos(LOGIN_CLIENTE)]
        self.assertNotIn("usuarios", chaves)
        self.assertEqual(chaves, [])

    def test_04_obter_e_listar_devolvem_campos(self):
        linha = gest.obter_usuario(LOGIN_CLIENTE)
        self.assertEqual(len(linha), 12)
        self.assertEqual(linha[10], "cliente")
        self.assertEqual(linha[11], 77)

        achado = next((r for r in gest.listar_usuarios()
                       if r[1] == LOGIN_CLIENTE), None)
        self.assertIsNotNone(achado)
        self.assertEqual(len(achado), 13)
        self.assertEqual(achado[11], "cliente")
        self.assertEqual(achado[12], 77)

    def test_05_interno_e_o_padrao(self):
        ok, msg = gest.criar_usuario(
            "master", LOGIN_INTERNO, SENHA, perfil="comum",
            nome_completo="Interno Fictício de Teste",
            exigir_telefone=False)
        self.assertTrue(ok, msg)
        linha = gest.obter_usuario(LOGIN_INTERNO)
        self.assertEqual(linha[10], "interno")
        self.assertIsNone(linha[11])

    def test_06_init_db_e_idempotente(self):
        colunas_antes = _colunas_usuarios()
        cliente_antes = gest.obter_usuario(LOGIN_CLIENTE)
        total_antes = len(gest.listar_usuarios())

        gest.init_db()

        self.assertEqual(_colunas_usuarios(), colunas_antes)
        self.assertEqual(len(gest.listar_usuarios()), total_antes)
        self.assertEqual(gest.obter_usuario(LOGIN_CLIENTE), cliente_antes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
