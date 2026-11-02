"""EN: Municipal telephone number ranges — what counts as "a number of ours".

PT-BR: Faixas de telefones da prefeitura — o que conta como "número nosso".

POR QUE ISTO EXISTE
    O telefone da prefeitura não é um número solto: a prefeitura tem
    faixas. O PABX da central atende de 5101 a 5199, a garagem tem a sua, o
    almoxarifado tem a sua. Um servidor que digitar "3591-5000" na lista
    telefônica não está dando o número errado — está dando um número de
    outro lugar, e o diretório vai propagatingo até alguém descobrir.

    A faixa não é burocracia: é o que permite dizer, na hora, que o número
    digitado não é desta prefeitura. E como a prefeitura tem mais de uma
    central (e a lista cresce), são **várias** faixas, não uma só.

A REGRA QUE A PREFEITURA DEFINIU
    Um telefone **fora** das faixas não é bloqueado — é **avisado**. Bloquear
    aqui puniria um servidor numa situação real: a unidade de saúde do
    distrito que atende no telefone da cidade vizinha, a escola que
    emprestou a linha. O número fica sinalizado, o sistema avisa, e o
    diretório continua funcionando.

    Fora da faixa o servidor ou corrige o número, ou marca como **recado** —
    o telefone do setor, onde alguém anota a mensagem e passa adiante.

O QUE NÃO É FAZIDO AQUI
    Este arquivo só responde "este número está dentro de alguma faixa nossa?".
    Quem valida o cadastro é o `mod_gest_cad_usuario`, que é dono do telefone.

EN: Ranges are stored in `tb_config` (key `faixas_telefone_prefeitura`) as a
JSON list of `{"inicio", "fim", "descricao"}`, all in digits. Multiple ranges.
"""

import json

# Chave de configuração. Uma lista de faixas, para a prefeitura poder
# cadastrar a central, a garagem, o almoxarifado e o que vier depois.
CONFIG_FAIXAS = "faixas_telefone_prefeitura"

# Faixa que vem na instalação. É um NÚMERO INVENTADO, da faixa que a ANPD
# reserva para exemplo (todos os zeros) — nunca o número de ninguém. Serve só
# para o sistema não começar sem nenhuma faixa, e vale até o administrador
# cadastrar a real pela tela de configurações. A faixa real de um município ou
# de uma empresa é informação DELE, e vai no `tb_config` dele, não no git:
# quem clona este repositório não deve herdar o telefone de ninguém.
FAIXA_INICIAL = {"inicio": "0000000000", "fim": "0000000099",
                 "descricao": "Faixa de exemplo — cadastre a real em Configurações"}


def _log():
    """Logger do núcleo (loguru), com fallback."""
    try:
        from mod_skyrover import observabilidade
        return observabilidade.get_logger("skyrover")
    except Exception:
        import logging
        return logging.getLogger("skyrover.telefone_faixas")


def _digitos(texto):
    """EN: Digits only, to compare a number against a range.

    PT-BR: Só os dígitos do número, para comparar faixa sem se preocupar com
    máscara, espaço ou o `+55` da frente."""
    try:
        return "".join(c for c in str(texto or "") if c.isdigit())
    except Exception:
        return ""


def _normalizar_faixa(bruto):
    """EN: Accepts a dict (or "inicio a fim" text) and returns the canonical form.

    PT-BR: Aceita `{'inicio','fim','descricao'}` e devolve a forma canônica.

    Devolve `None` se a faixa não fizer sentido (número curto demais) — uma
    faixa invertida é corrigida, não recusada: o usuário digitou o maior
    primeiro, e recusar por isso seria um erro de dedo tratado como erro de
    conceito. Uma faixa que INVERTE passaria a rejeitar todo número, e o
    aviso "fora da faixa" apareceria para o próprio telefone da prefeitura,
    que é exatamente o caso que destrói a confiança no aviso."""
    try:
        if isinstance(bruto, str):
            # aceita "0000000000 a 0000000099" colado no campo
            partes = [p for p in bruto.replace("-", " ").split() if p]
            if len(partes) >= 2:
                bruto = {"inicio": partes[0], "fim": partes[-1],
                         "descricao": " ".join(partes[1:-1])}
            else:
                return None
        inicio = _digitos(bruto.get("inicio"))
        fim = _digitos(bruto.get("fim"))
        if len(inicio) < 10 or len(fim) < 10:
            return None
        # uma faixa pode vir invertida (o usuário digitou o maior primeiro)
        if inicio > fim:
            inicio, fim = fim, inicio
        return {"inicio": inicio, "fim": fim,
                "descricao": str(bruto.get("descricao") or "").strip()}
    except Exception:
        return None


def faixa_inicial():
    """EN: The install-time range, so the screen has something to show.

    PT-BR: A faixa de instalação, para a tela ter o que mostrar."""
    return dict(FAIXA_INICIAL)


def listar_faixas(incluir_padrao=True):
    """EN: Every configured range, as `{"inicio","fim","descricao"}` in digits.

    PT-BR: Todas as faixas configuradas, em dígitos.

    Sem faixa cadastrada, devolve a faixa de instalação — um sistema sem
    nenhuma faixa avisaria "fora da faixa" para o próprio telefone da
    prefeitura, que é o caso que mais destrói a confiança no aviso.
    """
    try:
        from mod_skyrover.bd_conexao import get_config
        bruto = get_config(CONFIG_FAIXAS, "")
    except Exception as e:
        _log().warning(f"listar_faixas: falha ao ler a configuração ({e})")
        return [faixa_inicial()] if incluir_padrao else []

    faixas = []
    if bruto:
        try:
            dados = json.loads(bruto)
            if isinstance(dados, list):
                for item in dados:
                    normalizada = _normalizar_faixa(item)
                    if normalizada:
                        faixas.append(normalizada)
        except Exception as e:
            _log().warning(f"listar_faixas: configuração ilegível ({e})")
    if not faixas and incluir_padrao:
        faixas = [faixa_inicial()]
    return faixas


def salvar_faixas(ator, faixas):
    """EN: Saves the range list. Returns (ok, message).

    PT-BR: Grava a lista de faixas. Devolve (ok, mensagem).

    Faixa sem sentido é recusada com o nome dito — "a faixa de X tem o fim
    antes do início" é um erro que o usuário corrige sozinho; "erro ao
    salvar" não é."""
    try:
        validas, erros = [], []
        for i, bruto in enumerate(faixas or [], 1):
            if isinstance(bruto, dict) and not any(
                    str(bruto.get(k) or "").strip() for k in ("inicio", "fim")):
                continue  # linha em branco da tela
            normalizada = _normalizar_faixa(bruto)
            if normalizada:
                validas.append(normalizada)
            else:
                erros.append(f"faixa {i}")
        if not validas:
            return False, ("Informe pelo menos uma faixa válida "
                           "(início e fim com DDD + número).")
        from mod_skyrover.bd_conexao import set_config
        set_config(CONFIG_FAIXAS, json.dumps(validas, ensure_ascii=False))
        _log().info(f"faixas de telefone salvas por {ator}: {len(validas)}")
        if erros:
            return True, (f"{len(validas)} faixa(s) salva(s). "
                          f"Ignoradas por serem inválidas: {', '.join(erros)}.")
        return True, f"{len(validas)} faixa(s) de telefone salvas."
    except Exception as e:
        _log().exception(f"salvar_faixas: falha ({e})")
        return False, "Erro ao salvar as faixas de telefone."


def faixa_que_contem(numero):
    """EN: The range that contains this number, or None.

    PT-BR: A faixa que contém este número, ou None."""
    dig = _digitos(numero)
    if len(dig) < 10:
        return None
    # o usuário pode digitar com o 55 na frente; a comparação é pelos últimos
    # 10 dígitos (DDD + assinatura), que é onde a prefeitura opera
    for f in listar_faixas():
        inicio, fim = f["inicio"], f["fim"]
        comp = dig[-len(inicio):] if len(dig) > len(inicio) else dig
        if len(inicio) == len(comp) and inicio <= comp <= fim:
            return f
    return None


def numero_dentro_da_faixa(numero):
    """EN: (is_inside, range_that_matched). PT-BR: (está dentro, faixa que casou)."""
    f = faixa_que_contem(numero)
    return (f is not None), f


def faixa_mais_proxima(numero):
    """EN: A hint for a number outside every range — the closest own range.

    PT-BR: Uma dica para um número fora de todas as faixas — a faixa própria
    mais próxima.

    Serve ao aviso: "esse número está fora das faixas da prefeitura" é uma
    repreensão; "o número mais próximo é 0000000099, da Central" é uma ajuda
    para a pessoa descobrir o dela. A diferença entre as duas frases é a
    diferença entre o usuário arrumar o cadastro e o usuário desistir dele.
    """
    dig = _digitos(numero)
    if len(dig) < 10:
        return None
    melhor, distancia = None, None
    for f in listar_faixas():
        for alvo in (f["inicio"], f["fim"]):
            alvo_curto = alvo[-len(dig):] if len(alvo) > len(dig) else alvo
            if len(alvo_curto) != len(dig):
                continue
            d = abs(int(dig) - int(alvo_curto))
            if distancia is None or d < distancia:
                distancia, melhor = d, f
    return melhor
