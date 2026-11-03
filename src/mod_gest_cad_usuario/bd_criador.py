"""Legacy database creator — mod_gest_cad_usuario (kept only for compatibility).

Criador de BD LEGADO do módulo de Gestão de Usuários, mantido apenas por
compatibilidade histórica. O criador VIGENTE do esquema é `init_db()` em
`mod_gest_cad_usuario/db_manipulador.py` (banco próprio
`db_mod_gest_cad_usuario.db`, com migrações e seeds). Este arquivo conecta no
banco CENTRAL e cria um esquema divergente (inclui `tb_modulo_perfil`, que
não existe no esquema real) — não usar como fonte de verdade.

BLOQUEADO (29/09/2026). Este arquivo era o SEGUNDO caminho que criava a conta
`master` com senha de fábrica: um `INSERT` próprio, sem a marca que impede a
ressurreição. Hoje `mod_tisosdocfly.bd_criador.inicializar_bancos` só chama
`mod_gest_cad_usuario.bd_manipulador.init_db()`, então este código não roda no
boot — mas ficar ali era um segundo gatilho de porta aberta para a mesma falha
de segurança, e o AGENTS.md §2.1 já marca `bd_criador.py` como MORTO. Chamá-lo
passa a levantar, como já acontece em `mod_edit_pdf/bd_criador.py`.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import sqlite3
import os

from mod_tisosdocfly.bd_conexao import get_connection, DB_PATH
from mod_tisosdocfly.bd_manipulador import audit_log

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_PROJETO = os.path.dirname(BASE_DIR)
DB_CAD_PATH = os.path.join(DIR_PROJETO, "db_mod_gest_cad_usuario.db")


def _log():
    """Logger do módulo (loguru) — arquivo dedicado logs/gest_cad_usuario_<data>.log."""
    from mod_tisosdocfly import observabilidade
    return observabilidade.get_logger("gest_cad_usuario")


def init_db():
    """BLOQUEADO — levanta sempre (29/09/2026).

    EN: Raises unconditionally. The legacy creator is dead (AGENTS.md §2.1) and
        was a second path that re-inserted the `master` factory account without
        the marker that prevents its resurrection.
    PT-BR: Levanta sempre. O criador legado está morto e era um segundo caminho
        que reinseria a conta de fábrica `master` sem a marca que impede a
        ressurreição. O caminho vigente é `bd_manipulador.init_db()`.
    """
    raise RuntimeError(
        "mod_gest_cad_usuario.bd_criador.init_db() isolado/morto — "
        "usar mod_gest_cad_usuario.bd_manipulador.init_db()")


def _init_db_legado_morto():
    """Creates the LEGACY divergent schema in the CENTRAL database (do not use).

    Cria `tb_usuarios` e `tb_modulo_perfil` no banco central, semeia o
    usuário `master`/`master` e permissões padrão — comportamento legado.
    O esquema real (com `tb_acesso_usuario`, soft delete e migrações) vive em
    `manipulador_bd.init_db()`."""
    _log().info("criador_bd: (legado) inicializando esquema de gest_cad_usuario")
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tb_usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_nome TEXT NOT NULL UNIQUE,
            user_senha TEXT NOT NULL,
            user_email TEXT,
            user_fone TEXT,
            user_perfil TEXT NOT NULL DEFAULT 'comum',
            user_ativo INTEGER NOT NULL DEFAULT 1,
            data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
            modulo_acesso TEXT DEFAULT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tb_modulo_perfil (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo_nome TEXT NOT NULL,
            perfil_nome TEXT NOT NULL,
            permissao_escrita INTEGER NOT NULL DEFAULT 0,
            UNIQUE (modulo_nome, perfil_nome)
        )
    """)

    # Inserir usuário master se não existir
    cur.execute("SELECT COUNT(*) FROM tb_usuarios WHERE user_nome='master'")
    if cur.fetchone()[0] == 0:
        from mod_tisosdocfly.autenticacao import gerar_hash_senha
        hash_s = gerar_hash_senha("master")
        cur.execute(
            "INSERT INTO tb_usuarios (user_nome, user_senha, user_perfil, user_ativo) VALUES (?, ?, ?, ?)",
            ("master", hash_s, "administrador_geral", True),
        )

    # Permissões padrões
    cur.execute("INSERT OR IGNORE INTO tb_modulo_perfil (modulo_nome, perfil_nome, permissao_escrita) VALUES (?, ?, 1)",
                ("tisosdocfly", "administrador_geral"))
    cur.execute("INSERT OR IGNORE INTO tb_modulo_perfil (modulo_nome, perfil_nome, permissao_escrita) VALUES (?, ?, 1)",
                ("tisosdocfly", "administrador_modulo"))

    conn.commit()
    conn.close()