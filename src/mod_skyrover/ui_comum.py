"""Central factory for shared UI components (buttons, dialogs, footers).

Fábrica central de componentes de UI compartilhados por todas as telas:
paleta semântica de cores (`CORES`), fábrica de botões (`BotaoFabrica` +
`botao`/`botao_icone`), moldura de diálogo (`Dialogo` + `dialogo_card`),
base de DIÁLOGO DE FORMULÁRIO (`dialogo_formulario` +
`LARGURA_DIALOGO_FORMULARIO`/`CSS_GRADE_CAMPOS`/`CSS_GRADE_AVISOS`),
rodapés (`rodape_dialogo`, `rodape_salvar_restaurar`), campos de
configuração (`CampoBase`/`CampoCor`/`CampoTexto`/`CampoSelecao` +
`campo_cor`/`campo_texto`/`campo_selecao`) e card de configuração
(`Cartao` + `card_config`). As FUNÇÕES são wrappers finos que delegam às
CLASSES correspondentes — assinaturas e saída preservadas byte-identicamente
para as centenas de chamadas existentes; código novo pode usar as classes
diretamente. Unifica `tema_modulo.botao` (variantes de tema) com as
variantes fixas do painel de configurações, para que o mesmo dado tenha a
mesma aparência em qualquer lugar.

É o padrão oficial de componentes para os módulos `mod_*`: importe de
`mod_skyrover.ui_comum` em vez de criar `ui.button` crus ou repetir hexes
soltos (`#C62828`, `#EF6C00`, `#2E7D32`…) nas telas.
"""
import sys
import os
from contextlib import contextmanager, ExitStack

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from mod_skyrover.tema_modulo import notificar


def _log():
    """Returns the loguru logger bound to the core module ("skyrover").

    Logger loguru vinculado ao módulo núcleo (`skyrover`), no padrão
    `observabilidade._FMT` (`{module}:{function}:{line}`). Usado nos blocos
    `except` das fábricas de UI para registrar falhas sem derrubar a
    renderização da tela (fail-soft).
    """
    from mod_skyrover import observabilidade
    return observabilidade.get_logger("skyrover")


# Paleta semântica única do sistema: use `CORES["perigo"]`, `CORES["alerta"]`
# etc. em vez de hexes soltos repetidos nas telas (ver docs/convencoes_codigo).
CORES = {
    # Valores de RESERVA, os mesmos de antes da experiência de estilo visual.
    # O que vale mesmo é o que o administrador gravou em tb_config
    # (`cor_principal`/`cor_fundo` e as chaves por módulo), lidos a cada
    # renderização. O menu de estilo NÃO mexe nisto: quem escolhe "Padrão" está
    # justamente dizendo "usa a cor do meu módulo, como está".
    "primaria": "#1565C0",
    "sucesso": "#2E7D32",
    "alerta": "#EF6C00",
    "perigo": "#C62828",
    "info": "#00838F",
    "neutro": "#455A64",
    "destaque": "#6A1B9A",
    "cinza_escuro": "#37474F",
    "titulo": "#212121",
    "branco": "#FFFFFF",
    "fundo": "#EEEEEE",
}


class BotaoFabrica:
    """Factory of standardized buttons (module theme or fixed variant).

    Fábrica de botões padronizados: encapsula a leitura do tema do módulo
    (`tema_modulo.ler_tema`) e a montagem de props/classes/estilo por
    variante — `primario` (alias `solido`), `secundario` (alias
    `contorno`), `texto` e `icone` usam o tema; `neutro`, `restaurar`,
    `restaurar_fill`, `perigo`, `icone_branco` e `texto_branco` são 100%
    props fixas (o tema NÃO é lido para elas — economia de consultas por
    render). Com `cor` informado, o tema também NÃO é lido nem para as
    variantes tematizadas (nenhuma saída o utiliza: estilo limpo, sem
    `btn_cls`, cor via props `color=`). `cor` sobrescreve a cor da
    variante mantendo formato/tamanho; `extra_classes` soma classes;
    `compacto=True` remove `size=md`, `btn_cls` e sombra (visual de rodapé
    de diálogo). `no_caps=False` remove o token `no-caps` (para módulos
    com botões UPPERCASE herdados do Quasar). Variante
    inválida levanta `ValueError` (erro de programação — falha rápida
    intencional). Falha ao ler o tema registra warning no loguru e usa os
    padrões; falha ao montar o elemento registra exception e retorna
    `None` (fail-soft).
    """

    ALIAS = {"solido": "primario", "contorno": "secundario"}
    TEMATIZADAS = ("primario", "secundario", "texto", "icone")

    def __init__(self, chave_modulo="skyrover"):
        self.chave_modulo = chave_modulo

    def criar(self, rotulo=None, *, variante="primario", icone=None,
              on_click=None, tooltip=None, cor=None, extra_classes="",
              compacto=False, no_caps=True):
        """Builds one standardized button; returns the `ui.button` (or `None`).

        Aplica a sequência fixa de montagem: props da variante → estilo do
        tema (quando aplicável) → classes (`size`, sombra,
        `extra_classes`) → tooltip. Com `cor`, sobrescreve `color=`/
        `text-color=` nas props e zera o estilo. Retorna o `ui.button`
        criado ou `None` em falha de montagem (fail-soft).
        """
        from nicegui import ui
        from mod_skyrover import tema_modulo
        v = self.ALIAS.get(variante, variante)
        if v in self.TEMATIZADAS and not cor:
            try:
                tema = tema_modulo.ler_tema(self.chave_modulo)
            except Exception as e:
                _log().warning(f"botao: tema indisponível para "
                               f"'{self.chave_modulo}', usando padrões: {e}")
                tema = {}
            cor_tema = tema.get("cor_botao", "#1565C0") or "#1565C0"
            txt_tema = tema.get("cor_texto_botao", "#FFFFFF") or "#FFFFFF"
            tamanho = tema.get("btn_tamanho", "medium") or "medium"
        else:
            tema, cor_tema, txt_tema, tamanho = {}, "", "", "medium"
        if v == "primario":
            if compacto:
                props, classes = "unelevated no-caps", ""
            else:
                props, classes = "unelevated no-caps size=md", "shadow-sm"
            estilo = tema_modulo.btn_style(cor_tema, txt_tema)
            if not compacto and not cor:
                classes = f"{classes} {tema_modulo.btn_cls(tamanho)}"
        elif v == "secundario":
            props, classes = "outline no-caps", ""
            estilo = f"color:{cor_tema};border-color:{cor_tema};"
        elif v == "texto":
            props, classes = "flat no-caps", ""
            estilo = f"color:{cor_tema};"
        elif v == "neutro":
            props, classes, estilo = \
                "flat no-caps size=md text-color=grey-8", "", ""
        elif v == "restaurar":
            props, classes, estilo = (
                "outline no-caps size=md color=warning text-color=amber-10",
                "", "")
        elif v == "restaurar_fill":
            props, classes, estilo = (
                "unelevated no-caps size=md color=warning text-color=white",
                "shadow-sm", "")
        elif v == "perigo":
            props, classes, estilo = (
                "outline no-caps size=md color=negative text-color=negative",
                "", "")
        elif v == "icone":
            props, classes = "flat round dense size=sm", ""
            estilo = f"color:{cor_tema};"
        elif v == "icone_branco":
            props, classes, estilo = "flat round color=white", "", ""
        elif v == "texto_branco":
            props, classes, estilo = "flat dense color=white no-caps", "", ""
        else:
            raise ValueError(f"variante de botão inválida: {variante!r}")
        if not no_caps:
            props = " ".join(p for p in props.split() if p != "no-caps")
        classes = f"{classes} {extra_classes}".strip()
        if cor:
            partes = props.split()
            props = " ".join(
                f"color={cor}" if p.startswith("color=") else
                f"text-color={cor}" if p.startswith("text-color=") else p
                for p in partes)
            if not any(p.startswith("color=") for p in partes):
                props += f" color={cor}"
            estilo = ""
        try:
            btn = ui.button(rotulo, icon=icone, on_click=on_click).props(props)
            if estilo:
                btn.style(estilo)
            if classes:
                btn.classes(classes)
            if tooltip:
                btn.tooltip(tooltip)
            # A ESCOLHA DA PESSOA por último, e só nas variantes TEMATIZADAS.
            #
            # `aplicar_no_botao` precisa vir depois do `.style()` acima:
            # estilo inline vence CSS, então escrever a cor antes seria
            # sobrescrito na sequência. Nas variantes de ESTADO
            # (`neutro`, `restaurar`, `restaurar_fill`, `perigo`,
            # `icone_branco`, `texto_branco`) e quando `cor=` foi informado
            # pelo chamador, não se mexe: vermelho de "excluir" é vermelho em
            # qualquer estilo, e uma cor explícita é decisão de quem chamou.
            #
            # A `v` vai junto porque é ela que diz COMO a cor entra: fundo
            # cheio no primário, contorno no secundário, círculo translúcido
            # no ícone-sozinho. Sem a variante, a cor entrava igual em todas e
            # apagava a forma das que não têm fundo.
            if v in self.TEMATIZADAS and not cor:
                try:
                    from mod_skyrover import preview_estilos
                    preview_estilos.aplicar_no_botao(
                        btn, chave_modulo=self.chave_modulo, variante=v)
                except Exception:
                    _log().warning(f"botao: estilo visual indisponível para "
                                   f"'{self.chave_modulo}', mantendo cor do "
                                   f"módulo")
            return btn
        except Exception as e:
            _log().exception(f"botao: falha ao montar botão {rotulo!r} "
                             f"(variante={variante!r}): {e}")
            return None


def botao(rotulo=None, *, variante="primario", icone=None, on_click=None,
          tooltip=None, cor=None, chave_modulo="skyrover", extra_classes="",
          compacto=False, no_caps=True):
    """Builds the single standardized button (delegates to `BotaoFabrica`).

    Wrapper fino da classe `BotaoFabrica` — assinatura e saída idênticas à
    original. Fábrica única de botões: lê o tema do módulo
    (`tema_modulo.ler_tema`) e aplica props/classes/estilo por variante
    (`primario`/`secundario`/`texto`/`icone` tematizadas; `neutro`,
    `restaurar`, `restaurar_fill`, `perigo`, `icone_branco` e
    `texto_branco` com props fixas). Com `cor` informado, o tema não é
    lido e `cor` sobrescreve a variante mantendo formato/tamanho;
    `extra_classes` soma classes; `compacto=True` produz o visual de
    rodapé de diálogo; `no_caps=False` remove o token `no-caps` (módulos
    UPPERCASE, ex. edit_pdf). Variante inválida levanta `ValueError`;
    falha de tema registra warning e usa os padrões; falha de montagem
    registra exception e retorna `None` (fail-soft). Retorna o `ui.button`
    criado.
    """
    return BotaoFabrica(chave_modulo).criar(
        rotulo, variante=variante, icone=icone, on_click=on_click,
        tooltip=tooltip, cor=cor, extra_classes=extra_classes,
        compacto=compacto, no_caps=no_caps)


def botao_icone(icone, on_click=None, *, variante="icone", cor=None,
                tooltip=None, chave_modulo="skyrover", extra_classes=""):
    """Icon-only row-action button (themed or white header variants).

    Atalho para `botao(icone=..., variante=variante, ...)`: o padrão
    `variante="icone"` (`flat round dense size=sm` na cor do tema) serve às
    ações de linha de tabela (mover, excluir, abrir); `variante="icone_branco"`
    (`flat round color=white`) serve aos botões do header sobre fundo
    primário. `cor` sobrescreve a cor do tema mantendo o formato. Falhas são
    registradas no loguru e retornam `None` (fail-soft); retorna o
    `ui.button` criado.
    """
    try:
        return botao(None, variante=variante, icone=icone, on_click=on_click,
                     cor=cor, tooltip=tooltip, chave_modulo=chave_modulo,
                     extra_classes=extra_classes)
    except Exception as e:
        _log().exception(f"botao_icone: falha ao criar ação de linha "
                         f"(ícone={icone!r}): {e}")
        return None


class Dialogo:
    """Standard dialog + themed card as a context-manager class.

    Classe gerenciadora de contexto que replica `dialogo_card`: abre
    `ui.dialog` + `ui.card` via `ExitStack` (o escopo do card permanece
    aberto até `__exit__` — o conteúdo criado após o `__enter__` nasce
    dentro do card), aplica largura `largura`, altura máxima 90vh quando
    `max_altura` e o estilo de cartão do módulo
    (`tema_modulo.estilo_cartao`, fail-soft); com `titulo`, cria o rótulo
    `text-h6` e um separador. Expõe ainda `abrir()`/`fechar()`. O contexto
    devolve `(dlg, card)`, como o wrapper funcional.
    """

    def __init__(self, titulo="", largura="w-[560px]", *,
                 chave_modulo="skyrover", max_altura=True, sem_separador=False):
        self.titulo = titulo
        self.largura = largura
        self.chave_modulo = chave_modulo
        self.max_altura = max_altura
        # O separador é o padrão há anos, mas o diálogo de troca obrigatória
        # usa título sem divisória (30/09/2026) para não mudar o visual que já
        # era o dele. Precisou virar opção porque `Dialogo.__enter__` roda
        # ANTES de `dialogo_formulario` criar o `miolo` — então o título sai no
        # TOPO do cartão, e o chamador não tem como repor esse lugar depois:
        # tudo que ele cria nasce depois do `miolo` (ver docstring do
        # `dialogo_formulario`).
        self.sem_separador = sem_separador
        self.dlg = None
        self.card = None
        self._stack = None

    def __enter__(self):
        """Enters dialog + card contexts; returns `(dlg, card)`.

        Sequência de criação idêntica à de `dialogo_card`: dialog → card →
        classes (largura + `max-h-[90vh]`) → estilo do tema (fail-soft) →
        título/separador. Mantém os contextos abertos via `ExitStack`
        até `__exit__`.
        """
        from nicegui import ui
        from mod_skyrover import tema_modulo
        self._stack = ExitStack()
        dlg = self._stack.enter_context(ui.dialog())
        card = self._stack.enter_context(ui.card())
        card.classes(f"{self.largura}{' max-h-[90vh]' if self.max_altura else ''}")
        try:
            estilo = tema_modulo.estilo_cartao(self.chave_modulo)
        except Exception as e:
            _log().warning(f"dialogo_card: estilo de cartão indisponível "
                           f"para '{self.chave_modulo}': {e}")
            estilo = ""
        if estilo:
            card.style(estilo)
        if self.titulo:
            ui.label(self.titulo).classes("text-h6")
            if not self.sem_separador:
                ui.separator()
        self.dlg, self.card = dlg, card
        return dlg, card

    def __exit__(self, *exc):
        """Closes the card and dialog contexts (reverse order)."""
        stack, self._stack = self._stack, None
        if stack:
            stack.close()
        return False

    def abrir(self):
        """Opens the dialog (no-op quando o contexto ainda não entrou)."""
        if self.dlg is not None:
            self.dlg.open()

    def fechar(self):
        """Closes the dialog (no-op quando o contexto ainda não entrou)."""
        if self.dlg is not None:
            self.dlg.close()


@contextmanager
def dialogo_card(titulo="", largura="w-[560px]", *, chave_modulo="skyrover",
                 max_altura=True):
    """Opens a standard dialog + themed card (delegates to `Dialogo`).

    Wrapper fino da classe `Dialogo` — assinatura e saída idênticas à
    original. Abre `ui.dialog` + `ui.card` padronizados: largura `largura`,
    altura máxima de 90vh quando `max_altura` e estilo de cartão do módulo
    (`tema_modulo.estilo_cartao`). Com `titulo`, cria o rótulo `text-h6` e
    um separador. Falha ao ler o estilo do cartão registra warning no loguru
    e segue sem estilo (fail-soft). Faz `yield (dlg, card)`.
    """
    dialogo = Dialogo(titulo, largura, chave_modulo=chave_modulo,
                      max_altura=max_altura)
    with dialogo as (dlg, card):
        yield dlg, card


# ============ DIÁLOGO DE FORMULÁRIO: LARGURA, ALTURA E ROLAGEM ============
#
# O `Dialogo`/`dialogo_card` acima resolve o CASCO GERAL: um cartão de
# largura fixa com o conteúdo do tamanho que ele tiver. Ele serve para
# confirmação ("excluir?") e para campos poucos. O que ele NÃO serve é para o
# outro tipo de diálogo da skyrover: o FORMULÁRIO, que tem vários campos, dois
# ou três blocos informativos e um botão no pé.
#
# O sintoma desse segundo tipo, sem tratamento, é sempre o mesmo: cartão
# estreito (380–620px), conteúdo mais alto que a janela e o `max-h` ausente —
# então quem rola é a PÁGINA INTEIRA, e a barra de rolagem aparece no meio do
# formulário, longe do dedo de quem está num monitor de altura curta.
#
# A correção é sempre a mesma e por isso mora aqui, num lugar só:
#   largura  -> pelo menos 80% da viewport, com teto para não esticar em
#               monitor ultrawide (88vw / 1600px);
#   altura   -> teto de 90vh com o CONTEÚDO rolando por dentro do cartão, e o
#               `min-h-0` que é o que permite ao filho flex encolher abaixo da
#               altura do conteúdo — sem ele o `overflow-y` não pega e o teto é
#               simplesmente ignorado;
#   grade    -> `auto-fit` + `minmax`, que dispensa media query: cai sozinha
#               para uma coluna no celular e preenche as colunas no monitor.
#
# Não é 'responsividade' no sentido degrades de breakpoint: é o conteúdo
# deixar deldrastar a janela e passar a caber nela.

LARGURA_DIALOGO_FORMULARIO = "w-[88vw] max-w-[1600px]"

# Diálogo de TEXTO LONGO: o aceite de risco, a confirmação dupla, avisos
# jurídicos. Aqui o problema é o oposto do formulário de campos — o conteúdo é
# uma coluna de prosa, e `88vw` transformava cada parágrafo em uma linha de 15
# palavras, com o resto da largura vazio e rolagem horizontal para o texto
# longo (30/09/2026). Ler um termo de responsabilidade em linha de 1.400px é
# exatamente o contrário de ler.
#
# 760px é a medida de leitura que o responsável pediu: 640px já resolvia o
# estouro, mas sobrava aperto para o texto da LGPD, que é longo. 760px continua
# dentro da faixa confortável (45-75 caracteres) e dá espaço para o termo de
# responsabilidade sem esticar a linha. `92vw` continua no mobile, onde não
# há largura sobrando.
LARGURA_DIALOGO_TEXTO = "w-[92vw] max-w-[760px]"

# ============================================================================
# LARGURA DOS CAMPOS — 40 a 60 caracteres, 1/2/3 colunas conforme a tela
# ============================================================================
# Pedido do responsável (02/10/2026): cada campo deve ter CAPACIDADE DE EXIBIÇÃO
# entre 40 e 60 caracteres, e a quantidade de colunas acompanha a tela —
# 3 em tela grande, 2 em tela intermediária, 1 em celular.
#
# POR QUE `ch` E NÃO PIXEL. `ch` é a largura do glifo "0" da fonte do elemento,
# então 60ch é literalmente "cerca de 60 caracteres" — e o campo acompanha o
# tamanho da fonte, que é o que "ajustável conforme a tela" pede. Um `max-width`
# em pixel daria 60 caracteres na fonte padrão e 45 numa fonte maior, e ninguém
# perceberia até o texto cortado.
#
# POR QUE AS COLUNAS SÃO EXPLICITAS E NÃO `auto-fit`. `auto-fit` com mínimo de
# 40ch (~320px) caberia 4 colunas num cartão de 1600px, e o pedido é no máximo
# 3. Dá para tentar zerar com `auto-fit` + `max-width` no cartão, mas só
# estreitando o mínimo para ~44ch ou o teto para ~50ch — números mágicos que
# dependem da razão `ch`/fonte e quebram com a primeira troca de tipografia. Com
# `@media` a regra é o que foi pedida, escrita de forma legível, e ajustar
# depois é trocar dois números.
#
# POR QUE O `min(40ch, 100%)` NO MÍNIMO. Abaixo de 40ch disponível, a coluna
# usa a largura toda em vez de forçar barra horizontal — o `min()` impede a
# trilha de estourar a grade em tela estreita, que é exatamente o modo de falha
# que o `flex-wrap` do cartão causava.
#
# 40ch (~320px) cobre o requisito do telefone: DDI de 190px fixos + número
# precisam de ~300px de célula, senão o número vira um palito (ver o comentário
# de `telefone.py`). Com o teto de 60ch sobram ~290px para o número, que é
# confortável.
CSS_GRADE_CAMPOS = "display: grid; gap: 1rem; align-items: start;"

CSS_GRADE_CAMPOS_CELL = "min-width: 0;"

# A parte responsiva PRECISA de `@media`, e `@media` não vale em atributo
# `style` — só em folha de estilo. Por isso este bloco é injetado no `<head>`
# da página uma vez por cliente (ver `_injetar_css_grade_campos`), em vez de
# virar mais uma entrada de `CSS_GRADE_CAMPOS`.
CSS_GRADE_CAMPOS_HEAD = """<style>
/* Campos de formulário: 40-60 caracteres, 1/2/3 colunas conforme a tela.
   Substitui o antigo `auto-fit minmax(300px, 100%)`, que esticava cada campo
   para a largura inteira do diálogo (~1500px para um nome de 8 letras).

   `grid-template-columns` NÃO pode estar no atributo `style` inline: atributo
   `style` vence QUALQUER seletor de classe, então as regras de `@media` abaixo
   perderiam para ele e a resposta à largura jamais apareceria. Por isso a coluna
   vive só nesta folha; o inline (`CSS_GRADE_CAMPOS`) fica com o que não muda. */
.grade-campos { grid-template-columns: minmax(min(40ch, 100%), 60ch); }
@media (min-width: 900px) {
  .grade-campos { grid-template-columns: repeat(2, minmax(min(40ch, 100%), 60ch)); }
}
@media (min-width: 1400px) {
  .grade-campos { grid-template-columns: repeat(3, minmax(min(40ch, 100%), 60ch)); }
}

/* Cartões de acesso por cargo: 3 por linha na tela grande, 2 na intermediária,
   1 na pequena (empilhados). `minmax(0, 1fr)` e não `1fr` puro: o segundo
   precisa poder encolher abaixo do min-content do nome do módulo, senão a
   coluna cresce até o nome mais longo e os cartões estouram o diálogo — o
   mesmo mecanismo que o `flex-wrap` do cartão usava. */
.grade-cartoes { display: grid; gap: 0.75rem;
                 grid-template-columns: minmax(0, 1fr); }
@media (min-width: 900px) {
  .grade-cartoes { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (min-width: 1400px) {
  .grade-cartoes { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

</style>"""


def _injetar_css_grade_campos():
    """Injeta `CSS_GRADE_CAMPOS_HEAD` uma vez por cliente.

    `ui.add_head_html` não deduplica: chamar a cada diálogo abriria uma cópia
    do bloco por abertura. O guarda é o armazenamento de CLIENTE do NiceGUI
    (`app.storage.client`), que é por navegador — então a primeira janela paga
    a injeção, as seguintes não, e cada cliente novo recebe o CSS. Um guarda de
    módulo (flag global) daria o resultado oposto: a segunda janela de outro
    navegador abriria um diálogo sem estilo nenhum.

    Falha aqui não pode derrubar o diálogo: se o `add_head_html` falhar, os
    campos caem no `CSS_GRADE_CAMPOS` inline (coluna única de 40-60ch), que é
    funcional — perde-se a resposta à largura, não a leitura dos campos.
    """
    try:
        from nicegui import app
        if app.storage.client.get("_grade_campos_css"):
            return
    except Exception:
        pass
    try:
        from nicegui import ui
        ui.add_head_html(CSS_GRADE_CAMPOS_HEAD)
    except Exception as e:
        _log().warning(f"grade-campos: CSS responsivo não injetado: {e}")
        return
    try:
        from nicegui import app
        app.storage.client["_grade_campos_css"] = True
    except Exception:
        pass


# Blocos informativos são texto corrido, não campo: 320px evita que fiquem
# espremidos ao lado das três colunas do formulário.
#
# O `min(320px, 100%)` é o que impede o transbordo horizontal (04/10/2026).
# Com `minmax(320px, 1fr)` puro, a coluna tem 320px de piso SEMPRE — e numa
# janela mais estreita que isso, a grade fica mais larga que o cartão que a
# contém. Foi o que mediatei na troca de credenciais do `master`: o cartão
# tinha 342px de cliente e a grade 320px de piso mais o `gap`, o conteúdo
# inteiro nascia fora da janela e aparecia cortado, com barra horizontal.
# `min(320px, 100%)` deixa a coluna escolher o piso entre 320px e a largura
# disponível, que é a mesma ideia do `.grade-campos` logo acima.
CSS_GRADE_AVISOS = ("display: grid; grid-template-columns: "
                    "repeat(auto-fit, minmax(min(320px, 100%), 1fr)); "
                    "gap: 1rem; align-items: start;")


@contextmanager
def dialogo_formulario(titulo="", *, chave_modulo="skyrover", largura=None,
                       descricao="", sem_descricao=False, sem_separador=False,
                       largura_texto=False):
    """Abre um diálogo de FORMULÁRIO largo, com teto de altura e rolagem interna.

    Mesma moldura do `dialogo_card`, com o esqueleto que resolve o formulário
    que estoura a janela: o cartão vira coluna flex, e o miolo — criado aqui
    entre o cabeçalho e o rodapé — é a ÚNICA parte que rola. Título fica
    parado em cima, os botões que o chamador criar depois do `with` ficam
    parados embaixo, e o formulário some no meio.

    Devolve `(dlg, card, miolo, grade)`:
      - `dlg`/`card`  como em `dialogo_card`;
      - `miolo`        coluna rolável (`flex-1 min-h-0 overflow-y-auto`) —
                       tudo que for criado DENTRO dela rola;
      - `grade`        div com `CSS_GRADE_CAMPOS`, pronta para receber os
                       campos lado a lado. Para diálogos cujo corpo é lista ou
                       tabela, basta ignorar `grade` e criar o que for preciso
                       direto dentro de `miolo`.

    Os dois slots de contexto (`miolo` e `grade`) saem ANTES do `yield` de
    propósito: quem chama abre `with grade:` ou `with miolo:` para pôr os
    campos, e ao sair deles o slot corrente volta a ser o CARD — que é onde o
    rodapé (`rodape_dialogo`, botão "Salvar") tem de nascer, ancorado na base e
    fora da área rolável. Com o `yield` dentro de `with grade:`, o rodapé do
    chamador cairia dentro de uma célula da grade e rolaria junto com o
    formulário.

    `descricao` cria um parágrafo abaixo do título, do mesmo modo do diálogo de
    troca de credenciais; `sem_descricao=True` dispensa. `largura` sobrescreve
    `LARGURA_DIALOGO_FORMULARIO` quando um diálogo specifico precisar de outro
    teto (padrão: usar o padrão).

    `titulo` e `descricao` saem ACIMA do `miolo`, e isso é a diferença entre um
    diálogo com cabeçalho e um sem: o `yield` deste gerador vem DEPOIS do
    `miolo`, então um título que o chamador cria por conta própria aparece
    embaixo dos campos. Quem precisa de título no topo passa o texto por
    aqui — e `sem_separador=True` quando o diálogo de origem não tinha
    divisória sob o título.

    EN: Opens a wide, height-capped, internally scrollable FORM dialog. Same
        frame as `dialogo_card` plus the flex-column skeleton that stops the
        form from overflowing the window.
    """
    from nicegui import ui
    try:
        with Dialogo(
                    titulo,
                    largura or (LARGURA_DIALOGO_TEXTO if largura_texto
                                else LARGURA_DIALOGO_FORMULARIO),
                    chave_modulo=chave_modulo, max_altura=True,
                    sem_separador=sem_separador) as (dlg, card):
            # O `max-h-[90vh]` vem do `max_altura=True` acima. O `flex flex-col`
            # é o que transforma o cartão em coluna para o miolo poder dividir
            # a altura com o que estiver fora dele.
            # O `flex-wrap` do card precisa ser `nowrap`, e vem por ESTILO INLINE
            # (02/10/2026) — e não por classe utilitária do Tailwind.
            # Este é o defeito que empurrava o formulário para fora do diálogo
            # em TODO diálogo de formulário — Novo usuário, Editar, Duplicar,
            # os de Empenho/Estoque/Técnico/Lista telefônica e o de backup.
            #
            # O card é `display:flex` com `flex-direction: column` e `max-h-[90vh]`.
            # Quem impõe `flex-wrap: wrap` nele não é nenhuma folha de estilo
            # legível do documento (medido no navegador: nenhuma regra acessível
            # declara `flex-wrap` nem `flex-flow`, e o valor computado é `wrap`),
            # então a origem é opaca e não vale a pena caçá-la. O efeito é o
            # pior possível para esta disposição: em coluna COM wrap, quando o
            # conteúdo não cabe na ALTURA, o navegador cria uma NOVA LINHA — que
            # numa coluna é uma NOVA COLUNA À DIREITA. O `miolo` (altura
            # `flex-1`, o miolo rolável inteiro) saía do cartão, e o cartão
            # ganhava barra de rolagem horizontal: medido, `card.scrollWidth`
            # 952px num card de 484px, com o `miolo` em `x=510` em vez de `x=42`.
            # Com `nowrap`, o mesmo diálogo mede `scrollWidth` 484px e o `miolo`
            # volta para `x=42`.
            #
            # POR QUE INLINE E NÃO `flex-nowrap`: utilitário do Tailwind só é
            # gerado se o JIT varrer o fonte e encontrar a classe. Se a varredura
            # não rodar (cache, build parcial, classe nova no mesmo dia), a
            # classe simplesmente não existe e o defeito volta mudo — que é
            # exatamente o modo de falha que ninguém percebe. Estilo inline não
            # depende de build.
            card.classes("flex flex-col")
            card.style("flex-wrap: nowrap")
            if descricao and not sem_descricao:
                ui.label(descricao).classes("text-body2 text-grey-7")
            try:
                # `min-w-0` é comportamento correto de item flex: o card é
                # `flex flex-col`, e item flex vem com `min-width: auto`, ou
                # seja, se recusa a encolher abaixo do min-content dos filhos.
                #
                # NÃO há `overflow-x: hidden` aqui, e a omissão é deliberada:
                # o `miolo` também recebe lista e TABELA (os diálogos de
                # convite do Estoque e de arquivos do Técnico), que podem ser
                # legitimamente mais largos que o cartão. Esconder o transbordo
                # não conserta layout — esconde — e ainda cortaria conteúdo que
                # antes rolava. A barra horizontal que abria o bug era do
                # CARTÃO, por causa do `flex-wrap`, não do `miolo`.
                miolo = ui.column().classes("w-full min-w-0 flex-1 min-h-0 overflow-y-auto")
                miolo.props('role="region" tabindex="0" '
                            'aria-label="Conteúdo do formulário"')
                with miolo:
                    # `grade-campos` é o que traz `grid-template-columns` nas
                    # três faixas de largura; o `style` inline só carrega o
                    # esqueleto (`display:grid`, gap, alinhamento). A folha
                    # precisa estar na página ANTES de a classe valer, por isso
                    # a injeção acontece aqui — uma vez por cliente.
                    _injetar_css_grade_campos()
                    grade = ui.element("div").classes(
                        "w-full grade-campos").style(CSS_GRADE_CAMPOS)
                    grade.props('role="group" aria-label="Campos do formulário"')
                # Fora de `with miolo` e `with grade`: o `yield` acontece com o
                # slot corrente já no card, para o rodapé do chamador ancorar na
                # base em vez de virar célula da grade.
                yield dlg, card, miolo, grade
            except Exception as e:
                _log().error(f"dialogo_formulario: falha ao montar o miolo de "
                             f"'{titulo or chave_modulo}': {e}")
                raise
    except Exception as e:
        _log().error(f"dialogo_formulario: falha ao abrir '{titulo or chave_modulo}': {e}")
        raise


@contextmanager
def formulario_na_tela(*, gap="1rem",
                       max_altura="max(200px, calc(100vh - 25rem))",
                       rotulo="Conteúdo do formulário"):
    """Formulário montado no SLOT CORRENTE — sem cartão e sem diálogo.

    Devolve `(miolo, grade)` com o mesmo contrato de `dialogo_formulario`, e
    é por isso que existe: a troca de senha deixou de ser um modal e passou a
    ser a PRÓPRIA tela de login (`preview_estilos.tela_login` monta o
    invólucro e chama um callback). Um diálogo dentro dessa tela seria um
    cartão por cima de outra coisa — exatamente o que se queria tirar.

    Não cria moldura nenhuma. O que o chamador cria depois de sair de
    `with miolo:`/`with grade:` nasce no mesmo lugar do `miolo` (irmão, logo
    ABAIXO dele), que é o rodapé de tela cheia: o botão de salvar fica preso
    embaixo e o formulário some no meio, em vez de a rolagem levar o botão
    embora.

    `max_altura` é o teto do miolo, não o da tela: a coluna cresce até ele e a
    partir daí rola por dentro. Sem teto, o termo de responsabilidade empurra
    o rodapé para fora da janela e a pessoa precisa rolar a página inteira
    para achar "Salvar" — e a rolagem da página também leva embora o
    cabeçalho do login.

    O `min-height: 0` (04/10/2026) é o que FAZ esse teto valer, e ele só
    apareceu quando o formulário do `master` ficou mais alto que a janela.
    Item de flex em coluna tem `min-height: auto`, que vale a altura do
    conteúdo: o `max-height` era declarado e ignorado, o miolo crescia até
    1.127px dentro de uma janela de 900px, e quem rolava era a PÁGINA, não o
    miolo. É o mesmo `min-h-0` que o diálogo antigo já carregava: sem ele,
    nenhum teto de altura encolhe um filho flex.

    O TETO É DERIVADO, NÃO CHUTADO (04/10/2026). Era `72vh`, e esse número
    estava errado por construção: uma fração da JANELA não é o que sobra
    para o formulário, que é a janela MENOS o chassi — o respiro da tela, o
    padding da caixa, o cabeçalho, a dica verde, o rodapé e os gaps.

    E O CHASSI MEDE O QUE A TELA ESTÁ USANDO, não uma constante com a idade
    dela. E a tela mudou DUAS vezes no mesmo dia, o que é a prova de que
    este número não pode ser uma constante de verdade:

      - com o cartão mostrando cabeçalho e rodapé, medido em cinco tamanhos,
        o chassi deu 508 a 526px → primeiro `34rem`;
      - dispensados o cabeçalho e o rodapé na tela do `master` (o nome do
        produto já está no painel teal, e a dica verde assumiu o texto
        institucional), caiu para 276 a 290px → `20rem`. Um `34rem` teria
        deixado 254px de slack: o formulário ficaria com 356px quando cabem
        580px;
      - com a linha dos botões "Apagar" abaixo do "Salvar"/"Sair" e os
        rótulos quebrando em tela estreita, voltou para 342 a 392px →
        `25rem`.

    Três medições, três números, no mesmo dia. A lição que fica: **este
    valor descreve a tela, então precisa ser remedido sempre que a moldura
    mudar** — e o sintoma de que está velho é a página voltar a rolar.

    O PISO DE 200px é o outro lado da mesma conta. Sem ele o `calc` vira
    opressor em janela baixa: medido, um chassi de 544px deixava 156px de
    formulário em 1440x700 e **96px** em 360x640 — cabiam três linhas do
    bloco azul e NENHUM dos sete campos, com a rolagem interna funcionando e
    não servindo para nada. Abaixo de certa altura não há espaço para duas
    coisas ao mesmo tempo: formulário usável E página parada. O piso escolhe o
    formulário: o miolo nunca fica com menos de 200px, e a PÁGINA volta a
    rolar nesse trecho — que é o mal menor, porque rolagem de página é o
    comportamento de sempre e rolagem de 96px não é rolagem.

    O PISO FOI DE 300px PARA 200px, e a medição disse por quê (04/10/2026): a
    300px ele era o gargalo, e não a subtração. Na tela dos outros usuários,
    com 494 a 521px de chassi, o teto de `33rem` pedia 272px em 1280x800 — e o
    piso segurava em 300, de modo que a página ia a 817px numa janela de 800.
    Onde o piso morde, ele anula o próprio `calc` que existe para acertar a
    altura. 200px continua muito acima do caso de 96px que motivou o piso, e
    devolve os 100px.

    Onde nem o piso nem a subtração atrapalham, a página não rola: medido nas
    DUAS telas (credenciais do `master` e troca dos outros usuários) em
    1440x900, 1280x800, 1024x768, 390x844 e 360x740 — onze dos doze casos,
    com `scrollHeight` igual à altura da janela.

    O DÉCIMO SEGUNDO CASE É O 360x640 NA TELA DOS OUTROS, e ele é o piso
    funcionando como foi projetado: com ~523px de chassi numa janela de
    640px sobram 117px, menos que o piso de 200px, e a página vai a 723px.
    A alternativa seria deixar o formulário com 117px — duas linhas e meio.
    Quem abrir o sistema numa janela dessa rola a página, que é o
    comportamento de sempre; em qualquer janela de uso normal, não rola.

    Esta é a diferença entre as duas telas: com `72vh` a do `master` media
    1.183px numa janela de 900 (283px de transbordo) e a dos outros usuários
    transbordava em 1440x700. Com o teto derivado, as duas passam a caber e o
    que sobra do formulário vira rolagem interna.

    EN: Renders a form into the CURRENT slot, with no card and no dialog.
    """
    from nicegui import ui
    try:
        miolo = ui.column().classes("w-full min-w-0").style(
            f"gap: {gap}; max-height: {max_altura}; min-height: 0; "
            f"overflow-y: auto; overflow-x: hidden; padding-right: 2px")
        miolo.props(f'role="region" aria-label="{rotulo}"')
        with miolo:
            grade = ui.element("div").classes("w-full").style(CSS_GRADE_CAMPOS)
            grade.props('role="group" aria-label="Campos do formulário"')
        yield miolo, grade
    except Exception as e:
        _log().error(f"formulario_na_tela: falha ao montar '{rotulo}': {e}")
        raise


def rodape_dialogo(dlg, acoes=(), *, chave_modulo="skyrover", classes_extra=""):
    """Renders the standard right-aligned dialog footer (Cancel + actions).

    Rodapé de diálogo com ações primárias sempre visíveis: linha
    `w-full justify-end` (gap 0.5rem) com o botão "Cancelar" e, para cada
    item de `acoes` — tupla `(rotulo, on_click)` ou `(rotulo, on_click,
    kwargs)` — um botão primário compacto do tema do módulo. `classes_extra`
    soma classes à row (ex.: `mt-3`); default "" mantém a saída atual
    byte-idêntica. Itens malformados são ignorados com registro de erro no
    loguru (fail-soft, sem derrubar o diálogo).

    O "Cancelar" vai pela FÁBRICA `botao(..., variante="secundario")`, e não
    por `ui.button(...).props("flat no-caps")` como era antes (02/10/2026).
    `flat` produz o botão com a cor padrão do Quasar, enquanto o resto do
    rodapé sai pela cor do módulo: o par "Cancelar / Salvar" ficava com duas
    cores diferentes, e o "Salvar" com a cor do módulo ao lado de um "Cancelar"
    cinza-que-não-é-o-cinza-do-sistema. Como variante `secundario`, os dois
    saem da mesma paleta do módulo definida pelo admin — e o cancelamento
    continua visualmente distinto do salvar, que é a diferença que importa
    para não clicar no botão errado.
    """
    from nicegui import ui
    classes = "w-full justify-end" + (f" {classes_extra}" if classes_extra else "")
    with ui.row().classes(classes).style("gap: 0.5rem"):
        # `no_caps=False`: o padrão da fábrica é `no-caps`, que impede o
        # `text-transform` de caixa alta. Passar "no-caps" em `extra_classes`
        # brigaria com esse token; o parâmetro é a forma correta de dizer
        # "não force maiúscula" sem fighting com o estilo do tema.
        botao("Cancelar", variante="secundario", on_click=dlg.close,
              chave_modulo=chave_modulo, compacto=True)
        for item in acoes:
            try:
                rotulo, on_click, *resto = item
                kwargs = resto[0] if resto else {}
                botao(rotulo, variante="primario", compacto=True,
                      on_click=on_click, chave_modulo=chave_modulo, **kwargs)
            except Exception as e:
                _log().error(f"rodape_dialogo: ação de rodapé inválida "
                             f"ignorada ({item!r}): {e}")


def rodape_salvar_restaurar(salvar, restaurar=None, *, chave_modulo="skyrover",
                            rotulo_salvar="Aplicar", icone_salvar="save",
                            rotulo_restaurar="Restaurar padrão",
                            acoes_extra=(), data_testid=None):
    """Renders the standard per-card footer: restore + apply (+ extra actions).

    Rodapé PADRÃO dos cards de configuração (padrão de 2 botões por card):
    linha `w-full justify-end mt-2 flex-wrap` (gap 0.5rem) com, em ordem, as
    ações extras de `acoes_extra` — tuplas `(rotulo, icone, on_click[,
    tooltip[, variante]])`, variante default `solido` —, "Restaurar padrão"
    (variante `restaurar` — contorno âmbar; somente se `restaurar` for
    callable) e o botão "Aplicar" (variante `solido` do tema do módulo via
    `botao`) — ambos pela fábrica central, garantindo cor/tamanho idênticos
    em todo o módulo. "Aplicar" grava EXCLUSIVAMENTE o card em questão.
    `data_testid` (opcional) aplica `data-testid=<valor>` ao botão "Aplicar"
    (default `None` preserva a saída byte-idêntica das chamadas existentes).
    Falha de montagem registra exception e omite o botão (fail-soft); ações
    extras malformadas são ignoradas com registro.
    """
    from nicegui import ui
    with ui.row().classes("w-full justify-end mt-2 flex-wrap") \
            .style("gap: 0.5rem"):
        for item in acoes_extra:
            try:
                rotulo, icone, on_click, *resto = item
                tooltip = resto[0] if len(resto) > 0 else None
                variante = resto[1] if len(resto) > 1 else "solido"
                botao(rotulo, icone=icone, on_click=on_click, tooltip=tooltip,
                      variante=variante, chave_modulo=chave_modulo)
            except Exception as e:
                _log().error(f"rodape_salvar_restaurar: ação extra inválida "
                             f"ignorada ({item!r}): {e}")
        if callable(restaurar):
            _btn_restaurar = botao(rotulo_restaurar, on_click=restaurar, variante="restaurar",
                  chave_modulo=chave_modulo)
        else:
            _btn_restaurar = None
        _btn_aplicar = botao(rotulo_salvar, icone=icone_salvar, on_click=salvar,
                             variante="solido", chave_modulo=chave_modulo)
        if _btn_aplicar is not None and data_testid:
            _btn_aplicar.props(f'data-testid={data_testid}')
        return (_btn_restaurar, _btn_aplicar)


def _valor_config(chave, padrao, origem):
    """Resolves one `tb_config` value for the field factories (fail-soft).

    Resolve o valor inicial de um campo de configuração via `get_config`
    (import lazy de `conexao_bd`); falha de leitura registra warning no
    loguru e devolve o `padrao` (fail-soft, sem derrubar a renderização).
    """
    try:
        from mod_skyrover.bd_conexao import get_config
        return get_config(chave, padrao)
    except Exception as e:
        _log().warning(f"{origem}: falha ao ler '{chave}', usando "
                       f"valor/padrão: {e}")
        return padrao


class CampoBase:
    """Base class for config fields (`tb_config` resolution + finishing).

    Base dos campos de configuração: com `chave` informada e `valor=None`,
    o valor inicial vem de `get_config(chave, padrao)` (tb_config central,
    fail-soft via `_valor_config`); caso contrário, usa `valor`.
    `_finalizar` aplica a sequência fixa de acabamento — props, classes
    (`largura`), estilo inline (opcional), tooltip e `ao_mudar` repassado
    a `.on_value_change` — sobre o campo criado pela subclasse em
    `montar`. Falha de montagem registra exception e devolve `None`
    (fail-soft).
    """

    origem = "campo"

    def __init__(self, rotulo, valor=None, *, chave=None, padrao="",
                 ao_mudar=None, tooltip=None, largura="w-full",
                 props="outlined dense"):
        self.rotulo = rotulo
        self.valor = valor
        self.chave = chave
        self.padrao = padrao
        self.ao_mudar = ao_mudar
        self.tooltip = tooltip
        self.largura = largura
        self.props = props

    def _valor_resolvido(self):
        """Resolves the initial value (`tb_config` via `chave` or `valor`)."""
        if self.valor is None and self.chave:
            return _valor_config(self.chave, self.padrao,
                                 type(self).origem)
        return self.valor

    def _finalizar(self, campo, estilo=""):
        """Applies props/classes/style/tooltip/`ao_mudar` to the element.

        Sequência fixa de acabamento, na mesma ordem das funções
        originais: props → classes (`largura`) → style (`estilo`, quando
        não vazio) → tooltip → `ao_mudar`. Retorna o próprio campo.
        """
        if self.props:
            campo.props(self.props)
        if self.largura:
            campo.classes(self.largura)
        if estilo:
            campo.style(estilo)
        if self.tooltip:
            campo.tooltip(self.tooltip)
        if self.ao_mudar:
            campo.on_value_change(self.ao_mudar)
        return campo

    def montar(self):
        """Creates and finishes the field element (subclass hook)."""
        raise NotImplementedError


class CampoCor(CampoBase):
    """Standard color field (`ui.color_input`) with optional config lookup.

    Campo de cor padronizado: `ui.color_input(rotulo,
    value=valor_resolvido)` com props `props` (default `outlined dense`),
    classes `largura` (default `w-full`), tooltip opcional e `ao_mudar`
    repassado a `.on_value_change`. `props`/`largura` vazios não são
    aplicados (permite réplica crua, ex. painel de aparência sem props).
    Retorna o elemento criado (ou `None` em falha de montagem).
    """

    origem = "campo_cor"

    def montar(self):
        """Creates the `ui.color_input` with the resolved value."""
        from nicegui import ui
        try:
            return self._finalizar(ui.color_input(
                self.rotulo, value=self._valor_resolvido()))
        except Exception as e:
            _log().exception(f"campo_cor: falha ao montar campo "
                             f"{self.rotulo!r}: {e}")
            return None


class CampoTexto(CampoBase):
    """Standard text field (`ui.input`/`ui.textarea`) with config lookup.

    Campo de texto padronizado: `ui.textarea` quando `multiline`, senão
    `ui.input` (mesma assinatura posicional rótulo+valor). `cor_texto`/
    `cor_fundo` geram style inline (`color:`/`background-color:`)
    somente quando informados. `senha=True` cria o `ui.input` com
    `password=True, password_toggle_button=True` (botão exibir/ocultar,
    byte-idêntico aos campos de senha existentes; sem efeito com
    `multiline`). `placeholder` é repassado ao construtor quando
    informado. Sem valor resolvido (`valor=None` sem `chave`), o kwarg
    `value` NÃO é repassado — réplica crua byte-idêntica (`ui.input` sem
    `value` usa `''`, não `None`). Retorna o elemento criado (ou `None`
    em falha de montagem).
    """

    origem = "campo_texto"

    def __init__(self, rotulo, valor=None, *, chave=None, padrao="",
                 ao_mudar=None, tooltip=None, cor_texto=None, cor_fundo=None,
                 largura="w-full", multiline=False, props="outlined dense",
                 senha=False, placeholder=None):
        super().__init__(rotulo, valor, chave=chave, padrao=padrao,
                         ao_mudar=ao_mudar, tooltip=tooltip, largura=largura,
                         props=props)
        self.cor_texto = cor_texto
        self.cor_fundo = cor_fundo
        self.multiline = multiline
        self.senha = senha
        self.placeholder = placeholder

    def _estilo(self):
        """Builds the inline style from `cor_texto`/`cor_fundo` (or empty)."""
        estilo = ""
        if self.cor_texto:
            estilo += f"color:{self.cor_texto};"
        if self.cor_fundo:
            estilo += f"background-color:{self.cor_fundo};"
        return estilo

    def montar(self):
        """Creates the `ui.input`/`ui.textarea` and finishes it."""
        from nicegui import ui
        try:
            fabrica = ui.textarea if self.multiline else ui.input
            kwargs = {}
            valor_resolvido = self._valor_resolvido()
            if valor_resolvido is not None:
                kwargs["value"] = valor_resolvido
            if self.senha and not self.multiline:
                kwargs["password"] = True
                kwargs["password_toggle_button"] = True
            if self.placeholder is not None:
                kwargs["placeholder"] = self.placeholder
            campo = fabrica(self.rotulo, **kwargs)
            return self._finalizar(campo, estilo=self._estilo())
        except Exception as e:
            _log().exception(f"campo_texto: falha ao montar campo "
                             f"{self.rotulo!r}: {e}")
            return None


class CampoSelecao(CampoBase):
    """Standard select field (`ui.select`) with optional config lookup.

    Campo de seleção padronizado: `ui.select(opcoes, label=rotulo,
    value=valor_resolvido)` com props `props` (default `outlined dense`),
    classes `largura` (default `w-full`) e tooltip opcional. Com `chave`
    informada e `valor=None`, o valor inicial vem de `get_config(chave,
    padrao)`. `ao_mudar` é repassado a `.on_value_change`. Retorna o
    elemento criado (ou `None` em falha de montagem).
    """

    origem = "campo_selecao"

    def __init__(self, rotulo, opcoes, valor=None, *, chave=None,
                 padrao=None, ao_mudar=None, largura="w-full",
                 props="outlined dense", tooltip=None):
        super().__init__(rotulo, valor, chave=chave, padrao=padrao,
                         ao_mudar=ao_mudar, tooltip=tooltip, largura=largura,
                         props=props)
        self.opcoes = opcoes

    def montar(self):
        """Creates the `ui.select` with the resolved value."""
        from nicegui import ui
        try:
            return self._finalizar(ui.select(self.opcoes, label=self.rotulo,
                                             value=self._valor_resolvido()))
        except Exception as e:
            _log().exception(f"campo_selecao: falha ao montar campo "
                             f"{self.rotulo!r}: {e}")
            return None


def campo_cor(rotulo, valor=None, *, chave=None, padrao="", ao_mudar=None,
              tooltip=None, largura="w-full", props="outlined dense"):
    """Standard color field (delegates to `CampoCor`).

    Wrapper fino da classe `CampoCor` — assinatura e saída idênticas à
    original. Campo de cor padronizado: `ui.color_input(rotulo,
    value=valor_resolvido)` com props `props` (default `outlined dense`),
    classes `largura` (default `w-full`), tooltip opcional e `ao_mudar`
    repassado a `.on_value_change` (recebe o evento, igual ao padrão
    atual). Com `chave` informada e `valor=None`, o valor inicial vem de
    `get_config(chave, padrao)` (tb_config central); falha de leitura
    registra warning no loguru e usa `valor`/`padrao` (fail-soft).
    `props`/`largura` vazios não são aplicados. Retorna o elemento criado
    (ou `None` em falha de montagem).
    """
    return CampoCor(rotulo, valor, chave=chave, padrao=padrao,
                    ao_mudar=ao_mudar, tooltip=tooltip, largura=largura,
                    props=props).montar()


def campo_texto(rotulo, valor=None, *, chave=None, padrao="", ao_mudar=None,
                tooltip=None, cor_texto=None, cor_fundo=None,
                largura="w-full", multiline=False, props="outlined dense",
                senha=False, placeholder=None):
    """Standard text field (delegates to `CampoTexto`).

    Wrapper fino da classe `CampoTexto` — assinatura e saída idênticas à
    original. Campo de texto padronizado: `ui.textarea` quando `multiline`,
    senão `ui.input` (mesma assinatura posicional rótulo+valor), props
    `props` (default `outlined dense`), classes `largura` (default
    `w-full`), tooltip opcional e `ao_mudar` repassado a
    `.on_value_change`. Com `chave` informada e `valor=None`, o valor
    inicial vem de `get_config(chave, padrao)`; falha de leitura registra
    warning no loguru e usa `valor`/`padrao` (fail-soft). `cor_texto`/
    `cor_fundo` geram style inline somente quando informados.
    `senha=True` cria o campo com botão exibir/ocultar; `placeholder` é
    repassado quando informado; sem valor resolvido o kwarg `value` não é
    repassado (réplica crua byte-idêntica). Retorna o elemento criado (ou
    `None` em falha de montagem).
    """
    return CampoTexto(rotulo, valor, chave=chave, padrao=padrao,
                      ao_mudar=ao_mudar, tooltip=tooltip,
                      cor_texto=cor_texto, cor_fundo=cor_fundo,
                      largura=largura, multiline=multiline, props=props,
                      senha=senha, placeholder=placeholder).montar()


def campo_selecao(rotulo, opcoes, valor=None, *, chave=None, padrao=None,
                  ao_mudar=None, largura="w-full", props="outlined dense",
                  tooltip=None):
    """Standard select field (delegates to `CampoSelecao`).

    Wrapper fino da classe `CampoSelecao` — assinatura e saída idênticas à
    original. Campo de seleção padronizado: `ui.select(opcoes,
    label=rotulo, value=valor_resolvido)` com props `props` (default
    `outlined dense`), classes `largura` (default `w-full`) e tooltip
    opcional. Com `chave` informada e `valor=None`, o valor inicial vem de
    `get_config(chave, padrao)`; falha de leitura registra warning no
    loguru e usa `valor`/`padrao` (fail-soft). Retorna o elemento criado
    (ou `None` em falha de montagem).
    """
    return CampoSelecao(rotulo, opcoes, valor, chave=chave, padrao=padrao,
                        ao_mudar=ao_mudar, largura=largura, props=props,
                        tooltip=tooltip).montar()


class Cartao:
    """Configuration card class (themed title/caption/grid/actions/extras).

    Encapsula a montagem do card de configuração: estilo `cor_fundo`
    informado ou `tema_modulo.estilo_cartao(chave_modulo)` (fail-soft),
    mais `color:{cor_texto}` quando informado; cor de título do tema
    quando `cor_titulo=None`; grid `w-full grid-cols-1` + `colunas` com
    `gap:{gap}` para os CALLABLES de `campos` (cada um cria seu campo
    dentro do grid); `destaque_impar=True` com quantidade ímpar > 3
    aplica `col-span-full` ao primeiro campo; `extras` — CALLABLES
    renderizados ENTRE o grid e a row de ações; `acoes` — tuplas
    `(rotulo, icone, on_click[, tooltip])` — vira row `w-full
    justify-center` com botões `ui_comum.botao` do tema do módulo.
    Falhas por campo/ação/extra são registradas no loguru sem derrubar o
    card (fail-soft). `card_config` é o wrapper fino.
    """

    def __init__(self, *, chave_modulo="skyrover", cor_titulo=None,
                 cor_fundo=None, cor_texto=None, colunas="", gap="1.25rem",
                 destaque_impar=True):
        self.chave_modulo = chave_modulo
        self.cor_titulo = cor_titulo
        self.cor_fundo = cor_fundo
        self.cor_texto = cor_texto
        self.colunas = colunas
        self.gap = gap
        self.destaque_impar = destaque_impar

    def _estilo(self):
        """Builds the card inline style (explicit `cor_fundo` or theme)."""
        from mod_skyrover import tema_modulo
        if self.cor_fundo:
            estilo = f"background-color:{self.cor_fundo};"
        else:
            try:
                estilo = tema_modulo.estilo_cartao(self.chave_modulo)
            except Exception as e:
                _log().warning(f"card_config: estilo de cartão indisponível "
                               f"para '{self.chave_modulo}': {e}")
                estilo = ""
        if self.cor_texto:
            estilo = f"{estilo}color:{self.cor_texto};"
        return estilo

    def _cor_titulo_resolvida(self):
        """Resolves the title color (`cor_titulo` explicit or theme value)."""
        if self.cor_titulo is not None:
            return self.cor_titulo
        from mod_skyrover import tema_modulo
        try:
            return tema_modulo.ler_tema(self.chave_modulo).get(
                "cor_titulo", "#212121") or "#212121"
        except Exception as e:
            _log().warning(f"card_config: cor de título indisponível para "
                           f"'{self.chave_modulo}': {e}")
            return "#212121"

    def montar(self, titulo, campos=(), legenda="", acoes=(), extras=()):
        """Builds the full card; returns the element (or `None` on failure).

        Ordem fixa de criação: card (`w-full`) + estilo → título
        (`text-subtitle1 font-bold` na cor resolvida) → legenda
        (`text-caption text-grey-7 max-w-3xl -mt-2`) → grid de campos →
        extras → row de ações. Falha geral de montagem registra exception
        e retorna `None` (fail-soft).
        """
        from nicegui import ui
        estilo = self._estilo()
        cor_titulo = self._cor_titulo_resolvida()
        try:
            card = ui.card().classes("w-full")
            if estilo:
                card.style(estilo)
            with card:
                ui.label(titulo).classes("text-subtitle1 font-bold") \
                    .style(f"color:{cor_titulo}")
                if legenda:
                    ui.label(legenda).classes(
                        "text-caption text-grey-7 max-w-3xl -mt-2")
                classes_grid = "w-full grid-cols-1" + \
                    (f" {self.colunas}" if self.colunas else "")
                with ui.grid().classes(classes_grid).style(f"gap:{self.gap}"):
                    destacar = (self.destaque_impar and len(campos) > 3
                                and len(campos) % 2 == 1)
                    for i, criar in enumerate(campos):
                        try:
                            el = criar()
                            if destacar and i == 0 and el is not None:
                                el.classes("col-span-full")
                        except Exception as e:
                            _log().error(f"card_config: campo {i} ignorado "
                                         f"({criar!r}): {e}")
                for j, criar_extra in enumerate(extras):
                    try:
                        criar_extra()
                    except Exception as e:
                        _log().error(f"card_config: extra {j} ignorado "
                                     f"({criar_extra!r}): {e}")
                if acoes:
                    with ui.row().classes("w-full justify-center") \
                            .style("gap: 0.5rem"):
                        for item in acoes:
                            try:
                                rotulo, icone, on_click, *resto = item
                                tooltip = resto[0] if resto else None
                                botao(rotulo, icone=icone,
                                      on_click=on_click, tooltip=tooltip,
                                      chave_modulo=self.chave_modulo)
                            except Exception as e:
                                _log().error(f"card_config: ação inválida "
                                             f"ignorada ({item!r}): {e}")
            return card
        except Exception as e:
            _log().exception(f"card_config: falha ao montar card "
                             f"{titulo!r}: {e}")
            return None


def card_config(titulo, campos=(), *, legenda="", acoes=(),
                chave_modulo="skyrover", cor_titulo=None, cor_fundo=None,
                cor_texto=None, colunas="", gap="1.25rem",
                destaque_impar=True, extras=()):
    """Configuration card (delegates to `Cartao`).

    Wrapper fino da classe `Cartao` — assinatura e saída idênticas à
    original. Card de configuração padronizado: `ui.card().classes("w-full")`
    com estilo `cor_fundo` informado ou `tema_modulo.estilo_cartao`
    (fail-soft), mais `color:{cor_texto}` quando informado. Título em
    label `text-subtitle1 font-bold` na cor `cor_titulo` — quando `None`,
    usa a cor de título do tema. `legenda` vira label `text-caption
    text-grey-7 max-w-3xl -mt-2`. O grid recebe os CALLABLES de `campos`
    (o caller captura o elemento via closure); `destaque_impar=True` com
    quantidade ímpar > 3 aplica `col-span-full` ao primeiro campo.
    `extras` — CALLABLES renderizados ENTRE o grid e a row de ações;
    `acoes` — tuplas `(rotulo, icone, on_click[, tooltip])` — vira row
    `w-full justify-center` com botões do tema do módulo. Falhas por
    campo/ação são registradas no loguru sem derrubar o card (fail-soft).
    Retorna o card criado (ou `None` em falha de montagem).
    """
    cartao = Cartao(chave_modulo=chave_modulo, cor_titulo=cor_titulo,
                    cor_fundo=cor_fundo, cor_texto=cor_texto,
                    colunas=colunas, gap=gap, destaque_impar=destaque_impar)
    return cartao.montar(titulo, campos=campos, legenda=legenda,
                         acoes=acoes, extras=extras)


def card_admin(titulo, *, icone="settings", chave_modulo="skyrover",
               aberto=True, cor_borda=None, cor_fundo=None, extra_classes="",
               grade=True, gap="0.5rem"):
    """Standard admin card: essential card shell + collapsible header inside.

    Padrão dos painéis de administração (card ESSENCIAL): `ui.card` w-full
    com borda esquerda temática — `cor_borda` explícita vence; senão a
    `<prefixo>_cor_botao` do tema (ler_tema, fail-soft); senão cinza
    `#607D8B` — e fundo por `estilo_cartao(chave_modulo)` (fail-soft),
    salvo `cor_fundo` explícito. Dentro do card fica `ui.expansion(titulo,
    icon=icone)` — o cabeçalho retrátil; o card permanece visível mesmo
    com o conteúdo retraído (o retrátil é apenas o cabeçalho, nunca o
    card). O retorno é o alvo do `with` do chamador:

    - `grade=True` (padrão): dentro da expansion é criada a GRADE
      responsiva do projeto — `ui.grid().classes("w-full grid-cols-1
      sm:grid-cols-2 md:grid-cols-3")` com `gap:{gap}` — 1 campo por linha
      em tela pequena, 2 em média e 3 em grande; o retorno é a grade e o
      conteúdo do `with` flui nela (campos em células; rótulos/rodapés
      full-width usam `col-span-full`).
    - `grade=False`: o retorno é a própria expansion — conteúdo livre
      (tabelas, textareas, seções mistas).

    `extra_classes` soma classes no card (ex.: espaçamento `mt-2`);
    `aberto=True` inicia com o conteúdo expandido. O título (cabeçalho
    retrátil) é colorido com a cor de título do módulo
    (`<prefixo>_cor_titulo` via `ler_tema`, fail-soft → `#212121`), seguindo
    o padrão "cor dos títulos dos cards". Falha ao ler o tema registra
    warning e usa os padrões (fail-soft).
    """
    from nicegui import ui
    from mod_skyrover import tema_modulo
    try:
        tema = tema_modulo.ler_tema(chave_modulo)
        cor_tema = tema.get("cor_botao", "") or ""
        cor_titulo = tema.get("cor_titulo", "#212121") or "#212121"
    except Exception as e:
        _log().warning(f"card_admin: tema indisponível para "
                       f"'{chave_modulo}', usando borda padrão: {e}")
        cor_tema = ""
        cor_titulo = "#212121"
    borda = cor_borda or cor_tema or "#607D8B"
    estilo = f"border-left-color:{borda};"
    if cor_fundo:
        estilo += f"background-color:{cor_fundo};"
    else:
        try:
            estilo += tema_modulo.estilo_cartao(chave_modulo)
        except Exception:
            pass
    with ui.card().classes(
            f"w-full border-l-8 {extra_classes}".strip()).style(estilo):
        exp = ui.expansion(titulo, icon=icone, value=aberto).classes("w-full")
        if cor_titulo:
            exp.props(f"header-style='color:{cor_titulo}'")
        alvo = exp
        if grade:
            with exp:
                alvo = ui.grid().classes(
                    "w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-3"
                ).style(f"gap:{gap}")
    return alvo


class ItemMenuDrawer:
    """Accessible drawer menu item with Bootstrap list-group look (no global CSS).

    Item de menu do drawer acessível com visual Bootstrap list-group (sem CSS
    global): `ui.item` `w-full rounded-lg my-0.5` com `.style('min-width: 0')`,
    seção avatar com ícone `text-primary shrink-0 aria-hidden` e
    `ui.item_label` `truncate max-w-full grow`. O Bootstrap local
    (`assets/css/frameworks/bootstrap@5.3.8.min.css`, servido em
    `/css/frameworks/*` via `tema_css.montar_rotas_static()`) NÃO é injetado
    aqui — o reset global quebraria o Quasar; o visual list-group (borda
    arredondada, hover, estado ativo) é replicado com Tailwind (`.classes()`)
    + Quasar (`.props()`), com `focus-visible` ring, tooltip PT-BR, estado
    ativo (`bg-blue-100` + `aria-current="page"`) e `data-testid` via
    `.props()` (`menu-home`, `menu-<chave>`, `menu-admin`, `menu-docs`,
    `menu-sair`). Itens só-ícone (rótulo vazio) recebem `aria-label`.
    `chave_modulo` é reservada para tematização futura — o ícone usa
    `text-primary` (Quasar primary já tematizado via `ui.colors` no layout),
    sem `ler_tema` por item (economia de consultas). Falha de montagem
    registra exception e retorna `None` (fail-soft).
    """

    def __init__(self, rotulo, *, icone, on_click, tooltip=None,
                 chave_modulo="skyrover", testid=None, ativo=False):
        self.rotulo = rotulo
        self.icone = icone
        self.on_click = on_click
        self.tooltip = tooltip
        self.chave_modulo = chave_modulo
        self.testid = testid
        self.ativo = ativo

    def montar(self):
        """Builds the `ui.item` drawer entry; returns it (or `None`).

        Monta o `ui.item` do drawer e devolve o elemento (ou `None` em
        falha de montagem, fail-soft).
        """
        from nicegui import ui
        try:
            base = ("w-full rounded-lg my-0.5 cursor-pointer "
                    "focus-visible:ring-2 focus-visible:outline-none")
            estado = " bg-blue-100 font-bold" if self.ativo \
                else " hover:bg-blue-50"
            item = ui.item(on_click=self.on_click).classes(base + estado)
            item.style("min-width: 0")
            if self.testid:
                item.props(f"data-testid={self.testid}")
            if self.ativo:
                item.props('aria-current="page"')
            rotulo_txt = (self.rotulo or "").strip()
            if not rotulo_txt:
                item.props(f'aria-label="{self.tooltip or self.icone}"')
            if self.tooltip:
                item.tooltip(self.tooltip)
            with item:
                with ui.item_section().props("avatar"):
                    ui.icon(self.icone).classes("text-primary shrink-0") \
                        .props('aria-hidden="true"')
                if self.rotulo:
                    ui.item_label(self.rotulo) \
                        .classes("truncate max-w-full grow") \
                        .style("min-width: 0")
            return item
        except Exception as e:
            _log().exception(f"item_menu_drawer: falha ao montar item "
                             f"{self.rotulo!r} (icone={self.icone!r}): {e}")
            return None


def item_menu_drawer(rotulo, *, icone, on_click, tooltip=None,
                     chave_modulo="skyrover", testid=None, ativo=False):
    """Accessible drawer menu item (delegates to `ItemMenuDrawer`).

    Wrapper fino da classe `ItemMenuDrawer` — assinatura e saída idênticas.
    Fábrica DDD PT-BR do item do menu hambúrguer: `ui.item` acessível
    `w-full rounded-lg my-0.5` com `.style('min-width: 0')`, avatar com ícone
    `text-primary shrink-0 aria-hidden`, rótulo `truncate max-w-full grow`,
    tooltip PT-BR, anel `focus-visible`, estado ativo e `data-testid` via
    `.props()` (ex. `menu-home`, `menu-<chave>`, `menu-admin`, `menu-docs`,
    `menu-sair`); itens só-ícone recebem `aria-label`. Retorna o `ui.item`
    criado (ou `None` em falha de montagem, fail-soft).
    """
    return ItemMenuDrawer(
        rotulo, icone=icone, on_click=on_click, tooltip=tooltip,
        chave_modulo=chave_modulo, testid=testid, ativo=ativo).montar()
