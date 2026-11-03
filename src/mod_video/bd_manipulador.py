# -*- coding: utf-8 -*-
"""EN: Video download module — own database (db_mod_video.db, WAL). The ONLY
access point to the module's data: download history (who asked, which URL,
platform, title, format, status, file, expiry, published flag, when) and the
system library (published videos, no expiry, shared via /midia_video). Owns
its schema in `init_db` (portable SQL, SQLite/PostgreSQL). Never reads
another module's database; user identity comes from the session (`user_nome`
passed by the caller). Stage files live in `mod_video/downloads/` (10 min
default, configurable); published files live in `mod_video/biblioteca/`
(no expiry).

PT-BR: Módulo de baixar vídeos — banco próprio (db_mod_video.db, WAL). ÚNICO
ponto de acesso aos dados do módulo: histórico de downloads (quem pediu,
qual URL, plataforma, título, formato, status, arquivo, expiração,
publicado, quando) e a biblioteca do sistema (vídeos publicados, sem
expiração, servidos em /midia_video). Dono do schema em `init_db` (SQL
portátil, SQLite/PostgreSQL). Nunca lê banco de outro módulo; a identidade
vem da sessão (`user_nome` que quem chama informa). Arquivos de stage em
`mod_video/downloads/` (10 min padrão, configurável); publicados em
`mod_video/biblioteca/` (sem expiração).

TABLES (prefixo `tb_video_`)
    tb_video_historico  um por pedido: url + plataforma + título + formato +
                        status + arquivo + tamanho + expira_em + publicado +
                        quando
"""
import os
import sys
import time
import zipfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CHAVE_MODULO = "video"
NOME_MODULO = "Vídeos"

TENTATIVAS_LOCKED = 5
ESPERA_LOCKED_SEG = 0.05

EXPIRACAO_PADRAO_MIN = 10

MOD_DIR = os.path.dirname(os.path.abspath(__file__))
DIR_DOWNLOADS = os.path.join(MOD_DIR, "downloads")
DIR_BIBLIOTECA = os.path.join(MOD_DIR, "biblioteca")


def _log():
    """EN: Module-scoped logger. PT-BR: logger escopado do módulo."""
    try:
        from mod_tisosdocfly import observabilidade
        return observabilidade.get_logger("video")
    except Exception:
        return None


def _agora():
    """EN: Local datetime as text. PT-BR: data/hora local em texto."""
    try:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _daqui_a_minutos(minutos):
    """EN: Local datetime + N minutes as text. PT-BR: data/hora + N min."""
    try:
        return (datetime.now() + timedelta(minutes=int(minutos))).strftime(
            "%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def cfg_expiracao_min():
    """EN: Stage lifetime in minutes (`video_expiracao_min`, min 1).
    PT-BR: tempo de vida do stage em minutos (`video_expiracao_min`, mín 1)."""
    try:
        from mod_tisosdocfly.bd_conexao import get_config
        return max(1, int(get_config("video_expiracao_min",
                                     str(EXPIRACAO_PADRAO_MIN))))
    except (TypeError, ValueError):
        return EXPIRACAO_PADRAO_MIN
    except Exception:
        return EXPIRACAO_PADRAO_MIN


def _eh_bloqueio_banco(exc):
    """EN: True on transient lock contention. PT-BR: verdadeiro em contenção."""
    try:
        texto = str(exc or "").lower()
        return ("database is locked" in texto or "locked" in texto
                or "busy" in texto or "deadlock" in texto)
    except Exception:
        return False


def _rollback_seguro(conn, contexto=""):
    """EN: Best-effort rollback. PT-BR: rollback que nunca derruba."""
    try:
        if conn is not None:
            conn.rollback()
    except Exception:
        pass


def _commit_com_retry(conn, contexto="", tentativas=None, espera_s=None):
    """EN: Commit with short retry on lock. PT-BR: commit com retry curto."""
    try:
        tentativas = tentativas or TENTATIVAS_LOCKED
        espera_s = espera_s if espera_s is not None else ESPERA_LOCKED_SEG
        for tentativa in range(1, tentativas + 1):
            try:
                conn.commit()
                return True
            except Exception as exc:
                if _eh_bloqueio_banco(exc) and tentativa < tentativas:
                    try:
                        time.sleep(espera_s * tentativa)
                    except Exception:
                        pass
                    continue
                raise
        return True
    except Exception:
        raise


def get_connection():
    """EN: Opens the module connection (WAL). PT-BR: abre a conexão (WAL)."""
    try:
        from mod_tisosdocfly.banco_conexao import conexao
        conn = conexao(CHAVE_MODULO)
        if conn is None:
            raise RuntimeError("Falha ao abrir conexão mod_video")
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass
        return conn
    except Exception:
        try:
            lg = _log()
            if lg is not None:
                lg.exception("get_connection falhou")
        except Exception:
            pass
        raise


def _auditar(ator, acao, alvo, detalhe=""):
    """EN: Central audit trail (fail-soft). PT-BR: trilha central (fail-soft)."""
    try:
        from mod_tisosdocfly import integracoes
        integracoes.registrar_auditoria(
            ator or "sistema", CHAVE_MODULO, acao,
            f"Alvo: {alvo}" + (f" | {detalhe}" if detalhe else ""))
    except Exception:
        pass


DDL_HISTORICO = """
CREATE TABLE IF NOT EXISTS tb_video_historico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_nome TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    plataforma TEXT NOT NULL DEFAULT '',
    titulo TEXT NOT NULL DEFAULT '',
    formato TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    arquivo TEXT NOT NULL DEFAULT '',
    tamanho_bytes INTEGER NOT NULL DEFAULT 0,
    expira_em TEXT NOT NULL DEFAULT '',
    publicado INTEGER NOT NULL DEFAULT 0,
    data_registro TEXT NOT NULL DEFAULT '',
    miniatura TEXT NOT NULL DEFAULT ''
)
"""


def _garantir_colunas(conn):
    """EN: Adds new columns to a pre-existing table (idempotent, portable).
    PT-BR: adiciona colunas novas em tabela antiga (idempotente, portátil)."""
    try:
        cur = conn.cursor()
        for coluna, ddl in (("expira_em", "TEXT NOT NULL DEFAULT ''"),
                            ("publicado", "INTEGER NOT NULL DEFAULT 0"),
                            ("miniatura", "TEXT NOT NULL DEFAULT ''")):
            try:
                cur.execute(f"SELECT {coluna} FROM tb_video_historico LIMIT 1")
                cur.fetchall()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                try:
                    cur.execute(
                        f"ALTER TABLE tb_video_historico ADD COLUMN {coluna} {ddl}")
                except Exception as e2:
                    lg = _log()
                    if lg is not None:
                        lg.warning(f"_garantir_colunas({coluna}): {e2}")
        return True
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"_garantir_colunas: {e}")
        except Exception:
            pass
        return False


def init_db():
    """EN: Creates the module schema (idempotent). PT-BR: cria o schema."""
    conn = None
    try:
        for pasta in (DIR_DOWNLOADS, DIR_BIBLIOTECA):
            try:
                os.makedirs(pasta, exist_ok=True)
            except Exception:
                pass
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(DDL_HISTORICO)
        _garantir_colunas(conn)
        _commit_com_retry(conn, contexto="init_db")
        return True
    except Exception:
        _rollback_seguro(conn, contexto="init_db")
        try:
            lg = _log()
            if lg is not None:
                lg.exception("init_db falhou")
        except Exception:
            pass
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def init_db_video():
    """EN: Bootstrap alias. PT-BR: apelido de bootstrap (o boot chama este)."""
    try:
        ok = bool(init_db())
        try:
            reconciliar_pendentes_boot()
        except Exception:
            pass
        return ok
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"init_db_video falhou: {e}")
        except Exception:
            pass
        return False


def reconciliar_pendentes_boot():
    """EN: Stale 'pendente' rows failed (dead process). PT-BR: pendente
    antigo vira erro (processo morto no meio — reinício ou queda). Sem
    tarefa viva no boot, pendente com 2+ min é órfão. Devolve quantos."""
    try:
        from datetime import datetime as _dt
        from datetime import timedelta as _td
        conn = get_connection()
        try:
            cur = conn.cursor()
            try:
                linhas = cur.execute(
                    f"SELECT {_COLS} FROM tb_video_historico "
                    "WHERE status='pendente'").fetchall()
            except Exception:
                linhas = []
            n = 0
            agora = _dt.now()
            for ped in _linhas_para_dicts(linhas):
                try:
                    dt = _dt.strptime(
                        (ped.get("data_registro") or "")[:19],
                        "%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError):
                    continue
                except Exception:
                    continue
                if agora - dt > _td(minutes=2):
                    try:
                        cur.execute(
                            "UPDATE tb_video_historico SET status='erro' "
                            "WHERE id=?", (ped["id"],))
                        n += 1
                    except Exception:
                        pass
            _commit_com_retry(conn, contexto="reconciliar_pendentes_boot")
            if n:
                _auditar("sistema", "video_reconciliado", "boot",
                         f"{n} pendente(s) órfão(s) → erro")
            return n
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"reconciliar_pendentes_boot: {e}")
        except Exception:
            pass
        return 0


def montar_rotas_static():
    """EN: Serves the system library at /midia_video/* (like filas).
    PT-BR: serve a biblioteca em /midia_video/* (como as filas). Só a
    biblioteca (sem expiração) é pública; o stage nunca tem rota."""
    try:
        from nicegui import app as _app
        os.makedirs(DIR_BIBLIOTECA, exist_ok=True)
        _app.add_static_files("/midia_video", DIR_BIBLIOTECA)
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.warning(f"montar_rotas_static: {e}")
        except Exception:
            pass


def url_biblioteca(nome_arquivo):
    """EN: Public URL of a published file. PT-BR: URL pública do publicado."""
    try:
        base = _sanitizar_nome(nome_arquivo)
        if not base:
            return ""
        return f"/midia_video/{base}"
    except Exception:
        return ""


def registrar_pedido(user_nome, url, plataforma, formato="melhor_mp4",
                     expira_em="", titulo="", miniatura=""):
    """EN: Registers a download request (status pendente). PT-BR: registra o
    pedido (status pendente). `expira_em` vazio = sem expiração (admin).
    `titulo` prévio (da verificação) para a linha nunca ficar sem nome.
    `miniatura` é a capa do vídeo (URL) para o player. Devolve o id ou None."""
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tb_video_historico (user_nome, url, plataforma,"
                " titulo, formato, status, arquivo, tamanho_bytes, expira_em,"
                " publicado, data_registro, miniatura)"
                " VALUES (?, ?, ?, ?, ?, 'pendente', '', 0, ?, 0, ?, ?)",
                ((user_nome or "").strip(), (url or "").strip()[:2000],
                 (plataforma or "").strip()[:60],
                 str(titulo or "")[:300],
                 (formato or "").strip()[:30],
                 (expira_em or "").strip()[:19], _agora(),
                 str(miniatura or "")[:500]))
            _commit_com_retry(conn, contexto="registrar_pedido")
            try:
                return cur.lastrowid
            except Exception:
                return None
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"registrar_pedido: {e}")
        except Exception:
            pass
        return None


def definir_miniatura(pedido_id, url):
    """EN: Sets the thumbnail once (never overwrites). PT-BR: grava a capa
    uma vez (nunca sobrescreve a existente)."""
    try:
        mini = str(url or "")[:500]
        if not mini:
            return False
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tb_video_historico SET miniatura=? WHERE id=? "
                "AND (miniatura IS NULL OR miniatura='')",
                (mini, int(pedido_id)))
            _commit_com_retry(conn, contexto="definir_miniatura")
            return True
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        return False


def atualizar_status(pedido_id, status, titulo="", arquivo="", tamanho=0,
                     expira_em=None, miniatura=None):
    """EN: Updates status/title/file of a request. PT-BR: atualiza
    status/título/arquivo do pedido (`expira_em=None` não toca a expiração;
    `miniatura` só preenche quando vazia)."""
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            if titulo:
                cur.execute(
                    "UPDATE tb_video_historico SET status=?, titulo=?,"
                    " arquivo=?, tamanho_bytes=? WHERE id=?",
                    ((status or "").strip()[:30], str(titulo or "")[:300],
                     str(arquivo or "")[:300], int(tamanho or 0),
                     int(pedido_id)))
            else:
                cur.execute(
                    "UPDATE tb_video_historico SET status=?, arquivo=?,"
                    " tamanho_bytes=? WHERE id=?",
                    ((status or "").strip()[:30],
                     str(arquivo or "")[:300], int(tamanho or 0),
                     int(pedido_id)))
            if expira_em is not None:
                cur.execute(
                    "UPDATE tb_video_historico SET expira_em=? WHERE id=?",
                    (str(expira_em or "")[:19], int(pedido_id)))
            if miniatura:
                cur.execute(
                    "UPDATE tb_video_historico SET miniatura=? WHERE id=? "
                    "AND (miniatura IS NULL OR miniatura='')",
                    (str(miniatura or "")[:500], int(pedido_id)))
            _commit_com_retry(conn, contexto="atualizar_status")
            return True
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"atualizar_status({pedido_id}): {e}")
        except Exception:
            pass
        return False


def marcar_erro(pedido_id, detalhe=""):
    """EN: Marks a request as error. PT-BR: marca o pedido como erro."""
    try:
        ok = atualizar_status(pedido_id, "erro")
        try:
            _auditar("sistema", "video_erro", str(pedido_id),
                     str(detalhe or "")[:200])
        except Exception:
            pass
        return ok
    except Exception:
        return False


def obter_pedido(pedido_id):
    """EN: One request as dict (or {}). PT-BR: um pedido como dict (ou {})."""
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            l = cur.execute(
                "SELECT id, user_nome, url, plataforma, titulo, formato,"
                " status, arquivo, tamanho_bytes, expira_em, publicado,"
                " data_registro, miniatura FROM tb_video_historico WHERE id=?",
                (int(pedido_id),)).fetchone()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            l = cur.execute(
                "SELECT id, user_nome, url, plataforma, titulo, formato,"
                " status, arquivo, tamanho_bytes, expira_em, publicado,"
                " data_registro FROM tb_video_historico WHERE id=?",
                (int(pedido_id),)).fetchone()
        if not l:
            return {}
        return {"id": l[0], "user_nome": l[1] or "", "url": l[2] or "",
                "plataforma": l[3] or "", "titulo": l[4] or "",
                "formato": l[5] or "", "status": l[6] or "",
                "arquivo": l[7] or "", "tamanho_bytes": l[8] or 0,
                "expira_em": l[9] or "", "publicado": bool(l[10] or 0),
                "data_registro": l[11] or "",
                "miniatura": l[12] if len(l) > 12 and l[12] else ""}
    except Exception:
        return {}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _linhas_para_dicts(linhas):
    """EN: Rows to dicts. PT-BR: linhas para dicts."""
    saida = []
    for l in linhas or []:
        try:
            saida.append({"id": l[0], "user_nome": l[1] or "",
                          "url": l[2] or "", "plataforma": l[3] or "",
                          "titulo": l[4] or "", "formato": l[5] or "",
                          "status": l[6] or "", "arquivo": l[7] or "",
                          "tamanho_bytes": l[8] or 0,
                          "expira_em": l[9] or "",
                          "publicado": bool(l[10] or 0),
                          "data_registro": l[11] or "",
                          "miniatura": l[12] if len(l) > 12 and l[12]
                          else ""})
        except Exception:
            pass
    return saida


_COLS = ("id, user_nome, url, plataforma, titulo, formato, status, arquivo,"
         " tamanho_bytes, expira_em, publicado, data_registro, miniatura")


def listar_historico(user_nome="", limite=30):
    """EN: Recent requests (own or all for admin). PT-BR: pedidos recentes
    (próprios ou todos para o admin)."""
    try:
        limite = max(1, min(200, int(limite or 30)))
    except (TypeError, ValueError):
        limite = 30
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        if (user_nome or "").strip():
            linhas = cur.execute(
                f"SELECT {_COLS} FROM tb_video_historico WHERE user_nome=? "
                "ORDER BY id DESC LIMIT ?",
                ((user_nome or "").strip(), limite)).fetchall()
        else:
            linhas = cur.execute(
                f"SELECT {_COLS} FROM tb_video_historico "
                "ORDER BY id DESC LIMIT ?",
                (limite,)).fetchall()
        return _linhas_para_dicts(linhas)
    except Exception:
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def listar_biblioteca(limite=100):
    """EN: Published videos (no expiry, everyone with access). PT-BR: vídeos
    publicados (sem expiração, todos com acesso ao módulo)."""
    try:
        limite = max(1, min(500, int(limite or 100)))
    except (TypeError, ValueError):
        limite = 100
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        linhas = cur.execute(
            f"SELECT {_COLS} FROM tb_video_historico WHERE publicado=1 "
            "AND status='pronto' ORDER BY id DESC LIMIT ?",
            (limite,)).fetchall()
        return _linhas_para_dicts(linhas)
    except Exception:
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def contar_historico(user_nome=""):
    """EN: Counts requests. PT-BR: conta os pedidos."""
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        if (user_nome or "").strip():
            linha = cur.execute(
                "SELECT COUNT(*) FROM tb_video_historico WHERE user_nome=?",
                ((user_nome or "").strip(),)).fetchone()
        else:
            linha = cur.execute(
                "SELECT COUNT(*) FROM tb_video_historico").fetchone()
        return int((linha or [0])[0] or 0)
    except Exception:
        return 0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _sanitizar_nome(nome):
    """EN: Plain filename only (traversal-safe). PT-BR: só nome simples
    (anti traversal). Com barra ou `..` recusa, não neutraliza."""
    try:
        texto = str(nome or "")
        if not texto or texto in (".", ".."):
            return ""
        if "/" in texto or "\\" in texto or ".." in texto:
            return ""
        base = os.path.basename(texto)
        if base != texto or base in ("", ".", ".."):
            return ""
        return base
    except Exception:
        return ""


def _sob_dir(base_dir, nome):
    """EN: Absolute path inside a base dir (traversal-safe). PT-BR: caminho
    absoluto dentro da base (anti traversal). Devolve "" se inválido."""
    try:
        base = os.path.abspath(base_dir)
        alvo = os.path.normpath(os.path.join(base, _sanitizar_nome(nome)))
        if os.path.dirname(alvo) != base:
            return ""
        return alvo
    except Exception:
        return ""


def caminho_arquivo(nome_arquivo, publicado=False):
    """EN: Absolute stage/library path (traversal-safe). PT-BR: caminho
    absoluto do stage/biblioteca (anti traversal). Devolve "" se inválido."""
    try:
        base = DIR_BIBLIOTECA if publicado else DIR_DOWNLOADS
        nome = _sanitizar_nome(nome_arquivo)
        if not nome:
            return ""
        return _sob_dir(base, nome)
    except Exception:
        return ""


def _nome_unico(base_dir, nome):
    """EN: First free name in a dir. PT-BR: primeiro nome livre na pasta."""
    try:
        nome = _sanitizar_nome(nome)
        if not nome:
            return ""
        raiz, ext = os.path.splitext(nome)
        candidato = nome
        n = 2
        while os.path.exists(os.path.join(base_dir, candidato)):
            candidato = f"{raiz}_{n}{ext}"
            n += 1
            if n > 999:
                return ""
        return candidato
    except Exception:
        return ""


def publicar_pedido(pedido_id, ator=""):
    """EN: Moves a ready file to the system library (no expiry). PT-BR: move
    o arquivo pronto para a biblioteca do sistema (sem expiração). Devolve
    (ok, mensagem)."""
    try:
        ped = obter_pedido(pedido_id)
        if not ped:
            return False, "Pedido não encontrado."
        if ped.get("status") != "pronto" or not ped.get("arquivo"):
            return False, "Só vídeo pronto pode ser publicado."
        if ped.get("publicado"):
            return True, "Já está na biblioteca."
        origem = caminho_arquivo(ped["arquivo"], publicado=False)
        if not origem or not os.path.isfile(origem):
            return False, "Arquivo não está mais no servidor (expirou?)."
        try:
            os.makedirs(DIR_BIBLIOTECA, exist_ok=True)
        except Exception:
            pass
        destino_nome = _nome_unico(DIR_BIBLIOTECA, ped["arquivo"])
        if not destino_nome:
            return False, "Não foi possível reservar o nome na biblioteca."
        try:
            os.rename(origem, os.path.join(DIR_BIBLIOTECA, destino_nome))
        except Exception as e:
            return False, f"Não foi possível mover: {e}"
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tb_video_historico SET publicado=1, arquivo=?,"
                " expira_em='' WHERE id=?",
                (destino_nome, int(pedido_id)))
            _commit_com_retry(conn, contexto="publicar_pedido")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        _auditar(ator or "sistema", "video_publicado", str(pedido_id),
                 (ped.get("titulo") or "")[:200])
        return True, "Disponível na biblioteca do sistema."
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"publicar_pedido({pedido_id}): {e}")
        except Exception:
            pass
        return False, f"Não foi possível publicar: {e}"


def despublicar_pedido(pedido_id, ator=""):
    """EN: Moves a published file back to stage. PT-BR: devolve o publicado
    ao stage. Devolve (ok, mensagem)."""
    try:
        ped = obter_pedido(pedido_id)
        if not ped:
            return False, "Pedido não encontrado."
        if not ped.get("publicado"):
            return True, "Não está na biblioteca."
        origem = caminho_arquivo(ped["arquivo"], publicado=True)
        destino_nome = ped.get("arquivo") or ""
        if origem and os.path.isfile(origem):
            try:
                os.makedirs(DIR_DOWNLOADS, exist_ok=True)
            except Exception:
                pass
            destino_nome = _nome_unico(DIR_DOWNLOADS, ped["arquivo"])
            if not destino_nome:
                return False, "Não foi possível reservar o nome no stage."
            try:
                os.rename(origem, os.path.join(DIR_DOWNLOADS, destino_nome))
            except Exception as e:
                return False, f"Não foi possível mover: {e}"
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tb_video_historico SET publicado=0, arquivo=? WHERE id=?",
                (destino_nome if origem and destino_nome else "", int(pedido_id)))
            _commit_com_retry(conn, contexto="despublicar_pedido")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        _auditar(ator or "sistema", "video_despublicado", str(pedido_id), "")
        return True, "Devolvido ao stage."
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"despublicar_pedido({pedido_id}): {e}")
        except Exception:
            pass
        return False, f"Não foi possível devolver: {e}"


def excluir_pedido(pedido_id, ator=""):
    """EN: Deletes the file (stage or library) and the row. PT-BR: apaga o
    arquivo (stage ou biblioteca) e o registro. Devolve (ok, mensagem)."""
    try:
        ped = obter_pedido(pedido_id)
        if not ped:
            return False, "Pedido não encontrado."
        for pub in (False, True):
            try:
                caminho = caminho_arquivo(ped.get("arquivo") or "", publicado=pub)
                if caminho and os.path.isfile(caminho):
                    os.remove(caminho)
            except Exception:
                pass
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM tb_video_historico WHERE id=?",
                        (int(pedido_id),))
            _commit_com_retry(conn, contexto="excluir_pedido")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        _auditar(ator or "sistema", "video_excluido", str(pedido_id),
                 (ped.get("titulo") or "")[:200])
        return True, "Excluído."
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"excluir_pedido({pedido_id}): {e}")
        except Exception:
            pass
        return False, f"Não foi possível excluir: {e}"


def expirar_antigos(minutos=None):
    """EN: Removes expired stage files (like edit_pdf). PT-BR: remove os
    arquivos de stage expirados (como o edit_pdf). Publicado nunca expira.
    Devolve a quantidade removida."""
    removidos = 0
    conn = None
    try:
        try:
            limite = max(1, int(minutos if minutos is not None
                                else cfg_expiracao_min()))
        except (TypeError, ValueError):
            limite = EXPIRACAO_PADRAO_MIN
        agora_txt = _agora()
        conn = get_connection()
        cur = conn.cursor()
        try:
            # Legado sem expira_em: estima pelo pedido + TTL e GRAVA antes
            # de avaliar (só assim a contagem aparece e a regra vale igual
            # para todos; se já venceu, cai no expirado abaixo).
            try:
                cur.execute(
                    "UPDATE tb_video_historico SET expira_em = "
                    "datetime(data_registro, ?) "
                    "WHERE publicado=0 AND status='pronto' "
                    "AND (expira_em IS NULL OR expira_em='')",
                    (f"+{limite} minutes",))
            except Exception:
                pass
        except Exception:
            pass
        try:
            linhas = cur.execute(
                f"SELECT {_COLS} FROM tb_video_historico "
                "WHERE publicado=0 AND status='pronto' AND arquivo<>''"
            ).fetchall()
        except Exception:
            linhas = []
        for ped in _linhas_para_dicts(linhas):
            try:
                expira = (ped.get("expira_em") or "").strip()
                caminho = caminho_arquivo(ped.get("arquivo") or "",
                                          publicado=False)
                if not caminho or not os.path.isfile(caminho):
                    cur.execute(
                        "UPDATE tb_video_historico SET status='expirado',"
                        " arquivo='' WHERE id=?", (ped["id"],))
                    removidos += 1
                    continue
                vencido = False
                if expira:
                    vencido = expira <= agora_txt
                else:
                    try:
                        idade_s = time.time() - os.path.getmtime(caminho)
                        vencido = idade_s > limite * 60
                    except Exception:
                        vencido = False
                if vencido:
                    try:
                        os.remove(caminho)
                    except OSError:
                        pass
                    cur.execute(
                        "UPDATE tb_video_historico SET status='expirado',"
                        " arquivo='' WHERE id=?", (ped["id"],))
                    removidos += 1
            except Exception:
                pass
        _commit_com_retry(conn, contexto="expirar_antigos")
        try:
            # Varredura de órfãos: arquivo sem dono vivo (resto de queda,
            # ZIP efêmero que o timer não pegou, .part abandonado). Regra:
            # referenciado por pronto = intocável; download ativo tem
            # mtime fresco (gravando) e também escapa; o resto, passado o
            # TTL, sai. Linha terminal (erro/entregue/expirado) nunca tem
            # arquivo — limpa a referência junto.
            try:
                refs = cur.execute(
                    "SELECT arquivo FROM tb_video_historico "
                    "WHERE arquivo<>'' AND status='pronto'"
                ).fetchall()
                usados = {r[0] for r in refs if r and r[0]}
            except Exception:
                usados = set()
            try:
                nomes = os.listdir(DIR_DOWNLOADS)
            except OSError:
                nomes = []
            agora_s = time.time()
            for nome in nomes:
                try:
                    if not nome or nome in usados:
                        continue
                    cheio = os.path.join(DIR_DOWNLOADS, nome)
                    if not os.path.isfile(cheio):
                        continue
                    try:
                        idade_s = agora_s - os.path.getmtime(cheio)
                    except OSError:
                        continue
                    if idade_s > limite * 60:
                        try:
                            os.remove(cheio)
                            removidos += 1
                        except OSError:
                            pass
                except Exception:
                    pass
            try:
                cur.execute(
                    "UPDATE tb_video_historico SET arquivo='' "
                    "WHERE arquivo<>'' AND status IN "
                    "('erro', 'entregue', 'expirado')")
                _commit_com_retry(conn, contexto="expirar_antigos:orfaos")
            except Exception:
                pass
        except Exception:
            pass
        if removidos:
            _auditar("sistema", "video_expiracao", "stage",
                     f"{removidos} removido(s)")
        return removidos
    except Exception as e:
        _rollback_seguro(conn, contexto="expirar_antigos")
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"expirar_antigos: {e}")
        except Exception:
            pass
        return removidos
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def zipar_selecao(user_nome, nomes):
    """EN: ZIPs stage files into downloads/ (ephemeral, like edit_pdf).
    PT-BR: junta arquivos do stage num ZIP em downloads/ (efêmero, como o
    edit_pdf). Só arquivos existentes e válidos entram. Devolve o caminho
    ou None."""
    try:
        validos = []
        for nome in nomes or []:
            try:
                caminho = caminho_arquivo(nome, publicado=False)
                if caminho and os.path.isfile(caminho):
                    validos.append((caminho, _sanitizar_nome(nome)))
            except Exception:
                pass
        if not validos:
            return None
        try:
            os.makedirs(DIR_DOWNLOADS, exist_ok=True)
        except Exception:
            pass
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        base_user = "".join(c for c in (user_nome or "video") if c.isalnum() or c in ("_", "-"))[:30] or "video"
        zip_path = os.path.join(DIR_DOWNLOADS, f"{base_user}_{stamp}_selecao.zip")
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                for caminho, nome in validos:
                    try:
                        z.write(caminho, nome)
                    except Exception:
                        pass
        except Exception as e:
            try:
                lg = _log()
                if lg is not None:
                    lg.exception(f"zipar_selecao: {e}")
            except Exception:
                pass
            return None
        return zip_path if os.path.isfile(zip_path) else None
    except Exception:
        return None
