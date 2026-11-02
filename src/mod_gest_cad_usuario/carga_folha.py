"""EN: Syncs the collected server sheet into the user register.

PT-BR: Sincroniza a folha de servidores coletada no cadastro de usuários.

O QUE ESTE SCRIPT FAZ
    Lê o arquivo produzido por `coleta_folha.py` e grava cada servidor em
    `mod_gest_cad_usuario`, criando o que é novo e atualizando o que mudou.
    Pode rodar quantas vezes quiser: rodar duas vezes não duplica ninguém.

A MATRÍCULA É O NOME DE USUÁRIO
    A prefeitura já tem um identificador único e público para cada servidor,
    e ele é o login. Não há senha inventada a memorizar, não há colisão de
    nome entre homônimos (que no interior do Brasil não é raro) e o servidor
    reconhece o próprio número de matrícula na tela de login.

O QUE NÃO ENTRA NO BANCO
    Telefone. O portal não publica ramal — e esta escolha é do usuário que
    pediu, não um limite técnico. Todo servidor nasce com `telefone_pendente`
    ligado: no primeiro acesso, depois de trocar a senha, o sistema pergunta
    celular particular, celular da prefeitura e fixo da prefeitura, cada
    um com a sua caixa de "pode aparecer na lista telefônica?". O fixo da
    prefeitura publica sozinho, porque linha institucional existe para ser
    achada; o celular é escolha de cada pessoa.

QUEM NASCE BLOQUEADO
    Pensionista, Inativo e Eleito entram no cadastro — o registro é obrigatório
    e o histórico importa — mas bloqueados: não podem entrar no sistema. O
    mesmo vale para quem está com situação "Demitido". Bloquear é reversível
    pelo administrador; apagar não seria.

COMO USAR
    python mod_gest_cad_usuario/carga_folha.py            # ensaia
    python mod_gest_cad_usuario/carga_folha.py --aplicar   # grava
    python mod_gest_cad_usuario/carga_folha.py --aplicar --competencia 07/2026

    Sem `--aplicar` nada é escrito: o script só mostra o que faria.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime

# A raiz do repositório é UM nível acima do módulo. Dois `..` subiam um nível
# demais e faziam `caminho_csv` relativo resolver para fora do repositório —
# o "arquivo não encontrado" apontava para um caminho que não existe e não
# deixava pista de onde veio o erro.
RAIZ_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, RAIZ_REPO)

# A folha mora em `dados/`, dentro do módulo, e fora do git (AGENTS.md §1 e
# §8.3): os dados são de servidores reais e não vão para o histórico.
DIR_DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")
ARQUIVO_PADRAO = os.path.join(DIR_DADOS, "funcionarios.json")
SENHA_PROVISORIA = "123456"
# Competencia da folha em sincronizacao: carimba a remuneracao, para que
# o historico diga de que mes e o valor. A folha traz o campo por servidor;
# esta e a reserva para quando vier vazio.
COMPETENCIA_FOLHA = ""
ATOR = "carga_folha"

# Vínculos que continuam no cadastro (o registro é obrigatório) mas não podem
# entrar no sistema: quem não está mais vinculado não tem por que logar.
VINCULOS_BLOQUEADOS = {"pensionista", "inativo", "eleito", "exonerado"}
SITUACOES_BLOQUEADAS = {"demitido", "exonerado", "afastado"}

# ---- TODOS NASCEM BLOQUEADOS (decisão do responsável, 06/10/2026) ----
# Antes, `VINCULOS_BLOQUEADOS`/`SITUACOES_BLOQUEADAS` decidiam quem entrava
# fechado, e todo o resto nascia LIBERADO: 1.076 dos 1.159 servidores do
# `funcionarios.json` entravam com senha `123456` e acesso liberado, sem nunca
# terem passado pelo DTI.
#
# Agora a regra é outra, e é do responsável: a folha importa e CADASTRA todo
# mundo, mas **toda conta nasce bloqueada** e só entra depois de passar pelo
# DTI. Registro é obrigatório; acesso não.
#
# Consequência medida: 1.076 contas Ativo passam a `user_ativo=0`, e o DTI
# precisa liberá-las. a conta do administrador, `qacomum` e `qamaster` NÃO estão na folha e
# seguem liberados — é por isso que ainda dá para administered o banco depois
# da carga.
#
# `VINCULOS_BLOQUEADOS` e `SITUACOES_BLOQUEADAS` continuam existindo, e
# continuam valendo: o DTI pode liberar um servidor que a folha diz estar
# ativo; mas a folha NUNCA reabre uma conta que está fechada. O caminho de
# volta de `_bloquear_apos_espelho` mudou por isso — ver `liberado_pelo_dti`
# e o bloco de comentário dessa função.
#
# A consequência de manutenção que vem junto: um servidor que é READMITIDO
# depois de ter saído (o pensionista que o RH recontrata) **não volta sozinho**.
# O DTI precisa liberá-lo de novo, e é essa a hora de conferir o telefone.
NASCEM_BLOQUEADOS = True

# =====================================================================
#  COMPETÊNCIA: `SKYROVER_FOLHA_MES` (03/10/2026)
# =====================================================================
# POR QUE A VARIÁVEL DE AMBIENTE
#
# A competência é o que dá sentido a toda a parte nova: o histórico
# salarial cresce por competência, o movimento de demissão é "da folha de
# 10/2026", e o carimbo de "última carga" evita refazer o que já foi
# feito. Sem poder escolher a competência, nada disso pode ser conferido
# antes da hora — e é exatamente antes da hora que a prefeitura precisa
# conferir: a folha de outubro só é publicada em novembro, e quem prepara
# a conferência precisa rodá-la antes dela existir.
#
# `SKYROVER_FOLHA_MES` é o que permite "rodar a verificação do mês que
# vem" com uma folha que ainda não foi publicada.
#
# FORMATOS ACEITOS: `MM/AAAA` e `AAAA-MM`. O que sai daqui é sempre
# `MM/AAAA` — o mesmo formato que o portal usa e que o histórico usa, para
# que comparar competência seja comparar duas coisas do mesmo formato.
VAR_AMB_COMPETENCIA = "SKYROVER_FOLHA_MES"


def normalizar_competencia(valor):
    """`'10/2026'`, `'2026-10'`, `'10-2026'` -> `'10/2026'`. `''` se não der.

    Recusa o que não parece competência em vez de adivinhar: `'10'` pode
    ser o mês, o ano ou uma matrícula, e carregar a folha carimbando a
    competência errada contamina o histórico salarial de mil e poucas
    pessoas com um número inventado.
    """
    try:
        bruto = str(valor or "").strip()
        if not bruto:
            return ""
        partes = re.split(r"[/\-.]", bruto)
        if len(partes) != 2:
            return ""
        a, b = partes[0].strip(), partes[1].strip()
        if not (a.isdigit() and b.isdigit()):
            return ""
        if len(a) == 4 and len(b) in (1, 2):
            ano, mes = a, int(b)
        elif len(b) == 4 and len(a) in (1, 2):
            mes, ano = int(a), b
        else:
            return ""
        if not (1 <= mes <= 12) or len(ano) != 4:
            return ""
        return f"{mes:02d}/{ano}"
    except Exception:
        return ""


def competencia_da_folha(folha, cfg=None):
    """A competência que esta carga vai gravar, já resolvida.

    A ordem é deliberada:

    1. `SKYROVER_FOLHA_MES` — ordem explícita do administrador, que vence
       tudo. É o botão de "processar o mês que vem".
    2. a competência que vem no arquivo (`folha['competencia']`) — o que
       o portal diz ser.
    3. a competência da configuração (`fonte_folha.json`) — o que quem
       configurou disse ser.
    4. a de hoje (`MM/AAAA` da data local).

    O passo 4 é o que mata a competência VAZIA, que era o estado medido
    neste repositório: `.ultima_carga.json` estava com `"competencia": ""`
    e o histórico de remuneração recebia linha sem competência — o que
    deixa a linha inútil para a única pergunta que ela existe para
    responder.

    Devolve `(competencia, aviso)`. O aviso diz de onde veio, e é o que a
    carga imprime — porque uma competência forçada por variável de
    ambiente precisa ficar visível, senão ninguém sabe por que o mês
    gravado não é o do portal.
    """
    forca = normalizar_competencia(os.environ.get(VAR_AMB_COMPETENCIA))
    if forca:
        return forca, (f"competência FORÇADA por {VAR_AMB_COMPETENCIA}="
                       f"{forca}")
    do_arquivo = normalizar_competencia((folha or {}).get("competencia"))
    if do_arquivo:
        return do_arquivo, ""
    try:
        if cfg is None:
            cfg, _aviso = carregar_config()
        da_config = normalizar_competencia(cfg.get("competencia"))
    except Exception:
        da_config = ""
    if da_config:
        return da_config, "competência vinda de fonte_folha.json"
    return datetime.now().strftime("%m/%Y"), \
        "competência do dia (a folha não trouxe)"


def _log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "")
                   if not unicodedata.combining(c)).lower().strip()


def _bonito(texto: str) -> str:
    """`Secretaria Municipal De Educacao Publica` -> `Secretaria Municipal de Educacao Publica`.

    O portal guarda TUDO em caixa alta e sem acento, porque é assim que vai
    para o banco municipal. Mostrar "DE EDUCACAO" na lista telefônica da
    própria prefeitura é feio; mas inventar o acento (`EDUCAÇÃO`) é pior,
    porque passa a ser um dado que a fonte não disse. Aqui só se mexe na
    caixa — as minúsculas viram minúsculas, os acentos ficam como estão.
    """
    limpo = (texto or "").strip()
    if not limpo:
        return ""
    # "De Educacao" -> "de Educacao": preposições e artigos em minúscula
    minusculas = {"de", "da", "do", "das", "dos", "e", "a", "o"}
    partes = limpo.split()
    saida = []
    for i, p in enumerate(partes):
        if i > 0 and _sem_acento(p) in minusculas:
            saida.append(p.lower())
        else:
            saida.append(p)
    return " ".join(saida)


def _bloqueado(reg: dict) -> tuple[bool, str]:
    """Diz se o servidor entra bloqueado, e por quê.

    Desde 06/10/2026 a resposta é **sim para todo mundo**: a folha cadastra o
    servidor, mas ninguém entra sem passar pelo DTI. `_sem_acento` e as duas
    listas continuam vivos porque o motivo ainda é gravado na auditoria e é o
    que o DTI lê para saber por que o servidor está fora — mas eles já não
    decidem NADA sozinhos.
    """
    if NASCEM_BLOQUEADOS:
        return True, "aguardando liberação do DTI"
    vinculo = _sem_acento(reg.get("vinculo"))
    situacao = _sem_acento(reg.get("situacao"))
    if vinculo in VINCULOS_BLOQUEADOS:
        return True, f"vínculo {reg.get('vinculo')}"
    if situacao in SITUACOES_BLOQUEADAS:
        return True, f"situação {reg.get('situacao')}"
    return False, ""


def _matricula(reg: dict) -> str:
    """The login. Digits only — a matrícula with punctuation would be a
    different login depending on how the user typed it."""
    return "".join(c for c in str(reg.get("matricula") or "") if c.isdigit())


def _arvore_real(folha: dict) -> dict:
    """Monta a estrutura secretaria -> departamento a partir da folha.

    O portal dá DUAS coisas: `unidade` (a secretaria) e `lotacao` (o
    departamento dentro dela). Quando as duas são iguais, o servidor está
    ligado direto na secretaria e não há departamento a criar."""
    arvore, ordem = {}, {}
    for reg in folha.get("servidores") or []:
        sec = _bonito(reg.get("unidade"))
        if not sec:
            continue
        arvore.setdefault(sec, set())
        if sec not in ordem:
            ordem[sec] = len(ordem) + 1
        lot = _bonito(reg.get("lotacao"))
        if lot and _sem_acento(lot) != _sem_acento(sec):
            arvore[sec].add(lot)
    return {"secretarias": {k: sorted(v) for k, v in arvore.items()},
            "ordem": ordem}


def sincronizar_unidades(folha: dict, aplicar: bool = False) -> dict:
    """Monta o organograma que a folha conhece e pede para grava-lo.

    ESTE MÓDULO NÃO FALA COM A LISTA TELEFÔNICA
        A folha é do módulo de cadastro; o organograma gravado é do módulo da
        lista telefônica, que tem banco próprio. Módulo de negócio não importa
        módulo de negócio — nem para ler, muito menos para escrever
        (AGENTS.md §2, e `check_integridade.py` reprova a aresta). Por isso
        este arquivo só monta o PLANO e chama a fachada do núcleo, que costura
        com `mod_lista_telefonica.bd_manipulador.sincronizar_organograma`.

    POR QUE DESATIVAR E NÃO APAGAR
        O banco pode vir com um organograma de demonstração (12 secretarias
        fictícias, semeado por uma instalação anterior). Diante da folha real,
        elas viram pastas vazias na lista telefônica de uma prefeitura de
        verdade — confusão pura. Mas apagar é definitivo, e pasta vazia tem
        vez: o administrador pode estar montando um organograma que a folha
        ainda não publica. Então: `ativo=0`, que some da lista e pode voltar
        com um UPDATE. Nada é destruído.

    A ÁRVORE É RECIÁVEL
        Rodar de novo não duplica: casa por nome normalizado (sem acento, sem
        caixa, só letras e números), que é a mesma regra de
        `mod_lista_telefonica.bd_manipulador._norm` — duas grafias de "Saúde"
        são a mesma secretaria.
    """
    try:
        from mod_skyrover import integracoes
        modelo = _arvore_real(folha)
        # Plano flat, de raiz para a folha: (nome, tipo, pai, ordem).
        plano = []
        for i, (sec, setores) in enumerate(sorted(
                modelo["secretarias"].items(),
                key=lambda kv: modelo["ordem"].get(kv[0], 999))):
            plano.append((sec, "secretaria", None, i))
            for j, setor in enumerate(sorted(setores)):
                plano.append((setor, "setor", sec, j))
        return integracoes.sincronizar_organograma_cadastro(
            plano, aplicar=aplicar, ator=ATOR)
    except Exception as e:
        _log(f"  organograma nao sincronizado: {e}")
        return {"secretarias_criadas": 0, "setores_criadas": 0,
                "setores_criados": 0, "reativadas": 0, "desativadas": 0,
                "erros": [str(e)]}


def _comparar_dados(unidade_atual, lotacao_atual, cargo_atual,
                    unidade_nova, lotacao_nova, cargo_nova) -> str:
    """Monta o texto do alerta comparando o cadastro com a folha.

    O texto é escrito **para o servidor ler**, não para o técnico: "seu
    departamento mudou de A para B" e não "lote divergente: atual=..., novo=
    ...". A diferença é que o primeiro se responde, e o segundo só se
    traduz.

    Devolve "" quando não há diferença — e compara SEM ACENTO, porque o
    portal guarda "Educacao" e o cadastro pode ter "Educação" sem que isso
    seja mudança de setor. Sem essa tolerância, metade da prefeitura
    receberia um alerta por causa de acento.
    """
    partes = []
    for rotulo, atual, novo in (("secretaria", unidade_atual, unidade_nova),
                                ("departamento", lotacao_atual, lotacao_nova),
                                ("cargo", cargo_atual, cargo_nova)):
        atual = (atual or "").strip()
        novo = (novo or "").strip()
        if not novo:
            continue  # a folha não trouxe: não é mudança, é ausência
        if _sem_acento(atual) == _sem_acento(novo):
            continue
        if not atual:
            partes.append(f"o seu {rotulo} agora é \"{novo}\"")
        else:
            partes.append(f"seu {rotulo} mudou de \"{atual}\" para \"{novo}\"")
    if not partes:
        return ""
    return "; ".join(partes).capitalize() + "."


def _esta_ativo(bd, user_nome) -> bool:
    """A conta está ativa (não bloqueada) no cadastro?

    **O `cursor()` AQUI É O QUE FAZ ESTA FUNÇÃO FUNCIONAR (03/10/2026).**
    `get_connection()` devolve a CONEXÃO; quem lê é o CURSOR. O código
    antigo fazia `cur = bd.get_connection()`, chamava `cur.execute(...)`
    — que no `sqlite3` funciona, porque a conexão tem um método
    `execute` próprio — e depois `cur.fetchone()` na CONEXÃO, que não
    existe. O `AttributeError` caía no `except` e a função devolvia
    `True` para TODA conta, sempre. Ou seja: `_esta_ativo` dizia "está
    ativo" mesmo com `user_ativo=0`, e o caminho de volta da folha (o
    pensionista que o RH recontratou) nunca desbloqueava ninguém —
    silenciosamente, porque "não erro" é o que a tela mostra.

    O `except` continua devolvendo `True` (não se pode desbloquear conta
    por falta de leitura), mas agora ele só dispara em falha de verdade.
    """
    try:
        conn = bd.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT user_ativo FROM tb_usuarios WHERE user_nome=?",
                        (user_nome,))
            linha = cur.fetchone()
        finally:
            conn.close()
        return bool(linha and linha[0])
    except Exception as e:
        _log(f"  {_esta_ativo.__name__}: nao deu para ler {user_nome} ({e})")
        return True


def _nome_normalizado(texto: str) -> str:
    """Nome de comparação: sem acento, em caixa alta, só letras.

    É a MESMA regra que casa contrato com pessoa. Uma normalização só no
    módulo inteiro é o que impede a divergência que faria o mesmo nome
    casar num lugar e não no outro — que era a forma como o `teto_maximo_mb`
    virou decorativo.

    Só letras (espaço fora): o portal traz preposições que mudam de
    grafia ("Da Silva" / "da Silva") e sufixos que não comparam. O que
    sobra é o nome próprio, que é o que identifica a pessoa.
    """
    base = unicodedata.normalize("NFKD", str(texto or ""))
    limpo = "".join(c for c in base if not unicodedata.combining(c))
    return "".join(c for c in limpo.upper() if c.isalpha())


def _recolher_dados(reg: dict, matricula: str) -> dict:
    """Os 14 campos do portal, no dicionário que `gravar_dados_folha` grava.

    `matricula` entra separada porque `tb_usuarios` NÃO tem coluna de
    matrícula — o login É a matrícula. Em `tb_contratos` ela é a chave
    única.
    """
    unidade = _bonito(reg.get("unidade"))
    lotacao = _bonito(reg.get("lotacao"))
    # A lotação repete a unidade quando o servidor está ligado direto na
    # secretaria, sem departamento. Repetir na ficha é ruído — e é ruído
    # que apareceria como "mesmo departamento" no sinal de colisão de nomes.
    if _sem_acento(lotacao) == _sem_acento(unidade):
        lotacao = ""
    return {
        "matricula": matricula,
        "nome": (reg.get("nome") or "").strip(),
        "unidade": unidade,
        "lotacao": lotacao,
        "cargo": _bonito(reg.get("cargo")),
        "vinculo": (reg.get("vinculo") or "").strip(),
        "situacao": (reg.get("situacao") or "").strip(),
        "tipo": (reg.get("tipo") or "").strip(),
        "admissao": (reg.get("admissao") or "").strip(),
        # `exoneracao`, `regime` e `carga_horaria` vêm SEMPRE vazios do
        # portal (medido: 0 preenchidos em 1.159 registros). São gravados
        # assim mesmo, porque a folha é a fonte e o portal pode começar a
        # publicá-los; sem a coluna, esse dia seria migração.
        "exoneracao": (reg.get("exoneracao") or "").strip(),
        "regime": (reg.get("regime") or "").strip(),
        "carga_horaria": (reg.get("carga_horaria") or "").strip(),
        "remuneracao": (reg.get("remuneracao") or "").strip(),
        "ficha_contracheque": (reg.get("ficha_contracheque") or "").strip(),
    }


def _decidir_destino(bd, mat, nome, mapa_nomes):
    """Para quem é esta matrícula? Devolve (alvo, marca_revisar, situacao).

    Três desfechos, nesta ordem:

    - `contrato`: a matrícula já está em `tb_contratos`. A pessoa é a
      dona do contrato — não importa mais o que o nome diga, porque a
      matrícula é o identificador que o portal garante.
    - `pessoa`: existe um usuário cujo LOGIN é esta matrícula, mas ainda
      sem contrato gravado. É a instalação que já tinha o cadastro cheio
      antes de 03/10/2026: o contrato é criado sem mexer no login.
    - `novo`: nome normalizado bate com uma pessoa que já existe — entra
      como CONTRATO ADICIONAL, marcado para revisão; ou, sem nome
      conhecido, nasce pessoa nova com a matrícula como login.

    Devolve também o texto do aviso quando há mais de uma pessoa com o
    mesmo nome normalizado, porque escolher uma delas em silêncio é a
    decisão que este módulo não tem o direito de tomar.

    Sempre quatro valores: `(alvo, marca_revisar, tipo_destino, aviso)`.
    """
    contrato = bd.contrato_por_matricula(mat)
    if contrato:
        return contrato.get("user_nome") or mat, "", "contrato", ""
    if bd.obter_usuario(mat):
        return mat, "", "pessoa", ""
    candidatos = mapa_nomes.get(_nome_normalizado(nome)) or []
    if candidatos:
        aviso = ""
        if len(candidatos) > 1:
            aviso = (f"{mat}: {len(candidatos)} pessoas com o mesmo nome "
                     f"normalizado ({', '.join(candidatos)}) — ligado à "
                     f"primeira; revise em Contratos")
        return candidatos[0], candidatos[0], "contrato_adicional", aviso
    return mat, "", "pessoa_nova", ""


def sincronizar(folha: dict, aplicar: bool = False) -> dict:
    """Percorre a folha e cria/atualiza cada servidor. Devolve o resumo.

    **O QUE MUDOU (03/10/2026).** Antes, `sincronizar` gravava três campos
    por `definir_dados_funcionais`, mais vínculo/situação e remuneração em
    chamadas separadas — cinco lugares escrevendo em `tb_usuarios`, cada um
    com sua lista de campos. Hoje toda a gravação da folha passa por
    `bd.gravar_dados_folha`, que itera `CAMPOS_FONTE_FOLHA`: um campo novo
    entra na folha e na coluna no mesmo lugar, e não há como um lado
    gravar e o outro não.

    **A PESSOA E O CONTRATO.** Uma linha da folha é uma MATRÍCULA, e uma
    matrícula é um CONTRATO. Matrícula nova cujo nome normalizado já
    existe como pessoa vira contrato ADICIONAL dessa pessoa, marcado com
    `mesmo_nome_de` para revisão — porque nome igual pode ser homônimo, e
    fundir errado é pior do que perguntar. Medido em 09/2026: 1.159
    matrículas distintas e 5 nomes repetidos.

    **A CONTA NÃO É DESLIGADA PELA FOLHA.** Quem aparece Demitido continua
    com a conta exatamente como estava: grava-se
    `folha_situacao_atual`/`_anterior`/`data_movimento` e a linha em
    `tb_historico_movimentos`, e quem desliga é o administrador, por
    `user_ativo`. Já a conta que NASCE na folha com vínculo ou situação de
    fora (pensionista, inativo, eleito, demitido) nasce bloqueada: é uma
    decisão de criação, não um desligamento de quem já usava o sistema.

    EN: Walks the sheet, one contract per matrícula, and writes every
    sheet field through a single path.
    """
    global COMPETENCIA_FOLHA
    from mod_gest_cad_usuario import bd_manipulador as bd
    folha_competencia, aviso_comp = competencia_da_folha(folha)
    COMPETENCIA_FOLHA = folha_competencia

    servidores = folha.get("servidores") or []
    resumo = {"criados": 0, "nomes_corrigidos": 0, "marcados": 0,
              "a_marcar": 0, "inalterados": 0, "bloqueados": 0,
              "desbloqueados": 0, "erros": [], "vinculos": {},
              "competencia": folha_competencia,
              "aviso_competencia": aviso_comp,
              "contratos_novos": 0, "para_revisar": 0, "movimentos": 0,
              "remuneracoes": 0, "contratos_por_pessoa": 0}

    # Mapa nome-normalizado -> [logins], montado UMA vez: 1.159 linhas
    # contra a lista de pessoas a cada linha dariam 1,3 milhão de
    # comparações por carga, e o ganho seria zero.
    try:
        mapa_nomes = bd.pessoas_por_nome_normalizado()
    except Exception as e:
        _log(f"  nao deu para montar o mapa de nomes ({e}); "
             f"esta carga nao une contratos")
        mapa_nomes = {}

    # Pessoas tocadas por esta folha: o espelho delas é gravado no
    # SEGUNDO passo, depois que todos os contratos estão no banco.
    alvos = set()
    # matrícula -> a folha diz que ESTE contrato está de fora. A chave é a
    # matrícula, não o login, porque pessoa com dois contratos tem duas
    # situações e só a do principal decide o bloqueio.
    bloqueios_por_matricula = {}

    for i, reg in enumerate(servidores, 1):
        mat = ""
        try:
            mat = _matricula(reg)
            nome = (reg.get("nome") or "").strip()
            if not mat or not nome:
                resumo["erros"].append(f"linha {i}: sem matrícula ou nome")
                continue

            bloq, _motivo = _bloqueado(reg)
            vinculo = reg.get("vinculo") or "(sem vínculo)"
            resumo["vinculos"][vinculo] = resumo["vinculos"].get(vinculo, 0) + 1
            dados = _recolher_dados(reg, mat)

            alvo, marca, tipo_destino, aviso_destino = mat, "", "pessoa_nova", ""
            try:
                alvo, marca, tipo_destino, aviso_destino = _decidir_destino(
                    bd, mat, nome, mapa_nomes)
            except Exception as e:
                resumo["erros"].append(f"linha {i} ({mat}): destino {e}")
                continue
            if aviso_destino:
                resumo["erros"].append(aviso_destino)

            if tipo_destino == "pessoa_nova":
                if not aplicar:
                    resumo["criados"] += 1
                    resumo["contratos_novos"] += 1
                    continue
                ok_c, msg_c = bd.criar_usuario(
                    ATOR, mat, SENHA_PROVISORIA, perfil="comum",
                    nome_completo=nome, exigir_telefone=True)
                if not ok_c:
                    resumo["erros"].append(f"{mat}: {msg_c}")
                    continue
                resumo["criados"] += 1
                ok_g, msg_g = bd.gravar_contrato(ATOR, mat, dados,
                                                 folha_competencia,
                                                 principal=True)
                if not ok_g:
                    resumo["erros"].append(f"{mat}: {msg_g}")
                    continue
                resumo["contratos_novos"] += 1
                mapa_nomes.setdefault(_nome_normalizado(nome), []).append(mat)
            else:
                # `contrato`, `pessoa` ou `contrato_adicional`: nos três já
                # existe alguém, e o que falta é ATUALIZAR o contrato com
                # o que a folha traz hoje.
                #
                # O `contrato` (matrícula já registrada) tem de entrar
                # aqui também — e sem ele o contrato nunca era atualizado:
                # a carga criava pessoa e contrato na primeira vez e, em
                # todas as seguintes, escrevia o espelho com o valor
                # ANTIGO que estava em `tb_contratos`. Medido: mudar o
                # departamento na folha de outubro não mudou nada —
                # 0 movimentos, 0 pendências, e o espelho igual ao de
                # setembro. O relatório dizia "inalterados: 1", que era
                # literalmente verdade e não queria dizer nada.
                if tipo_destino == "contrato_adicional":
                    resumo["para_revisar"] += 1
                    resumo["contratos_por_pessoa"] += 1
                if not aplicar:
                    continue
                ok_g, msg_g = bd.gravar_contrato(
                    ATOR, alvo, dados, folha_competencia,
                    mesmo_nome_de=marca)
                if not ok_g:
                    resumo["erros"].append(f"{mat}: {msg_g}")
                    continue

            # ---- nome de exibição (objetivo, sem perguntar) ----
            try:
                linha = bd.obter_usuario(alvo)
                if linha and _sem_acento(linha[9] or "") != _sem_acento(nome):
                    if aplicar:
                        bd.editar_usuario(ATOR, alvo, nome_completo=nome,
                                          auditar=False)
                    resumo["nomes_corrigidos"] += 1
            except Exception as e:
                _log(f"  {alvo}: nome nao conferido ({e})")

            # ---- bloqueio do ACESSO (decidido no SEGUNDO passo) ----
            # Guardado aqui, aplicado lá: só no segundo passo se sabe
            # qual é o contrato PRINCIPAL da pessoa, e é o principal que
            # decide se a conta fica fechada. Ver `_bloquear_apos_espelho`.
            #
            # Por que guardar o valor da LINHA e não da PESSOA: pessoa
            # com dois contratos tem duas situações, e o que vale é a do
            # principal. Com a linha decidindo, um contrato secundário
            # "Demitido" bloqueava a pessoa cujo contrato principal é
            # "Ativo" — medido, e é o tipo de erro que só aparece quando
            # alguém com dois contratos tenta entrar.
            if bloq:
                resumo["bloqueados"] += 1
                bloqueios_por_matricula[mat] = True
            else:
                bloqueios_por_matricula[mat] = False

            # A pessoa fica na lista para o SEGUNDO passo.
            alvos.add(alvo)

            if i % 100 == 0 or i == len(servidores):
                _log(f"  {i}/{len(servidores)} "
                     f"(criados {resumo['criados']}, "
                     f"contratos {resumo['contratos_novos']}, "
                     f"revisar {resumo['para_revisar']})")
        except Exception as e:
            resumo["erros"].append(f"linha {i} ({mat or '?'}): {e}")

    # =================================================================
    #  SEGUNDO PASSO: o espelho da pessoa (03/10/2026)
    # =================================================================
    # Por que só agora, e não dentro do laço:
    #
    # Uma pessoa com DOIS contratos tem dois salários e dois cargos, e
    # `tb_usuarios` tem UMA coluna de cada. Escrever pelos dois dentro do
    # laço fazia a última matrícula da folha ganhar sempre — e, como a
    # ordem da folha é a do portal, o espelho mudava a cada carga, sem
    # que ninguém tivesse mudado nada. Medido: rodar a folha duas vezes
    # deixava 6 pendências e 20 movimentos novos, todos da mesma causa.
    #
    # Quem escreve no espelho é o contrato PRINCIPAL, que é o de MENOR
    # matrícula. Com os contratos já registrados, dá para saber qual é
    # sem depender da ordem em que o portal devolveu as linhas — o que
    # também faz a carga ser repetível.
    #
    # E o valor gravado é o do contrato principal, VERBATIM. Sem soma de
    # contratos, sem média, sem "valor consolidado": o portal publica um
    # valor por matrícula, e o que a tela mostra é o valor que a folha
    # publicou para aquela matrícula.
    if aplicar:
        _espelhar_principais(bd, alvos, folha_competencia, resumo,
                             bloqueios_por_matricula)
    return resumo


def _liberado_pelo_dti(bd, user_nome) -> bool:
    """Esta conta já passou pelo DTI? Não é tocada pela folha.

    Lê `liberado_pelo_dti`. Fail-soft devolvendo `False`: um banco ilegível
    aqui faz a folha conferir a conta — que é o comportamento de sempre — e
    não o contrário, porque o efeito colateral de errar seria devolver acesso
    a quem o DTI fechou.
    """
    try:
        conn = bd.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT liberado_pelo_dti FROM tb_usuarios "
                        "WHERE user_nome=?", (user_nome,))
            linha = cur.fetchone()
        finally:
            conn.close()
        return bool(linha and linha[0])
    except Exception as e:
        _log(f"  {_liberado_pelo_dti.__name__}: nao deu para ler {user_nome} ({e})")
        return False


def _bloquear_apos_espelho(bd, alvo, matricula_principal, folha_manda_bloquear,
                           gravado, resumo):
    """Aplica o bloqueio/debloqueio do ACESSO, depois do espelho.

    **A REGRA, E POR QUE ELA DEPENDE DE SABER SE É O PRIMEIRO REGISTRO.**
    A folha não desliga conta de quem estava usando o sistema — o
    desligamento é decisão do administrador, por `user_ativo`, e a folha
    só registra o movimento. Mas a conta que NASCE na folha com vínculo
    ou situação de fora (pensionista, inativo, eleito, demitido) nasce
    bloqueada, e esse é um requisito antigo do módulo: registro é
    obrigatório, acesso não.

    São dois casos, e a diferença é `primeiro_registro`:

    - `primeiro_registro=True` (nunca teve dado de folha): a conta acaba
      de nascer. Se a folha diz que está de fora, bloqueia — e a pessoa
      nunca entrou no sistema, então nada foi desligado.
    - `primeiro_registro=False` (já tem folha): a pessoa JÁ TRABALHAVA
      AQUI. A folha dizer "Demitido" grava `folha_situacao_atual`,
      `data_movimento` e o movimento, e **não** mexe em `user_ativo`.
      Quem desliga é o administrador, com o motivo e a data na mão.

    O caminho de volta existe nos dois casos: se a folha deixa de dizer
    que a pessoa está de fora, e a conta está bloqueada, ela abre. Sem
    isso, um servidor que o RH recontratou ficaria preso sem que ninguém
    soubesse por quê.

    `matricula_principal` decide, e não a pessoa inteira: pessoa com dois
    contratos tem duas situações, e é a do contrato PRINCIPAL que diz se
    a conta fica fechada. Um contrato secundário "Demitido" não fecha a
    conta de quem tem um contrato "Ativo" como principal — que é o caso
    real do professor com contrato efetivo e contrato determinado.
    """
    try:
        # ---- O LIBERADO PELO DTI É AUTORITATIVO (06/10/2026) ----
        # Este `if` vem ANTES de tudo, e é o que impede a folha de desfazer o
        # trabalho do DTI a cada boot.
        #
        # Sem ele, o CAMINHO DE VOLTA desta função seria acionado para os
        # 1.076 servidores Ativo: a folha não os manda bloquear (a regra nova
        # manda bloquear todo mundo na CRIAÇÃO, mas quem já foi liberado não
        # entra de novo nessa regra), a conta está fechada, e o
        # `bloquear_usuario(..., False)` a reabria. Na prática: o DTI fecha, o
        # servidor reinicia a máquina, e o acesso volta sozinho. Visto por
        # leitura do código antes de rodar — é o tipo de defeito que só
        # apareceria de madrugada, e como "funciona", ninguém reclamaria.
        #
        # `liberado_pelo_dti` é a marca de que alguém passou pelo DTI. Quem
        # tem a marca não é tocado pela folha, em nenhum sentido do acesso.
        if _liberado_pelo_dti(bd, alvo):
            return

        if folha_manda_bloquear:
            # Só a conta que ACABOU DE NASCER entra bloqueada. E a
            # condição NÃO é "está inativo": `criar_usuario` grava
            # `user_ativo=1`, então quem nasce de fora está ATIVO no
            # momento desta chamada, e esperar o oposto deixava o
            # requisito antigo (pensionista/inativo/eleito/demitido não
            # entram) sem efeito nenhum — medido: `bloqueados_aplicados`
            # ficava `None` e as contas nasciam ativas.
            #
            # Quem já tem folha NÃO é tocado, mesmo que a folha diga
            # "demitido": desligar é decisão do administrador.
            if gravado.get("primeiro_registro"):
                bd.bloquear_usuario(ATOR, alvo, True)
                resumo["bloqueados_aplicados"] = \
                    resumo.get("bloqueados_aplicados", 0) + 1
            return
        # CAMINHO DE VOLTA: a folha deixou de dizer que a pessoa está de
        # fora e a conta está fechada. `_esta_ativo` devolve True para
        # quem está ativo — e quem já está ativo não precisa de nada.
        if _esta_ativo(bd, alvo):
            return
        bd.bloquear_usuario(ATOR, alvo, False)
        resumo["desbloqueados_aplicados"] = \
            resumo.get("desbloqueados_aplicados", 0) + 1
    except Exception as e:
        _log(f"  {alvo}: bloqueio nao aplicado ({e})")


def _espelhar_principais(bd, alvos, competencia, resumo,
                         bloqueios_por_matricula=None):
    """Grava os campos da folha em `tb_usuarios`, a partir do contrato principal.

    Um laço sobre as pessoas tocadas pela folha: lê o contrato principal
    do banco (que acabou de ser gravado) e escreve os 12 campos no
    espelho da pessoa, mais o histórico salarial. Nunca inventa o
    principal — se `recalcular_principais_em_lote` não achou contrato
    para alguém, essa pessoa é pulada e o motivo vai para os erros,
    porque um espelho sem contrato por trás não tem de onde ter vindo.

    **O PRINCIPAL É CALCULADO EM LOTE, DE PROPÓSITO.** Com uma conexão
    por pessoa, o custo medido era de 114 ms por pessoa em checkpoint de
    WAL — 132 segundos numa carga inteira, para descobrir qual das
    matrículas é a menor. Em lote são 0,3 ms por pessoa. `alvos` tem
    1.159 entradas e a diferença entre as duas formas é a diferença
    entre uma carga que roda e uma que não.
    """
    try:
        principais = bd.recalcular_principais_em_lote(alvos)
    except Exception as e:
        _log(f"  _espelhar_principais: principais nao calculados ({e})")
        principais = {}
    bloqueios_por_matricula = bloqueios_por_matricula or {}
    try:
        for alvo in sorted(alvos):
            try:
                principal = principais.get(alvo)
                if not principal:
                    resumo["erros"].append(
                        f"{alvo}: nenhum contrato gravado — espelho da folha "
                        f"nao foi escrito")
                    continue
                contrato = bd.contrato_por_matricula(principal)
                if not contrato:
                    resumo["erros"].append(
                        f"{alvo}: contrato principal {principal} nao encontrado "
                        f"apos a gravacao")
                    continue
                gravado = bd.gravar_dados_folha(ATOR, alvo, contrato,
                                                competencia,
                                                matricula=principal)
                if not gravado.get("ok"):
                    resumo["erros"].append(
                        f"{alvo}: {gravado.get('motivo')}")
                    continue
                resumo["movimentos"] += len(gravado.get("movimentos") or ())
                if gravado.get("pendencia"):
                    resumo["marcados"] += 1
                if not gravado.get("campos_alterados"):
                    resumo["inalterados"] += 1
                if contrato.get("remuneracao"):
                    ok_r, _msg_r = bd.gravar_salario_da_folha(
                        ATOR, alvo, contrato["remuneracao"], competencia,
                        matricula=principal)
                    if ok_r:
                        resumo["remuneracoes"] = \
                            resumo.get("remuneracoes", 0) + 1
                    else:
                        _log(f"  {alvo}: historico salarial nao gravado")
                # Foto mensal: UMA linha por pessoa por competência, sempre —
                # é o que permite responder "quanto recebeu em 05/2026?" e
                # "onde estava lotado?" sem juntar tabelas por proximidade.
                try:
                    ok_f, _msg_f = bd.registrar_foto_mensal(
                        ATOR, alvo, competencia,
                        {"matricula": principal,
                         "unidade": contrato.get("unidade") or "",
                         "lotacao": contrato.get("lotacao") or "",
                         "cargo": contrato.get("cargo") or "",
                         "vinculo": contrato.get("vinculo") or "",
                         "situacao": contrato.get("situacao") or "",
                         "remuneracao": contrato.get("remuneracao") or "",
                         "ficha_contracheque":
                             contrato.get("ficha_contracheque") or ""})
                    if ok_f:
                        resumo["fotos_mensais"] = \
                            resumo.get("fotos_mensais", 0) + 1
                    else:
                        _log(f"  {alvo}: foto mensal nao gravada ({_msg_f})")
                except Exception as e_foto:
                    _log(f"  {alvo}: foto mensal falhou ({e_foto})")
                _bloquear_apos_espelho(
                    bd, alvo, principal,
                    bool(bloqueios_por_matricula.get(principal)),
                    gravado, resumo)
            except Exception as e:
                resumo["erros"].append(f"{alvo}: espelho {e}")
    except Exception as e:
        _log(f"  _espelhar_principais: falha geral ({e})")


COLUNAS_CSV = ("matricula", "nome", "unidade", "lotacao", "cargo",
              "vinculo", "situacao", "remuneracao", "ficha_contracheque",
              "regime", "carga_horaria", "admissao", "exoneracao")

# ---- Configuração da fonte (28/09/2026) ----
# O sistema é publicado em git para qualquer prefeitura ou empresa usar.
# Nada de município, empresa, URL ou nome de órgão pode estar no código: o
# que a prefeitura é entra no ARQUIVO DE CONFIGURAÇÃO, e o padrão é
# "desligado", para quem não configurar nada receber um sistema funcionando
# e vazio, em vez de um sistema que tenta se conectar a um lugar estranho.
CONFIG_PADRAO = {
    "ativo": False,
    "origem": "csv",
    "caminho_csv": "mod_gest_cad_usuario/dados/funcionarios.csv",
    "delimitador": "auto",
    "competencia": "",
    "portal_url": "",
    "portal_pagina": "/servidores-por-nomes",
    "portal_intervalo_min_s": 1.0,
    "portal_intervalo_max_s": 5.0,
    "portal_user_agent": "skyrover/1.0 (carga de servidores - dados publicos)",
    "origem_rotulo": "",
    "portal_endpoints": {"folha": "", "competencia": ""},
    "colunas": {campo: [campo] for campo in COLUNAS_CSV},
}
ARQUIVO_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "fonte_folha.json")


def carregar_config(caminho=None):
    """Lê a configuração da fonte, com o padrão quando ela não existe.

    Devolve o dicionário pronto para uso. Um JSON quebrado NÃO derruba o
    script: cai no padrão (desligado) e diz o que houve. Um arquivo de
    configuração com vírgula faltando é motivo para o técnico corrigir, não
    para o sistema de skyrover parar.
    """
    arq = caminho or ARQUIVO_CONFIG
    cfg = dict(CONFIG_PADRAO)
    cfg["colunas"] = {k: list(v) for k, v in CONFIG_PADRAO["colunas"].items()}
    if not os.path.exists(arq):
        return cfg, f"sem arquivo de configuração em {arq}"
    try:
        with open(arq, encoding="utf-8") as f:
            bruto = json.load(f)
        for chave in ("ativo", "origem", "caminho_csv", "delimitador",
                      "competencia", "portal_url", "portal_pagina",
                      "portal_intervalo_s", "portal_user_agent",
                      "origem_rotulo", "portal_endpoints"):
            if chave in bruto:
                cfg[chave] = bruto[chave]
        if isinstance(bruto.get("colunas"), dict):
            for campo, apelidos in bruto["colunas"].items():
                if isinstance(apelidos, str):
                    apelidos = [apelidos]
                if apelidos:
                    cfg["colunas"][campo] = list(apelidos)
        return cfg, None
    except Exception as e:
        return cfg, f"configuração ilegível ({e}) — usando o padrão DESLIGADO"


def _detectar_delimitador(amostra, preferido="auto"):
    """`;`, `,` ou tabulação — whichever o arquivo usa.

    Pontua pela CONSISTÊNCIA entre linhas, e não pela contagem: um nome de
    servidor com vírgula ("Souza, Ana") pontua alto numa coluna só, e um
    arquivo inteiro com `,` pontua igual em todas. Quem decide é a segunda
    linha, que é onde o padrão se mostra.
    """
    if preferido and preferido != "auto":
        return preferido
    linhas = [l for l in amostra.splitlines() if l.strip()][:8]
    if not linhas:
        return ";"
    melhor, pontos = ";", -1
    for sep in (";", ",", "\t", "|"):
        contagens = {sep: l.count(sep) for l in linhas}
        if not max(contagens.values()):
            continue
        moda = max(set(contagens.values()), key=contagens.get)
        # precisa ser o mesmo número de separadores em todas as linhas
        if all(c == moda for c in contagens.values()) and moda > pontos:
            melhor, pontos = sep, moda
    return melhor


def _resolver_coluna(cabecalho, apelidos):
    """acha a coluna do arquivo entre os apelidos aceitos.

    A comparação tira acento, espaço e pontuação, porque "Carga Horária",
    "carga_horaria" e "CARGA-HORARIA" são a mesma coluna para quem está
    configuring e três campos lostos para quem não sabe disso.
    """
    def chave(txt):
        return re.sub(r"[^a-z0-9]", "", _sem_acento(txt or ""))

    mapa = {chave(h): h for h in cabecalho}
    for apelido in (apelidos or []):
        achado = mapa.get(chave(apelido))
        if achado:
            return achado
    return None


def _texto_csv(caminho):
    """Lê o CSV da folha como texto, tolerando a codificação que o órgão entregou.

    O portal da Transparência exporta em latin-1/cp1252, e a coleta pode ter
    gravado em UTF-8 ou UTF-8-BOM: os dois aparecem na mesma pasta `dados/`.
    Abrir sempre como UTF-8 e aposta cega. Um acento no nome de um servidor
    vira `UnicodeDecodeError` e a carga INTEIRA e pulada com "nada a
    sincronizar", sem carga nenhuma.

    A ordem e UTF-8-BOM, cp1252 e, por ultimo, latin-1, que nunca falha porque
    todo byte latin-1 e valido. A rede garante que a carga acontece; se o texto
    ficou legivel e quem le o resultado que decide, nao a excecao.

    Decodificar os BYTES e obrigatorio: `open(..., encoding=...)` NAO valida a
    codificacao na abertura. O `UnicodeDecodeError` so aparece na primeira
    leitura, longe do ponto que escolheu o `encoding` e sem nenhum erro para um
    `except` em volta do `open` conseguir segurar.
    """
    with open(caminho, "rb") as f:
        bruto = f.read()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return bruto.decode(enc)
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1")


def ler_folha_json(caminho):
    """Lê a folha no formato JSON do COLETOR (06/10/2026).

    O `coleta_folha.py` grava `funcionarios.json` em `dados/` — é esse arquivo
    que existe neste repositório. O `fonte_folha.json` apontava para
    `funcionarios.csv`, que NÃO existe, e por isso todo boot registrava
    "CSV nao encontrado" e a carga era pulada: os 1.159 servidores entravam
    pelo caminho do seed, não pela folha. Quem feltou o cadastro parado era o
    mesmo que ia ler "nada a sincronizar" no log e concluir que a folha estava
    vazia.

    O formato do JSON é o MESMO que o CSV levanta: `{"servidores": [...]}` com
    os campos de `COLUNAS_CSV`. Por isso `carregar_folha` entrega os dois pelo
    mesmo `sincronizar`, sem caminho de escrita novo.
    """
    import json
    with open(caminho, "rb") as f:
        bruto = f.read()
    dados = None
    for enc in ("utf-8-sig", "cp1252"):
        try:
            dados = json.loads(bruto.decode(enc))
            break
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    if dados is None:
        dados = json.loads(bruto.decode("latin-1"))
    if isinstance(dados, list):
        dados = {"servidores": dados}
    if not isinstance(dados, dict):
        return {"origem": f"JSON ({caminho})", "competencia": "",
                "coletado_em": "", "total": 0, "servidores": []}
    saida = {
        "origem": dados.get("origem_rotulo") or f"JSON ({caminho})",
        "competencia": dados.get("competencia") or "",
        "coletado_em": dados.get("coletado_em") or "",
        "aviso": dados.get("aviso") or "",
        "servidores": dados.get("servidores") or [],
    }
    saida["total"] = len(saida["servidores"])
    return saida


def ler_csv_configuravel(caminho, cfg):
    """Lê o CSV do município/empresa seguindo a configuração.

    Aceita o mesmo formato do JSON do coletor, para que as duas entradas
    (`--csv` e o arquivo padrão) levem ao mesmo sync.
    """
    import csv
    import io
    with io.StringIO(_texto_csv(caminho), newline="") as f:
        primeiro = f.readline()
        f.seek(0)
        sep = _detectar_delimitador(primeiro, cfg.get("delimitador", "auto"))
        leitor = csv.reader(f, delimiter=sep)
        cabecalho = next(leitor, [])
        if not cabecalho:
            return {"origem": f"CSV ({caminho})", "competencia": "",
                    "coletado_em": "", "total": 0, "servidores": []}
        # mapa: campo que a tela precisa -> coluna real do arquivo
        resolucao = {}
        for campo in COLUNAS_CSV:
            achado = _resolver_coluna(cabecalho, cfg["colunas"].get(campo))
            if achado:
                resolucao[campo] = achado
        faltando = [c for c in ("matricula", "nome") if c not in resolucao]
        if faltando:
            raise ValueError(
                f"o CSV não tem coluna de {', '.join(faltando)}. "
                f"Colunas encontradas: {', '.join(cabecalho)}. "
                f"Renomeie a coluna no arquivo, ou acrescente o nome dela em "
                f"'colunas' no arquivo fonte_folha.json.")
        servidores = []
        for linha in leitor:
            if not any((v or "").strip() for v in linha):
                continue
            reg = {}
            for campo, coluna in resolucao.items():
                try:
                    valor = (linha[cabecalho.index(coluna)] or "").strip()
                except (IndexError, ValueError):
                    valor = ""
                reg[campo] = valor or None
            servidores.append(reg)
        return {
            "origem": f"CSV ({os.path.basename(caminho)})",
            "url": "",
            "competencia": cfg.get("competencia") or "",
            "coletado_em": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "total": len(servidores),
            "aviso": f"delimitador '{sep}' | colunas: "
                     f"{', '.join(sorted(resolucao.values()))}",
            "servidores": servidores,
        }


def _tem_terminal() -> bool:
    """Da para perguntar algo a quem esta rodando?"""
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


# ===========================================================================
# CARGA AUTOMÁTICA (chamada pelo agendador, sem ninguém perguntando nada)
# ===========================================================================
# A carga automática tem uma regra a mais que a manual: ela só age sobre um
# arquivo NOVO. A manual pode ser rodada a qualquer hora por alguém que sabe o
# que está fazendo; a automática roda sozinha, todo dia, e o requisito dela é
# ser inofensiva para quem não a configurou e para quem configurou mas ainda
# não fechou o mês.
#
# Três travas, nesta ordem:
#   1. `ativo` precisa estar ligado no `fonte_folha.json`;
#   2. a folha precisa ter PELO MENOS um servidor — arquivo vazio ou truncado
#      é o jeito mais comum de a prefeitura errar o caminho, e zerar o
#      cadastro por causa disso seria o pior resultado possível;
#   3. o arquivo precisa ser DIFERENTE do da última carga — repetir o mesmo
#      arquivo todo dia não reconta nada, não gera alerta e não gasta tempo.
#
# Nenhuma das travas depende de o arquivo estar certo: mesmo com a folha
# trocada, a carga NUNCA sobrescreve o cadastro de quem já existe. Servidor que
# mudou de setor recebe pendência e confirma no primeiro acesso.

ESTADO_CARGA = os.path.join(DIR_DADOS, ".ultima_carga.json")
# Abaixo disto é suspiciously pouco para uma folha de servidores; o piso evita
# que um CSV exportado pela metade vire "cadastro de 3 pessoas".
MINIMO_SERVIDORES = 1


def _importar_coletor():
    """Carrega o `coleta_folha` esteja ele como script ou como pacote.

    O mesmo arquivo é executável de dois jeitos (`python coleta_folha.py`) e
    importável (`from mod_gest_cad_usuario import coleta_folha`), e o nome do
    módulo é diferente nos dois casos. Testar os dois, em vez de escolher um,
    é o que evita a falha que só apareceria no agendador — que importa por
    pacote — e nunca na mão do técnico — que roda por script.
    """
    try:
        from mod_gest_cad_usuario import coleta_folha as modulo
        return modulo
    except Exception:
        pass
    try:
        if DIR_DADOS not in sys.path:
            sys.path.insert(0, DIR_DADOS)
        import coleta_folha as modulo
        return modulo
    except Exception:
        return None


def _digitalizar(caminho: str) -> str:
    """Impressão digital do arquivo: muda se o conteúdo mudar."""
    import hashlib
    try:
        h = hashlib.sha256()
        with open(caminho, "rb") as f:
            for bloco in iter(lambda: f.read(65536), b""):
                h.update(bloco)
        return h.hexdigest()[:16]
    except Exception:
        return ""


def ler_ultima_carga():
    """O que foi carregado por último (para o log e para a Home)."""
    try:
        with open(ESTADO_CARGA, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _registrar_carga(estado: dict) -> bool:
    try:
        os.makedirs(DIR_DADOS, exist_ok=True)
        with open(ESTADO_CARGA, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        _log(f"  nao deu para registrar o estado da carga: {e}")
        return False


def carregar_folha(cfg):
    """Folha a ser sincronizada, conforme a origem configurada.

    `csv`  -> lê o arquivo local (é o padrão, e não depende de terceiro).
    `portal` -> recolhe do portal e devolve a folha freshly coletada; se o
               portal não estiver configurado, avisa e devolve None em vez de
               cair no CSV por baixo dos panos — porque quem pediu `portal` e
               receber o arquivo de três meses atrás sem saber é pior que
               não receber nada.
    """
    origem = (cfg.get("origem") or "csv").strip().lower()
    if origem == "portal":
        coletor = _importar_coletor()
        if coletor is None:
            _log("  'origem' pede portal, mas o coletor nao carregou. Nada foi "
                 "coletado.")
            return None
        if not getattr(coletor, "RAIZ", "") or not getattr(coletor, "GRID", ""):
            _log("  'origem' pede portal, mas 'portal_url'/'portal_endpoints' "
                 "estao vazios. Nada foi coletado.")
            return None
        coleta_folha = coletor
        try:
            os.makedirs(DIR_DADOS, exist_ok=True)
            return coleta_folha.coletar()
        except Exception as e:
            _log(f"  coleta do portal falhou: {e}")
            return None
    # csv (padrao)
    caminho = cfg.get("caminho_csv") or ""
    if caminho and not os.path.isabs(caminho):
        caminho = os.path.join(RAIZ_REPO, caminho)
    # 06/10/2026: aceita `.json` e `.csv`. O `coleta_folha.py` grava JSON, e
    # foi o `.json` que ficou em `dados/` — o `fonte_folha.json` apontava para
    # um `.csv` que não existe, e a carga era pulada em todo boot com "CSV nao
    # encontrado". A decisão é pelo SUFIXO, não pelo `origem`: quem aponta o
    # caminho decide o formato, e nenhuma configuração nova é preciso para o
    # arquivo que o coletor produz ser lido.
    if caminho.lower().endswith(".json"):
        if not os.path.exists(caminho):
            _log(f"  JSON nao encontrado: {caminho}")
            return None
        try:
            return ler_folha_json(caminho)
        except Exception as e:
            _log(f"  falha ao ler o JSON da folha ({e})")
            return None
    if not caminho or not os.path.exists(caminho):
        _log(f"  CSV nao encontrado: {caminho or '(nao configurado)'}")
        return None
    return ler_csv_configuravel(caminho, cfg)


def servidores_no_cadastro() -> int:
    """Quantos servidores da folha já estão no cadastro de usuários.

    A contagem é sobre quem tem **vínculo gravado**, que é o que a folha
    preenche (`sincronizar`, `carga_folha.py:242`) e o que o seed **não**
    preenche. Isso evita a lista de nomes de fábrica — que mudaria a cada
    renomeação de conta, e cuja lista explícita seria uma constante para
    manter. Um cadastro recém-criado tem os servidores de fábrica sem
    vínculo, então a conta começa em zero, que é exatamente o estado de
    "ainda não carregou".

    EN: How many sheet servers are already in the user register.
    """
    try:
        from mod_gest_cad_usuario import bd_manipulador as bd
        conn = bd.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_usuarios "
                        "WHERE vinculo IS NOT NULL AND TRIM(vinculo) <> ''")
            return int(cur.fetchone()[0] or 0)
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        try:
            _log(f"  nao deu para contar os servidores no cadastro ({e})")
        except Exception:
            pass
        return 0


def primeira_carga_pendente() -> bool:
    """A carga da folha ainda nunca rodou neste banco? (30/09/2026)

    É o que separa o **primeiro boot** dos outros. A coleta do portal leva
    ~100 s e quase 50 requisições; pagar isso a cada reinício tornaria o
    servidor impraticável de subir. E o custo é real: com a folha já no
    cadastro, o agendador das 03:00 (com as três travas) é quem atualiza —
    que é o desenho que o `AGENTS.md` e o `docs/carga_de_servidores.md`
    já descrevem.

    **Por que o estado é o cadastro, e não um arquivo de marcador:** o banco é
    o que o administrador reinstala, apaga e recria. Um marcador em arquivo
    sobreviveria a `DELETE FROM tb_usuarios` e deixaria a installation com o
    banco vazio e a carga pulada — que é justamente o estado ruim que este
    passo existe para evitar.

    EN: True when the sheet has never been loaded into this database.
    """
    try:
        return servidores_no_cadastro() == 0
    except Exception:
        # Falhou a contagem: carrega. Uma folha a mais é desperdício de tempo;
        # um cadastro de servidores vazio é o sistema quebrado.
        return True


def carga_automatica(forcar: bool = False, config: str | None = None) -> dict:
    """Uma passada da carga, sozinha, sem prompt. Chamada pelo agendador.

    `config` existe para os testes (e para o técnico conferir uma configuração
    alternativa sem tocar na do sistema). O agendador não passa nada e usa a
    de `fonte_folha.json`.

    Devolve um dicionário de relatório (nunca levanta exceção) — quem chama é
    um job de fundo, e um job de fundo que levanta exceção some do log do
    APScheduler sem ninguém ver.
    """
    relatorio = {"rodou": False, "motivo": "", "criados": 0, "marcados": 0,
                 "bloqueados": 0, "erros": []}
    try:
        cfg, aviso_cfg = carregar_config(config)
        if aviso_cfg:
            relatorio["motivo"] = aviso_cfg
            return relatorio
        if not cfg.get("ativo") and not forcar:
            relatorio["motivo"] = "fonte desativada (fonte_folha.json: ativo=false)"
            return relatorio

        folha = carregar_folha(cfg)
        if not folha or not (folha.get("servidores") or []):
            relatorio["motivo"] = ("folha vazia ou indisponivel — nada foi "
                                   "gravado (o cadastro existente esta intacto)")
            return relatorio
        if len(folha["servidores"]) < MINIMO_SERVIDORES:
            relatorio["motivo"] = (f"folha com {len(folha['servidores'])} "
                                   "servidor(es) — abaixo do minimo, descartada")
            return relatorio

        # ---- trava 3: a COMPETÊNCIA (03/10/2026) ----
        # A trava que existia era "o arquivo é o mesmo da última carga?",
        # comparando a impressão digital. Isso respondia "o arquivo mudou"
        # e não respondia a pergunta que o mês pede: "esta folha já foi
        # processada?". Duas consequências reais:
        #
        #   * uma folha NOVA com a MESMA competência (o RH reexporta o
        #     mesmo mês corrigindo um cargo) era reprocessada — certo —
        #     mas só por acaso, porque a impressão mudava;
        #   * uma competência nova com o MESMO arquivo — o caso de quem
        #     rodou a conferência do mês que vem sem trocar o arquivo —
        #     era SKIPPADA, e a conferência não acontecia.
        #
        # A regra agora: pula quando a competência é a mesma E o arquivo
        # é o mesmo. Mesma competência com arquivo diferente (correção do
        # RH) reprocessa; competência nova reprocessa sempre. E
        # `SKYROVER_FOLHA_MES` manda na competência e vence a trava —
        # quem pediu competência explícita pediu para processar.
        competencia, aviso_comp = competencia_da_folha(folha, cfg)
        relatorio["competencia"] = competencia
        if aviso_comp:
            relatorio["aviso_competencia"] = aviso_comp
        competencia_forcada = bool(
            normalizar_competencia(os.environ.get(VAR_AMB_COMPETENCIA)))

        origem_arquivo = (cfg.get("caminho_csv") if (cfg.get("origem") or "") == "csv"
                          else ARQUIVO_PADRAO)
        if origem_arquivo and not os.path.isabs(origem_arquivo):
            origem_arquivo = os.path.join(RAIZ_REPO, origem_arquivo)
        digital = _digitalizar(origem_arquivo) if origem_arquivo else ""
        if not digital:
            # origem portal: usa a própria folha, que acabou de ser coletada
            digital = _digitalizar(ARQUIVO_PADRAO) or str(len(folha["servidores"]))
        anterior = ler_ultima_carga()
        comp_anterior = normalizar_competencia(anterior.get("competencia"))
        if not forcar and not competencia_forcada \
                and digital and anterior.get("digital") == digital:
            # Arquivo igual. Quem decide agora é a COMPETÊNCIA:
            #   mesma competência -> já rodou, não há o que fazer;
            #   competência nova  -> é a conferência do mês que vem, que a
            #     trava antiga (só por digital) descartava por engano.
            # Cadastro VAZIO ignora a trava (29/10/2026): o banco foi
            # recriado/apagado mas o `.ultima_carga.json` (fora do git e
            # fora do banco) ficou — sem isto a trava diria "já carregou"
            # e o cadastro nunca nasceria. Cadastro vazio sempre carrega.
            if primeira_carga_pendente():
                relatorio["motivo"] = ("cadastro vazio — primeira carga "
                                       "(trava de arquivo ignorada)")
            elif comp_anterior and comp_anterior == competencia:
                relatorio["motivo"] = (
                    f"folha inalterada e competencia {competencia} ja "
                    f"carregada em {anterior.get('em', '?')[:16]} — nada a fazer")
                return relatorio
            elif not comp_anterior:
                # Instalação antiga, sem competência registrada: sem
                # competência não há como decidir, e o arquivo igual é a
                # única evidência de que a carga já rodou.
                relatorio["motivo"] = (
                    f"folha inalterada desde a carga de "
                    f"{anterior.get('em', '?')[:16]} — nada a fazer")
                return relatorio
            else:
                relatorio["motivo"] = (
                    f"mesmo arquivo, competencia nova ({competencia}) — "
                    f"conferencia de mes futuro")

        relatorio["rodou"] = True
        uni = sincronizar_unidades(folha, aplicar=True)
        resumo = sincronizar(folha, aplicar=True)
        relatorio.update({
            "criados": resumo.get("criados", 0),
            "marcados": resumo.get("marcados", 0),
            "bloqueados": resumo.get("bloqueados", 0),
            "desbloqueados": resumo.get("desbloqueados", 0),
            # Os DOIS contadores que a regra de 06/10/2026 produziu, e que o
            # DTI precisa ler no log do boot: quantas contas foram mesmo
            # fechadas nesta carga e quantas foram poupadas por já terem
            # passado por lá. Sem o segundo, o relatório diria "0 bloqueados"
            # numa carga em que o servidor já estava liberado, e o técnico
            # não distinguiria "não precisou" de "não aconteceu".
            "bloqueados_aplicados": resumo.get("bloqueados_aplicados", 0),
            "desbloqueados_aplicados": resumo.get("desbloqueados_aplicados", 0),
            "secretarias_criadas": uni.get("secretarias_criadas", 0),
            "setores_criados": uni.get("setores_criados", 0),
            # A competência RESOLVIDA, não a que o arquivo trazia: com
            # `SKYROVER_FOLHA_MES` as duas diferem, e é a resolvida que
            # foi gravada. Registrar a do arquivo deixaria o estado de
            # carga mentindo sobre o que está no banco.
            "competencia": resumo.get("competencia") or competencia,
            "total": len(folha["servidores"]),
            "erros": resumo.get("erros", [])[:20],
        })
        # O que MUDOU, e não só o que sobrou (01/10/2026). Sem estes o
        # relatório respondia "criados 0, bloqueados 0" numa folha em que 40
        # salários tinham mudado e 600 continuavam iguais — e quem lê o log do
        # boot não distinguiria "a folha não mudou" de "a carga não rodou".
        relatorio.update({
            "nomes_corrigidos": resumo.get("nomes_corrigidos", 0),
            "remuneracoes": resumo.get("remuneracoes", 0),
            "fotos_mensais": resumo.get("fotos_mensais", 0),
            "inalterados": resumo.get("inalterados", 0),
            "contratos_novos": resumo.get("contratos_novos", 0),
            "para_revisar": resumo.get("para_revisar", 0),
            "movimentos": resumo.get("movimentos", 0),
        })
        _registrar_carga({
            "digital": digital,
            "em": datetime.now().isoformat(timespec="seconds"),
            "origem": folha.get("origem", ""),
            "competencia": relatorio["competencia"],
            "competencia_forcada": competencia_forcada,
            "total": len(folha["servidores"]),
            "criados": relatorio["criados"],
            "marcados": relatorio["marcados"],
        })
        # Proveniência no BANCO (e não só no `.ultima_carga.json` em disco):
        # qual competência entrou, de onde veio, quando foi coletada e quantos
        # trouxe/criou/atualizou. "Atualizados" é aproximação documentada
        # (total menos criados menos inalterados, sem nunca negativar), e a
        # falha aqui nunca derruba a carga — é metadado, não dado.
        try:
            from mod_gest_cad_usuario import bd_manipulador as _bd_carga
            _tot = int(len(folha["servidores"]))
            _atu = max(0, _tot - int(relatorio.get("criados", 0))
                       - int(resumo.get("inalterados", 0)))
            _bd_carga.registrar_carga_folha(
                ATOR, relatorio["competencia"], folha.get("origem", ""),
                folha.get("url", ""), folha.get("coletado_em", ""), _tot,
                relatorio.get("criados", 0), _atu)
        except Exception as e_carga:
            _log(f"  registro da carga no banco falhou ({e_carga})")
        return relatorio
    except Exception as e:
        relatorio["erros"].append(f"{type(e).__name__}: {e}")
        relatorio["motivo"] = f"falhou: {e}"
        try:
            import traceback
            relatorio["erros"].append(traceback.format_exc(limit=3))
        except Exception:
            pass
        return relatorio


def folha_arquivo_atual() -> dict:
    """A folha de servidores como está no ARQUIVO, sem gravar nada (01/10/2026).

    Lê o mesmo arquivo que a carga lê — o `dados/funcionarios.json` quando ele
    existe, e o CSV configurado em `fonte_folha.json` quando não — e devolve
    o dicionário cru: `origem`, `url`, `competencia`, `coletado_em`, `total`,
    `aviso` e a lista `servidores`.

    **Por que existe, e por que aqui:** quem publica dado público sobre a folha
    é o módulo de Dados Abertos, e ele NÃO pode ler um arquivo que mora na
    pasta deste módulo (AGENTS.md §2: módulo de negócio não alcança outro). A
    costura oficial é `mod_skyrover/integracoes.folha_de_servidores_publica()`,
    que chama ESTA função. O conhecimento do arquivo — nome, caminho, formato,
    delimitador, colunas — fica aqui, com quem escreveu o arquivo; lá fora só
    circula o dicionário.

    **O que ela NÃO faz:** não grava, não audita, não bloqueia, não calcula
    média. É a leitura mais burra possível, porque é a que a tela de dados
    abertos precisa: mostrar o que a fonte publica, e não o que o cadastro
    Virou depois. `{}` em qualquer falha (fail-soft) — quem chama decide o
    que mostrar quando não há folha.

    EN: The server sheet as it sits in the FILE, writing nothing.
    """
    try:
        if os.path.exists(ARQUIVO_PADRAO):
            with open(ARQUIVO_PADRAO, encoding="utf-8") as f:
                folha = json.load(f)
            if isinstance(folha, dict):
                return folha
        # Sem o JSON: cai no CSV configurado — a mesma folha, em outro formato.
        cfg, _aviso = carregar_config()
        if not cfg.get("caminho_csv"):
            return {}
        caminho = cfg["caminho_csv"]
        if not os.path.isabs(caminho):
            caminho = os.path.join(RAIZ_REPO, caminho)
        if not os.path.exists(caminho):
            return {}
        return ler_csv_configuravel(caminho, cfg) or {}
    except Exception as e:
        _log(f"  nao deu para ler a folha do arquivo ({e})")
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Grava a folha de servidores no cadastro de usuarios.")
    ap.add_argument("--arquivo", default=ARQUIVO_PADRAO,
                    help="folha em JSON (padrao: funcionarios.json)")
    ap.add_argument("--csv", dest="arquivo_csv",
                    help="folha em CSV, em vez do JSON")
    ap.add_argument("--aplicar", action="store_true",
                    help="grava sem perguntar (para cron). Sem esta flag, "
                         "pergunta - e sem terminal, nao grava.")
    ap.add_argument("--so-ensaio", action="store_true",
                    help="mostra o que faria e nao grava, mesmo com --aplicar.")
    ap.add_argument("--config", default=ARQUIVO_CONFIG,
                    help="arquivo de configuracao da fonte (fonte_folha.json).")
    ap.add_argument("--forcar", action="store_true",
                    help="ignora 'ativo: false' da configuracao.")
    args = ap.parse_args()

    cfg, aviso_cfg = carregar_config(args.config)
    if aviso_cfg:
        print(f"  (configuracao: {aviso_cfg})")
    if not cfg.get("ativo") and not args.forcar:
        # NADA CONFIGURADO, NADA ACONTECE. E sai com 0, e nao com erro: um
        # sistema novo de uma prefeitura sem folha de funcionarios pronta
        # esta perfectly normal, e um codigo de saida diferente de zero faria
        # o cron acusar falha onde nada falhou.
        print("\n  Carga de funcionarios DESLIGADA "
              "(fonte_folha.json com \"ativo\": true).")
        print("  Nada foi lido e nada foi gravado — este e o estado normal de "
              "um sistema")
        print("  recem-instalado. Para ligar: edite "
              "mod_gest_cad_usuario/fonte_folha.json, aponte o CSV e rode de novo.")
        print("  Para forcar agora, use --forcar.\n")
        return 0

    # ---- carrega a folha ----
    origem = args.arquivo_csv or args.arquivo
    try:
        if args.arquivo_csv:
            folha = ler_csv_configuravel(args.arquivo_csv, cfg)
        else:
            with open(args.arquivo, encoding="utf-8") as f:
                folha = json.load(f)
            # a competencia do JSON tem prioridade sobre a da configuracao:
            # o JSON foi coletado de uma folha especifica
            if not folha.get("competencia") or folha.get("competencia") == "(do CSV)":
                folha["competencia"] = cfg.get("competencia") or ""
    except FileNotFoundError:
        print(f"\n  Folha nao encontrada: {origem}\n"
              f"  Apontar o CSV:  edite 'caminho_csv' em {args.config}\n"
              f"  Ou coletar:     python mod_gest_cad_usuario/coleta_folha.py --atualizar\n",
              file=sys.stderr)
        return 1

    servidores = folha.get("servidores") or []
    print(f"\n  Folha   : {origem}")
    print(f"  Origem  : {folha.get('origem')}")
    print(f"  Competencia: {folha.get('competencia')}  ({len(servidores)} servidores)")

    # ---- o que vai acontecer, ANTES de qualquer escrita ----
    modelo = _arvore_real(folha)
    bloq = sum(1 for r in servidores if _bloqueado(r)[0])
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd_ensaio
        # `listar_usuarios()` devolve tuplas por índice e o índice 0 é o ID,
        # não o login — ler o login de lá dava sempre "não cadastrado" e o
        # ensaio prometia 1165 servidores novos sobre uma base já cheia.
        _c = _bd_ensaio.get_connection()
        try:
            existentes = {r[0] for r in _c.execute(
                "SELECT user_nome FROM tb_usuarios").fetchall()}
        finally:
            _c.close()
    except Exception:
        existentes = set()
    novos = sum(1 for r in servidores if _matricula(r) not in existentes)
    conhecidos = len(servidores) - novos

    print(f"\n  {novos} servidor(es) NOVOS seriam criados")
    print(f"  {conhecidos} ja cadastrados seriam conferidos")
    print(f"  {bloq} BLOQUEADOS (pensionista/inativo/eleito/demitido)")
    print(f"  Senha provisoria {SENHA_PROVISORIA} para os novos, com troca "
          f"+ telefone obrigatorios no 1o acesso")
    print(f"\n  Organograma: {len(modelo['secretarias'])} secretarias e "
          f"{sum(len(v) for v in modelo['secretarias'].values())} "
          f"departamentos; as unidades de demonstracao que o portal nao "
          f"conhece seriam DESATIVADAS")
    print("\n  Nos servidores ja cadastrados, o script NAO sobrescreve o setor:")
    print("  quem ja tem cadastro e mudou de secretaria/departamento/cargo")
    print("  recebe um ALERTA e confirma sozinho no primeiro acesso.")

    # ---- a pergunta ----
    aplicar = args.aplicar
    if not args.so_ensaio and not aplicar:
        if not _tem_terminal():
            print("\n  Sem terminal para perguntar (cron, pipe, servico). "
                  "Nada foi gravado.")
            print("  Use --aplicar para gravar sem perguntar, ou rode num "
                  "terminal.\n")
            return 0
        print("\n  Aplicar no banco de dados?")
        try:
            resp = input("     [s/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            resp = ""
        aplicar = resp in ("s", "sim", "y", "yes")
        if not aplicar:
            print("\n  Nada foi gravado.\n")
            return 0
    if args.so_ensaio:
        aplicar = False

    if not aplicar:
        print("\n  ENSAIO: nada sera gravado.\n")
        return 0

    print("\n  --- Organograma ---")
    uni = sincronizar_unidades(folha, aplicar=True)
    print(f"  secretarias criadas : {uni['secretarias_criadas']}")
    print(f"  setores criados      : {uni['setores_criados']}")
    print(f"  reativadas           : {uni['reativadas']}")
    print(f"  desativadas (demo)   : {uni['desativadas']}")

    print("\n  --- Usuarios ---")
    resumo = sincronizar(folha, aplicar=True)
    print(f"\n  criados        : {resumo['criados']}")
    print(f"  nomes corrigidos: {resumo['nomes_corrigidos']}")
    print(f"  marcados p/ confirmar: {resumo['marcados']}")
    print(f"  inalterados    : {resumo['inalterados']}")
    print(f"  fotos mensais   : {resumo.get('fotos_mensais', 0)}")
    print(f"  bloqueados     : {resumo['bloqueados']}")
    if resumo["desbloqueados"]:
        print(f"  desbloqueados  : {resumo['desbloqueados']} "
              f"(voltaram a aparecer como ativos no portal)")
    if resumo["marcados"]:
        print("\n  Os servidores marcados veem o alerta no proximo acesso.")
        print("  O DTI acompanha a pendencia na Home.")
    if resumo["erros"]:
        print(f"\n  {len(resumo['erros'])} erro(s) - primeiros 10:")
        for e in resumo["erros"][:10]:
            print(f"    {e}")
    # Proveniência no banco (mesma da carga automática): sem este registro a
    # foto mensal ficaria sem dizer de qual carga veio.
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd_cli
        _tot = int(len(servidores))
        _atu = max(0, _tot - int(resumo.get("criados", 0))
                   - int(resumo.get("inalterados", 0)))
        _bd_cli.registrar_carga_folha(
            "carga_folha", folha.get("competencia", ""),
            folha.get("origem", ""), folha.get("url", ""),
            folha.get("coletado_em", ""), _tot,
            resumo.get("criados", 0), _atu)
    except Exception as e_carga:
        print(f"  (registro da carga no banco falhou: {e_carga})")
    print()
    return 0



if __name__ == "__main__":
    sys.exit(main())
