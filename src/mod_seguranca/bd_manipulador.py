"""Segurança Pública — único ponto de acesso ao banco (db_mod_seguranca.db).

EN: Public safety data access: triage analyses and occurrences. Own database
only; no cross-query. Every occurrence is a TRIAGE result and carries an
explicit human-review flag. No automated guilt decision.

PT-BR: Acesso a dados de Segurança Pública: análises de triagem e ocorrências.
Banco próprio, sem cross-query. Toda ocorrência é TRIAGEM e carrega a marca
explícita de revisão humana; o sistema não decide culpa automaticamente.

Tabelas:
    tb_seguranca_analise     análise de um voo (tipo, risco, status, resumo)
    tb_seguranca_ocorrencia  achado da triagem (classe, quantidade, confiança)
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CHAVE_MODULO = "seguranca"
NOME_MODULO = "Segurança Pública"

STATUS = ("rascunho", "em_revisao", "concluido")
TIPOS = ("aglomeracao", "pessoas", "veiculos", "placas", "objetos_risco",
         "multipla")
NIVEIS_RISCO = ("baixo", "medio", "alto", "critico")
CLASSES = ("pessoa", "aglomeracao", "veiculo", "placa", "arma_fogo",
           "arma_branca", "crianca_risco", "outro")


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
            "CREATE TABLE IF NOT EXISTS tb_seguranca_analise ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "voo_id INTEGER NOT NULL, "
            "cliente_id INTEGER, "
            "propriedade_id INTEGER, "
            "tipo TEXT DEFAULT 'multipla', "
            "nivel_risco TEXT DEFAULT 'baixo', "
            "status TEXT NOT NULL DEFAULT 'rascunho', "
            "resumo TEXT DEFAULT '', "
            "criado_por TEXT DEFAULT '', "
            "criado_em TEXT DEFAULT '')")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS tb_seguranca_ocorrencia ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "analise_id INTEGER NOT NULL, "
            "classe TEXT DEFAULT '', "
            "quantidade INTEGER DEFAULT 0, "
            "confianca REAL DEFAULT 0, "
            "revisao_humana INTEGER NOT NULL DEFAULT 0, "
            "evidencia TEXT DEFAULT '', "
            "criado_em TEXT DEFAULT '')")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_seguranca_analise_voo "
            "ON tb_seguranca_analise (voo_id)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_seguranca_ocorrencia_analise "
            "ON tb_seguranca_ocorrencia (analise_id)")
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


def criar_analise(ator, voo_id, tipo="multipla", nivel_risco="baixo",
                  resumo=""):
    try:
        if not voo_id:
            return False, "Selecione um voo"
        if tipo not in TIPOS:
            return False, "Tipo inválido"
        if nivel_risco not in NIVEIS_RISCO:
            return False, "Nível de risco inválido"
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
                "INSERT INTO tb_seguranca_analise "
                "(voo_id, cliente_id, propriedade_id, tipo, nivel_risco, "
                "status, resumo, criado_por, criado_em) "
                "VALUES (?, ?, ?, ?, ?, 'rascunho', ?, ?, ?)",
                (int(voo_id), cliente_id, propriedade_id, tipo, nivel_risco,
                 resumo or "", ator or "", _agora()))
            conn.commit()
            novo_id = getattr(cur, "lastrowid", None)
            _audit(ator, "criar_analise", novo_id,
                   f"voo={voo_id} tipo={tipo} risco={nivel_risco}")
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
    try:
        if not init_db():
            return []
        conn = get_connection()
        if conn is None:
            return []
        try:
            termo = (busca or "").strip()
            sql = ("SELECT id, voo_id, cliente_id, propriedade_id, tipo, "
                   "nivel_risco, status, resumo, criado_por, criado_em "
                   "FROM tb_seguranca_analise")
            params = ()
            if termo:
                sql += (" WHERE tipo LIKE ? OR nivel_risco LIKE ? OR "
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
            _log().exception(f"listar_analises: falha | {e}")
        except Exception:
            pass
        return []


def obter_analise(analise_id):
    try:
        conn = get_connection()
        if conn is None:
            return None
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, voo_id, cliente_id, propriedade_id, tipo, "
                "nivel_risco, status, resumo, criado_por, criado_em "
                "FROM tb_seguranca_analise WHERE id=?", (int(analise_id),))
            return cur.fetchone()
        finally:
            conn.close()
    except Exception:
        return None


def atualizar_status(analise_id, status, resumo=None):
    try:
        if status not in STATUS:
            return False, "Status inválido"
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            if resumo is None:
                conn.execute(
                    "UPDATE tb_seguranca_analise SET status=? WHERE id=?",
                    (status, int(analise_id)))
            else:
                conn.execute(
                    "UPDATE tb_seguranca_analise SET status=?, resumo=? "
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


def adicionar_ocorrencia(ator, analise_id, classe, quantidade=0,
                         confianca=0, revisao_humana=0, evidencia=""):
    """Registra uma TRIAGEM. Não é acusação; revisão humana é obrigatória."""
    try:
        if classe not in CLASSES:
            return False, "Classe inválida"
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tb_seguranca_ocorrencia "
                "(analise_id, classe, quantidade, confianca, revisao_humana, "
                "evidencia, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (int(analise_id), classe, int(quantidade or 0),
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
    try:
        conn = get_connection()
        if conn is None:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, analise_id, classe, quantidade, confianca, "
                "revisao_humana, evidencia, criado_em "
                "FROM tb_seguranca_ocorrencia WHERE analise_id=? ORDER BY id",
                (int(analise_id),))
            return cur.fetchall()
        finally:
            conn.close()
    except Exception:
        return []


def marcar_revisao(ocorrencia_id, revisada=True):
    try:
        conn = get_connection()
        if conn is None:
            return False
        try:
            conn.execute(
                "UPDATE tb_seguranca_ocorrencia SET revisao_humana=? "
                "WHERE id=?", (1 if revisada else 0, int(ocorrencia_id)))
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


def resumo():
    vazio = {"total": 0, "rascunho": 0, "em_revisao": 0, "concluido": 0,
             "ocorrencias": 0, "pendentes_revisao": 0}
    try:
        if not init_db():
            return vazio
        conn = get_connection()
        if conn is None:
            return vazio
        try:
            cur = conn.cursor()
            cur.execute("SELECT status, COUNT(*) FROM tb_seguranca_analise "
                        "GROUP BY status")
            por_status = {s: int(n) for s, n in cur.fetchall()}
            cur.execute("SELECT COUNT(*) FROM tb_seguranca_ocorrencia")
            ocorrencias = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT COUNT(*) FROM tb_seguranca_ocorrencia "
                "WHERE COALESCE(revisao_humana, 0)=0")
            pendentes = int(cur.fetchone()[0] or 0)
            return {"total": sum(por_status.values()),
                    "rascunho": por_status.get("rascunho", 0),
                    "em_revisao": por_status.get("em_revisao", 0),
                    "concluido": por_status.get("concluido", 0),
                    "ocorrencias": ocorrencias,
                    "pendentes_revisao": pendentes}
        finally:
            conn.close()
    except Exception:
        return vazio
