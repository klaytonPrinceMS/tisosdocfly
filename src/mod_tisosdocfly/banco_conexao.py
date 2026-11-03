"""Database backend selection: SQLite (default) or PostgreSQL (optional).

Camada de seleção de SGBD pensada para o usuário final: servidores simples
seguem com SQLite (padrão, zero dependências extras — os módulos já operam
via `CrudBase`/sqlite3); demandas maiores ativam PostgreSQL em container
(`docker/postgres/docker-compose.yml`). Configuração em `tb_config` central
(ajustável pelo admin, vale para engines criadas depois — sem restart para
trocar de URL):

- `banco_tipo`: `'sqlite'` (padrão) ou `'postgres'`
- `postgres_url`: DSN SQLAlchemy (default `postgresql+psycopg2://
  tisosdocfly:tisosdocfly@localhost:5432/tisosdocfly`)

`obter_engine()` cria a engine SQLAlchemy sob demanda (singleton por DSN,
import lazy — sem `sqlalchemy`/driver instalado o sistema segue de pé em
SQLite com exception registrada no loguru, fail-soft). O DSN nunca é
logado com credenciais (`_dsn_publico` mascara usuário/senha). No Postgres
a estrutura espelha o SQLite: **um DATABASE por módulo** (`db_mod_<chave>`,
criado por `garantir_bancos_postgres`) e o schema real vem do DDL próprio
dos `init_db` de cada módulo — a migração de dados SQLite→PostgreSQL é fase
futura documentada.
"""
import sys
import os
import re
import threading
from datetime import datetime, date
from functools import lru_cache, cache

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _log():
    """Returns the loguru logger bound to the core module ("tisosdocfly").

    Logger loguru vinculado ao módulo núcleo (`tisosdocfly`), no padrão
    `observabilidade._FMT`. Usado para registrar a criação/falha da engine
    sem expor credenciais e sem derrubar a aplicação (fail-soft).
    """
    from mod_tisosdocfly import observabilidade
    return observabilidade.get_logger("tisosdocfly")


def _dsn_publico(url):
    """Masks credentials in the DSN before logging (never log secrets).

    Remove usuário/senha do DSN para uso seguro em logs: mantém o esquema
    e o host (`postgresql+psycopg2://***@localhost:5432/tisosdocfly`); DSN
    sem credenciais volta intacto; qualquer falha devolve `'<dsn>'`.
    """
    try:
        esquema, _, resto = url.partition("://")
        if "@" in resto:
            host = resto.rpartition("@")[2]
            return f"{esquema}://***@{host}"
        return url
    except Exception:
        return "<dsn>"


def _banco_central_sem_schema():
    """True quando o SQLite central ainda não tem tabela nenhuma (instalação nova).

    Usado só para classificar o erro de boot: no primeiro boot o
    `sqlite3.connect()` em `_ler_config_sqlite` CRIA o arquivo vazio antes de
    consultar `tb_config`, e o `init_db` só semeia o schema em seguida. Nesse
    intervalo o `SELECT` falha com `no such table`. True aqui = banco
    zerado de verdade; False = banco já semeado, onde a falha é anômala e
    precisa de atenção. Qualquer erro ao inspecionar devolve False (não
    mascaramos falha real como se fosse primeiro boot).
    """
    try:
        from mod_tisosdocfly.repositorio import DB_PATH
        if not os.path.exists(DB_PATH):
            return True
        import sqlite3
        conn = sqlite3.connect(DB_PATH, timeout=2.0)
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            return total == 0
        finally:
            conn.close()
    except Exception:
        return False


@lru_cache(maxsize=32)
def _ler_config_sqlite(chave, default=""):
    """Reads a selector config key straight from the central SQLite file.

    Lê `banco_tipo`/`postgres_url` DIRETO do `db_mod_tisosdocfly.db` (sqlite),
    sem passar pelo `Repositorio`/engine — evita a recursão
    `sgbd_ativo → get_config → engine → sgbd_ativo`. Essas chaves são o
    "seletor de backend" e vivem no arquivo SQLite central (autoritativo
    no boot). Conexão direta sqlite3 (não via `conexao()` para não
    recursar) com pragmas WAL+`synchronous=NORMAL`+`busy_timeout=5000`.
    Fail-soft: devolve `default` em qualquer falha.
    """
    try:
        from mod_tisosdocfly.repositorio import DB_PATH
        import sqlite3
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            row = conn.execute(
                "SELECT valor FROM tb_config WHERE chave=?", (chave,)).fetchone()
            return (row[0] if row else default) or default
        finally:
            conn.close()
    except Exception as exc:
        # O log NUNCA é suprimido (AGENTS.md 3.2): a causa fica registrada
        # mesmo quando o erro é o esperado do primeiro boot. O que muda é
        # apenas a impressão no terminal, para quem está olhando o boot
        # entender que ali não há defeito — é a primeira execução sem banco.
        try:
            _log().exception(f"_ler_config_sqlite('{chave}'): {exc}")
        except Exception:
            pass
        try:
            if _banco_central_sem_schema():
                try:
                    _log().info(f"[banco] Primeira execução: '{chave}' ainda não existe em "
                                f"tb_config porque o banco central ainda não foi criado. "
                                f"Erro esperado no primeiro boot — o schema é semeado em "
                                f"seguida. Causa registrada no log.")
                except Exception:
                    pass
                print(f"[banco] Primeira execução: '{chave}' ainda não existe em "
                      f"tb_config porque o banco central ainda não foi criado. "
                      f"Erro esperado no primeiro boot — o schema é semeado em "
                      f"seguida. Causa registrada no log.", flush=True)
        except Exception:
            pass
        return default


def _gravar_config_sqlite(chave, valor):
    """Upserts a selector config key directly in the central SQLite file.

    Escrita direta sqlite3 (não via `conexao()` para não recursar o
    seletor de backend), com pragmas WAL+`synchronous=NORMAL`+
    `busy_timeout=5000`. Idempotente via `ON CONFLICT DO UPDATE`.
    """
    try:
        from mod_tisosdocfly.repositorio import DB_PATH
        import sqlite3
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(
                "INSERT INTO tb_config (chave, valor) VALUES (?, ?) "
                "ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor",
                (chave, str(valor)))
            conn.commit()
        finally:
            conn.close()
        try:
            _ler_config_sqlite.cache_clear()
        except Exception:
            pass
        try:
            _sgbd_ativo_cached.cache_clear()
        except Exception:
            pass
        try:
            postgres_url.cache_clear()
        except Exception:
            pass
        return True
    except Exception as e:
        try:
            _log().exception(f"_gravar_config_sqlite('{chave}'): {e}")
        except Exception:
            pass
        return False


def definir_banco_tipo(valor):
    """Sets `banco_tipo` ('sqlite'|'postgres') in the central SQLite file.

    Grava o seletor de backend no arquivo SQLite central (persistente e
    lido no boot). Aplica após reiniciar o servidor."""
    tipo = (valor or "sqlite").strip().lower()
    return _gravar_config_sqlite("banco_tipo",
                                 tipo if tipo in ("sqlite", "postgres") else "sqlite")


def definir_postgres_url(url):
    """Sets `postgres_url` (DSN) in the central SQLite file."""
    return _gravar_config_sqlite("postgres_url", (url or "").strip())


def config_backend() -> dict:
    """Returns the backend selector as a dict (`banco_tipo`, `postgres_url`).

    Usado pela aba de administração (/configuracoes) para exibir e editar o
    seletor de banco (lido do arquivo SQLite central — autoritativo no boot)."""
    return {
        "banco_tipo": sgbd_ativo(),
        "postgres_url": _ler_config_sqlite(
            "postgres_url",
            "postgresql+psycopg2://tisosdocfly:tisosdocfly@localhost:5432/tisosdocfly"),
    }


def salvar_backend(banco_tipo, postgres_url) -> bool:
    """Persists the backend selector (`banco_tipo`, `postgres_url`).

    Grava no arquivo SQLite central. Aplica ao REINICIAR o servidor
    (as conexões ativas seguem no backend anterior)."""
    ok1 = definir_banco_tipo(banco_tipo)
    ok2 = definir_postgres_url(postgres_url)
    return ok1 and ok2


@lru_cache(maxsize=1)
def _sgbd_ativo_cached():
    """Cached internal helper for sgbd_ativo (without env-var check)."""
    tipo = _ler_config_sqlite("banco_tipo", "sqlite").strip().lower()
    return tipo if tipo in ("sqlite", "postgres") else "sqlite"


def sgbd_ativo():
    """Returns the active SGBD ('sqlite' or 'postgres') from the central file.

    Lê `banco_tipo` direto do arquivo SQLite central (seletor de backend,
    autoritativo no boot). Valores distintos de 'sqlite'/'postgres' caem
    em 'sqlite'. A variável de ambiente `TISOSDOCFLY_FORCE_SQLITE=1` força
    'sqlite' (usada pela suíte de testes standalone para não depender de um
    PostgreSQL ativo).
    """
    if os.environ.get("TISOSDOCFLY_FORCE_SQLITE") == "1":
        return "sqlite"
    return _sgbd_ativo_cached()


@lru_cache(maxsize=2)
def postgres_url(como_admin=False):
    """Returns the configured PostgreSQL DSN (SQLAlchemy format).

    Lê `postgres_url` da `tb_config` central; sem chave/valor devolve o
    DSN default do container (`docker/postgres/docker-compose.yml`).
    Se `como_admin=True`, usa `banco_admin_usuario`/`banco_admin_senha`
    (padrão master/master) para operações administrativas (criação de banco,
    migrations). Caso contrário usa `banco_usuario`/`banco_senha`
    (padrão tisosdocfly/tisosdocfly) para operações normais.
    """
    try:
        base = _ler_config_sqlite(
            "postgres_url",
            "postgresql+psycopg2://tisosdocfly:tisosdocfly@localhost:5432/tisosdocfly")
        esquema, _, resto = base.partition("://")
        # Se a URL já traz credenciais e não é operação admin, usa-as como está
        # (ex.: container com tisosdocfly:tisosdocfly) — não sobrescreve com seeds
        # antigos de banco_usuario/banco_senha.
        if not como_admin and "@" in resto:
            return base
        if como_admin:
            user = _ler_config_sqlite("banco_admin_usuario", "master")
            senha = _ler_config_sqlite("banco_admin_senha", "master")
        else:
            user = _ler_config_sqlite("banco_usuario", "tisosdocfly")
            senha = _ler_config_sqlite("banco_senha", "tisosdocfly")
        if "@" in resto:
            host = resto.rpartition("@")[2]
            return f"{esquema}://{user}:{senha}@{host}"
        return base
    except Exception as e:
        _log().warning(f"banco_conexao: falha ao ler postgres_url, usando default: {e}")
        if como_admin:
            return "postgresql+psycopg2://master:master@localhost:5432/tisosdocfly"
        return "postgresql+psycopg2://tisosdocfly:tisosdocfly@localhost:5432/tisosdocfly"


_engine = None
_engine_url = ""
_engine_lock = threading.Lock()


def obter_engine():
    """Returns the SQLAlchemy engine (lazy singleton) or `None` (fail-soft).

    Com `banco_tipo='sqlite'` devolve `None` (o CrudBase/sqlite3 já cobre
    — nada a fazer). Com `'postgres'`, cria `create_engine(url,
    pool_pre_ping=True)` na primeira chamada e reusa nas seguintes;
    DSN alterado na configuração descarta a engine antiga (`dispose`) e
    cria outra — troca vale sem restart. Sem `sqlalchemy`/driver
    instalado, registra exception no loguru e devolve `None` (a
    aplicação segue operando em SQLite).
    """
    global _engine, _engine_url
    if sgbd_ativo() != "postgres":
        return None
    url = postgres_url()
    with _engine_lock:
        if _engine is not None and _engine_url == url:
            return _engine
        try:
            from sqlalchemy import create_engine
            nova = create_engine(url, pool_pre_ping=True, future=True)
            antiga, _engine, _engine_url = _engine, nova, url
            if antiga is not None:
                try:
                    antiga.dispose()
                except Exception:
                    pass
            _log().info(f"banco_conexao: engine PostgreSQL criada "
                        f"({_dsn_publico(url)})")
            return _engine
        except Exception as e:
            _log().exception(f"banco_conexao: falha ao criar engine "
                             f"PostgreSQL ({e}); seguindo em SQLite")
            return None


def engine_disponivel():
    """Returns `True` when the active SGBD has a working engine.

    Verificação rápida para bootstrap/telas de administração: 'sqlite'
    sempre disponível; 'postgres' exige `obter_engine()` sem falha (ou
    engine já criada e válida).
    """
    if sgbd_ativo() == "sqlite":
        return True
    return obter_engine() is not None


# =============================================================================
# PostgreSQL: engine POR MÓDULO (banco próprio) + conexão compatível
# =============================================================================
# Cada módulo usa o SEU PRÓPRIO BANCO no Postgres (espelha o modelo "um SQLite
# por módulo"): assim como no SQLite há um `db_mod_<chave>.db` por módulo, no
# Postgres há um DATABASE `db_mod_<chave>` por módulo. A estrutura é idêntica
# nos dois backends e as MESMAS funções de acesso (`conexao`, proxy psycopg2
# com tradução de DDL/datetime/GROUP_CONCAT) valem para ambos.

_engines_modulo: dict[str, object] = {}
_lock_modulo = threading.Lock()
_bancos_criados: set = set()
_lock_bancos = threading.Lock()


def eh_chave_modulo(chave: str) -> bool:
    """True if `chave` is a known module database key."""
    from mod_tisosdocfly.repositorio import MODULOS_BD
    return chave in MODULOS_BD


def banco_modulo(chave: str = "tisosdocfly") -> str:
    """PostgreSQL database name for a module key (mirrors SQLite file).

    O nome do banco espelha o arquivo SQLite (`db_mod_<chave>.db` → banco
    `db_mod_<chave>`), mantendo a estrutura idêntica entre backends."""
    from mod_tisosdocfly.repositorio import MODULOS_BD
    nome = MODULOS_BD.get(chave, MODULOS_BD["tisosdocfly"])
    return nome[:-3] if nome.endswith(".db") else nome


def _url_com_banco(url, banco):
    """Swaps the database (last path segment) in a postgresql DSN URL."""
    if not url:
        return url
    return re.sub(r"(postgresql(?:\+psycopg2)?://[^/]+/)[^/]*$",
                  rf"\g<1>{banco}", url, flags=re.I)


def _garantir_bd_postgres(banco: str) -> bool:
    """Creates the module's PostgreSQL database if it does not exist.

    Conecta no banco de manutenção `postgres` e cria `db_mod_<chave>` quando
    ausente (`CREATE DATABASE`, autocommit — não roda em transação).
    Idempotente por processo (`_bancos_criados`). Sem isso, o banco de um
    módulo nunca é materializado no Postgres — a causa do Postgres só ter o
    banco central."""
    if banco in _bancos_criados:
        return True
    with _lock_bancos:
        if banco in _bancos_criados:
            return True
        try:
            import psycopg2
            from psycopg2 import sql
            base = postgres_url()
            dsn = _url_com_banco(base, "postgres").replace(
                "postgresql+psycopg2://", "postgresql://")
            conn = psycopg2.connect(dsn)
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (banco,))
            if cur.fetchone() is None:
                cur.execute(sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(banco)))
                _log().info(f"banco_conexao: banco PostgreSQL '{banco}' criado")
            cur.close()
            conn.close()
            _bancos_criados.add(banco)
            return True
        except Exception as e:
            _log().exception(f"_garantir_bd_postgres('{banco}'): {e}")
            return False


def garantir_bancos_postgres() -> dict[str, bool]:
    """Ensures EVERY module PostgreSQL database exists (CREATE DATABASE).

    Percorre os bancos dos módulos e cria os que faltarem (idempotente).
    Usado no boot (`garantir_bancos`) para o Postgres materializar TODOS os
    bancos de módulo — não apenas o central."""
    from mod_tisosdocfly.repositorio import MODULOS_BD
    resultado: dict[str, bool] = {}
    for chave in MODULOS_BD:
        resultado[chave] = _garantir_bd_postgres(banco_modulo(chave))
    return resultado


def obter_engine_modulo(chave: str = "tisosdocfly"):
    """SQLAlchemy engine for a module on the ACTIVE backend.

    postgres: engine para o BANCO do módulo (`db_mod_<chave>`, criado se
    necessário) — um banco por módulo, igual ao SQLite. Reutilizado (cache
    por chave). sqlite: devolve `None` — o `repositorio.engine(chave)` cuida
    dos engines SQLite por arquivo."""
    if sgbd_ativo() != "postgres":
        return None
    banco = banco_modulo(chave)
    if not _garantir_bd_postgres(banco):
        return None
    with _lock_modulo:
        if chave in _engines_modulo:
            return _engines_modulo[chave]
        try:
            from sqlalchemy import create_engine
            url = _url_com_banco(postgres_url(), banco)
            eng = create_engine(url, pool_pre_ping=True, future=True)
            _engines_modulo[chave] = eng
            _log().info(f"banco_conexao: engine Postgres para o módulo "
                        f"'{chave}' (banco '{banco}')")
            return eng
        except Exception as e:
            _log().exception(f"obter_engine_modulo('{chave}'): {e}")
            return None


# Controle de transação do CHAMADOR (ver `_CursorPostgres.execute`). No
# PostgreSQL `RELEASE x` libera x E os savepoints posteriores a x, então
# embrulhar um `RELEASE` do chamador em `ng_stmt` faria o proxy estourar ao
# tentar liberar o próprio embrulho, já destruído em cascata.
_TXN_RE = re.compile(
    r"(?is)^\s*(SAVEPOINT|RELEASE(?:\s+SAVEPOINT)?|ROLLBACK(?:\s+TO(?:\s+SAVEPOINT)?)?"
    r"|BEGIN|COMMIT|END)\b"
)


@lru_cache(maxsize=64)
def _ddl_postgres(ddl: str) -> str:
    """Translates SQLite CREATE TABLE DDL into PostgreSQL-compatible DDL.

    Lida com os padrões usados pelos `init_db` dos módulos: `AUTOINCREMENT`,
    `INTEGER PRIMARY KEY` → `SERIAL PRIMARY KEY`, `BLOB` → `BYTEA`,
    `DATETIME` → `TIMESTAMP` e remove `FOREIGN KEY ... REFERENCES ...`
    (o Postgres exige a tabela referenciada pré-existente; os módulos criam
    na ordem do SQLite — a integridade é gerida no aplicativo). `IF NOT
    EXISTS` é válido em ambos para `CREATE TABLE`.

    Paridade `ALTER TABLE ADD COLUMN`: padrão portável é check-then-add
    idempotente (`PRAGMA table_info(t)` → traduzido para
    `information_schema.columns` no proxy — ver `_CursorPostgres.execute`;
    exemplo em `bd_manipulador.garantir_rastreabilidade`). `ADD COLUMN IF
    NOT EXISTS` é nativo no Postgres mas NÃO existe no SQLite — não usar
    em código portável (quebraria o SQLite, que não passa pelo proxy).

    `CREATE OR REPLACE` NÃO implementado: não traduzido pelo proxy —
    usar sempre `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT
    EXISTS` (portável nos dois backends).
    """
    try:
        d = (ddl or "").strip()
        if not (d.upper().startswith("CREATE TABLE")
                or d.upper().startswith("ALTER TABLE")):
            return d
        d = re.sub(r"\bAUTOINCREMENT\b", "", d, flags=re.I)
        d = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\b", "SERIAL PRIMARY KEY", d, flags=re.I)
        d = re.sub(r"\bBLOB\b", "BYTEA", d, flags=re.I)
        d = re.sub(r"\bDATETIME\b", "TIMESTAMP", d, flags=re.I)
        if d.upper().startswith("ALTER TABLE"):
            return d
        # Colunas TEXT com DEFAULT de timestamp recebem cast ::text (Postgres não
        # converte implicitamente no DEFAULT).
        d = re.sub(r"(\bTEXT\b[^,()]*?DEFAULT\s*\((LOCALTIMESTAMP|CURRENT_TIMESTAMP)\))",
                   r"\1::text", d, flags=re.I)
        # Remove REFERENCES (inline e de tabela) + cláusulas ON DELETE/UPDATE.
        #
        # A ação de cada cláusula é uma palavra que NÃO pode ser a keyword
        # `ON`: com `\w+(?:\s+\w+)?`, o grupo depois de `DELETE CASCADE`
        # casava o " ON" seguinte — `\w` também casa "ON" — e com as duas
        # cláusulas na mesma linha sobrava `UPDATE CASCADE` pendurado na
        # coluna, que o PostgreSQL rejeita com
        # `relation "tb_contratos" does not exist` no `CREATE TABLE`
        # seguinte. Duas referências com `ON DELETE CASCADE ON UPDATE
        # CASCADE` — como `tb_contratos`, `tb_historico_movimentos` e
        # `tb_historico_salarial` (03/10/2026) — são exatamente o caso
        # que dispara, e nenhuma referência anterior do projeto tinha as
        # DUAS cláusulas: por isso a tabela antiga passou e as três novas
        # não.
        ref = (r"\s+REFERENCES\s+[`\"]?[\w.]+[`\"]?\s*\([^)]*\)"
               r"(?:\s+ON\s+(?:DELETE|UPDATE)\s+(?:CASCADE|RESTRICT|SET\s+"
               r"(?:NULL|DEFAULT)|NO\s+ACTION))*")
        d = re.sub(ref, "", d, flags=re.I)
        d = re.sub(r",\s*FOREIGN\s+KEY\s*\([^)]*\)", "", d, flags=re.I)
        return d
    except Exception as exc:
        try:
            _log().exception(f"_ddl_postgres: {exc}")
        except Exception:
            pass
        return ddl or ""


class _CursorPostgres:
    """psycopg2 cursor proxy: translates `?`→`%s`, SQLite DDL/PRAGMA and
    captures `lastrowid` for plain INSERTs (RETURNING id). Datetime values
    from Postgres are normalized to strings so the app treats dates the same
    way it does in SQLite (backend-agnostic)."""

    def __init__(self, cur):
        self._cur = cur
        self._lastrowid = None

    @staticmethod
    def _preparar(sql, params):
        import re
        s = sql or ""
        # Funções/DDL específicos do SQLite → portáveis para o Postgres.
        s = s.replace("datetime('now','localtime', ?)",
                      "(LOCALTIMESTAMP + cast(? as interval))")
        s = s.replace("datetime('now','localtime')", "LOCALTIMESTAMP")
        s = s.replace("datetime('now')", "CURRENT_TIMESTAMP")
        # GROUP_CONCAT é SQLite-only; no Postgres o equivalente é STRING_AGG
        # (mesma sintaxe/semântica para os usos `GROUP_CONCAT(x, ', ')`).
        s = s.replace("GROUP_CONCAT(", "STRING_AGG(")
        # INSERT OR IGNORE → ON CONFLICT DO NOTHING (válido em SQLite e Postgres).
        if re.match(r"(?is)^\s*INSERT\s+OR\s+IGNORE\s+INTO", s):
            s = re.sub(r"(?is)^\s*INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", s, count=1)
            s = s.rstrip(";") + " ON CONFLICT DO NOTHING"
        if params is None:
            return s, None
        if isinstance(params, (list, tuple)):
            return s.replace("?", "%s"), params
        return s, params

    def execute(self, sql, params=None):
        s = (sql or "").strip()
        if not s:
            return self._cur.execute(s)
        # Savepoint do CHAMADOR passa direto, sem o embrulho `ng_stmt` deste
        # proxy (03/10/2026 — medido rodando o boot com Postgres de verdade).
        #
        # No PostgreSQL, `RELEASE x` libera x E todos os savepoints criados
        # DEPOIS de x. Como o proxy criava `ng_stmt` a cada execute, e ele é
        # sempre posterior ao savepoint do chamador, o `RELEASE sonda_imagem`
        # do `mod_filas` (bd_manipulador.py:132) cascateava e destruía o
        # `ng_stmt` do proxy — que então estourava
        # `InvalidSavepointSpecification: savepoint "ng_stmt" does not exist`
        # ao tentar liberá-lo, derrubando a migração de `tb_midia` no meio.
        #
        # Savepoint é controle de transação do CHAMADOR: embrulhar é que é o
        # bug. O proxy só precisa do embrulho nos comandos que ELE executa.
        if _TXN_RE.match(s):
            self._lastrowid = None
            return self._cur.execute(s)
        if s.upper().startswith("PRAGMA"):
            m = re.match(r"(?is)^\s*PRAGMA\s+TABLE_INFO\(\s*['\"]?([a-zA-Z_0-9]+)['\"]?\s*\)", s)
            if m:
                s = (f"SELECT 0, column_name FROM information_schema.columns "  # nosec B608 — m.group(1) do regex [a-zA-Z_0-9]+, nunca input cru
                     f"WHERE table_schema = current_schema() "
                     f"AND table_name = '{m.group(1)}'")
            else:
                self._cur.execute("SELECT NULL WHERE 1=0")
                return self._cur  # PRAGMA (journal_mode, etc.) sem efeito/resultado
        if "CREATE VIRTUAL TABLE" in s.upper():
            return self._cur  # FTS5 é SQLite — módulo usa tabela de fallback
        if "CREATE TRIGGER" in s.upper():
            return self._cur  # trigger FTS5 (tr_fts_del_empenho) é SQLite-only
        # sqlite_master é sistema do SQLite: no Postgres devolve SEM resultados
        # (as migrações guardadas por ele são para bancos SQLite existentes).
        if "sqlite_master" in s.lower():
            self._cur.execute("SELECT NULL WHERE 1=0")
            return self._cur
        s, params = self._preparar(s, params)  # datetime(), OR IGNORE, ?→%s
        s = _ddl_postgres(s)                    # tipos SQLite → Postgres
        upper = s.upper()
        if upper.startswith("INSERT INTO") and "RETURNING" not in upper \
                and "ON CONFLICT" not in upper:
            # Captura lastrowid via RETURNING id, com SAVEPOINT para não abortar
            # a transação se a tabela não tiver coluna `id` (ex.: tb_config,
            # cuja PK é `chave`) nem em outros erros pontuais.
            tentativa = s.rstrip(";") + " RETURNING id"
            try:
                self._cur.execute("SAVEPOINT ng_sp")
                if params is None:
                    self._cur.execute(tentativa)
                else:
                    self._cur.execute(tentativa, params)
                row = self._cur.fetchone()
                self._cur.execute("RELEASE SAVEPOINT ng_sp")
                self._lastrowid = row[0] if row else None
                return self._cur
            except Exception:
                try:
                    self._cur.execute("ROLLBACK TO SAVEPOINT ng_sp")
                except Exception:
                    pass
                self._lastrowid = None
        if s.upper().startswith("SELECT"):
            if params is None:
                self._cur.execute(s)
            else:
                self._cur.execute(s, params)
            self._lastrowid = None
            return self._cur
        self._cur.execute("SAVEPOINT ng_stmt")
        try:
            if params is None:
                self._cur.execute(s)
            else:
                self._cur.execute(s, params)
            self._cur.execute("RELEASE SAVEPOINT ng_stmt")
        except Exception as exc_stmt:
            try:
                self._cur.execute("ROLLBACK TO SAVEPOINT ng_stmt")
                self._cur.execute("RELEASE SAVEPOINT ng_stmt")
            except Exception:
                pass
            # ALTER TABLE ADD COLUMN idempotente (paridade PG sem quebrar
            # SQLite): padrão portável é check-then-add via PRAGMA
            # table_info (traduzido p/ information_schema); se a guarda
            # correr em concorrência ou o chamador repetir o ADD, o PG
            # levanta duplicate column (42701/already exists) — engole e
            # segue (migração idempotente), sem derrubar o handler.
            try:
                msg = str(exc_stmt).lower()
                eh_alter_add = upper.startswith("ALTER TABLE") and "ADD COLUMN" in upper
                eh_dup = ("already exists" in msg or "duplicate column" in msg
                          or "duplicate_column" in msg or "42701" in msg)
                if eh_alter_add and eh_dup:
                    try:
                        _log().warning(f"_CursorPostgres ALTER idempotente: {exc_stmt}")
                    except Exception:
                        pass
                    self._lastrowid = None
                    return self._cur
            except Exception:
                pass
            try:
                _log().exception(f"_CursorPostgres.execute: {exc_stmt}")
            except Exception:
                pass
            raise
        self._lastrowid = None
        return self._cur

    def executemany(self, sql, seq):
        """Batched writes with `?`→`%s` translation (portable SQLite→PG).

        Corrige paridade PG: `executemany` traduz `?`→`%s` (o `_preparar`
        só traduzia no `execute` com params list/tuple — aqui `seq` é a
        lista de tuplas, então força a tradução), além de datetime()/
        `INSERT OR IGNORE`/`_ddl_postgres`. Falha registra exception e
        propaga (fail-loud — o chamador decide).
        """
        try:
            s = _ddl_postgres((sql or "").strip())
            # Força tradução ?→%s: _preparar só traduz com params list/tuple.
            s, _ = self._preparar(s, [(None,)])
            if "?" in s:
                s = s.replace("?", "%s")
            return self._cur.executemany(s, seq)
        except Exception as exc:
            try:
                _log().exception(f"_CursorPostgres.executemany: {exc}")
            except Exception:
                pass
            raise

    def executescript(self, script):
        """Splits a script on ';' and runs each statement (SQLite emulation)."""
        for stmt in (script or "").split(";"):
            if stmt.strip():
                self.execute(stmt)

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description

    def _normalizar_valor(self, v):
        """Converts Postgres datetime/date to string (SQLite-compatible)."""
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(v, date):
            return v.isoformat()
        return v

    def _normalizar_linha(self, linha):
        if linha is None:
            return None
        if isinstance(linha, dict):
            return {k: self._normalizar_valor(v) for k, v in linha.items()}
        if isinstance(linha, (list, tuple)):
            return tuple(self._normalizar_valor(v) for v in linha)
        return self._normalizar_valor(linha)

    def fetchone(self):
        return self._normalizar_linha(self._cur.fetchone())

    def fetchall(self):
        return [self._normalizar_linha(r) for r in self._cur.fetchall()]

    def fetchmany(self, size=None):
        return [self._normalizar_linha(r) for r in self._cur.fetchmany(size)]

    def __getattr__(self, item):
        return getattr(self._cur, item)


class _ConexaoPostgres:
    """psycopg2 connection proxy exposing the DBAPI used by the modules."""

    def __init__(self, raw):
        self._raw = raw

    def cursor(self):
        return _CursorPostgres(self._raw.cursor())

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        return self._raw.commit()

    def rollback(self):
        return self._raw.rollback()

    def close(self):
        return self._raw.close()


def conexao(chave: str = "tisosdocfly"):
    """DBAPI-level connection for a module on the ACTIVE backend.

    sqlite: conexão sqlite3 (WAL+`synchronous=NORMAL`+`busy_timeout=5000`+
    `foreign_keys=ON`) para o arquivo do módulo. postgres:
    conexão psycopg2 (via SQLAlchemy) para o DATABASE do módulo
    (`db_mod_<chave>`), envolvida num proxy que traduz `?`→`%s`, DDL
    SQLite e PRAGMA, e captura `lastrowid`. Devolve `None` em falha
    (fail-soft). Assinatura inalterada.
    """
    if sgbd_ativo() == "postgres":
        eng = obter_engine_modulo(chave)
        if eng is None:
            return None
        try:
            return _ConexaoPostgres(eng.raw_connection())
        except Exception as e:
            try:
                _log().exception(f"conexao('{chave}'): falha ao obter conexão "
                                 f"PostgreSQL: {e}")
            except Exception:
                pass
            return None
    # SQLite
    try:
        from mod_tisosdocfly.repositorio import caminho_db
        import sqlite3
        conn = sqlite3.connect(caminho_db(chave), timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
        except Exception as exc_pragma:
            try:
                _log().warning(f"conexao('{chave}'): pragma SQLite: {exc_pragma}")
            except Exception:
                pass
        return conn
    except Exception as e:
        try:
            _log().exception(f"conexao('{chave}'): falha ao abrir SQLite: {e}")
        except Exception:
            pass
        return None


def conexao_central():
    """Shortcut: `conexao('tisosdocfly')` for the central module."""
    return conexao("tisosdocfly")
