"""Mapeamento — único ponto de acesso ao banco (db_mod_mapeamento.db).

EN: Mapping module data access: analyses and geospatial products. Own database
only; no cross-query. Schema is portable SQL (SQLite and PostgreSQL via
`mod_skyrover.banco_conexao`).

PT-BR: Acesso a dados do módulo Mapeamento: análises e produtos geoespaciais.
Banco próprio, sem cross-query. O schema é SQL portável (SQLite e PostgreSQL
via `mod_skyrover.banco_conexao`).

Tabelas:
    tb_mapeamento_analise  análise de um voo (área, GSD, tipo, status)
    tb_mapeamento_produto  produto gerado (nome, tipo, caminho, hash)
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CHAVE_MODULO = "mapeamento"
NOME_MODULO = "Mapeamento"

STATUS = ("rascunho", "em_revisao", "concluido")
TIPOS = ("ortomosaico", "topografia", "volumetria", "outro")
TIPOS_PRODUTO = ("geotiff", "cog", "geojson", "pdf", "outro")


def _log():
    from mod_skyrover import observabilidade
    return observabilidade.get_logger(CHAVE_MODULO)


def get_connection():
    """Conexão do banco do módulo no backend ativo (None em falha)."""
    try:
        from mod_skyrover.banco_conexao import conexao
        return conexao(CHAVE_MODULO)
    except Exception as e:
        try:
            _log().exception(f"get_connection: falha | {e}")
        except Exception:
            pass
        return None


def _agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    """Cria o schema do módulo (idempotente, SQL portável)."""
    conn = get_connection()
    if conn is None:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS tb_mapeamento_analise ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "voo_id INTEGER NOT NULL, "
            "cliente_id INTEGER, "
            "propriedade_id INTEGER, "
            "area_ha REAL DEFAULT 0, "
            "gsd_cm REAL DEFAULT 0, "
            "tipo TEXT DEFAULT 'outro', "
            "status TEXT NOT NULL DEFAULT 'rascunho', "
            "resumo TEXT DEFAULT '', "
            "criado_por TEXT DEFAULT '', "
            "criado_em TEXT DEFAULT '')")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS tb_mapeamento_produto ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "analise_id INTEGER NOT NULL, "
            "nome TEXT DEFAULT '', "
            "tipo TEXT DEFAULT 'outro', "
            "caminho TEXT DEFAULT '', "
            "hash_sha256 TEXT DEFAULT '', "
            "confianca REAL DEFAULT 0, "
            "criado_em TEXT DEFAULT '')")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_mapeamento_analise_voo "
            "ON tb_mapeamento_analise (voo_id)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_mapeamento_produto_analise "
            "ON tb_mapeamento_produto (analise_id)")
        conn.commit()
        return True
    except Exception as e:
        try:
            _log().exception(f"init_db: falha | {e}")
        except Exception:
            pass
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _audit(ator, acao, alvo, detalhe=""):
    try:
        from mod_skyrover.bd_manipulador import audit_log
        audit_log(ator or "sistema", CHAVE_MODULO, acao, detalhe or str(alvo))
    except Exception:
        pass


def _resumo_vazio():
    return {"total": 0, "rascunho": 0, "em_revisao": 0, "concluido": 0,
            "produtos": 0}


def criar_analise(ator, voo_id, area_ha=0, gsd_cm=0, tipo="ortomosaico",
                  resumo=""):
    """Cria uma análise de mapeamento de um voo e devolve (ok, id_ou_msg)."""
    try:
        if not voo_id:
            return False, "Selecione um voo"
        if tipo not in TIPOS:
            return False, "Tipo de análise inválido"
        voo = None
        try:
            from mod_skyrover import voos
            voo = voos.obter_voo(int(voo_id))
        except Exception:
            voo = None
        if not voo:
            return False, "Voo não encontrado"
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tb_mapeamento_analise "
                "(voo_id, cliente_id, propriedade_id, area_ha, gsd_cm, tipo, "
                "status, resumo, criado_por, criado_em) "
                "VALUES (?, ?, ?, ?, ?, ?, 'rascunho', ?, ?, ?)",
                (int(voo_id), voo.get("cliente_id"),
                 voo.get("propriedade_id"), float(area_ha or 0),
                 float(gsd_cm or 0), tipo, resumo or "", ator or "", _agora()))
            conn.commit()
            novo_id = getattr(cur, "lastrowid", None)
            _audit(ator, "criar_analise", novo_id,
                   f"voo={voo_id} tipo={tipo}")
            return True, novo_id
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"criar_analise: falha | {e}")
        except Exception:
            pass
        return False, "Erro ao criar análise"


def listar_analises(busca=""):
    """Lista análises (mais novas primeiro), com filtro textual opcional."""
    try:
        if not init_db():
            return []
        conn = get_connection()
        if conn is None:
            return []
        try:
            termo = (busca or "").strip()
            sql = ("SELECT id, voo_id, cliente_id, propriedade_id, area_ha, "
                   "gsd_cm, tipo, status, resumo, criado_por, criado_em "
                   "FROM tb_mapeamento_analise")
            params = ()
            if termo:
                sql += (" WHERE tipo LIKE ? OR status LIKE ? OR resumo LIKE ?")
                like = f"%{termo}%"
                params = (like, like, like)
            sql += " ORDER BY id DESC"
            cur = conn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"listar_analises: falha | {e}")
        except Exception:
            pass
        return []


def obter_analise(analise_id):
    """Devolve uma análise pelo id (ou None)."""
    try:
        conn = get_connection()
        if conn is None:
            return None
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, voo_id, cliente_id, propriedade_id, area_ha, "
                "gsd_cm, tipo, status, resumo, criado_por, criado_em "
                "FROM tb_mapeamento_analise WHERE id=?",
                (int(analise_id),))
            return cur.fetchone()
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"obter_analise: falha | {e}")
        except Exception:
            pass
        return None


def atualizar_status(analise_id, status, resumo=None):
    """Muda o status e, quando informado, o texto do resumo."""
    try:
        if status not in STATUS:
            return False, "Status inválido"
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            cur = conn.cursor()
            if resumo is None:
                cur.execute(
                    "UPDATE tb_mapeamento_analise SET status=? WHERE id=?",
                    (status, int(analise_id)))
            else:
                cur.execute(
                    "UPDATE tb_mapeamento_analise SET status=?, resumo=? "
                    "WHERE id=?", (status, resumo, int(analise_id)))
            conn.commit()
            _audit("sistema", "atualizar_status", analise_id, status)
            return True, "Status atualizado"
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"atualizar_status: falha | {e}")
        except Exception:
            pass
        return False, "Erro ao atualizar status"


def adicionar_produto(ator, analise_id, nome, tipo="outro", caminho="",
                      hash_sha256="", confianca=0):
    """Registra um produto geoespacial de uma análise."""
    try:
        if tipo not in TIPOS_PRODUTO:
            return False, "Tipo de produto inválido"
        if not (nome or "").strip():
            return False, "Informe o nome do produto"
        if not obter_analise(analise_id):
            return False, "Análise não encontrada"
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tb_mapeamento_produto "
                "(analise_id, nome, tipo, caminho, hash_sha256, confianca, "
                "criado_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (int(analise_id), nome.strip(), tipo, caminho or "",
                 hash_sha256 or "", float(confianca or 0), _agora()))
            conn.commit()
            novo_id = getattr(cur, "lastrowid", None)
            _audit(ator, "adicionar_produto", novo_id,
                   f"analise={analise_id} produto={nome} tipo={tipo}")
            return True, novo_id
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"adicionar_produto: falha | {e}")
        except Exception:
            pass
        return False, "Erro ao registrar produto"


def listar_produtos(analise_id):
    """Lista os produtos de uma análise (ordem de cadastro)."""
    try:
        conn = get_connection()
        if conn is None:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, analise_id, nome, tipo, caminho, hash_sha256, "
                "confianca, criado_em FROM tb_mapeamento_produto "
                "WHERE analise_id=? ORDER BY id", (int(analise_id),))
            return cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"listar_produtos: falha | {e}")
        except Exception:
            pass
        return []


def resumo():
    """Contagens para o painel: total, por status e produtos."""
    try:
        if not init_db():
            return _resumo_vazio()
        conn = get_connection()
        if conn is None:
            return _resumo_vazio()
        try:
            cur = conn.cursor()
            cur.execute("SELECT status, COUNT(*) FROM tb_mapeamento_analise "
                        "GROUP BY status")
            por_status = {s: int(n) for s, n in cur.fetchall()}
            cur.execute("SELECT COUNT(*) FROM tb_mapeamento_produto")
            produtos = int(cur.fetchone()[0] or 0)
            return {"total": sum(por_status.values()),
                    "rascunho": por_status.get("rascunho", 0),
                    "em_revisao": por_status.get("em_revisao", 0),
                    "concluido": por_status.get("concluido", 0),
                    "produtos": produtos}
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"resumo: falha | {e}")
        except Exception:
            pass
        return _resumo_vazio()
