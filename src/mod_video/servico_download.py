# -*- coding: utf-8 -*-
"""EN: Download engine — yt-dlp wrapper (YouTube, Facebook, TikTok, Instagram
and hundreds of other sites). Prefers the `yt_dlp` Python package; falls back
to the `yt-dlp` CLI binary. Files land in `mod_video/downloads/`. Every
function is try/except (never crashes the handler).

PT-BR: Motor de download — invólucro do yt-dlp (YouTube, Facebook, TikTok,
Instagram e centenas de outros sites). Prefere o pacote `yt_dlp`; cai para o
binário `yt-dlp` da CLI. Arquivos em `mod_video/downloads/`. Toda função com
try/except (nunca derruba o handler).
"""
import os
import re
import shutil
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

try:
    from mod_video import bd_manipulador as _bd
    _DIR_DOWNLOADS = _bd.DIR_DOWNLOADS
except Exception:
    _DIR_DOWNLOADS = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "downloads")

FORMATOS = (
    ("melhor_mp4", "Melhor qualidade (MP4)"),
    ("medio_mp4", "Média qualidade (MP4 720p)"),
    ("audio_mp3", "Somente áudio (MP3)"),
)

# ============================================================
# EASTER EGG — NÃO DOCUMENTAR (decisão do responsável, 17/10/2026).
# O bloco FALA (texto → áudio) é função escondida: NUNCA entra em docs/,
# estrutura.md, site/ ou wiki — documentar estraga a graça. Quem mexer
# aqui mantém a marca em cada função do bloco.
# ============================================================
# Fala (texto → áudio): a voz neural (Edge, pt-BR M/F) é a padrão; o
# espeak offline é a reserva. O formato já carrega a voz
# (`fala_mp3_F` = MP3 feminina…), escolhido no combolist.
FORMATOS_FALA = (
    ("fala_mp3_francisca", "Fala em MP3 — Eliana (feminina BR)"),
    ("fala_mp3_antonio", "Fala em MP3 — Luiz Miguel (masculina BR)"),
    ("fala_mp3_thalita", "Fala em MP3 — Thalita (feminina BR)"),
    ("fala_mp3_duarte", "Fala em MP3 — Duarte (masculino PT)"),
    ("fala_mp3_raquel", "Fala em MP3 — Raquel (feminina PT)"),
    ("fala_wav_francisca", "Fala em WAV — Eliana (feminina BR)"),
    ("fala_wav_antonio", "Fala em WAV — Luiz Miguel (masculina BR)"),
    ("fala_wav_thalita", "Fala em WAV — Thalita (feminina BR)"),
    ("fala_wav_duarte", "Fala em WAV — Duarte (masculino PT)"),
    ("fala_wav_raquel", "Fala em WAV — Raquel (feminina PT)"),
)

FALA_MAX_CHARS = 3000

VOZES_FALA = (
    ("F", "pt-BR-FranciscaNeural", "Francisca"),
    ("M", "pt-BR-AntonioNeural", "Antonio"),
    ("T", "pt-BR-ThalitaMultilingualNeural", "Thalita"),
    ("D", "pt-PT-DuarteNeural", "Duarte"),
    ("R", "pt-PT-RaquelNeural", "Raquel"),
)

_CHAVES_VOZ = ("F", "M", "T", "D", "R")

# Sem ffmpeg não há junção: só arquivo único (o que não couber aqui nem
# é oferecido — playlist inclusa).
FORMATOS_SEM_FFMPEG = (
    ("unico", "Melhor arquivo único"),
    ("audio_orig", "Somente áudio (original)"),
)

FORMATOS_VALIDOS = ("melhor_mp4", "medio_mp4", "audio_mp3",
                    "unico", "audio_orig")

_DOMINIO_PLATAFORMA = (
    ("youtube", "YouTube"),
    ("youtu.be", "YouTube"),
    ("facebook", "Facebook"),
    ("fb.watch", "Facebook"),
    ("tiktok", "TikTok"),
    ("instagram", "Instagram"),
    ("kwai", "Kwai"),
    ("vimeo", "Vimeo"),
    ("dailymotion", "Dailymotion"),
    ("twitch", "Twitch"),
    ("twitter", "X/Twitter"),
    ("x.com", "X/Twitter"),
)


def _log():
    """EN: Module-scoped logger. PT-BR: logger escopado do módulo."""
    try:
        from mod_tisosdocfly import observabilidade
        return observabilidade.get_logger("video")
    except Exception:
        return None


def validar_url(url):
    """EN: Accepts only http/https URLs. PT-BR: aceita só URL http/https."""
    try:
        texto = (url or "").strip()
        if not texto or len(texto) > 2000:
            return ""
        partes = urllib.parse.urlparse(texto)
        if partes.scheme not in ("http", "https"):
            return ""
        if not partes.netloc or "." not in partes.netloc:
            return ""
        return texto
    except Exception:
        return ""


def detectar_plataforma(url):
    """EN: Platform label from the host. PT-BR: rótulo da plataforma."""
    try:
        hospedeiro = (urllib.parse.urlparse(url or "").netloc or "").lower()
        for pedaco, rotulo in _DOMINIO_PLATAFORMA:
            if pedaco in hospedeiro:
                return rotulo
        return "Outro site"
    except Exception:
        return "Outro site"


def yt_dlp_disponivel():
    """EN: True if the Python package or the CLI binary exists. PT-BR:
    verdadeiro se o pacote Python ou o binário da CLI existir."""
    try:
        try:
            import yt_dlp  # noqa: F401
            return True
        except Exception:
            pass
        return bool(shutil.which("yt-dlp"))
    except Exception:
        return False


def tem_ffmpeg():
    """EN: True if ffmpeg is on PATH (merging/converting available). PT-BR:
    verdadeiro se o ffmpeg está no PATH (permite juntar e converter)."""
    try:
        return bool(shutil.which("ffmpeg"))
    except Exception:
        return False


class DownloadCancelado(Exception):
    """EN: Raised by the progress hook when the user cancels. PT-BR:
    lançada pelo hook de progresso quando o usuário cancela."""


_CANCELADOS = set()
_PROCESSOS = {}


def solicitar_cancelamento(pedido_id):
    """EN: Asks a running download to stop (hook raises / CLI killed).
    PT-BR: pede a parada de um download em curso (hook levanta / CLI
    morre). Idempotente; vale também antes de começar."""
    try:
        _CANCELADOS.add(int(pedido_id))
        try:
            proc = _PROCESSOS.get(int(pedido_id))
            if proc is not None and proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        return True
    except Exception:
        return False


def consumir_cancelamento(pedido_id):
    """EN: Pops the cancel flag (True = was cancelled). PT-BR: consome o
    pedido de cancelamento (True = foi cancelado)."""
    try:
        pid = int(pedido_id)
        if pid in _CANCELADOS:
            _CANCELADOS.discard(pid)
            return True
        return False
    except Exception:
        return False


def _limpar_cancelamento(pedido_id):
    """EN: Forgets flag + process handle. PT-BR: esquece flag e processo."""
    try:
        pid = int(pedido_id)
        _CANCELADOS.discard(pid)
        _PROCESSOS.pop(pid, None)
    except Exception:
        pass


def aviso_qualidade():
    """EN: Warning when ffmpeg is missing (single-file fallback). PT-BR:
    aviso quando falta ffmpeg (cai para arquivo único)."""
    try:
        if tem_ffmpeg():
            return ""
        return ("Sem ffmpeg no servidor: o vídeo vem em arquivo único "
                "(até 720p) e o áudio no formato original. Para qualidade "
                "máxima e MP3, peça ao administrador geral do servidor "
                "(quem fez a instalação e a ativação) para instalar o "
                "ffmpeg.")
    except Exception:
        return ""


def _nome_seguro_usuario(user_nome):
    """EN: Sanitized user for filenames. PT-BR: usuário sanitizado para
    nome de arquivo (só letras/números/_/-)."""
    try:
        base = "".join(c for c in str(user_nome or "") if c.isalnum()
                        or c in ("_", "-")).strip("_-")[:30]
        return base or "video"
    except Exception:
        return "video"


def _opcoes_saida(formato, pedido_id, user_nome=""):
    """EN: Output template + format selector. PT-BR: modelo de saída. Sem
    ffmpeg não há junção nem conversão: cai para o melhor arquivo único.
    O arquivo nasce como `usuario_AAAAMMDDHHMMSS_titulo[id]-pid.ext` para
    identificar o dono no disco (como o edit_pdf)."""
    try:
        os.makedirs(_DIR_DOWNLOADS, exist_ok=True)
    except Exception:
        pass
    try:
        from datetime import datetime as _dt
        stamp = _dt.now().strftime("%Y%m%d%H%M%S")
    except Exception:
        stamp = "semdata"
    prefixo = f"{_nome_seguro_usuario(user_nome)}_{stamp}_"
    modelo = os.path.join(_DIR_DOWNLOADS, prefixo + f"%(title).60s [%(id)s]-{pedido_id}.%(ext)s")
    ffmpeg = tem_ffmpeg()
    if formato == "unico":
        return {"formato_ytdlp": "b", "modelo": modelo, "pos": [],
                "converter": False, "mesclar": False}
    if formato == "audio_orig":
        return {"formato_ytdlp": "ba/b", "modelo": modelo, "pos": [],
                "converter": False, "mesclar": False}
    if formato == "audio_mp3":
        if not ffmpeg:
            return {"formato_ytdlp": "ba/b", "modelo": modelo, "pos": [],
                    "converter": False, "mesclar": False}
        return {"formato_ytdlp": "bestaudio/best", "modelo": modelo,
                "pos": [{"key": "FFmpegExtractAudio",
                         "preferredcodec": "mp3",
                         "preferredquality": "192"}],
                "converter": True, "mesclar": False}
    if formato == "medio_mp4":
        if not ffmpeg:
            return {"formato_ytdlp": "b[height<=720]/b", "modelo": modelo,
                    "pos": [], "converter": False, "mesclar": False}
        return {"formato_ytdlp": "bv*[height<=720]+ba/b[height<=720]/b",
                "modelo": modelo, "pos": [],
                "converter": False, "mesclar": True}
    if not ffmpeg:
        return {"formato_ytdlp": "b", "modelo": modelo, "pos": [],
                "converter": False, "mesclar": False}
    return {"formato_ytdlp": "bv*+ba/b", "modelo": modelo, "pos": [],
            "converter": False, "mesclar": True}


def obter_informacoes(url):
    """EN: Title/uploader/duration without downloading. PT-BR: título/autor/
    duração sem baixar. Devolve dict (fail-soft: {})."""
    try:
        url_ok = validar_url(url)
        if not url_ok:
            return {}
        try:
            import yt_dlp
            opcoes = {"quiet": True, "no_warnings": True, "noplaylist": True,
                      "socket_timeout": 20}
            with yt_dlp.YoutubeDL(opcoes) as cliente:
                info = cliente.extract_info(url_ok, download=False)
            if not info:
                return {}
            try:
                dur = int(info.get("duration") or 0)
            except Exception:
                dur = 0
            return {"titulo": str(info.get("title") or "")[:300],
                    "autor": str(info.get("uploader") or info.get("channel") or "")[:150],
                    "duracao_s": dur,
                    "miniatura": str(info.get("thumbnail") or "")[:500],
                    "tem_progressivo": tem_progressivo(info)}
        except Exception:
            pass
        except Exception:
            pass
        try:
            proc = subprocess.run(
                ["yt-dlp", "--no-playlist", "--print",
                 "%(title)s ||| %(uploader)s ||| %(duration)s ||| "
                 "%(thumbnail)s",
                 "--no-warnings", url_ok],
                capture_output=True, text=True, timeout=30)
            texto = (proc.stdout or "").strip().split(" ||| ")
            if len(texto) >= 1 and texto[0].strip() and texto[0].strip() != "NA":
                try:
                    dur = int(float((texto[2] if len(texto) > 2 else "0") or 0))
                except Exception:
                    dur = 0
                try:
                    mini = (texto[3] if len(texto) > 3 else "").strip()
                    mini = "" if mini == "NA" else mini[:500]
                except Exception:
                    mini = ""
                return {"titulo": texto[0].strip()[:300],
                        "autor": (texto[1] if len(texto) > 1 else "").strip()[:150],
                        "duracao_s": dur,
                        "miniatura": mini}
        except Exception:
            pass
        return {}
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"obter_informacoes: {e}")
        except Exception:
            pass
        return {}


def _nome_final_esperado(pedido_id):
    """EN: Newest file for this request id. PT-BR: arquivo mais novo do pedido."""
    try:
        sufixo = f"-{pedido_id}."
        candidatos = []
        for nome in os.listdir(_DIR_DOWNLOADS):
            try:
                if sufixo in nome:
                    cheio = os.path.join(_DIR_DOWNLOADS, nome)
                    candidatos.append((os.path.getmtime(cheio), nome))
            except Exception:
                pass
        if not candidatos:
            return "", 0
        candidatos.sort()
        nome = candidatos[-1][1]
        try:
            tam = os.path.getsize(os.path.join(_DIR_DOWNLOADS, nome))
        except Exception:
            tam = 0
        return nome, int(tam or 0)
    except Exception:
        return "", 0


def _sanitizar_nome(nome):
    """EN: Basename only (traversal-safe). PT-BR: só o nome base."""
    try:
        return os.path.basename(str(nome or ""))
    except Exception:
        return ""


def limpar_parciais(pedido_id):
    """EN: Removes leftover files of a failed request. PT-BR: remove restos
    de um pedido que falhou (ex.: par .f251/.f616 sem junção)."""
    try:
        sufixo = f"-{pedido_id}."
        for nome in os.listdir(_DIR_DOWNLOADS):
            try:
                if sufixo in nome:
                    os.remove(os.path.join(_DIR_DOWNLOADS, nome))
            except (OSError, ValueError):
                pass
        return True
    except Exception:
        return False


def extrair_progresso_linha(linha):
    """EN: Parses a yt-dlp --newline progress line. PT-BR: lê uma linha de
    progresso do yt-dlp (`[download] 42.1% of ~5.00MiB at 1.00MiB/s ETA
    00:03`). Devolve dict (vazio se não for progresso)."""
    try:
        texto = str(linha or "")
        m = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%\s+of\s+(\S+)"
                      r"(?:\s+at\s+(\S+))?(?:\s+ETA\s+(\S+))?", texto)
        if not m:
            return {}
        try:
            pct = float(m.group(1)) / 100.0
        except (TypeError, ValueError):
            pct = 0.0
        return {"pct": max(0.0, min(1.0, pct)), "total_txt": m.group(2) or "",
                "vel": m.group(3) or "", "eta": m.group(4) or ""}
    except Exception:
        return {}
def tem_edge():
    """EN: Neural TTS available (Microsoft Edge, no key). PT-BR: voz
    neural disponível (Edge da Microsoft, sem chave).
    EASTER EGG — NÃO DOCUMENTAR."""
    try:
        import edge_tts  # noqa: F401
        return True
    except Exception:
        return False


def _voz_edge_id(voz):
    """EN: Voice id for M/F. PT-BR: id da voz masculina/feminina.
    EASTER EGG — NÃO DOCUMENTAR."""
    try:
        v = (voz or "F").strip().upper()
        for sigla, vid, _rot in VOZES_FALA:
            if sigla == v:
                return vid
    except Exception:
        pass
    return "pt-BR-FranciscaNeural"


def _formato_e_voz(formato):
    """EN: Splits `fala_mp3_antonio` into (base, voice). PT-BR: separa
    `fala_mp3_antonio` em (base, voz). EASTER EGG — NÃO DOCUMENTAR."""
    try:
        f = (formato or "").strip().lower()
        if f.startswith("fala_wav"):
            base = "fala_wav"
        else:
            base = "fala_mp3"
        for sigla, vid, _rot in VOZES_FALA:
            try:
                nome = str(vid or "").split("-")[-1].lower().replace(
                    "neural", "").replace("multilingual", "")
                if nome and nome in f:
                    return base, sigla
            except Exception:
                pass
        if f.endswith("_m"):
            return base, "M"
        if f.endswith("_f"):
            return base, "F"
        return base, None
    except Exception:
        return "fala_mp3", None


def tem_espeak():
    """EN: TTS engine available. PT-BR: motor de fala disponível."""
    try:
        return shutil.which("espeak") is not None
    except Exception:
        return False


def _voz_fala():
    """EN: pt-br voice if present, else fallback. PT-BR: voz pt-br se
    houver, senão a padrão."""
    try:
        proc = subprocess.run(["espeak", "--voices"], capture_output=True,
                              text=True, timeout=10)
        txt = (proc.stdout or "").lower()
        if "pt-br" in txt:
            return "pt-br"
        if "pt-pt" in txt or "portugal" in txt:
            return "pt-pt"
    except Exception:
        pass
    return ""


def sintetizar_fala(texto, pedido_id, formato="fala_mp3_F",
                    progresso_cb=None, user_nome="", voz=None,
                    motor="auto"):
    """EN: Text → audio (neural Edge pt-BR M/F first, offline espeak as
    fallback). PT-BR: texto → áudio (neural Edge pt-BR M/F primeiro,
    espeak offline como reserva). `formato` já carrega a voz
    (`fala_mp3_F`…); `voz` explícita vence. `motor`: auto/edge/espeak.
    Mesmo contrato do `baixar()`: (ok, titulo, nome_arquivo, tamanho,
    mensagem). EASTER EGG — NÃO DOCUMENTAR."""
    try:
        texto = (texto or "").strip()[:FALA_MAX_CHARS]
        if len(texto) < 2:
            return False, "", "", 0, "Escreva um texto para virar áudio."
        formato_base, voz_fmt = _formato_e_voz(formato)
        voz_final = ((voz or "").strip().upper() or (voz_fmt or "F"))
        if voz_final not in _CHAVES_VOZ:
            voz_final = "F"

        def _avisar(**kwargs):
            try:
                if callable(progresso_cb):
                    progresso_cb(kwargs)
            except Exception:
                pass

        _avisar(status="iniciando", pct=0.0)
        try:
            os.makedirs(_DIR_DOWNLOADS, exist_ok=True)
        except Exception:
            pass
        try:
            from datetime import datetime as _dt
            stamp = _dt.now().strftime("%Y%m%d%H%M%S")
        except Exception:
            stamp = "semdata"
        titulo = " ".join(texto.split())[:60] or "fala"
        base = (f"{_nome_seguro_usuario(user_nome)}_{stamp}_"
                f"{titulo} audio gerado a partir de texto-{pedido_id}")
        caminho_wav = os.path.join(_DIR_DOWNLOADS, base + ".wav")
        caminho_mp3 = os.path.join(_DIR_DOWNLOADS, base + ".mp3")
        usou_edge = False
        if (motor or "auto") in ("auto", "edge") and tem_edge():
            try:
                import asyncio as _aio
                import edge_tts as _edge
                _avisar(status="baixando", pct=0.5)
                _aio.run(_edge.Communicate(
                    texto, _voz_edge_id(voz_final)).save(caminho_mp3))
                if (not os.path.isfile(caminho_mp3)
                        or os.path.getsize(caminho_mp3) < 1000):
                    raise RuntimeError("edge vazio")
                usou_edge = True
            except Exception:
                usou_edge = False
                try:
                    if os.path.isfile(caminho_mp3):
                        os.remove(caminho_mp3)
                except Exception:
                    pass
        if not usou_edge and (motor or "auto") in ("auto", "espeak"):
            if not tem_espeak():
                _avisar(status="erro")
                return False, titulo, "", 0, (
                    "Sem voz neural (falha de rede?) e sem espeak no "
                    "servidor. Peça ao administrador geral para instalar "
                    "(`sudo apt install espeak`).")
            voz_local = _voz_fala()
            cmd = ["espeak", "-s", "175", "--stdout", texto]
            if voz_local:
                cmd[1:1] = ["-v", voz_local]
            try:
                espera = 60 + len(texto) // 10
                with open(caminho_wav, "wb") as fh:
                    proc = subprocess.run(
                        cmd, stdout=fh, stderr=subprocess.PIPE,
                        timeout=espera)
                if (proc.returncode != 0
                        or not os.path.isfile(caminho_wav)):
                    raise RuntimeError("espeak falhou")
            except Exception:
                try:
                    if os.path.isfile(caminho_wav):
                        os.remove(caminho_wav)
                except Exception:
                    pass
                _avisar(status="erro")
                return False, titulo, "", 0, (
                    "Não foi possível gerar o áudio do texto.")
        if not usou_edge and not os.path.isfile(caminho_wav):
            _avisar(status="erro")
            return False, titulo, "", 0, (
                "Não foi possível gerar o áudio do texto.")
        _avisar(status="processando", pct=1.0)
        nome_final = base + ".wav"
        if formato_base != "fala_wav":
            if usou_edge:
                nome_final = base + ".mp3"
            else:
                try:
                    ffmpeg = shutil.which("ffmpeg") or ""
                    if not ffmpeg:
                        raise RuntimeError("sem ffmpeg")
                    proc = subprocess.run(
                        [ffmpeg, "-y", "-v", "error", "-i", caminho_wav,
                         "-codec:a", "libmp3lame", "-b:a", "128k",
                         caminho_mp3],
                        capture_output=True, text=True, timeout=300)
                    if (proc.returncode != 0
                            or not os.path.isfile(caminho_mp3)):
                        raise RuntimeError("conversão falhou")
                    try:
                        os.remove(caminho_wav)
                    except Exception:
                        pass
                    nome_final = base + ".mp3"
                except Exception:
                    nome_final = base + ".wav"
        elif usou_edge:
            try:
                ffmpeg = shutil.which("ffmpeg") or ""
                if not ffmpeg:
                    raise RuntimeError("sem ffmpeg")
                proc = subprocess.run(
                    [ffmpeg, "-y", "-v", "error", "-i", caminho_mp3,
                     "-codec:a", "pcm_s16le", caminho_wav],
                    capture_output=True, text=True, timeout=300)
                if (proc.returncode != 0
                        or not os.path.isfile(caminho_wav)):
                    raise RuntimeError("conversão falhou")
                try:
                    os.remove(caminho_mp3)
                except Exception:
                    pass
                nome_final = base + ".wav"
            except Exception:
                nome_final = base + ".mp3"
        try:
            tam = int(os.path.getsize(
                os.path.join(_DIR_DOWNLOADS, nome_final)) or 0)
        except Exception:
            tam = 0
        return True, titulo, nome_final, tam, ""
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"sintetizar_fala: {e}")
        except Exception:
            pass
        return False, "", "", 0, "Não foi possível gerar o áudio do texto."


def _mensagem_erro(detalhe):
    """EN: Friendly message for known failures. PT-BR: mensagem amigável
    para falhas conhecidas (403 = limite temporário do YouTube)."""
    try:
        txt = str(detalhe or "")
        baixo = txt.lower()
        if "403" in baixo or "forbidden" in baixo:
            return ("O YouTube recusou temporariamente (limite de "
                    "downloads). Aguarde alguns minutos e tente de novo.")
        if "private" in baixo or "privado" in baixo:
            return "Este vídeo é privado."
        if "unavailable" in baixo or "indispon" in baixo:
            return "Vídeo indisponível (removido ou restrito)."
        if "timeout" in baixo or "timed out" in baixo:
            return "O download demorou demais e foi interrompido."
        detalhe = txt.strip()[-200:]
        return ("Não foi possível baixar. Confira o link "
                f"(detalhe: {detalhe})" if detalhe
                else "Não foi possível baixar. Confira o link.")
    except Exception:
        return "Não foi possível baixar. Confira o link."


def tem_progressivo(info):
    """EN: True if any format carries audio+video in one file. PT-BR:
    verdadeiro se algum formato traz áudio+vídeo num arquivo só."""
    try:
        for f in (info or {}).get("formats") or []:
            try:
                if (f.get("vcodec") or "none") != "none" and \
                        (f.get("acodec") or "none") != "none":
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False


def opcoes_de_formatos(info, com_ffmpeg=None):
    """EN: Every usable format of this video (offline-friendly). PT-BR:
    TODOS os formatos aproveitáveis deste vídeo. Vídeo: um item por
    resolução/extensão (com ffmpeg junta o melhor áudio; sem, só arquivo
    único). Áudio: um por formato (MP3 só com ffmpeg, via conversão).
    Cada item: {id, rotulo, spec, audio, converter, mesclar}."""
    try:
        if com_ffmpeg is None:
            com_ffmpeg = tem_ffmpeg()
        formatos = (info or {}).get("formats") or []
        opcoes = []
        vistos = set()
        videos = []
        audios = []
        for f in formatos:
            try:
                ext = str(f.get("ext") or "").lower()
                if ext in ("mhtml", ""):
                    continue
                v = (f.get("vcodec") or "none") != "none"
                a = (f.get("acodec") or "none") != "none"
                if not v and not a:
                    continue
                try:
                    h = int(f.get("height") or 0)
                except (TypeError, ValueError):
                    h = 0
                try:
                    abr = int(float(f.get("abr") or f.get("tbr") or 0) or 0)
                except (TypeError, ValueError):
                    abr = 0
                try:
                    tam = f.get("filesize") or f.get("filesize_approx") or 0
                    tam = int(tam or 0)
                except (TypeError, ValueError):
                    tam = 0
                except Exception:
                    tam = 0
                fid = str(f.get("format_id") or "")
                if not fid:
                    continue
                chave = (h if v else 0, ext, abr, fid)
                if chave in vistos:
                    continue
                vistos.add(chave)
                (videos if v else audios).append({
                    "fid": fid, "ext": ext, "h": h, "abr": abr,
                    "tam": tam, "a": a})
            except Exception:
                pass
        try:
            from mod_video.bd_manipulador import _tamanho_legivel as _tam_leg
            _tam_leg(1)
        except Exception:
            def _tam_leg(n):
                try:
                    n = float(n or 0)
                    for u in ("B", "KB", "MB", "GB"):
                        if n < 1024 or u == "GB":
                            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
                        n /= 1024.0
                    return f"{n:.1f} GB"
                except Exception:
                    return ""

        def _rot_tam(tam):
            try:
                txt = _tam_leg(tam) if tam else ""
                return f" ~{txt}" if txt and txt != "0 B" else ""
            except Exception:
                return ""

        if com_ffmpeg:
            for v in sorted(videos, key=lambda d: (-d["h"], d["ext"])):
                if v["a"]:
                    rot = (f"Vídeo {v['h']}p {v['ext'].upper()} "
                           f"(com áudio){_rot_tam(v['tam'])}")
                    spec = v["fid"]
                    mesclar = False
                else:
                    rot = (f"Vídeo {v['h']}p {v['ext'].upper()} "
                           f"(+ áudio){_rot_tam(v['tam'])}")
                    spec = f"{v['fid']}+bestaudio/b"
                    mesclar = True
                opcoes.append({
                    "id": f"f_{v['fid']}", "rotulo": rot, "spec": spec,
                    "audio": False, "converter": False, "mesclar": mesclar})
            for a in sorted(audios, key=lambda d: -d["abr"]):
                rot = f"Áudio {a['ext'].upper()} (original)"
                if a["abr"]:
                    rot += f" {a['abr']}k"
                rot += _rot_tam(a["tam"])
                opcoes.append({
                    "id": f"f_{a['fid']}", "rotulo": rot,
                    "spec": a["fid"], "audio": True,
                    "converter": False, "mesclar": False})
            if audios or videos:
                opcoes.append({
                    "id": "a_mp3", "rotulo": "Somente áudio (MP3)",
                    "spec": "bestaudio/best", "audio": True,
                    "converter": True, "mesclar": False})
        else:
            for v in sorted(videos, key=lambda d: (-d["h"], d["ext"])):
                rot = f"Vídeo {v['h']}p {v['ext'].upper()}"
                if v["a"]:
                    rot += " (arquivo único)"
                else:
                    rot += " (só vídeo, sem áudio)"
                rot += _rot_tam(v["tam"])
                opcoes.append({
                    "id": f"f_{v['fid']}", "rotulo": rot, "spec": v["fid"],
                    "audio": False, "converter": False, "mesclar": False})
            for a in sorted(audios, key=lambda d: -d["abr"]):
                rot = f"Áudio {a['ext'].upper()} (original)"
                if a["abr"]:
                    rot += f" {a['abr']}k"
                rot += _rot_tam(a["tam"])
                opcoes.append({
                    "id": f"f_{a['fid']}", "rotulo": rot,
                    "spec": f"{a['fid']}/ba/b", "audio": True,
                    "converter": False, "mesclar": False})
        return opcoes
    except Exception:
        return []


def exige_ffmpeg(info):
    """EN: True when merging is unavoidable (no single-file format). PT-BR:
    verdadeiro quando só juntando (sem arquivo único)."""
    try:
        return not tem_progressivo(info)
    except Exception:
        return False


def extrair_verificacao(url):
    """EN: What this link holds (blocking — call via run.io_bound). PT-BR:
    o que este link contém. Vídeo único: título/autor/duração + opções
    reais de formato. Playlist: entradas (título/duração/url, até 50).
    Devolve dict com `tipo` (video|playlist|"")."""
    saida = {"tipo": "", "titulo": "", "autor": "", "duracao_s": 0,
             "entradas": [], "formatos": [], "total": 0, "limitado": False,
             "miniatura": ""}
    try:
        url_ok = validar_url(url)
        if not url_ok:
            return saida
        try:
            import yt_dlp
            opcoes = {"quiet": True, "no_warnings": True,
                      "socket_timeout": 20}
            with yt_dlp.YoutubeDL(opcoes) as cliente:
                info = cliente.extract_info(url_ok, download=False,
                                            process=True)
        except Exception:
            return saida
        if not info:
            return saida
        if (info.get("_type") or "") == "playlist":
            entradas = []
            try:
                brutas = list(info.get("entries") or [])
            except Exception:
                brutas = []
            total = len(brutas)
            for e in brutas[:50]:
                try:
                    if not e:
                        continue
                    eid = str(e.get("id") or "")
                    eurl = str(e.get("webpage_url") or e.get("url") or "")
                    if eurl and "://" not in eurl and eid:
                        eurl = f"https://www.youtube.com/watch?v={eid}"
                    try:
                        dur = int(e.get("duration") or 0)
                    except (TypeError, ValueError):
                        dur = 0
                    entradas.append({
                        "titulo": str(e.get("title") or eid or "Sem título")[:200],
                        "duracao_s": dur, "url": eurl})
                except Exception:
                    pass
            saida.update({"tipo": "playlist",
                          "titulo": str(info.get("title") or "")[:200],
                          "entradas": entradas, "total": total,
                          "limitado": total > len(entradas)})
            return saida
        try:
            dur = int(info.get("duration") or 0)
        except (TypeError, ValueError):
            dur = 0
        try:
            max_h = 0
            for f in info.get("formats") or []:
                try:
                    if (f.get("vcodec") or "none") != "none":
                        max_h = max(max_h, int(f.get("height") or 0))
                except (TypeError, ValueError):
                    pass
                except Exception:
                    pass
        except Exception:
            max_h = 0
        saida.update({"tipo": "video",
                      "titulo": str(info.get("title") or "")[:300],
                      "autor": str(info.get("uploader")
                                   or info.get("channel") or "")[:150],
                      "duracao_s": dur,
                      "miniatura": str(info.get("thumbnail") or "")[:500],
                      "formatos": opcoes_de_formatos(info),
                      "max_altura": max_h,
                      "tem_progressivo": tem_progressivo(info)})
        return saida
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"extrair_verificacao: {e}")
        except Exception:
            pass
        return saida


def _yt_dlp_cmd():
    """EN: CLI binary or `python -m yt_dlp` fallback. PT-BR: binário da CLI
    ou `python -m yt_dlp` (o pacote basta, sem instalar binário)."""
    try:
        if shutil.which("yt-dlp"):
            return ["yt-dlp"]
        return [sys.executable, "-m", "yt_dlp"]
    except Exception:
        return ["yt-dlp"]


def mime_por_nome(nome):
    """EN: MIME type by extension (for the player). PT-BR: MIME pela
    extensão (para o player)."""
    try:
        ext = os.path.splitext(str(nome or ""))[1].lower()
        return {".mp4": "video/mp4", ".webm": "video/webm",
                ".mov": "video/quicktime", ".mkv": "video/x-matroska",
                ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
                ".ogg": "audio/ogg", ".oga": "audio/ogg",
                ".wav": "audio/wav", ".opus": "audio/opus"}.get(ext, "")
    except Exception:
        return ""


def eh_audio(nome):
    """EN: True if the file is audio-only. PT-BR: verdadeiro se só áudio."""
    try:
        return (mime_por_nome(nome) or "").startswith("audio/")
    except Exception:
        return False


def baixar(url, formato, pedido_id, progresso_cb=None, spec=None,
           converter=None, mesclar=None, user_nome=""):
    """EN: Downloads the video/audio (blocking — call via run.io_bound).
    PT-BR: baixa o vídeo/áudio (bloqueante — chamar via run.io_bound).
    `progresso_cb` recebe dicts (`baixado/total/vel/eta/pct/status`) — o
    hook do yt-dlp (por bytes) ou o parse da CLI. `spec`/`converter`/
    `mesclar` vêm da verificação (formato real escolhido); sem eles valem
    os presets de `_opcoes_saida`. O arquivo leva o dono no nome. Devolve
    (ok, titulo, nome_arquivo, tamanho, mensagem)."""
    try:
        url_ok = validar_url(url)
        if not url_ok:
            return False, "", "", 0, "Link inválido: use um link http(s)."
        if formato not in FORMATOS_VALIDOS:
            formato = "melhor_mp4"
        conf = _opcoes_saida(formato, pedido_id, user_nome)
        if spec:
            conf["formato_ytdlp"] = str(spec)[:200]
        if converter is not None:
            conf["converter"] = bool(converter)
            conf["pos"] = ([{"key": "FFmpegExtractAudio",
                              "preferredcodec": "mp3",
                              "preferredquality": "192"}]
                           if converter and tem_ffmpeg() else [])
        if mesclar is not None:
            conf["mesclar"] = bool(mesclar)
        titulo = ""
        info_previa = {}

        def _avisar(**kwargs):
            try:
                if callable(progresso_cb):
                    progresso_cb(kwargs)
            except Exception:
                pass

        try:
            info_previa = obter_informacoes(url_ok) or {}
            titulo = str(info_previa.get("titulo") or "")
        except Exception:
            titulo = ""
        precisa_juntar = bool(conf.get("mesclar") or conf.get("converter"))
        if not tem_ffmpeg() and precisa_juntar and \
                "tem_progressivo" in info_previa and \
                exige_ffmpeg(info_previa):
            try:
                limpar_parciais(pedido_id)
            except Exception:
                pass
            _avisar(status="erro")
            return False, titulo, "", 0, (
                "Este vídeo só existe em trilhas separadas e o servidor não "
                "tem ffmpeg para juntar. Peça ao administrador geral "
                "(instalação/ativação) para rodar "
                "`instalar_externos.py --ffmpeg`.")

        _avisar(status="iniciando", pct=0.0)
        erro = ""
        cancelado = False
        try:
            import yt_dlp

            def _hook(d):
                try:
                    if _CANCELADOS and pedido_id in _CANCELADOS:
                        raise DownloadCancelado()
                    estado = str((d or {}).get("status") or "")
                    if estado == "downloading":
                        _avisar(status="baixando",
                                baixado=(d or {}).get("downloaded_bytes"),
                                total=(d or {}).get("total_bytes")
                                or (d or {}).get("total_bytes_estimate"),
                                vel=(d or {}).get("speed"),
                                eta=(d or {}).get("eta"))
                    elif estado == "finished":
                        _avisar(status="processando", pct=1.0)
                except DownloadCancelado:
                    raise
                except Exception:
                    pass

            opcoes = {"format": conf["formato_ytdlp"],
                      "outtmpl": conf["modelo"],
                      "noplaylist": True, "quiet": True, "no_warnings": True,
                      "socket_timeout": 60,
                      "merge_output_format": ("mp4" if conf.get("mesclar")
                                              else None),
                      "postprocessors": conf["pos"],
                      "progress_hooks": [_hook],
                      "newline": True,
                      "retries": 2}
            opcoes = {k: v for k, v in opcoes.items() if v is not None}
            erro = ""
            try:
                with yt_dlp.YoutubeDL(opcoes) as cliente:
                    cliente.download([url_ok])
            except DownloadCancelado:
                raise
            except Exception as e1:
                # 403 = limite temporário: espera e tenta 1x de novo antes
                # de cair no fallback/desistir.
                if "403" in str(e1 or "") or "orbidden" in str(e1 or ""):
                    try:
                        _avisar(status="aguardando",
                                detalhe="limite do YouTube, nova tentativa")
                        import time as _tt
                        _tt.sleep(15)
                        if pedido_id in _CANCELADOS:
                            raise DownloadCancelado()
                        with yt_dlp.YoutubeDL(opcoes) as cliente2:
                            cliente2.download([url_ok])
                        erro = ""
                    except DownloadCancelado:
                        raise
                    except Exception as e2:
                        erro = str(e2)
                else:
                    erro = str(e1)
                if erro:
                    try:
                        lg = _log()
                        if lg is not None:
                            lg.warning(f"baixar via pacote falhou: {erro}")
                    except Exception:
                        pass
        except ImportError as e:
            erro = f"import: {e}"
        except DownloadCancelado:
            cancelado = True
        except Exception as e:
            if pedido_id in _CANCELADOS or \
                    "cancelado" in str(e or "").lower():
                cancelado = True
            else:
                erro = str(e)
                try:
                    lg = _log()
                    if lg is not None:
                        lg.warning(f"baixar via pacote falhou: {e}")
                except Exception:
                    pass
        if cancelado:
            try:
                limpar_parciais(pedido_id)
            except Exception:
                pass
            _limpar_cancelamento(pedido_id)
            _avisar(status="erro")
            return False, titulo, "", 0, "Download cancelado."
        if erro:
            try:
                comando = _yt_dlp_cmd() + ["--no-playlist", "--newline",
                                           "--progress", "-f",
                                           conf["formato_ytdlp"], "-o",
                                           conf["modelo"]]
                if conf.get("converter"):
                    comando += ["-x", "--audio-format", "mp3",
                                "--audio-quality", "192K"]
                elif conf.get("mesclar"):
                    comando += ["--merge-output-format", "mp4"]
                comando.append(url_ok)
                proc = subprocess.Popen(comando, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True)
                _PROCESSOS[pedido_id] = proc
                saida_cli = []
                try:
                    for linha in proc.stdout:
                        try:
                            if pedido_id in _CANCELADOS:
                                try:
                                    proc.kill()
                                except Exception:
                                    pass
                                break
                            saida_cli.append(linha)
                            if len(saida_cli) > 50:
                                del saida_cli[0]
                            info_lin = extrair_progresso_linha(linha)
                            if info_lin:
                                _avisar(status="baixando",
                                        pct=info_lin.get("pct"),
                                        total_txt=info_lin.get("total_txt"),
                                        vel=info_lin.get("vel"),
                                        eta=info_lin.get("eta"))
                        except Exception:
                            pass
                    rc = proc.wait(timeout=900)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    raise
                finally:
                    _PROCESSOS.pop(pedido_id, None)
                if pedido_id in _CANCELADOS:
                    try:
                        limpar_parciais(pedido_id)
                    except Exception:
                        pass
                    _limpar_cancelamento(pedido_id)
                    _avisar(status="erro")
                    return False, titulo, "", 0, "Download cancelado."
                if rc != 0:
                    detalhe = "".join(saida_cli)[-400:]
                    try:
                        limpar_parciais(pedido_id)
                    except Exception:
                        pass
                    _avisar(status="erro")
                    if not tem_ffmpeg() and \
                            "not available" in detalhe.lower():
                        return False, titulo, "", 0, (
                            "Este vídeo só existe em trilhas separadas e o "
                            "servidor não tem ffmpeg para juntar. Peça ao "
                            "administrador geral (instalação/ativação) para "
                            "rodar `instalar_externos.py --ffmpeg`.")
                    return False, titulo, "", 0, _mensagem_erro(detalhe)
            except FileNotFoundError:
                _avisar(status="erro")
                return False, titulo, "", 0, (
                    "Baixador indisponível (pacote yt-dlp não instalado). "
                    "Avise o administrador.")
            except subprocess.TimeoutExpired:
                try:
                    limpar_parciais(pedido_id)
                except Exception:
                    pass
                _avisar(status="erro")
                return False, titulo, "", 0, (
                    "O download demorou demais e foi interrompido.")
            except Exception as e:
                try:
                    limpar_parciais(pedido_id)
                except Exception:
                    pass
                _avisar(status="erro")
                return False, titulo, "", 0, f"Falha no download: {e}"
        nome, tamanho = _nome_final_esperado(pedido_id)
        nome = _sanitizar_nome(nome)
        if not nome:
            try:
                limpar_parciais(pedido_id)
            except Exception:
                pass
            detalhe = (erro or "")[-200:]
            return False, titulo, "", 0, (
                "Download terminou sem gerar arquivo. "
                f"{detalhe}".strip())
        if not titulo:
            titulo = re.sub(r"\s*\[[^\]]*\]-\d+\.[^.]+$", "", nome)
            titulo = re.sub(r"^[A-Za-z0-9_-]{1,30}_\d{14}_", "", titulo)[:300]
        _avisar(status="concluido", pct=1.0)
        return True, titulo, nome, int(tamanho or 0), "Download concluído."
    except Exception as e:
        try:
            lg = _log()
            if lg is not None:
                lg.exception(f"baixar: {e}")
        except Exception:
            pass
        return False, "", "", 0, f"Falha no download: {e}"
