"""SQLAlchemy ORM session factory and repository for mod_tisosdocfly.

Provides a lazy singleton SQLAlchemy `Engine` and `Session` factory
bound to `DB_PATH` (db_mod_tisosdocfly.db). All ORM operations flow
through `Repositorio` which wraps `Session` with typed CRUD methods
that return dataclass model instances.

The module keeps full backward compatibility with the existing
`get_config`/`set_config` functions in `bd_conexao.py`: those
functions delegate to `Repositorio` internally, so callers are
unaffected.

Usage::

    from mod_tisosdocfly.repositorio import engine, sessaodb, Repositorio

    repo = Repositorio()
    cfg = repo.obter_config("titulo_sistema")
    sessoes = repo.listar_sessoes_ativas()
    modulo = repo.obter_modulo("blog")

EN: Centralised data access layer (Repository pattern) using SQLAlchemy 2.0
    ORM Session with typed model returns.
PT: Camada centralizada de acesso a dados (padrão Repository) usando
    SQLAlchemy 2.0 ORM Session com retornos tipados em modelos dataclass.

Pattern (pilot module — to propagate to all modules):
    1. models/       dataclass + Table definitions
    2. bd_conexao.py engine + session factory
    3. repositorio.py typed CRUD via Session
    4. autenticacao.py uses Repositorio for all DB ops
    5. bd_manipulador.py uses Repositorio for all DB ops
"""
from __future__ import annotations

import os
import sys
import threading
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from mod_tisosdocfly.models import Configuracao, Sessao, Modulo, metadata


# `BASE_DIR` é `src/` (a pasta que contém os `mod_*`); `DIR_PROJETO` é a raiz
# do repositório, onde os `db_mod_*.db` vivem. Desde 02/10/2026 o código mora
# em `src/` (AGENTS.md §2.2) e os bancos continuam na raiz — ver a nota em
# `mod_tisosdocfly/bd_conexao.py`.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# `DIR_PROJETO` e a RAIZ do repositorio: onde os `db_mod_*.db` moram (§2.2 do
# AGENTS.md: dado fora do codigo).
#
# 03/10/2026 - `TISOSDOCFLY_DIR_BANCO` aponta os bancos para outro lugar. A razao
# e medida: a suite criava usuarios no banco de DESENVOLVIMENTO, porque
# `get_connection()` resolve por `MODULOS_BD` + `DIR_PROJETO` e `bd.DB_PATH`
# sozinho nao isola nada. Com os scripts rodando, `tb_usuarios` foi de 1.305
# para 2.467 e `tb_acesso_usuario` para 17.484 - 1.308 usuarios de teste, cada
# um gerando 7 vinculos (9.156 linhas espurias na tela de orfaos).
#
# O override vale para o processo inteiro e para TODOS os modulos, porque
# `MODULOS_BD` e um dicionario de NOMES de arquivo: mudar o diretorio muda
# todos de uma vez. Isolar teste por teste e o que nao resolveu.
DIR_PROJETO = os.path.dirname(BASE_DIR)
_DIR_BANCO_OVERRIDE = os.environ.get("TISOSDOCFLY_DIR_BANCO", "").strip()
if _DIR_BANCO_OVERRIDE:
    os.makedirs(_DIR_BANCO_OVERRIDE, exist_ok=True)
    DIR_PROJETO = _DIR_BANCO_OVERRIDE

# Banco de CADA módulo (chave do módulo → arquivo SQLite na raiz do projeto).
# O SQLAlchemy passa a trabalhar com TODOS os bancos: `engine(chave)` devolve
# o engine do banco daquele módulo; `Repositorio(chave_db=...)` vincula a
# Session a ele. O banco central é a chave "tisosdocfly".
MODULOS_BD = {
    "tisosdocfly": "db_mod_tisosdocfly.db",
    "usuarios": "db_mod_gest_cad_usuario.db",
    "agro": "db_mod_agro.db",
    "vistoria_predial": "db_mod_vistoria_predial.db",
    "seguranca": "db_mod_seguranca.db",
    "ambiental": "db_mod_ambiental.db",
    "obras": "db_mod_obras.db",
    "mapeamento": "db_mod_mapeamento.db",
    "defesa_civil": "db_mod_defesa_civil.db",
    "inspecao_industrial": "db_mod_inspecao_industrial.db",
    "eventos": "db_mod_eventos.db",
    "perimetro": "db_mod_perimetro.db",
}

CHAVE_CENTRAL = "tisosdocfly"


DB_PATH = os.path.join(DIR_PROJETO, MODULOS_BD["tisosdocfly"])

_engines: dict[str, object] = {}
_SessionFactories: dict[str, object] = {}
_lock = threading.Lock()


def _log():
    """Loguru logger for this module (tisosdocfly)."""
    from mod_tisosdocfly import observabilidade
    return observabilidade.get_logger("tisosdocfly")


def caminho_db(chave: str = "tisosdocfly") -> str:
    """Returns the SQLite file path for a module key (fallback: central).

    Devolve o caminho do banco (`MODULOS_BD`); chave desconhecida cai no
    banco central ("tisosdocfly") — fail-soft.
    """
    return os.path.join(DIR_PROJETO,
                        MODULOS_BD.get(chave, MODULOS_BD["tisosdocfly"]))


def _uri(path: str) -> str:
    """Builds the database URI from a SQLite file path.

    Uses SQLite with WAL journaling and foreign_keys support.
    URI format for SQLAlchemy 2.0 compatibility.
    """
    return f"sqlite:///{path}?check_same_thread=false"


def _tem_schema_central(_eng) -> bool:
    """True se TODAS as tabelas centrais do metadata já existem no engine.

    Usado para o self-healing do banco central: arquivo pré-existente mas
    sem schema (ou com schema parcial — ex.: só `tb_config` criada no
    pre-boot) precisa do create_all mesmo com `novo_banco=False`. Checa o
    conjunto completo de `metadata.tables` (hoje `tb_config`, `tb_sessoes`,
    `tb_modulos`). Fail-soft: False em qualquer falha.
    """
    try:
        from sqlalchemy import inspect as _insp
        existentes = set(_insp(_eng).get_table_names() or [])
        return set(metadata.tables) <= existentes
    except Exception:
        return False


def engine(chave: str = "tisosdocfly"):
    """Lazily creates/reuses the SQLAlchemy Engine for a module database.

    Postgres (`banco_tipo='postgres'`): delega ao `banco_conexao.obter_engine_modulo`
    (DATABASE `db_mod_<chave>`, um banco por módulo). SQLite: um engine
    POR banco (`MODULOS_BD`), cacheado por chave (singleton por processo),
    com pragmas WAL/synchronous/foreign_keys via event listener. CRIAÇÃO
    DO BANCO CENTRAL: `metadata.create_all` roda quando o ARQUIVO do banco
    NÃO existe OU quando ele existe mas está sem schema (ausente ou parcial,
    ex.: arquivo vazio de um boot interrompido) — sem isso, `get_config`/
    `set_config` falhavam com "no such table: tb_config" antes do
    `init_db` central. `create_all` é idempotente (só cria o que falta).
    Para módulos (não "tisosdocfly") NÃO roda `create_all`: o schema de cada
    banco é responsabilidade do `init_db` do próprio módulo. Retorna `None`
    em falha (fail-soft).
    """
    if chave not in MODULOS_BD:
        chave = "tisosdocfly"
    from mod_tisosdocfly import banco_conexao
    if banco_conexao.sgbd_ativo() == "postgres":
        return banco_conexao.obter_engine_modulo(chave)
    if chave in _engines:
        return _engines[chave]
    with _lock:
        if chave in _engines:
            return _engines[chave]
        path = caminho_db(chave)
        novo_banco = not os.path.exists(path)
        try:
            # NullPool: cada Session/thread usa a PRÓPRIA conexão (fechada ao
            # final do `with Repositorio()`). Evita SQLITE_MISUSE ("bad
            # parameter") de uma única conexão compartilhada (StaticPool) sob
            # concorrência — ex.: monitor de empenhos lendo `get_config` em
            # background enquanto a thread principal acessa o banco. Com WAL,
            # leituras concorrentes são seguras entre conexões distintas.
            _eng = create_engine(
                _uri(path),
                connect_args={"check_same_thread": False},
                poolclass=NullPool,
                echo=False,
                future=True,
            )
            @event.listens_for(_eng, "connect")
            def _set_pragmas(dbapi_conn, connection_record):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

            if chave == "tisosdocfly" and (novo_banco or not _tem_schema_central(_eng)):
                # Banco central novo OU pré-existente sem schema (total ou
                # parcial): cria as tabelas do metadata (tb_config,
                # tb_sessoes, tb_modulos). O segundo caso é o self-healing
                # (arquivo vazio/parcial, ex.: boot interrompido).
                metadata.create_all(_eng)
                _log().info(f"repositorio: banco central criado ({path})")
            elif novo_banco:
                # Banco de módulo inexistente: o arquivo é criado na
                # primeira conexão; o schema entra via `init_db` do módulo
                # (garantir_bancos/inicializar_bancos no boot).
                try:
                    _eng.connect().close()
                except Exception:
                    pass
                _log().info(f"repositorio: banco do módulo '{chave}' "
                            f"criado ({path}; schema via init_db)")
            _engines[chave] = _eng
            return _eng
        except Exception as ex:
            _log().exception(f"repositorio: falha ao criar engine "
                             f"'{chave}': {ex}")
            return None


def sessaodb(chave: str = "tisosdocfly") -> Optional[Session]:
    """Creates a new SQLAlchemy Session bound to a module database engine.

    Uma Session POR banco (`chave`); factory cacheada por chave. Retorna
    `None` se o engine estiver indisponível (fail-soft). Caller é
    responsável por fechar (use `with`/`repo.fechar()`).
    """
    if chave not in MODULOS_BD:
        chave = "tisosdocfly"
    _eng = engine(chave)
    if _eng is None:
        return None
    with _lock:
        if chave not in _SessionFactories:
            _SessionFactories[chave] = sessionmaker(
                bind=_eng, expire_on_commit=False)
    return _SessionFactories[chave]()


def garantir_bancos() -> dict[str, bool]:
    """Ensures EVERY module database exists on the ACTIVE backend.

    postgres: cria TODOS os bancos dos módulos (`db_mod_<chave>`) via
    `banco_conexao.garantir_bancos_postgres()` e força uma conexão em cada
    engine (materializa o DATABASE recém-criado). sqlite: cria o ARQUIVO do
    banco de cada módulo quando não existe (o schema entra pelo `init_db`
    de cada módulo, chamado em `inicializar_bancos`). Retorna
    `{chave: criado_agora}` (fail-soft: falha registra exception e segue).
    """
    from mod_tisosdocfly import banco_conexao
    if banco_conexao.sgbd_ativo() == "postgres":
        resultado = banco_conexao.garantir_bancos_postgres()
        for chave in MODULOS_BD:
            eng = engine(chave)
            if eng is None:
                resultado[chave] = False
                continue
            try:
                eng.connect().close()
            except Exception as ex:
                _log().warning(f"garantir_bancos('{chave}'): {ex}")
                resultado[chave] = False
        return resultado
    resultado: dict[str, bool] = {}
    for chave in MODULOS_BD:
        path = caminho_db(chave)
        criado = not os.path.exists(path)
        eng = engine(chave)
        if eng is None:
            resultado[chave] = False
            continue
        if criado:
            try:
                eng.connect().close()
            except Exception as ex:
                _log().warning(f"garantir_bancos('{chave}'): {ex}")
        resultado[chave] = criado
    return resultado


class Repositorio:
    """Centralised data access layer for mod_tisosdocfly (and module DBs).

    Wraps a SQLAlchemy Session with typed CRUD methods that return
    dataclass model instances (Configuracao, Sessao, Modulo). A instância
    pode ser vinculada a QUALQUER banco de `MODULOS_BD` via
    `Repositorio(chave_db="blog")` — os helpers genéricos `consultar`/
    `executar`/`ultimo_id` operam no banco vinculado (default: central).

    EN: Repository for database operations using SQLAlchemy ORM.
    PT: Repositório para operações no banco usando SQLAlchemy ORM.

    Attributes:
        sessoes: Active SQLAlchemy Session (created on demand).
        closed: Whether this instance's session has been closed.
    """

    def __init__(self, sessao: Optional[Session] = None,
                 chave_db: str = "tisosdocfly"):
        if chave_db not in MODULOS_BD:
            chave_db = "tisosdocfly"
        self.chave_db = chave_db
        self._sessao = sessao
        self._encerrada = False

    @property
    def sessoes(self) -> Optional[Session]:
        """Lazily acquires a session if one was not provided at construction."""
        if self._sessao is None and not self._encerrada:
            self._sessao = sessaodb(self.chave_db)
        return self._sessao

    def fechar(self):
        """Closes the session and releases the connection."""
        if self._sessao is not None:
            try:
                self._sessao.close()
            except Exception:
                pass
            self._sessao = None
        self._encerrada = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.fechar()

    # ============ helpers genéricos (qualquer banco de MODULOS_BD) ============

    def consultar(self, sql: str, params: Optional[dict] = None) -> list[dict]:
        """Runs a SELECT on the bound database; returns rows as dicts.

        Executa SQL de leitura no banco vinculado (`chave_db`) via
        Session (fail-soft: falha registra warning e devolve `[]`). Use
        para migrar gradualmente o SQL cru dos módulos ao SQLAlchemy.
        """
        if self.sessoes is None:
            return []
        try:
            rows = self.sessoes.execute(
                text(sql), params or {}).mappings().all()
            return [dict(r) for r in rows]
        except Exception as ex:
            _log().warning(f"consultar({self.chave_db}): {ex}")
            return []

    def executar(self, sql: str, params: Optional[dict] = None) -> int:
        """Runs a DML statement on the bound database; returns rowcount.

        Executa SQL de escrita no banco vinculado (`chave_db`) com commit
        (fail-soft: falha registra warning, faz rollback e devolve `-1`).
        Use com `ultimo_id()` para recuperar o id gerado no INSERT.
        """
        if self.sessoes is None:
            return -1
        try:
            res = self.sessoes.execute(text(sql), params or {})
            self.sessoes.commit()
            return res.rowcount if res.rowcount is not None else 0
        except Exception as ex:
            _log().warning(f"executar({self.chave_db}): {ex}")
            try:
                self.sessoes.rollback()
            except Exception:
                pass
            return -1

    def ultimo_id(self):
        """Returns the last autoincrement id inserted on the bound database.

        SQLite: `SELECT last_insert_rowid()` (sqlite-only — não existe no
        PG). Postgres: `SELECT LASTVAL()` (último `SERIAL` da sessão;
        `RETURNING id` já é capturado como `lastrowid` no proxy
        `_CursorPostgres` para INSERTs diretos). Falha devolve None
        (fail-soft, sem derrubar handler NiceGUI). Teste com
        `TISOSDOCFLY_FORCE_SQLITE=1` para o caminho sqlite-only.
        """
        if self.sessoes is None:
            return None
        try:
            try:
                from mod_tisosdocfly import banco_conexao
                eh_pg = banco_conexao.sgbd_ativo() == "postgres"
            except Exception:
                eh_pg = False
            if eh_pg:
                try:
                    return self.sessoes.execute(text("SELECT LASTVAL()")).scalar()
                except Exception as exc_pg:
                    try:
                        self.sessoes.rollback()
                    except Exception:
                        pass
                    _log().exception(f"ultimo_id({self.chave_db}) PG LASTVAL: {exc_pg}")
                    return None
            return self.sessoes.execute(
                text("SELECT last_insert_rowid()")).scalar()
        except Exception as ex:
            _log().exception(f"ultimo_id({self.chave_db}): {ex}")
            return None

    # ============ tb_config ============

    def obter_config(self, chave: str, padrao: str = "") -> str:
        """Returns the value for a configuration key or `padrao` if not found.

        EN: Reads a single key from tb_config (fail-soft: returns default).
        PT: Lê uma chave da tb_config (fail-soft: devolve padrão em caso de erro).
        """
        if self.sessoes is None:
            return padrao
        try:
            row = self.sessoes.execute(
                text("SELECT valor FROM tb_config WHERE chave=:chave"),
                {"chave": chave},
            ).scalar_one_or_none()
            return row if row is not None else padrao
        except Exception as ex:
            _log().warning(f"obter_config('{chave}'): {ex}")
            return padrao

    def definir_config(self, chave: str, valor) -> bool:
        """Inserts or replaces a configuration key (upsert ON CONFLICT).

        EN: Upserts a configuration key (portable: SQLite and PostgreSQL).
        PT: Faz upsert de uma chave de configuração (portável: SQLite e PostgreSQL).
        """
        if self.sessoes is None:
            return False
        try:
            self.sessoes.execute(
                text("INSERT INTO tb_config (chave, valor) VALUES (:chave, :valor) "
                     "ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor"),
                {"chave": chave, "valor": str(valor)},
            )
            self.sessoes.commit()
            return True
        except Exception as ex:
            _log().warning(f"definir_config('{chave}'): {ex}")
            return False

    def listar_config(self) -> list[Configuracao]:
        """Returns all configuration entries.

        EN: Returns all rows from tb_config as Configuracao dataclass instances.
        PT: Devolve todas as entradas de configuração como instâncias de Configuracao.
        """
        if self.sessoes is None:
            return []
        try:
            rows = self.sessoes.execute(
                text("SELECT chave, valor FROM tb_config ORDER BY chave")
            ).fetchall()
            return [Configuracao(chave=r[0], valor=r[1]) for r in rows]
        except Exception as ex:
            _log().warning(f"listar_config: {ex}")
            return []

    # ============ tb_sessoes ============

    def registrar_sessao(
        self,
        usuario: str,
        modulo: str,
        cookie_hash: str,
        login_timestamp: Optional[datetime] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        dispositivo: Optional[str] = None,
        mac: Optional[str] = None,
    ) -> Optional[int]:
        """Inserts a new session and returns the new row id.

        EN: Creates a session record (fail-soft: logs and returns None).
        PT: Cria um registro de sessão (fail-soft: registra e retorna None).
        """
        if self.sessoes is None:
            return None
        try:
            resultado = self.sessoes.execute(
                text("""INSERT INTO tb_sessoes
                    (usuario, modulo, login_timestamp, cookie_hash, ip, user_agent, dispositivo, mac)
                    VALUES (:u, :m, :t, :h, :ip, :ua, :d, :mac)"""),
                {
                    "u": usuario, "m": modulo,
                    "t": login_timestamp or datetime.now(),
                    "h": cookie_hash,
                    "ip": ip, "ua": user_agent,
                    "d": dispositivo, "mac": mac,
                },
            )
            self.sessoes.commit()
            return resultado.lastrowid
        except Exception as ex:
            _log().exception(f"registrar_sessao('{usuario}'): {ex}")
            return None

    def obter_sessao_ativa(self, usuario: str, cookie_hash: str) -> Optional[Sessao]:
        """Returns the active session for a user+hash pair.

        EN: Returns the session row where logout_timestamp IS NULL (fail-soft).
        PT: Devolve a sessão ativa para o par usuário+hash (fail-soft).
        """
        if self.sessoes is None:
            return None
        try:
            row = self.sessoes.execute(
                text("""SELECT id, usuario, modulo, login_timestamp, logout_timestamp,
                                cookie_hash, ip, user_agent, dispositivo, mac
                         FROM tb_sessoes
                         WHERE usuario=:u AND cookie_hash=:h AND logout_timestamp IS NULL
                         LIMIT 1"""),
                {"u": usuario, "h": cookie_hash},
            ).fetchone()
            if row is None:
                return None
            return Sessao(
                id=row[0], usuario=row[1], modulo=row[2],
                login_timestamp=row[3], logout_timestamp=row[4],
                cookie_hash=row[5], ip=row[6], user_agent=row[7],
                dispositivo=row[8], mac=row[9],
            )
        except Exception as ex:
            _log().warning(f"obter_sessao_ativa('{usuario}'): {ex}")
            return None

    def sessao_ativa(self, usuario: str, cookie_hash: str) -> bool:
        """True if an active session exists for this user+hash.

        EN: Checks session existence (fail-soft: returns False).
        PT: Verifica existência de sessão ativa (fail-soft: retorna False).
        """
        if self.sessoes is None:
            return False
        try:
            row = self.sessoes.execute(
                text("""SELECT 1 FROM tb_sessoes
                         WHERE usuario=:u AND cookie_hash=:h AND logout_timestamp IS NULL
                         LIMIT 1"""),
                {"u": usuario, "h": cookie_hash},
            ).scalar_one_or_none()
            return row is not None
        except Exception as ex:
            _log().warning(f"sessao_ativa('{usuario}'): {ex}")
            return False

    def fechar_sessao(self, usuario: str, cookie_hash: str) -> bool:
        """Soft-closes a session by setting logout_timestamp.

        EN: Sets logout_timestamp=NOW() for the matching session (fail-soft).
        PT: Define logout_timestamp para a sessão correspondente (fail-soft).
        """
        if self.sessoes is None:
            return False
        try:
            self.sessoes.execute(
                text("""UPDATE tb_sessoes
                         SET logout_timestamp=:t
                         WHERE usuario=:u AND cookie_hash=:h AND logout_timestamp IS NULL"""),
                {"t": datetime.now(), "u": usuario, "h": cookie_hash},
            )
            self.sessoes.commit()
            return True
        except Exception as ex:
            _log().warning(f"fechar_sessao('{usuario}'): {ex}")
            return False

    def fechar_todas_sessoes(self, usuario: str) -> int:
        """Closes ALL open sessions for a user.

        EN: Sets logout_timestamp on all open sessions for the user.
        PT: Fecha todas as sessões abertas do usuário.
        Returns the number of sessions closed.
        """
        if self.sessoes is None:
            return 0
        try:
            resultado = self.sessoes.execute(
                text("""UPDATE tb_sessoes
                         SET logout_timestamp=:t
                         WHERE usuario=:u AND logout_timestamp IS NULL"""),
                {"t": datetime.now(), "u": usuario},
            )
            self.sessoes.commit()
            return resultado.rowcount
        except Exception as ex:
            _log().warning(f"fechar_todas_sessoes('{usuario}'): {ex}")
            return 0

    def podar_sessoes(self, usuario: str, limite: int = 50) -> int:
        """LGPD retention: deletes oldest sessions beyond `limite` for the user.

        EN: Keeps only the `limite` most-recent sessions per user (fail-soft).
        PT: Mantém apenas as `limite` sessões mais recentes por usuário (fail-soft).
        """
        if self.sessoes is None or limite <= 0:
            return 0
        try:
            resultado = self.sessoes.execute(
                text("""DELETE FROM tb_sessoes
                         WHERE usuario=:u AND id NOT IN (
                                SELECT id FROM tb_sessoes
                                WHERE usuario=:u
                                ORDER BY id DESC LIMIT :lim)"""),
                {"u": usuario, "lim": limite},
            )
            self.sessoes.commit()
            return resultado.rowcount
        except Exception as ex:
            _log().warning(f"podar_sessoes('{usuario}'): {ex}")
            return 0

    # ============ tb_modulos ============

    def listar_modulos(self, somente_ativos: bool = False) -> list[Modulo]:
        """Returns all registered modules, ordered by `ordem` then name.

        EN: Returns module rows as Modulo dataclass instances (fail-soft).
        PT: Devolve módulos como instâncias de Modulo (fail-soft).
        """
        if self.sessoes is None:
            return []
        try:
            sql = "SELECT id, chave, nome, icone, rota, ativo, nativo, ordem FROM tb_modulos"
            if somente_ativos:
                sql += " WHERE ativo=1"
            sql += " ORDER BY ordem ASC, nome"
            rows = self.sessoes.execute(text(sql)).fetchall()
            return [
                Modulo(id=r[0], chave=r[1], nome=r[2], icone=r[3],
                       rota=r[4], ativo=bool(r[5]), nativo=bool(r[6]), ordem=r[7])
                for r in rows
            ]
        except Exception as ex:
            _log().warning(f"listar_modulos: {ex}")
            return []

    def obter_modulo(self, chave: str) -> Optional[Modulo]:
        """Returns the module with the given key or None if not found.

        EN: Single module lookup (fail-soft).
        PT: Busca módulo pela chave (fail-soft).
        """
        if self.sessoes is None:
            return None
        try:
            row = self.sessoes.execute(
                text("""SELECT id, chave, nome, icone, rota, ativo, nativo, ordem
                         FROM tb_modulos WHERE chave=:c"""),
                {"c": chave},
            ).fetchone()
            if row is None:
                return None
            return Modulo(id=row[0], chave=row[1], nome=row[2], icone=row[3],
                         rota=row[4], ativo=bool(row[5]), nativo=bool(row[6]),
                         ordem=row[7])
        except Exception as ex:
            _log().warning(f"obter_modulo('{chave}'): {ex}")
            return None

    def registrar_modulo(
        self,
        chave: str,
        nome: str,
        icone: str = "extension",
        rota: str = "#",
        ativo: bool = False,
        nativo: bool = False,
    ) -> bool:
        """Inserts a new module and returns success status.

        EN: Creates a module row (fail-soft).
        PT: Cria um módulo (fail-soft).
        """
        if self.sessoes is None:
            return False
        try:
            max_ordem = self.sessoes.execute(
                text("SELECT COALESCE(MAX(ordem), 0) FROM tb_modulos")
            ).scalar_one()
            self.sessoes.execute(
                text("""INSERT INTO tb_modulos
                         (chave, nome, icone, rota, ativo, nativo, ordem)
                         VALUES (:c, :n, :i, :r, :a, :n2, :o)"""),
                {
                    "c": chave, "n": nome, "i": icone,
                    "r": rota, "a": 1 if ativo else 0,
                    "n2": 1 if nativo else 0, "o": max_ordem + 1,
                },
            )
            self.sessoes.commit()
            return True
        except Exception as ex:
            _log().warning(f"registrar_modulo('{chave}'): {ex}")
            return False

    def atualizar_modulo(
        self,
        chave: str,
        nome: Optional[str] = None,
        icone: Optional[str] = None,
        rota: Optional[str] = None,
        ativo: Optional[bool] = None,
        ordem: Optional[int] = None,
    ) -> bool:
        """Updates mutable fields of a module.

        EN: Partial update of module fields (fail-soft).
        PT: Atualização parcial dos campos do módulo (fail-soft).
        """
        if self.sessoes is None:
            return False
        campos = {}
        if nome is not None:
            campos["nome"] = nome
        if icone is not None:
            campos["icone"] = icone
        if rota is not None:
            campos["rota"] = rota
        if ativo is not None:
            campos["ativo"] = 1 if ativo else 0
        if ordem is not None:
            campos["ordem"] = ordem
        if not campos:
            return True
        set_sql = ", ".join(f"{k}=:{k}" for k in campos)
        campos["c"] = chave
        try:
            self.sessoes.execute(
                text(f"UPDATE tb_modulos SET {set_sql} WHERE chave=:c"),  # nosec B608 — `set_sql` é montado só das chaves literais do if-chain acima (nome/icone/rota/ativo/ordem); valores vão por bind `:nome` etc., nunca interpolados
                campos,
            )
            self.sessoes.commit()
            return True
        except Exception as ex:
            _log().warning(f"atualizar_modulo('{chave}'): {ex}")
            return False

    def reordenar_modulos(self, chaves_ordenadas: list[str]) -> bool:
        """Updates the `ordem` column for all modules in the given sequence.

        EN: Batch reorder of modules (fail-soft).
        PT: Reordenação em lote dos módulos (fail-soft).
        """
        if self.sessoes is None:
            return False
        try:
            for idx, chave in enumerate(chaves_ordenadas, start=1):
                self.sessoes.execute(
                    text("UPDATE tb_modulos SET ordem=:o WHERE chave=:c"),
                    {"o": idx, "c": chave},
                )
            self.sessoes.commit()
            return True
        except Exception as ex:
            _log().warning(f"reordenar_modulos: {ex}")
            return False

    def excluir_modulo(self, chave: str) -> bool:
        """Deletes a module by key (fails silently if not found).

        EN: Removes a module from the registry (fail-soft).
        PT: Remove um módulo do registro (fail-soft).
        """
        if self.sessoes is None:
            return False
        try:
            self.sessoes.execute(
                text("DELETE FROM tb_modulos WHERE chave=:c"),
                {"c": chave},
            )
            self.sessoes.commit()
            return True
        except Exception as ex:
            _log().warning(f"excluir_modulo('{chave}'): {ex}")
            return False

    def modulo_existe(self, chave: str) -> bool:
        """True if a module with this key exists.

        EN: Checks existence of a module key (fail-soft: returns False).
        PT: Verifica existência de chave de módulo (fail-soft: retorna False).
        """
        if self.sessoes is None:
            return False
        try:
            row = self.sessoes.execute(
                text("SELECT 1 FROM tb_modulos WHERE chave=:c LIMIT 1"),
                {"c": chave},
            ).scalar_one_or_none()
            return row is not None
        except Exception as ex:
            _log().warning(f"modulo_existe('{chave}'): {ex}")
            return False
