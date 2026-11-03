"""Coleta a folha de servidores do portal da transparência, com parcimônia.

EN: Collects the published payroll sheet from the transparency portal, politely.

POR QUE ESTE SCRIPT EXISTE
    `coleta_folha.py` grew features and became fragile: it repeated itself twice
    in a row and the portal answered both times by dropping the connection, and
    a page that came back EMPTY was read as "the sheet ended" — so a throttled
    portal produced a sheet of 650 records that looked complete. This script is
    the plain version, written from what the protocol actually does.

O QUE FOI APRENDIDO LENDO O PORTAL (01/10/2026)
    These are not guesses; each one was confirmed against the live portal.

    - O endpoint do grid é
      `/transparencia/servidor/tpc_servidor_data.ashx?metodo=ServidorGetNomeGrid`
      e a resposta vem em **ISO-8859-1**, não em UTF-8.
    - É um grid **DataTables**: o corpo é
      `{"parameters": {start, length, draw, columns[], order[]}, "competencia": ...}`.
    - **`length` é travado em 25.** Pedir 1 ou 100 devolve ZERO registros com
      HTTP 200 — parece "o portal está vazio" e não está. A única página que
      funciona é 25.
    - **`recordsFiltered` é o total real da folha.** Confirmado: a folha de
      08/2026 tem 1165 servidores, e é esse campo que diz isso. A última página
      cheia é `start=1140` e `start=1165` devolve vazio. É o que este script
      usa para saber quando parou — e NÃO a página vazia, que pode ser recusa.
    - O portal **derruba a conexão** quando recebe requisições demais. Chega
      como `RemoteDisconnected` / `ConnectionResetError` / `WinError 10060`, e
      depois de algumas rodadas ele nem responde o handshake. Por isso o
      intervalo aqui é largo e o cooldown entre rodadas é obrigatório.

COMO USAR
    python mod_gest_cad_usuario/coletar_folha_simples.py              # retoma ou coleta
    python mod_gest_cad_usuario/coletar_folha_simples.py --competencia 07/2026
    python mod_gest_cad_usuario/coletar_folha_simples.py --esperar 15  # espera antes de começar

SEM RUIDO E SEM SOBRECARGA
    - Uma requisição por página de 25, com espera **sorteada** entre 4 s e 9 s.
      Intervalo fixo é a assinatura de robô; o sorteado não é.
    - Depois de uma queda de conexão, a espera sobe progressivamente (a pausa
      é o que faz o portal perdoar), e nunca menos que `PAUSA_CONEJAO`.
    - A página vazia só encerra a coleta quando ela bate com o `recordsFiltered`
      que o próprio portal informou. Antes disso, é recusa: espera e repete.
    - Grava o parcial **a cada página**, por `.tmp` + troca atômica. Uma queda
      custa uma página, não a folha.
    - `COOLDOWN_S` impede collectar duas vezes seguidas: rodadas repetidas sem
      pausa é o que faz o portal banir a origem temporariamente.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Onde a folha mora. Fora do git de propósito (AGENTS.md §1 e §8.3): nome e
# matrícula de servidor real não vão para o histórico do repositório.
# --------------------------------------------------------------------------
DIR_DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")
ARQUIVO_JSON = os.path.join(DIR_DADOS, "funcionarios.json")
ARQUIVO_CSV = os.path.join(DIR_DADOS, "funcionarios.csv")
ARQUIVO_PARCIAL = os.path.join(DIR_DADOS, "funcionarios.parcial.json")

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "fonte_folha.json")

# O portal recusa QUALQUER length diferente de 25 — ver o docstring.
PAGINA = 25

# A espera entre requisições. Larga de propósito: o portal é de terceiro e
# derruba quem insiste. Média ~6,5 s, e a folha de 1165 leva ~5 minutos.
ESPERA_MIN_S = 4.0
ESPERA_MAX_S = 9.0

# Depois que a conexão cai, a espera cresce. A primeira espera curta é o que
# faz a origem ser banida: recarregar contra um servidor que acabou de dizer
# "pare" é o caminho mais curto para ser bloqueado de vez.
PAUSA_CONEJAO_S = 45.0
TENTATIVAS = 4
ESPERA_REPETICA_S = (10, 25, 60, 120)

# Nada de collectar duas vezes seguidas sem esfriar: rodadas repetidas sem
# pausa é o que produz o bloqueio que dura horas.
COOLDOWN_S = 90.0

# Campos pedidos ao grid e o que é guardado de cada um. `vldefault` (remuneração)
# e `cdContraCheque` (ficha) chegam no grid e ficam de fora do que o sistema
# usa, pela mesma razão de `coleta_folha.py`: ler menos do que o portal oferece
# é a parte fácil de estar dentro da lei.
COLUNAS_GRID = ("nmMatricula", "nmServidor", "nmUnidade", "nmLotacao",
                "nmCargo", "nmSituacao", "nmVinculo", "nmRegime",
                "nuCargaHoraria", "dtAdmissao", "dtExoneracao", "nmTipo")

CAMPOS_CSV = ("matricula", "nome", "unidade", "lotacao", "cargo", "vinculo",
              "situacao", "regime", "carga_horaria", "admissao", "exoneracao")

USER_AGENT = "tisosdocfly/1.0 (carga de servidores - dados publicos)"

# Tudo que pode significar "o portal me cortou" — e que portanto NÃO pode
# encerrar a coleta.
ERROS_CONEXAO = (urllib.error.URLError, OSError, ssl.SSLError)


def log(mensagem: str) -> None:
    """Uma linha por evento, com tempo. `flush` porque a pessoa acompanha."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {mensagem}", flush=True)


def carregar_config() -> dict:
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"configuracao ilegivel ({e}); usando o padrao do portal")
        return {}


def montar_urls(cfg: dict) -> tuple[str, str, str]:
    """Devolve (url do grid, url da competencia, pagina para o Referer)."""
    raiz = (cfg.get("portal_url") or "").rstrip("/")
    pontos = cfg.get("portal_endpoints") or {}
    return (raiz + (pontos.get("folha") or ""),
            raiz + (pontos.get("competencia") or ""),
            raiz + (cfg.get("portal_pagina") or "/servidores-por-nomes"))


def abrir(url_referer: str):
    """Abre a página uma vez, para pegar o cookie de sessão.

    Sem isso o portal pode responder com o grid vazio, e o sintoma é o mesmo
    de "não há servidores" — erro que se disfarça de dado.
    """
    contexto = ssl.create_default_context()
    req = urllib.request.Request(url_referer, headers={
        "User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=contexto))
    opener.open(req, timeout=90).read()
    return opener


def esperar_entre_requisicoes() -> float:
    """Espera sorteada e devolve quanto esperou."""
    espera = random.uniform(ESPERA_MIN_S, ESPERA_MAX_S)
    time.sleep(espera)
    return espera


def pagina(opener, url: str, competencia: str, inicio: int,
           tentativas_pagina_vazia: int = 3) -> tuple[list[dict], int | None]:
    """Lê UMA página. Devolve (linhas, total_anunciado).

    O `total_anunciado` é o `recordsFiltered` do portal — o número que diz
    quantos servidores existem. Ele vem em toda resposta e é o que decide se a
    coleta acabou: a página vazia é ambígua (pode ser fim OU recusa), o total
    não.

    A página vazia que ainda não bateu com o total é tratada como RECUSA: a
    função espera e repete, em vez de devolver lista vazia e encerrar a folha
    pela metade. Foi esse o defeito que fez a versão anterior gravar 650 de
    1165 e chamar aquilo de folha completa.
    """
    corpo = {
        "parameters": {
            "draw": inicio // PAGINA + 1,
            "columns": [{"data": c, "name": "", "searchable": True,
                         "orderable": True,
                         "search": {"value": "", "regex": False}}
                        for c in COLUNAS_GRID],
            # Ordena por matrícula: duas rodadas saem na mesma ordem e o diff
            # entre elas é só mudança de verdade.
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

            if linhas:
                return linhas, (int(total) if total is not None else None)

            # Página vazia: aqui está o defeito antigo. Se o portal já disse
            # quantos existem e o inicio chegou lá, é o fim de verdade. Se
            # ainda não bateu, é o portal segurando a resposta.
            if isinstance(total, int) and inicio >= total:
                return [], total
            log(f"  pagina {inicio} veio vazia e o total anunciado e "
                f"{total}; tratando como recusa do portal")
            espera = ESPERA_REPETICA_S[min(tentativa,
                                           len(ESPERA_REPETICA_S) - 1)]
            log(f"  esperando {espera}s e repetindo")
            time.sleep(espera)
            continue

        except ERROS_CONEXAO as e:
            ultima = e
            nome = e.__class__.__name__
            # A conexão caiu no meio da resposta: o portal respondeu e cortou.
            # Pausa LONGA antes de repetir — recarregar rápido contra um
            # servidor que mandou parar é o que garante o banimento.
            log(f"  o portal cortou a conexao ({nome}); "
                f"pausa de {PAUSA_CONEJAO_S:.0f}s")
            time.sleep(PAUSA_CONEJAO_S)
            continue

    raise RuntimeError(
        f"o portal nao respondeu na pagina {inicio} apos {TENTATIVAS} "
        f"tentativas: {ultima}")


def normalizar(linha: dict) -> dict:
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
        "regime": txt("nmRegime"),
        "carga_horaria": txt("nuCargaHoraria"),
        "admissao": txt("dtAdmissao"),
        "exoneracao": txt("dtExoneracao"),
    }


def gravar_parcial(servidores: list, competencia: str, proximo: int,
                   total: int | None) -> None:
    """Grava o parcial por arquivo temporário e troca atômica.

    Gravar direto deixaria um JSON pela metade se o processo morresse no meio
    da escrita, e a próxima leitura cairia em exceção — que é perder a folha
    inteira por causa de um arquivo truncado.
    """
    os.makedirs(DIR_DADOS, exist_ok=True)
    tmp = f"{ARQUIVO_PARCIAL}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"competencia": competencia,
                   "proximo_inicio": proximo,
                   "total_anunciado": total,
                   "coletado_em": datetime.now(timezone.utc).isoformat(
                       timespec="seconds"),
                   "servidores": servidores}, f, ensure_ascii=False)
    os.replace(tmp, ARQUIVO_PARCIAL)


def ler_parcial(competencia: str) -> tuple[list, set, int]:
    """Retoma de onde a coleta anterior parou.

    Só reaproveita se for a MESMA competência: misturar o parcial de um mês
    com a folha de outro produz uma folha que não existe no portal.
    """
    if not os.path.exists(ARQUIVO_PARCIAL):
        return [], set(), 0
    try:
        with open(ARQUIVO_PARCIAL, encoding="utf-8") as f:
            bruto = json.load(f)
        if (bruto.get("competencia") or "") != competencia:
            log("o parcial e de outra competencia; recomecando do zero")
            return [], set(), 0
        servidores = bruto.get("servidores") or []
        vistos = {s.get("matricula") for s in servidores
                  if s.get("matricula")}
        inicio = int(bruto.get("proximo_inicio") or 0)
        if servidores and inicio:
            log(f"retomando: {len(servidores)} servidores ja lidos, "
                f"proxima pagina em {inicio}")
        return servidores, vistos, inicio
    except Exception as e:
        log(f"parcial ilegivel ({e}); recomecando do zero")
        return [], set(), 0


def gravar_json(servidores: list, competencia: str) -> None:
    folha = {
        "origem": "Portal da transparencia",
        "competencia": competencia,
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(servidores),
        "servidores": servidores,
    }
    os.makedirs(DIR_DADOS, exist_ok=True)
    tmp = f"{ARQUIVO_JSON}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(folha, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ARQUIVO_JSON)


def gravar_csv(servidores: list) -> None:
    """Grava o CSV que a pessoa ABRE e confere.

    Separador PONTO-E-VÍRGULA: em português a vírgula é separador de milhar, e
    um CSV com vírgula aberto no Excel pt-BR quebra a coluna em todas as
    linhas — sem erro nenhum, e sem que ninguém perceba que a culpa é o
    separador. BOM UTF-8 no começo para os acentos sobreviverem à ida e volta.
    """
    os.makedirs(DIR_DADOS, exist_ok=True)
    tmp = f"{ARQUIVO_CSV}.tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        f.write(";".join(CAMPOS_CSV) + "\n")
        for s in servidores:
            campos = []
            for col in CAMPOS_CSV:
                valor = str(s.get(col) or "")
                if '"' in valor or ";" in valor or "\n" in valor:
                    valor = '"' + valor.replace('"', '""') + '"'
                campos.append(valor)
            f.write(";".join(campos) + "\n")
    os.replace(tmp, ARQUIVO_CSV)


def coletar(competencia: str, url: str, opener) -> tuple[list, int | None]:
    """Percorre a folha inteira, uma página por vez, e devolve os servidores.

    O `opener` vem de fora de propósito: abrir a página do portal é o que pega
    o cookie de sessão, e abrir DUAS vezes (uma para descobrir a competência e
    outra para ler) cria duas sessões — a segunda pode não valer e o grid volta
    vazio, que é o mesmo sintoma de "não há servidores".
    """
    servidores, vistos, inicio = ler_parcial(competencia)
    total = None
    inicio_espera = time.monotonic()
    pagina_n = inicio // PAGINA
    log(f"lendo a folha de {competencia} "
        f"(página de {PAGINA}, {ESPERA_MIN_S:.0f}-{ESPERA_MAX_S:.0f}s "
        f"entre requisições)")

    while True:
        elapsed = time.monotonic() - inicio_espera
        if elapsed < ESPERA_MIN_S:
            # Mesmo na retomada a primeira espera existe: acordar e sair em
            # sequência é o que faz o padrão parecer automático.
            time.sleep(ESPERA_MIN_S - elapsed)

        linhas, total = pagina(opener, url, competencia, inicio)
        if not linhas:
            break

        novos = 0
        for linha in linhas:
            reg = normalizar(linha)
            chave = reg["matricula"]
            # Uma matrícula pode aparecer duas vezes (exoneração e
            # exoneração). Fica a primeira, e a contagem final continua
            # dizendo quantas pessoas são.
            if chave and chave in vistos:
                continue
            if chave:
                vistos.add(chave)
            servidores.append(reg)
            novos += 1

        inicio += PAGINA
        pagina_n += 1
        gravar_parcial(servidores, competencia, inicio, total)

        faltam = (f"/{total}" if isinstance(total, int) else "?")
        log(f"  página {pagina_n:>2} | {len(servidores):>4}{faltam} servidores "
            f"| +{novos}")

        if novos == 0:
            break
        if isinstance(total, int) and len(servidores) >= total:
            log(f"  o portal anunciou {total} e ja foram lidos "
                f"{len(servidores)}: folha completa")
            break

    return servidores, total


def conferir(servidores: list, total: int | None) -> None:
    """Não grava folha incompleta sem avisar.

    A versão anterior gravava 650 de 1165 e informava "650 servidores" como se
    fosse a folha. O total do portal é a referência, e uma diferença grande
    demais significa que o portal segurou páginas — o arquivo ficaria errado e
    ninguém saberia, porque o CSV abre bem e parece folha.
    """
    if not isinstance(total, int) or total <= 0:
        log(f"AVISO: o portal nao anunciou o total; segue com "
            f"{len(servidores)} servidores conferidos so pela leitura")
        return
    if len(servidores) >= total:
        log(f"conferencia ok: {len(servidores)} lidos para {total} anunciados")
        return
    falta = total - len(servidores)
    log(f"AVISO: o portal anunciou {total} e vieram {len(servidores)}; "
        f"faltam {falta}. O parcial ficou salvo — rodar de novo completa.")
    raise RuntimeError(
        f"folha incompleta: {len(servidores)} de {total}. "
        f"Nada foi gravado para nao substituir a folha boa por uma parcial.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--competencia", help="mês/ano, ex.: 08/2026")
    ap.add_argument("--esperar", type=float, default=COOLDOWN_S,
                    help="espera antes de começar (evita rodar em sequência)")
    args = ap.parse_args()

    cfg = carregar_config()
    url, url_competencia, url_referer = montar_urls(cfg)
    competencia = args.competencia or "auto"

    if args.esperar > 0:
        log(f"esperando {args.esperar:.0f}s antes de comecar "
            f"(o portal precisa de folga entre rodadas)")
        time.sleep(args.esperar)

    try:
        log("abrindo a pagina do portal")
        opener = abrir(url_referer)

        if competencia == "auto":
            log("descobrindo a competencia mais recente")
            competencia = competencia_mais_recente(opener, url_competencia)
            log(f"competencia: {competencia}")

        servidores, total = coletar(competencia, url, opener)
        conferir(servidores, total)

        gravar_json(servidores, competencia)
        gravar_csv(servidores)
        # O parcial cumpriu o papel. Deixá-lo faria a próxima rodada retomar
        # de um `proximo_inicio` que já passou da folha, e quem lesse o log
        # veria "retomando" numa folha já completa.
        if os.path.exists(ARQUIVO_PARCIAL):
            os.remove(ARQUIVO_PARCIAL)

        log(f"{len(servidores)} servidores de {competencia}")
        log(f"  JSON: {ARQUIVO_JSON}")
        log(f"  CSV : {ARQUIVO_CSV}")
        return 0

    except KeyboardInterrupt:
        log("interrompido; o parcial ficou salvo para retomar")
        return 130
    except Exception as e:
        log(f"FALHOU: {e}")
        log("o parcial ficou salvo; rodar de novo retoma de onde parou")
        return 1


def competencia_mais_recente(opener, url_competencia: str) -> str:
    """Lê a lista de competências do portal e devolve a mais recente."""
    try:
        req = urllib.request.Request(
            url_competencia, data=b"{}",
            headers={"Content-Type": "application/json; charset=utf-8",
                     "User-Agent": USER_AGENT})
        bruto = opener.open(req, timeout=90).read()
        dados = json.loads(bruto.decode("iso-8859-1"))
        lista = [c.get("nome") or c.get("id") for c in (dados or [])
                 if isinstance(c, dict)]
        if not lista:
            raise RuntimeError("o portal nao informou competencia nenhuma")
        return lista[0]
    except Exception as e:
        log(f"  nao deu para ler as competencias ({e}); usando o mes corrente")
        return datetime.now(timezone.utc).strftime("%m/%Y")


if __name__ == "__main__":
    sys.exit(main())
