# -*- coding: utf-8 -*-
"""EN: Collects each servant's paycheck detail (masked CPF + earnings).

PT-BR: Coleta a ficha de cada servidor (CPF parcial + vencimentos).

O QUE ESTE SCRIPT FAZ
    Lê `dados/funcionarios.json` (a folha já coletada) e, para cada ficha
    (`ficha_contracheque`, formato AAAAMM + matrícula), abre o detalhe
    `ServidorDetalhes` do portal e grava `dados/funcionarios_detalhe.json`
    + `dados/funcionarios_detalhe.csv` (as MESMAS informações, UMA LINHA
    POR FICHA — um servidor por linha, com as verbas em JSON na coluna
    `verbas`). O detalhe traz o CPF PARCIAL
    (`nuCPF`, ex.: `***.273.866-**` — o portal nunca mostra o número
    inteiro), nascimento, base, proventos, descontos, líquido e a lista
    de verbas (`lstItens`: código, descrição, referência, tipo, valor).

POR QUE CPF PARCIAL BASTA
    O confronto que interessa é entre contratos com o MESMO nome: mesma
    pessoa tem o mesmo meio de CPF; homônimos têm meios diferentes. Seis
    dígitos centrais iguais por acaso em dois homônimos é improvável o
    bastante para decidir, e o que sobrar vai para revisão humana com a
    evidência ao lado — que é onde a decisão pertence.

RITMO HUMANO (uma vez por mês, sem pressa)
    Uma ficha por vez, espera VARIÁVEL sorteada entre
    `detalhe_intervalo_min_s` e `detalhe_intervalo_max_s` de
    `fonte_folha.json` (padrão 2 s a 6 s, média ~4 s — a folha inteira
    leva ~80 min). Intervalo fixo é assinatura de robô; variável não é
    só educação, é o que faz o tráfego parecer gente. A captura pode
    levar horas sem problema: roda em processo próprio, não escreve no
    banco (só em `dados/`), então roda em paralelo com o sistema no ar.
    Dá para interromper e continuar: o parcial
    (`funcionarios_detalhe.parcial.json`) guarda o que já foi lido, na
    mesma competência, e a próxima rodada continua de onde parou.

COMO USAR
    python mod_gest_cad_usuario/coleta_kbp.py --atualizar
    python mod_gest_cad_usuario/coleta_kbp.py --max 2 --atualizar
    python mod_gest_cad_usuario/coleta_kbp.py --entrada /tmp/folha.json

    Sem `--atualizar`, reaproveita o arquivo já coletado (e regrava os
    CSVs a partir dele). `--max N` limita a N fichas (para testar o
    ritmo e o formato sem buscar a folha inteira).

    Exemplo de ficha (número INVENTADO, nunca usar matrícula real aqui):
    cd=202609MT-1234
"""

from __future__ import annotations

import argparse
import http.client
import http.cookiejar
import json
import os
import random
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone

DIR_MODULO = os.path.dirname(os.path.abspath(__file__))
if DIR_MODULO not in sys.path:
    sys.path.insert(0, DIR_MODULO)


def _carregar_config():
    """Lê `fonte_folha.json`; devolve {} se não der (portal desligado)."""
    try:
        from carga_folha import carregar_config
        cfg, _aviso = carregar_config()
        return cfg or {}
    except Exception as e:
        print(f"  configuracao ilegivel ({e}); portal considerado NAO "
              f"configurado", file=sys.stderr)
        return {}


CFG = _carregar_config()
# O endereço mora na CONFIGURAÇÃO, nunca no código (decisão de 04/10/2026:
# este arquivo vai para o git e não pode amarrar o sistema a um órgão).
# Quem usa preenche `portal_url` em `fonte_folha.json`. A variável de
# ambiente vence o arquivo: permite rodar sem editar um config versionado
# (ex.: teste pontual sem amarrar o clone ao órgão).
def _cfg_tb(chave, padrao=""):
    """Lê `tb_config` central (o que a tela de administração grava).

    A tela do módulo grava `usuarios_portal_url` e os intervalos aqui —
    e o arquivo `fonte_folha.json` vira o fallback, não a verdade. Leitura
    tardia (dentro da função) de propósito: importar `bd_conexao` no topo
    acoplaria o coletor ao banco no import, e quem importa este arquivo é
    o `carga_folha`.
    """
    try:
        from mod_tisosdocfly.bd_conexao import get_config
        valor = get_config(chave, padrao)
        return valor if valor not in (None, "") else padrao
    except Exception:
        return padrao


RAIZ = (os.environ.get("TISOSDOCFLY_PORTAL_URL")
        or _cfg_tb("usuarios_portal_url", "")
        or CFG.get("portal_url") or "").rstrip("/")
_PT = CFG.get("portal_endpoints") or {}
REFERER = RAIZ + (CFG.get("portal_pagina") or "/servidores-por-nomes")
DETALHE = RAIZ + _PT.get(
    "detalhe",
    "/transparencia/servidor/tpc_servidor_data.ashx?metodo=ServidorDetalhes")
USER_AGENT = (CFG.get("portal_user_agent")
              or "tisosdocfly/1.0 (carga de servidores - dados publicos)")


def _numero(chave, padrao):
    """Lê um número da configuração, com piso de 0,1 s (AGENTS §3.2).

    A tela de administração grava `usuarios_<chave>` na `tb_config`
    central, e ela vence o arquivo — é o que faz o intervalo editado na
    tela valer na próxima coleta sem tocar em config versionado.
    """
    try:
        bruto = _cfg_tb("usuarios_" + chave, None)
        if bruto in (None, ""):
            bruto = CFG.get(chave)
        valor = float(bruto) if bruto not in (None, "") else padrao
        return max(0.1, valor)
    except (TypeError, ValueError):
        return padrao


# Faixa de espera ENTRE FICHAS (09/10/2026, a pedido do responsável):
# variável de propósito (ver docstring), configurável sem tocar no código.
# Padrão 2–6 s: ~4 s por ficha, ~80 min para a folha inteira, uma vez/mês.
INTERVALO_MIN_S = _numero("detalhe_intervalo_min_s", 2.0)
INTERVALO_MAX_S = _numero("detalhe_intervalo_max_s", 6.0)
if INTERVALO_MAX_S < INTERVALO_MIN_S:
    INTERVALO_MAX_S = INTERVALO_MIN_S
TENTATIVAS = 4
BACKOFF_S = (3, 8, 20, 45)
PAUSA_CONEXAO_S = 30.0
# Acima disso, uma ficha está lenta e a coleta avisa que continua viva.
LIMITE_BATIMENTO_S = 20.0

_ERROS_TRANSIENTES = (
    OSError,
    urllib.error.URLError,
    http.client.HTTPException,
    ssl.SSLError,
)

DIR_DADOS = os.path.join(DIR_MODULO, "dados")
ARQUIVO_ENTRADA = os.path.join(DIR_DADOS, "funcionarios.json")
ARQUIVO_PADRAO = os.path.join(DIR_DADOS, "funcionarios_detalhe.json")
ARQUIVO_CSV = os.path.join(DIR_DADOS, "funcionarios_detalhe.csv")
ARQUIVO_PARCIAL = os.path.join(DIR_DADOS, "funcionarios_detalhe.parcial.json")
# Progresso para a TELA ler enquanto a captura corre. É um arquivo PEQUENO e
# separado do parcial por um motivo concreto: o parcial só é gravado a cada 5
# fichas (e tem o peso da folha inteira), então a tela mostraria "último
# coletado" com até 5 fichas de atraso — justamente o número que a pessoa
# quer ver para saber se ainda está andando. Aqui é um JSON de poucas linhas,
# reescrito a cada ficha, e a tela lê direto.
ARQUIVO_PROGRESSO = os.path.join(DIR_DADOS, "coleta_progresso.json")

# O CPF é o que separa homônimo de mesma pessoa, então é campo OBRIGATÓRIO
# da captura: se a ficha volta sem ele, a linha entra assim mesmo e a coleta
# AVISA — porque um `SEM_CPF` silencioso só apareceria no relatório final,
# depois de uma hora de coleta, e é exatamente o defeito que ninguém enxerga.
# `n_itens` vai junto porque confere de relance quantas verbas a linha
# carrega. JSON em célula de CSV é opaco no Excel, mas é exato — e exatidão
# é o que o confronto precisa.
CAMPOS_FICHA_CSV = ("ficha", "matricula", "nome", "cpf_parcial",
                    "nascimento", "unidade", "lotacao", "cargo", "funcao",
                    "vinculo", "situacao", "regime", "tipo", "competencia",
                    "admissao", "exoneracao", "termino_contrato",
                    "carga_horaria", "carga_horaria_mensal", "salario_base",
                    "proventos", "descontos", "liquido", "grupo_calculo",
                    "n_itens", "verbas")

# ================== EVENTOS (loguru) ==================
# A coleta é um trabalho de HORAS que roda em segundo plano (ver `--popular`
# no `main.py`). Sem evento datado, a pessoa que olha o terminal não sabe
# dizer se o script está vivo, travado ou já acabou — e o sintoma disso é
# sempre o mesmo: alguém abre o `.log`, vê a última linha de uma hora atrás
# e reinicia uma coleta que estava Indo.
#
# O loguru entra aqui em vez do `observabilidade` do `mod_tisosdocfly` de
# propósito: este script roda como SUBPROCESS, fora do servidor, e não pode
# arrastar o núcleo (e o banco dele) só para escrever no terminal. Loguru
# puro, com sink de console e um de arquivo.
from loguru import logger as _logger

_FMT_EVENTO = ("<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | "
               "<level>{message}</level>")
_FMT_ARQUIVO = ("{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
                "{name}:{function}:{line} | {message}")
ARQUIVO_LOG = os.path.join(DIR_DADOS, "coleta_detalhe.log")


def _configurar_eventos():
    """Liga os sinks do loguru. Idempotente (chamar duas vezes não duplica).

    Console em `sys.stdout` — é o que o `--popular` mostra no terminal — e
    arquivo em `dados/coleta_detalhe.log`, que sobrevive ao fechamento do
    terminal. O `enqueue=False` é o que garante a linha na tela IMEDIATAMENTE:
    o coletor é iniciado com a saída em arquivo, e quem o acompanha com
    `tail -f` precisa ver a ficha chegando, não um lote minutos depois.
    """
    try:
        os.makedirs(DIR_DADOS, exist_ok=True)
    except Exception:
        pass
    _logger.remove()
    _logger.add(sys.stdout, level="INFO", format=_FMT_EVENTO,
                colorize=True, enqueue=False)
    try:
        _logger.add(ARQUIVO_LOG, level="DEBUG", format=_FMT_ARQUIVO,
                    encoding="utf-8", enqueue=False)
    except Exception as e:
        # Sem arquivo ainda vale o console: a coleta é o que importa, e o
        # log em arquivo é conforto, não requisito.
        _logger.warning(f"não consegui abrir o log em arquivo: {e}")
    return _logger


def _log(msg):
    """Linha de progresso no console — compatível com o uso antigo.

    Mantida porque o script inteiro já chama `_log`, e trocar todas as
    chamadas agora seria mexer em código que funciona. O que muda é que
    `_log` agora passa pelo loguru, então ganha carimbo de hora e nível.
    """
    try:
        _logger.info(msg)
    except Exception:
        try:
            print(f"  {msg}", flush=True)
        except Exception:
            pass


def mascarar_cpf(valor):
    """CPF em `***DDD.DDD***` — os 6 primeiros dígitos, o resto coberto.

    O PORTAL já entrega o CPF parcial (`nuCPF`), normalmente `***.273.866-**`
    (mexe no MEIO). O responsável pediu explicitamente o formato
    `***047.273***`, que mostra o INÍCIO em vez do meio — e o início serve
    igual para separar homônimos, com a vantagem de ser o que o técnico
    reconhece de cara.

    Robustude: o portal pode devolver 11 dígitos (CPF inteiro, o que não
    deveria acontecer), 6 (já parcial), ou nada. Cada caso vira o máximo de
    dígitos que existe, sem inventar número.
    """
    try:
        digitos = "".join(ch for ch in str(valor or "") if ch.isdigit())
        if not digitos:
            return "—"
        if len(digitos) > 6:
            digitos = digitos[:6]
        return "***" + digitos[:3] + "." + digitos[3:6] + "***"
    except Exception:
        return "—"


def _txt(valor):
    """Texto limpo ou None (campo vazio do portal não vira string)."""
    try:
        texto = (valor or "").strip() if isinstance(valor, str) else valor
        return texto or None
    except Exception:
        return None


def _nome_normalizado(nome):
    """Normaliza para agrupar contratos da mesma pessoa (AGENTS §3.2)."""
    try:
        base = unicodedata.normalize(
            "NFKD", str(nome or "")).encode("ascii", "ignore").decode()
        return " ".join(base.upper().split())
    except Exception:
        return str(nome or "").upper().strip()


def _abrir():
    """Abre a sessão (o portal põe cookie BotDeTect no primeiro GET)."""
    try:
        cookies = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookies))
        opener.addheaders = [
            ("User-Agent", USER_AGENT),
            ("X-Requested-With", "XMLHttpRequest"),
            ("Referer", REFERER),
            ("Accept", "application/json, text/javascript, */*; q=0.01"),
        ]
        opener.open(REFERER, timeout=60).read()
        return opener
    except Exception as e:
        raise RuntimeError(f"portal não abriu sessão: {e}")


def _esperar():
    """Espera sorteada na faixa; devolve quanto esperou (para o log)."""
    try:
        espera = random.uniform(INTERVALO_MIN_S, INTERVALO_MAX_S)
    except Exception:
        espera = 4.0
    try:
        time.sleep(espera)
    except Exception:
        pass
    return espera


def _buscar_ficha(opener, ficha):
    """POST ServidorDetalhes para UMA ficha; devolve o dict do portal.

    Mesma família de erro transitório e mesmo backoff da coleta da
    folha: queda de conexão é o portal pedindo menos, e ganha a pausa
    longa antes de repetir — recuar rápido é o caminho para bloqueio.
    """
    try:
        url = DETALHE + "&cdContraCheque=" + str(ficha)
        corpo = json.dumps({}).encode("utf-8")
        req = urllib.request.Request(
            url, data=corpo,
            headers={"Content-Type": "application/json; charset=utf-8"})
        ultima = None
        for tentativa in range(TENTATIVAS):
            try:
                bruto = opener.open(req, timeout=90).read()
                dados = json.loads(bruto.decode("iso-8859-1"))
                return dados if isinstance(dados, dict) else {}
            except _ERROS_TRANSIENTES as e:
                ultima = e
                caiu = isinstance(e, (http.client.RemoteDisconnected,
                                       ConnectionResetError,
                                       http.client.IncompleteRead))
                if caiu:
                    _log(f"  {ficha}: o portal fechou a conexão; "
                         f"pausa de {PAUSA_CONEXAO_S:.0f}s")
                    try:
                        time.sleep(PAUSA_CONEXAO_S)
                    except Exception:
                        pass
                espera = BACKOFF_S[min(tentativa, len(BACKOFF_S) - 1)]
                _log(f"  {ficha}: falha ({e.__class__.__name__}), "
                     f"nova tentativa em {espera}s")
                try:
                    time.sleep(espera)
                except Exception:
                    pass
            except ValueError as e:
                ultima = e
                _log(f"  {ficha}: resposta fora do formato; de novo em 10s")
                try:
                    time.sleep(10)
                except Exception:
                    pass
        raise RuntimeError(
            f"portal não respondeu após {TENTATIVAS} tentativas: {ultima}")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"ficha {ficha}: {e}")


def _normalizar_ficha(dados, matricula, ficha, competencia):
    """Dict do portal → registro da ficha (só o que a tisosdocfly usa)."""
    try:
        itens = []
        for item in (dados.get("lstItens") or []):
            try:
                if not isinstance(item, dict):
                    continue
                itens.append({
                    "codigo": _txt(item.get("cdVerba")),
                    "descricao": _txt(item.get("dsVerba")),
                    "referencia": _txt(item.get("rfVerba")),
                    "tipo": _txt(item.get("tpVerba")),
                    "valor": _txt(item.get("vlVerba")),
                })
            except Exception:
                continue
        return {
            "ficha": ficha,
            "matricula": matricula,
            "nome": _txt(dados.get("nmServidor")),
            "cpf_parcial": _txt(dados.get("nuCPF")),
            "nascimento": _txt(dados.get("dtNascimento")),
            "unidade": _txt(dados.get("nmUnidade")),
            "lotacao": _txt(dados.get("nmLotacao")),
            "cargo": _txt(dados.get("nmCargo")),
            "funcao": _txt(dados.get("nmFuncao")),
            "vinculo": _txt(dados.get("nmVinculo")),
            "situacao": _txt(dados.get("nmSituacao")),
            "regime": _txt(dados.get("nmRegime")),
            "tipo": _txt(dados.get("nmTipo")),
            "competencia": _txt(dados.get("nmCompetencia")) or competencia,
            "admissao": _txt(dados.get("dtAdmissao")),
            "exoneracao": _txt(dados.get("dtExoneracao")),
            "termino_contrato": _txt(dados.get("dtTerminoContrato")),
            "carga_horaria": _txt(dados.get("nuCargaHoraria")),
            "carga_horaria_mensal": _txt(dados.get("nuCargaHorariaMensal")),
            "salario_base": _txt(dados.get("nuSalarioBase")),
            "proventos": _txt(dados.get("nuProventos")),
            "descontos": _txt(dados.get("nuDescontos")),
            "liquido": _txt(dados.get("nuValorLiquido")),
            "grupo_calculo": _txt(dados.get("nmgrupocalculo")),
            "n_itens": len(itens),
            "itens": itens,
        }
    except Exception as e:
        raise RuntimeError(f"normalizar ficha {ficha}: {e}")


def _gravar_progresso(competencia, total, lidas, registro=None, inicio=None):
    """Escreve o progresso da captura para a tela ler (a cada ficha).

    Falha-soft e BARATO de propósito: é um arquivo de poucas linhas, reescrito
    por `tmp`+`os.replace` (nunca pela metade), chamado ~1.159 vezes numa
    coleta de hora e meia. Não substitui o parcial — este é o que permite
    retomar; este é o que a pessoa olha.
    """
    try:
        os.makedirs(DIR_DADOS, exist_ok=True)
        dados = {
            "competencia": competencia or "",
            "total": int(total or 0),
            "lidas": int(lidas or 0),
            "atualizado_em": datetime.now().isoformat(timespec="seconds"),
            "pid": os.getpid(),
        }
        if inicio:
            dados["iniciada_em"] = inicio
        if registro:
            dados["ultimo_nome"] = (registro.get("nome") or "").strip()
            dados["ultimo_matricula"] = (registro.get("matricula")
                                         or "").strip()
            dados["ultimo_cpf"] = mascarar_cpf(registro.get("cpf_parcial"))
        tmp = f"{ARQUIVO_PROGRESSO}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)
        os.replace(tmp, ARQUIVO_PROGRESSO)
        return True
    except Exception as e:
        _logger.warning(f"não consegui gravar o progresso ({e})")
        return False


def _gravar_parcial(fichas, competencia, proximo_indice):
    """Guarda o progresso para retomar depois de parar (AGENTS §3.2)."""
    try:
        os.makedirs(DIR_DADOS, exist_ok=True)
        tmp = f"{ARQUIVO_PARCIAL}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"competencia": competencia,
                       "proximo_indice": proximo_indice,
                       "coletado_em": datetime.now(timezone.utc).isoformat(
                           timespec="seconds"),
                       "fichas": fichas}, f, ensure_ascii=False)
        os.replace(tmp, ARQUIVO_PARCIAL)
        return True
    except Exception as e:
        _log(f"  (não consegui gravar o parcial: {e})")
        return False


def _ler_parcial(competencia):
    """Devolve (fichas, vistos, proximo_indice) ou vazio (AGENTS §3.2)."""
    try:
        if not os.path.exists(ARQUIVO_PARCIAL):
            return [], set(), 0
        with open(ARQUIVO_PARCIAL, encoding="utf-8") as f:
            bruto = json.load(f)
        if (bruto.get("competencia") or "") != (competencia or ""):
            _log("  o parcial é de outra competência; recomeçando do zero")
            return [], set(), 0
        fichas = bruto.get("fichas") or []
        vistos = {s.get("ficha") for s in fichas if s.get("ficha")}
        inicio = int(bruto.get("proximo_indice") or 0)
        if fichas and inicio:
            _log(f"  retomando: {len(fichas)} fichas já lidas, "
                 f"próxima em {inicio}")
        return fichas, vistos, inicio
    except Exception as e:
        _log(f"  parcial ilegível ({e}); recomeçando do zero")
        return [], set(), 0


def _confronto(fichas):
    """Agrupa por nome e compara o CPF parcial (homônimo x mesma pessoa).

    Um nome, um CPF parcial → MESMA_PESSOA (contratos da mesma pessoa).
    Um nome, dois ou mais → HOMONIMO (precisa de revisão com a evidência
    ao lado). Sem CPF em ninguém → SEM_CPF (o portal escondeu o campo).
    """
    try:
        grupos = {}
        for ficha in fichas:
            try:
                chave = _nome_normalizado(ficha.get("nome"))
                if not chave:
                    continue
                grupos.setdefault(chave, []).append(ficha)
            except Exception:
                continue
        relatorio = []
        for nome, lista in sorted(grupos.items()):
            try:
                if len(lista) < 2:
                    continue
                cpfs = sorted({f.get("cpf_parcial") or "?"
                               for f in lista})
                if len(cpfs) == 1 and cpfs[0] != "?":
                    veredito = "MESMA_PESSOA"
                elif len(cpfs) > 1:
                    veredito = "HOMONIMO"
                else:
                    veredito = "SEM_CPF"
                relatorio.append({
                    "nome": lista[0].get("nome"),
                    "veredito": veredito,
                    "fichas": [f.get("ficha") for f in lista],
                    "cpfs_parciais": cpfs,
                })
            except Exception:
                continue
        return relatorio
    except Exception:
        return []


def _usuario_existe(matricula):
    """True se já existe conta com esse login (que É a matrícula)."""
    try:
        from mod_gest_cad_usuario import bd_manipulador as bd
        conn = bd.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tb_usuarios WHERE user_nome=? LIMIT 1",
                    (matricula,))
        achou = cur.fetchone() is not None
        conn.close()
        return achou
    except Exception:
        return False


def _incluir_ficha_agora(registro):
    """Inclui UMA ficha capturada no banco, AGORA. Devolve o estado.

    É a peça que faltava e que o responsável apontou (10/10/2026): a captura
    pode ser PAUSADA, mas a INCLUSÃO tem de ser IMEDIATA. Com a inclusão só
    no fim, uma coleta interrompida na ficha 400 não deixava NADA no banco —
    e, pior, como o "já capturou?" é perguntado ao banco, a próxima execução
    repetiria as 400 fichas no portal. Parar e voltar custava um retrabalho
    de horas.

    Aqui cada ficha entra assim que chega. Se o processo morrer na 400, o
    banco tem as 400 e a próxima rodada pega da 401.

    Devolve `"novo"`, `"existente"` ou `"falha"` — é o que permite a linha do
    terminal dizer se a pessoa é NOVA no cadastro, que é o número que o
    responsável fica olhando.
    """
    mat = (registro.get("matricula") or "").strip()
    nome = (registro.get("nome") or "").strip()
    competencia = (registro.get("competencia") or "").strip()
    if not mat:
        return "falha"
    try:
        from mod_gest_cad_usuario import bd_manipulador as bd
        if _usuario_existe(mat):
            estado = "existente"
        else:
            ok, msg = bd.criar_usuario(
                ATOR, mat, SENHA_PROVISORIA, perfil="comum",
                nome_completo=nome, exigir_telefone=True)
            if not ok:
                _logger.error(f"não consegui criar {mat} ({nome}): {msg}")
                return "falha"
            # NASCER BLOQUEADO, como a carga da folha faz
            # (`NASCEM_BLOQUEADOS=True`): a folha cadastra o servidor, mas
            # ninguém entra sem passar pelo DTI. `criar_usuario` grava
            # `user_ativo=1`, então sem esta linha a conta ficaria ABERTA
            # durante as ~80 min da captura — e é justamente esse o período em
            # que a pessoa tentaria entrar pela primeira vez. A liberação é
            # do DTI, e ela marca `liberado_pelo_dti`, que manda sobre a
            # folha depois.
            try:
                bd.bloquear_usuario(ATOR, mat, True)
            except Exception as e:
                _logger.warning(f"{mat}: não consegui bloquear a conta nova "
                                f"({e}) — ela pode estar acessível antes do DTI")
            estado = "novo"
        # O contrato guarda a folha por competência, e é por ele que a tela
        # mostra onde a pessoa trabalhou e como o salário evoluiu. Os nomes
        # vêm do detalhe JÁ NORMALIZADO (`unidade`, `cargo`…), não do registro
        # cru do portal (`nmUnidade`…), porque o `_normalizar_ficha` já
        # resolveu isso.
        dados = {
            "matricula": mat, "nome": nome,
            "unidade": registro.get("unidade") or "",
            "lotacao": registro.get("lotacao") or "",
            "cargo": registro.get("cargo") or "",
            "vinculo": registro.get("vinculo") or "",
            "situacao": registro.get("situacao") or "",
            "tipo": registro.get("tipo") or "",
            "admissao": registro.get("admissao") or "",
            "exoneracao": registro.get("exoneracao") or "",
            "regime": registro.get("regime") or "",
            "carga_horaria": registro.get("carga_horaria") or "",
            # O detalhe chama de `salario_base`; o contrato chama de
            # `remuneracao`. Mesmo número, nome diferente.
            "remuneracao": registro.get("salario_base") or "",
            "ficha_contracheque": registro.get("ficha") or "",
        }
        try:
            bd.gravar_contrato(ATOR, mat, dados, competencia, principal=True)
        except Exception as e:
            # O contrato é histórico; a ficha abaixo é o dado que o pedido de
            # "novo usuário" quer ver. Falhar aqui não pode impedir a entrada
            # da pessoa no cadastro.
            _logger.warning(f"{mat}: contrato não gravado ({e}) — a ficha "
                            f"entra mesmo assim")
        bd.carregar_detalhe_ficha([registro], ATOR, competencia)
        return estado
    except Exception as e:
        _logger.exception(f"inclusão imediata de {mat} ({nome}): {e}")
        return "falha"


def _fichas_do_banco(competencia):
    """(lista_de_fichas, conjunto_das_fichas) já gravadas nesta competência.

    Duas coisas num lugar só porque elas precisam concordar: o CONJUNTO é o
    que evita re-buscar no portal, e a LISTA é o que devolve as fichas ao
    JSON — senão o arquivo de uma execução que pulou 800 fichas teria só as
    20 novas, e quem lesse o JSON receberia uma folha incompleta sem aviso.

    Devolve `([], set())` quando o banco não está acessível: a captura segue
    como se fosse a primeira vez. É o comportamento seguro — busca a mais
    nunca, perde dado nunca.
    """
    try:
        if not competencia:
            return [], set()
        from mod_gest_cad_usuario import bd_manipulador as _gest
        return _gest.listar_fichas_por_competencia(competencia)
    except Exception as e:
        _logger.warning(f"não consegui ler as fichas já gravadas no banco "
                        f"({e}) — capturando como se fosse a primeira vez")
        return [], set()


def coletar(entrada, competencia=None, maximo=0, incluir_agora=False):
    """Busca o detalhe de cada ficha da folha (AGENTS §3.2 em tudo).

    O terminal mostra uma linha por servidor (nome + CPF parcial) com o
    contador `i/total` — é o que responde "ainda está capturando?" sem
    precisar abrir o arquivo no dia seguinte.

    TRÊS REGRAS, e a ordem delas é o pedido de 10/10/2026 para não martelar
    o servidor público:

    1. **Mês completo não se recaptura.** Se todas as fichas da competência já
       estão no banco, a função nem ABRE SESSÃO no portal — é o caso mais
       comum quando o script é rodado duas vezes no mesmo dia.
    2. **Mês parcial só busca o que falta.** As fichas já gravadas são puladas
       uma a uma; o portal não recebe uma requisição para nenhuma delas.
    3. **Parada retoma de onde parou.** O parcial em disco guarda o índice, e
       o banco guarda o que já entrou: uma coleta interrompida na ficha 400 de
       1.159 continua na 401, sem refazer as 400.

    `incluir_agora` (só com `--total`) grava cada ficha no banco ASSIM que ela
    chega, e não no fim: é o que permite pausar a captura sem perder o que já
    foi lido.
    """
    try:
        with open(entrada, encoding="utf-8") as f:
            folha = json.load(f)
    except Exception as e:
        raise RuntimeError(f"não li a folha {entrada}: {e}")
    try:
        if competencia is None:
            competencia = folha.get("competencia") or ""
        servidores = folha.get("servidores") or []
        alvos = []
        for reg in servidores:
            try:
                ficha = (reg.get("ficha_contracheque") or "").strip()
                mat = (reg.get("matricula") or "").strip()
                if ficha and mat:
                    alvos.append((mat, ficha))
            except Exception:
                continue
        if maximo and maximo > 0:
            alvos = alvos[:maximo]
        total_folha = len(alvos)

        # --- regras 1 e 2: o que já está no banco NÃO volta ao portal ---
        fichas_db, vistas_db = _fichas_do_banco(competencia)
        pendentes = [(m, f) for m, f in alvos if f not in vistas_db]
        puladas = total_folha - len(pendentes)
        if puladas:
            _logger.info(f"{puladas} ficha(s) desta competência já estão no "
                         f"banco — não serão pedidas de novo ao portal")
        if not pendentes:
            _logger.info(f"competência {competencia or '—'}: as {total_folha} "
                         f"ficha(s) já estão capturadas — nada a buscar")
            return {
                "origem": "Portal da Transparência (detalhe ServidorDetalhes)",
                "competencia": competencia,
                "coletado_em": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"),
                "total": len(fichas_db),
                "erros": [],
                "fichas_sem_cpf": 0,
                "ja_capturadas": len(fichas_db),
                "confronto": _confronto(fichas_db),
                "fichas": fichas_db,
            }

        total = len(pendentes)
        _logger.info(f"capturando {total} ficha(s) de {total_folha} "
                     f"(competência {competencia or '—'})"
                     + (" — incluindo no banco a cada ficha"
                        if incluir_agora else ""))
        opener = _abrir()
        _logger.success("sessão aberta no portal — iniciando a captura")

        # --- regra 3: retomar de onde parou ---
        fichas_parcial, vistos, inicio = _ler_parcial(competencia)
        # Junta BANCO + PARCIAL sem repetir ficha: o JSON tem de sair
        # completo, e o mesmo servidor duas vezes faria o confronto de
        # homônimo contar errado.
        fichas = list(fichas_db)
        vistos = set(vistos) | vistas_db
        ja_por_ficha = {str(f.get("ficha") or "") for f in fichas}
        for reg in fichas_parcial:
            chave = str(reg.get("ficha") or "")
            if chave and chave not in ja_por_ficha:
                fichas.append(reg)
                ja_por_ficha.add(chave)
        if fichas_parcial:
            _logger.info(f"retomando: {len(fichas)} ficha(s) já lidas "
                         f"(índice {inicio})")
        erros = []
        sem_cpf = sum(1 for f in fichas if not f.get("cpf_parcial"))
        novos = 0
        falhas = 0
        i = inicio
        while i < total:
            try:
                mat, ficha = pendentes[i]
                if ficha in vistos:
                    i += 1
                    continue
                inicio_ficha = time.monotonic()
                registro_atual = None
                try:
                    dados = _buscar_ficha(opener, ficha)
                    registro = _normalizar_ficha(dados, mat, ficha, competencia)
                    fichas.append(registro)
                    vistos.add(ficha)
                    sem_cpf += 0 if registro.get("cpf_parcial") else 1
                    # A LINHA PEDIDA: quem é este e de qual CPF. O nome vem
                    # do portal quando ele responde, senão da matrícula — e
                    # a matrícula é sempre melhor que uma linha sem rótulo.
                    rotulo = (registro.get("nome") or "").strip() or f"mat. {mat}"
                    registro_atual = registro
                    # A INCLUSÃO IMEDIATA. Só com `--total`: sem a flag a
                    # execução é de consulta e não escreve no banco. O
                    # resultado entra na própria linha, porque "quantos
                    # novos entraram" é a pergunta que o responsável faz a
                    # cada minuto enquanto a captura roda.
                    marca = ""
                    if incluir_agora:
                        est = _incluir_ficha_agora(registro)
                        if est == "novo":
                            novos += 1
                            marca = "  [NOVO]"
                        elif est == "existente":
                            marca = "  [já existia]"
                        else:
                            falhas += 1
                            marca = "  [falhou]"
                    _logger.info(
                        f"[{i + 1}/{total}] {rotulo}  "
                        f"cpf {mascarar_cpf(registro.get('cpf_parcial'))}"
                        f"{marca}  ({len(fichas)} gravadas"
                        + (f", {novos} novo(s)" if incluir_agora else "") + ")")
                    if not registro.get("cpf_parcial"):
                        _logger.warning(
                            f"    {rotulo} veio SEM CPF parcial — o confronto "
                            f"de homônimo fica sem evidência para esta ficha")
                except Exception as e:
                    erros.append(f"{ficha}: {e}")
                    _logger.error(f"[{i + 1}/{total}] falhou {mat}/{ficha}: {e}")
                i += 1
                # O progresso vai para a tela a CADA ficha — é o que
                # responde "ainda está andando?" sem esperar as 5 do parcial.
                _gravar_progresso(competencia, total, i, registro=registro_atual)
                # Batimento: uma ficha que demora mais que isto está lenta
                # (portal sob carga ou rede ruim). Sem esta linha, uma pausa
                # de 40 s é indistinguível de um script travado.
                decorrido = time.monotonic() - inicio_ficha
                if decorrido > LIMITE_BATIMENTO_S:
                    _logger.warning(
                        f"    esta ficha demorou {decorrido:.0f}s — ainda "
                        f"capturando (lento, mas não travado)")
                if (i - inicio) % 5 == 0:
                    _gravar_parcial(fichas, competencia, i)
                if i < total:
                    _esperar()
            except Exception as e:
                erros.append(f"índice {i}: {e}")
                _logger.error(f"índice {i}: {e}")
                i += 1
        confronto = _confronto(fichas)
        folha_detalhe = {
            "origem": "Portal da Transparência (detalhe ServidorDetalhes)",
            "competencia": competencia,
            "coletado_em": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "total": len(fichas),
            "erros": erros,
            "fichas_sem_cpf": sem_cpf,
            "ja_capturadas": len(fichas_db),
            "confronto": confronto,
            "fichas": fichas,
        }
        _logger.info(f"captura da folha terminada: {len(fichas)} ficha(s), "
                     f"{len(erros)} erro(s), {sem_cpf} sem CPF parcial"
                     + (f", {novos} usuário(s) NOVO(s) no cadastro"
                        if incluir_agora else ""))
        try:
            if os.path.exists(ARQUIVO_PARCIAL):
                os.remove(ARQUIVO_PARCIAL)
        except Exception as e:
            _logger.warning(f"não consegui apagar o parcial: {e}")
        return folha_detalhe
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"coleta do detalhe: {e}")


def _linha_csv(valores):
    """Uma linha CSV ponto-e-vírgula (mesmo padrão da coleta da folha)."""
    try:
        campos = []
        for valor in valores:
            texto = str(valor or "")
            if '"' in texto or ";" in texto or "\n" in texto:
                texto = '"' + texto.replace('"', '""') + '"'
            campos.append(texto)
        return ";".join(campos) + "\n"
    except Exception:
        return "\n"


def gravar_csv(folha_detalhe, caminho):
    """Grava o CSV único: mesmas informações do JSON, uma linha por ficha.

    Cada linha é um servidor; as verbas vão serializadas em JSON na
    coluna `verbas`. Assim o CSV e o JSON carregam o mesmo dado — muda
    só o formato (AGENTS §3.2).
    """
    try:
        fichas = folha_detalhe.get("fichas") or []
        with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
            f.write(";".join(CAMPOS_FICHA_CSV) + "\n")
            for ficha in fichas:
                try:
                    itens = ficha.get("itens") or []
                    try:
                        verbas = json.dumps(itens, ensure_ascii=False)
                    except Exception:
                        verbas = ""
                    f.write(_linha_csv([
                        ficha.get("ficha"), ficha.get("matricula"),
                        ficha.get("nome"), ficha.get("cpf_parcial"),
                        ficha.get("nascimento"), ficha.get("unidade"),
                        ficha.get("lotacao"), ficha.get("cargo"),
                        ficha.get("funcao"), ficha.get("vinculo"),
                        ficha.get("situacao"), ficha.get("regime"),
                        ficha.get("tipo"), ficha.get("competencia"),
                        ficha.get("admissao"), ficha.get("exoneracao"),
                        ficha.get("termino_contrato"),
                        ficha.get("carga_horaria"),
                        ficha.get("carga_horaria_mensal"),
                        ficha.get("salario_base"), ficha.get("proventos"),
                        ficha.get("descontos"), ficha.get("liquido"),
                        ficha.get("grupo_calculo"),
                        ficha.get("n_itens"), verbas]))
                except Exception:
                    continue
        return True, f"{len(fichas)} fichas em {len(fichas)} linhas"
    except Exception as e:
        return False, str(e)


ATOR = "coleta_kbp"
# A senha que a conta nova nasce. É a MESMA da carga da folha
# (`carga_folha.SENHA_PROVISORIA`), e é provisória: o primeiro acesso obriga a
# trocar. Um caminho de criação diferente criaria um tipo de conta que o resto
# do sistema não sabe tratar — e a tela de troca de credenciais contaria isso
# como falha.
SENHA_PROVISORIA = "123456"


def _incluir_no_banco(folha_detalhe):
    """Captura -> banco do módulo de gestão. Só é chamada pelo `--total`.

    São DOIS passos, e a ordem importa:

    1. `carga_folha.carga_automatica()` monta o CADASTRO a partir da folha:
       cria o usuário que ainda não existe (com senha provisória e troca
       obrigatória), cria/atualiza os contratos, a foto do mês e o histórico
       salarial. É o passo que "disponibiliza o usuário" — sem ele, o
       detalhe capturado ficaria órfão, sem login dono.
    2. `gest.carregar_detalhe_ficha()` grava o DETALHE capturado (CPF parcial,
       salário base, proventos, descontos, líquido e as verbas) em
       `tb_detalhe_ficha`, idempotente por (ficha, competência), e aplica a
       regra de CPF — funde mesmo CPF, separa homônimo.

    A ordem é o inverso do erro: gravar o detalhe antes do cadastro deixaria
    linhas sem `user_nome`, que é a coluna que liga o detalhe à pessoa.

    O HISTÓRICO não depende deste código, e é o que faz o pedido de "ver a
    evolução" funcionar: cada competência é uma LINHA nova em `tb_contratos`,
    `tb_foto_mensal` e `tb_detalhe_ficha`. Rodar de novo no mês seguinte não
    sobrescreve o anterior — atualiza o registro do mês corrente e guarda o
    passado.
    """
    try:
        from mod_gest_cad_usuario import carga_folha as _carga
        _logger.info("incluindo no banco do módulo de gestão (passo 1/2: "
                     "cadastro a partir da folha)...")
        rel = _carga.carga_automatica(forcar=True)
        if not rel.get("rodou"):
            _logger.warning(
                f"a carga da folha não rodou ({rel.get('motivo') or 'sem motivo'}"
                f") — o detalhe vai ser gravado mesmo assim, mas quem não "
                f"existia no cadastro pode ficar sem login")
        else:
            _logger.success(
                f"cadastro em dia: {rel.get('criados', 0)} criado(s), "
                f"{rel.get('remuneracoes', 0)} salário(s), "
                f"{rel.get('fotos_mensais', 0)} foto(s) do mês, "
                f"{rel.get('contratos_novos', 0)} contrato(s) novo(s); "
                f"competência {rel.get('competencia') or '—'}")

        _logger.info("gravando o detalhe capturado (passo 2/2)...")
        from mod_gest_cad_usuario import bd_manipulador as _gest
        resumo = _gest.carregar_detalhe_ficha(
            folha_detalhe.get("fichas") or [], ATOR,
            folha_detalhe.get("competencia") or "")
        _logger.success(
            f"detalhe gravado: {resumo.get('gravadas', 0)} ficha(s) "
            f"gravada(s), {resumo.get('inalteradas', 0)} inalterada(s), "
            f"{resumo.get('fundidos', 0)} login(s) fundido(s) por CPF igual, "
            f"{resumo.get('separados', 0)} separado(s) por homônimo, "
            f"{resumo.get('sem_cpf', 0)} sem CPF")
        for erro in (resumo.get("erros") or [])[:10]:
            _logger.error(f"inclusão: {erro}")
        return resumo
    except Exception as e:
        # Falha na inclusão NÃO desfaz a captura: os dois arquivos já
        # estão gravados e a pessoa pode reprocessar depois com `--total`.
        _logger.exception(
            f"falha ao incluir no banco ({e}) — os arquivos JSON e CSV estão "
            f"gravados; rode de novo com --total para tentar a inclusão")
        return {}


def main():
    """CLI da coleta do detalhe (espelha a coleta da folha)."""
    try:
        # Primeiro negócio do `main` e antes de qualquer leitura: sem os
        # sinks, os primeiros eventos (configuração, "não configurada") saem
        # por um `print` e a captura seguinte entra por outro caminho — foi o
        # que deixou o log com duas aparências diferentes.
        _configurar_eventos()
        ap = argparse.ArgumentParser(
            description="Coleta a ficha (CPF parcial + vencimentos) de cada "
                        "servidor da folha em fonte_folha.json.")
        ap.add_argument("--entrada", default=ARQUIVO_ENTRADA,
                        help="folha JSON de origem.")
        ap.add_argument("--saida", default=ARQUIVO_PADRAO,
                        help="detalhe JSON de destino.")
        ap.add_argument("--csv", default=ARQUIVO_CSV,
                        help="CSV único (mesmas informações do JSON).")
        ap.add_argument("--sem-csv", action="store_true",
                        help="não grava o CSV.")
        ap.add_argument("--atualizar", action="store_true",
                        help="busca de novo mesmo que já exista arquivo.")
        ap.add_argument("--max", type=int, default=0,
                        help="limita a N fichas (teste de ritmo/formato).")
        ap.add_argument("--competencia", default=None,
                        help="MM/AAAA (padrão: o da folha de entrada).")
        ap.add_argument("--total", action="store_true",
                        help="PIPELINE COMPLETO: acessa o portal, grava o JSON "
                             "e o CSV e INCLUI tudo no banco do módulo de "
                             "gestão — cria o usuário que ainda não existe, "
                             "atualiza o mês corrente e guarda o histórico "
                             "por competência. Sem esta flag, a execução só "
                             "grava os dois arquivos e não toca no banco.")
        args = ap.parse_args()

        if not RAIZ or not DETALHE or not CFG.get("portal_endpoints"):
            _logger.warning(
                "Coleta do detalhe NÃO CONFIGURADA — nada foi acessado e "
                "nada foi gravado. Preencha 'portal_url' e 'portal_endpoints' "
                f"em {os.path.join(DIR_MODULO, 'fonte_folha.json')}.")
            return 0

        try:
            os.makedirs(DIR_DADOS, exist_ok=True)
            # `--total` implica recapturar. Sem isso, rodar `--total` numa
            # máquina que já tinha um JSON antigo faria a inclusão no banco
            # com o mês passado — e o pedido é justamente "pega a informação
            # agora e inclui agora". Reaproveitar o arquivo continua
            # disponível para quem só quer consultar, sem a flag.
            if os.path.exists(args.saida) and not args.atualizar and not args.total:
                with open(args.saida, encoding="utf-8") as f:
                    folha_detalhe = json.load(f)
                _logger.info(f"reaproveitando {args.saida} "
                             f"({folha_detalhe.get('total')} fichas de "
                             f"{folha_detalhe.get('coletado_em')})")
                _logger.info("use --atualizar para buscar de novo")
            else:
                _logger.info("ritmo: "
                             f"{INTERVALO_MIN_S:.1f}s a {INTERVALO_MAX_S:.1f}s "
                             "por ficha (sorteado)")
                folha_detalhe = coletar(args.entrada, args.competencia,
                                        args.max,
                                        incluir_agora=args.total)
                with open(args.saida, "w", encoding="utf-8") as f:
                    json.dump(folha_detalhe, f, ensure_ascii=False, indent=2)
                _logger.success(f"JSON gravado: {args.saida}")

            # O CSV é OBRIGATÓRIO, não um extra: o confronto de homônimo é
            # feito por gente, em planilha, ao lado da folha. Um JSON sozinho
            # obriga a abrir editor de texto para cada linha, e é assim que a
            # revisão acaba não sendo feita. Por isso `--sem-csv` só sai com
            # pedido explícito.
            if not args.sem_csv:
                ok, info = gravar_csv(folha_detalhe, args.csv)
                if not ok:
                    _logger.error(f"ERRO ao gravar o CSV: {info}")
                    return 1
                _logger.success(f"CSV gravado: {args.csv} ({info})")
            else:
                _logger.warning("CSV não gravado (--sem-csv) — o confronto de "
                                "homônimo fica sem a planilha")

            _logger.info(f"resumo: {folha_detalhe.get('total')} ficha(s) "
                         f"({folha_detalhe.get('competencia')}) — JSON "
                         f"{args.saida}"
                         + ("" if args.sem_csv else f" e CSV {args.csv}"))

            confronto = folha_detalhe.get("confronto") or []
            mesma = sum(1 for c in confronto
                        if c.get("veredito") == "MESMA_PESSOA")
            homo = sum(1 for c in confronto
                       if c.get("veredito") == "HOMONIMO")
            sem = sum(1 for c in confronto
                      if c.get("veredito") == "SEM_CPF")
            erros = folha_detalhe.get("erros") or []
            _logger.info(f"confronto por nome: {mesma} mesma pessoa, "
                         f"{homo} homônimo(s), {sem} sem CPF; "
                         f"{len(erros)} erro(s)")
            if folha_detalhe.get("fichas_sem_cpf"):
                _logger.warning(
                    f"{folha_detalhe['fichas_sem_cpf']} ficha(s) vieram sem CPF "
                    f"parcial — sem ele não dá para separar homônimo de mesma "
                    f"pessoa; confira o portal ou a competência")
            for erro in erros[:10]:
                _logger.error(erro)
            if len(erros) > 10:
                _logger.error(f"... e mais {len(erros) - 10} erro(s) "
                              f"(ver o JSON)")

            # ---- A INCLUSÃO no banco é do `--total`, e só dele ----
            #
            # Sem a flag, esta execução termina aqui de propósito: os dois
            # arquivos estão escritos e o banco fica intacto. Quem roda a
            # coleta para consultar não está pedindo cadastro — e uma escrita
            # no banco de usuários é o tipo de efeito que não deve sair de
            # uma captura por acidente.
            if not args.total:
                _logger.info("sem --total: os arquivos foram gravados e o "
                             "banco de usuários NÃO foi tocado")
                return 0

            _logger.info("=== --total: incluindo no banco de usuários ===")
            _incluir_no_banco(folha_detalhe)
            return 0
        except Exception as e:
            _logger.exception(f"ERRO na coleta do detalhe: {e}")
            return 1
    except Exception as e:
        _logger.exception(f"ERRO: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
