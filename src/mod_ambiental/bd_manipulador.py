"""Ambiental — único ponto de acesso ao banco do módulo (db_mod_ambiental.db).

EN: Environmental module data access: analyses and occurrences. Own database
only; no cross-query. Schema is portable SQL (SQLite and PostgreSQL via
`mod_skyrover.banco_conexao`).

PT-BR: Acesso a dados do módulo Ambiental: análises e ocorrências. Banco
próprio, sem cross-query. O schema é SQL portável (SQLite e PostgreSQL via
`mod_skyrover.banco_conexao`).

Tabelas:
    tb_ambiental_analise     análise de um voo (área, tipo, status, resumo)
    tb_ambiental_ocorrencia  achado da análise (classe, severidade, evidência)
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CHAVE_MODULO = "ambiental"
NOME_MODULO = "Ambiental"

STATUS = ("rascunho", "em_revisao", "concluido")
TIPOS = ("desmatamento", "app", "queimada", "recuperacao", "outro")
CLASSES = ("desmatamento", "queimada", "app", "erosao", "outro")
SEVERIDADES = ("baixa", "media", "alta", "critica")


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
            "CREATE TABLE IF NOT EXISTS tb_ambiental_analise ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "voo_id INTEGER NOT NULL, "
            "cliente_id INTEGER, "
            "propriedade_id INTEGER, "
            "area REAL DEFAULT 0, "
            "tipo TEXT DEFAULT 'outro', "
            "status TEXT NOT NULL DEFAULT 'rascunho', "
            "resumo TEXT DEFAULT '', "
            "criado_por TEXT DEFAULT '', "
            "criado_em TEXT DEFAULT '')")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS tb_ambiental_ocorrencia ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "analise_id INTEGER NOT NULL, "
            "classe TEXT DEFAULT '', "
            "severidade TEXT DEFAULT 'baixa', "
            "area_m2 REAL DEFAULT 0, "
            "confianca REAL DEFAULT 0, "
            "revisao_humana INTEGER NOT NULL DEFAULT 0, "
            "evidencia TEXT DEFAULT '', "
            "criado_em TEXT DEFAULT '')")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_ambiental_analise_voo "
            "ON tb_ambiental_analise (voo_id)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_ambiental_ocorrencia_analise "
            "ON tb_ambiental_ocorrencia (analise_id)")
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
            "ocorrencias": 0, "pendentes_revisao": 0}


def criar_analise(ator, voo_id, area=0, tipo="outro", resumo=""):
    """Cria uma análise ambiental de um voo e devolve (ok, id_ou_msg)."""
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
                "INSERT INTO tb_ambiental_analise "
                "(voo_id, cliente_id, propriedade_id, area, tipo, status, "
                "resumo, criado_por, criado_em) "
                "VALUES (?, ?, ?, ?, ?, 'rascunho', ?, ?, ?)",
                (int(voo_id), voo.get("cliente_id"),
                 voo.get("propriedade_id"), float(area or 0), tipo,
                 resumo or "", ator or "", _agora()))
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
            sql = ("SELECT id, voo_id, cliente_id, propriedade_id, area, "
                   "tipo, status, resumo, criado_por, criado_em "
                   "FROM tb_ambiental_analise")
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
                "SELECT id, voo_id, cliente_id, propriedade_id, area, tipo, "
                "status, resumo, criado_por, criado_em "
                "FROM tb_ambiental_analise WHERE id=?",
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
                    "UPDATE tb_ambiental_analise SET status=? WHERE id=?",
                    (status, int(analise_id)))
            else:
                cur.execute(
                    "UPDATE tb_ambiental_analise SET status=?, resumo=? "
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


def adicionar_ocorrencia(ator, analise_id, classe, severidade="baixa",
                         area_m2=0, confianca=0, revisao_humana=0,
                         evidencia=""):
    """Registra um achado da análise (triagem; revisão humana é explícita)."""
    try:
        if classe not in CLASSES:
            return False, "Classe inválida"
        if severidade not in SEVERIDADES:
            return False, "Severidade inválida"
        if not obter_analise(analise_id):
            return False, "Análise não encontrada"
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tb_ambiental_ocorrencia "
                "(analise_id, classe, severidade, area_m2, confianca, "
                "revisao_humana, evidencia, criado_em) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (int(analise_id), classe, severidade, float(area_m2 or 0),
                 float(confianca or 0), 1 if revisao_humana else 0,
                 evidencia or "", _agora()))
            conn.commit()
            novo_id = getattr(cur, "lastrowid", None)
            _audit(ator, "adicionar_ocorrencia", novo_id,
                   f"analise={analise_id} classe={classe}")
            return True, novo_id
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"adicionar_ocorrencia: falha | {e}")
        except Exception:
            pass
        return False, "Erro ao registrar ocorrência"


def listar_ocorrencias(analise_id):
    """Lista as ocorrências de uma análise (ordem de cadastro)."""
    try:
        conn = get_connection()
        if conn is None:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, analise_id, classe, severidade, area_m2, "
                "confianca, revisao_humana, evidencia, criado_em "
                "FROM tb_ambiental_ocorrencia WHERE analise_id=? ORDER BY id",
                (int(analise_id),))
            return cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"listar_ocorrencias: falha | {e}")
        except Exception:
            pass
        return []


def marcar_revisao(ocorrencia_id, revisada=True):
    """Marca (ou desmarca) a revisão humana de uma ocorrência."""
    try:
        conn = get_connection()
        if conn is None:
            return False
        try:
            conn.execute(
                "UPDATE tb_ambiental_ocorrencia SET revisao_humana=? "
                "WHERE id=?", (1 if revisada else 0, int(ocorrencia_id)))
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"marcar_revisao: falha | {e}")
        except Exception:
            pass
        return False


def resumo():
    """Contagens para o painel: total, por status, ocorrências e pendências."""
    try:
        if not init_db():
            return _resumo_vazio()
        conn = get_connection()
        if conn is None:
            return _resumo_vazio()
        try:
            cur = conn.cursor()
            cur.execute("SELECT status, COUNT(*) FROM tb_ambiental_analise "
                        "GROUP BY status")
            por_status = {s: int(n) for s, n in cur.fetchall()}
            cur.execute("SELECT COUNT(*) FROM tb_ambiental_ocorrencia")
            ocorrencias = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT COUNT(*) FROM tb_ambiental_ocorrencia "
                "WHERE revisao_humana=0")
            pendentes = int(cur.fetchone()[0] or 0)
            return {"total": sum(por_status.values()),
                    "rascunho": por_status.get("rascunho", 0),
                    "em_revisao": por_status.get("em_revisao", 0),
                    "concluido": por_status.get("concluido", 0),
                    "ocorrencias": ocorrencias,
                    "pendentes_revisao": pendentes}
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"resumo: falha | {e}")
        except Exception:
            pass
        return _resumo_vazio()
