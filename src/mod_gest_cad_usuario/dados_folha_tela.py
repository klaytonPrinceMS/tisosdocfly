"""Read-only display of the payroll sheet fields inside the user record.

EN — Renders the fields published by the Transparency Portal
(`dados/funcionarios.json`) as **plain text inside the user record**, on the
three screens where the record is read: the admin "Editar" dialog, the popup
that opens when the pointer rests on a name in the users list, and the
server's own "Meu Perfil" dialog. Nothing here is editable — by anyone.

PT-BR — Mostra os campos publicados pelo Portal da Transparência
(`dados/funcionarios.json`) como **texto puro dentro do cadastro**, nas três
telas onde o cadastro é lido: o diálogo "Editar" do administrador, o popup que
abre ao passar o mouse no nome da lista de usuários e o "Meu Perfil" do
próprio servidor. Nada aqui é editável — por ninguém.

POR QUE UM ARQUIVO SÓ (04/10/2026): a regra é "secretaria, unidade e salário
ficam apenas como texto, sem edição nem pelo usuário nem pelo administrador,
porque esses dados devem vir do arquivo". Regra que vive em três telas
separadas vira três implementações que divergem na primeira correção — e a
divergência aqui seria silenciosa, porque as três continuam funcionando. Um
renderizador só, chamado pelas três, é o que faz "somente leitura" ser uma
propriedade do código e não uma promessa de quem escreve a tela.

O QUE É VERBATIM E O QUE NÃO É:

- **Matrícula** e os **12 campos** de `CAMPOS_FONTE_FOLHA` vão como o portal
  os publicou, sem passar por nada.
- **Nome** NÃO entra aqui, e a distinção é deliberada. O portal publica o
  nome do servidor, mas a coluna `user_nome_completo` do cadastro é o NOME DE
  TRATAMENTO, que pode ser nome social (Decreto 8.727/2016) e pode ter sido
  corrigido por quem administra. Mostrar `user_nome_completo` como se fosse
  "o nome do portal" seria afirmar o que não é — e impedir a edição do nome
  social traria de volta a cunha que o decreto abre. O nome de tratamento
  continua editável no lugar onde já estava.

UMA PESSOA, VÁRIOS CONTRATOS: a folha é uma lista de matrículas, e uma
pessoa pode ter mais de uma (foi ativo e demitido em contratos diferentes, ou
tem dois contratos no mesmo período). Medido em 09/2026: 1.159 matrículas,
1.154 nomes, 5 pessoas com 2 contratos. Quando há mais de um, este módulo
mostra **todos**, um por cartão, com o principal marcado. Mostrar só um é o que
faz o cadastro dizer "Demitido" de quem está com outro contrato ativo — que foi
exatamente o caso de Isadora Ercia Marquesani de Oliveira e Julio Cesar Ramos
Terra, as duas medidas aqui.
"""

import sys, os
import calendar
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from nicegui import ui

from mod_gest_cad_usuario import bd_manipulador as gest
from mod_skyrover import observabilidade

log = observabilidade.get_logger("gest_cad_usuario")

# Os 12 campos que o Portal publica, na ordem em que fazem sentido na ficha —
# secretaria/unidade, depois lotação/departamento, depois o vínculo, e a
# admitting/date por último. O rótulo é a PALAVRA DO DOMÍNIO
# ("Secretaria", não "unidade"): é assim que quem usa o sistema chama.
CAMPOS_FOLHA_CADASTRO = (
    ("unidade", "Secretaria"),
    ("lotacao", "Lotação"),
    ("cargo", "Cargo"),
    ("vinculo", "Vínculo"),
    ("situacao", "Situação"),
    ("tipo", "Tipo"),
    ("admissao", "Admissão"),
    ("exoneracao", "Exoneração"),
    ("regime", "Regime"),
    ("carga_horaria", "Carga horária"),
    ("remuneracao", "Remuneração"),
    ("ficha_contracheque", "Ficha de contracheque"),
)

# Campos que o portal NÃO publica (medido em 09/2026, 1.159 registros, zero
# preenchidos em cada um). Eles aparecem vazios na ficha, com uma nota, em vez
# de sumirem: um campo ausente parece erro de tela, e um campo vazio com nota
# é o que é — informação que o portal ainda não publica.
CAMPOS_SEM_PUBLICO = ("exoneracao", "regime", "carga_horaria", "tipo")

# Situação que significa que a pessoa ESTÁ na prefeitura, mesmo sem estar
# trabalhando na competência. Um "Demitido" ao lado de um "Ativo" não é
# contradição: são contratos diferentes, e quem lê precisa ver os dois.
_SITUACOES_VINCULADAS = ("ativo", "ferias", "licença", "licenca")


def _situacao_contratada(situacao):
    """Este contrato diz que a pessoa está na prefeitura na competência?"""
    return any(p in str(situacao or "").lower() for p in _SITUACOES_VINCULADAS)


def _valor(valor):
    """O texto do campo, ou um traço quando o portal não mandou nada."""
    texto = str(valor or "").strip()
    return texto if texto else "—"


# ============ TEMPO DE CASA E ANIVERSÁRIO ============
def _data_para_date(valor):
    """'14/08/2023' ou '2023-08-14' → `date`; anything else → None."""
    try:
        texto = str(valor or "").strip()
        if not texto:
            return None
        for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
            try:
                return datetime.strptime(texto[:10], formato).date()
            except ValueError:
                continue
        return None
    except Exception:
        return None


def _tempo_de_casa(admissao):
    """'3 anos, 2 meses e 11 dias' de vínculo, a partir da admissão.

    O cálculo é de CALENDÁRIO, não de divisão de dias: 1 ano de vínculo tem
    12 meses de trabalho, mesmo que o ano bissexto tenha 366 dias. Dividir os
    dias por 365 dava 3 anos para quem tem 3 anos e 2 meses — que é
    exatamente o tipo de número que a pessoa percebe estar errado.
    """
    try:
        inicio = _data_para_date(admissao)
        if not inicio:
            return None
        hoje = date.today()
        if hoje < inicio:
            return None
        anos = hoje.year - inicio.year
        meses = hoje.month - inicio.month
        dias = hoje.day - inicio.day
        if dias < 0:
            meses -= 1
            # Empresta o dia do mês anterior: o jeito certo é o último dia do
            # mês que vem antes, porque ele muda de tamanho.
            mes_anterior = hoje.month - 1 or 12
            ano_anterior = hoje.year if hoje.month > 1 else hoje.year - 1
            ultimo = calendar.monthrange(ano_anterior, mes_anterior)[1]
            dias += ultimo
        if meses < 0:
            anos -= 1
            meses += 12
        partes = []
        if anos:
            partes.append(f"{anos} ano{'s' if anos > 1 else ''}")
        if meses:
            partes.append(f"{meses} mes{'es' if meses > 1 else ''}")
        partes.append(f"{dias} dia{'s' if dias != 1 else ''}")
        return ", ".join(partes)
    except Exception:
        return None


def _proximo_aniversario(admissao):
    """Quantos dias faltam para o aniversário de vínculo, e a data.

    O caso de 29 de fevereiro é o que faz esta função existir separada: o
    `replace(year=...)` LANÇA quando o ano destino não é bissexto, e a versão
    anterior tratava isso referenciando a própria variável que nunca chegou a
    ser atribuída — o resultado era `None` sem explicação. Aqui o ano é
    decidido primeiro e a data é montada com o dia limitado pelo mês.
    """
    try:
        inicio = _data_para_date(admissao)
        if not inicio:
            return None, None
        hoje = date.today()
        ja_passou = (hoje.month, hoje.day) > (inicio.month, inicio.day)
        ano_destino = hoje.year + (1 if ja_passou else 0)
        # O dia 29 só existe em fevereiro bissexto: nos outros anos o
        # aniversário cai no dia 28, que é a convenção do calendário
        # administrativo.
        dia = inicio.day
        if dia > calendar.monthrange(ano_destino, inicio.month)[1]:
            dia = calendar.monthrange(ano_destino, inicio.month)[1]
        aniversario = date(ano_destino, inicio.month, dia)
        return (aniversario - hoje).days, aniversario
    except Exception:
        return None, None


def _par_de_campos(campo, rotulo, valor):
    """Uma célula rótulo+valor, para a grade de 2 pares (4 colunas)."""
    with ui.column().classes("gap-0 min-w-0"):
        ui.label(rotulo).classes("text-caption text-grey-6 leading-none")
        ui.label(_valor(valor)).classes("text-body2 font-medium break-words")


def bloco_tempo_de_casa(admissao, vinculo=""):
    """Tempo de vínculo e aniversário — o que a pessoa pergunta primeiro.

    Fica logo abaixo da admissão, e não escondido no fim da ficha: o motivo
    é que "quanto tempo eu estou aqui" e "quando completo mais um ano" são as
    duas perguntas que o servidor faz ao olhar o próprio cadastro, e as duas
    estavam sem resposta na tela.

    Devolve `True` se havia admissão para calcular.
    """
    try:
        tempo = _tempo_de_casa(admissao)
        if not tempo:
            return False
        faltam, data = _proximo_aniversario(admissao)
        with ui.row().classes("w-full items-center gap-2 flex-wrap mt-1"):
            ui.badge(f"{tempo} de vínculo", color="teal-2").props(
                "text-color=teal-10 outline dense")
            if faltam is not None:
                if faltam == 0:
                    texto, cor = ("Feliz aniversário de vínculo!", "amber-2")
                elif faltam == 1:
                    texto, cor = ("Amanhã completa mais um ano de vínculo.",
                                  "teal-2")
                elif faltam <= 30:
                    texto = f"Faltam {faltam} dias para completar mais um ano."
                    cor = "amber-2"
                else:
                    texto = (f"Próximo aniversário de vínculo: "
                             f"{data.strftime('%d/%m/%Y')}.")
                    cor = "teal-2"
                ui.badge(texto, color=cor).props(
                    "text-color=black-9 outline dense")
        return True
    except Exception:
        return False


def _etiqueta(campo, rotulo, valor, compacto):
    """Uma linha rótulo/valor. Rótulo em cima quando é para caber no popup."""
    if compacto:
        with ui.column().classes("min-w-0"):
            ui.label(rotulo).classes("text-caption text-grey-6 leading-none")
            ui.label(_valor(valor)).classes("text-caption font-medium break-words")
    else:
        with ui.row().classes("w-full items-start no-wrap").style("gap: 0.75rem"):
            ui.label(rotulo).classes("text-caption text-grey-6 shrink-0 no-wrap") \
                .style("min-width: 11rem")
            ui.label(_valor(valor)).classes("text-body2 grow min-w-0 break-words")


def _cabecalho_folha(titulo, subtitulo=None):
    """O título do bloco e a frase que diz por que nada aqui se edita.

    A frase não é enfeite: sem ela, um campo cinza e sem cursor parece campo
    quebrado, e a primeira reaction de quem vê é "isso não está carregando".
    """
    with ui.column().classes("w-full gap-0 mb-2"):
        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
            ui.icon("description", size="18px").classes("text-grey-6")
            ui.label(titulo).classes("text-subtitle2 text-grey-8")
        ui.label(subtitulo or
                 "Dados publicados pelo Portal da Transparência. Não são "
                 "editáveis aqui: vêm da folha e são atualizados na próxima "
                 "carga.").classes("text-caption text-grey-6")


def bloco_detalhe_financeiro(user_nome, *, limite_competencias=1):
    """Os valores capturados da ficha: proventos, descontos, líquido, verbas.

    **ESTE BLOCO É A RAZÃO DE `tb_detalhe_ficha` EXISTIR.** O contrato tem
    salário, mas o salário não é o contracheque: proventos, descontos, o líquido
    e a lista de verbas (auxílio alimentação, INSS, vencimento) só existem na
    ficha. Até aqui esses valores eram capturados, gravados no banco e
    **não apareciam em lugar nenhum** — a pessoa via "Analista de Sistemas,
    Efetivo, R$ 3.738,17" e não via o que de fato recebeu.

    Mostra a competência mais recente por padrão. Devolve `False` quando não há
    nada capturado, para o chamador decidir se mostra um aviso — que é
    diferente de mostrar zeros.
    """
    try:
        detalhes = gest.listar_detalhes_financeiros(user_nome) or []
    except Exception:
        log.exception(f"bloco_detalhe_financeiro: falha ao ler {user_nome}")
        return False
    if not detalhes:
        return False

    mostrados = detalhes[:max(1, int(limite_competencias or 1))]
    with ui.column().classes("w-full gap-2 mt-2"):
        ui.separator().classes("my-1")
        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
            ui.icon("payments", size="18px").classes("text-grey-6")
            ui.label("Contracheque (somente leitura)").classes(
                "text-subtitle2 text-grey-8")
        ui.label("Capturado do Portal da Transparência na ficha de "
                 "contracheque. É o valor que a pessoa recebeu de fato — o "
                 "salário do contrato acima é só uma parte dele.").classes(
            "text-caption text-grey-6")

        for det in mostrados:
            with ui.column().classes("w-full gap-1"):
                with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                    ui.badge(det.get("competencia") or "—", color="blue-grey-2") \
                        .props("text-color=blue-grey-10 outline dense")
                    if det.get("matricula"):
                        ui.label(f"matrícula {det['matricula']}").classes(
                            "text-caption text-grey-6")
                # Grade de 2 pares = 4 colunas: rótulo/valor, rótulo/valor.
                with ui.grid(columns=2).classes("w-full").style(
                        "gap: 0.6rem 2rem"):
                    _par_de_campos("sb", "Salário base", det.get("salario_base"))
                    _par_de_campos("pr", "Proventos", det.get("proventos"))
                    _par_de_campos("ds", "Descontos", det.get("descontos"))
                    _par_de_campos("li", "Valor líquido", det.get("liquido"))

                itens = det.get("itens") or []
                if itens:
                    with ui.column().classes("w-full gap-0 mt-1"):
                        ui.label("Verbas do contracheque").classes(
                            "text-caption text-grey-6")
                        with ui.grid(columns=2).classes("w-full").style(
                                "gap: 0.3rem 2rem"):
                            for item in itens:
                                rotulo = (item.get("descricao")
                                          or item.get("codigo") or "verba")
                                valor = item.get("valor")
                                with ui.row().classes(
                                        "w-full items-baseline justify-between "
                                        "min-w-0").style("gap: 0.5rem"):
                                    ui.label(str(rotulo)).classes(
                                        "text-caption text-grey-8 truncate "
                                        "min-w-0")
                                    ui.label(_valor(valor)).classes(
                                        "text-caption font-medium no-wrap")
                else:
                    ui.label("A ficha veio sem a lista de verbas.").classes(
                        "text-caption text-grey-6")
        if len(detalhes) > len(mostrados):
            with ui.label(
                    f"Existem {len(detalhes)} competências capturadas; "
                    f"mostrando as {len(mostrados)} mais recentes.").classes(
                    "text-caption text-grey-6"):
                pass
    return True


def bloco_diarias(user_nome):
    """As diárias que a pessoa recebeu, ano a ano (somente leitura).

    O valor é o CONSOLIDADO ANUAL do portal (`idExercicio` + `vlPago` do ano:
    uma linha por favorecido por ano, ligada pelo CPF parcial). Fica junto do
    contracheque porque responde a mesma pergunta — "o que eu recebi de fato"
    — por outra verba. Nada aqui é editável: vem do portal e atualiza na
    próxima coleta (dia 10+). Devolve `False` quando não há nada, para o
    chamador não desenhar bloco vazio.
    """
    try:
        linhas = gest.listar_diarias_usuario(user_nome) or []
    except Exception:
        log.exception(f"bloco_diarias: falha ao ler {user_nome}")
        return False
    if not linhas:
        return False
    try:
        total = sum(float(l.get("vl_pago") or 0) for l in linhas)
    except Exception:
        total = 0.0
    with ui.column().classes("w-full gap-2 mt-2"):
        ui.separator().classes("my-1")
        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
            ui.icon("flight", size="18px").classes("text-grey-6")
            ui.label("Diárias recebidas (somente leitura)").classes(
                "text-subtitle2 text-grey-8")
        ui.label("Consolidado anual do Portal da Transparência, ligado pelo "
                 "CPF. Atualiza na coleta mensal (após o dia 10).").classes(
            "text-caption text-grey-6")
        with ui.grid(columns=2).classes("w-full").style(
                "gap: 0.6rem 2rem"):
            for linha in linhas:
                try:
                    rotulo = f"Diárias {linha.get('ano') or '—'} (pago)"
                    valor = ("R$ {:,.2f}".format(
                        float(linha.get("vl_pago") or 0))
                        .replace(",", "X").replace(".", ",")
                        .replace("X", "."))
                    _par_de_campos("dr", rotulo, valor)
                except Exception:
                    continue
        if len(linhas) > 1:
            try:
                total_txt = ("R$ {:,.2f}".format(total)
                             .replace(",", "X").replace(".", ",")
                             .replace("X", "."))
                _par_de_campos("dt", "Total no período (pago)", total_txt)
            except Exception:
                pass
    return True


def _ficha_contrato(contrato, compacto, mostrar_matricula):
    """Uma matrícula: os 12 campos do portal, mais a matrícula se houver mais
    de uma ficha para a mesma pessoa."""
    with ui.column().classes("w-full gap-1"):
        if mostrar_matricula:
            with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                ui.label(f"Matrícula {contrato.get('matricula') or '—'}").classes(
                    "text-body2 font-bold")
                if contrato.get("principal"):
                    ui.badge("principal", color="grey-4").props(
                        "outline dense text-color=grey-9")
        _etiqueta("unidade", "Secretaria", contrato.get("unidade"), compacto)
        _etiqueta("lotacao", "Lotação", contrato.get("lotacao"), compacto)
        _etiqueta("cargo", "Cargo", contrato.get("cargo"), compacto)
        _etiqueta("vinculo", "Vínculo", contrato.get("vinculo"), compacto)
        _etiqueta("situacao", "Situação", contrato.get("situacao"), compacto)
        _etiqueta("admissao", "Admissão", contrato.get("admissao"), compacto)
        if not compacto:
            _etiqueta("tipo", "Tipo", contrato.get("tipo"), compacto)
            _etiqueta("exoneracao", "Exoneração", contrato.get("exoneracao"), compacto)
            _etiqueta("regime", "Regime", contrato.get("regime"), compacto)
            _etiqueta("carga_horaria", "Carga horária",
                      contrato.get("carga_horaria"), compacto)
        _etiqueta("remuneracao", "Remuneração", contrato.get("remuneracao"), compacto)
        if not compacto:
            _etiqueta("ficha_contracheque", "Ficha de contracheque",
                      contrato.get("ficha_contracheque"), compacto)


def bloco_dados_folha(user_nome, *, compacto=False, titulo="Dados da folha"):
    """Desenha os campos da folha da pessoa, somente como texto.

    Aparece em três telas — diálogo "Editar" do admin, popup do nome na lista
    e "Meu Perfil" do próprio servidor — e NENHUMA delas pode editar o que
    este bloco mostra. `compacto=True` é a versão do popup: duas colunas,
    sem o cabeçalho comprido, para caber no overlay.

    Quem não tem contrato (conta fora da folha, como a conta do administrador ou as contas de
    fábrica) recebe um aviso curto em vez de um bloco vazio — bloco vazio parece
    falha de carga.
    """
    try:
        contratos = gest.listar_contratos(user_nome) or []
    except Exception:
        log.exception(f"bloco_dados_folha: falha ao ler os contratos de {user_nome}")
        return

    with ui.column().classes("w-full gap-2"):
        if not contratos:
            with ui.row().classes("w-full items-center gap-2"):
                ui.icon("info_outline", size="16px").classes("text-grey-5")
                ui.label("Esta conta não tem registro na folha de "
                         "funcionários.").classes("text-caption text-grey-6")
            return

        principal = next((c for c in contratos if c.get("principal")), contratos[0])
        outros = [c for c in contratos if c is not principal]
        # Mais de uma matrícula para a mesma pessoa: a frase muda, porque é
        # outro fato que precisa ser dito. A pessoa que lê tem duas fichas
        # na mão e precisa saber que são da mesma pessoa.
        aviso_extra = ""
        if outros:
            ativos = [c for c in contratos if _situacao_contratada(c.get("situacao"))]
            if ativos and len(ativos) < len(contratos):
                aviso_extra = (
                    " Há contrato em que a pessoa está ativa e outro em que "
                    "não está — são contratos diferentes, e nenhum dos dois "
                    "desliga a pessoa.")

        _cabecalho_folha(titulo, _subtitulo(principal, aviso_extra, compacto))

        _ficha_contrato(principal, compacto, mostrar_matricula=bool(outros))
        # Tempo de casa e aniversário: as duas perguntas que o servidor faz ao
        # olhar o próprio cadastro, e que a ficha não respondia.
        bloco_tempo_de_casa(principal.get("admissao"), principal.get("vinculo"))

        for contrato in outros:
            ui.separator().classes("my-1")
            _ficha_contrato(contrato, compacto, mostrar_matricula=True)

        # O contracheque é o que a pessoa realmente recebeu, e é um bloco
        # SEPARADO do contrato porque vem de outra tabela
        # (`tb_detalhe_ficha`, por competência) — e porque antes ele não era
        # mostrado em lugar nenhum.
        try:
            bloco_detalhe_financeiro(user_nome)
        except Exception:
            log.exception("bloco_dados_folha: detalhe financeiro não desenhado")

        # As diárias vêm de outra coleta (`tb_diarias`, por ano, ligada pelo
        # CPF) e entram no mesmo lugar: perfil, ficha e edição.
        try:
            bloco_diarias(user_nome)
        except Exception:
            log.exception("bloco_dados_folha: diárias não desenhadas")


def _subtitulo(principal, aviso_extra, compacto):
    """A frase que explica a origem dos dados e por que não se edita."""
    competencia = principal.get("competencia")
    origem = ("Dados publicados pelo Portal da Transparência"
              + (f", competência {competencia}" if competencia else "") + ". ")
    if compacto:
        return origem + "Somente leitura — vêm da folha."
    return origem + ("Não são editáveis aqui: vêm da folha e são atualizados "
                     "na próxima carga." + aviso_extra)


def bloco_dados_folha_resumido(user_nome):
    """Secretaria, cargo, vínculo, situação e remuneração — para a ficha.

    A ficha abriu com o clique no nome da lista (10/10/2026, era um tooltip
    ao passar o mouse). O `compacto=True` da folha vem da própria assinatura
    e continua disponível para quem quiser a versão curta.

    A REMUNERAÇÃO entrou junto: o pedido foi "todos os dados — cargo,
    secretaria e salário", e o resumo antigo parava em vínculo/situação.
    Ela é o dado que a pessoa procura primeiro e era o que faltava.
    """
    try:
        contratos = gest.listar_contratos(user_nome) or []
    except Exception:
        log.exception(f"bloco_resumido: falha ao ler os contratos de {user_nome}")
        return
    if not contratos:
        return
    principal = next((c for c in contratos if c.get("principal")), contratos[0])
    with ui.column().classes("w-full gap-1 mt-1"):
        ui.separator().classes("my-1")
        ui.label("Folha (somente leitura)").classes(
            "text-caption font-bold text-grey-7")
        for chave, rotulo in (("unidade", "Secretaria"),
                              ("cargo", "Cargo"),
                              ("vinculo", "Vínculo"),
                              ("remuneracao", "Remuneração"),
                              ("lotacao", "Lotação"),
                              ("admissao", "Admissão"),
                              ("situacao", "Situação")):
            valor = _valor(principal.get(chave))
            if valor == "—":
                continue
            _etiqueta(chave, rotulo, valor, compacto=False)
        try:
            diarias = gest.listar_diarias_usuario(user_nome) or []
            if diarias:
                partes = []
                for linha in diarias:
                    try:
                        pago = ("R$ {:,.2f}".format(
                            float(linha.get("vl_pago") or 0))
                            .replace(",", "X").replace(".", ",")
                            .replace("X", "."))
                        partes.append(f"{linha.get('ano')}: {pago}")
                    except Exception:
                        continue
                if partes:
                    _etiqueta("diarias", "Diárias (pago/ano)",
                              " · ".join(partes), compacto=False)
        except Exception:
            log.exception("bloco_resumido: diárias não desenhadas")
        if len(contratos) > 1:
            with ui.row().classes("w-full items-center gap-1 flex-wrap mt-1"):
                ui.badge(f"{len(contratos)} matrículas", color="grey-4").props(
                    "outline dense text-color=grey-9").tooltip(
                    "A pessoa tem mais de um contrato na folha. "
                    "Abra a ficha para ver todos.")