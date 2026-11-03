"""Vistoria Predial — único ponto de acesso ao banco (db_mod_vistoria_predial.db).

EN: Building inspection data access: inspections and pathologies. Own database
only; no cross-query. Portable SQL (SQLite/PostgreSQL via banco_conexao).

PT-BR: Acesso a dados da Vistoria Predial: vistorias e patologias. Banco
próprio, sem cross-query. SQL portável (SQLite/PostgreSQL via banco_conexao).

Tabelas:
    tb_vistoria            vistoria de um voo (imóvel, tipo, status, resumo)
    tb_vistoria_patologia  achado da vistoria (tipo, severidade, área)
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CHAVE_MODULO = "vistoria_predial"
NOME_MODULO = "Vistoria Predial"

STATUS = ("rascunho", "em_revisao", "concluido")
TIPOS = ("fachada", "telhado", "estrutural", "completa")
PATOLOGIAS = ("trinca", "infiltracao", "mancha", "vegetacao", "corrosao",
              "desplacamento", "outro")
SEVERIDADES = ("baixa", "media", "alta", "critica")


def _log():
    from mod_tisosdocfly import observabilidade
    return observabilidade.get_logger(CHAVE_MODULO)


def get_connection():
    try:
        from mod_tisosdocfly.banco_conexao import conexao
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
    conn = get_connection()
    if conn is None:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS tb_vistoria ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "voo_id INTEGER NOT NULL, "
            "cliente_id INTEGER, "
            "propriedade_id INTEGER, "
            "imovel TEXT DEFAULT '', "
            "tipo TEXT DEFAULT 'completa', "
            "status TEXT NOT NULL DEFAULT 'rascunho', "
            "resumo TEXT DEFAULT '', "
            "criado_por TEXT DEFAULT '', "
            "criado_em TEXT DEFAULT '')")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS tb_vistoria_patologia ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "vistoria_id INTEGER NOT NULL, "
            "tipo TEXT DEFAULT '', "
            "severidade TEXT DEFAULT 'baixa', "
            "area_m2 REAL DEFAULT 0, "
            "descricao TEXT DEFAULT '', "
            "revisao_humana INTEGER NOT NULL DEFAULT 0, "
            "criado_em TEXT DEFAULT '')")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_vistoria_voo "
            "ON tb_vistoria (voo_id)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_vistoria_patologia_vistoria "
            "ON tb_vistoria_patologia (vistoria_id)")
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
        from mod_tisosdocfly.bd_manipulador import audit_log
        audit_log(ator or "sistema", CHAVE_MODULO, acao, detalhe or str(alvo))
    except Exception:
        pass


def criar_vistoria(ator, voo_id, imovel="", tipo="completa", resumo=""):
    try:
        if not voo_id:
            return False, "Selecione um voo"
        if tipo not in TIPOS:
            return False, "Tipo inválido"
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            voo = None
            try:
                from mod_tisosdocfly import voos
                voo = voos.obter_voo(int(voo_id))
            except Exception:
                voo = None
            cliente_id = voo.get("cliente_id") if voo else None
            propriedade_id = voo.get("propriedade_id") if voo else None
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tb_vistoria "
                "(voo_id, cliente_id, propriedade_id, imovel, tipo, status, "
                "resumo, criado_por, criado_em) "
                "VALUES (?, ?, ?, ?, ?, 'rascunho', ?, ?, ?)",
                (int(voo_id), cliente_id, propriedade_id, imovel or "",
                 tipo, resumo or "", ator or "", _agora()))
            conn.commit()
            novo_id = getattr(cur, "lastrowid", None)
            _audit(ator, "criar_vistoria", novo_id,
                   f"voo={voo_id} imovel={imovel} tipo={tipo}")
            return True, novo_id
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"criar_vistoria: falha | {e}")
        except Exception:
            pass
        return False, "Erro ao criar vistoria"


def listar_vistorias(busca=""):
    try:
        if not init_db():
            return []
        conn = get_connection()
        if conn is None:
            return []
        try:
            termo = (busca or "").strip()
            sql = ("SELECT id, voo_id, cliente_id, propriedade_id, imovel, "
                   "tipo, status, resumo, criado_por, criado_em "
                   "FROM tb_vistoria")
            params = ()
            if termo:
                sql += (" WHERE imovel LIKE ? OR tipo LIKE ? OR "
                        "status LIKE ?")
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
            _log().exception(f"listar_vistorias: falha | {e}")
        except Exception:
            pass
        return []


def obter_vistoria(vistoria_id):
    try:
        conn = get_connection()
        if conn is None:
            return None
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, voo_id, cliente_id, propriedade_id, imovel, "
                "tipo, status, resumo, criado_por, criado_em "
                "FROM tb_vistoria WHERE id=?", (int(vistoria_id),))
            return cur.fetchone()
        finally:
            conn.close()
    except Exception:
        return None


def atualizar_status(vistoria_id, status, resumo=None):
    try:
        if status not in STATUS:
            return False, "Status inválido"
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            if resumo is None:
                conn.execute(
                    "UPDATE tb_vistoria SET status=? WHERE id=?",
                    (status, int(vistoria_id)))
            else:
                conn.execute(
                    "UPDATE tb_vistoria SET status=?, resumo=? WHERE id=?",
                    (status, resumo, int(vistoria_id)))
            conn.commit()
            _audit("sistema", "atualizar_status", vistoria_id, status)
            return True, "Status atualizado"
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"atualizar_status: falha | {e}")
        except Exception:
            pass
        return False, "Erro ao atualizar status"


def adicionar_patologia(ator, vistoria_id, tipo, severidade="baixa",
                        area_m2=0, descricao="", revisao_humana=0):
    try:
        if tipo not in PATOLOGIAS:
            return False, "Patologia inválida"
        if severidade not in SEVERIDADES:
            return False, "Severidade inválida"
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tb_vistoria_patologia "
                "(vistoria_id, tipo, severidade, area_m2, descricao, "
                "revisao_humana, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (int(vistoria_id), tipo, severidade, float(area_m2 or 0),
                 descricao or "", 1 if revisao_humana else 0, _agora()))
            conn.commit()
            novo_id = getattr(cur, "lastrowid", None)
            _audit(ator, "adicionar_patologia", novo_id,
                   f"vistoria={vistoria_id} tipo={tipo}")
            return True, novo_id
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"adicionar_patologia: falha | {e}")
        except Exception:
            pass
        return False, "Erro ao registrar patologia"


def listar_patologias(vistoria_id):
    try:
        conn = get_connection()
        if conn is None:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, vistoria_id, tipo, severidade, area_m2, "
                "descricao, revisao_humana, criado_em "
                "FROM tb_vistoria_patologia WHERE vistoria_id=? ORDER BY id",
                (int(vistoria_id),))
            return cur.fetchall()
        finally:
            conn.close()
    except Exception:
        return []


def marcar_revisao(patologia_id, revisada=True):
    try:
        conn = get_connection()
        if conn is None:
            return False
        try:
            conn.execute(
                "UPDATE tb_vistoria_patologia SET revisao_humana=? "
                "WHERE id=?", (1 if revisada else 0, int(patologia_id)))
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


def resumo():
    vazio = {"total": 0, "rascunho": 0, "em_revisao": 0, "concluido": 0,
             "patologias": 0}
    try:
        if not init_db():
            return vazio
        conn = get_connection()
        if conn is None:
            return vazio
        try:
            cur = conn.cursor()
            cur.execute("SELECT status, COUNT(*) FROM tb_vistoria "
                        "GROUP BY status")
            por_status = {s: int(n) for s, n in cur.fetchall()}
            cur.execute("SELECT COUNT(*) FROM tb_vistoria_patologia")
            patologias = int(cur.fetchone()[0] or 0)
            return {"total": sum(por_status.values()),
                    "rascunho": por_status.get("rascunho", 0),
                    "em_revisao": por_status.get("em_revisao", 0),
                    "concluido": por_status.get("concluido", 0),
                    "patologias": patologias}
        finally:
            conn.close()
    except Exception:
        return vazio
