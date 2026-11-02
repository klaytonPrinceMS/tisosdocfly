"""Perímetro — único ponto de acesso ao banco do módulo (db_mod_perimetro.db).

EN: Perimeter data access: audits, findings and sanitized RF records. Own
database only; no cross-query. Schema is portable SQL (SQLite and PostgreSQL
via `mod_skyrover.banco_conexao`).

PT-BR: Acesso a dados do módulo Perímetro: auditorias, achados e registros RF
sanitizados. Banco próprio, sem cross-query. O schema é SQL portável (SQLite e
PostgreSQL via `mod_skyrover.banco_conexao`).

Tabelas:
    tb_perimetro_auditoria  auditoria de um voo (local, tipo, status, resumo)
    tb_perimetro_achado     achado físico (classe, severidade, revisão humana)
    tb_perimetro_rf         rede Wi-Fi/RF observada (BSSID só em hash SHA-256)

Regra de privacidade: o BSSID cru nunca entra nesta camada. `importar_rf`
normaliza cada registro por `mod_skyrover.rf_scan.normalizar_registro`, que
substitui o endereço MAC pelo hash SHA-256.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CHAVE_MODULO = "perimetro"
NOME_MODULO = "Perímetro"

STATUS = ("rascunho", "em_revisao", "concluido")
# Tipos de auditoria: perímetro completo, fachada, acessos, iluminação e RF.
TIPOS = ("perimetro", "fachada", "acesso", "iluminacao", "rf")
CLASSES = ("ponto_cego_camera", "vao_cerca", "iluminacao_deficiente",
           "acesso_desprotegido", "wifi_exposto", "vazamento_sinal",
           "rf_vulneravel", "outro")
SEVERIDADES = ("baixa", "media", "alta", "critica")
SEGURANCAS = ("aberta", "wep", "wpa2", "wpa3", "desconhecida")
RISCOS = ("baixo", "medio", "alto", "critico")


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
            "CREATE TABLE IF NOT EXISTS tb_perimetro_auditoria ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "voo_id INTEGER NOT NULL, "
            "cliente_id INTEGER, "
            "propriedade_id INTEGER, "
            "local TEXT DEFAULT '', "
            "tipo TEXT NOT NULL DEFAULT 'perimetro', "
            "status TEXT NOT NULL DEFAULT 'rascunho', "
            "resumo TEXT DEFAULT '', "
            "criado_por TEXT DEFAULT '', "
            "criado_em TEXT DEFAULT '')")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS tb_perimetro_achado ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "auditoria_id INTEGER NOT NULL, "
            "classe TEXT DEFAULT '', "
            "severidade TEXT DEFAULT 'baixa', "
            "confianca REAL DEFAULT 0, "
            "revisao_humana INTEGER NOT NULL DEFAULT 0, "
            "evidencia TEXT DEFAULT '', "
            "latitude REAL, "
            "longitude REAL, "
            "criado_em TEXT DEFAULT '')")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS tb_perimetro_rf ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "auditoria_id INTEGER NOT NULL, "
            "ssid TEXT DEFAULT '', "
            "bssid_hash TEXT DEFAULT '', "
            "banda TEXT DEFAULT '', "
            "canal INTEGER DEFAULT 0, "
            "rssi REAL DEFAULT 0, "
            "seguranca TEXT DEFAULT 'desconhecida', "
            "fora_perimetro INTEGER NOT NULL DEFAULT 0, "
            "risco TEXT DEFAULT 'baixo', "
            "evidencia TEXT DEFAULT '', "
            "criado_em TEXT DEFAULT '')")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_perimetro_auditoria_voo "
            "ON tb_perimetro_auditoria (voo_id)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_perimetro_achado_auditoria "
            "ON tb_perimetro_achado (auditoria_id)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_perimetro_rf_auditoria "
            "ON tb_perimetro_rf (auditoria_id)")
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


def criar_auditoria(ator, voo_id, local="", tipo="perimetro", resumo=""):
    """Cria uma auditoria de perímetro e devolve (ok, id_ou_msg).

    O `voo_id` é obrigatório. Cliente/propriedade são lidos da API pública de
    voos apenas como IDs de referência (sem copiar nome/documento).
    """
    try:
        if not voo_id:
            return False, "Selecione um voo"
        if tipo not in TIPOS:
            return False, "Tipo de auditoria inválido"
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
                "INSERT INTO tb_perimetro_auditoria "
                "(voo_id, cliente_id, propriedade_id, local, tipo, status, "
                "resumo, criado_por, criado_em) "
                "VALUES (?, ?, ?, ?, ?, 'rascunho', ?, ?, ?)",
                (int(voo_id), cliente_id, propriedade_id, local or "", tipo,
                 resumo or "", ator or "", _agora()))
            conn.commit()
            novo_id = getattr(cur, "lastrowid", None)
            _audit(ator, "criar_auditoria", novo_id,
                   f"voo={voo_id} local={local} tipo={tipo}")
            return True, novo_id
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"criar_auditoria: falha | {e}")
        except Exception:
            pass
        return False, "Erro ao criar auditoria"


def listar_auditorias(busca=""):
    """Lista auditorias (mais novas primeiro), com filtro textual opcional."""
    try:
        if not init_db():
            return []
        conn = get_connection()
        if conn is None:
            return []
        try:
            termo = (busca or "").strip()
            sql = ("SELECT id, voo_id, cliente_id, propriedade_id, local, "
                   "tipo, status, resumo, criado_por, criado_em "
                   "FROM tb_perimetro_auditoria")
            params = ()
            if termo:
                sql += (" WHERE local LIKE ? OR tipo LIKE ? OR status LIKE ? "
                        "OR resumo LIKE ?")
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
            _log().exception(f"listar_auditorias: falha | {e}")
        except Exception:
            pass
        return []


def obter_auditoria(auditoria_id):
    """Devolve uma auditoria pelo id (None em falha ou ausência)."""
    try:
        conn = get_connection()
        if conn is None:
            return None
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, voo_id, cliente_id, propriedade_id, local, tipo, "
                "status, resumo, criado_por, criado_em "
                "FROM tb_perimetro_auditoria WHERE id=?",
                (int(auditoria_id),))
            return cur.fetchone()
        finally:
            conn.close()
    except Exception:
        return None


def atualizar_status(auditoria_id, status, resumo=None):
    """Muda o status e, quando informado, o texto do resumo."""
    try:
        if status not in STATUS:
            return False, "Status inválido"
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            if resumo is None:
                conn.execute(
                    "UPDATE tb_perimetro_auditoria SET status=? WHERE id=?",
                    (status, int(auditoria_id)))
            else:
                conn.execute(
                    "UPDATE tb_perimetro_auditoria SET status=?, resumo=? "
                    "WHERE id=?", (status, resumo, int(auditoria_id)))
            conn.commit()
            _audit("sistema", "atualizar_status", auditoria_id, status)
            return True, "Status atualizado"
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"atualizar_status: falha | {e}")
        except Exception:
            pass
        return False, "Erro ao atualizar status"


def adicionar_achado(ator, auditoria_id, classe, severidade="baixa",
                     confianca=0, revisao_humana=0, evidencia="",
                     latitude=None, longitude=None):
    """Registra um achado físico (triagem; revisão humana é explícita)."""
    try:
        if classe not in CLASSES:
            return False, "Classe inválida"
        if severidade not in SEVERIDADES:
            return False, "Severidade inválida"
        try:
            lat = float(latitude) if latitude not in (None, "") else None
        except Exception:
            lat = None
        try:
            lon = float(longitude) if longitude not in (None, "") else None
        except Exception:
            lon = None
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tb_perimetro_achado "
                "(auditoria_id, classe, severidade, confianca, revisao_humana, "
                "evidencia, latitude, longitude, criado_em) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (int(auditoria_id), classe, severidade,
                 float(confianca or 0), 1 if revisao_humana else 0,
                 evidencia or "", lat, lon, _agora()))
            conn.commit()
            novo_id = getattr(cur, "lastrowid", None)
            _audit(ator, "adicionar_achado", novo_id,
                   f"auditoria={auditoria_id} classe={classe} "
                   f"severidade={severidade}")
            return True, novo_id
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"adicionar_achado: falha | {e}")
        except Exception:
            pass
        return False, "Erro ao registrar achado"


def listar_achados(auditoria_id):
    """Lista os achados de uma auditoria, em ordem de criação."""
    try:
        conn = get_connection()
        if conn is None:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, auditoria_id, classe, severidade, confianca, "
                "revisao_humana, evidencia, latitude, longitude, criado_em "
                "FROM tb_perimetro_achado WHERE auditoria_id=? ORDER BY id",
                (int(auditoria_id),))
            return cur.fetchall()
        finally:
            conn.close()
    except Exception:
        return []


def marcar_revisao(achado_id, revisada=True):
    """Marca (ou desmarca) a revisão humana de um achado."""
    try:
        conn = get_connection()
        if conn is None:
            return False
        try:
            conn.execute(
                "UPDATE tb_perimetro_achado SET revisao_humana=? WHERE id=?",
                (1 if revisada else 0, int(achado_id)))
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


def _registro_canonico(registro):
    """Normaliza um registro RF antes da escrita (nunca guarda BSSID cru)."""
    if not isinstance(registro, dict):
        return {}
    if "bssid" in registro or "bssid_hash" not in registro:
        try:
            from mod_skyrover.rf_scan import normalizar_registro
            return normalizar_registro(registro)
        except Exception:
            return {}
    if not (registro.get("ssid") or registro.get("bssid_hash")):
        return {}
    return dict(registro)


def adicionar_rf(ator, auditoria_id, registro):
    """Grava um registro RF sanitizado e devolve (ok, id_ou_msg).

    Aceita o dict canônico de `rf_scan.normalizar_registro` ou um dict bruto
    (nesse caso normaliza aqui). O BSSID cru é descartado em qualquer caminho.
    """
    try:
        reg = _registro_canonico(registro)
        if not reg:
            return False, "Registro RF inválido"
        seguranca = reg.get("seguranca") or "desconhecida"
        risco = reg.get("risco") or "baixo"
        if seguranca not in SEGURANCAS:
            seguranca = "desconhecida"
        if risco not in RISCOS:
            risco = "baixo"
        try:
            canal = int(reg.get("canal") or 0)
        except Exception:
            canal = 0
        try:
            rssi = float(reg.get("rssi") or 0)
        except Exception:
            rssi = 0.0
        conn = get_connection()
        if conn is None:
            return False, "Falha ao conectar no banco do módulo"
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tb_perimetro_rf "
                "(auditoria_id, ssid, bssid_hash, banda, canal, rssi, "
                "seguranca, fora_perimetro, risco, evidencia, criado_em) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (int(auditoria_id), reg.get("ssid") or "",
                 reg.get("bssid_hash") or "", reg.get("banda") or "",
                 canal, rssi, seguranca,
                 1 if reg.get("fora_perimetro") else 0, risco,
                 reg.get("evidencia") or "", _agora()))
            conn.commit()
            novo_id = getattr(cur, "lastrowid", None)
            _audit(ator, "adicionar_rf", novo_id,
                   f"auditoria={auditoria_id} ssid={reg.get('ssid') or '—'} "
                   f"seguranca={seguranca} risco={risco}")
            return True, novo_id
        finally:
            conn.close()
    except Exception as e:
        try:
            _log().exception(f"adicionar_rf: falha | {e}")
        except Exception:
            pass
        return False, "Erro ao registrar rede RF"


def importar_rf(ator, auditoria_id, registros):
    """Importa registros brutos/canônicos e devolve (ok, quantidade_ou_msg).

    Cada item passa por `normalizar_registro` (SHA-256 do BSSID, banda/canal,
    severidade da segurança e risco calculado) antes de chegar ao banco.
    """
    try:
        if not registros:
            return True, 0
        total = 0
        for bruto in registros:
            reg = _registro_canonico(bruto)
            if not reg:
                continue
            ok, _msg = adicionar_rf(ator, auditoria_id, reg)
            if ok:
                total += 1
        if total == 0:
            return False, "Nenhum registro RF válido"
        return True, total
    except Exception as e:
        try:
            _log().exception(f"importar_rf: falha | {e}")
        except Exception:
            pass
        return False, "Erro ao importar registros RF"


def listar_rf(auditoria_id):
    """Lista as redes RF de uma auditoria (somente BSSID em hash)."""
    try:
        conn = get_connection()
        if conn is None:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, auditoria_id, ssid, bssid_hash, banda, canal, "
                "rssi, seguranca, fora_perimetro, risco, evidencia, criado_em "
                "FROM tb_perimetro_rf WHERE auditoria_id=? ORDER BY id",
                (int(auditoria_id),))
            return cur.fetchall()
        finally:
            conn.close()
    except Exception:
        return []


def resumo():
    """Contagens para o painel: status, severidades e indicadores RF."""
    vazio = {"total": 0, "rascunho": 0, "em_revisao": 0, "concluido": 0,
             "achados": 0, "baixa": 0, "media": 0, "alta": 0, "critica": 0,
             "pendentes_revisao": 0, "rf_total": 0, "rf_abertas": 0,
             "fora_perimetro": 0}
    try:
        if not init_db():
            return vazio
        conn = get_connection()
        if conn is None:
            return vazio
        try:
            cur = conn.cursor()
            cur.execute("SELECT status, COUNT(*) FROM tb_perimetro_auditoria "
                        "GROUP BY status")
            por_status = {s: int(n) for s, n in cur.fetchall()}
            cur.execute("SELECT severidade, COUNT(*) FROM tb_perimetro_achado "
                        "GROUP BY severidade")
            por_sev = {s: int(n) for s, n in cur.fetchall()}
            cur.execute("SELECT COUNT(*) FROM tb_perimetro_achado")
            achados = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT COUNT(*) FROM tb_perimetro_achado "
                "WHERE COALESCE(revisao_humana, 0)=0")
            pendentes = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM tb_perimetro_rf")
            rf_total = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT COUNT(*) FROM tb_perimetro_rf "
                "WHERE seguranca='aberta'")
            rf_abertas = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT COUNT(*) FROM tb_perimetro_rf "
                "WHERE COALESCE(fora_perimetro, 0)=1")
            fora = int(cur.fetchone()[0] or 0)
            return {"total": sum(por_status.values()),
                    "rascunho": por_status.get("rascunho", 0),
                    "em_revisao": por_status.get("em_revisao", 0),
                    "concluido": por_status.get("concluido", 0),
                    "achados": achados,
                    "baixa": por_sev.get("baixa", 0),
                    "media": por_sev.get("media", 0),
                    "alta": por_sev.get("alta", 0),
                    "critica": por_sev.get("critica", 0),
                    "pendentes_revisao": pendentes,
                    "rf_total": rf_total,
                    "rf_abertas": rf_abertas,
                    "fora_perimetro": fora}
        finally:
            conn.close()
    except Exception:
        return vazio
