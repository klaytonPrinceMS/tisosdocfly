"""Provisório — 4 padrões visuais (Login + Home) na estética de app social.

Substitui a primeira tentativa, que ficou genérica demais: eram CSS
frameworks de uso geral (Tachyons, Spectre, Foundation, Milligram), sem a
linguagem visual de rede social/mensageiro. Aqui os 4 padrões são escolhidos
dentro da estética pedida — resemble **Facebook** e **WhatsApp**: cartão
claro sobre fundo cinza, cantos generosamente arredondados, barra de topo
colorida e tipografia sans-serif limpa.

OS 4 PADRÕES
-------------
  azul       nome do produto em azul grande ACIMA do cartão branco, botão azul
             de largura toda — o login clássico do Facebook
  verde      TELA DIVIDIDA: painel verde à esquerda, formulário branco à direita
             (empilha e o painel some no celular), botão em pílula
  roxo       cartão muito arredondado (raio 22px) com faixa gradiente no topo
  preto      monocromático, aro colorido no avatar, botão preto

Nenhum framework genérico reproduz linguagem de mensageiro (painel dividido,
faixa gradiente, aro de avatar), então os quatro são **designs próprios**,
escritos para esta sessão em `assets/css/preview-estilos-v1.css`. A identidade
visual vem por custom property (`--pe-*`).

A COR DO BOTÃO SAI PELA VARIÁVEL `--q-primary`, NÃO POR CSS
----------------------------------------------------------
O Quasar declara `.bg-primary { background: var(--q-primary) !important }`
*dentro de uma cascade layer*, e em `!important` a camada vence QUALQUER
regra nossa que esteja fora de camada — por mais específica que ela seja, e
por mais `!important` que esteja. Tentamos pintar o botão "por fora" e não
funcionou: nem `!important` nosso, nem universal. A saída é a via que o próprio
Quasar usa para personalizar o tema (`ui.colors`): mexer no TOKEN. Por isso o botão do
login e o cabeçalho da Home saem na cor do padrão sem uma única disputa de
cascata no meio. Ver `_defs_css` e o bloco do `.q-layout` na folha.

SELEÇÃO POR QUERY PARAM
-----------------------
`?estilo=<chave>`. O botão do alternador apenas navega — **sem JavaScript
direto** e **sem gravar no banco**, então a URL é compartilhável, o padrão
aparece em print/compartilhamento e não custa uma escrita por troca.

ACESSIBILIDADE
--------------
As cores de botão foram escurecidas um passo para chegar a 4,5:1 com o texto
branco (WCAG AA): o azul clássico do Facebook dá 4,23:1 e o verde vivo do
WhatsApp só 1,98:1 — os dois reprovariam. Ver o comentário em `_CORES`.

EN: TEMPORARY 4-pattern switcher for login and home, in the social-app
visual family. Chosen via `?estilo=<key>`; the switcher only navigates — no
direct JavaScript, no database writes. Button colour comes from overriding
`--q-primary` (gancho de personalização do próprio Quasar), because Quasar's `.bg-primary` is
`!important` inside a cascade layer and cannot be outranked by a stylesheet.

>>> ESTE MÓDULO É PROVISÓRIO <<<
Para REMOVER depois de escolher o padrão definitivo:
  1. apague este arquivo e `assets/css/preview-estilos-v1.css`;
  2. em `main.py`, apague o bloco `montar_rotas_static()` do boot e os blocos
     `# ===== PROVISÓRIO: padrão visual =====` em `page_login`,
     `_construir_dashboard` e `page_dashboard` (o `modelo=` volta a ser o
     literal de antes);
  3. nada mais depende deste módulo (só `home_visual` continua valendo).
"""

import os

VERSAO_CSS = "v1"
ARQUIVO_CSS = f"preview-estilos-{VERSAO_CSS}.css"
DIRETORIO_CSS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "assets", "css")


def _versao_arquivo() -> str:
    """Cache-buster da folha: o mtime do arquivo.

    Durante o protótipo a folha muda várias vezes por sessão; com uma versão
    fixa (`?v=1`) o navegador segura a folha antiga e a mudança "não aparece" —
    foi exatamente o que aconteceu na primeira rodada de testes. O mtime muda a
    cada edição, então o Ctrl+F5 já traz a folha nova.
    """
    try:
        return str(int(os.path.getmtime(os.path.join(DIRETORIO_CSS, ARQUIVO_CSS))))
    except Exception:
        return VERSAO_CSS

PADROES = (
    {"chave": "azul", "rotulo": "Azul",
     "descricao": "azul de marca, nome grande e cartoes brancos"},
    {"chave": "verde", "rotulo": "Verde",
     "descricao": "tela dividida, painel verde e botao em pilula"},
    {"chave": "roxo", "rotulo": "Roxo",
     "descricao": "faixa gradiente roxo para rosa, bem arredondado"},
    {"chave": "preto", "rotulo": "Preto",
     "descricao": "preto, aro colorido no avatar, bem monocromatico"},
)
CHAVES = tuple(p["chave"] for p in PADROES)
ROTULOS = {p["chave"]: p["rotulo"] for p in PADROES}
DESCRICOES = {p["chave"]: p["descricao"] for p in PADROES}

# Opção "Padrão": NÃO é um estilo, é a AUSÊNCIA de escolha pessoal. Quem clica
# nela volta a seguir a cor que o ADMINISTRADOR configurou para o módulo
# (ver `ler_estilo`): o vazio não é ausência de estilo, é ausência de imposição.
# Fica no fim da lista para os quatro estilos ficarem juntos no começo.
CHAVE_PADRAO = "padrao"
OPCAO_PADRAO = {
    "chave": CHAVE_PADRAO, "rotulo": "Padrão",
    "descricao": "segue o padrão definido pelo administrador",
}
# Padrão do LOGIN quando a URL não traz `?estilo=` — DEFINIDO PELO RESPONSÁVEL:
# o WhatsApp foi o escolhido (tela dividida, botão em pílula, painel teal).
# Trocar de padrão depois é só mudar esta linha.
PADRAO_PADRAO = "verde"

# Estilo FIXO da tela de login, por decisão do responsável: é o WhatsApp
# (`verde`) para todo mundo, independentemente da preferência que o usuário
# tenha escolhido para os módulos internos. Fica em constante própria para
# que, se um dia o login deixar de ser fixo, o padrão do sistema
# (`PADRAO_PADRAO`) possa mudar sem arrastar o login junto.
PADRAO_LOGIN = "verde"

# Padrão que absorve a cor do admin (`cor_principal`/`cor_fundo` de tb_config).
#
# Deixou de ser `None` em 30/09/2026. Enquanto era `None`, a comparação
# `p == PADRAO_ADM` nunca era verdadeira, e aí "Padrão" caía no estilo default
# do protótipo — **verde** — em vez da cor do administrador. Era o defeito do
# print: com "Padrão" escolhido, a tela estava na cor do admin (quase preta) e
# o botão do diálogo aparecia verde. Escolher "Padrão" e receber uma cor que o
# administrador nunca configurou é a mesma confusão.
#
# Agora `PADRAO_ADM` aponta para a chave default, então "Padrão" significa
# exatamente o que a pessoa lê: a cor que o administrador configurou.
PADRAO_ADM = PADRAO_PADRAO

# ---------------------------------------------------------------------------
#  Paleta de cada padrão. `escuro` decide se a Home recebe as classes de tema
#  escuro do Quasar; `primaria_texto` é separado de `primaria` porque o
#  WhatsApp usa teal escuro na barra e verde claro no botão; `primaria_q` é a
#  cor que o Quasar assume como "primary" (é dela que sai a cor do botão).
_CORES = {
    "azul": {
        "escuro": False, "familia": "Feed",
        "fundo": "#f0f2f5", "superficie": "#ffffff",
        # O azul clássico do Facebook (#1877f2) dá 4,23:1 com o texto branco do
        # botão — abaixo dos 4,5:1 da WCAG AA. Este é o tom um passo mais
        # escuro: 5,24:1, e ainda lê como "azul de rede social".
        "primaria": "#1668d8", "primaria_q": "#1668d8",
        "primaria_texto": "#ffffff",
        "raio": "8px", "sombra": "0 1px 2px rgba(0,0,0,.13)",
    },
    "verde": {
        "escuro": False, "familia": "Mensageiro",
        "fundo": "#eae6df", "superficie": "#ffffff",
        "primaria": "#075e54", "primaria_q": "#0f7a6d",
        # O verde vivo do WhatsApp (#25d366) dá só 1,98:1 com branco — impossível
        # num botão de texto branco. O verde de ação do botão é o teal do
        # próprio WhatsApp, um tom mais escuro (5,22:1); o #25d366 continua
        # disponível como cor de acento.
        "primaria_acao": "#25d366",
        "primaria_texto": "#ffffff",
        "raio": "10px", "sombra": "0 1px 2px rgba(0,0,0,.10)",
    },
    "roxo": {
        "escuro": False, "familia": "Bolhas",
        "fundo": "#f4f5fb", "superficie": "#ffffff",
        "primaria": "#7c3aed", "primaria_q": "#7c3aed", "primaria_2": "#db2777",
        "primaria_texto": "#ffffff",
        "raio": "22px", "sombra": "0 2px 10px rgba(80,60,160,.14)",
    },
    "preto": {
        "escuro": False, "familia": "Monocromático",
        "fundo": "#fafafa", "superficie": "#ffffff",
        "primaria": "#111111", "primaria_q": "#111111", "primaria_2": "#e1306c",
        "primaria_texto": "#ffffff",
        "raio": "14px", "sombra": "0 1px 3px rgba(0,0,0,.10)",
    },
}


# ---------------------------------------------------------------------------
#  API
# ---------------------------------------------------------------------------
def montar_rotas_static() -> bool:
    """Monta a rota estática que serve a folha do protótipo (`/assets/css/*`).

    O projeto só tinha um mount estático (`/css/frameworks`, em `tema_css`), e
    ele aponta para `assets/css/frameworks` — por isso o `<link>` do protótipo
    devolvia 404 e NENHUMA regra de estilo era aplicada. Montando o diretório
    `assets/css` inteiro, o `<link>` passa a ser servido sem rede externa.

    Chamada uma vez no boot do `main.py`. Falha silenciosa: a página continua
    abrindo, só sem a decoração do protótipo.
    """
    destino = os.path.abspath(DIRETORIO_CSS)
    if not os.path.exists(os.path.join(destino, ARQUIVO_CSS)):
        return False
    try:
        from nicegui import app
        app.add_static_files("/assets/css", destino)
        return True
    except Exception as exc:
        try:
            import logging
            logging.getLogger(__name__).warning(
                "preview_estilos: rota estática não montada: %s", exc)
        except Exception:
            pass
        return False


# Marcador das telas que ocupam a JANELA INTEIRA: login e troca de senha.
#
# Existe para o CSS dar um alvo próprio. A classe `pe-*` não serve, porque ela
# também está na Home e em todos os módulos quando a pessoa escolheu um
# estilo — uma regra para "tela cheia" escrita em cima de `pe-*` mudaria o
# respiro de todas as telas do sistema.
CLASSE_TELA_INTEIRA = "preview-tela-inteira"


def _defs_css(paleta: dict) -> str:
    """`:root` com as custom properties do padrão + o `--q-primary` da página.

    As `--pe-*` vão na raiz porque o fundo da página precisa delas FORA do
    wrapper do padrão (no `<body>`/`.q-page`).

    A `--q-primary` é a peça que mais importa e precisa de cuidado: o Quasar
    declara `.bg-primary { background: var(--q-primary) !important }` dentro de
    uma cascade layer, e em `!important` a camada ganha de QUALQUER regra nossa
    fora de camada — por mais específica que ela seja. Ou seja: não dá para
    pintar botão e cabeçalho "por fora"; tem de ser pela variável que o próprio
    Quasar lê, que é o mesmo mecanismo de `ui.colors()`.

    Ela é escrita no `.q-layout` (e não no wrapper do padrão) porque o
    cabeçalho é montado pelo layout de 4 partes, ACIMA do wrapper. O
    `!important` é o que vence a declaração inline que o `ui.colors()` deixa
    no layout. O valor vem da paleta, que continua sendo a fonte única — não
    há cor chumbada no CSS.

    O `.q-dialog` está na lista pelo mesmo motivo e pela mesma armadilha: modal
    do Quasar nasce num portal no `body`, IRMÃO do `.q-layout`, então uma
    regra que sópega o layout deixa o botão do modal com a cor do
    administrador. O token é o mesmo; só o alvo mudou.
    """
    chaves = ("fundo", "superficie", "primaria", "primaria_acao", "primaria_2",
              "primaria_texto", "raio", "sombra")
    linhas = "\n".join(
        f"    --pe-{k}: {paleta[k]};" for k in chaves if k in paleta)
    q_primaria = paleta.get("primaria_q", paleta["primaria"])
    # ATENÇÃO: `--q-primary` é só o PONTO DE PARTIDA. Ver
    # `aplicar_no_botao()` — o botão padronizado do sistema lê a paleta do
    # estilo que estiver em vigor e escreve a cor nele. Nenhum botão tem cor
    # fixa: quem escolhe o estilo escolhe a cor de todos eles.
    #
    # `.q-dialog` entrou na lista em 30/09/2026 porque o diálogo é a primeira
    # coisa que mostrou o furo: o Quasar monta modal num PORTAL no `body`, fora
    # do `.q-layout`, e a regra antiga cobria só o layout. Resultado era o botão
    # do "Salvar nova senha" na cor do ADMINISTRADOR (o preto de
    # `cor_principal`), com o servidor logado num estilo verde — o botão não
    # seguia o tema que a pessoa estava usando. O token é o mesmo e o
    # `!important` é o mesmo; só faltava o elemento certo no seletor.
    return (f":root {{\n{linhas}\n  }}\n"
            f"  .pe-{paleta['chave']},\n"
            f"  body:has(.pe-{paleta['chave']}) .q-layout,\n"
            f"  body:has(.pe-{paleta['chave']}) .q-dialog,\n"
            f"  body:has(.pe-{paleta['chave']}) .q-menu,\n"
            f"  body:has(.pe-{paleta['chave']}) .q-notification {{\n"
            f"    --q-primary: {q_primaria} !important;\n"
            f"  }}\n"
            # O `padding: 0` aqui é a correção do SCROLL QUE NÃO LEVA A
            # NENHUM LUGAR (30/09/2026). A tela de login abria com a barra de
            # rolagem sempre visível mesmo com todo o conteúdo à vista: o
            # `.q-page` do Quasar já traz `min-height: 100vh` E `padding: 16px`,
            # e o wrapper da tela também pedia `100vh`. São dois 100vh mais 32px
            # de padding dentro de uma janela de 100vh — o transbordo é
            # garantido, e a barra some quando se rola até o fim. A pessoa
            # rolava e não acontecia nada.
            #
            # O escopo é `CLASSE_TELA_INTEIRA`, e não `body:has(.pe-verde)`:
            # a classe `pe-*` também está na Home e em todos os módulos quando
            # a pessoa escolheu um estilo, e zerar o padding da página tiraria
            # o respiro de todas as telas do sistema para consertar o login.
            # `CLASSE_TELA_INTEIRA` só existe nos layouts de tela cheia (login e
            # troca de senha), que já trazem o próprio respiro.
            # O `!important` não é força bruta: é a mesma armadilha de camada do
            # `--q-primary` acima. O NiceGUI/Quasar escreve o padding do
            # `.q-page` numa cascade layer, e em camada quem vence é a camada —
            # por mais específica que seja a nossa regra. Sem o `!important` a
            # regra estava no CSS e não valia nada (medido: 16px no
            # computado, com a regra presente na folha).
            #
            # E ZERAR O `.q-page` SOZINHO NÃO RESOLVIA (medido 04/10/2026): o
            # padding que produz o transbordo não está nele, está no FILHO.
            # O NiceGUI embrulha o conteúdo da página em `.nicegui-content`,
            # que nasce com `padding: 16px` e `display: flex; gap: 16px`.
            # A regra acertava o pai (computado passava a `0px`) e a página
            # continuava 32px mais alta que a janela — 16px de padding em cima
            # e 16px embaixo de um `min-height: 100vh`. Era o
            # `.nicegui-content` que precisava entrar, e ele é o que o
            # `padding: 0 !important` nunca alcança.
            f"  body:has(.{CLASSE_TELA_INTEIRA}) .q-page,\n"
            f"  body:has(.{CLASSE_TELA_INTEIRA}) .nicegui-content {{\n"
            f"    padding: 0 !important;\n"
            # O `gap` vai junto pelo mesmo motivo: são 16px entre o wrapper e
            # o que ele envolve, e eles somam aos 32px do transbordo. zerado o
            # padding, sobrava só o `gap` fazendo a mesma barra sumir.
            f"    gap: 0 !important;\n"
            f"  }}\n"
            # TOOLTIP DE TEXTO LONGO (04/10/2026).
            #
            # O QTooltip do Quasar escreve `max-height`, `min-height` e
            # `max-width` no atributo `style` **quando aparece**, e reescreve o
            # que o servidor mandou. Medido: o tooltip dos dados do responsável
            # saía com `max-height: 14px` — uma linha só — e o resto do texto
            # ficava fora da tela, colado no topo da página. Nenhum `style`
            # inline enviado pelo servidor vence isso, porque o Quasar escreve
            # DEPOIS; só uma regra de folha com `!important` vence o inline.
            #
            # O `min-height: 0 !important` é o par do `max-height`: sem ele o
            # Quasar também impõe `min-height: 14px` e a caixa fica com a
            # altura de uma linha mesmo depois de o teto ser solto.
            f"  .tt-texto-longo {{\n"
            f"    max-height: 420px !important;\n"
            f"    min-height: 0 !important;\n"
            f"    max-width: 340px !important;\n"
            f"    white-space: pre-line;\n"
            f"    line-height: 1.35;\n"
            f"    text-align: left;\n"
            f"  }}")


def aplicar(padrao: str = "", cor_principal: str = "#000000",
            cor_fundo: str = "#EEEEEE") -> dict:
    """Aplica o padrão: injeta as custom properties e a folha de estilo.

    Devolve a paleta efetiva, para a tela usar as cores.

    **A cor do administrador só entra em "Padrão"** — nunca num estilo concreto.

    A regra é `if not padrao or padrao == CHAVE_PADRAO`, e não
    `p == PADRAO_ADM`. A diferença não é de estilo, é de correção: com
    `PADRAO_ADM` apontando para uma chave que é TAMBÉM um estilo concreto
    (`PADRAO_ADM = PADRAO_PADRAO = "verde"`), o login — que pede `verde` por
    decisão do responsável — passava a receber `cor_principal`, e a cor preta
    do admin cobria o teal do WhatsApp. Foi a regressão de 30/09/2026: o login
    "perdeu a configuração e ficou preto".

    Com a regra por `padrao`, as duas perguntas ficam separadas e não colidem:

    - a pessoa escolheu um estilo? → vale o estilo, e o admin não interfere;
    - a pessoa ficou em "Padrão"? → vale a cor que o administrador configurou.
    """
    p = padrao if padrao in CHAVES else PADRAO_PADRAO
    paleta = dict(_CORES[p])
    paleta["chave"] = p
    if not padrao or padrao == CHAVE_PADRAO:
        # Sem escolha da pessoa: quem manda é o administrador.
        paleta["primaria"] = cor_principal or paleta["primaria"]
        paleta["fundo"] = cor_fundo or paleta["fundo"]
    try:
        from nicegui import ui
        ui.add_head_html(
            f"<style data-estilo-pe='{p}'>\n  {_defs_css(paleta)}\n</style>\n"
            f'<link rel="stylesheet" href="/assets/css/{ARQUIVO_CSS}?v={_versao_arquivo()}">')
    except Exception:
        pass
    return paleta


# ---------------------------------------------------------------------------
#  Telas
# ---------------------------------------------------------------------------
RODAPE = "Acesso restrito — uso interno da prefeitura"


def _dica(padrao: str, hint: str, tooltip: str = "", atraso_ms: int = 0) -> None:
    """Bloco de dica do rodapé do formulário (tom próprio de cada app).

    `tooltip` e `atraso_ms` são o par que virou o destino dos dados do
    responsável na tela de credenciais do `master` (04/10/2026): a dica
    continua sendo o texto curto, e os dados ficam a um `hover` de distância,
    aparecendo só depois de `atraso_ms` milissegundos com o mouse em cima.
    O `delay` é do QTooltip do Quasar e é ele que faz a espera — um
    `ui.timer` aqui mostraria o tooltip para quem não está olhando para a
    dica, que é justamente quem não deve vê-lo.
    """
    if not hint:
        return
    try:
        from nicegui import ui
        with ui.row().classes("pe-aviso w-full items-start no-wrap").style(
                "gap: .5rem; padding: .7rem; margin-top: 1.1rem"):
            ui.icon("info", size="18px").classes("q-mt-xs")
            # `white-space: pre-line` (18/10/2026): a dica da troca de senha
            # passou a ser uma LISTA, uma regra por linha. Sem isto o HTML
            # come os `\n` e as sete regras viram um parágrafo só.
            ui.label(hint).classes("text-caption grow min-w-0").style(
                "white-space: pre-line")
        if tooltip:
            try:
                _t = ui.tooltip(tooltip)
                _t.props(f"delay={int(atraso_ms)}")
                # `tt-texto-longo` é uma regra da FOLHA com `!important`, e
                # não um `style` inline, porque o Quasar reescreve o `style`
                # do tooltip quando ele aparece (ver a regra e a medição em
                # `_defs_css`). É ela que segura o `max-height` e o
                # `white-space: pre-line` que dão as quatro linhas.
                _t.classes("tt-texto-longo text-caption")
            except Exception:
                pass
    except Exception:
        pass


def _campos(campos) -> None:
    """Chama o callback do `main.py` dentro de uma coluna com respiro."""
    from nicegui import ui
    with ui.column().classes("w-full min-w-0").style("gap: 1rem"):
        campos()


def _rodape() -> None:
    from nicegui import ui
    with ui.column().classes("w-full items-center").style("gap: .25rem; margin-top: 1.25rem"):
        ui.label(RODAPE).classes("text-caption text-grey-6 text-center")


# ---------------------------------------------------------------------------
#  Os 4 layouts. Cada um é uma FUNÇÃO separada de propósito: se os quatro
#  coubessem num `if/elif` só, trocar o estilo acabaria virando um galho
#  impossível de manter. Um por padrão deixa o removê-lo uma dela só.
# ---------------------------------------------------------------------------
# Largura maxima do CARTAO DE FORMULARIO da tela de login (layout verde).
#
# 680px, decisão do responsável em 05/10/2026 — e o número é o MESMO nas três
# telas do padrão verde (login, troca de senha e troca de credenciais do
# `master`). Antes cada uma passava a largura que o seu formulário precisava
# (640px, 640px e 880px); um número só é o que impede a mesma caixa de nascer
# com três larguras diferentes dependendo de quem abriu.
#
# A CONTA DA FOLGA (medido no navegador, 05/10/2026, 1920px)
# ------------------------------------------------------
# Com o padding lateral novo de 12px (abaixo), a caixa de 680px deixa 656px de
# conteúdo. A grade de dois pais da tela do `master`
# (`repeat(auto-fit, minmax(min(260px, 100%), 1fr))`, `gap: 16px`) divide isso
# em DUAS colunas de 319px (medido). É o que faz o telefone caber INTEIRO lado a
# lado: 140px do DDI + 8px de gap + 171px do número = 319px, e o número precisa
# de 112px para o placeholder "(##) #####-####" — sobram 33px.
#
# Antes (640px, padding 32px) a coluna saía com 279px: 140 + 8 + 131, e o
# número ficava no limite. Por isso o `master` passava `largura_caixa="880px"`.
#
# Por que 680px e não o menor número da conta (660px): a 660px as colunas
# saem com 309px (medido), o que já cabe, mas com 23px de sobra — e sobra é o
# que impede a próxima diferença de fonte (ou a instalação com a fonte do
# servidor maior) de voltar a cortar o campo. Por que não 700px: as colunas
# iriam a 329px sem ganhar nada, porque o formulário de sete campos do `master`
# já tem altura de sobra — o limite DELE é a largura, e 319px resolve.
#
# O `largura_caixa` continua na assinatura dos quatro layouts porque é API
# (`main.py:379` e `mod_tisosdocfly/telas.py:230` dependem dela); o que mudou foi
# só o valor padrão.
LARGURA_CAIXA_PADRAO = "680px"

# Padding LATERAL da caixa branca do formulário (05/10/2026, decisão do
# responsável): **6px**. Começou em 32px (`2rem`), passou por 12px na mesma
# decisão, e o responsável pediu menos uma vez ao ver a tela — 12px ainda lia
# como "moldura" e não como respiro. O vertical continua em 40px (`2.5rem`),
# porque respiro vertical é outro assunto: ele separa os campos, e 6px colaria
# as caixas umas nas outras.
#
# Medido: 32px tirava 64px de um cartão que já é estreito. O campo de login
# passou de 576px para 668px de conteúdo útil (680px de caixa menos 12px de
# padding lateral), e é essa largura maior que faz as DUAS colunas do `master`
# darem conta do telefone sem o `880px` de antes: 668px menos 16px de gap
# divide em DUAS colunas de 326px, e o telefone precisa de 319px. No celular o
# efeito é o mesmo, a favor: 390px de janela dão 348px de conteúdo.
PADDING_LATERAL_CAIXA = "0.375rem"
PADDING_VERTICAL_CAIXA = "2.5rem"


def _login_azul(*, padrao, icone, titulo, subtitulo, hint, paleta, campos,
                titulo_caixa=None, cabecalho=True, rodape=True,
                dica_tooltip="", dica_atraso_ms=0,
                largura_caixa=LARGURA_CAIXA_PADRAO) -> None:
    """Facebook: cartão branco centralizado sobre fundo cinza, marca em cima.

    É a assinatura do login do Facebook: nome do produto grande e azul ACIMA do
    cartão, formulário dentro do cartão, botão azul de largura total.
    """
    from nicegui import ui
    with ui.element("div").classes(f"pe-azul w-full min-w-0 {CLASSE_TELA_INTEIRA}").style(
            "min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 1.5rem 1rem; gap: 1.5rem"):
        with ui.column().classes("items-center").style("gap: .35rem"):
            ui.icon(icone, size="46px").classes("pe-marca")
            ui.label(titulo).classes("pe-marca").style("font-size: 2rem; line-height: 1.1")
            ui.label("entrar na sua conta").classes("text-caption text-grey-6")
        with ui.column().classes("pe-caixa-login w-full min-w-0").style(
                "padding: 1rem 1.1rem; max-width: 396px; gap: .9rem"):
            with ui.column().classes("w-full").style("gap: .85rem"):
                _campos(campos)
            _dica("azul", hint)
        if rodape:
            _rodape()


def _login_verde(*, padrao, icone, titulo, subtitulo, hint, paleta, campos,
                 titulo_caixa=None, cabecalho=True, rodape=True,
                 dica_tooltip="", dica_atraso_ms=0,
                 largura_caixa=LARGURA_CAIXA_PADRAO) -> None:
    """WhatsApp Web: painel colorido à esquerda, formulário branco à direita.

    A tela dividida é a assinatura do WhatsApp Web — e no telefone ela
    empilha, porque o painel some e sobra só o formulário.

    `titulo_caixa` é o título do FORMULÁRIO, e por padrão é o mesmo `titulo`.
    Existe porque a troca de senha usa o painel para o texto da tarefa
    ("Troca de senha obrigatória", no lugar onde o login escreve o nome do
    sistema) e a caixa branca para o nome do produto. Sem o parâmetro os dois
    campos repetiriam a mesma frase, e era o que acontecia: o mesmo título
    gigante à esquerda e o mesmo título pequeno à direita, lado a lado.
    """
    from nicegui import ui
    # O `padding` do CONTêiner é o respiro da tela (04/10/2026). Antes o
    # `.pe-verde` era `min-height: 100vh` com `padding: 0`, e os dois blocos
    # (`align-items: stretch`) iam de ponta a ponta: o painel teal e a caixa
    # branca encostavam nos quatro lados da janela, sem margem nenhuma.
    #
    # `box-sizing: border-box` é o que faz o trabalho: sem ele o `padding`
    # SOMARIA ao `min-height` e o transbordo de 32px voltaria — que é
    # exatamente o defeito que o `padding: 0 !important` do `.q-page`
    # (linha 281) existe para matar. Com border-box, os 100vh já incluem o
    # respiro, e o que encolhe é a ALTURA dos dois blocos, que é o que se
    # pediu: a tela deixa de ser um retângulo colado na janela.
    #
    # `clamp` em vez de px fixo porque o mesmo div serve ao telefone: 12px em
    # 390px de largura (onde a tela já é uma coluna só e o respiro é
    # escasso) e 28px em 1440px. Sem `gap`: o espaço pedido é na borda da
    # tela, não entre o painel e a caixa — que são as duas metades do mesmo
    # desenho e não podem parecer dois blocos separados.
    with ui.element("div").classes(f"pe-verde w-full min-w-0 {CLASSE_TELA_INTEIRA}").style(
            "min-height: 100vh; box-sizing: border-box; display: flex; "
            "align-items: stretch; flex-wrap: wrap; "
            "padding: clamp(0.75rem, 2.5vw, 1.75rem)"):
        # painel decorativo (some no telefone)
        with ui.column().classes("pe-painel w-full").style(
                "flex: 1 1 46%; min-width: 0; padding: 3rem 2.5rem; justify-content: center; gap: .5rem"):
            ui.icon(icone, size="54px")
            with ui.column().classes("w-full min-w-0").style("gap: .3rem; margin-top: .6rem"):
                ui.label(titulo).classes("pe-sistema")
                if subtitulo:
                    ui.label(subtitulo).classes("text-body2 opacity-90")
                # A dica aparece aqui SÓ quando é uma linha (18/10/2026).
                # O verde é o único padrão que escreve a dica duas vezes: uma
                # no painel decorativo e outra na caixa de aviso, logo abaixo
                # do formulário (`_dica`). Com uma frase curta as duas se
                # confundem com legenda; com a LISTA DE REGRAS da troca de
                # senha eram oito parágrafos repetidos lado a lado.
                #
                # E o lugar que sobra é o do aviso: o painel some abaixo de
                # 900px (o CSS `display: none`), e é justamente no telefone
                # que a pessoa precisa da regra. Lista de regras não cabe em
                # legenda de painel.
                if hint and "\n" not in hint:
                    ui.label(hint).classes("text-caption opacity-75").style(
                        "margin-top: .8rem; white-space: pre-line")
        # formulário
        #
        # `box-sizing: border-box` no pai (acima) é o que permite o `padding`
        # lateral virar 12px sem o `max-width` estourar: sem ele o padding
        # SOMARIA à largura e a caixa de 680px passaria a medir 704px. Ver o
        # bloco de comentário do contêiner — o mesmo mecanismo que impede o
        # transbordo vertical dos 100vh.
        with ui.column().classes("pe-caixa-login w-full min-w-0").style(
                f"flex: 1 1 54%; min-width: 0; box-sizing: border-box; "
                f"padding: {PADDING_VERTICAL_CAIXA} {PADDING_LATERAL_CAIXA}; "
                f"justify-content: center; gap: 1.1rem; max-width: {largura_caixa}"):
            # `cabecalho=False` some com o nome do produto e o "Entre para
            # continuar" DENTRO do cartão (04/10/2026). É pedido do
            # responsável para a tela de credenciais do `master`, e o motivo
            # não é estética: os dois blocos tiravam ~89px da área de rolagem
            # do formulário, e repete o que o painel teal à esquerda já
            # mostra — o nome do sistema está ali, em 54px.
            #
            # Só o layout verde consome `cabecalho`; os outros três aceitam o
            # parâmetro pela assinatura comum do despacho e porque o cartão
            # deles não tem esse par (o `azul` escreve "entrar na sua conta"
            # acima do cartão, fora dele). O que vale para os quatro é
            # `rodape`, que é o mesmo `_rodape()` em todos.
            #
            # ---- 05/10/2026: o nome do produto SAIU do cartão inteiro ----
            # O responsável pediu, no login e na troca de senha, tirar o
            # "[T! SOS DOCFLY Básica]" e o "[Entre para continuar]". E pediu o
            # "[T! SOS DOCFLY]" CENTRALIZADO no cartão branco, com este motivo:
            # no dispositivo onde o fundo verde não aparece, sem o nome no
            # cartão a tela fica uma coluna branca sem identificação nenhuma.
            #
            # A linha vive dentro do `if cabecalho` porque é a MESMA
            # responsabilidade: `cabecalho=False` é o pedido de "cartão só com
            # campos" que a tela de credenciais do master faz desde 04/10.
            # Quem pede o cartão limpo não quer o nome — quem pede o login e a
            # troca agora querem o nome curto, e o `_rodape` some com a linha
            # institucional para não repetir "prefeitura" duas vezes.
            if cabecalho:
                # `items-center` é o que CENTRALIZA de verdade, e não o
                # `text-center` do rótulo (medido em 05/10/2026): a coluna é
                # um flex de `align-items: flex-start`, então o rótulo
                # encolhe até o tamanho do texto — 98px num cartão de 668px —
                # e centralizar DENTRO de 98px não move nada. O nome ficava
                # colado na borda esquerda com 409px de vazio à direita.
                with ui.column().classes("w-full min-w-0 items-center").style(
                        "gap: .35rem"):
                    # Só o NOME, centralizado, em vez do nome do produto com
                    # o "Entre para continuar" embaixo. Não é o `titulo` do
                    # sistema: `titulo_caixa` é o que a troca de senha passa
                    # ("T! SOS DOCFLY"), e é ele que identifica o produto quando o
                    # painel não está na tela.
                    ui.label(titulo_caixa or titulo).classes("text-h6 text-center").style(
                        "font-weight: 700")
            _campos(campos)
            _dica("verde", hint, dica_tooltip, dica_atraso_ms)
            if rodape:
                _rodape()


def _login_roxo(*, padrao, icone, titulo, subtitulo, hint, paleta, campos,
                titulo_caixa=None, cabecalho=True, rodape=True,
                dica_tooltip="", dica_atraso_ms=0,
                largura_caixa=LARGURA_CAIXA_PADRAO) -> None:
    """Messenger: cartão muito arredondado com faixa gradiente no topo."""
    from nicegui import ui
    with ui.element("div").classes(f"pe-roxo w-full min-w-0 {CLASSE_TELA_INTEIRA}").style(
            "min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 1.5rem 1rem; gap: 1.25rem"):
        with ui.column().classes("pe-caixa-login w-full min-w-0").style(
                "padding: 0; max-width: 440px; overflow: hidden"):
            with ui.column().classes("pe-topo w-full items-center").style(
                    "gap: .6rem; padding: 1.4rem 1.2rem; flex-direction: column; text-align: center"):
                ui.icon(icone, size="38px")
                ui.label(titulo).classes("pe-sistema")
                if subtitulo:
                    ui.label(subtitulo).classes("text-caption opacity-90")
            with ui.column().classes("w-full").style("padding: 1.4rem 1.3rem; gap: 1rem"):
                _campos(campos)
                _dica("roxo", hint)
        if rodape:
            _rodape()


def _login_preto(*, padrao, icone, titulo, subtitulo, hint, paleta, campos,
                 titulo_caixa=None, cabecalho=True, rodape=True,
                dica_tooltip="", dica_atraso_ms=0,
                largura_caixa=LARGURA_CAIXA_PADRAO) -> None:
    """Instagram: monocromático, aro colorido no avatar, muito limpo."""
    from nicegui import ui
    with ui.element("div").classes(f"pe-preto w-full min-w-0 {CLASSE_TELA_INTEIRA}").style(
            "min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 1.5rem 1rem; gap: 1.25rem"):
        with ui.column().classes("items-center").style("gap: .6rem"):
            with ui.element("div").classes("pe-aro"):
                with ui.element("span").classes("pe-aro-interna"):
                    ui.icon(icone, size="26px")
            ui.label(titulo).classes("pe-marca").style("font-size: 1.5rem")
            if subtitulo:
                ui.label(subtitulo).classes("text-caption text-grey-6 text-center").style("max-width: 300px")
        with ui.column().classes("pe-caixa-login w-full min-w-0").style(
                "padding: 1.5rem 1.2rem; max-width: 400px; gap: 1rem"):
            _campos(campos)
            _dica("preto", hint)
        if rodape:
            _rodape()


_LAYOUTS = {
    "azul": _login_azul,
    "verde": _login_verde,
    "roxo": _login_roxo,
    "preto": _login_preto,
}


def tela_login(padrao: str, *, icone: str, titulo: str, subtitulo: str,
               hint: str, paleta: dict, campos, titulo_caixa: str = "",
               cabecalho: bool = True, rodape: bool = True,
               dica_tooltip: str = "", dica_atraso_ms: int = 0,
               largura_caixa: str = LARGURA_CAIXA_PADRAO) -> None:
    """Monta a tela de login no padrão escolhido.

    `campos` é uma CALLABLE que o `main.py` fornece: é ela quem cria os
    inputs e o botão com os `data-testid` de produção e o `tentar_login`
    real. Este módulo **não** sabe autenticar — ele só desenha o invólucro
    visual. É por isso que trocar de padrão não pode quebrar o login.

    `cabecalho` e `rodape` desligam, cada um, um bloco da moldura: o
    cabeçalho do cartão (nome do produto e "Entre para continuar", no layout
    verde) e o rodapé institucional. São os dois que mais custam altura para
    quem tem formulário longo, e a tela de credenciais do `master` — sete
    campos e dois blocos informativos — precisa é justamente de área de
    rolagem para os campos (04/10/2026).

    Se o layout do padrão falhar por qualquer motivo, cai no mais simples
    possível — os campos aparecem SEM nenhum enfeite, em vez da tela ficar
    branca. O login é a única tela que não pode quebrar.
    """
    p = padrao if padrao in _LAYOUTS else PADRAO_PADRAO
    try:
        _LAYOUTS[p](padrao=p, icone=icone, titulo=titulo, subtitulo=subtitulo,
                    hint=hint, paleta=paleta, campos=campos,
                    titulo_caixa=titulo_caixa, cabecalho=cabecalho,
                    rodape=rodape, dica_tooltip=dica_tooltip,
                    dica_atraso_ms=dica_atraso_ms,
                    largura_caixa=largura_caixa)
    except Exception:
        try:
            import logging
            logging.getLogger(__name__).exception(
                "preview_estilos: layout '%s' falhou; usando o login mínimo", p)
        except Exception:
            pass
        try:
            from nicegui import ui
            with ui.column().classes("w-full").style("padding: 2rem; gap: 1rem"):
                campos()
        except Exception:
            pass



# ---------------------------------------------------------------------------
#  ESCOLHA DE ESTILO: COOKIE DO NAVEGADOR (não vai para o banco)
# ---------------------------------------------------------------------------
# A preferência é DO NAVEGADOR, não do banco: fica só neste computador, neste
# navegador, e não viaja com o usuário para outra máquina nem aparece para
# outra pessoa que usar o mesmo login. Por isso ela NÃO está em `tb_config`.
#
# Por que cookie e não `localStorage`: o estilo é aplicado na RENDERIZAÇÃO, no
# servidor. Com `localStorage` só existe JavaScript rodando no cliente, então o
# servidor teria de desenhar a tela no padrão padrão e o navegador trocar
# depois — um piscar de layout em toda troca de estilo, e um segundo round-trip.
# O cookie é lido no request, então a página já nasce no estilo certo. Também
# evita JavaScript direto, que o projeto proíbe.
COOKIE_ESTILO = "estilo_visual"

# ---------------------------------------------------------------------------
#  AS TRÊS CAMADAS DO ESTILO (decisão do responsável, 06/10/2026)
# ---------------------------------------------------------------------------
# Antes havia uma camada só: "sem escolha" e "Padrão" davam o mesmo resultado,
# porque `ler_estilo()` devolvia "" nos dois casos, e "" significava "vale a cor
# que o administrador configurou". Quem entrava pela primeira vez ficava na cor
# do admin — quase sempre preta — e nunca via o sistema na identidade com que ele
# foi entregue.
#
# Agora são três, e a ordem importa:
#
#   1. ESCOLHA PESSOAL — o cookie deste navegador diz azul, preto, roxo ou
#      verde. Vence sempre: é a pessoa escolhendo, e ninguém desiste disso por
#      configuração de módulo.
#   2. "PADRÃO" — a pessoa clicou em Padrão. Aí sim vale a cor que o
#      ADMINISTRADOR configurou para aquele módulo (`tema_modulo.ler_tema`).
#      Escolher "Padrão" é dizer "não imponho nada", não "me devolva o verde".
#   3. SEM ESCOLHA — o navegador é novo, ou o cookie expirou, ou não é deste
#      usuário. Vale o PADRÃO DO SISTEMA, que é o verde.
#
# A camada 3 é a que o responsável pediu: cor verde padrão para todos ao logar,
# e se a pessoa definir sua preferência depois de logar, entra no que escolheu.
#
# `PADRAO_SISTEMA_PADRAO` é o valor embutido, para o sistema nascer certo mesmo
# que a chave não exista. A chave que manda é
# `estilo_visual_padrao_sistema` na `tb_config` — que existe desde 27/09/2026 e
# nunca era LIDA por ninguém (ver `padrao_do_sistema`).
CHAVE_PADRAO_SISTEMA = "estilo_visual_padrao_sistema"
PADRAO_SISTEMA_PADRAO = "verde"


def padrao_do_sistema() -> str:
    """O estilo do sistema para quem ainda não escolheu — verde, por padrão.

    Lê `tb_config.estilo_visual_padrao_sistema` e cai no verde quando a chave
    está ausente ou tem valor que não é um padrão válido. Fail-soft: um banco
    inacessível devolve o verde, que é o estado de entrega — nunca uma exceção,
    porque a tela de entrada não pode ser a que quebra.
    """
    try:
        from mod_tisosdocfly.bd_conexao import get_config
        bruto = (get_config(CHAVE_PADRAO_SISTEMA, PADRAO_SISTEMA_PADRAO)
                 or "").strip().lower()
        if bruto == CHAVE_PADRAO:
            return PADRAO_SISTEMA_PADRAO
        return bruto if bruto in CHAVES else PADRAO_SISTEMA_PADRAO
    except Exception:
        return PADRAO_SISTEMA_PADRAO
ROTA_TROCA = "/estilo-visual"


def paleta_do_estilo(padrao: str = "") -> dict:
    """A paleta de um estilo, ou a do ADMINISTRADOR quando não há escolha.

    É a função que o botão do sistema consulta para saber a cor. Ela é o
    **ponto único** onde "quem escolheu o estilo" vira uma cor concreta, e é
    por isso que a regra vale para o sistema inteiro em vez de valer por botão.
    """
    try:
        # Sem escolha — ou escolha "padrao" — quem decide é o ADMINISTRADOR.
        # Sem este desvio, "Padrão" caía na paleta default do protótipo em vez
        # da cor configurada, e era assim que "Padrão + azul" rendia botão
        # verde. A cor do admin tem de ser a que a pessoa vê no cabeçalho.
        if not padrao or padrao == CHAVE_PADRAO:
            from mod_tisosdocfly.bd_conexao import get_config
            paleta = dict(_CORES[PADRAO_ADM])
            paleta["primaria"] = (get_config("cor_principal", "") or
                                  paleta["primaria"])
            paleta["primaria_q"] = paleta["primaria"]
            paleta["chave"] = PADRAO_ADM
            return paleta
        p = padrao if padrao in CHAVES else PADRAO_ADM
        paleta = dict(_CORES[p])
        paleta["chave"] = p
        return paleta
    except Exception:
        try:
            import logging
            logging.getLogger(__name__).exception(
                "preview_estilos: paleta do estilo indisponível")
        except Exception:
            pass
        return dict(_CORES[PADRAO_PADRAO])


def cor_do_botao(padrao: str = "") -> str:
    """A cor de fundo de TODOS os botões do sistema, já resolvida.

    Resolution única, do maior para o menor:

    1. **Padrão do administrador.** Sem escolha da pessoa, a cor vem de
       `cor_principal`, que é o que o print mostrava: azul.
    2. **Estilo escolhido pela pessoa** (`estilo_visual`), com o mesmo cuidado
       de contraste que o cabeçalho usa — `primaria_q` é a variante
       escurecida, para o texto branco bater 4,5:1 (WCAG AA).

    Ela já resolve o caso "Padrão" do print, que é o mais comum: a pessoa não
    escolheu nada, então vale a cor do administrador, e o botão do diálogo
    precisa ser azul como todo o resto da tela.
    """
    try:
        paleta = paleta_do_estilo(padrao)
        return (paleta.get("primaria_q") or paleta.get("primaria")
                or "#1565C0")
    except Exception:
        return "#1565C0"


def _rgba(cor: str, alfa: float) -> str:
    """Converte `#rgb`/`#rrggbb` em `rgba(r,g,b,alfa)`.

    Aceita o que a paleta e o tema do módulo podem devolver — hex de 3 ou 6
    dígitos, `rgb()`/`rgba()` — porque um tom malformado não pode derrubar a
    pintura do botão: no pior dos casos devolve a cor sem alpha, o navegador
    descarta a regra e o botão fica como estava.
    """
    try:
        c = (cor or "").strip()
        if c.startswith("#"):
            h = c[1:]
            if len(h) == 3:
                h = "".join(ch * 2 for ch in h)
            if len(h) == 6:
                return (f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},"
                        f"{int(h[4:6], 16)},{alfa})")
        return c
    except Exception:
        return cor or ""


# Fundo do ícone-sozinho: bem fraco, na tonalidade do estilo. Abaixo de ~10% o
# círculo some de vez; acima de ~20% compete com o glifo. 14% é o ponto em que
# a ação fica visível como CIRCULO mas o ícone continua sendo a informação.
_ALFA_CIRCULO_ICONE = 0.14


def _estilo_do_botao(cor: str, variante: str = "primario") -> str:
    """Traduz a cor do estilo em vigor para a FORMA que a variante pede.

    Cada variante do `BotaoFabrica` tem uma forma, e a cor do estilo tem de
    entrar NESSA forma — nunca apagar a forma. Antes esta função escrevia
    `background-color:<cor>;color:#FFFFFF` em todas, o que destruía as
    variantes que não têm fundo: em Gestão de Usuários as ações de linha
    (editar, duplicar, sessões, bloquear, excluir) viravam uma fileira de
    círculos sólidos com o glifoperdido dentro. "Padrão" continuava correto
    porque nesse caminho a função nem pinta.

    | variante     | forma               | como a cor entra                     |
    |--------------|---------------------|--------------------------------------|
    | `primario`   | sólida              | fundo cheio, texto `#FFFFFF`         |
    | `secundario` | contorno            | fundo vazado, borda e texto na cor   |
    | `texto`      | só o rótulo         | fundo vazado, texto na cor           |
    | `icone`      | círculo translúcido | fundo a 14% da cor, ícone na cor cheia |

    A `secundario` e a `texto` são transcritas pelo mesmo motivo da `icone`:
    um botão de contorno com fundo sólido deixa de ser contorno, e um botão
    de texto com fundo sólido vira um segundo botão primário na mesma tela.
    """
    if variante == "icone":
        return f"background-color:{_rgba(cor, _ALFA_CIRCULO_ICONE)};color:{cor};"
    if variante == "secundario":
        return f"background-color:transparent;border-color:{cor};color:{cor};"
    if variante == "texto":
        return f"background-color:transparent;color:{cor};"
    return f"background-color:{cor};color:#FFFFFF;"


def aplicar_no_botao(elemento, *, chave_modulo: str = "tisosdocfly",
                     variante: str = "primario"):
    """Escreve a cor do estilo em vigor no botão. Chame DEPOIS de `.style()`.

    Existe porque **estilo inline vence CSS**. A fábrica de botões escreve
    `background-color` inline com a cor do módulo, e nenhuma custom property
    chega naquele botão. Por isso o botão do diálogo "Duplicar usuário" saía
    teal fixo enquanto a tela inteira estava azul — não era o botão estar
    "errado", era ele ser o único que não ouvia a escolha da pessoa.

    `variante` é a chave que `BotaoFabrica` já tem em mãos: é ela que decide
    se a cor entra como fundo cheio, contorno, rótulo ou círculo de ação
    (ver `_estilo_do_botao`). Sem ela, todas as variantes são pintadas igual e
    as que não têm fundo perdem a forma.

    Não mexe em cor de ESTADO (apagar, restaurar, aviso): o vermelho de
    "excluir" é o mesmo em qualquer estilo, e pintar esse botão de azul
    esconderia o que a ação faz. `BotaoFabrica` não chama esta função para
    elas, e o chamador que passa `cor=` também não.
    """
    if elemento is None:
        return None
    try:
        padrao = estilo_efetivo()
    except Exception:
        padrao = ""
    try:
        from mod_tisosdocfly.tema_modulo import ler_tema
        tema = ler_tema(chave_modulo) or {}
    except Exception:
        tema = {}
    # Cor do módulo só entra quando a pessoa NÃO escolheu estilo — aí quem
    # manda é o administrador, como manda em todo o resto da tela.
    if not padrao:
        admin = tema.get("cor_botao", "") or ""
        if admin:
            return elemento
    cor = cor_do_botao(padrao)
    try:
        elemento.style(_estilo_do_botao(cor, variante))
    except Exception:
        try:
            import logging
            logging.getLogger(__name__).exception(
                "preview_estilos: falha ao aplicar a cor no botão")
        except Exception:
            pass
    return elemento


def _request_atual():
    """Request HTTP da renderização, ou None se não houver.

    O NiceGUI 3 expone o request em `context.client.request` e removeu o
    `context.request` que existia no 2 — por isso a cadeia: o acesso novo
    primeiro, o antigo como reserva. Sem isso o cookie chegava como vazio e o
    usuário nunca tinha sua escolha aplicada (falha silenciosa, que é a pior
    delas: a tela abre, mas no estilo errado).
    """
    try:
        from nicegui import context
        req = getattr(context, "request", None)
        if req is None:
            req = getattr(getattr(context, "client", None), "request", None)
        return req
    except Exception:
        return None


def ler_estilo() -> str:
    """O estilo que este navegador impõe, já resolvidas as três camadas.

    Devolve uma chave de `CHAVES` — o estilo que manda na tela — ou "" quando a
    pessoa escolheu "Padrão", que é o único caso em que nenhum estilo está
    sendo imposto e quem manda na cor é o administrador do módulo (o
    `tema_modulo.ler_tema`).

    A distinção que faltava até 06/10/2026: cookie AUSENTE e cookie "Padrão"
    davam a mesma resposta. Agora são coisas diferentes, com efeitos diferentes:

        cookie = "azul" | "preto" | "roxo" | "verde"  ->  esse estilo
        cookie = "padrao"                             ->  "" (cor do admin)
        cookie ausente / desconhecido                ->  `padrao_do_sistema()`
                                                          (verde)

    Sem essa separação, um navegador novo caía na cor do administrador e o
    verde de entrega nunca aparecia para quem não tinha clicado em nada.
    """
    req = _request_atual()
    bruto = ""
    try:
        bruto = (req.cookies.get(COOKIE_ESTILO) or "").strip().lower() if req else ""
    except Exception:
        bruto = ""
    # "Padrão" é a ÚNICA coisa que devolve vazio: é a escolha explícita de não
    # impor estilo. Qualquer outro valor é um padrão, mesmo que venha de uma
    # versão antiga do menu, com chave que hoje não existe mais.
    if bruto == CHAVE_PADRAO:
        return ""
    if bruto in CHAVES:
        return bruto
    return padrao_do_sistema()


def escolha_pessoal() -> str:
    """O que a pessoa escolheu de fato: uma de `CHAVES`, `padrao`, ou "".

    Diferente de `ler_estilo`, que responde "o que vale AGORA", esta responde
    "o que está marcado no cookie". É o que o menu de estilo usa para acender a
    opção selecionada. Sem escolha nenhuma o menu acende **Padrão** — é o que a
    pessoa vê, e é para onde ela volta se quiser — e não o verde do sistema; senão
    o menu mentiria, mostrando "Verde" escolhido para quem nunca escolheu.
    """
    req = _request_atual()
    try:
        bruto = ((req.cookies.get(COOKIE_ESTILO) or "").strip().lower()
                 if req else "")
    except Exception:
        bruto = ""
    if bruto == CHAVE_PADRAO:
        return CHAVE_PADRAO
    return bruto if bruto in CHAVES else ""


def estilo_efetivo() -> str:
    """Estilo que vale AGORA, ou "" quando o usuário escolheu "Padrão".

    O vazio é uma resposta válida e importante: significa que NENHUM estilo está
    sendo imposto, e quem manda na cor é o administrador do módulo (o que o
    `tema_modulo.ler_tema` do próprio módulo devolve). Por isso o padrão do
    sistema NÃO é mais um estilo: ele é a configuração de cada módulo.
    """
    return ler_estilo()


def link_troca(chave: str, volta: str = "/") -> str:
    """URL que troca o estilo e devolve o usuário para onde ele estava.

    `volta` é o caminho da tela atual. O botão navega para cá, a rota grava o
    cookie e redireciona de volta — então o usuário troca o estilo sem perder a
    página em que estava, inclusive o módulo.
    """
    from urllib.parse import quote
    destino = volta or "/"
    if not destino.startswith("/"):
        destino = "/"
    return f"{ROTA_TROCA}/{chave}?volta={quote(destino, safe='')}"


def montar_rota_troca() -> bool:
    """Registra a rota que grava o cookie do estilo e volta para a tela.

    Uma rota HTTP de verdade (e não um evento do WebSocket) porque só uma
    resposta HTTP consegue mandar `Set-Cookie` para o navegador — num evento de
    socket não há resposta para anexar o cabeçalho. O redirecionamento é 303
    para não repetir o POST no destino. Chave fora da lista é ignorada e
    devolve o padrão, sem gravar nada.
    """
    try:
        from fastapi.responses import RedirectResponse
        from nicegui import app
        from urllib.parse import urlparse

        @app.get(ROTA_TROCA + "/{chave}")
        def trocar_estilo(chave: str, volta: str = "/"):
            """Grava a escolha de estilo no cookie deste navegador e volta."""
            # `padrao` e qualquer valor desconhecido viram "sem escolha
            # pessoal": o cookie guarda a intenção, e o estilo em vigor é
            # resolvido na renderização (padrão do administrador).
            if chave not in CHAVES:
                chave = CHAVE_PADRAO
            # Só aceita caminho interno: um `volta` externo aqui viraria um
            # redirecionamento aberto (o usuário cairia numa página controlada
            # por quem montou o link).
            alvo = urlparse(volta).path if volta.startswith("/") else "/"
            resp = RedirectResponse(url=alvo or "/", status_code=303)
            resp.set_cookie(
                COOKIE_ESTILO, chave, max_age=60 * 60 * 24 * 365,
                httponly=False, samesite="lax", path="/")
            return resp

        return True
    except Exception:
        try:
            import logging
            logging.getLogger(__name__).exception(
                "preview_estilos: rota de troca de estilo não foi registrada")
        except Exception:
            pass
        return False


def _caminho_atual() -> str:
    """Caminho da tela atual (a troca de estilo devolve o usuario para aqui)."""
    req = _request_atual()
    try:
        return (req.url.path if req else "") or "/"
    except Exception:
        return "/"


def barra_alternador(padrao: str, discreto: bool = False) -> None:
    """Barra de escolha de estilo, no rodape de TODAS as telas internas.

    Clicar em um estilo navega para a rota que grava o cookie do navegador e
    volta para a tela atual — de onde o usuario nao sai. E o que faz o padrao
    escolhido continuar valendo no proximo login, neste computador.

    Os botoes sao `ui.button` crus, e nao a fabrica `ui_comum.botao`, por um
    motivo concreto: a fabrica aplica `text-primary`/`bg-primary` do Quasar,
    que sao `!important` DENTRO de uma cascade layer — nenhuma regra nossa
    fora de camada os vence. Como aqui a cor e justamente a informacao
    (ativo x inativo), o controle tem de ser nosso.

    `discreto=True` deixa a barra menor — e o modo do rodapé, que é uma faixa
    baixa e não pode crescer. A barra NUNCA é posicionada de forma fixa: ela
    fica no fluxo, entre os itens que o rodapé ja tinha, para o padrao antigo
    do rodape (titulo a esquerda, versao a direita) continuar valendo.

    Falha registrada e silenciosa: o alternador e decoracao, nunca pode
    derrubar a tela em que ele esta.
    """
    # `padrao` recebido e o que esta EFETIVO na tela; o que marca o botao ativo
    # e a ESCOLHA do usuario (ver `escolha_pessoal`).
    #
    # 06/10/2026: antes era `ler_estilo() or CHAVE_PADRAO`, e com o verde de
    # entrega virando padrao do sistema isso passou a acender "Verde" para quem
    # NUNCA escolheu — o menu dizia que a pessoa tinha escolhido verde, o que
    # ela nao fez. `escolha_pessoal()` le o cookie cru, e sem cookie nenhum o
    # menu acende "Padrao", que e a verdade sobre a tela.
    escolhido = escolha_pessoal() or CHAVE_PADRAO
    try:
        from nicegui import ui
        classes = ["pe-alternador", "items-center", "justify-center", "flex-wrap",
                   "no-wrap"]
        with ui.row().classes(f"pe-{padrao} " + " ".join(classes)).style(
                "gap: .35rem" if discreto else "gap: .5rem"):
            ui.label("Estilo:").classes(
                "pe-alt-texto text-caption" if discreto else "pe-alt-texto text-body2")
            for p in tuple(PADROES) + (OPCAO_PADRAO,):
                chave = p["chave"]
                # Só o que o USUÁRIO escolheu é marcado como ativo. Quando ele
                # não escolheu, quem fica marcado é "Padrão" — mesmo que o
                # estilo em vigor por causa do administrador seja o verde, o
                # botão "Verde" não é dele, e fingir o contrário mentiria.
                ativo = chave == escolhido
                destino = link_troca(chave, _caminho_atual())
                props = "flat no-caps dense" + ("" if discreto else " size=sm")
                classes_alt = (
                    "pe-alt pe-alt--ativo"
                    if ativo else "pe-alt pe-alt--inativo"
                ) + (" text-caption" if discreto else " text-body2")
                with ui.button(
                        p["rotulo"],
                        on_click=lambda d=destino: ui.navigate.to(d),
                ).props(props).classes(classes_alt).props(
                        f'data-testid="estilo-{chave}"'):
                    ui.tooltip(
                        f"{p['rotulo']} - {p['descricao']}"
                        + (" (ativo)" if ativo else ""))
                    if not discreto and ativo:
                        ui.icon("check", size="16px").classes("q-mr-xs")
            # Rótulo do que está valendo. Sem estilo imposto não há nome de
            # estilo para mostrar, e a resposta útil é DE ONDE vem a cor: o
            # padrão é a cor que o administrador configurou no módulo.
            ui.label(ROTULOS.get(padrao) or "cor do módulo").props(
                'data-testid="estilo-atual"').classes(
                "pe-alt-texto text-caption q-px-sm")
    except Exception:
        try:
            import logging
            logging.getLogger(__name__).exception(
                "preview_estilos: alternador nao pode ser montado")
        except Exception:
            pass


def barra_home(padrao: str, url_base: str = "/", paleta: dict = None) -> None:
    """Barra de escolha de estilo na Home (assinatura antiga do prototipo)."""
    barra_alternador(padrao, discreto=False)


def resumo_padroes() -> str:
    """Uma linha com os 4 padrões — usado em relatório de QA."""
    return " | ".join(f"{p['rotulo']} ({p['chave']})" for p in PADROES)
