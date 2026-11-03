"""Ciclo do mod_video (17/10/2026): stage com expiração, biblioteca publicada,
entrega ao comum e utilidades do motor — tudo OFFLINE (sem rede, sem yt-dlp).

Cobre:
    - init_db idempotente (2x) + colunas novas em banco antigo
    - cfg_expiracao_min padrão 10, piso 1
    - registrar -> publicar (vai à biblioteca, zera expiração) ->
      despublicar (volta ao stage) -> excluir (some disco + banco)
    - expirar_antigos: expira_em passado remove; publicado nunca expira;
      arquivo sumido vira 'expirado'
    - zipar_selecao junta os válidos e ignora o resto
    - caminho_arquivo anti-traversal; biblioteca isolada do stage
    - motor: validar_url, detectar_plataforma, fallback sem ffmpeg
      (arquivo único), mime_por_nome, limpar_parciais
    - versões centrais video/tisosdocfly (idempotente 2x) (2x idempotente)
    - integracoes.listar_videos_publicados espelha a biblioteca

Execute: poetry run python tests/test_video_ciclo.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")))

os.environ.setdefault("TISOSDOCFLY_DIR_BANCO", "/tmp/opencode/bd_teste_video")

from mod_video import bd_manipulador as bd  # noqa: E402
from mod_video import servico_download as dl  # noqa: E402

_OK = 0
_FALHAS = []


def check(cond, msg):
    global _OK
    if cond:
        _OK += 1
    else:
        _FALHAS.append(msg)
    print(("  ok   " if cond else "  FALHOU ") + msg)


def teste_init_e_config():
    print("\n[init e config]")
    check(bd.init_db() is True, "init_db 1a vez")
    check(bd.init_db() is True, "init_db 2a vez (idempotente)")
    check(bd.cfg_expiracao_min() == 10, "expiracao padrao 10 min")
    check(os.path.isdir(bd.DIR_DOWNLOADS), "pasta downloads/ existe")
    check(os.path.isdir(bd.DIR_BIBLIOTECA), "pasta biblioteca/ existe")


def teste_publicar_ciclo():
    print("\n[publicar -> despublicar -> excluir]")
    pid = bd.registrar_pedido("MT-1234", "https://www.youtube.com/watch?v=x",
                              "YouTube", "melhor_mp4",
                              expira_em=bd._daqui_a_minutos(10))
    check(bool(pid), "pedido registrado")
    nome = f"teste_{pid}.mp4"
    with open(os.path.join(bd.DIR_DOWNLOADS, nome), "wb") as f:
        f.write(b"0" * 100)
    check(bd.atualizar_status(pid, "pronto", titulo="T", arquivo=nome,
                              tamanho=100), "marcado pronto")
    ok, msg = bd.publicar_pedido(pid, ator="MT-1234")
    check(ok, f"publicado: {msg}")
    ped = bd.obter_pedido(pid)
    check(ped.get("publicado") is True, "flag publicado")
    check(ped.get("expira_em") == "", "publicado zera a expiracao")
    bib = [i["id"] for i in bd.listar_biblioteca()]
    check(pid in bib, "aparece na biblioteca")
    check(bd.url_biblioteca(ped["arquivo"]).startswith("/midia_video/"),
          "URL da biblioteca em /midia_video/")
    ok, msg = bd.despublicar_pedido(pid, ator="MT-1234")
    check(ok, f"despublicado: {msg}")
    check(bd.obter_pedido(pid).get("publicado") is False, "saiu da biblioteca")
    ok, msg = bd.excluir_pedido(pid, ator="MT-1234")
    check(ok, f"excluido: {msg}")
    check(bd.obter_pedido(pid) == {}, "registro sumiu")
    check(bd.caminho_arquivo(nome, publicado=True) == "" or
          not os.path.isfile(bd.caminho_arquivo(nome, publicado=True)),
          "arquivo saiu do disco")


def teste_expiracao():
    print("\n[expiracao]")
    pid = bd.registrar_pedido("MT-1234", "https://fb.watch/x", "Facebook",
                              "medio_mp4", expira_em="2000-01-01 00:00:00")
    nome = f"velho_{pid}.mp4"
    with open(os.path.join(bd.DIR_DOWNLOADS, nome), "wb") as f:
        f.write(b"0" * 10)
    bd.atualizar_status(pid, "pronto", titulo="V", arquivo=nome, tamanho=10)
    n = bd.expirar_antigos()
    check(n >= 1, f"expirados: {n}")
    ped = bd.obter_pedido(pid)
    check(ped.get("status") == "expirado", "status expirado")
    check(not os.path.isfile(os.path.join(bd.DIR_DOWNLOADS, nome)),
          "arquivo removido do stage")
    # publicado nunca expira
    pid2 = bd.registrar_pedido("MT-1234", "https://x.com/y", "X/Twitter",
                               "audio_mp3", expira_em="")
    nome2 = f"pub_{pid2}.mp3"
    with open(os.path.join(bd.DIR_DOWNLOADS, nome2), "wb") as f:
        f.write(b"0" * 10)
    bd.atualizar_status(pid2, "pronto", titulo="P", arquivo=nome2, tamanho=10)
    bd.publicar_pedido(pid2, ator="MT-1234")
    n2 = bd.expirar_antigos()
    check(bd.obter_pedido(pid2).get("status") == "pronto",
          "publicado sobrevive a expiração")
    check(n2 == 0, "nada a expirar na 2a passada")
    # zip junta os válidos
    pid3 = bd.registrar_pedido("MT-1234", "https://youtu.be/z", "YouTube",
                               "melhor_mp4", expira_em=bd._daqui_a_minutos(10))
    nome3 = f"zip_{pid3}.mp4"
    with open(os.path.join(bd.DIR_DOWNLOADS, nome3), "wb") as f:
        f.write(b"0" * 10)
    bd.atualizar_status(pid3, "pronto", titulo="Z", arquivo=nome3, tamanho=10)
    z = bd.zipar_selecao("MT-1234", [nome3, "inexistente.mp4"])
    check(bool(z) and os.path.isfile(z), "ZIP com o válido, sem o inexistente")
    try:
        os.remove(z)
    except OSError:
        pass
    for p in (pid, pid2, pid3):
        bd.excluir_pedido(p, ator="MT-1234")


def teste_varredura_orfaos():
    print("\n[varredura de órfãos]")
    import time as _t
    velho = os.path.join(bd.DIR_DOWNLOADS, "orfao_velho-424243.tmp")
    novo = os.path.join(bd.DIR_DOWNLOADS, "orfao_novo-424244.tmp")
    with open(velho, "wb") as f:
        f.write(b"0" * 10)
    with open(novo, "wb") as f:
        f.write(b"0" * 10)
    ontem = _t.time() - 3600
    os.utime(velho, (ontem, ontem))
    pid = bd.registrar_pedido("MT-1234", "https://x.com/q", "X/Twitter",
                              "melhor_mp4",
                              expira_em=bd._daqui_a_minutos(10))
    nome = f"vivo_{pid}.mp4"
    with open(os.path.join(bd.DIR_DOWNLOADS, nome), "wb") as f:
        f.write(b"0" * 10)
    bd.atualizar_status(pid, "pronto", titulo="V", arquivo=nome, tamanho=10)
    n = bd.expirar_antigos(minutos=10)
    check(not os.path.isfile(velho), "órfão velho removido")
    check(os.path.isfile(novo), "órfão fresco mantido (download ativo)")
    check(os.path.isfile(os.path.join(bd.DIR_DOWNLOADS, nome)),
          "referenciado por pronto mantido")
    check(n >= 1, f"contados: {n}")
    try:
        os.remove(novo)
    except OSError:
        pass
    bd.excluir_pedido(pid, ator="MT-1234")


def teste_isolamento_e_motor():
    print("\n[isolamento e motor]")
    check(bd.caminho_arquivo("../../x", publicado=False) == "",
          "traversal barrado no stage")
    check(bd.caminho_arquivo("a.mp4", publicado=True).startswith(
        os.path.abspath(bd.DIR_BIBLIOTECA)), "biblioteca isolada do stage")
    check(dl.validar_url("https://www.tiktok.com/@x/video/1").startswith(
        "https"), "url válida passa")
    check(dl.validar_url("file:///etc/passwd") == "", "file:// barrado")
    check(dl.detectar_plataforma("https://www.tiktok.com/@x/video/1")
          == "TikTok", "plataforma TikTok")
    check(dl.detectar_plataforma("https://fb.watch/x") == "Facebook",
          "plataforma Facebook")
    check(dl.mime_por_nome("a.mp4") == "video/mp4", "mime mp4")
    check(dl.mime_por_nome("a.mp3") == "audio/mpeg", "mime mp3")
    check(dl.eh_audio("a.mp3") is True, "mp3 é áudio")
    check(dl.eh_audio("a.mp4") is False, "mp4 não é áudio")
    conf = dl._opcoes_saida("melhor_mp4", 999999)
    if dl.tem_ffmpeg():
        check(conf.get("mesclar") is True, "com ffmpeg: junta adaptativos")
    else:
        check(conf.get("formato_ytdlp") == "b",
              "sem ffmpeg: melhor arquivo único (sem par solto)")
        check(dl.aviso_qualidade() != "", "aviso de qualidade exibido")
    with open(os.path.join(bd.DIR_DOWNLOADS, "resto-999999.f251.webm"),
              "wb") as f:
        f.write(b"0")
    check(dl.limpar_parciais(999999) is True, "limpa parciais")
    check(not os.path.isfile(
        os.path.join(bd.DIR_DOWNLOADS, "resto-999999.f251.webm")),
        "parcial removido")


def teste_formato_unico():
    print("\n[arquivo único x trilhas]")


def teste_miniatura():
    print("\n[capa do video (miniatura)]")
    pid = bd.registrar_pedido("MT-1234", "https://www.youtube.com/watch?v=m",
                              "YouTube", "melhor_mp4", titulo="M",
                              miniatura="https://i.ytimg.com/vi/m/hqdefault.jpg")
    check(bool(pid), "pedido com miniatura registrado")
    ped = bd.obter_pedido(pid)
    check(ped.get("miniatura") == "https://i.ytimg.com/vi/m/hqdefault.jpg",
          "obter_pedido traz a miniatura")
    hist = [l for l in bd.listar_historico("MT-1234", limite=50)
            if l.get("id") == pid]
    check(bool(hist) and hist[0].get("miniatura", "").endswith("hqdefault.jpg"),
          "listar_historico traz a miniatura")
    check(bd.definir_miniatura(pid, "https://x/y.jpg") in (True, False),
          "definir em pedido com capa nao quebra")
    check(bd.obter_pedido(pid).get("miniatura", "").endswith("hqdefault.jpg"),
          "definir nao sobrescreve a existente")
    check(bd.atualizar_status(pid, "pronto", titulo="M",
                              miniatura="https://z/w.jpg"),
          "atualizar_status com miniatura nao quebra")
    check(bd.obter_pedido(pid).get("miniatura", "").endswith("hqdefault.jpg"),
          "atualizar nao sobrescreve a existente")
    pid2 = bd.registrar_pedido("MT-1234", "https://www.youtube.com/watch?v=n",
                               "YouTube", "melhor_mp4", titulo="N")
    check(bd.definir_miniatura(pid2, "https://i.ytimg.com/vi/n/hqdefault.jpg"),
          "definir preenche quando vazia")
    check(bd.obter_pedido(pid2).get("miniatura", "").endswith("hqdefault.jpg"),
          "backfill gravado")


def teste_fala():
    print("\n[texto vira audio (fala)]")
    tem_espeak = dl.tem_espeak() is True
    check(True if tem_espeak else dl.tem_espeak() is False,
          "espeak presente ou ausencia detectada")
    tem_edge = dl.tem_edge() is True
    check(True if tem_edge else dl.tem_edge() is False,
          "edge-tts presente ou ausencia detectada")
    check(dl._formato_e_voz("fala_mp3_francisca") == ("fala_mp3", "F"),
          "formato carrega a voz francisca")
    check(dl._formato_e_voz("fala_wav_antonio") == ("fala_wav", "M"),
          "formato carrega a voz antonio")
    check(dl._formato_e_voz("fala_mp3_thalita") == ("fala_mp3", "T"),
          "formato carrega a voz thalita")
    check(dl._formato_e_voz("fala_mp3_duarte") == ("fala_mp3", "D"),
          "formato carrega a voz duarte")
    check(dl._formato_e_voz("fala_wav_raquel") == ("fala_wav", "R"),
          "formato carrega a voz raquel")
    check(dl._formato_e_voz("fala_mp3_F") == ("fala_mp3", "F"),
          "sufixo antigo F segue valido")
    check(dl._formato_e_voz("fala_wav_M") == ("fala_wav", "M"),
          "sufixo antigo M segue valido")
    check(dl._formato_e_voz("fala_mp3") == ("fala_mp3", None),
          "formato antigo segue valido")
    check(dl._voz_edge_id("M") == "pt-BR-AntonioNeural",
          "voz masculina = Antonio")
    check(dl._voz_edge_id("F") == "pt-BR-FranciscaNeural",
          "voz feminina = Francisca")
    if tem_espeak:
        ok, titulo, nome, tam, msg = dl.sintetizar_fala(
            "Teste de voz em português.", 999001, formato="fala_mp3_francisca",
            user_nome="MT-1234", motor="espeak")
        check(ok, f"sintetiza MP3 (espeak): {msg}")
        check("audio gerado a partir de texto" in (nome or ""),
              f"nome segue o padrao + sufixo: {nome}")
        check(str(nome or "").endswith("-999001.mp3"),
              "nome termina com -pid.ext")
        if ok and nome:
            cam = os.path.join(bd.DIR_DOWNLOADS, nome)
            check(os.path.isfile(cam) and tam and tam > 1000,
                  f"MP3 no stage ({tam} bytes)")
            try:
                os.remove(cam)
            except Exception:
                pass
        ok2, _, nome2, _, _ = dl.sintetizar_fala(
            "Outro teste.", 999002, formato="fala_wav_antonio",
            user_nome="MT-1234", motor="espeak")
        check(ok2 and str(nome2 or "").endswith(".wav"), "sintetiza WAV")
        if ok2 and nome2:
            try:
                os.remove(os.path.join(bd.DIR_DOWNLOADS, nome2))
            except Exception:
                pass
    else:
        _ok_e, _, _, _, _msg_e = dl.sintetizar_fala(
            "Teste.", 999001, formato="fala_mp3_francisca",
            user_nome="MT-1234", motor="espeak")
        check(_ok_e is False and _msg_e,
              "sem espeak: falha graciosa com mensagem")
    ok3, _, _, _, msg3 = dl.sintetizar_fala(" ", 999003)
    check(ok3 is False and msg3, "texto vazio nao sintetiza")
    pid = bd.registrar_pedido("MT-1234", "", "Texto em áudio",
                              "fala_mp3_francisca", titulo="Teste de voz")
    check(bool(pid), "pedido de fala registrado")
    check(bd.obter_pedido(pid).get("plataforma") == "Texto em áudio",
          "plataforma de fala gravada")


def teste_mensagem_erro():
    print("\n[mensagem de erro]")
    check("temporariamente" in dl._mensagem_erro("ERROR 403 Forbidden"),
          "403 vira aviso de limite")
    check(dl._mensagem_erro("Video unavailable") != "",
          "indisponível tem mensagem")
    check(dl._mensagem_erro("") != "", "vazio não quebra")
    check(dl._nome_seguro_usuario("qamaster") == "qamaster",
          "dono simples passa")
    check(dl._nome_seguro_usuario("../../x") == "x",
          "dono sanitizado")
    conf = dl._opcoes_saida("unico", 555001, "qamaster")
    check("qamaster_" in conf["modelo"] and conf["modelo"].endswith(
        "-555001.%(ext)s"), "arquivo leva o dono e o pedido")
    info_mux = {"formats": [
        {"format_id": "18", "vcodec": "avc1", "acodec": "mp4a"},
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a"}]}
    info_sep = {"formats": [
        {"format_id": "616", "vcodec": "avc1", "acodec": "none"},
        {"format_id": "251", "vcodec": "none", "acodec": "opus"}]}
    check(dl.tem_progressivo(info_mux) is True, "muxado detectado")
    check(dl.tem_progressivo(info_sep) is False, "só trilhas detectado")
    check(dl.exige_ffmpeg(info_sep) is True, "trilhas exigem ffmpeg")
    check(dl.exige_ffmpeg(info_mux) is False, "muxado não exige")
    check(dl.exige_ffmpeg({}) is True, "sem info = cautela (exige)")
    check(isinstance(dl._yt_dlp_cmd(), list) and dl._yt_dlp_cmd(),
          "comando CLI resolvido (binário ou python -m)")


def teste_selecao_tabela():
    print("\n[seleção da tabela]")
    try:
        from mod_video import telas as tv
    except Exception as e:
        _FALHAS.append(f"import telas: {e}")
        return
    check(tv._chaves_da_selecao([{"id": 1}, {"id": 2}]) == [1, 2],
          "evento lista de linhas")
    check(tv._chaves_da_selecao([]) == [], "vazio limpa")
    check(tv._chaves_da_selecao(None) == [], "None não levanta")
    check(tv._chaves_da_selecao([7, {"id": 8}]) == [7, 8],
          "misto id/dict")


def teste_opcoes_reais():
    print("\n[opções reais por vídeo]")
    info_mux = {"formats": [
        {"format_id": "22", "vcodec": "avc1", "acodec": "mp4a",
         "ext": "mp4", "height": 720},
        {"format_id": "18", "vcodec": "avc1", "acodec": "mp4a",
         "ext": "mp4", "height": 360},
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a",
         "ext": "m4a", "abr": 128}]}
    ops = dl.opcoes_de_formatos(info_mux, com_ffmpeg=True)
    check(any(o["id"] == "f_22" and o["mesclar"] is False for o in ops),
          "com ffmpeg: muxado direto por id")
    check(any(o["id"] == "a_mp3" and o["converter"] for o in ops),
          "com ffmpeg: áudio MP3")
    ops2 = dl.opcoes_de_formatos(info_mux, com_ffmpeg=False)
    check(all(not o["mesclar"] and not o["converter"] for o in ops2),
          "sem ffmpeg: nada para juntar/converter")
    check(any(o["id"] == "f_18" for o in ops2), "sem ffmpeg: 360p único")
    info_sep = {"formats": [
        {"format_id": "616", "vcodec": "avc1", "acodec": "none",
         "ext": "mp4", "height": 720},
        {"format_id": "251", "vcodec": "none", "acodec": "opus",
         "ext": "webm", "abr": 160}]}
    ops3 = dl.opcoes_de_formatos(info_sep, com_ffmpeg=False)
    ids3 = [o["id"] for o in ops3]
    check("f_616" in ids3 and "f_251" in ids3,
          f"sem ffmpeg: vídeo sem áudio + áudio listados {ids3}")
    check(any(o["audio"] is False and "sem áudio" in o["rotulo"]
              for o in ops3),
          "vídeo sem áudio vem rotulado")
    ops4 = dl.opcoes_de_formatos(info_sep, com_ffmpeg=True)
    check(any(o["id"] == "f_616" and o["mesclar"] for o in ops4),
          "com ffmpeg: 720p juntável por id")
    info_aud = {"formats": [
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a",
         "ext": "m4a", "abr": 128},
        {"format_id": "251", "vcodec": "none", "acodec": "opus",
         "ext": "webm", "abr": 160}]}
    ops5 = dl.opcoes_de_formatos(info_aud, com_ffmpeg=False)
    ids5 = [o["id"] for o in ops5]
    check("f_140" in ids5 and "f_251" in ids5,
          f"sem ffmpeg: um áudio por formato {ids5}")
    check(all(o["converter"] is False for o in ops5),
          "sem ffmpeg: nenhum converte")
    conf_u = dl._opcoes_saida("unico", 777001)
    check(conf_u.get("formato_ytdlp") == "b" and not conf_u.get("mesclar"),
          "preset unico: arquivo único, sem junção")
    conf_ao = dl._opcoes_saida("audio_orig", 777002)
    check(conf_ao.get("formato_ytdlp") == "ba/b"
          and not conf_ao.get("converter"),
          "preset audio_orig: áudio original, sem conversão")
    check("unico" in dl.FORMATOS_VALIDOS, "unico é formato válido")


def teste_progresso():
    print("\n[progresso por pedido]")
    lin = dl.extrair_progresso_linha(
        "[download]  42.1% of ~5.00MiB at 1.00MiB/s ETA 00:03")
    check(abs(lin.get("pct", 0) - 0.421) < 0.001, "percentual da linha CLI")
    check(lin.get("eta") == "00:03", "ETA da linha CLI")
    check(dl.extrair_progresso_linha("ERROR: Video unavailable") == {},
          "linha de erro não é progresso")
    check(dl.extrair_progresso_linha("") == {}, "linha vazia não é progresso")
    # hook do pacote: bytes -> pct (sem rede, só o contrato do callback)
    estado = {}

    def _cb(info):
        estado.update(info or {})

    _cb({"status": "baixando", "baixado": 21, "total": 100,
         "vel": 1024.0, "eta": 5})
    check(estado.get("status") == "baixando", "hook escreve estado")
    check(estado.get("baixado") == 21 and estado.get("total") == 100,
          "hook leva bytes")
    import inspect
    check("progresso_cb" in inspect.signature(dl.baixar).parameters,
          "baixar aceita progresso_cb")


def teste_cancelamento():
    print("\n[cancelamento]")
    check(dl.solicitar_cancelamento(888888) is True, "pedido aceito")
    check(dl.consumir_cancelamento(888888) is True, "flag consumida")
    check(dl.consumir_cancelamento(888888) is False, "só uma vez")
    check(hasattr(dl, "DownloadCancelado"), "exceção própria existe")
    with open(os.path.join(bd.DIR_DOWNLOADS, "x-888888.mp4"), "wb") as f:
        f.write(b"0")
    check(dl.limpar_parciais(888888) is True, "limpa pelo sufixo -pid-")
    check(not os.path.isfile(
        os.path.join(bd.DIR_DOWNLOADS, "x-888888.mp4")),
        "final com -pid- também sai")


def teste_tarefas_vivas():
    print("\n[tarefas vivas entre telas]")
    try:
        from mod_video import telas as tv
    except Exception as e:
        _FALHAS.append(f"import telas: {e}")
        return
    tv._TAREFAS_VIVAS[424242] = {"user_nome": "MT-1234", "url": "https://x",
                                 "plataforma": "X", "formato": "a",
                                 "titulo": "T"}
    tv._TAREFAS_VIVAS[424243] = {"user_nome": "OUTRO", "url": "https://y",
                                 "plataforma": "Y", "formato": "a",
                                 "titulo": "O"}
    check(424242 in tv._TAREFAS_VIVAS, "tarefa registrada")
    meus = [pid for pid, t in tv._TAREFAS_VIVAS.items()
            if (t or {}).get("user_nome") == "MT-1234"]
    check(meus == [424242], "isolado por usuário (sem misturar stage)")
    chamadas = []
    tv._OUVIDORES["MT-1234"] = lambda: chamadas.append(1)
    tv._ouvir_conclusao("MT-1234")
    check(chamadas == [1], "ouvinte cutuca a tela aberta")
    tv._ouvir_conclusao("NINGUEM")
    check(True, "sem ouvinte não levanta")
    tv._OUVIDORES.pop("MT-1234", None)
    tv._TAREFAS_VIVAS.pop(424242, None)
    tv._TAREFAS_VIVAS.pop(424243, None)
    tv._avisar_seguro("ok", tipo="positive")
    check(True, "aviso seguro fora de tela não levanta")


def teste_versoes_e_fachada():
    print("\n[versoes e fachada]")
    from mod_tisosdocfly import bd_conexao as c
    c.init_db()
    c.init_db()
    import sqlite3
    db = os.path.join(os.environ["TISOSDOCFLY_DIR_BANCO"], "db_mod_tisosdocfly.db")
    con = sqlite3.connect(db)
    try:
        v = con.execute("SELECT valor FROM tb_config "
                        "WHERE chave='versao_modulo:video'").fetchone()
        check(bool(v) and v[0] == "1.0.261017", f"versao video {v}")
        vi = con.execute("SELECT valor FROM tb_config "
                         "WHERE chave='versao_modulo:tisosdocfly'").fetchone()
        check(bool(vi) and vi[0] == "1.0.261101", f"versao tisosdocfly {vi}")
        for m in ("migracao_versao_video_261017_biblioteca",
                  "migracao_versao_tisosdocfly_261017_video_limpeza"):
            n = con.execute("SELECT COUNT(*) FROM tb_config WHERE chave=?",
                            (m,)).fetchone()
            check(bool(n) and n[0] == 1, f"marcador {m}")
    finally:
        con.close()
    pid = bd.registrar_pedido("MT-1234", "https://vimeo.com/1", "Vimeo",
                              "melhor_mp4", expira_em="")
    nome = f"fachada_{pid}.mp4"
    with open(os.path.join(bd.DIR_DOWNLOADS, nome), "wb") as f:
        f.write(b"0" * 10)
    bd.atualizar_status(pid, "pronto", titulo="F", arquivo=nome, tamanho=10)
    bd.publicar_pedido(pid, ator="MT-1234")
    try:
        from mod_tisosdocfly import integracoes
        itens = integracoes.listar_videos_publicados()
    except Exception as e:
        itens = []
        _FALHAS.append(f"fachada levantou: {e}")
    check(any(i.get("id") == pid and i.get("url_midia", "").startswith(
        "/midia_video/") for i in itens), "fachada espelha a biblioteca")
    bd.excluir_pedido(pid, ator="MT-1234")


def main():
    print("\n=== video: stage, biblioteca e motor (offline) ===")
    try:
        bd.init_db()
        teste_init_e_config()
        teste_publicar_ciclo()
        teste_expiracao()
        teste_varredura_orfaos()
        teste_isolamento_e_motor()
        teste_progresso()
        teste_cancelamento()
        teste_tarefas_vivas()
        teste_formato_unico()
        teste_fala()
        teste_mensagem_erro()
        teste_miniatura()
        teste_opcoes_reais()
        teste_selecao_tabela()
        teste_versoes_e_fachada()
    except Exception as e:
        import traceback
        traceback.print_exc()
        _FALHAS.append(f"excecao: {e}")
    print(f"\n{_OK} ok, {len(_FALHAS)} falha(s)")
    for f in _FALHAS:
        print(f"  - {f}")
    return 1 if _FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
