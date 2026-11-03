"""Complemento do ciclo do mod_video (17/10/2026): decisões do dia que o
`test_video_ciclo.py` não cobre — tudo OFFLINE (sem rede, sem yt-dlp).

Cobre:
    - TTL vale para TODO perfil (comum e admin expiram no stage);
      biblioteca (publicado) nunca expira, mesmo com registro antigo
    - entrega automática ao comum: desce para o PC mas o arquivo FICA
      no stage até o TTL (igual ao admin) para ZIP/separados
    - papel antes da escrita: `_eh_admin` (geral é admin; comum sem
      vínculo não é); publicar/despublicar/excluir movem disco + banco
    - ZIP e separados pela seleção da tabela (evento é LISTA): só entra
      `pronto` com arquivo existente; inexistente fica de fora
    - cancelamento: bandeira idempotente (só uma vez), `DownloadCancelado`
      existe, parciais com sufixo `-pid-` saem no `limpar_parciais`
    - fila de 2: `VAGAS_DOWNLOAD == 2` e `_semaforo()` com 2 vagas
    - reattach ao voltar: `_TAREFAS_VIVAS` é global e filtrado por
      `user_nome` (ninguém vê pedido alheio)
    - reconcile de pendente órfão no boot: velho (>2 min) vira `erro`,
      fresco continua `pendente`, `pronto` não é tocado
    - varredura de órfãos: `.part` velho sai; referência de status
      terminal (`erro`/`expirado`) é limpa; fresco fica
    - remoção manual do admin não tem retry: após `excluir_pedido` o
      registro some, segunda exclusão devolve `False` sem levantar e
      expirar/reconciliar não ressuscitam nada
    - isolamento por usuário: `listar_historico(user)` só devolve os
      próprios; biblioteca é global (sem filtro)
    - `cfg_expiracao_min` tem piso 1; `init_db_video` é apelido do boot
    - `cleanup_video` registrado a cada 1 min em `rotinas.py`
    - todas as migrações `migracao_versao_video_261017_*` presentes e
      idempotentes (init 2x, cada marcador == 1)
    - fachada: chaves, prefixo `/midia_video/` e `limite`

Execute: poetry run python tests/test_video_completo.py
"""
import os
import sys
import zipfile

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")))

os.environ.setdefault("TISOSDOCFLY_DIR_BANCO", "/tmp/opencode/bd_teste_video_compl")

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


def _pedido_pronto(user, nome_base, conteudo=b"0" * 40, expira=None):
    """Registra pedido e planta o arquivo no stage como pronto."""
    exp = expira if expira is not None else bd._daqui_a_minutos(10)
    pid = bd.registrar_pedido(user, "https://www.youtube.com/watch?v=x",
                              "YouTube", "melhor_mp4", expira_em=exp)
    nome = f"{nome_base}_{pid}.mp4"
    with open(os.path.join(bd.DIR_DOWNLOADS, nome), "wb") as f:
        f.write(conteudo)
    bd.atualizar_status(pid, "pronto", titulo="T", arquivo=nome,
                        tamanho=len(conteudo))
    return pid, nome


def _limpar(pid, nomes=(), ator="MT-1234"):
    """Exclui o pedido e garante que nenhum arquivo dele sobre no disco.

    (`atualizar_status` de status puro limpa a referência no banco, então
    o `excluir_pedido` sozinho deixaria órfão no `downloads/` real —
    o varredor o pegaria depois, mas o teste não polui o disco.)
    """
    try:
        bd.excluir_pedido(pid, ator=ator)
    except Exception:
        pass
    for nome in nomes or ():
        for pub in (False, True):
            try:
                cam = bd.caminho_arquivo(nome, publicado=pub)
                if cam and os.path.isfile(cam):
                    os.remove(cam)
            except Exception:
                pass


def teste_ttl_todo_perfil():
    print("\n[TTL para todo perfil]")
    check(bd.init_db() is True, "init_db ok")
    # O TTL nasce do pedido: comum e admin ganham a mesma expiração.
    pid_c, nome_c = _pedido_pronto("MT-1234", "ttlcomum")
    pid_a, nome_a = _pedido_pronto("qamaster", "ttladmin")
    exp_c = bd.obter_pedido(pid_c).get("expira_em") or ""
    exp_a = bd.obter_pedido(pid_a).get("expira_em") or ""
    check(bool(exp_c) and bool(exp_a), "comum e admin têm expiração no stage")
    check(exp_c[:13] == exp_a[:13], "mesmo TTL para os dois perfis")
    # Vencidos somem do disco nos dois perfis (`atualizar_status` sem
    # título limpa o arquivo — por isso o nome vai junto aqui).
    bd.atualizar_status(pid_c, "pronto", titulo="T", arquivo=nome_c,
                        tamanho=40, expira_em="2000-01-01 00:00:00")
    bd.atualizar_status(pid_a, "pronto", titulo="T", arquivo=nome_a,
                        tamanho=40, expira_em="2000-01-01 00:00:00")
    n = bd.expirar_antigos()
    check(n >= 2, f"stage dos dois perfis expirou ({n})")
    check(bd.obter_pedido(pid_c).get("status") == "expirado",
          "comum expirado")
    check(bd.obter_pedido(pid_a).get("status") == "expirado",
          "admin expira junto (TTL total, sem exceção)")
    # Publicado não expira nem com registro antigo.
    pid_b, nome_b = _pedido_pronto("qamaster", "ttlpub", expira="")
    bd.publicar_pedido(pid_b, ator="qamaster")
    conn = bd.get_connection()
    try:
        conn.execute("UPDATE tb_video_historico SET data_registro="
                     "'2000-01-01 00:00:00' WHERE id=?", (pid_b,))
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    check(bd.expirar_antigos() == 0, "biblioteca sobrevive à varredura")
    check(bd.obter_pedido(pid_b).get("status") == "pronto",
          "publicado continua pronto")
    _limpar(pid_c, (), "qamaster")
    _limpar(pid_a, (), "qamaster")
    _limpar(pid_b, (), "qamaster")


def teste_entrega_comum_x_admin():
    print("\n[entrega automática ao comum]")
    # Comum e admin: pronto + arquivo fica até o TTL (nada some em 10 s;
    # o ZIP/separados precisam do arquivo no stage).
    pid_c, nome_c = _pedido_pronto("MT-1234", "entregacomum")
    cam_c = bd.caminho_arquivo(nome_c, publicado=False)
    check(bd.obter_pedido(pid_c).get("status") == "pronto",
          "comum continua pronto")
    check(os.path.isfile(cam_c), "arquivo do comum fica no stage")
    pid_a, nome_a = _pedido_pronto("qamaster", "entregaadmin")
    cam_a = bd.caminho_arquivo(nome_a, publicado=False)
    check(bd.obter_pedido(pid_a).get("status") == "pronto",
          "admin continua pronto")
    check(os.path.isfile(cam_a), "arquivo do admin fica no stage")
    _limpar(pid_c, (nome_c,), "MT-1234")
    _limpar(pid_a, (nome_a,), "qamaster")


def teste_papel_antes_da_escrita():
    print("\n[papel antes da escrita]")
    try:
        from mod_video import telas as tv
    except Exception as e:
        _FALHAS.append(f"import telas: {e}")
        return
    check(tv._eh_admin("alguem", "administrador_geral") is True,
          "geral é admin do módulo")
    check(tv._eh_admin("MT-1234", "comum") is False,
          "comum sem vínculo não é admin (fail-soft)")
    # Publicar move disco + banco; só admin publica (porta da UI).
    pid, nome = _pedido_pronto("qamaster", "papelpub")
    ok, _ = bd.publicar_pedido(pid, ator="qamaster")
    check(ok, "admin publica")
    check(not os.path.isfile(os.path.join(bd.DIR_DOWNLOADS, nome)),
          "saiu do stage")
    check(os.path.isfile(bd.caminho_arquivo(
        bd.obter_pedido(pid)["arquivo"], publicado=True)),
        "chegou à biblioteca")
    ok2, _ = bd.despublicar_pedido(pid, ator="qamaster")
    check(ok2, "admin despublica")
    atual = bd.obter_pedido(pid).get("arquivo") or ""
    ok3, _ = bd.excluir_pedido(pid, ator="qamaster")
    check(ok3, "admin exclui")
    _limpar(pid, tuple(n for n in (nome, atual) if n), "qamaster")
    check(bd.obter_pedido(pid) == {}, "registro sumiu")


def teste_zip_e_separados_pela_selecao():
    print("\n[ZIP e separados pela seleção (lista)]")
    try:
        from mod_video import telas as tv
    except Exception as e:
        _FALHAS.append(f"import telas: {e}")
        return

    class _Ev:
        def __init__(self, selection):
            self.selection = selection

    pid1, nome1 = _pedido_pronto("MT-1234", "lotea")
    pid2, nome2 = _pedido_pronto("MT-1234", "loteb")
    pid3, nome3 = _pedido_pronto("MT-1234", "lotec")
    bd.atualizar_status(pid3, "entregue")  # já desceu: fora do lote
    linhas = [
        {"id": pid1, "status": "pronto", "arquivo": nome1},
        {"id": pid2, "status": "pronto", "arquivo": nome2},
        {"id": pid3, "status": "entregue", "arquivo": ""},
    ]
    ev = _Ev(selection=[{"id": pid1}, {"id": pid2}, {"id": pid3}])
    chaves = tv._chaves_da_selecao(ev.selection)
    check(chaves == [pid1, pid2, pid3], "evento lista vira chaves")
    por_id = {l["id"]: l for l in linhas}
    marcados = [por_id[k] for k in chaves if k in por_id]
    nomes_zip = [l["arquivo"] for l in marcados
                 if l.get("status") == "pronto" and l.get("arquivo")]
    check(nomes_zip == [nome1, nome2], "só pronto com arquivo entra no lote")
    z = bd.zipar_selecao("MT-1234", nomes_zip + ["fantasma.mp4"])
    try:
        check(bool(z) and os.path.isfile(z), "ZIP junta os válidos")
        membros = zipfile.ZipFile(z).namelist() if z else []
        check(nome1 in membros and nome2 in membros,
              "ZIP tem os dois arquivos")
        check("fantasma.mp4" not in membros, "fantasma fica de fora")
    finally:
        try:
            if z:
                os.remove(z)
        except OSError:
            pass
    check(bd.zipar_selecao("MT-1234", ["fantasma.mp4"]) is None,
          "só fantasma = sem ZIP")
    # Separados: mesmo filtro, um download por arquivo existente.
    baixaveis = [l for l in marcados if l.get("status") == "pronto"
                 and l.get("arquivo") and os.path.isfile(
                     bd.caminho_arquivo(l["arquivo"], publicado=False))]
    check(len(baixaveis) == 2, "separados: 2 arquivos reais no disco")
    _limpar(pid1, (nome1,), "MT-1234")
    _limpar(pid2, (nome2,), "MT-1234")
    _limpar(pid3, (nome3,), "MT-1234")


def teste_cancelamento_bandeiras():
    print("\n[cancelamento]")
    pid = 500001
    check(dl.solicitar_cancelamento(pid) is True, "pedido aceito")
    check(dl.solicitar_cancelamento(pid) is True, "idempotente (2x ok)")
    check(dl.consumir_cancelamento(pid) is True, "flag consumida")
    check(dl.consumir_cancelamento(pid) is False, "só uma vez")
    check(hasattr(dl, "DownloadCancelado"), "exceção própria existe")
    nome = f"video-teste-{pid}.mp4"
    parcial = f"resto-{pid}.f251.webm"
    for n in (nome, parcial):
        with open(os.path.join(bd.DIR_DOWNLOADS, n), "wb") as f:
            f.write(b"0")
    check(dl.limpar_parciais(pid) is True, "limpa pelo sufixo -pid-")
    check(not os.path.isfile(os.path.join(bd.DIR_DOWNLOADS, nome)),
          "final com -pid- também sai")
    check(not os.path.isfile(os.path.join(bd.DIR_DOWNLOADS, parcial)),
          "parcial .f251 sai junto")
    dl.solicitar_cancelamento(pid)
    dl._limpar_cancelamento(pid)
    check(dl.consumir_cancelamento(pid) is False,
          "limpeza esquece flag e processo")


def teste_fila_de_2_e_reattach():
    print("\n[fila de 2 e reattach]")
    try:
        from mod_video import telas as tv
    except Exception as e:
        _FALHAS.append(f"import telas: {e}")
        return
    check(tv.VAGAS_DOWNLOAD == 2, "2 vagas simultâneas")
    sem = tv._semaforo()
    try:
        check(sem is not None and sem._value == 2, "semáforo com 2 vagas")
    except Exception as e:
        _FALHAS.append(f"semáforo: {e}")
    check(tv._semaforo() is sem, "mesmo semáforo no processo")
    # Tarefas vivas sobrevivem à navegação; cada um vê só as próprias.
    tv._TAREFAS_VIVAS[600001] = {"user_nome": "MT-1234", "url": "https://x/1",
                                 "titulo": "Um"}
    tv._TAREFAS_VIVAS[600002] = {"user_nome": "OUTRO", "url": "https://x/2",
                                 "titulo": "Dois"}
    minhas = [p for p, t in tv._TAREFAS_VIVAS.items()
              if (t or {}).get("user_nome") == "MT-1234"]
    check(minhas == [600001], "reattach filtra pelo dono")
    check(tv._PROGRESSO_VIVO is not None, "progresso global existe")
    tv._TAREFAS_VIVAS.pop(600001, None)
    tv._TAREFAS_VIVAS.pop(600002, None)


def teste_reconcile_orfao_boot():
    print("\n[reconcile de pendente órfão]")
    check(bd.init_db_video() is True, "apelido do boot ok")
    velho = bd.registrar_pedido("MT-1234", "https://x.com/velho", "X",
                                "melhor_mp4",
                                expira_em=bd._daqui_a_minutos(10))
    fresco = bd.registrar_pedido("MT-1234", "https://x.com/fresco", "X",
                                 "melhor_mp4",
                                 expira_em=bd._daqui_a_minutos(10))
    pid_pronto, _ = _pedido_pronto("MT-1234", "reconcpronto")
    conn = bd.get_connection()
    try:
        conn.execute("UPDATE tb_video_historico SET data_registro="
                     "'2000-01-01 00:00:00' WHERE id=?", (velho,))
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    n = bd.reconciliar_pendentes_boot()
    check(n >= 1, f"órfão reconciliado ({n})")
    check(bd.obter_pedido(velho).get("status") == "erro",
          "pendente velho vira erro")
    check(bd.obter_pedido(fresco).get("status") == "pendente",
          "pendente fresco continua")
    check(bd.obter_pedido(pid_pronto).get("status") == "pronto",
          "pronto não é tocado")
    check(bd.reconciliar_pendentes_boot() == 0, "2a passada: nada a fazer")
    _limpar(velho, (), "MT-1234")
    _limpar(fresco, (), "MT-1234")
    _limpar(pid_pronto, (), "MT-1234")


def teste_varredura_orfaos_terminal():
    print("\n[varredura: terminal e .part]")
    import time as _t
    part = os.path.join(bd.DIR_DOWNLOADS, "queda-700001.f616.mp4")
    fresco = os.path.join(bd.DIR_DOWNLOADS, "ativo-700002.tmp")
    with open(part, "wb") as f:
        f.write(b"0" * 10)
    with open(fresco, "wb") as f:
        f.write(b"0" * 10)
    velho = _t.time() - 3600
    os.utime(part, (velho, velho))
    pid_e, nome_e = _pedido_pronto("MT-1234", "terminalerro")
    bd.atualizar_status(pid_e, "erro")  # status puro limpa a referência…
    conn = bd.get_connection()  # …reposta aqui para simular resto de queda
    try:
        conn.execute("UPDATE tb_video_historico SET arquivo=? WHERE id=?",
                     (nome_e, pid_e))
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    n = bd.expirar_antigos(minutos=10)
    check(not os.path.isfile(part), ".part velho sem dono sai")
    check(os.path.isfile(fresco), "arquivo fresco (download ativo) fica")
    check(bd.obter_pedido(pid_e).get("arquivo") == "",
          "referência de terminal é limpa")
    check(n >= 1, f"contados: {n}")
    try:
        os.remove(fresco)
    except OSError:
        pass
    _limpar(pid_e, (nome_e,), "MT-1234")


def teste_remocao_manual_sem_retry():
    print("\n[remoção manual sem retry]")
    pid, nome = _pedido_pronto("qamaster", "semretry")
    ok, _ = bd.excluir_pedido(pid, ator="qamaster")
    check(ok, "admin remove")
    check(bd.obter_pedido(pid) == {}, "registro sumiu")
    check(not os.path.isfile(os.path.join(bd.DIR_DOWNLOADS, nome)),
          "arquivo sumiu do stage")
    ok2, msg2 = bd.excluir_pedido(pid, ator="qamaster")
    check(ok2 is False, f"2a exclusão não ressuscita ({msg2})")
    check(bd.expirar_antigos() >= 0, "expirar não levanta sem o registro")
    check(bd.reconciliar_pendentes_boot() == 0, "reconcile não ressuscita")
    check(bd.obter_pedido(pid) == {}, "continua sumido")


def teste_isolamento_usuarios():
    print("\n[isolamento por usuário]")
    pid_a, _ = _pedido_pronto("MT-1234", "isomeu")
    pid_b, _ = _pedido_pronto("OUTRO", "isooutro")
    meus = [p["id"] for p in bd.listar_historico("MT-1234", limite=100)]
    check(pid_a in meus, "vejo o meu")
    check(pid_b not in meus, "não vejo o alheio")
    check(bd.contar_historico("MT-1234") >= 1, "contagem por usuário")
    pid_pub, _ = _pedido_pronto("qamaster", "isopub", expira="")
    bd.publicar_pedido(pid_pub, ator="qamaster")
    bib = [p["id"] for p in bd.listar_biblioteca()]
    check(pid_pub in bib, "biblioteca é global (sem filtro de dono)")
    _limpar(pid_a, (), "qamaster")
    _limpar(pid_b, (), "qamaster")
    _limpar(pid_pub, (), "qamaster")


def teste_traversal_e_config():
    print("\n[traversal e config]")
    for mau in ("../../x", "..\\x", "/etc/passwd", "", ".", "a/b",
                "C:\\win\\x.mp4"):
        check(bd.caminho_arquivo(mau, publicado=False) == "",
              f"barrado no stage: {mau!r}")
        check(bd.caminho_arquivo(mau, publicado=True) == "",
              f"barrado na biblioteca: {mau!r}")
    check(bd.url_biblioteca("../x") == "", "URL não vaza traversal")
    check(bd.url_biblioteca("ok.mp4") == "/midia_video/ok.mp4",
          "URL pública da biblioteca")
    check(bd.cfg_expiracao_min() == 10, "padrão 10 min")
    try:
        from mod_tisosdocfly.bd_conexao import set_config
        set_config("video_expiracao_min", "0")
        check(bd.cfg_expiracao_min() == 1, "piso 1 min")
    finally:
        try:
            set_config("video_expiracao_min", "10")
        except Exception:
            pass
    check(bd.cfg_expiracao_min() == 10, "volta ao padrão")


def teste_formatos_e_progresso_offline():
    print("\n[formatos e progresso (offline)]")
    for f in ("melhor_mp4", "medio_mp4", "audio_mp3", "unico", "audio_orig"):
        check(f in dl.FORMATOS_VALIDOS, f"{f} é formato válido")
    check(isinstance(dl.FORMATOS, tuple) and len(dl.FORMATOS) == 3,
          "3 presets com ffmpeg")
    check(isinstance(dl.FORMATOS_SEM_FFMPEG, tuple)
          and len(dl.FORMATOS_SEM_FFMPEG) == 2, "2 presets sem ffmpeg")
    check(dl.opcoes_de_formatos({}) == [], "sem info = sem opções")
    check(dl.opcoes_de_formatos({"formats": []}) == [],
          "sem trilhas = sem opções")
    check(dl.exige_ffmpeg({}) is True, "sem info = cautela (exige)")
    conf = dl._opcoes_saida("melhor_mp4", 700003)
    check(conf.get("mesclar") is True or
          conf.get("formato_ytdlp") == "b", "preset coerente com o ffmpeg")
    lin = dl.extrair_progresso_linha(
        "[download] 100.0% of 5.00MiB at 1.00MiB/s ETA 00:00")
    check(abs(lin.get("pct", 0) - 1.0) < 0.001, "100% = 1.0")
    check(dl.extrair_progresso_linha("[download] 150% of X") .get("pct", 0)
          <= 1.0, "teto em 1.0")
    check(dl.mime_por_nome("a.MP4") == "video/mp4", "mime ignora caixa")
    check(dl.mime_por_nome("semext") == "", "sem extensão = vazio")
    check(dl.detectar_plataforma("https://exemplo.com/v") == "Outro site",
          "desconhecido = Outro site")
    check(dl.validar_url("http://x" * 500) == "", "URL gigante barrada")


def teste_job_e_migracoes():
    print("\n[job e migrações 1.0.261017]")
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rot = open(os.path.join(raiz, "src", "mod_tisosdocfly", "rotinas.py"),
               encoding="utf-8").read()
    check('"cleanup_video"' in rot or "'cleanup_video'" in rot,
          "job cleanup_video registrado")
    check("minutes=1" in rot, "limpeza a cada 1 min")
    from mod_tisosdocfly import bd_conexao as c
    try:
        c.init_db()
        check(True, "init central 1x (sem levantar)")
    except Exception as e:
        check(False, f"init central 1x: {e}")
    try:
        c.init_db()
        check(True, "init central 2x (idempotente, sem levantar)")
    except Exception as e:
        check(False, f"init central 2x: {e}")
    import sqlite3
    db = os.path.join(os.environ["TISOSDOCFLY_DIR_BANCO"], "db_mod_tisosdocfly.db")
    con = sqlite3.connect(db)
    try:
        for chave, esp in (("versao_modulo:video", "1.0.261017"),
                           ("versao_modulo:tisosdocfly", "1.0.261101")):
            v = con.execute("SELECT valor FROM tb_config WHERE chave=?",
                            (chave,)).fetchone()
            check(bool(v) and v[0] == esp, f"{chave} = {esp}")
        marcas = [r[0] for r in con.execute(
            "SELECT chave FROM tb_config WHERE chave LIKE "
            "'migracao_versao_video_261017%'").fetchall()]
        check(len(marcas) >= 20, f"{len(marcas)} migrações video 261017")
        for m in ("migracao_versao_video_261017_biblioteca",
                  "migracao_versao_video_261017_ttl_total",
                  "migracao_versao_video_261017_fila_3",
                  "migracao_versao_video_261017_sobrevive_tela",
                  "migracao_versao_video_261017_varredura_orfaos",
                  "migracao_versao_video_261017_sel_lista",
                  "migracao_versao_video_261017_entrega_auto",
                  "migracao_versao_video_261017_meus_arquivos",
                  "migracao_versao_video_261017_grade_arquivos",
                  "migracao_versao_video_261017_tabela_pdf",
                  "migracao_versao_video_261017_fica_ate_ttl"):
            n = con.execute("SELECT COUNT(*) FROM tb_config WHERE chave=?",
                            (m,)).fetchone()
            check(bool(n) and n[0] == 1, f"marcador {m}")
        n = con.execute("SELECT COUNT(*) FROM tb_config WHERE chave=?",
                        ("migracao_versao_tisosdocfly_261017_video_limpeza",
                         )).fetchone()
        check(bool(n) and n[0] == 1, "marcador tisosdocfly video_limpeza")
    finally:
        con.close()


def teste_fachada_publicados():
    print("\n[fachada listar_videos_publicados]")
    pid1, _ = _pedido_pronto("qamaster", "fachada1", expira="")
    pid2, _ = _pedido_pronto("qamaster", "fachada2", expira="")
    bd.publicar_pedido(pid1, ator="qamaster")
    bd.publicar_pedido(pid2, ator="qamaster")
    pid_stage, _ = _pedido_pronto("MT-1234", "fachadastage")
    try:
        from mod_tisosdocfly import integracoes
        todos = integracoes.listar_videos_publicados()
        um = integracoes.listar_videos_publicados(limite=1)
    except Exception as e:
        _FALHAS.append(f"fachada levantou: {e}")
        todos, um = [], []
    ids = [i.get("id") for i in todos]
    check(pid1 in ids and pid2 in ids, "publicados aparecem")
    check(pid_stage not in ids, "stage não vaza na fachada")
    item = next((i for i in todos if i.get("id") == pid1), {})
    check(set(("id", "titulo", "plataforma", "url_midia",
               "tamanho_bytes")) <= set(item), "chaves da fachada")
    check(str(item.get("url_midia") or "").startswith("/midia_video/"),
          "url_midia em /midia_video/")
    check(len(um) == 1, "limite respeitado")
    _limpar(pid1, (), "qamaster")
    _limpar(pid2, (), "qamaster")
    _limpar(pid_stage, (), "qamaster")


def main():
    print("\n=== video completo: decisões 17/10 (offline) ===")
    try:
        bd.init_db()
        teste_ttl_todo_perfil()
        teste_entrega_comum_x_admin()
        teste_papel_antes_da_escrita()
        teste_zip_e_separados_pela_selecao()
        teste_cancelamento_bandeiras()
        teste_fila_de_2_e_reattach()
        teste_reconcile_orfao_boot()
        teste_varredura_orfaos_terminal()
        teste_remocao_manual_sem_retry()
        teste_isolamento_usuarios()
        teste_traversal_e_config()
        teste_formatos_e_progresso_offline()
        teste_job_e_migracoes()
        teste_fachada_publicados()
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
