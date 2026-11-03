"""Core flight-report domain: clients, properties, flights, media and reports.

Domínio do T! SOS DocFly: cliente → propriedade → voo → upload de fotos/vídeos
→ análise de imagem (baseline/ONNX) → laudo PDF. Tudo no banco central
(`db_mod_tisosdocfly.db`); sem cross-query entre módulos.

O schema é criado de forma idempotente por `garantir_schema_voos`, chamado
pelo bootstrap (`bd_criador.inicializar_bancos`) e sob demanda pelas funções
públicas. A mídia fica fora do banco, em `src/mod_tisosdocfly/midia/<voo_id>/`
(ou em `TISOSDOCFLY_DIR_MIDIA`), e o banco guarda só os metadados e o SHA-256.
"""
import hashlib
import json
import mimetypes
import os
import re
import unicodedata
from datetime import date, datetime

from mod_tisosdocfly.bd_conexao import DB_PATH
from mod_tisosdocfly.bd_manipulador import audit_log
from mod_tisosdocfly.crud_base import CrudBase

_CHAVE_BD = "tisosdocfly"
_MODULO_AUDITORIA = "tisosdocfly"
_schema_ok = False

SCHEMA_VOOS = (
    """
    CREATE TABLE IF NOT EXISTS tb_clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        documento TEXT,
        email TEXT,
        telefone TEXT,
        observacao TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_propriedades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        endereco TEXT,
        geometria TEXT,
        observacao TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_voos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER NOT NULL,
        propriedade_id INTEGER,
        data_voo TEXT,
        piloto TEXT,
        drone TEXT,
        gsd_cm REAL,
        status TEXT NOT NULL DEFAULT 'rascunho',
        observacao TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_capturas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        voo_id INTEGER NOT NULL,
        tipo TEXT,
        status TEXT NOT NULL DEFAULT 'pendente',
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_arquivos_midia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        captura_id INTEGER,
        voo_id INTEGER NOT NULL,
        nome_original TEXT,
        nome_seguro TEXT NOT NULL,
        caminho TEXT NOT NULL,
        hash_sha256 TEXT,
        tamanho_bytes INTEGER,
        mime TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_laudos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        voo_id INTEGER NOT NULL,
        cliente_id INTEGER,
        titulo TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'base',
        resumo TEXT,
        caminho_pdf TEXT,
        gerado_em DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_analises_ia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        voo_id INTEGER NOT NULL,
        arquivo_id INTEGER,
        modulo TEXT NOT NULL,
        modelo TEXT,
        versao TEXT,
        resumo TEXT,
        ocorrencias_json TEXT,
        metricas_json TEXT,
        revisao_humana INTEGER NOT NULL DEFAULT 0,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
)

INDICES_VOOS = (
    "CREATE INDEX IF NOT EXISTS idx_propriedades_cliente "
    "ON tb_propriedades (cliente_id)",
    "CREATE INDEX IF NOT EXISTS idx_voos_cliente ON tb_voos (cliente_id)",
    "CREATE INDEX IF NOT EXISTS idx_voos_propriedade "
    "ON tb_voos (propriedade_id)",
    "CREATE INDEX IF NOT EXISTS idx_capturas_voo ON tb_capturas (voo_id)",
    "CREATE INDEX IF NOT EXISTS idx_midias_voo ON tb_arquivos_midia (voo_id)",
    "CREATE INDEX IF NOT EXISTS idx_midias_captura "
    "ON tb_arquivos_midia (captura_id)",
    "CREATE INDEX IF NOT EXISTS idx_laudos_voo ON tb_laudos (voo_id)",
    "CREATE INDEX IF NOT EXISTS idx_analises_ia_voo "
    "ON tb_analises_ia (voo_id)",
    "CREATE INDEX IF NOT EXISTS idx_analises_ia_modulo "
    "ON tb_analises_ia (modulo)",
)

_COLUNAS_CLIENTE = (
    "id", "nome", "documento", "email", "telefone", "observacao", "criado_em",
)
_COLUNAS_PROPRIEDADE = (
    "id", "cliente_id", "nome", "endereco", "geometria", "observacao",
    "criado_em",
)
_COLUNAS_VOO = (
    "id", "cliente_id", "propriedade_id", "data_voo", "piloto", "drone",
    "gsd_cm", "status", "observacao", "criado_em",
)
_COLUNAS_MIDIA = (
    "id", "captura_id", "voo_id", "nome_original", "nome_seguro", "caminho",
    "hash_sha256", "tamanho_bytes", "mime", "criado_em",
)
_COLUNAS_LAUDO = (
    "id", "voo_id", "cliente_id", "titulo", "status", "resumo",
    "gerado_em", "caminho_pdf",
)
_COLUNAS_ANALISE_IA = (
    "id", "voo_id", "arquivo_id", "modulo", "modelo", "versao", "resumo",
    "ocorrencias_json", "metricas_json", "revisao_humana", "criado_em",
)


def _log():
    """Logger loguru vinculado ao núcleo (`tisosdocfly`)."""
    from mod_tisosdocfly import observabilidade
    return observabilidade.get_logger(_MODULO_AUDITORIA)


def _agora():
    """Timestamp local no formato usado pelo banco central."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _crud():
    """CrudBase ligado ao banco central (SQLite ou PostgreSQL)."""
    return CrudBase(DB_PATH, _CHAVE_BD)


def _dictificar(linhas, colunas):
    """Converte tuplas do banco em dicionários {coluna: valor}."""
    try:
        return [dict(zip(colunas, linha)) for linha in (linhas or [])]
    except Exception:
        return []


def _primeiro(linha, colunas):
    """Converte a primeira linha em dicionário (ou None)."""
    if not linha:
        return None
    try:
        return dict(zip(colunas, linha))
    except Exception:
        return None


def _registrar_auditoria(ator, acao, descricao, hash_arquivo=None):
    """Registra a ação no banco central sem derrubar o fluxo de negócio."""
    try:
        audit_log(ator or "-", _MODULO_AUDITORIA, acao, descricao,
                  hash_arquivo)
    except Exception as exc:
        try:
            _log().exception(f"voos: falha ao auditar '{acao}': {exc}")
        except Exception:
            pass


def garantir_schema_voos():
    """Creates the idempotent Onda 1 schema in the central database.

    Cria (sem apagar nada) as tabelas de clientes, propriedades, voos,
    capturas, mídias e laudos, mais os índices de busca. DDL portável
    (`CREATE TABLE/INDEX IF NOT EXISTS`), válida em SQLite e PostgreSQL.
    Devolve `True` quando o schema está pronto.
    """
    global _schema_ok
    if _schema_ok:
        return True
    try:
        crud = _crud()
        with crud.transacao() as cur:
            for ddl in SCHEMA_VOOS:
                cur.execute(ddl)
            for ddl in INDICES_VOOS:
                cur.execute(ddl)
            # Migração idempotente: bancos criados antes do laudo PDF não
            # têm `caminho_pdf`. SQLite não aceita ADD COLUMN IF NOT EXISTS
            # em todas as versões; o try/except cobre SQLite e o proxy cobre
            # PostgreSQL.
            try:
                cur.execute(
                    "ALTER TABLE tb_laudos ADD COLUMN caminho_pdf TEXT")
            except Exception:
                pass
        _schema_ok = True
        return True
    except Exception as exc:
        try:
            _log().exception(f"voos.garantir_schema_voos: {exc}")
        except Exception:
            pass
        return False


def _pronto():
    """Garante o schema antes de qualquer leitura/escrita pública."""
    return garantir_schema_voos()


def nome_seguro(nome_original, padrao="arquivo"):
    """Returns a filesystem-safe name (a-z, 0-9, `_`, `-` and the extension).

    Normaliza acentos, remove caminho, troca qualquer caractere fora do
    conjunto permitido por `_`, colapsa repetições e limita o tamanho. O
    nome resultante nunca é vazio nem começa/termina com ponto, hífen ou
    sublinhado.
    """
    try:
        base = os.path.basename(str(nome_original or "").replace("\\", "/"))
        base = unicodedata.normalize("NFKD", base)
        base = base.encode("ascii", "ignore").decode("ascii").lower()
        base = re.sub(r"[^a-z0-9._-]+", "_", base)
        base = re.sub(r"_{2,}", "_", base).strip("._-")
        if not base:
            base = padrao
        raiz, ext = os.path.splitext(base)
        ext = re.sub(r"[^a-z0-9.]", "", ext.lower())[:10]
        raiz = (raiz[:60].strip("._-") or padrao)
        return f"{raiz}{ext}"
    except Exception:
        return padrao


def diretorio_midia(voo_id=None):
    """Returns the media root (or the flight folder) for uploads.

    A raiz é `src/mod_tisosdocfly/midia`; `TISOSDOCFLY_DIR_MIDIA` redireciona
    (usado pela suíte para não sujar o repositório). Com `voo_id`, devolve
    a pasta daquele voo, criada sob demanda por `salvar_arquivo_midia`.
    """
    raiz = (os.environ.get("TISOSDOCFLY_DIR_MIDIA", "").strip()
            or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "midia"))
    if voo_id is None:
        return raiz
    return os.path.join(raiz, str(voo_id))


def _ler_conteudo(conteudo):
    """Normaliza bytes/file-like/str em bytes (None quando inválido)."""
    try:
        if conteudo is None:
            return None
        if isinstance(conteudo, (bytes, bytearray, memoryview)):
            return bytes(conteudo)
        if hasattr(conteudo, "read"):
            dados = conteudo.read()
            if isinstance(dados, str):
                return dados.encode("utf-8")
            return bytes(dados)
        if isinstance(conteudo, str):
            return conteudo.encode("utf-8")
    except Exception as exc:
        try:
            _log().exception(f"voos._ler_conteudo: {exc}")
        except Exception:
            pass
    return None


def _tipo_por_mime(mime, nome_original=""):
    """Classifica a captura em foto/vídeo/arquivo a partir do MIME/nome."""
    mime = (mime or "").lower().strip()
    if not mime:
        mime = (mimetypes.guess_type(nome_original or "")[0] or "").lower()
    if mime.startswith("video/"):
        return "video", mime
    if mime.startswith("image/"):
        return "foto", mime
    return "arquivo", mime


# =============================================================================
# Clientes
# =============================================================================

def criar_cliente(nome, documento="", email="", telefone="", observacao="",
                  ator=""):
    """Creates a client and returns its id (None on failure)."""
    nome = (nome or "").strip()
    if not nome:
        return None
    try:
        if not _pronto():
            return None
        crud = _crud()
        novo_id = crud.criar(
            "INSERT INTO tb_clientes (nome, documento, email, telefone, "
            "observacao) VALUES (?, ?, ?, ?, ?)",
            (nome, (documento or "").strip(), (email or "").strip(),
             (telefone or "").strip(), (observacao or "").strip()))
        _registrar_auditoria(ator, "criar_cliente",
                             f"cliente #{novo_id}: {nome}")
        return novo_id
    except Exception as exc:
        _log().exception(f"voos.criar_cliente('{nome}'): {exc}")
        return None


def obter_cliente(cliente_id):
    """Returns one client as a dict (or None)."""
    try:
        if not _pronto():
            return None
        linha = _crud().obter(
            "SELECT id, nome, documento, email, telefone, observacao, "
            "criado_em FROM tb_clientes WHERE id=?", (cliente_id,))
        return _primeiro(linha, _COLUNAS_CLIENTE)
    except Exception as exc:
        _log().exception(f"voos.obter_cliente({cliente_id}): {exc}")
        return None


def listar_clientes(busca=""):
    """Lists clients, optionally filtered by name/document/email/phone."""
    try:
        if not _pronto():
            return []
        termo = (busca or "").strip()
        sql = ("SELECT id, nome, documento, email, telefone, observacao, "
               "criado_em FROM tb_clientes")
        params = ()
        if termo:
            like = f"%{termo}%"
            sql += (" WHERE nome LIKE ? OR documento LIKE ? OR email LIKE ? "
                    "OR telefone LIKE ?")
            params = (like, like, like, like)
        sql += " ORDER BY nome, id"
        return _dictificar(_crud().listar(sql, params), _COLUNAS_CLIENTE)
    except Exception as exc:
        _log().exception(f"voos.listar_clientes('{busca}'): {exc}")
        return []


def atualizar_cliente(cliente_id, nome=None, documento=None, email=None,
                      telefone=None, observacao=None, ator=""):
    """Updates the provided client fields and returns True on success."""
    try:
        if not _pronto():
            return False
        campos = {}
        for chave, valor in (("nome", nome), ("documento", documento),
                             ("email", email), ("telefone", telefone),
                             ("observacao", observacao)):
            if valor is not None:
                campos[chave] = (valor or "").strip()
        if not campos:
            return True
        sets = ", ".join(f"{chave}=?" for chave in campos)
        params = tuple(campos.values()) + (cliente_id,)
        linhas = _crud().atualizar(
            f"UPDATE tb_clientes SET {sets} WHERE id=?", params)
        if linhas:
            _registrar_auditoria(ator, "atualizar_cliente",
                                 f"cliente #{cliente_id}")
            return True
        return False
    except Exception as exc:
        _log().exception(f"voos.atualizar_cliente({cliente_id}): {exc}")
        return False


def excluir_cliente(cliente_id, ator=""):
    """Deletes a client only when it has no properties or flights."""
    try:
        if not _pronto():
            return False
        crud = _crud()
        total_prop = crud.obter(
            "SELECT COUNT(*) FROM tb_propriedades WHERE cliente_id=?",
            (cliente_id,))[0]
        total_voos = crud.obter(
            "SELECT COUNT(*) FROM tb_voos WHERE cliente_id=?",
            (cliente_id,))[0]
        if (total_prop or 0) or (total_voos or 0):
            return False
        linhas = crud.excluir("DELETE FROM tb_clientes WHERE id=?",
                              (cliente_id,))
        if linhas:
            _registrar_auditoria(ator, "excluir_cliente",
                                 f"cliente #{cliente_id}")
            return True
        return False
    except Exception as exc:
        _log().exception(f"voos.excluir_cliente({cliente_id}): {exc}")
        return False


# =============================================================================
# Propriedades
# =============================================================================

def criar_propriedade(cliente_id, nome, endereco="", geometria="",
                      observacao="", ator=""):
    """Creates a property for an existing client and returns its id."""
    try:
        nome = (nome or "").strip()
        if not nome or not obter_cliente(cliente_id):
            return None
        if not _pronto():
            return None
        novo_id = _crud().criar(
            "INSERT INTO tb_propriedades (cliente_id, nome, endereco, "
            "geometria, observacao) VALUES (?, ?, ?, ?, ?)",
            (cliente_id, nome, (endereco or "").strip(),
             (geometria or "").strip(), (observacao or "").strip()))
        _registrar_auditoria(ator, "criar_propriedade",
                             f"propriedade #{novo_id}: {nome} "
                             f"(cliente #{cliente_id})")
        return novo_id
    except Exception as exc:
        _log().exception(f"voos.criar_propriedade({cliente_id}): {exc}")
        return None


def obter_propriedade(propriedade_id):
    """Returns one property as a dict (or None)."""
    try:
        if not _pronto():
            return None
        linha = _crud().obter(
            "SELECT id, cliente_id, nome, endereco, geometria, observacao, "
            "criado_em FROM tb_propriedades WHERE id=?", (propriedade_id,))
        return _primeiro(linha, _COLUNAS_PROPRIEDADE)
    except Exception as exc:
        _log().exception(f"voos.obter_propriedade({propriedade_id}): {exc}")
        return None


def listar_propriedades(cliente_id=None, busca=""):
    """Lists properties, optionally by client and by name/address."""
    try:
        if not _pronto():
            return []
        termo = (busca or "").strip()
        sql = ("SELECT id, cliente_id, nome, endereco, geometria, observacao, "
               "criado_em FROM tb_propriedades")
        condicoes, params = [], []
        if cliente_id is not None:
            condicoes.append("cliente_id=?")
            params.append(cliente_id)
        if termo:
            like = f"%{termo}%"
            condicoes.append("(nome LIKE ? OR endereco LIKE ?)")
            params.extend((like, like))
        if condicoes:
            sql += " WHERE " + " AND ".join(condicoes)
        sql += " ORDER BY nome, id"
        return _dictificar(_crud().listar(sql, tuple(params)),
                           _COLUNAS_PROPRIEDADE)
    except Exception as exc:
        _log().exception(f"voos.listar_propriedades: {exc}")
        return []


def atualizar_propriedade(propriedade_id, nome=None, endereco=None,
                          geometria=None, observacao=None, ator=""):
    """Updates the provided property fields and returns True on success."""
    try:
        if not _pronto():
            return False
        campos = {}
        for chave, valor in (("nome", nome), ("endereco", endereco),
                             ("geometria", geometria),
                             ("observacao", observacao)):
            if valor is not None:
                campos[chave] = (valor or "").strip()
        if not campos:
            return True
        sets = ", ".join(f"{chave}=?" for chave in campos)
        params = tuple(campos.values()) + (propriedade_id,)
        linhas = _crud().atualizar(
            f"UPDATE tb_propriedades SET {sets} WHERE id=?", params)
        if linhas:
            _registrar_auditoria(ator, "atualizar_propriedade",
                                 f"propriedade #{propriedade_id}")
            return True
        return False
    except Exception as exc:
        _log().exception(f"voos.atualizar_propriedade({propriedade_id}): {exc}")
        return False


def excluir_propriedade(propriedade_id, ator=""):
    """Deletes a property only when it has no flights."""
    try:
        if not _pronto():
            return False
        crud = _crud()
        total = crud.obter(
            "SELECT COUNT(*) FROM tb_voos WHERE propriedade_id=?",
            (propriedade_id,))[0]
        if total:
            return False
        linhas = crud.excluir("DELETE FROM tb_propriedades WHERE id=?",
                              (propriedade_id,))
        if linhas:
            _registrar_auditoria(ator, "excluir_propriedade",
                                 f"propriedade #{propriedade_id}")
            return True
        return False
    except Exception as exc:
        _log().exception(f"voos.excluir_propriedade({propriedade_id}): {exc}")
        return False


# =============================================================================
# Voos
# =============================================================================

def criar_voo(cliente_id, propriedade_id, data_voo="", piloto="",
              drone="", gsd_cm=None, status="rascunho",
              observacao="", ator=""):
    """Creates a flight tied to an existing client/property.

    A propriedade, quando informada, precisa existir e pertencer ao
    cliente — o fluxo do produto é cliente → propriedade → voo.
    """
    try:
        if not obter_cliente(cliente_id):
            return None
        if propriedade_id:
            prop = obter_propriedade(propriedade_id)
            if not prop or prop.get("cliente_id") != cliente_id:
                return None
        if not _pronto():
            return None
        try:
            gsd = float(str(gsd_cm).replace(",", ".")) if gsd_cm not in (
                None, "") else None
        except Exception:
            gsd = None
        novo_id = _crud().criar(
            "INSERT INTO tb_voos (cliente_id, propriedade_id, data_voo, "
            "piloto, drone, gsd_cm, status, observacao) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cliente_id, propriedade_id or None,
             (data_voo or "").strip() or date.today().isoformat(),
             (piloto or "").strip(), (drone or "").strip(),
             gsd, (status or "rascunho").strip() or "rascunho",
             (observacao or "").strip()))
        _registrar_auditoria(ator, "criar_voo",
                             f"voo #{novo_id} (cliente #{cliente_id}, "
                             f"propriedade #{propriedade_id})")
        return novo_id
    except Exception as exc:
        _log().exception(f"voos.criar_voo: {exc}")
        return None


def obter_voo(voo_id):
    """Returns one flight (with client/property names) as a dict or None."""
    try:
        if not _pronto():
            return None
        linha = _crud().obter(
            "SELECT v.id, v.cliente_id, v.propriedade_id, v.data_voo, "
            "v.piloto, v.drone, v.gsd_cm, v.status, v.observacao, "
            "v.criado_em, c.nome AS cliente_nome, "
            "p.nome AS propriedade_nome "
            "FROM tb_voos v "
            "LEFT JOIN tb_clientes c ON c.id=v.cliente_id "
            "LEFT JOIN tb_propriedades p ON p.id=v.propriedade_id "
            "WHERE v.id=?", (voo_id,))
        colunas = _COLUNAS_VOO + ("cliente_nome", "propriedade_nome")
        return _primeiro(linha, colunas)
    except Exception as exc:
        _log().exception(f"voos.obter_voo({voo_id}): {exc}")
        return None


def listar_voos(busca="", cliente_id=None, status=None):
    """Lists flights with client/property names, newest first."""
    try:
        if not _pronto():
            return []
        termo = (busca or "").strip()
        sql = ("SELECT v.id, v.cliente_id, v.propriedade_id, v.data_voo, "
               "v.piloto, v.drone, v.gsd_cm, v.status, v.observacao, "
               "v.criado_em, c.nome AS cliente_nome, "
               "p.nome AS propriedade_nome "
               "FROM tb_voos v "
               "LEFT JOIN tb_clientes c ON c.id=v.cliente_id "
               "LEFT JOIN tb_propriedades p ON p.id=v.propriedade_id")
        condicoes, params = [], []
        if cliente_id is not None:
            condicoes.append("v.cliente_id=?")
            params.append(cliente_id)
        if status:
            condicoes.append("v.status=?")
            params.append(status)
        if termo:
            like = f"%{termo}%"
            condicoes.append(
                "(c.nome LIKE ? OR p.nome LIKE ? OR v.piloto LIKE ? "
                "OR v.drone LIKE ? OR v.status LIKE ?)")
            params.extend((like, like, like, like, like))
        if condicoes:
            sql += " WHERE " + " AND ".join(condicoes)
        sql += " ORDER BY v.data_voo DESC, v.id DESC"
        colunas = _COLUNAS_VOO + ("cliente_nome", "propriedade_nome")
        return _dictificar(_crud().listar(sql, tuple(params)), colunas)
    except Exception as exc:
        _log().exception(f"voos.listar_voos('{busca}'): {exc}")
        return []


def atualizar_voo(voo_id, data_voo=None, piloto=None, drone=None,
                  gsd_cm=None, status=None, observacao=None, ator=""):
    """Updates the provided flight fields and returns True on success."""
    try:
        if not _pronto():
            return False
        campos = {}
        for chave, valor in (("data_voo", data_voo), ("piloto", piloto),
                             ("drone", drone), ("status", status),
                             ("observacao", observacao)):
            if valor is not None:
                campos[chave] = (valor or "").strip()
        if gsd_cm is not None:
            try:
                campos["gsd_cm"] = float(str(gsd_cm).replace(",", "."))
            except Exception:
                pass
        if not campos:
            return True
        sets = ", ".join(f"{chave}=?" for chave in campos)
        params = tuple(campos.values()) + (voo_id,)
        linhas = _crud().atualizar(f"UPDATE tb_voos SET {sets} WHERE id=?",
                                   params)
        if linhas:
            _registrar_auditoria(ator, "atualizar_voo", f"voo #{voo_id}")
            return True
        return False
    except Exception as exc:
        _log().exception(f"voos.atualizar_voo({voo_id}): {exc}")
        return False


def excluir_voo(voo_id, ator=""):
    """Deletes a flight only when it has no media or reports."""
    try:
        if not _pronto():
            return False
        crud = _crud()
        total_midia = crud.obter(
            "SELECT COUNT(*) FROM tb_arquivos_midia WHERE voo_id=?",
            (voo_id,))[0]
        total_laudo = crud.obter(
            "SELECT COUNT(*) FROM tb_laudos WHERE voo_id=?", (voo_id,))[0]
        if (total_midia or 0) or (total_laudo or 0):
            return False
        linhas = crud.excluir("DELETE FROM tb_voos WHERE id=?", (voo_id,))
        if linhas:
            _registrar_auditoria(ator, "excluir_voo", f"voo #{voo_id}")
            return True
        return False
    except Exception as exc:
        _log().exception(f"voos.excluir_voo({voo_id}): {exc}")
        return False


# =============================================================================
# Capturas e arquivos de mídia
# =============================================================================

def registrar_captura(voo_id, tipo="foto", status="recebido", ator=""):
    """Registers a capture of a flight and returns its id (None on failure)."""
    try:
        if not obter_voo(voo_id):
            return None
        if not _pronto():
            return None
        novo_id = _crud().criar(
            "INSERT INTO tb_capturas (voo_id, tipo, status) VALUES (?, ?, ?)",
            (voo_id, (tipo or "arquivo").strip(),
             (status or "pendente").strip() or "pendente"))
        _registrar_auditoria(ator, "registrar_captura",
                             f"captura #{novo_id} do voo #{voo_id} "
                             f"({tipo})")
        return novo_id
    except Exception as exc:
        _log().exception(f"voos.registrar_captura({voo_id}): {exc}")
        return None


def salvar_arquivo_midia(voo_id, nome_original, conteudo, mime="",
                         captura_id=None, ator=""):
    """Stores an upload outside the database and records its metadata.

    Calcula o SHA-256 do conteúdo, grava em `midia/<voo_id>/` com nome
    seguro (sem espaço/acento e com prefixo do hash), registra a captura
    quando `captura_id` não é informado e devolve um dict com id, caminho,
    hash, tamanho, mime e nome seguro — ou `None` em falha.
    """
    dados = _ler_conteudo(conteudo)
    if not dados:
        return None
    try:
        voo = obter_voo(voo_id)
        if not voo:
            return None
        if not _pronto():
            return None
        tipo, mime_real = _tipo_por_mime(mime, nome_original)
        hash_sha = hashlib.sha256(dados).hexdigest()
        seguro = nome_seguro(nome_original)
        raiz, ext = os.path.splitext(seguro)
        nome_final = f"{raiz}_{hash_sha[:12]}{ext}"
        pasta = diretorio_midia(voo_id)
        os.makedirs(pasta, exist_ok=True)
        caminho = os.path.join(pasta, nome_final)
        with open(caminho, "wb") as arquivo:
            arquivo.write(dados)
        if captura_id is None:
            captura_id = registrar_captura(voo_id, tipo=tipo,
                                           status="recebido", ator=ator)
        novo_id = _crud().criar(
            "INSERT INTO tb_arquivos_midia (captura_id, voo_id, "
            "nome_original, nome_seguro, caminho, hash_sha256, "
            "tamanho_bytes, mime) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (captura_id, voo_id, (nome_original or "")[:255], nome_final,
             caminho, hash_sha, len(dados), mime_real or ""))
        _registrar_auditoria(
            ator, "salvar_midia",
            f"mídia #{novo_id} do voo #{voo_id}: {nome_final} "
            f"({len(dados)} bytes)",
            hash_sha)
        return {
            "id": novo_id,
            "captura_id": captura_id,
            "voo_id": voo_id,
            "nome_original": nome_original,
            "nome_seguro": nome_final,
            "caminho": caminho,
            "hash_sha256": hash_sha,
            "tamanho_bytes": len(dados),
            "mime": mime_real or "",
        }
    except Exception as exc:
        _log().exception(f"voos.salvar_arquivo_midia({voo_id}): {exc}")
        try:
            caminho_falha = locals().get("caminho")
            if caminho_falha and os.path.isfile(caminho_falha):
                os.remove(caminho_falha)
        except Exception:
            pass
        return None


def listar_midias_do_voo(voo_id):
    """Lists the uploaded media metadata of a flight (oldest first)."""
    try:
        if not _pronto():
            return []
        linhas = _crud().listar(
            "SELECT id, captura_id, voo_id, nome_original, nome_seguro, "
            "caminho, hash_sha256, tamanho_bytes, mime, criado_em "
            "FROM tb_arquivos_midia WHERE voo_id=? ORDER BY id", (voo_id,))
        return _dictificar(linhas, _COLUNAS_MIDIA)
    except Exception as exc:
        _log().exception(f"voos.listar_midias_do_voo({voo_id}): {exc}")
        return []


def obter_midia(midia_id):
    """Returns one media metadata row as a dict (or None)."""
    try:
        if not _pronto():
            return None
        linha = _crud().obter(
            "SELECT id, captura_id, voo_id, nome_original, nome_seguro, "
            "caminho, hash_sha256, tamanho_bytes, mime, criado_em "
            "FROM tb_arquivos_midia WHERE id=?", (midia_id,))
        return _primeiro(linha, _COLUNAS_MIDIA)
    except Exception as exc:
        _log().exception(f"voos.obter_midia({midia_id}): {exc}")
        return None


# =============================================================================
# Laudos
# =============================================================================

def _resumo_laudo_base(voo, midias):
    """Builds the textual summary of the Onda 1 base report."""
    total = len(midias or [])
    fotos = sum(1 for m in midias or [] if (m.get("mime") or "").startswith(
        "image/"))
    videos = sum(1 for m in midias or [] if (m.get("mime") or "").startswith(
        "video/"))
    gsd = voo.get("gsd_cm")
    gsd_txt = f"{gsd:g} cm/px" if isinstance(gsd, (int, float)) else "não informado"
    linhas = [
        f"Laudo base do voo #{voo.get('id')}",
        f"Cliente: {voo.get('cliente_nome') or '-'}",
        f"Propriedade: {voo.get('propriedade_nome') or '-'}",
        f"Data do voo: {voo.get('data_voo') or '-'}",
        f"Piloto: {voo.get('piloto') or '-'}",
        f"Drone: {voo.get('drone') or '-'}",
        f"GSD: {gsd_txt}",
        f"Mídias recebidas: {total} (fotos: {fotos}, vídeos: {videos})",
        "Status: laudo gerado pelo T! SOS DocFly; o pipeline de imagem e a "
        "revisão humana são registrados à parte.",
        "Os arquivos originais permanecem armazenados com hash SHA-256 "
        "para rastreabilidade.",
    ]
    return "\n".join(linhas)


def _mime_imagem(item):
    """True when the media record points to an image the pipeline can read."""
    try:
        mime = str(item.get("mime") or "").lower()
        caminho = str(item.get("caminho") or item.get("nome_seguro") or "")
        ext = os.path.splitext(caminho)[1].lower()
        return (mime.startswith("image/")
                or ext in {".jpg", ".jpeg", ".png", ".tif", ".tiff",
                           ".webp", ".bmp"})
    except Exception:
        return False


def executar_analise_ia(voo_id, modulo="tisosdocfly", ator="", contexto=None):
    """Runs the image pipeline over every image of a flight and stores it.

    Executa o pipeline (baseline RGB ou modelo registrado) em cada imagem do
    voo e grava o resultado em `tb_analises_ia`. Os módulos de negócio leem
    essas análises pela API pública; o núcleo não escreve no banco deles.
    Devolve um resumo com contagens e resultados por arquivo.
    """
    resumo = {"total": 0, "analisadas": 0, "falhas": 0, "ocorrencias": 0,
              "revisao_humana": 0, "resultados": []}
    try:
        if not _pronto():
            return resumo
        voo = obter_voo(voo_id)
        if not voo:
            return resumo
        midias = listar_midias_do_voo(voo_id)
        imagens = [m for m in midias if _mime_imagem(m)]
        resumo["total"] = len(imagens)
        if not imagens:
            return resumo
        from mod_tisosdocfly import ia
        ctx = {"voo_id": voo_id, "voo": voo}
        if isinstance(contexto, dict):
            ctx.update(contexto)
        for midia in imagens:
            try:
                analise = ia.analisar_imagem(
                    midia.get("caminho"), modulo, contexto=ctx)
                if not isinstance(analise, dict):
                    resumo["falhas"] += 1
                    continue
                ocorrencias = analise.get("ocorrencias") or []
                _crud().criar(
                    "INSERT INTO tb_analises_ia "
                    "(voo_id, arquivo_id, modulo, modelo, versao, resumo, "
                    "ocorrencias_json, metricas_json, revisao_humana) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (voo_id, midia.get("id"), modulo,
                     analise.get("modelo"), analise.get("versao"),
                     analise.get("resumo"),
                     json.dumps(ocorrencias, ensure_ascii=False),
                     json.dumps(analise.get("metricas") or {},
                                ensure_ascii=False),
                     1 if analise.get("revisao_humana_obrigatoria") else 0))
                resumo["analisadas"] += 1
                resumo["ocorrencias"] += len(ocorrencias)
                if analise.get("revisao_humana_obrigatoria"):
                    resumo["revisao_humana"] += 1
                resumo["resultados"].append({
                    "midia": midia,
                    "analise": analise,
                })
            except Exception as exc:
                resumo["falhas"] += 1
                _log().exception(
                    f"executar_analise_ia: mídia {midia.get('id')}: {exc}")
        _crud().atualizar(
            "UPDATE tb_voos SET status='analisado' WHERE id=?", (voo_id,))
        _registrar_auditoria(
            ator, "executar_analise_ia",
            f"voo #{voo_id} módulo={modulo}: {resumo['analisadas']}/"
            f"{resumo['total']} imagem(ns), {resumo['ocorrencias']} "
            f"ocorrência(s)")
        return resumo
    except Exception as exc:
        _log().exception(f"executar_analise_ia({voo_id},{modulo}): {exc}")
        return resumo


def listar_analises_ia(voo_id=None, modulo=None):
    """Lists stored image analyses (optionally by flight/module)."""
    try:
        if not _pronto():
            return []
        sql = ("SELECT id, voo_id, arquivo_id, modulo, modelo, versao, "
               "resumo, ocorrencias_json, metricas_json, revisao_humana, "
               "criado_em FROM tb_analises_ia")
        condicoes, params = [], []
        if voo_id is not None:
            condicoes.append("voo_id=?")
            params.append(voo_id)
        if modulo:
            condicoes.append("modulo=?")
            params.append(modulo)
        if condicoes:
            sql += " WHERE " + " AND ".join(condicoes)
        sql += " ORDER BY id DESC"
        return _dictificar(_crud().listar(sql, tuple(params)),
                           _COLUNAS_ANALISE_IA)
    except Exception as exc:
        _log().exception(
            f"listar_analises_ia({voo_id},{modulo}): {exc}")
        return []


def ocorrencias_das_analises(voo_id, modulo=None):
    """Flattens stored analysis JSON into occurrence dicts for a report."""
    try:
        saida = []
        for analise in listar_analises_ia(voo_id=voo_id, modulo=modulo):
            try:
                itens = json.loads(analise.get("ocorrencias_json") or "[]")
            except Exception:
                itens = []
            for item in itens:
                if not isinstance(item, dict):
                    continue
                linha = dict(item)
                linha.setdefault("modulo", analise.get("modulo"))
                linha.setdefault("modelo", analise.get("modelo"))
                saida.append(linha)
        return saida
    except Exception:
        return []


def detectar_linhas_plantio(voo_id, ator="", max_imagens=1,
                            max_lado=192):
    """Detecta linhas de plantio nas primeiras imagens do voo (Hough puro).

    Grava um registro em `tb_analises_ia` com o resumo (linhas, ângulo,
    espaçamento) e devolve a lista de resultados. A conta é lenta em Python
    puro; por isso o padrão é 1 imagem por chamada.
    """
    resultados = []
    try:
        from mod_tisosdocfly import linhas_plantio
        if not _pronto():
            return resultados
        midias = [m for m in listar_midias_do_voo(voo_id)
                  if _mime_imagem(m)][:max(1, int(max_imagens or 1))]
        for midia in midias:
            r = linhas_plantio.detectar_linhas_plantio(
                midia.get("caminho"), max_lado=max_lado)
            if not r:
                continue
            resumo = (
                f"Hough: {r['total_linhas']} linha(s), ângulo "
                f"{r['angulo_dominante']:.1f}°, espaçamento "
                f"{r['espacamento_px']:.1f}px.")
            metricas = {
                "total_linhas": r["total_linhas"],
                "angulo_dominante": r["angulo_dominante"],
                "angulo_mascara": r["angulo_mascara"],
                "espacamento_px": r["espacamento_px"],
                "comprimento_medio": r["comprimento_medio"],
                "vegetacao_ratio": r["vegetacao_ratio"],
            }
            _crud().criar(
                "INSERT INTO tb_analises_ia "
                "(voo_id, arquivo_id, modulo, modelo, versao, resumo, "
                "ocorrencias_json, metricas_json, revisao_humana) "
                "VALUES (?, ?, 'agro', 'hough-linhas-v1', '1.0', ?, '[]', "
                "?, 1)",
                (voo_id, midia.get("id"), resumo,
                 json.dumps(metricas, ensure_ascii=False)))
            resultados.append({"midia": midia, "resultado": r,
                               "resumo": resumo})
        _registrar_auditoria(
            ator, "detectar_linhas_plantio",
            f"voo #{voo_id}: {len(resultados)} imagem(ns)")
        return resultados
    except Exception as exc:
        _log().exception(f"detectar_linhas_plantio({voo_id}): {exc}")
        return resultados


def gerar_laudo_modulo_pdf(chave_modulo, voo_id, titulo, resumo,
                           ocorrencias, ator=""):
    """Gera um PDF de laudo para um módulo de negócio (sem tocar no banco dele).

    Recebe a lista de ocorrências já convertida em dicts pelo módulo e grava
    em `laudos/<chave>/`. Devolve o caminho ou None. A imagem de capa usa até
    6 fotos do voo, quando existirem.
    """
    try:
        voo = obter_voo(voo_id)
        if not voo:
            return None
        midias = listar_midias_do_voo(voo_id)
        imagens = [m.get("caminho") for m in midias
                   if _mime_imagem(m)][:6]
        from mod_tisosdocfly import relatorio
        caminho = relatorio.gerar_pdf_modulo(
            chave_modulo, titulo, _metadados_laudo(voo, midias),
            resumo, ocorrencias, imagens=imagens)
        if caminho:
            _registrar_auditoria(
                ator, "gerar_laudo_modulo_pdf",
                f"{chave_modulo}: voo #{voo_id}, {len(ocorrencias or [])} "
                f"ocorrência(s)")
        return caminho
    except Exception as exc:
        _log().exception(
            f"gerar_laudo_modulo_pdf({chave_modulo},{voo_id}): {exc}")
        return None


def processar_multiespectral(voo_id, ator=""):
    """Roda o processamento multiespectral nas bandas do voo.

    Espera arquivos nomeados com sufixo de banda (`talhao_R.png`,
    `talhao_NIR.png`, ...). Grava JSON e GeoTIFF em
    `midia/<voo_id>/indices/` e audita a execução.
    """
    try:
        from mod_tisosdocfly import multiespectral
        pasta = diretorio_midia(int(voo_id))
        saida = os.path.join(pasta, "indices")
        resumo = multiespectral.processar_diretorio(pasta, saida=saida)
        grupos = len(resumo or {})
        _registrar_auditoria(
            ator, "processar_multiespectral",
            f"voo #{voo_id}: {grupos} grupo(s) de bandas")
        return resumo or {}
    except Exception as exc:
        _log().exception(
            f"processar_multiespectral({voo_id}): {exc}")
        return {}


def diretorio_laudos():
    """Returns the report directory used by the PDF pipeline."""
    try:
        from mod_tisosdocfly.relatorio import diretorio_laudos as _dir
        return _dir()
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "laudos")


def _metadados_laudo(voo, midias):
    """Builds the metadata table for the PDF report."""
    try:
        gsd = voo.get("gsd_cm")
        gsd_txt = f"{gsd} cm/px" if gsd not in (None, "", 0) else "-"
        fotos = sum(1 for m in midias if _mime_imagem(m))
        videos = len(midias) - fotos
        return {
            "Voo": f"#{voo.get('id')}",
            "Cliente": voo.get("cliente_nome") or "-",
            "Propriedade": voo.get("propriedade_nome") or "-",
            "Data do voo": voo.get("data_voo") or "-",
            "Piloto": voo.get("piloto") or "-",
            "Drone": voo.get("drone") or "Não informado",
            "GSD": gsd_txt,
            "Mídias": f"{len(midias)} (fotos: {fotos}, vídeos: {videos})",
        }
    except Exception:
        return {}


def criar_laudo_base(voo_id, titulo="", ator=""):
    """Creates the report record and its PDF, returning the report id.

    Registra o laudo em `tb_laudos`, gera o PDF em `laudos/tisosdocfly/` com as
    ocorrências das análises de IA já executadas, marca o voo e audita. Falha
    de PDF não impede o registro do laudo (fail-soft).
    """
    try:
        voo = obter_voo(voo_id)
        if not voo:
            return None
        if not _pronto():
            return None
        midias = listar_midias_do_voo(voo_id)
        titulo_final = (titulo or "").strip() or (
            f"Laudo — Voo #{voo_id} — "
            f"{voo.get('propriedade_nome') or voo.get('cliente_nome') or '-'}")
        analises = listar_analises_ia(voo_id)
        ocorrencias = ocorrencias_das_analises(voo_id)
        resumo = _resumo_laudo_base(voo, midias)
        if analises:
            resumo += (f"\n\nAnálises de imagem: {len(analises)} análise(s), "
                       f"{len(ocorrencias)} ocorrência(s) automática(s). "
                       "Revisão humana obrigatória antes de uso externo.")
        else:
            resumo += ("\n\nNenhuma análise de imagem registrada. "
                       "Execute 'Analisar mídias' antes de gerar o laudo "
                       "para incluir as ocorrências automáticas.")
        novo_id = _crud().criar(
            "INSERT INTO tb_laudos (voo_id, cliente_id, titulo, status, "
            "resumo) VALUES (?, ?, ?, 'base', ?)",
            (voo_id, voo.get("cliente_id"), titulo_final, resumo))

        # PDF (fail-soft: o laudo textual continua existindo sem ele).
        try:
            from mod_tisosdocfly import relatorio
            imagens = [m.get("caminho") for m in midias
                       if _mime_imagem(m)][:6]
            caminho = relatorio.gerar_pdf_modulo(
                "tisosdocfly", titulo_final, _metadados_laudo(voo, midias),
                resumo, ocorrencias, imagens=imagens)
            if caminho:
                _crud().atualizar(
                    "UPDATE tb_laudos SET caminho_pdf=? WHERE id=?",
                    (caminho, novo_id))
        except Exception as exc:
            _log().exception(
                f"criar_laudo_base: PDF do laudo #{novo_id}: {exc}")

        _crud().atualizar("UPDATE tb_voos SET status='laudo_gerado' "
                          "WHERE id=?", (voo_id,))
        _registrar_auditoria(
            ator, "criar_laudo_base",
            f"laudo #{novo_id} do voo #{voo_id} "
            f"({len(midias)} mídia(s), {len(ocorrencias)} ocorrência(s))")
        return novo_id
    except Exception as exc:
        _log().exception(f"voos.criar_laudo_base({voo_id}): {exc}")
        return None


def listar_laudos(voo_id=None):
    """Lists reports (all or by flight), newest first."""
    try:
        if not _pronto():
            return []
        sql = ("SELECT l.id, l.voo_id, l.cliente_id, l.titulo, l.status, "
               "l.resumo, l.gerado_em, l.caminho_pdf, "
               "c.nome AS cliente_nome, "
               "p.nome AS propriedade_nome "
               "FROM tb_laudos l "
               "LEFT JOIN tb_clientes c ON c.id=l.cliente_id "
               "LEFT JOIN tb_voos v ON v.id=l.voo_id "
               "LEFT JOIN tb_propriedades p ON p.id=v.propriedade_id")
        params = ()
        if voo_id is not None:
            sql += " WHERE l.voo_id=?"
            params = (voo_id,)
        sql += " ORDER BY l.id DESC"
        colunas = _COLUNAS_LAUDO + ("cliente_nome", "propriedade_nome")
        return _dictificar(_crud().listar(sql, params), colunas)
    except Exception as exc:
        _log().exception(f"voos.listar_laudos({voo_id}): {exc}")
        return []
