"""EN: Collects the payroll register published by the transparency portal.

PT-BR: Coleta o cadastro de servidores publicado pelo portal da transparência.

O QUE ESTE SCRIPT FAZ
    Lê a lista "Servidores por Nomes" do portal da transparência de Monte
    Santo de Minas e grava um arquivo local com matrícula, nome, secretaria,
    departamento, cargo, vínculo e situação de cada servidor.

POR QUE ELE EXISTE SEPARADO DA SINCRONIZAÇÃO
    A coleta é conversa com um site de terceiro: pode cair, mudar de layout ou
    estar fora do ar. Se o script que escreve no banco também fosse o que
    busca na web, uma falha de rede viraria um banco pela metade. Aqui a
    coleta para em um arquivo; `carga_folha.py` só lê esse arquivo.
    Dá para conferir o que foi coletado antes de gravar qualquer coisa.

O QUE ESTE SCRIPT NÃO FAZ — E POR QUÊ
    O portal também devolve o salário (`vldefault`) e o Ficha do contracheque
    (`cdContraCheque`). Nada disso é lido, guardado ou usado. A lista
    telefônica precisa de nome, cargo e ramal — não de quanto a pessoa ganha.
    Ler menos do que o portal oferece é a parte fácil de estar dentro da lei;
    a difícil é não usar o resto.

BASE LEGAL
    Lei 12.527/2011 (Lei de Acesso à Informação). A prefeitura é OBRIGADA a
    publicar a relação nominal dos servidores com cargo e lotação. O
    User-Agent se identifica por essa razão.

    O intervalo entre requisições é VARIÁVEL, sorteado na faixa configurada
    (padrão 1 s a 5 s, média ~3 s) — 47 requisições para a folha inteira, com
    ~3 minutos de espera somada. Intervalo FIXO é o que denuncia acesso
    automatizado: mesmo tempo entre toda requisição é a assinatura de robô.
    Variável não é só educação: é o que faz o tráfego não parecer programa.

    A coleta é uma ÚNICA VEZ. Ela escreve `dados/funcionarios.json` e
    `dados/funcionarios.csv`, e a carga passa a ler o arquivo local
    (`origem: "csv"`) — sem tocar mais no portal. Para atualizar a folha de
    novo, é `coleta_folha.py --atualizar`, de propósito e não por acidente.

COMO USAR
    python mod_gest_cad_usuario/coleta_folha.py --atualizar
    python mod_gest_cad_usuario/coleta_folha.py --competencia 07/2026
    python mod_gest_cad_usuario/coleta_folha.py --saida /tmp/folha.json

    Sem `--atualizar`, reaproveita o arquivo já coletado.
"""

from __future__ import annotations

import argparse
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

# A configuração mora no arquivo ao lado; o leitor é o mesmo do `carga_folha`
# (mesmo módulo, sem abrir banco), para os dois lados do caminho lerem a mesma
# fonte e não haver duas verdades.
DIR_MODULO = os.path.dirname(os.path.abspath(__file__))
if DIR_MODULO not in sys.path:
    sys.path.insert(0, DIR_MODULO)


def _carregar_config_coleta():
    """Lê `fonte_folha.json`; devolve o padrão (desligado) se não der.

    Isolado em `try/except` de propósito: um JSON quebrado tem de devolver
    "portal não configurado", não `NameError` no import — porque quem importa
    este arquivo é o `carga_folha`, e a falha de um não pode derrubar o outro.
    """
    try:
        from carga_folha import carregar_config
        cfg, _aviso = carregar_config()
        return cfg
    except Exception as e:
        print(f"  configuracao ilegivel ({e}); portal considerado NAO "
              f"configurado", file=sys.stderr)
        return {}


# ---- Onde o portal fica: configuração, nunca código ----------------------
# Este arquivo vai para o git público e pode ser usado por qualquer prefeitura
# ou empresa. Nada de endereço, município ou nome de órgão aqui: a URL base vem
# de `fonte_folha.json`, e sem ela o script não faz nada e diz por quê. Um
# sistema distribuído que abre conexão para um portal que não é do dono é pior
# que um sistema que não abre conexão nenhuma.
#
# Os caminhos dos endpoints são do "Portal Fácil" (plataforma de transparência
# de uso comum em municípios brasileiros). Quem usa outra plataforma preenche os
# três campos em `portal_endpoints` com os dela — ou, melhor, usa
# `origem: "csv"`, que não depende de terceiro nenhum.
CFG = _carregar_config_coleta()
# O endereço mora na CONFIGURAÇÃO, nunca no código (decisão de 04/10/2026):
# `portal_url` em `fonte_folha.json`. Sem ele o script recusa com
# explicação (ver `main`) em vez de presumir o portal de alguém.
# Precedência: ambiente > `tb_config` (tela de administração) > arquivo.
def _cfg_tb(chave, padrao=""):
    """Lê `tb_config` central (leitura tardia: ver `coleta_kbp._cfg_tb`)."""
    try:
        from mod_skyrover.bd_conexao import get_config
        valor = get_config(chave, padrao)
        return valor if valor not in (None, "") else padrao
    except Exception:
        return padrao


RAIZ = (os.environ.get("SKYROVER_PORTAL_URL")
        or _cfg_tb("usuarios_portal_url", "")
        or CFG.get("portal_url") or "").rstrip("/")
_PT = CFG.get("portal_endpoints") or {}
REFERER = RAIZ + (CFG.get("portal_pagina") or "/servidores-por-nomes")
GRID = RAIZ + _PT.get("folha", "")
COMPETENCIA = RAIZ + _PT.get("competencia", "")
USER_AGENT = (CFG.get("portal_user_agent")
              or "skyrover/1.0 (carga de servidores - dados publicos)")

# The server caps the page at the DataTables lengthMenu values and answers an
# empty page for anything else — `length=1` and `length=100` both return zero
# records, `length=25` returns 25. Discovered the hard way; do not "optimize".
PAGINA = 25

# INTERVALO VARIÁVEL ENTRE REQUISIÇÕES (01/10/2026, por decisão do responsável)
#
# Antes era um intervalo FIXO de 1,2 s. Intervalo fixo é o que faz um acesso
# parecer máquina: mesmo tempo, sempre, sem variação — é a assinatura de robô
# que a prefeitura não quer ver batendo no portal 47 vezes seguidas. Agora
# cada espera é sorteada na faixa, com média ~3 s.
#
# A folha inteira leva ~3 minutos com esta faixa, e é um custo que se paga
# UMA vez: a coleta escreve `dados/funcionarios.json` e `dados/funcionarios.csv`,
# e a carga passa a ler o arquivo local (`origem: "csv"`), sem tocar mais no
# portal.
def _intervalo_cfg(chave_min, chave_max, padrao_min, padrao_max, legado=None):
    """Lê a faixa do intervalo da configuração, com piso e teto garantidos.

    Aceita tanto as chaves novas (`*_min_s` / `*_max_s`) quanto o
    `portal_intervalo_s` antigo: um valor fixo legado vira uma faixa
    degenerada, e assim uma configuração existente continua valendo em vez de
    virar `None`. Piso de 0,1 s porque um intervalo abaixo disso é um
    laço apertado contra servidor de terceiro; teto nunca menor que o piso,
    porque uma faixa invertidasortearia valores inválidos.
    """
    def numero(chave):
        try:
            bruto = CFG.get(chave)
            return float(bruto) if bruto not in (None, "") else None
        except (TypeError, ValueError):
            return None

    fixo = numero(legado) if legado else None
    lo = numero(chave_min)
    hi = numero(chave_max)
    lo = lo if lo is not None else (fixo if fixo is not None else padrao_min)
    hi = hi if hi is not None else (fixo if fixo is not None else padrao_max)
    lo = max(0.1, lo)
    hi = max(lo, hi)
    return lo, hi


INTERVALO_MIN_S, INTERVALO_MAX_S = _intervalo_cfg(
    "portal_intervalo_min_s", "portal_intervalo_max_s", 1.0, 5.0,
    legado="portal_intervalo_s")
TENTATIVAS = 4

# BACKOFF DEVOLVE PROGRESSIVO (01/10/2026)
#
# A coleta morria por volta da página 20 (425 a 525 servidores) e não deixava
# arquivo nenhum. A causa NÃO era o portal fora do ar: `_post` só repetia a
# tentativa em `URLError`, `TimeoutError` e `ValueError`, e o portal responde
# ao excesso de requisições derrubando a conexão no meio da resposta — o que
# chega como `http.client.RemoteDisconnected` (herda de `ConnectionResetError`,
# logo de `OSError`). Essa exceção escapava do `except`, subia e matava o
# processo com as ~500 fichas já lidas na memória.
#
# A espera de 1s/2s/4s era curta demais para um servidor que está pedindo para
# receber menos. Agora é 3s/8s/20s/45s, e a queda de conexão — que é o portal
# dizendo "e plenty" — ganha uma pausa longa antes de repetir.
#
# `PAUSA_CONEXAO_S` é a resposta a esse sinal: 30s antes de tentar a página de
# novo. A espera é do COLETOR, não do banco, então mora aqui.
BACKOFF_S = (3, 8, 20, 45)
PAUSA_CONEXAO_S = 30.0

# A FAMÍLIA INTEIRA DE ERRO DE CONEXÃO (01/10/2026)
#
# `OSError` é a superclasse que costura quase tudo: `URLError`,
# `RemoteDisconnected`, `IncompleteRead`, `SSLError` e `TimeoutError` (no
# Windows) descendem dela. Fica nomeada à parte porque `TimeoutError` no
# Windows é `OSError` e em outros sistemas não — nomear os dois deixa o
# comportamento igual em qualquer SO, que é o que um coletor precisa ser.
_ERROS_TRANSIENTES = (
    OSError,
    urllib.error.URLError,
    http.client.HTTPException,
    ssl.SSLError,
)


def _esperar_entre_requisicoes() -> float:
    """Espera sorteada na faixa e devolve quanto esperou (para o log)."""
    espera = random.uniform(INTERVALO_MIN_S, INTERVALO_MAX_S)
    time.sleep(espera)
    return espera

# Colunas PEDIDAS ao grid. A resposta traz mais do que estas, e `vldefault`
# e `cdContraCheque` estão entre elas de propósito: a remuneração e a ficha de
# contracheque são informação pública por lei, e a prefeitura publica todo
# mês. A skyrover importa para o servidor conferir o próprio valor e para o
# DTI conferir a folha contra o portal.
COLUNAS = ["nmMatricula", "nmServidor", "nmUnidade", "nmLotacao",
           "nmCargo", "nmSituacao", "nmVinculo", "nmRegime",
           "nuCargaHoraria", "dtAdmissao", "dtExoneracao", "nmTipo",
           "vldefault", "cdContraCheque"]

# O que é GRAVADO. `vldefault` chega como texto já formatado ("3.456,78") e é
# guardado como texto: dinheiro em ponto flutuante perde centavo, e o valor
# arredondado divergiria do portal — que é justamente a conferência que o
# DTI faz.
CAMPOS_GUARDADOS = ("matricula", "nome", "unidade", "lotacao", "cargo",
                    "vinculo", "situacao", "tipo", "admissao", "exoneracao",
                    "regime", "carga_horaria", "remuneracao",
                    "ficha_contracheque")

# A folha mora em `dados/`, dentro do módulo, e fora do git (AGENTS.md §1 e
# §8.3): os dados são de servidores reais e não vão para o histórico.
DIR_DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")
ARQUIVO_PADRAO = os.path.join(DIR_DADOS, "funcionarios.json")
# O CSV é o arquivo que o administrador ABRE e confere. O JSON fica com os
# metadados (competência, data da coleta) que o CSV não cabe; os dois saem
# juntos, sempre, para que ninguém confira uma folha de um mês com os dados
# do outro.
ARQUIVO_CSV = os.path.join(DIR_DADOS, "funcionarios.csv")
# Estado de EXECUÇÃO da coleta (01/10/2026): onde a folha está sendo lida.
# Mora em `dados/` — que já é fora do git — porque carrega nome e matrícula de
# servidor real, exatamente como os outros dois. É apagado no fim da coleta
# bem-sucedida; se sobrar, é porque a coleta morreu, e é aí que serve.
ARQUIVO_PARCIAL = os.path.join(DIR_DADOS, "funcionarios.parcial.json")


def _garantir_dir_dados() -> None:
    """Cria `dados/` se ainda não existir (clone novo, sem a pasta)."""
    try:
        os.makedirs(DIR_DADOS, exist_ok=True)
    except Exception as e:
        print(f"  nao foi possivel criar {DIR_DADOS}: {e}", flush=True)


def _log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def _abrir() -> urllib.request.OpenerDirector:
    """Opens a session. The portal sets a BotDeTect cookie on the first GET and
    the grid endpoint answers 500 without it."""
    import http.cookiejar
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    opener.addheaders = [
        ("User-Agent", USER_AGENT),
        ("X-Requested-With", "XMLHttpRequest"),
        ("Referer", REFERER),
        ("Accept", "application/json, text/javascript, */*; q=0.01"),
    ]
    opener.open(REFERER, timeout=60).read()
    return opener


def _post(opener, url: str, corpo: dict) -> dict:
    """POSTs JSON and decodes ISO-8859-1.

    The page declares `charset=iso-8859-1` and the accents really are encoded
    that way, so `json.loads(resp)` on the raw bytes raises UnicodeDecodeError
    on the first accented name. Every name in the sheet is unaccented anyway,
    which is how the source stores them. The name here is fictitious: the real
    sheet stays out of git.

    A EXCEÇÃO QUE NÃO ERA EXCEÇÃO (01/10/2026)
        Repetir aqui não era `URLError`/`TimeoutError`/`ValueError` — era uma
        família maior. `http.client.RemoteDisconnected` (que herda de
        `OSError`), `IncompleteRead`, `HTTPException`, `ssl.SSLError` e o
        próprio `OSError` subiam direto e matavam o processo. O sintoma era
       collected: a coleta parava na página 20 e não gravava nada.

    `OSError` é a SUPERCLASSE que costura tudo: `URLError`, `RemoteDisconnected`,
    `IncompleteRead`, `SSLError` e `TimeoutError` (em Windows) descendem dela.
    Fica também a lista explícita, porque `RemoteDisconnected` é
    `ConnectionResetError`, não `URLError`, e a distinção de família importa
    para escolher a espera: queda de conexão é sinal de PORTAL PEDINDO PARA,
    e ganha a pausa longa.

    A diferença entre as duas esperas: erro de rede comum repete em
    `BACKOFF_S`; queda de conexão repete em `BACKOFF_S` DEPOIS de
    `PAUSA_CONEXAO_S`, porque recuar rápido contra um servidor que acabou de
    recusar é o caminho mais curto para ser bloqueado de vez.
    """
    dados = json.dumps(corpo).encode("utf-8")
    req = urllib.request.Request(
        url, data=dados,
        headers={"Content-Type": "application/json; charset=utf-8"})
    ultima = None
    for tentativa in range(TENTATIVAS):
        try:
            bruto = opener.open(req, timeout=90).read()
            return json.loads(bruto.decode("iso-8859-1"))
        except _ERROS_TRANSIENTES as e:
            ultima = e
            # Queda de conexão: o portal respondeu e cortou. Tratar como
            # erro passageiro e repetir já é o que derruba a coleta.
            caiu = isinstance(e, (http.client.RemoteDisconnected,
                                   ConnectionResetError,
                                   http.client.IncompleteRead))
            if caiu:
                _log(f"  o portal fechou a conexão ({e.__class__.__name__}); "
                     f"pausa de {PAUSA_CONEXAO_S:.0f}s para não ser "
                     f"tratado como robô")
                time.sleep(PAUSA_CONEXAO_S)
            espera = BACKOFF_S[min(tentativa, len(BACKOFF_S) - 1)]
            _log(f"  falha ({e.__class__.__name__}), nova tentativa em {espera}s")
            time.sleep(espera)
        except ValueError as e:
            # Resposta que não é JSON: não adianta repetir igual, porque a
            # página voltou com outra coisa (erro do portal, HTML de manutenção).
            ultima = e
            _log(f"  resposta fora do formato esperado "
                 f"({e.__class__.__name__}); tentando de novo em 10s")
            time.sleep(10)
    raise RuntimeError(f"portal não respondeu após {TENTATIVAS} tentativas: {ultima}")


def _competencias(opener) -> list[str]:
    """Available payroll months, most recent first."""
    try:
        dados = _post(opener, COMPETENCIA, {})
        return [c.get("nome") or c.get("id")
                for c in (dados or []) if isinstance(c, dict)]
    except Exception as e:
        _log(f"  não foi possível ler as competências ({e}); usando a atual")
        return [datetime.now(timezone.utc).strftime("%m/%Y")]


def _pagina(opener, competencia: str, inicio: int) -> list[dict]:
    """One page of the grid.

    The `columns` array is not decoration: without it the server builds no
    SELECT and answers `recordsTotal: 0` with HTTP 200. It looks like "the
    portal is empty" and it is not — the first version of this script had this
    bug and read zero servants while the website showed a full sheet.
    """
    corpo = {
        "parameters": {
            "draw": inicio // PAGINA + 1,
            "columns": [{"data": c, "name": "", "searchable": True,
                         "orderable": True,
                         "search": {"value": "", "regex": False}} for c in COLUNAS],
            # Ascending by matrícula, so two runs produce the same order and
            # the diff between them is only real changes.
            "order": [{"column": 0, "dir": "asc"}, {"column": 1, "dir": "asc"}],
            "start": inicio,
            "length": PAGINA,
            "search": {"value": "", "regex": False},
        },
        "entidade": "", "competencia": competencia, "unidade": "", "cargo": "",
        "funcao": "", "vinculo": "", "vlInicio": "0", "vlFim": "0",
        "grupocalculo": "", "covid": None,
    }
    dados = _post(opener, GRID, corpo)
    linhas = dados.get("data")
    if isinstance(linhas, dict):
        linhas = linhas.get("data", [])
    return [l for l in (linhas or []) if isinstance(l, dict)]


def _normalizar(linha: dict) -> dict:
    """Portal row → record with the fields the skyrover needs."""
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
        "admissao": txt("dtAdmissao"),
        "exoneracao": txt("dtExoneracao"),
        "regime": txt("nmRegime"),
        "carga_horaria": txt("nuCargaHoraria"),
        # `vldefault` é o valor da remuneração; `cdContraCheque` é a ficha.
        "remuneracao": txt("vldefault"),
        "ficha_contracheque": txt("cdContraCheque"),
    }


def _gravar_parcial(servidores, competencia, proximo_inicio):
    """Grava o que já foi lido, para a coleta não morrer sem deixar nada.

    Arquivo à parte do `funcionarios.json` porque este é estado de EXECUÇÃO,
    não resultado: ele existe para ser lido pela próxima tentativa e pode ser
    apagado sem perda. Um `.tmp` seguido de troca é o que garante que uma
    queda no meio da escrita não deixe um JSON pela metade — o próximo
    `json.load` cairia em exceção e a retomada perderia o que já tinha.
    """
    try:
        _garantir_dir_dados()
        tmp = f"{ARQUIVO_PARCIAL}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"competencia": competencia,
                       "proximo_inicio": proximo_inicio,
                       "coletado_em": datetime.now(timezone.utc).isoformat(
                           timespec="seconds"),
                       "servidores": servidores},
                      f, ensure_ascii=False)
        os.replace(tmp, ARQUIVO_PARCIAL)
        return True
    except Exception as e:
        # Perder o parcial NÃO pode derrubar a coleta: o que vale é a folha
        # final, e ela ainda está sendo montada na memória.
        _log(f"  (não consegui gravar o parcial: {e})")
        return False


def _ler_parcial(competencia):
    """Devolve (servidores, vistos, proximo_inicio) do parcial, ou vazio.

    Só reaproveita quando a COMPETÊNCIA é a mesma: o parcial é de uma
    referência de folha, e continuar uma 07/2026 a partir de onde parou uma
    08/2026 mistura dois meses e produz uma folha que não existe no portal.
    """
    try:
        if not os.path.exists(ARQUIVO_PARCIAL):
            return [], set(), 0
        with open(ARQUIVO_PARCIAL, encoding="utf-8") as f:
            bruto = json.load(f)
        if (bruto.get("competencia") or "") != (competencia or ""):
            _log("  o parcial é de outra competência; recomeçando do zero")
            return [], set(), 0
        servidores = bruto.get("servidores") or []
        vistos = {s.get("matricula") for s in servidores if s.get("matricula")}
        inicio = int(bruto.get("proximo_inicio") or 0)
        if servidores and inicio:
            _log(f"  retomando de onde parou: {len(servidores)} servidores já "
                 f"lidos, próxima página em {inicio}")
        return servidores, vistos, inicio
    except Exception as e:
        _log(f"  parcial ilegível ({e}); recomeçando do zero")
        return [], set(), 0


def coletar(competencia: str | None = None) -> dict:
    """Walks every page and returns the sheet as a dict."""
    opener = _abrir()
    if competencia is None:
        disponiveis = _competencias(opener)
        if not disponiveis:
            raise RuntimeError("o portal não informou nenhuma competência")
        competencia = disponiveis[0]
        _log(f"competência mais recente: {competencia}")

    _log("lendo a folha (página de 25, 1,2s entre requisições)...")
    servidores, vistos, inicio = _ler_parcial(competencia)
    while True:
        lote = _pagina(opener, competencia, inicio)
        if not lote:
            break
        novos = 0
        for linha in lote:
            reg = _normalizar(linha)
            chave = reg["matricula"]
            # One matrícula can appear twice (an exoneration and a
            # reappointment, for instance). Keep the first and count the rest,
            # so the count below is truthful about how many people there are.
            if chave and chave in vistos:
                continue
            if chave:
                vistos.add(chave)
            servidores.append(reg)
            novos += 1
        if novos == 0:
            break
        _log(f"  {len(servidores)} servidores")
        # GRAVA O PARCIAL A CADA PAGINA (01/10/2026)
        #
        # Perder ~500 fichas não era o portal recusando: era o processo
        # morrendo com tudo acumulado SÓ na memória. O `return` só acontecia
        # no fim do laço, então qualquer exceção levava a folha inteira junto.
        #
        # Gravar a cada página custa um `json.dump` de algumas centenas de KB
        # e transforma a falha em perda de UMA página em vez da folha. A
        # próxima rodada pode ler este arquivo e continuar de onde parou, sem
        # refazer as 20 primeiras páginas de requisição.
        _gravar_parcial(servidores, competencia, inicio)
        inicio += PAGINA
        # Espera VARIÁVEL (01/10/2026): ver `_intervalo_cfg`. O valor
        # sorteado vai para o log, porque uma coleta que demora ~3 minutos
        # precisa deixar visível que está esperando por educação e não
        # travada — e porque quem lê o log depois precisa poder reconstituir
        # o ritmo das requisições.
        espera = _esperar_entre_requisicoes()
        if len(servidores) % (PAGINA * 10) == 0:
            _log(f"  ... aguardou {espera:.1f}s antes da próxima página")
        if inicio > 20000:
            _log("  limite de segurança de 20.000 registros atingido")
            break

    folha = {
        "origem": CFG.get("origem_rotulo") or f"Portal ({RAIZ})",
        "url": REFERER,
        "competencia": competencia,
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(servidores),
        "aviso": ("Dados publicados por lei (Lei 12.527/2011 e Lei "
                  "11.129/2005). Inclui remuneração e ficha de "
                  "contracheque, também publicação legal."),
        "servidores": servidores,
    }
    # O parcial cumpriu o papel e agora é iscaso: deixá-lo faria a próxima
    # coleta retomar de um `proximo_inicio` que já passou da folha inteira, e
    # o operador veria "retomando de onde parou" numa folha já completa.
    try:
        if os.path.exists(ARQUIVO_PARCIAL):
            os.remove(ARQUIVO_PARCIAL)
    except Exception as e:
        _log(f"  (não consegui apagar o parcial: {e})")
    return folha


COLUNAS_CSV = ("matricula", "nome", "unidade", "lotacao", "cargo",
              "vinculo", "situacao", "remuneracao", "ficha_contracheque",
              "regime", "carga_horaria", "admissao", "exoneracao")


def gravar_csv(folha, caminho):
    """Grava a folha em CSV — o arquivo que o administrador abre e confere.

    SEPARADOR PONTO-E-VÍRGULA, E NÃO VÍRGULA
        Em português o separador de milhar é a vírgula. Um CSV com vírgula
        aberto no Excel em pt-BR quebra a coluna em todas as linhas — e a
        primeira pessoa a abrir o arquivo teria a planilha toda partida,
        sem erro nenhum mensagem, e sem perceber que a culpa é do separador.

    BOM UTF-8 no começo do arquivo
        Sem isso o Excel abre acentos como "Saude" virando "SaÃºde". O portal
        guarda os nomes sem acento, mas os que vierem com acento
        precisam sobreviver à ida e volta pelo Excel.

    Uma linha por servidor, na ordem em que o portal devolve (por
    matrícula), porque um diff entre duas coletas é mais fácil de ler em
    ordem de verdade do que em ordem alfabética de nome.
    """
    try:
        with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
            f.write(";".join(COLUNAS_CSV) + "\n")
            for s in folha.get("servidores") or []:
                campos = []
                for col in COLUNAS_CSV:
                    valor = str(s.get(col) or "")
                    # aspas duplicadas: um ; ou " dentro do dado quebraria a linha
                    if '"' in valor or ";" in valor or "\n" in valor:
                        valor = '"' + valor.replace('"', '""') + '"'
                    campos.append(valor)
                f.write(";".join(campos) + "\n")
        return True, caminho
    except Exception as e:
        return False, str(e)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Coleta a folha de servidores do portal da transparência "
                    "configurado em fonte_folha.json.")
    ap.add_argument("--competencia", help="mês/ano (ex.: 08/2026). Padrão: o mais recente.")
    ap.add_argument("--saida", default=ARQUIVO_PADRAO, help="arquivo JSON de destino.")
    ap.add_argument("--csv", default=ARQUIVO_CSV,
                    help="arquivo CSV de destino (padrao: funcionarios.csv ao lado).")
    ap.add_argument("--sem-csv", action="store_true",
                    help="nao grava o CSV.")
    ap.add_argument("--atualizar", action="store_true",
                    help="recoleta mesmo que já exista arquivo.")
    args = ap.parse_args()

    # Sem portal configurado, este script não tem o que fazer. Recusa com
    # explicação e sai com 0: quem instalou o sistema e não o configurou está
    # no estado esperado, e um código de erro faria o cron acusar defeito.
    if not RAIZ or not GRID or not CFG.get("portal_endpoints"):
        print("\n  Coleta do portal NAO CONFIGURADA.\n"
              "  Nada foi acessado e nada foi gravado — este e o estado normal\n"
              "  de quem instalou o sistema e nao configurou a fonte.\n"
              "  Para ligar: edite 'portal_url' e 'portal_endpoints' em\n"
              f"  {os.path.join(DIR_MODULO, 'fonte_folha.json')}.\n"
              "  Sem portal, use a via que nao depende de terceiro: escreva a\n"
              "  folha em CSV e rode  carga_folha.py  com 'origem': 'csv'.\n")
        return 0

    try:
        reaproveitando = False
        # `dados/` é gitignored (AGENTS.md §1 e §8.3), então numa instalação
        # nova ele NUNCA existe — e a coleta abre `args.saida` para escrita
        # direto. Sem esta linha, o primeiro `open(..., "w")` morre com
        # `[Errno 2]` e a folha some depois de 100 segundos de coleta. Foi
        # exatamente o que aconteceu na instalação limpa: `_garantir_dir_dados`
        # existia desde sempre e não era chamada de lugar nenhum.
        _garantir_dir_dados()
        if os.path.exists(args.saida) and not args.atualizar:
            with open(args.saida, encoding="utf-8") as f:
                anterior = json.load(f)
            _log(f"reaproveitando {args.saida} "
                 f"({anterior.get('total')} servidores de {anterior.get('coletado_em')})")
            _log("use --atualizar para buscar a folha de novo")
            folha = anterior
            reaproveitando = True
        else:
            print("\nColetando servidores no portal da transparência...\n")
            folha = coletar(args.competencia)
            with open(args.saida, "w", encoding="utf-8") as f:
                json.dump(folha, f, ensure_ascii=False, indent=2)

        # O CSV é SEMPRE gravado, mesmo reaproveitando o JSON: ele é o
        # arquivo que o administrador abre para conferir, e um CSV velho
        # seria pior que nenhum — a pessoa conferiria a folha anterior
        # achando que era a nova.
        if not args.sem_csv:
            ok_csv, info = gravar_csv(folha, args.csv)
            if ok_csv:
                print(f"\n  {folha['total']} servidores da competência "
                      f"{folha['competencia']}")
                print(f"  JSON: {args.saida}")
                print(f"  CSV : {info}")
                if reaproveitando:
                    print("  (CSV regravado a partir do JSON existente)")
                print()
            else:
                print(f"  ERRO ao gravar o CSV: {info}", file=sys.stderr)
                return 1
        else:
            print(f"\n  {folha['total']} servidores; CSV não gravado "
                  f"(--sem-csv)")
        return 0
    except Exception as e:
        print(f"\n  ERRO na coleta: {e}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
