"""Base CRUD class and audit wrapper for module SQLite databases.

Classe base de acesso a dados dos módulos: conexão SQLite padronizada
(WAL + `synchronous`, `foreign_keys` opcional), execução com fechamento
garantido (try/finally), commit/rollback, atalhos de leitura/escrita
(`listar`, `obter`, `criar`, `atualizar`, `excluir`, `executar_muitas`,
`criar_tabela`) e transação multi-instrução (`transacao`). Também expõe o
wrapper de auditoria `audit_reg`. Elimina o boilerplate
`conn = _conn(); try: ... finally: conn.close()` replicado nos
`bd_manipulador.py` dos módulos. Camada baixa: sem imports circulares —
`audit_log` é importado lazily dentro de `audit_reg`.

Classe base de CRUD para o banco exclusivo de cada módulo
(db_mod_<modulo>.db). Uso típico::

    crud = CrudBase(DB_BLOG_PATH, "blog", foreign_keys=True)
    linhas = crud.listar("SELECT * FROM tb_postagens WHERE ativo=1")
    with crud.transacao() as cur:
        cur.execute("INSERT ...")
        cur.execute("UPDATE ...")
    audit_reg(ator, "blog", "criar", "postagem", titulo)
"""
import sys
import os
from contextlib import contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import sqlite3


def _log():
    """Returns the loguru logger bound to the core module ("tisosdocfly").

    Logger loguru vinculado ao módulo núcleo (`tisosdocfly`), no padrão
    `observabilidade._FMT`. Usado nos blocos `except` deste arquivo para
    registrar falhas de acesso a dados sem derrubar a aplicação.
    """
    from mod_tisosdocfly import observabilidade
    return observabilidade.get_logger("tisosdocfly")


def audit_reg(ator, modulo, acao, alvo="", detalhe="", hash_arquivo=None):
    """Registers one action in the central audit trail (fail-soft).

    Wrapper fino de `mod_tisosdocfly.manipulador_bd.audit_log` com assinatura
    curta (`ator`, `modulo`, `acao`, `alvo`, `detalhe`, `hash_arquivo`):
    `detalhe` vazio usa `alvo` como descrição. Falha de auditoria registra
    exception no loguru e NÃO interrompe a operação de negócio (fail-soft)
    — a trilha de rastreabilidade não deve derrubar a gravação do módulo.
    """
    try:
        from mod_tisosdocfly.bd_manipulador import audit_log
        audit_log(ator, modulo, acao, detalhe or alvo, hash_arquivo)
    except Exception as e:
        _log().exception(f"audit_reg: falha ao auditar "
                         f"({modulo}/{acao}/{alvo}): {e}")


class CrudBase:
    """Base class for CRUD operations over a module's own SQLite database.

    Encapsula a conexão (WAL + `synchronous=NORMAL`, `foreign_keys=ON`
    opcional — módulos com FK CASCADE devem instanciar com
    `foreign_keys=True`), o fechamento garantido (try/finally) e o
    commit/rollback. Os atalhos `listar`/`obter`/`criar`/`atualizar`/
    `excluir`/`executar_muitas`/`criar_tabela` cobrem os padrões repetidos
    nos `bd_manipulador.py`; sequências atômicas multi-instrução usam
    `transacao()`. Exceções são registradas no loguru e PROPAGAM — a
    camada de negócio decide o fail-soft (padrão atual dos módulos).
    """

    def __init__(self, db_path, modulo="sistema", *, foreign_keys=False,
                 synchronous="NORMAL"):
        self.db_path = db_path
        self.modulo = modulo
        self.foreign_keys = foreign_keys
        self.synchronous = synchronous

    def _log(self):
        """Returns the loguru logger bound to this CRUD's module.

        Logger loguru vinculado ao módulo dono do banco (`self.modulo`),
        gerando arquivo dedicado `logs/<modulo>_<data>.log` quando
        configurado na Observabilidade.
        """
        from mod_tisosdocfly import observabilidade
        return observabilidade.get_logger(self.modulo)

    def _conectar(self):
        """Opens a connection routed by the ACTIVE backend (WAL + pragmas).

        Conexão via `banco_conexao.conexao(modulo)` quando o módulo é um
        banco conhecido — SQLite (arquivo do módulo, WAL+`synchronous=NORMAL`
        +`busy_timeout=5000`+`foreign_keys=ON`) ou PostgreSQL
        (DATABASE `db_mod_<chave>`); caso contrário cai na conexão sqlite3
        clássica (`db_path`) com os pragmas padrão. `PRAGMA` é ignorado pelo
        proxy no Postgres. Com `banco_tipo=postgres` NÃO há fallback para o
        arquivo SQLite: falha de conexão levanta exceção (fail-fast), para
        não rebaixar silenciosamente o backend ativo.
        """
        try:
            from mod_tisosdocfly import banco_conexao
            postgres = banco_conexao.sgbd_ativo() == "postgres"
            if banco_conexao.eh_chave_modulo(self.modulo):
                try:
                    conn = banco_conexao.conexao(self.modulo)
                except Exception as e:
                    if postgres:
                        try:
                            self._log().exception(
                                f"{self.modulo}: falha ao conectar no Postgres: {e}")
                        except Exception:
                            pass
                        raise RuntimeError(
                            f"falha ao conectar '{self.modulo}' no Postgres: "
                            f"{e}") from e
                    conn = None
                if conn is not None:
                    try:
                        conn.execute("PRAGMA journal_mode=WAL")
                        conn.execute("PRAGMA synchronous=NORMAL")
                        conn.execute("PRAGMA busy_timeout=5000")
                        if self.foreign_keys:
                            conn.execute("PRAGMA foreign_keys=ON")
                    except Exception as exc_pragma:
                        # No Postgres o proxy ignora PRAGMA (SELECT NULL);
                        # no SQLite falha de pragma não derruba a conexão.
                        try:
                            self._log().warning(
                                f"{self.modulo}: pragma: {exc_pragma}")
                        except Exception:
                            pass
                    return conn
                if postgres:
                    raise RuntimeError(
                        f"conexao('{self.modulo}') indisponível com "
                        f"banco_tipo=postgres — sem fallback para SQLite")
            elif postgres:
                raise RuntimeError(
                    f"módulo '{self.modulo}' desconhecido com banco_tipo=postgres "
                    f"— sem fallback para SQLite")
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL")
            if self.synchronous:
                conn.execute(f"PRAGMA synchronous={self.synchronous}")
            conn.execute("PRAGMA busy_timeout=5000")
            if self.foreign_keys:
                conn.execute("PRAGMA foreign_keys=ON")
            return conn
        except RuntimeError:
            raise
        except Exception as exc:
            try:
                self._log().exception(f"{self.modulo}: falha em _conectar: {exc}")
            except Exception:
                pass
            raise

    def _executar(self, sql, params=(), *, commit=False, fetchall=False,
                  fetchone=False):
        """Runs one statement with guaranteed connection close (try/finally).

        Executa `sql` com `params` e devolve: as linhas (`fetchall=True`),
        a primeira linha (`fetchone=True`) ou o cursor (acesso a
        `lastrowid`/`rowcount`). `commit=True` grava a transação. Em
        exceção: rollback, registro exception no loguru e repasse da
        exceção (fail-loud — a camada de negócio decide).
        """
        conn = self._conectar()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            if commit:
                conn.commit()
            if fetchone:
                return cur.fetchone()
            if fetchall:
                return cur.fetchall()
            return cur
        except Exception as e:
            conn.rollback()
            self._log().exception(f"{self.modulo}: falha em _executar: {e}")
            raise
        finally:
            conn.close()

    @contextmanager
    def transacao(self):
        """Yields a cursor within an atomic multi-statement transaction.

        Transação atômica para sequências de instruções (ex.: leitura +
        gravação + gravação em cascata): `commit` quando o bloco termina
        sem erro, `rollback` e repasse da exceção em falha (registrada no
        loguru). A conexão é sempre fechada no `finally`.
        """
        conn = self._conectar()
        try:
            yield conn.cursor()
            conn.commit()
        except Exception as e:
            conn.rollback()
            self._log().exception(f"{self.modulo}: transação abortada: {e}")
            raise
        finally:
            conn.close()

    def listar(self, sql, params=()):
        """Runs a SELECT returning all rows (list of tuples)."""
        return self._executar(sql, params, fetchall=True)

    def obter(self, sql, params=()):
        """Runs a SELECT returning the first row (or `None`)."""
        return self._executar(sql, params, fetchone=True)

    def criar(self, sql, params=()):
        """Runs an INSERT with commit, returning the new `lastrowid`."""
        return self._executar(sql, params, commit=True).lastrowid

    def atualizar(self, sql, params=()):
        """Runs an UPDATE/DELETE with commit, returning `rowcount`."""
        return self._executar(sql, params, commit=True).rowcount

    def excluir(self, sql, params=()):
        """Runs a DELETE with commit, returning removed `rowcount`."""
        return self.atualizar(sql, params)

    def executar_muitas(self, sql, seq_params):
        """Runs `executemany` + commit for batched writes (seeds/migrations)."""
        conn = self._conectar()
        try:
            cur = conn.cursor()
            cur.executemany(sql, seq_params)
            conn.commit()
            return cur.rowcount
        except Exception as e:
            conn.rollback()
            self._log().exception(f"{self.modulo}: falha em executar_muitas: {e}")
            raise
        finally:
            conn.close()

    def criar_tabela(self, ddl):
        """Runs idempotent DDL (`CREATE TABLE IF NOT EXISTS ...`) with commit."""
        return self._executar(ddl, commit=True)
