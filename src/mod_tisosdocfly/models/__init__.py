"""Models package for mod_tisosdocfly — dataclasses + SQLAlchemy ORM.

Provides type-safe domain models for the central database tables:
tb_config, tb_sessoes, tb_modulos. Uses SQLAlchemy 2.0 Table objects
mapped to Python dataclasses via `mapper()`, keeping SQLAlchemy optional
(the ORM layer in `repositorio.py` falls back to CrudBase if SQLAlchemy
is unavailable).

Architecture (pilot module — pattern to propagate):
    models/          — dataclass definitions + SQLAlchemy Table metadata
    repositorio.py   — data access layer using SQLAlchemy ORM Session
    bd_conexao.py   — session factory (engine bound to DB_PATH)
    autenticacao.py  — uses Repositorio for all DB operations
    bd_manipulador.py — uses Repositorio for all DB operations

EN: Dataclass definitions mapped to SQLite tables via SQLAlchemy 2.0 ORM.
    PT: Definições de dataclasses mapeadas às tabelas SQLite via SQLAlchemy 2.0 ORM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    Table,
    MetaData,
    text as _sqla_text,
)

__all__ = [
    "Configuracao",
    "Sessao",
    "Modulo",
    "metadata",
]


metadata = MetaData()


tb_config = Table(
    "tb_config",
    metadata,
    Column("chave", String(255), primary_key=True),
    Column("valor", Text, nullable=False),
)


tb_sessoes = Table(
    "tb_sessoes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("usuario", String(100), nullable=False),
    Column("modulo", String(50)),
    Column("login_timestamp", DateTime, default=datetime.now),
    Column("logout_timestamp", DateTime, nullable=True),
    Column("cookie_hash", String(64), nullable=False),
    Column("ip", String(45)),
    Column("user_agent", Text),
    Column("dispositivo", String(100)),
    Column("mac", String(17)),
)


tb_modulos = Table(
    "tb_modulos",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("chave", String(50), nullable=False, unique=True),
    Column("nome", String(100), nullable=False),
    Column("icone", String(50), default="extension"),
    Column("rota", String(255), nullable=False),
    Column("ativo", Boolean, default=True, nullable=False, server_default=_sqla_text("1")),
    Column("nativo", Boolean, default=False, nullable=False, server_default=_sqla_text("0")),
    Column("ordem", Integer, default=0, nullable=False, server_default=_sqla_text("0")),
)


@dataclass
class Configuracao:
    """Key-value configuration entry (tb_config).

    EN: Represents a single key=value configuration pair from tb_config.
    PT: Representa um par chave=valor de configuração da tb_config.
    """
    chave: str
    valor: str


@dataclass
class Sessao:
    """User session entry (tb_sessoes) with LGPD tracking fields.

    EN: Represents an active or closed user session with optional
    traceability fields (IP, user-agent, device, MAC).
    PT: Representa uma sessão de usuário ativa ou fechada com campos
    opcionais de rastreabilidade LGPD (IP, user-agent, dispositivo, MAC).
    """
    id: Optional[int] = None
    usuario: str = ""
    modulo: Optional[str] = None
    login_timestamp: Optional[datetime] = None
    logout_timestamp: Optional[datetime] = None
    cookie_hash: str = ""
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    dispositivo: Optional[str] = None
    mac: Optional[str] = None


@dataclass
class Modulo:
    """Module registry entry (tb_modulos).

    EN: Represents a registered module in the system sidebar and
    user-access grants.
    PT: Representa um módulo registrado no sistema para exibição na
    barra lateral e liberações de acesso por usuário.
    """
    id: Optional[int] = None
    chave: str = ""
    nome: str = ""
    icone: str = "extension"
    rota: str = "#"
    ativo: bool = True
    nativo: bool = False
    ordem: int = 0


from sqlalchemy.orm import registry

_reg = registry()
_reg.map_imperatively(Configuracao, tb_config)
_reg.map_imperatively(Sessao, tb_sessoes)
_reg.map_imperatively(Modulo, tb_modulos)
