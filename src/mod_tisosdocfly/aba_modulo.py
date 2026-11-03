"""Common visual standard for module headers, tabs and screen components.

Padrão visual comum de cabeçalho, abas e componentes de tela dos módulos.

Segue o exemplo do módulo Editor de PDF: um card de cabeçalho (título +
subtítulo) seguido de uma barra de abas contendo a(s) aba(s) do próprio
módulo e a aba "Administração" (ícone `admin_panel_settings`), exibida
apenas para administradores. Também concentra os componentes de tela
padrão dos módulos: menu de abas (`menu_modulo`), campo de pesquisa
(`campo_busca`) e barra de ações (`barra_acoes`).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from nicegui import ui

from mod_tisosdocfly import ui_comum
from mod_tisosdocfly.ui_comum import botao


def _log():
    """Returns the loguru logger bound to the core module ("tisosdocfly").

    Logger loguru vinculado ao módulo núcleo (`tisosdocfly`), no padrão
    `observabilidade._FMT`. Usado nos blocos `except` dos helpers de tela
    para registrar falhas sem derrubar a renderização (fail-soft).
    """
    from mod_tisosdocfly import observabilidade
    return observabilidade.get_logger("tisosdocfly")


def cabecalho(titulo: str, subtitulo: str = "",
              cor_borda: str = None, cor_titulo: str = None,
              cor_fundo: str = None, *, chave_modulo: str = None):
    """Module header card (title + optional subtitle) colored by the module theme.

    Card de cabeçalho do módulo (título + subtítulo opcional; o subtítulo
    aceita HTML como `<code>`). Com `chave_modulo`, as cores vêm do tema do
    módulo (`tema_modulo.ler_tema`): `cor_borda` = `cor_botao` — a MESMA cor
    geral do módulo (chave `<prefixo>_cor_botao`; vazia = padrão do próprio
    módulo via `PADROES_TEMA`; editável no cupê Aparência, campo "Cor geral
    do módulo") —, `cor_titulo` = `cor_titulo` e `cor_fundo` =
    `cor_fundo`, sempre que o parâmetro correspondente for None; parâmetros
    explícitos vencem o tema (retrocompatibilidade total). Sem `chave_modulo`,
    os defaults vêm da paleta central `ui_comum.CORES` (comportamento
    idêntico ao anterior). Falha ao ler o tema → warning no loguru + defaults
    (fail-soft). `cor_fundo` vazio/"" significa "herda" (não pinta o
    `.q-page`).
    """
    if chave_modulo:
        try:
            from mod_tisosdocfly import tema_modulo
            tema = tema_modulo.ler_tema(chave_modulo)
            if cor_borda is None:
                cor_borda = tema["cor_botao"]
            if cor_titulo is None:
                cor_titulo = tema["cor_titulo"]
            if cor_fundo is None:
                cor_fundo = tema["cor_fundo"]
        except Exception as e:
            _log().warning(f"cabecalho: falha ao ler tema '{chave_modulo}' "
                           f"({e}); usando cores padrão")
    if cor_borda is None:
        cor_borda = ui_comum.CORES["primaria"]
    if cor_titulo is None:
        cor_titulo = ui_comum.CORES["titulo"]
    if cor_fundo is None:
        cor_fundo = ""
    with ui.card().classes("w-full border-l-8").style(f"border-left-color:{cor_borda}"):
        with ui.row().classes("w-full items-center justify-between flex-wrap").style("gap: 0.75rem"):
            with ui.column().style("gap: 0"):
                ui.label(titulo).classes("text-h5 font-bold whitespace-nowrap cabecalho-titulo").style(f"color:{cor_titulo}")
                if subtitulo:
                    ui.label(subtitulo).classes("text-caption text-grey-6")
    if cor_fundo:
        try:
            ui.query(".q-page").style(f"background-color:{cor_fundo}")
        except Exception:
            pass


def abas(titulo_principal: str, icone_principal: str, admin: bool = False,
         valor: str = "principal", observabilidade: bool = False):
    """Creates the tab bar: main tab + 'Observabilidade' (if OTel/Grafana is running).

    The 'Administração' tab is no longer included here — admin is accessed via the
    hamburger menu (route /admin/{chave_modulo}) for all modules except tisosdocfly
    (which uses /configuracoes). The `admin` parameter is kept for backward
    compatibility but has no effect.
    """
    tabs_el = ui.tabs(value=valor)
    with tabs_el:
        ui.tab("principal", label=titulo_principal, icon=icone_principal)
        if observabilidade:
            ui.tab("obs", label="Observabilidade", icon="query_stats")
    return tabs_el


def menu_modulo(itens, valor=None, *, classes_extra="", props_extra=""):
    """Builds the module menu tabs (icon above, label below).

    Cria a barra de abas de menu do módulo no padrão do Renomeador de
    Empenhos: `ui.tabs` com classes `w-full` e, para cada item de `itens` —
    tupla `(chave, rotulo, icone)` — um `ui.tab` posicional com o ícone em
    cima e o nome embaixo (sem `inline-label`). `valor=None` ativa o
    primeiro item. Retorna o elemento `ui.tabs` para uso em `ui.tab_panels`.

    `classes_extra`/`props_extra` são acréscimos **opcionais**: por padrão a
    saída é exatamente `w-full` (byte-idêntica). Use-os quando a barra ficar
    dentro de uma `ui.row` e precisar de comportamento de flex/scroll — por
    exemplo `classes_extra="min-w-0 flex-1 overflow-x-auto"` e
    `props_extra="dense"` para as telas estreitas (mobile), em vez de
    reescrever a barra à mão.
    """
    if valor is None and itens:
        valor = itens[0][0]
    tabs_el = ui.tabs(value=valor).classes("w-full")
    if classes_extra:
        tabs_el.classes(classes_extra)
    if props_extra:
        tabs_el.props(props_extra)
    with tabs_el:
        for chave, rotulo, icone in itens:
            ui.tab(chave, rotulo, icon=icone)
    return tabs_el


def campo_busca(placeholder, on_change=None, *, valor_inicial="", tooltip=None):
    """Builds the standard search field (outlined, dense, clearable, debounced).

    Cria o campo de pesquisa padrão das barras de ações: `ui.input` com
    `placeholder`/`value`, props `outlined dense clearable debounce='150'` e
    classes `w-full grow min-w-[220px]`. `tooltip` é aplicado somente quando
    informado. Retorna o `ui.input` criado.

    POR QUE `on_value_change` E NÃO `on_change` (28/09/2026)
        `on_change` escuta o evento DOM `change`, que num campo de texto só
        dispara ao perder o foco ou apertar Enter. Quem digita "Guerzoni" vê a
        lista inteira por baixo enquanto escreve e o filtro só fecha no fim —
        que parece defeito, e é. `on_value_change` escuta o `v-model` do
        Quasar e dispara a cada tecla; o `debounce='150'` agrupa as teclas em
        rajada, então não redesenha a lista a cada caractere.

        Os dois entregam um evento com `.value`, então o handler passado aqui
        funciona igual nos dois casos — nenhum dos módulos que usa este campo
        (lista telefônica, blog, gestão de usuários) precisa mudar.

        Cai para `on_change` se a versão do NiceGUI não tiver
        `on_value_change`: o campo continua funcionando, só sem filtrar
        enquanto se digita.
    """
    campo = ui.input(placeholder=placeholder, value=valor_inicial) \
        .props("outlined dense clearable debounce='150'") \
        .classes("w-full grow min-w-[220px]")
    if on_change is not None:
        if hasattr(campo, "on_value_change"):
            campo.on_value_change(on_change)
        else:
            campo.on_change(on_change)
    if tooltip:
        campo.tooltip(tooltip)
    return campo


def barra_acoes(busca=None, acoes=()):
    """Builds the white action bar (optional search + themed buttons).

    Cria a barra branca do padrão Gestão de Usuários, sem abas: `ui.row`
    `w-full items-center justify-between gap-4 flex-nowrap bg-white
    rounded-lg shadow-sm px-3 py-1`. Com `busca` (dict de kwargs de
    `campo_busca`), renderiza o campo dentro da row `items-center gap-2
    flex-nowrap shrink-0` (`width:min(46%, 620px)`) seguido dos botões; sem
    `busca`, os botões ficam alinhados à direita em row `justify-end`.
    `acoes` recebe tuplas `(rotulo, icone, on_click)` ou `(rotulo, icone,
    on_click, tooltip)`; cada botão é criado por `ui_comum.botao` (variante
    `primario`, `extra_classes="shrink-0"`). Itens malformados são ignorados
    com registro no loguru (fail-soft). Retorna a row da barra.
    """
    barra = ui.row().classes("w-full items-center justify-between gap-4 flex-nowrap "
                             "bg-white rounded-lg shadow-sm px-3 py-1")
    with barra:
        if busca:
            with ui.row().classes("items-center gap-2 flex-nowrap shrink-0") \
                    .style("width:min(46%, 620px)"):
                campo_busca(**busca)
                _botoes_acoes(acoes)
        else:
            with ui.row().classes("w-full items-center justify-end flex-nowrap") \
                    .style("gap: 0.5rem"):
                _botoes_acoes(acoes)
    return barra


def _botoes_acoes(acoes):
    """Renders the action buttons of `barra_acoes` (fail-soft on bad items).

    Renderiza os botões de ação da `barra_acoes`: cada item de `acoes` —
    tupla `(rotulo, icone, on_click)` ou `(rotulo, icone, on_click,
    tooltip)` — vira um botão primário do tema via `ui_comum.botao` com
    `extra_classes="shrink-0"`. Itens malformados são ignorados com registro
    de erro no loguru, sem derrubar a renderização da tela.
    """
    for item in acoes:
        try:
            rotulo, icone, on_click, *resto = item
            tooltip = resto[0] if resto else None
            botao(rotulo, icone=icone, on_click=on_click, tooltip=tooltip,
                  extra_classes="shrink-0")
        except Exception as e:
            _log().error(f"barra_acoes: ação inválida ignorada ({item!r}): {e}")
