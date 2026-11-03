"""Coleta a folha COMPLETA de servidores do portal da transparencia.

EN: Collects the complete payroll sheet from the transparency portal.

POR QUE ESTE SCRIPT EXISTE (01/10/2026)
    Os outros dois coletores do modulo pecam em complements opostos:

    - `coleta_folha.py` pede remuneracao e ficha de contracheque, mas trata
      PAGINA VAZIA como "a folha acabou". O portal limita a resposta quando
      recebe requisicoes demais, e-limitacao pareceu fim de folha: gravou
      **650 de 1165** servidores e chamou aquilo de folha completa.
    - `coletar_folha_simples.py` acerta o fim da folha (so encerra quando
      `inicio >= recordsFiltered`, e pagina vazia antes disso e recusa), mas
      pede **menos colunas**: deixa de fora `vldefault` e `cdContraCheque`.
      Uma folha coletada por ele perde a remuneracao — que e o historico que
      `carga_folha.definir_remuneracao` grava e o numero que o card de Dados
      Abertos mostra (mediana, folha bruta).

    Este script junta as duas partes: le a folha INTEIRA E com remuneracao.

O QUE ESTE SCRIPT FAZ
    Devolve `funcionarios.json` e `funcionarios.csv` em `dados/` — os mesmos
    arquivos, nos mesmos caminhos, que `carga_folha.py` le. Nao toca no banco.

COMO USAR
    python mod_gest_cad_usuario/coletar_folha_completa.py
    python mod_gest_cad_usuario/coletar_folha_completa.py --competencia 07/2026

    Rodar de onde a rede ALCANCA o portal. A rede de trabalho nao alcancava
    (TCP 443 sem resposta em 20.49.43.71), e nenhum intervalo corrige rede
    morta.

SAIDAS — o script FALHA em vez de gravar folha truncada
    0  folha completa, conferida contra o total anunciado; gravada
    2  o portal anunciou N e vieram menos: NAO grava, e o parcial fica em
       `dados/funcionarios.parcial.json` para retomar
    3  o portal nao informou `recordsFiltered`: sem base para afirmar que a
       folha esta completa, e NAO grava

    Truncar e chamar aquilo de completo e o defeito que este script fecha.

REGRAS DE REDE (o portal e de terceiro e derruba quem insiste)
    - uma requisicao por pagina de 25: o portal trava `length` em 25, e pedir
      1 ou 100 devolve ZERO registros com HTTP 200 — o sintoma e "o portal esta
      vazio" e nao esta
    - espera SORTEADA de 4 a 9 s: intervalo fixo entre requisicoes e a
      assinatura de acesso automatizado
    - `recordsFiltered` e o total real, e decide o fim da folha
    - queda de conexao (`RemoteDisconnected`, `WinError 10060`...) -> pausa de
      45 s antes de repetir: recarregar rapido contra quem mandou parar e o
      caminho mais curto para ser banido
    - grava o parcial a cada pagina, por `.tmp` + troca atomica: uma queda
      custa uma pagina, nao a folha

BASE LEGAL
    Lei 12.527/2011 e Lei 11.129/2005: a prefeitura e OBRIGADA a publicar a
    relacao nominal dos servidores. O User-Agent se identifica por essa razao.
"""
import http.client
import json
import os
import random
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

RAIZ = r"D:\Documents\git\tisosdocfly"
DIR_DADOS = os.path.join(RAIZ, "mod_gest_cad_usuario", "dados")
CFG_ARQ = os.path.join(RAIZ, "mod_gest_cad_usuario", "fonte_folha.json")
ARQ_JSON = os.path.join(DIR_DADOS, "funcionarios.json")
ARQ_CSV = os.path.join(DIR_DADOS, "funcionarios.csv")
ARQ_PARCIAL = os.path.join(DIR_DADOS, "funcionarios.parcial.json")

PAGINA = 25
ESPERA_MIN_S = 4.0
ESPERA_MAX_S = 9.0
PAUSA_CONEJAO_S = 45.0
TENTATIVAS = 4
REPETICA_S = (10, 25, 60, 120)
USER_AGENT = "tisosdocfly/1.0 (carga de servidores - dados publicos)"

COLUNAS_GRID = ("nmMatricula", "nmServidor", "nmUnidade", "nmLotacao",
                "nmCargo", "nmSituacao", "nmVinculo", "nmRegime",
                "nuCargaHoraria", "dtAdmissao", "dtExoneracao", "nmTipo",
                "vldefault", "cdContraCheque")

CAMPOS_CSV = ("matricula", "nome", "unidade", "lotacao", "cargo", "vinculo",
              "situacao", "remuneracao", "ficha_contracheque", "regime",
              "carga_horaria", "admissao", "exoneracao")

ERROS_CONEXAO = (urllib.error.URLError, OSError, ssl.SSLError,
                 http.client.HTTPException)


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def gravar_tmp(caminho, texto):
    """Grava por .tmp e troca: uma queda custa uma pagina, nao a folha."""
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(texto)
    os.replace(tmp, caminho)


def abrir_sessao(url_referer):
    """Abre a pagina uma vez, para pegar o cookie. Duas sessoes => grid vazio."""
    req = urllib.request.Request(url_referer, headers={
        "User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    opener.open(req, timeout=90).read()
    return opener


def ler_competencias(opener, url):
    corpo = {"entidade": "", "competencia": "", "unidade": "", "cargo": "",
             "funcao": "", "vinculo": "", "vlInicio": "0", "vlFim": "0",
             "grupocalculo": "", "covid": None}
    req = urllib.request.Request(
        url, data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": USER_AGENT})
    dados = json.loads(opener.open(req, timeout=90).read().decode("iso-8859-1"))
    if isinstance(dados, dict):
        for chave in ("data", "dados", "competencias", "lista"):
            if chave in dados:
                return [str(c) for c in (dados.get(chave) or [])]
    return [str(c) for c in (dados or [])]


def ler_pagina(opener, url, competencia, inicio):
    """Uma pagina. Devolve (linhas, total_anunciado)."""
    corpo = {
        "parameters": {
            "draw": inicio // PAGINA + 1,
            "columns": [{"data": c, "name": "", "searchable": True,
                         "orderable": True,
                         "search": {"value": "", "regex": False}}
                        for c in COLUNAS_GRID],
            "order": [{"column": 0, "dir": "asc"}],
            "start": inicio,
            "length": PAGINA,
            "search": {"value": "", "regex": False},
        },
        "entidade": "", "competencia": competencia, "unidade": "",
        "cargo": "", "funcao": "", "vinculo": "", "vlInicio": "0",
        "vlFim": "0", "grupocalculo": "", "covid": None,
    }

    ultima = None
    for tentativa in range(TENTATIVAS):
        try:
            req = urllib.request.Request(
                url, data=json.dumps(corpo).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8",
                         "User-Agent": USER_AGENT})
            bruto = opener.open(req, timeout=90).read()
            dados = json.loads(bruto.decode("iso-8859-1"))
            linhas = dados.get("data") or []
            if isinstance(linhas, dict):
                linhas = linhas.get("data", [])
            linhas = [l for l in linhas if isinstance(l, dict)]
            total = dados.get("recordsFiltered")
            total = int(total) if total is not None else None

            if linhas:
                return linhas, total
            if isinstance(total, int) and inicio >= total:
                return [], total
            log(f"    pagina {inicio} vazia com total anunciado {total}: "
                f"vou tratar como recusa, nao como fim")
            espera = REPETICA_S[min(tentativa, len(REPETICA_S) - 1)]
            log(f"    esperando {espera}s e repetindo")
            time.sleep(espera)
            continue
        except ERROS_CONEXAO as e:
            ultima = e
            log(f"    o portal cortou a conexao ({type(e).__name__}); "
                f"pausa de {PAUSA_CONEJAO_S:.0f}s")
            time.sleep(PAUSA_CONEJAO_S)
            continue
    raise RuntimeError(f"o portal nao respondeu na pagina {inicio} apos "
                       f"{TENTATIVAS} tentativas: {ultima}")


def normalizar(linha):
    def txt(campo):
        return (linha.get(campo) or "").strip() or None
    return {
        "matricula": txt("nmMatricula"),
        "nome": txt("nmServidor"),
        "unidade": txt("nmUnidade"),
        "lotacao": txt("nmLotacao"),
        "cargo": txt("nmCargo"),
        "vinculo": txt("nmVinculo"),
        "situacao": txt("nmSituacao"),
        "tipo": txt("nmTipo"),
        "regime": txt("nmRegime"),
        "carga_horaria": txt("nuCargaHoraria"),
        "admissao": txt("dtAdmissao"),
        "exoneracao": txt("dtExoneracao"),
        # Dinheiro e TEXTO: guardar em ponto flutuante perde centavo, e o valor
        # arredondado divergiria do portal -- que e a conferencia que o DTI faz.
        "remuneracao": txt("vldefault"),
        "ficha_contracheque": txt("cdContraCheque"),
    }


def ler_parcial(competencia):
    if not os.path.exists(ARQ_PARCIAL):
        return [], set(), 0
    try:
        with open(ARQ_PARCIAL, encoding="utf-8") as fh:
            d = json.load(fh)
        if d.get("competencia") != competencia:
            return [], set(), 0
        servidores = d.get("servidores") or []
        vistos = {s.get("matricula") for s in servidores if s.get("matricula")}
        proximo = int(d.get("proximo") or 0)
        log(f"retomando do parcial: {len(servidores)} servidores, "
            f"proxima pagina em {proximo}")
        return servidores, vistos, proximo
    except Exception as e:
        log(f"  parcial ilegivel ({e}); comecando do zero")
        return [], set(), 0


def gravar_parcial(servidores, competencia, proximo, total):
    gravar_tmp(ARQ_PARCIAL, json.dumps(
        {"competencia": competencia, "proximo": proximo, "total": total,
         "servidores": servidores}, ensure_ascii=False))


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="Coleta a folha COMPLETA de servidores do portal.")
    ap.add_argument("--competencia", default=None,
                    help="MM/AAAA (padrao: a mais recente que o portal "
                         "informar)")
    ap.add_argument("--forcar", action="store_true",
                    help="coleta mesmo com 'ativo': false em fonte_folha.json")
    args = ap.parse_args()

    with open(CFG_ARQ, encoding="utf-8") as fh:
        cfg = json.load(fh)

    # O INTERRUPTOR QUE ANTES NAO EXISTIA (01/10/2026)
    #
    # `fonte_folha.json` tem o `ativo`, e ele era lido ONLY pela carga — o que
    # desligava a populacao do cadastro mas NAO impedia ninguem de rodar o
    # coletor. Ou seja: desligar a fonte na configuracao e, na pratica, nao
    # desligava a captura. E a captura e a unica parte desta cadeia que fala
    # com o servidor de terceiro: a carga le o arquivo local.
    #
    # Isso importa por um motivo que nao e de codigo: o portal e o servidor
    # PRINCIPAL da prefeitura, e a coleta faz requisicao a cada 4 a 9 s.
    # Quem administra aquele servidor registra a carga. Uma opcao de
    # configuracao que parece desligar a captura e nao desliga e pior do que
    # nao ter a opcao — ela da a impressao de que o problema foi resolvido.
    #
    # Aqui o coletor PARA, sem abrir uma unica conexao, e diz como forcar.
    if not cfg.get("ativo") and not args.forcar:
        log("FONTE DESATIVADA em fonte_folha.json ('ativo': false).")
        log("Nada foi pedido ao portal — nenhuma conexao foi aberta.")
        log("A carga da folha segue normal: ela le o arquivo local em dados/,")
        log("e nao toca no portal.")
        log("")
        log("Se a coleta for mesmo necessaria, rode com --forcar — e o que")
        log("estaquinha o servidor principal da prefeitura.")
        return 4
    raiz = (cfg.get("portal_url") or "").rstrip("/")
    pontos = cfg.get("portal_endpoints") or {}
    url_grid = raiz + (pontos.get("folha") or "")
    url_comp = raiz + (pontos.get("competencia") or "")
    url_referer = raiz + (cfg.get("portal_pagina") or "/servidores-por-nomes")

    log(f"portal: {raiz}")
    log(f"intervalo {ESPERA_MIN_S:.0f}-{ESPERA_MAX_S:.0f}s sorteado | "
        f"pagina {PAGINA} | pausa em queda {PAUSA_CONEJAO_S:.0f}s")

    os.makedirs(DIR_DADOS, exist_ok=True)
    log("abrindo a pagina do portal (uma vez, para o cookie de sessao)")
    opener = abrir_sessao(url_referer)

    log("perguntando as competencias")
    comps = ler_competencias(opener, url_comp)
    if not comps and not args.competencia:
        log("o portal nao informou competencia nenhuma")
        return 1
    competencia = args.competencia or comps[0]
    log(f"competencias: {comps} | usando {competencia}")

    servidores, vistos, inicio = ler_parcial(competencia)
    total = None
    espera_ate = time.monotonic()
    pagina_n = inicio // PAGINA

    while True:
        decorrido = time.monotonic() - espera_ate
        if decorrido < ESPERA_MIN_S:
            time.sleep(ESPERA_MIN_S - decorrido)
        espera = random.uniform(ESPERA_MIN_S, ESPERA_MAX_S)

        linhas, total = ler_pagina(opener, url_grid, competencia, inicio)
        if not linhas:
            break

        novos = 0
        for linha in linhas:
            reg = normalizar(linha)
            chave = reg["matricula"]
            # A mesma matricula pode vir duas vezes (exoneracao e reconducao).
            # Fica a primeira, e a contagem continua dizendo quantas PESSOAS sao.
            if chave and chave in vistos:
                continue
            if chave:
                vistos.add(chave)
            servidores.append(reg)
            novos += 1

        inicio += PAGINA
        pagina_n += 1
        gravar_parcial(servidores, competencia, inicio, total)
        log(f"pagina {pagina_n:>2} | {len(servidores):>4}/{total or '?'} "
            f"servidores | +{novos} | proxima em {espera:.1f}s")

        if novos == 0:
            break
        if isinstance(total, int) and len(servidores) >= total:
            log(f"o portal anunciou {total} e foram lidos {len(servidores)}: "
                f"folha completa")
            break

    time.sleep(espera)

    log(f"--- conferencia: {len(servidores)} servidores, "
        f"total anunciado {total}")
    if isinstance(total, int) and len(servidores) < total:
        log(f"FALTA {total - len(servidores)}. NADA gravado; o parcial ficou "
            f"em {ARQ_PARCIAL}")
        return 2
    if not isinstance(total, int):
        log("o portal NAO informou recordsFiltered: sem base para dizer que a "
            "folha esta completa. Nada gravado.")
        return 3

    folha = {
        "origem": cfg.get("origem_rotulo") or f"Portal ({raiz})",
        "url": url_referer,
        "competencia": competencia,
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(servidores),
        "aviso": ("Dados publicados por lei (Lei 12.527/2011 e Lei "
                  "11.129/2005). Inclui remuneração e ficha de "
                  "contracheque, também publicação legal."),
        "servidores": servidores,
    }
    gravar_tmp(ARQ_JSON, json.dumps(folha, ensure_ascii=False, indent=2))

    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(CAMPOS_CSV)
    for s in servidores:
        w.writerow([s.get(c) or "" for c in CAMPOS_CSV])
    gravar_tmp(ARQ_CSV, buf.getvalue())

    try:
        os.remove(ARQ_PARCIAL)
    except OSError:
        pass

    log(f"GRAVADO {len(servidores)} servidores da competencia {competencia}")
    log(f"  {ARQ_JSON}")
    log(f"  {ARQ_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())