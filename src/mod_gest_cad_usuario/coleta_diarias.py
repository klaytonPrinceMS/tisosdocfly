# -*- coding: utf-8 -*-
"""Coleta de despesas com diárias no portal da transparência.

EN — Fetches yearly per-person travel-allowance ("diárias") totals from the
Transparency Portal and stores them locally, so each server's profile can show
what they received without depending on an external site at click time.

PT-BR: Busca os totais anuais de diárias por favorecido no portal da
transparência e grava local, para o perfil de cada servidor mostrar o que ele
recebeu sem depender de site externo na hora do clique.

O VALOR É CONSOLIDADO POR ANO (medido em 11/10/2026): o grid
(`DespesasGetFornecedorGrid`) devolve UMA linha por favorecido por ano
(`idExercicio`), com `vlEmpenhado`/`vlLiquidado`/`vlPago` do ano inteiro — o
mesmo `cdFornecedor` aparece em 2025 e 2026 com valores diferentes. Não é por
empenho: o detalhe por empenho mora na página de empenhos (`tipo=d`), e aqui
só o consolidado interessa.

QUANDO RODA
-----------
1. **No boot.** Se nunca coletou, ou o dado é velho demais.
2. **Uma vez por mês, depois do dia 10.** A folha de diárias fecha junto da
   folha de pagamento, e antes do dia 10 o mês anterior ainda pode estar
   incompleto. O dia 10 é o que o responsável definiu.

LIGAÇÃO POR CPF (decisão do responsável, 11/10/2026): o portal devolve o nome
do favorecido com o CPF parcial mascarado (`***.312.178-**`), no MESMO formato
que `tb_usuarios.cpf_parcial` guarda. A ligação é pelo CPF parcial exato — e
não pelo nome, que homônimo quebra. Linha sem CPF correspondente continua
gravada (com `user_nome` vazio): o painel mostra o gasto total mesmo de quem
não é servidor cadastrado, e o vínculo aparece sozinho quando o CPF entrar no
cadastro.

FALHA
-----
`coletar()`/`coletar_todas()` nunca levantam. Portal fora do ar é o estado
normal de um site externo, não uma exceção — e uma exceção derrubaria o boot
inteiro por causa de um card. Devolvem `{"erro": ...}` e pronto.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from mod_skyrover import observabilidade

log = observabilidade.get_logger("gest_cad_usuario")

# URL de fábrica (commitada de propósito, 11/10/2026): quem baixa o sistema já
# nasce apontando para o portal certo, e o administrador troca no painel
# (`usuarios_diarias_url` na `tb_config` central) sem mexer em código — o
# mesmo contrato da ficha detalhada (`usuarios_portal_url`).
URL_DIARIAS_PADRAO = ("https://transparencia.montesantodeminas.mg.gov.br/"
                      "despesas-por-diarias")

# Elementos de despesa que são diária (medido em 11/10/2026, via
# `DespesasGetElementosDiaria` no portal de Monte Santo de Minas). Vão no
# `elemento` do grid; sem eles o grid devolve despesa geral, não diária.
ELEMENTOS_DIARIA_PADRAO = "339014,335014"

DIA_COLETA_MES = 10
TIMEOUT_SEGUNDOS = 30

# Ritmo humano entre requisições (padrão 2–6 s, igual à ficha detalhada):
# intervalo fixo denuncia robô, e a coleta é mensal — sem pressa. O
# administrador troca no painel (`usuarios_diarias_intervalo_min_s/_max_s`)
# sem restart; o coletor lê a cada espera, então vale na coleta em curso.
INTERVALO_MIN_S = 2.0
INTERVALO_MAX_S = 6.0

# Tamanho de página que o grid do portal aceita (medido em 11/10/2026):
# o `lengthMenu` da página é [5, 10, 25] e qualquer outro tamanho devolve
# zero linhas — inclusive 100. Página maior que 25 não é "mais rápido", é
# vazia.
TAMANHO_PAGINA = 25

AGENTE = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Andamento da coleta em curso, para o painel mostrar barra + último nome
# sem recarregar. Vive em memória (é estado de execução, não dado): o botão
# "Atualizar andamento" e o relógio do card lêem por `obter_progresso()`.
PROGRESSO = {"rodando": False, "anos_total": 0, "anos_feitos": 0, "ano": "",
             "total_ano": 0, "lidas_ano": 0, "lidas": 0, "ultimo_nome": "",
             "atualizado_em": ""}


def intervalos():
    """(min, max) de espera entre requisições — config, com fábrica 2–6 s."""
    try:
        from mod_skyrover import bd_conexao as _bd
        try:
            minimo = float(_bd.get_config("usuarios_diarias_intervalo_min_s",
                                          INTERVALO_MIN_S)
                           or INTERVALO_MIN_S)
        except (TypeError, ValueError):
            minimo = INTERVALO_MIN_S
        try:
            maximo = float(_bd.get_config("usuarios_diarias_intervalo_max_s",
                                          INTERVALO_MAX_S)
                           or INTERVALO_MAX_S)
        except (TypeError, ValueError):
            maximo = INTERVALO_MAX_S
        minimo = max(0.1, minimo)
        return (minimo, max(minimo, maximo))
    except Exception:
        return (INTERVALO_MIN_S, INTERVALO_MAX_S)


def _esperar():
    """Espera sorteada entre min e max (ritmo humano, nunca trava a tela).

    Lê a config a cada chamada: trocar no painel vale na coleta em curso.
    Nunca levanta — espera que falha é espera pulada, não coleta perdida.
    """
    try:
        import random as _aleatorio
        import time as _tempo
        minimo, maximo = intervalos()
        _tempo.sleep(_aleatorio.uniform(minimo, maximo))
    except Exception:
        pass


def obter_progresso():
    """Cópia do andamento atual (para o painel; nunca levanta)."""
    try:
        return dict(PROGRESSO)
    except Exception:
        return {"rodando": False}


def _progresso_resetar(total_anos):
    """Zera o andamento no início de uma coleta."""
    try:
        PROGRESSO.update({"rodando": True, "anos_total": int(total_anos or 0),
                          "anos_feitos": 0, "ano": "", "total_ano": 0,
                          "lidas_ano": 0, "lidas": 0, "ultimo_nome": "",
                          "atualizado_em": datetime.now().strftime(
                              "%d/%m %H:%M")})
    except Exception:
        pass


def _progresso_pagina(ano, total_ano, lidas_ano, ultimo_nome=""):
    """Atualiza o andamento a cada página lida."""
    try:
        PROGRESSO.update({"ano": str(ano or ""),
                          "total_ano": int(total_ano or 0),
                          "lidas_ano": int(lidas_ano or 0)})
        if (ultimo_nome or "").strip():
            PROGRESSO["ultimo_nome"] = str(ultimo_nome or "")[:120]
            PROGRESSO["atualizado_em"] = datetime.now().strftime(
                "%d/%m %H:%M")
    except Exception:
        pass


def _progresso_encerrar():
    """Marca a coleta como terminada (sucesso ou falha)."""
    try:
        PROGRESSO["rodando"] = False
    except Exception:
        pass


def url_portal_diarias():
    """A base do portal que o coletor usa DE FATO.

    `tb_config` (`usuarios_diarias_url`, o que o administrador digita no
    painel) manda sobre a constante — é a troca sem editar código. Tela vazia
    vale a fábrica commitada acima.
    """
    try:
        from mod_skyrover import bd_conexao as _bd
        da_tela = str(_bd.get_config("usuarios_diarias_url", "") or "").strip()
        if da_tela:
            return da_tela.rstrip("/")
        return URL_DIARIAS_PADRAO
    except Exception:
        return URL_DIARIAS_PADRAO


def elementos_diaria():
    """Os elementos de diária (`usuarios_diarias_elementos`, fábrica acima)."""
    try:
        from mod_skyrover import bd_conexao as _bd
        val = str(_bd.get_config("usuarios_diarias_elementos",
                                 ELEMENTOS_DIARIA_PADRAO) or "").strip()
        return val or ELEMENTOS_DIARIA_PADRAO
    except Exception:
        return ELEMENTOS_DIARIA_PADRAO


def _base_api():
    """O `scheme://host` do portal, para chamar a API interna dele.

    A URL configurada é a da PÁGINA (`.../despesas-por-diarias`, para gente
    ler); a API (`.../transparencia/despesas/tpc_des_data.ashx`) mora na RAIZ
    do host. Concatenar o caminho da API na URL da página devolve 404
    (medido em 11/10/2026: `.../despesas-por-diarias/transparencia/...` não
    existe) — por isso o host é extraído aqui, e a página segue só para
    exibição.
    """
    try:
        from urllib.parse import urlparse as _parse
        partes = _parse((url_portal_diarias() or "").strip())
        if partes.scheme in ("http", "https") and partes.netloc:
            return f"{partes.scheme}://{partes.netloc}"
        return URL_DIARIAS_PADRAO.rsplit("/", 1)[0]
    except Exception:
        return "https://transparencia.montesantodeminas.mg.gov.br"


def _para_real(texto):
    """"R$ 4.100,00" -> 4100.0. Vazio vira 0.0."""
    try:
        import re as _re
        limpo = _re.sub(r"[^\d,.]", "", str(texto or ""))
        if not limpo:
            return 0.0
        return float(limpo.replace(".", "").replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _post_json(url, carga):
    """POST JSON e devolve o texto. Levanta só em erro de rede."""
    try:
        dados = json.dumps(carga).encode("utf-8")
        pedido = urllib.request.Request(
            url, data=dados,
            headers={"User-Agent": AGENTE,
                     "Content-Type": "application/json; charset=utf-8",
                     "Accept": "application/json"})
        with urllib.request.urlopen(pedido,
                                    timeout=TIMEOUT_SEGUNDOS) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        raise


def _anos_disponiveis(base):
    """Os anos que o portal tem diária (`DespesasGetAnoDiarias`)."""
    try:
        bruto = _post_json(
            base + "/transparencia/despesas/tpc_des_data.ashx"
            "?metodo=DespesasGetAnoDiarias&entidade=", {})
        anos = []
        for item in (json.loads(bruto or "[]") or []):
            try:
                anos.append(str(int(item.get("id"))))
            except (TypeError, ValueError):
                continue
        return sorted(set(anos))
    except Exception as e:
        log.warning(f"diarias: falha ao listar anos ({e})")
        return []


def _consultar_ano(base, ano, elemento, inicio=0, tamanho=100):
    """Uma página do grid de fornecedores do ano. Levanta em erro de rede."""
    try:
        carga = {
            "parameters": {
                "draw": 1, "start": int(inicio), "length": int(tamanho),
                "search": {"value": ""},
                "order": [{"column": 0, "dir": "asc"}],
            },
            "entidade": "", "Ano": str(ano), "Competencia": "",
            "dtInicio": "", "dtFim": "", "unidade": "", "acao": "",
            "dsacao": "", "elemento": elemento, "cargoDiaria": "",
        }
        bruto = _post_json(
            base + "/transparencia/despesas/tpc_des_data.ashx"
            "?metodo=DespesasGetFornecedorGrid", carga)
        return json.loads(bruto or "{}") or {}
    except Exception:
        raise


def coletar(ano="", gravar=True):
    """Coleta UM ano de diárias. **Nunca levanta.**

    Sem `ano`, coleta todos os anos que o portal anuncia. Devolve o dicionário
    gravado, ou `{"erro": ...}`.
    """
    try:
        pagina = (url_portal_diarias() or "").rstrip("/")
        if not pagina.startswith("http"):
            return {"erro": "URL do portal de diárias inválida"}
        base = _base_api()
        elemento = elementos_diaria()
        anos = [str(ano)] if str(ano or "").strip() else _anos_disponiveis(base)
        if not anos:
            return {"erro": "o portal não anunciou nenhum ano de diárias "
                            "(veja o log do módulo para a causa)"}
        from mod_gest_cad_usuario import bd_manipulador as gest
        total_linhas, total_anos = 0, []
        _progresso_resetar(len(anos))
        for cada_ano in anos:
            try:
                primeira = _consultar_ano(base, cada_ano, elemento, 0,
                                          TAMANHO_PAGINA)
            except Exception as e:
                log.warning(f"diarias: ano {cada_ano} sem resposta ({e})")
                continue
            try:
                filtrados = int(primeira.get("recordsFiltered") or 0)
            except (TypeError, ValueError):
                filtrados = 0
            linhas = list(primeira.get("data") or [])
            _progresso_pagina(cada_ano, filtrados, len(linhas),
                              (linhas[-1].get("nmFornecedor") if linhas
                               else ""))
            cursor = len(linhas)
            while cursor < filtrados:
                _esperar()
                try:
                    pagina_req = _consultar_ano(base, cada_ano, elemento,
                                                cursor, TAMANHO_PAGINA)
                except Exception as e:
                    log.warning(f"diarias: ano {cada_ano} parou em "
                                f"{cursor} ({e})")
                    break
                lote = list(pagina_req.get("data") or [])
                if not lote:
                    break
                linhas.extend(lote)
                cursor += len(lote)
                _progresso_pagina(cada_ano, filtrados, cursor,
                                  lote[-1].get("nmFornecedor"))
            _esperar()
            normalizadas = []
            for linha in linhas:
                try:
                    normalizadas.append({
                        "ano": str(cada_ano),
                        "cd_fornecedor": str(linha.get("cdFornecedor") or ""),
                        "nome_portal": str(linha.get("nmFornecedor") or ""),
                        "cpf_parcial": str(linha.get("nuCpfCnpj") or ""),
                        "vl_empenhado": _para_real(linha.get("vlEmpenhado")),
                        "vl_liquidado": _para_real(linha.get("vlLiquidado")),
                        "vl_pago": _para_real(linha.get("vlPago")),
                    })
                except Exception:
                    continue
            if gravar and normalizadas:
                try:
                    gest.gravar_diarias(normalizadas)
                except Exception as e:
                    log.warning(f"diarias: ano {cada_ano} não gravou ({e})")
                    continue
            total_linhas += len(normalizadas)
            total_anos.append(cada_ano)
            try:
                PROGRESSO["anos_feitos"] = len(total_anos)
                PROGRESSO["lidas"] = int(total_linhas)
            except Exception:
                pass
        if not total_anos:
            _progresso_encerrar()
            return {"erro": "nenhum ano respondeu no portal"}
        log.info(f"diarias: coleta concluída — {total_linhas} linha(s) em "
                 f"{len(total_anos)} ano(s)")
        _progresso_encerrar()
        return {"erro": "", "anos": total_anos, "linhas": total_linhas}
    except Exception as e:
        try:
            log.warning(f"diarias: falha ao coletar ({e})")
        except Exception:
            pass
        try:
            _progresso_encerrar()
        except Exception:
            pass
        return {"erro": str(e)}


def ultima_coleta_em():
    """Quando foi a última carga de diárias (`coletado_em` máximo)."""
    try:
        from mod_gest_cad_usuario import bd_manipulador as gest
        return gest.ultima_coleta_diarias_em() or ""
    except Exception:
        return ""


def deve_coletar():
    """Se é hora de coletar — nunca coletado, dia 10+, ou +40 dias.

    A regra é testada por DATA, e não por "quantas horas faz": num sistema que
    fica no ar semanas, a regra por intervalo nunca seria satisfeita, e o dado
    envelheceria em silêncio (mesmo contrato de `coleta_pntp.deve_coletar`).
    """
    try:
        ultima = (ultima_coleta_em() or "")[:19]
        if not ultima:
            return True
        try:
            marca = datetime.fromisoformat(ultima)
        except (TypeError, ValueError):
            return True
        hoje = datetime.now()
        if hoje.day >= DIA_COLETA_MES and marca < hoje.replace(
                day=DIA_COLETA_MES, hour=0, minute=0, second=0,
                microsecond=0):
            return True
        return (hoje - marca) > timedelta(days=40)
    except Exception:
        return True


def coletar_todas(forcar=False):
    """Coleta todos os anos. **Nunca levanta.**

    `forcar=True` ignora a regra do dia 10 — é o que o botão "coletar agora"
    do painel usa.
    """
    try:
        if not forcar and not deve_coletar():
            return {"coletadas": 0, "motivo": "fora da janela (dia 10)"}
        saida = coletar(gravar=True)
        if saida.get("erro"):
            return {"coletadas": 0, "motivo": saida["erro"]}
        return {"coletadas": int(saida.get("linhas") or 0),
                "anos": saida.get("anos") or []}
    except Exception as e:
        try:
            log.warning(f"diarias: coletar_todas falhou ({e})")
        except Exception:
            pass
        return {"coletadas": 0, "motivo": str(e)}
