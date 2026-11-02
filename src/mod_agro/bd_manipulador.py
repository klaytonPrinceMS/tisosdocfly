"""Agro — único ponto de acesso ao banco do módulo (db_mod_agro.db, WAL).

EN: Agro module data access: analyses and occurrences. Own database only; no
cross-query. Schema is portable SQL (SQLite and PostgreSQL via banco_conexao).

PT-BR: Acesso a dados do módulo Agropecuário: análises e ocorrências. Banco
próprio, sem cross-query. O schema é SQL portável (SQLite e PostgreSQL via
`mod_skyrover.banco_conexao`).

Tabelas:
    tb_agro_analise     análise de um voo (talhão, cultura, índice, status)
    tb_agro_ocorrencia  achado da análise (classe, severidade, área, confiança)
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CHAVE_MODULO = "agro"
NOME_MODULO = "Agropecuário"

STATUS = ("rascunho", "processando", "concluido")
CULTURAS = ("soja", "milho", "tomate", "cafe", "banana", "maca",
            "mandioca", "uva", "frutiferas", "outra")
TIPOS_ANALISE = ("lavoura", "pastagem", "rebanho")
FINALIDADES = ("producao", "seguro_agricola", "vistoria", "pesquisa")
INDICES = ("NDVI", "NDRE", "GNDVI", "NDWI", "SAVI")
SEVERIDADES = ("baixa", "media", "alta")
# Classes de lavoura e de pecuária (Embrapa, 2024: monitoramento de gado).
CLASSES = ("estresse_metabolico", "ferrugem_asiatica", "oidio", "nematoides",
           "falha_plantio", "matocompeticao", "deficiencia_nutricional",
           "contagem_gado", "animal_isolado", "aglomeracao_animal",
           "animal_caido", "pastagem_degradada", "sombra_agua",
           "doenca_foliar", "deficit_hidrico", "excesso_umidade", "outro")


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
            "CREATE TABLE IF NOT EXISTS tb_agro_analise ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "voo_id INTEGER NOT NULL, "
            "cliente_id INTEGER, "
            "propriedade_id INTEGER, "
            "talhao TEXT DEFAULT '', "
            "cultura TEXT DEFAULT '', "
            "indice TEXT DEFAULT '', "
            "estagio TEXT DEFAULT '', "
            "area_ha REAL DEFAULT 0, "
            "resultado TEXT DEFAULT '', "
            "status TEXT NOT NULL DEFAULT 'rascunho', "
            "criado_por TEXT DEFAULT '', "
            "criado_em TEXT DEFAULT '', "
            "tipo_analise TEXT DEFAULT 'lavoura', "
            "cabecas_estimadas INTEGER DEFAULT 0, "
            "area_pastagem_ha REAL DEFAULT 0, "
            "finalidade TEXT DEFAULT 'producao', "
            "perda_estimada_pct REAL DEFAULT 0, "
            "area_afetada_ha REAL DEFAULT 0)")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS tb_agro_ocorrencia ("
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
            "CREATE INDEX IF NOT EXISTS ix_agro_analise_voo "
            "ON tb_agro_analise (voo_id)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_agro_ocorrencia_analise "
            "ON tb_agro_ocorrencia (analise_id)")
        # Migração idempotente para bancos criados antes da pecuária.
        for coluna, tipo in (
                ("tipo_analise", "TEXT DEFAULT 'lavoura'"),
                ("cabecas_estimadas", "INTEGER DEFAULT 0"),
                ("area_pastagem_ha", "REAL DEFAULT 0"),
                ("finalidade", "TEXT DEFAULT 'producao'"),
                ("perda_estimada_pct", "REAL DEFAULT 0"),
                ("area_afetada_ha", "REAL DEFAULT 0")):
            try:
                cur.execute(
                    f"ALTER TABLE tb_agro_analise ADD COLUMN {coluna} {tipo}")
            except Exception:
                pass
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


def criar_analise(ator, voo_id, talhao="", cultura="", indice="",
                  estagio="", area_ha=0, resultado="",
                  tipo_analise="lavoura", cabecas_estimadas=0,
                  area_pastagem_ha=0, finalidade="producao",
                  perda_estimada_pct=0, area_afetada_ha=0):
    """Cria uma análise de voo e devolve (ok, id_ou_msg).

    `tipo_analise` cobre lavoura, pastagem e rebanho. Em rebanho, a contagem
    é declarada/revisada; o baseline RGB não conta animais (Embrapa, 2024).
    """
    try:
        if not voo_id:
            return False, "Selecione um voo"
        if tipo_analise not in TIPOS_ANALISE:
            return False, "Tipo de análise inválido"
        if finalidade not in FINALIDADES:
            return False, "Finalidade inválida"
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            voo = None
            try:
                from mod_skyrover import voos
                voo = voos.obter_voo(int(voo_id))
            except Exception:
                voo = None
            cliente_id = voo.get("cliente_id") if voo else None
            propriedade_id = voo.get("propriedade_id") if voo else None
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tb_agro_analise "
                "(voo_id, cliente_id, propriedade_id, talhao, cultura, "
                "indice, estagio, area_ha, resultado, status, criado_por, "
                "criado_em, tipo_analise, cabecas_estimadas, "
                "area_pastagem_ha, finalidade, perda_estimada_pct, "
                "area_afetada_ha) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'rascunho', ?, ?, ?, ?, ?, "
                "?, ?, ?)",
                (int(voo_id), cliente_id, propriedade_id, talhao or "",
                 cultura or "", indice or "", estagio or "",
                 float(area_ha or 0), resultado or "", ator or "", _agora(),
                 tipo_analise, int(cabecas_estimadas or 0),
                 float(area_pastagem_ha or 0), finalidade,
                 float(perda_estimada_pct or 0),
                 float(area_afetada_ha or 0)))
            conn.commit()
            novo_id = getattr(cur, "lastrowid", None)
            _audit(ator, "criar_analise", novo_id,
                   f"voo={voo_id} talhao={talhao} cultura={cultura}")
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
            sql = ("SELECT id, voo_id, cliente_id, propriedade_id, talhao, "
                   "cultura, indice, estagio, area_ha, resultado, status, "
                   "criado_por, criado_em, tipo_analise, cabecas_estimadas, "
                   "area_pastagem_ha, finalidade, perda_estimada_pct, "
                   "area_afetada_ha FROM tb_agro_analise")
            params = ()
            if termo:
                sql += (" WHERE talhao LIKE ? OR cultura LIKE ? OR "
                        "indice LIKE ? OR status LIKE ?")
                like = f"%{termo}%"
                params = (like, like, like, like)
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
                "SELECT id, voo_id, cliente_id, propriedade_id, talhao, "
                "cultura, indice, estagio, area_ha, resultado, status, "
                "criado_por, criado_em, tipo_analise, cabecas_estimadas, "
                "area_pastagem_ha, finalidade, perda_estimada_pct, "
                "area_afetada_ha FROM tb_agro_analise WHERE id=?",
                (int(analise_id),))
            return cur.fetchone()
        finally:
            conn.close()
    except Exception:
        return None


def atualizar_status(analise_id, status, resultado=None):
    """Muda o status e, quando informado, o texto do resultado."""
    try:
        if status not in STATUS:
            return False, "Status inválido"
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            cur = conn.cursor()
            if resultado is None:
                cur.execute(
                    "UPDATE tb_agro_analise SET status=? WHERE id=?",
                    (status, int(analise_id)))
            else:
                cur.execute(
                    "UPDATE tb_agro_analise SET status=?, resultado=? "
                    "WHERE id=?", (status, resultado, int(analise_id)))
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
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tb_agro_ocorrencia "
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
    try:
        conn = get_connection()
        if conn is None:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, analise_id, classe, severidade, area_m2, "
                "confianca, revisao_humana, evidencia, criado_em "
                "FROM tb_agro_ocorrencia WHERE analise_id=? ORDER BY id",
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
                "UPDATE tb_agro_ocorrencia SET revisao_humana=? WHERE id=?",
                (1 if revisada else 0, int(ocorrencia_id)))
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


def resumo():
    """Contagens para o painel: total, por status e ocorrências."""
    try:
        if not init_db():
            return {"total": 0, "rascunho": 0, "processando": 0,
                    "concluido": 0, "ocorrencias": 0}
        conn = get_connection()
        if conn is None:
            return {"total": 0, "rascunho": 0, "processando": 0,
                    "concluido": 0, "ocorrencias": 0}
        try:
            cur = conn.cursor()
            cur.execute("SELECT status, COUNT(*) FROM tb_agro_analise "
                        "GROUP BY status")
            por_status = {s: int(n) for s, n in cur.fetchall()}
            cur.execute("SELECT COUNT(*) FROM tb_agro_ocorrencia")
            ocorrencias = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COALESCE(SUM(cabecas_estimadas), 0) "
                        "FROM tb_agro_analise WHERE tipo_analise='rebanho'")
            cabecas = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM tb_agro_analise "
                        "WHERE tipo_analise='rebanho'")
            rebanho = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT AVG(perda_estimada_pct) FROM tb_agro_analise "
                        "WHERE perda_estimada_pct > 0")
            perda_media = float(cur.fetchone()[0] or 0)
            total = sum(por_status.values())
            return {"total": total,
                    "rascunho": por_status.get("rascunho", 0),
                    "processando": por_status.get("processando", 0),
                    "concluido": por_status.get("concluido", 0),
                    "ocorrencias": ocorrencias,
                    "rebanho": rebanho,
                    "cabecas": cabecas,
                    "perda_media": perda_media}
        finally:
            conn.close()
    except Exception:
        return {"total": 0, "rascunho": 0, "processando": 0,
                "concluido": 0, "ocorrencias": 0}
