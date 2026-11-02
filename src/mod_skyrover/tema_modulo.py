"""Central helper for module theme/appearance.

Helper central de tema/aparência dos módulos.

Padroniza as variáveis de configuração de aparência usadas por TODOS os
módulos, eliminando a duplicação de código e a variação de nomes entre telas.
Cada módulo lê/grava suas chaves em `tb_config` central com um PREFIXO próprio
(mapeado por `PREFIXO_POR_CHAVE`), e os 6 campos são sempre:

    <prefixo>_cor_botao        cor de fundo dos botões (vazio = padrão do
                               próprio módulo, ver `PADROES_TEMA`)
    <prefixo>_cor_texto_botao  cor do texto dos botões (vazio = padrão do módulo)
    <prefixo>_cor_fundo        cor de fundo da página (vazio = padrão da tela)
    <prefixo>_cor_titulo       cor dos títulos
    <prefixo>_btn_tamanho      small | medium | large (vazio = padrão do módulo)
    <prefixo>_texto_header     subtítulo do cabeçalho

Regra de precedência dos BOTÕES: chave do módulo com valor → usa esse valor;
chave vazia → default do parâmetro (ou o padrão do próprio módulo em
`PADROES_TEMA` quando o chamador não informa). O tema do sistema
(`skyrover_*` / "Botões do sistema" em /configuracoes) NÃO é herdado por
outros módulos: cada módulo inicia com as cores do seu próprio padrão.
`cor_fundo`, `cor_titulo` e `texto_header` seguem a mesma regra.

Todos os botões de um módulo usam SEMPRE a mesma cor (não há variação por
botão). A aplicação é imediata (sem restart), pois é lida via `get_config` a
cada renderização da tela. O próprio módulo Skyrover usa o prefixo
`skyrover` (configurado em /configuracoes → Config → "Botões do sistema");
`botao()` cria botões já padronizados a partir do tema.
"""
import sys
import os
from functools import lru_cache

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


# Mapeia a CHAVE do módulo (usada em tb_modulos/rotas) para o PREFIXO de
# configuração em tb_config central. Mantém compatibilidade com o padrão
# documentado na Fase 1 do PLANO.md.
PREFIXO_POR_CHAVE = {
    "blog": "blog",
    "usuarios": "usuarios",
    "auditoria": "auditoria",
    "editar_pdf": "editpdf",
    "empenhos": "empenhos",
    "solicita_impressao": "solicita_impressao",
    "skyrover": "skyrover",
    "tecnico": "tecnico",
    "filas": "filas",
    "lista_telefonica": "lista_telefonica",
    "agregador_noticias": "agregador_noticias",
    "os": "os",
    "estoque": "estoque",
    "dados_abertos": "dados_abertos",
    "hora_certa": "hora_certa",
}


# Padrão de aparência de CADA módulo (cor de botões/texto, título e tamanho).
# Usado quando a chave do módulo está vazia em tb_config: o módulo inicia com
# as SUAS cores padrão (não herda o tema do sistema). O valor de cada módulo
# coincide com o usado nas rotas de administração (main.py, `ui.colors(primary=)`).
# Tema do sistema: PRETO (#000000), como estava antes da experiência de
# estilo visual (27/09/2026). O "Padrão" do menu de estilo significa exatamente
# isto — não impor cor nenhuma e deixar a cor que o ADMINISTRADOR configurou
# para o módulo aparecer. Por isso o padrão voltou a ser o de antes: o estilo
#WhatsApp virou uma OPÇÃO do menu (a "Verde"), não a cor do sistema.
PADROES_TEMA = {
    "skyrover": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
                 "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "blog": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
             "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "usuarios": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
                 "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "auditoria": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
                  "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "editar_pdf": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
                   "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "empenhos": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
                 "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "solicita_impressao": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
                           "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "tecnico": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
                "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "filas": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
              "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "lista_telefonica": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
                         "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "agregador_noticias": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
                           "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "os": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
           "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "estoque": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
                "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "dados_abertos": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
                      "cor_titulo": "#212121", "btn_tamanho": "medium"},
    "hora_certa": {"cor_botao": "#000000", "cor_texto_botao": "#FFFFFF",
                   "cor_titulo": "#212121", "btn_tamanho": "medium"},
}


def prefixo_da_chave(chave_modulo: str) -> str:
    """Returns the `tb_config` prefix for a module key (fallback: the key itself).

    Devolve o prefixo de configuração em `tb_config` central para a chave do
    módulo (mapa `PREFIXO_POR_CHAVE`); chaves desconhecidas usam a própria
    chave como prefixo.
    """
    return PREFIXO_POR_CHAVE.get(chave_modulo, chave_modulo)


@lru_cache(maxsize=32)
def _cfg(chave, default):
    """Reads one central `tb_config` key as stripped text (fail-soft).

    Lê uma chave de `tb_config` central via `get_config` (trim); em falha de
    banco retorna o `default` sem propagar exceção.
    """
    from mod_skyrover.bd_conexao import get_config
    try:
        return (get_config(chave, default) or "").strip() or default
    except Exception:
        return default


@lru_cache(maxsize=16)
def ler_tema(chave_modulo: str, cor_botao=None, cor_texto_botao=None,
             cor_fundo="", cor_titulo=None, btn_tamanho=None,
             texto_header=""):
    """Reads the module's 6 appearance keys; empty keys use the module's own defaults.

    Lê as 6 chaves de aparência do módulo em tb_config central. Os campos de
    BOTÃO (cor_botao, cor_texto_botao, btn_tamanho) seguem a precedência:
    (1) valor não vazio da chave do módulo (`<prefixo>_<campo>`) → (2) default
    do parâmetro OU padrão do próprio módulo (`PADROES_TEMA`) quando o
    chamador não informa. O tema do sistema (`skyrover_*`) NÃO é herdado:
    cada módulo inicia com as cores do seu próprio padrão. `cor_fundo`,
    `cor_titulo` e `texto_header` seguem a mesma regra (vazio = default do
    parâmetro).

    Returns dict com chaves: cor_botao, cor_texto_botao, cor_fundo,
    cor_titulo, btn_tamanho, texto_header.
    """
    p = prefixo_da_chave(chave_modulo)
    pad = PADROES_TEMA.get(chave_modulo, PADROES_TEMA["skyrover"])

    def _botao(campo, default):
        v = _cfg(f"{p}_{campo}", "")
        return v or default

    return {
        "cor_botao": _botao("cor_botao", cor_botao or pad["cor_botao"]),
        "cor_texto_botao": _botao("cor_texto_botao",
                                  cor_texto_botao or pad["cor_texto_botao"]),
        "cor_fundo": _cfg(f"{p}_cor_fundo", cor_fundo),
        "cor_titulo": _cfg(f"{p}_cor_titulo", cor_titulo or pad["cor_titulo"]),
        "btn_tamanho": _botao("btn_tamanho", btn_tamanho or pad["btn_tamanho"]),
        "texto_header": _cfg(f"{p}_texto_header", texto_header),
    }


def salvar_tema(chave_modulo: str, valores: dict) -> None:
    """Saves the module's appearance keys (incl. card colors) to `tb_config`.

    Grava as chaves de aparência do módulo em tb_config central, incluindo
    as cores de card (`cor_fundo_card`/`cor_texto_card`).

    `valores` deve conter as chaves cor_botao/cor_texto_botao/cor_fundo/
    cor_titulo/btn_tamanho/texto_header e, opcionalmente, cor_fundo_card/
    cor_texto_card. Aplica sem restart.
    """
    from mod_skyrover.bd_conexao import set_config
    p = prefixo_da_chave(chave_modulo)
    mapa = {
        "cor_botao": f"{p}_cor_botao",
        "cor_texto_botao": f"{p}_cor_texto_botao",
        "cor_fundo": f"{p}_cor_fundo",
        "cor_titulo": f"{p}_cor_titulo",
        "btn_tamanho": f"{p}_btn_tamanho",
        "texto_header": f"{p}_texto_header",
        "cor_fundo_card": f"{p}_cor_fundo_card",
        "cor_texto_card": f"{p}_cor_texto_card",
    }
    for campo, chave in mapa.items():
        if campo in valores:
            set_config(chave, valores[campo] or "")
    try:
        _cfg.cache_clear()
    except Exception:
        pass
    try:
        ler_tema.cache_clear()
    except Exception:
        pass


def restaurar_tema(chave_modulo: str, defaults: dict) -> None:
    """Restores the module's 6 appearance keys to the provided defaults.

    Restaura os padrões das 6 chaves de aparência do módulo: grava o dict
    `defaults` (normalmente `tema["_defaults"]`, com campos de botão vazios
    = usar o padrão do próprio módulo via `PADROES_TEMA`) através de
    `salvar_tema`. Aplica sem restart.
    """
    salvar_tema(chave_modulo, defaults)


def btn_cls(tamanho: str = "medium") -> str:
    """CSS width classes for buttons by size (single visual standard).

    Classes CSS de largura dos botões por tamanho (`small`/`medium`/
    `large`) — padrão visual único de todos os botões do módulo.
    """
    if tamanho == "small":
        return "min-w-[140px] text-sm"
    if tamanho == "large":
        return "min-w-[220px] text-lg"
    return "min-w-[180px]"


def btn_style(cor_botao: str = "", cor_texto_botao: str = "") -> str:
    """Inline style for buttons: background + text color (always the same).

    Estilo inline dos botões: fundo + cor do texto (sempre os mesmos em
    todo o módulo).
    """
    st = ""
    if cor_botao:
        st += f"background-color:{cor_botao};"
    if cor_texto_botao:
        st += f"color:{cor_texto_botao};"
    return st


def botao(rotulo=None, *, variante="solido", icone=None, on_click=None,
          tooltip=None, chave_modulo="skyrover", extra_classes=""):
    """Builds a themed button from the module's 6 appearance keys.

    Cria um `ui.button` padronizado lendo o tema do módulo (`ler_tema`):
    mesma cor de fundo/texto e mesmo tamanho em todos os botões.
    Variantes: `solido` (preenchido), `contorno` (outline) e `texto`
    (flat, cor do tema); variante desconhecida cai em `primario`.
    `extra_classes` soma classes (ex.: `w-full`). Delega à fábrica central
    `ui_comum.botao` (fonte única das variantes) preservando o visual.
    """
    from mod_skyrover import ui_comum
    v = {"solido": "primario", "contorno": "secundario",
         "texto": "texto"}.get(variante, "primario")
    classes = extra_classes
    if v in ("primario", "secundario"):
        try:
            tamanho = ler_tema(chave_modulo).get(
                "btn_tamanho", "medium") or "medium"
        except Exception:
            tamanho = "medium"
        classes = f"{btn_cls(tamanho)} {extra_classes}".strip()
    return ui_comum.botao(rotulo, variante=v, icone=icone, on_click=on_click,
                          tooltip=tooltip, chave_modulo=chave_modulo,
                          extra_classes=classes, compacto=v != "texto")


def ler_cartao(chave_modulo: str = "skyrover"):
    """Reads the card appearance keys (background + base text).

    Lê as chaves de aparência dos cards (`<prefixo>_cor_fundo_card`,
    `<prefixo>_cor_texto_card`). Retorna dict; fundo vazio = branco."""
    p = prefixo_da_chave(chave_modulo)
    return {
        "cor_fundo_card": _cfg(f"{p}_cor_fundo_card", "#FFFFFF"),
        "cor_texto_card": _cfg(f"{p}_cor_texto_card", ""),
    }


def estilo_cartao(chave_modulo: str = "skyrover") -> str:
    """Inline style for cards: themed background + base text color.

    Estilo inline dos cards: fundo e cor base do texto conforme o tema.
    Textos com classe de cor própria (ex.: `text-grey-7`) mantêm a sua.
    """
    try:
        cartao = ler_cartao(chave_modulo)
    except Exception:
        cartao = {"cor_fundo_card": "#FFFFFF", "cor_texto_card": ""}
    fundo = (cartao.get("cor_fundo_card", "#FFFFFF") or "#FFFFFF").strip()
    st = f"background-color:{fundo};"
    txt = (cartao.get("cor_texto_card", "") or "").strip()
    if txt:
        st += f"color:{txt};"
    return st


def titulo_cartao(texto: str, chave_modulo: str = "skyrover"):
    """Card title label in the module's title color.

    Título de card na cor de título do módulo (`<prefixo>_cor_titulo`).
    """
    from nicegui import ui
    try:
        cor = ler_tema(chave_modulo).get("cor_titulo", "#212121") or "#212121"
    except Exception:
        cor = "#212121"
    return ui.label(texto).classes("text-subtitle1 font-bold").style(f"color:{cor}")


def notificacao_timeout() -> int:
    """System toast display time in seconds (admin-configurable).

    Tempo de exibição dos avisos do sistema em segundos, configurável
    pelo administrador (`notificacao_timeout`, **10–30**, padrão 20).

    O PISO SUBIU DE 1 PARA 10 SEGUNDOS (04/10/2026, pedido do responsável).
    Não é que 10 seja o melhor número — é que 1 segundo é pior que qualquer
    outro: o aviso some antes de a pessoa conseguir LER, e some antes de
    conseguir tirar o mouse de onde foi clicar. Aviso que ninguém viu é o
    mesmo que aviso que não existe.

    O PISO É 10 E NÃO 1 DE PROPÓSITO. Se o `max(1, v)` continuasse, bastava o
    administrador gravar `1` no painel e o problema voltaria inteiro — a
    garantia de 10s tem que estar no CÓDIGO, não numa configuração que
    qualquer um sobrescreve. A faixa configurável passa a 10–30s.

    Vale para instalação nova E para a que já está no ar: o default lido aqui
    cobre banco sem a chave, e a migração em `bd_conexao.py` reescreve o valor
    gravado que estiver abaixo de 10.
    """
    try:
        from mod_skyrover.bd_conexao import get_config
        v = int((get_config("notificacao_timeout", "20") or "20").strip() or 20)
    except Exception:
        return 20
    return min(30, max(10, v))


def _normalizar_tipo_notificacao(tipo):
    """EN: Maps toast-type aliases to canonical Quasar Notify types.

    PT-BR: Converte apelidos de tipo de aviso para os tipos canônicos.

    Achado 5 da análise do dados_abertos: 12 chamadas usam `error`/`erro`,
    que NÃO são tipos do Quasar — o toast aparece, mas sem a cor de erro.
    Corrigir chamada por chamada espalha o conserto; normalizar aqui resolve
    as 12 de uma vez e qualquer futura. Desconhecido passa intacto.
    """
    try:
        return {"error": "negative", "erro": "negative",
                "danger": "negative", "dangerous": "negative",
                "success": "positive", "sucesso": "positive",
                "warn": "warning", "aviso": "warning",
                "alerta": "warning"}.get(str(tipo or "").strip().lower(),
                                         tipo)
    except Exception:
        return tipo


def notificar(msg, tipo="positive", **kwargs):
    """Themed system toast honoring the configured display time.

    Aviso do sistema respeitando o tempo configurado (`notificacao_timeout`).
    Aceita `type=` ou `tipo=` (explícito vence o padrão); demais kwargs
    repassados (`timeout` explícito tem prioridade). Nunca quebra a tela.
    """
    from nicegui import ui
    try:
        if "type" in kwargs:
            tipo = kwargs.pop("type")
        tipo = _normalizar_tipo_notificacao(tipo)
        # SEM converter o tempo aqui, de propósito (04/10/2026).
        #
        # Quem aplica o tempo do sistema é o `nicegui_patch`, que embrulha o
        # `ui.notify` do NiceGUI e converte para milissegundos — a unidade que
        # o Quasar espera. Este `notificar` só repassaria `timeout` em SEGUNDOS
        # e, fazendo isso, burlaria a conversão do patch: o `timeout` explícito
        # sairia em segundos num campo que quer milissegundos, e o aviso
        # morreria em 20ms. Foi o que aconteceu na primeira tentativa.
        #
        # Então: sem `timeout` no kwargs, o patch aplica o tempo do sistema e
        # converte. Com `timeout` explícito, quem passa sabe o que está
        # fazendo e a unidade é dele — mas continua sendo milissegundos, que
        # é o que o Quasar sempre esperou.
        ui.notify(msg, type=tipo, **kwargs)
    except Exception:
        try:
            ui.notify(msg)
        except Exception:
            pass


def bloco_aparencia(usuario_logado, chave_modulo, tema: dict,
                    ao_salvar_descricao="configurações de cores salvas",
                    prefixo_auditoria="skyrover", com_card=True,
                    com_texto_header=True):
    """Renders the standard 'Configurações de cores' card (live preview).

    Renderiza o card PADRÃO "Configurações de cores" — segue o exemplo do
    módulo Skyrover (/configuracoes → Config → Cores): card recolhível
    (`ui_comum.card_admin`) com PRÉVIA AO VIVO (a cada troca de cor o
    exemplo de cabeçalho/card/botões atualiza na hora) e os campos de cores
    no padrão do skyrover: cor geral do módulo (menus e destaques), cor do
    texto do módulo, cor de fundo da página (vazio = herda), cor dos
    títulos, cor de fundo dos cards, cor do texto dos cards (vazio = herda)
    e tamanho dos botões; com `com_texto_header=True`, também o texto do
    cabeçalho. Rodapé padrão de 2 botões (`ui_comum.rodape_salvar_restaurar`):
    "Restaurar padrão" + "Aplicar" — o Aplicar grava EXCLUSIVAMENTE este
    card (via `salvar_tema`, agora com cores de card), audita
    (`prefixo_auditoria`/`configuracao`), notifica e recarrega após 1s.

    `com_card=True` (padrão) envolve o conteúdo em `card_admin` (card
    recolhível do padrão do projeto — título colorido com a cor de título
    do módulo); `com_card=False` renderiza APENAS o conteúdo (legenda +
    prévia + campos + rodapé), para chamadores que já fornecem o card —
    evita card dentro de card. Falha ao ler o tema registra warning e usa
    os padrões (fail-soft). Retorna o callable `salvar`.
    """
    from nicegui import ui
    from mod_skyrover import ui_comum
    from mod_skyrover.bd_manipulador import audit_log
    pad = PADROES_TEMA.get(chave_modulo, PADROES_TEMA["skyrover"])
    if not tema:
        tema = ler_tema(chave_modulo, cor_botao=pad["cor_botao"],
                        cor_texto_botao=pad["cor_texto_botao"], cor_fundo="",
                        cor_titulo=pad["cor_titulo"],
                        btn_tamanho=pad["btn_tamanho"], texto_header="")
    tema.setdefault("_defaults", {})
    cartao = ler_cartao(chave_modulo)
    fundo_card = (cartao.get("cor_fundo_card", "#FFFFFF") or "#FFFFFF").strip()
    texto_card = (cartao.get("cor_texto_card", "") or "").strip()

    _tamanhos = {0: "small", 1: "medium", 2: "large"}
    estado = {}
    _estado_tam = {"valor": {"small": 0, "medium": 1, "large": 2}.get(
        tema.get("btn_tamanho", "medium"), 1)}

    def _pv(campo, default):
        """Live preview value: unsaved field state, else the theme value."""
        v = estado.get(campo)
        if v is None:
            v = tema.get(campo, default)
        return (v or default or "").strip() or (default or "")

    @ui.refreshable
    def _previa():
        """Live preview: header/card/buttons reflecting the unsaved colors.

        Prévia ao vivo do card "Configurações de cores": renderiza um
        exemplo de cabeçalho (barra na cor geral do módulo), card (fundo/
        texto/título) e botões (sólido + contorno) usando os valores
        pendentes dos campos (`_pv`), atualizando a cada troca de cor."""
        c_btn = _pv("cor_botao", pad["cor_botao"])
        c_txt = _pv("cor_texto_botao", pad["cor_texto_botao"])
        c_fundo = _pv("cor_fundo", "")
        c_tit = _pv("cor_titulo", pad["cor_titulo"])
        c_fundo_card = _pv("cor_fundo_card", "#FFFFFF")
        c_texto_card = _pv("cor_texto_card", "")
        c_tam = _pv("btn_tamanho", "medium")
        with ui.element("div").classes("rounded-lg w-full overflow-hidden") \
                .style(f"background:{c_fundo or '#EEEEEE'}"):
            with ui.row().classes("items-center px-4 py-2 w-full") \
                    .style(f"background:{c_btn}; gap: 0.5rem"):
                ui.icon("extension").style(f"color:{c_txt}")
                ui.label("Exemplo do módulo").classes("font-bold") \
                    .style(f"color:{c_txt}")
            with ui.element("div").classes("w-full").style("padding:0.75rem"):
                with ui.element("div").classes("rounded-lg w-full") \
                        .style(f"background:{c_fundo_card};"
                               + (f"color:{c_texto_card};" if c_texto_card else "")
                               + "padding:0.75rem"):
                    ui.label("Exemplo de card") \
                        .style(f"color:{c_tit};font-weight:700")
                    ui.label("Texto apresentado nos cards.")
                    with ui.row().classes("items-center flex-wrap") \
                            .style("gap: 0.5rem"):
                        ui.button("Botão exemplo", icon="info") \
                            .props("unelevated no-caps") \
                            .classes(btn_cls(c_tam)) \
                            .style(btn_style(c_btn, c_txt))
                        ui.button("Contorno", icon="open_in_new") \
                            .props("outline no-caps") \
                            .classes(btn_cls(c_tam)) \
                            .style(f"color:{c_btn};border-color:{c_btn};")

    def _mudou(campo):
        """Returns a field-change callback that refreshes the live preview.

        Devolve o callback de `ao_mudar` de um campo de cor: guarda o valor
        pendente em `estado` e atualiza a prévia ao vivo (silencioso se a
        prévia ainda não foi renderizada)."""
        def _cb(e):
            estado[campo] = e.value
            try:
                _previa.refresh()
            except Exception:
                pass
        return _cb

    def _mudou_tamanho(e):
        """Field-change callback for the button-size selector (live preview).

        Callback do seletor de tamanho dos botões: converte o índice
        selecionado (`0/1/2`) para `small/medium/large`, guarda em `estado`
        e atualiza a prévia ao vivo."""
        _estado_tam["valor"] = e.value
        estado["btn_tamanho"] = _tamanhos[e.value]
        try:
            _previa.refresh()
        except Exception:
            pass

    def _conteudo():
        """Renders the card content: legend, live preview, fields and footer.

        Monta o conteúdo do card "Configurações de cores": legenda, prévia
        ao vivo, grid de campos (cores + tamanho + texto do cabeçalho
        opcional) e o rodapé padrão de 2 botões ("Restaurar padrão" +
        "Aplicar"). Retorna o callable `salvar` (grava EXCLUSIVAMENTE este
        card via `salvar_tema`, audita, notifica e recarrega após 1 s)."""
        ui.label("Selecione as cores e veja a prévia ao vivo — o exemplo "
                 "acima acompanha cada alteração. Tudo vale sem reiniciar "
                 "após Aplicar.").classes(
            "text-caption text-grey-7 max-w-3xl -mt-2")
        _previa()
        with ui.grid().classes(
                "w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-4") \
                .style("gap: 1.25rem"):
            inp_cor_botao = ui_comum.campo_cor(
                "Cor geral do módulo (menus e destaques)",
                valor=tema.get("cor_botao", ""), ao_mudar=_mudou("cor_botao"))
            inp_cor_txt = ui_comum.campo_cor(
                "Cor do texto do módulo",
                valor=tema.get("cor_texto_botao", ""),
                ao_mudar=_mudou("cor_texto_botao"))
            inp_cor_fundo = ui_comum.campo_cor(
                "Cor de fundo da página (vazio = herda)",
                valor=tema.get("cor_fundo", ""), ao_mudar=_mudou("cor_fundo"))
            inp_cor_titulo = ui_comum.campo_cor(
                "Cor dos títulos",
                valor=tema.get("cor_titulo", ""), ao_mudar=_mudou("cor_titulo"))
            inp_cor_fundo_card = ui_comum.campo_cor(
                "Cor de fundo dos cards",
                valor=fundo_card, ao_mudar=_mudou("cor_fundo_card"))
            inp_cor_texto_card = ui_comum.campo_cor(
                "Cor do texto dos cards (vazio = herda)",
                valor=texto_card, ao_mudar=_mudou("cor_texto_card"))
            sel_tamanho = ui_comum.campo_selecao(
                "Tamanho dos botões",
                {0: "Pequeno", 1: "Médio", 2: "Grande"},
                valor=_estado_tam["valor"], ao_mudar=_mudou_tamanho)
            inp_texto_header = None
            if com_texto_header:
                inp_texto_header = ui_comum.campo_texto(
                    "Texto do cabeçalho", valor=tema.get("texto_header", ""))

        _estado_tema = {"ocupado": False}

        def salvar():
            """Applies ONLY this card's colors: saves, audits, reloads after 1s.

            Grava EXCLUSIVAMENTE as cores deste card via `salvar_tema`
            (incluindo `cor_fundo_card`/`cor_texto_card`), audita
            (`prefixo_auditoria`/`configuracao`), notifica e recarrega após
            1 segundo. Falha de gravação propaga para o chamador (o rodapé
            padrão trata e notifica negativo)."""
            valores = {
                "cor_botao": inp_cor_botao.value or "",
                "cor_texto_botao": inp_cor_txt.value or "",
                "cor_fundo": inp_cor_fundo.value or "",
                "cor_titulo": inp_cor_titulo.value or "",
                "btn_tamanho": _tamanhos[_estado_tam["valor"]],
                "cor_fundo_card": inp_cor_fundo_card.value or "#FFFFFF",
                "cor_texto_card": inp_cor_texto_card.value or "",
            }
            if inp_texto_header is not None:
                valores["texto_header"] = inp_texto_header.value or ""
            if _estado_tema["ocupado"]:
                notificar("Aguarde a operação em andamento…", tipo="warning")
                return
            _estado_tema["ocupado"] = True
            try:
                salvar_tema(chave_modulo, valores)
            finally:
                _estado_tema["ocupado"] = False
            try:
                audit_log(usuario_logado, prefixo_auditoria, "configuracao",
                          ao_salvar_descricao)
            except Exception:
                pass
            notificar("Cores aplicadas (vale sem reiniciar)", tipo="positive")
            ui.timer(1.0, lambda: ui.navigate.reload(), once=True)

        def restaurar():
            """Restores the module's default colors and reloads after 1s.

            Restaura os padrões do card: preenche `_defaults` a partir de
            `PADROES_TEMA` quando o chamador não forneceu (campos de botão
            vazios = padrão do próprio módulo), grava via `restaurar_tema`
            e recarrega após 1 segundo."""
            defaults = dict(tema.get("_defaults") or {})
            defaults.setdefault("cor_botao", "")
            defaults.setdefault("cor_texto_botao", "")
            defaults.setdefault("cor_fundo", "")
            defaults.setdefault("cor_titulo", pad["cor_titulo"])
            defaults.setdefault("btn_tamanho", "")
            defaults.setdefault("texto_header", "")
            defaults.setdefault("cor_fundo_card", "#FFFFFF")
            defaults.setdefault("cor_texto_card", "")
            restaurar_tema(chave_modulo, defaults)
            ui.timer(1.0, lambda: ui.navigate.reload(), once=True)

        ui_comum.rodape_salvar_restaurar(salvar, restaurar=restaurar,
                                         chave_modulo=chave_modulo)
        return salvar

    if com_card:
        with ui_comum.card_admin("Configurações de cores", icone="palette",
                                 chave_modulo=chave_modulo, grade=False,
                                 aberto=False):
            fn_salvar = _conteudo()
    else:
        fn_salvar = _conteudo()
    return fn_salvar


def campo_modulo(usuario_logado, chave_modulo, nome_atual=None, icone_atual=None,
                 ativo_atual=None):
    """Renders the 'Module edition' panel in the module admin tab.

    Cupê 'Edição do módulo' na aba Administração: nome, ícone e status.

    Permite ao administrador do módulo alterar nome de exibição, ícone e
    status (ativo/desativado) registrados em `tb_modulos` — hoje só disponível
    no painel central `/configuracoes`. Se os valores não forem informados,
    são carregados automaticamente de `tb_modulos`. O rodapé Salvar é o
    padronizado (`ui_comum.rodape_salvar_restaurar`).
    """
    from nicegui import ui
    from mod_skyrover import autenticacao
    from mod_skyrover import ui_comum
    from mod_skyrover.bd_manipulador import audit_log
    from mod_skyrover.bd_conexao import get_connection

    if nome_atual is None or icone_atual is None or ativo_atual is None:
        try:
            c = get_connection()
            row = c.execute("SELECT nome, icone, ativo FROM tb_modulos WHERE chave=?",
                            (chave_modulo,)).fetchone()
            c.close()
            if row:
                if nome_atual is None:
                    nome_atual = row[0] or chave_modulo
                if icone_atual is None:
                    icone_atual = row[1] or "extension"
                if ativo_atual is None:
                    ativo_atual = bool(row[2])
        except Exception:
            pass
    nome_atual = nome_atual or chave_modulo
    icone_atual = icone_atual or "extension"
    ativo_atual = bool(ativo_atual)

    with ui.expansion("Edição do módulo", icon="settings_applications").classes("w-full"):
        inp_nome = ui_comum.campo_texto("Nome de exibição do módulo",
                                        nome_atual or "")
        inp_icone = ui_comum.campo_texto(
            "Ícone (Material Icons)", icone_atual or "extension",
            tooltip="Nome do ícone Material, ex.: article, folder_open, print")
        sw_ativo = ui.switch("Módulo ativo (visível para os usuários)",
                             value=bool(ativo_atual))

        def salvar():
            from mod_skyrover.bd_conexao import get_connection
            autenticacao.set_modulo_ativo(usuario_logado, chave_modulo,
                                          bool(sw_ativo.value))
            try:
                c = get_connection()
                c.execute(
                    "UPDATE tb_modulos SET nome=?, icone=? WHERE chave=?",
                    ((inp_nome.value or "").strip() or chave_modulo,
                     (inp_icone.value or "extension").strip(), chave_modulo))
                c.commit(); c.close()
            except Exception:
                pass
            try:
                audit_log(usuario_logado, "skyrover", "editar_modulo",
                          f"{chave_modulo}: nome='{inp_nome.value.strip()}' "
                          f"icone='{inp_icone.value.strip()}' "
                          f"ativo={int(bool(sw_ativo.value))}")
            except Exception:
                pass
            notificar("Módulo atualizado", tipo="positive")
            ui.timer(0.1, lambda: ui.navigate.reload(), once=True)

        ui_comum.rodape_salvar_restaurar(salvar, chave_modulo=chave_modulo,
                                         rotulo_salvar="Salvar módulo")
    return salvar


def _misturar(cor, fracao, para_branco):
    """Mistura `cor` com branco (ou preto), na mesma matiz.

    `fracao` e a participacao final da outra cor: 0 devolve `cor` intacta,
    1 devolve branco (ou preto) puro. Devolve `""` para cor vazia ou mal
    formada — quem chama cai no padrao do Quasar."""
    h = (cor or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return ""
    try:
        canais = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return ""
    alvo = 255 if para_branco else 0
    saida = [max(0, min(255, int(round(v + (alvo - v) * fracao))))
             for v in canais]
    return "#{:02x}{:02x}{:02x}".format(*saida)


def tom_clara(cor, fracao=0.5):
    """Clareia uma cor hexadecimal, mantendo a matiz.

    Para montar o par cor-fundo/cor-texto de rotulos que seguem o tema: o
    rotulo continua sendo "a cor do sistema", mas no tom que da leitura.

    `fracao` e quanto da cor se mistura com o branco — 0 devolve a cor
    intacta, 1 devolve branco puro. Para ESCURECER, use `tom_escura`.

    Devolve `""` para cor vazia ou fora do formato — quem chama cai no
    padrao do Quasar."""
    return _misturar(cor, fracao, True)


def tom_escura(cor, fracao=0.5):
    """Escurece uma cor hexadecimal, mantendo a matiz.

    O par de `tom_clara`: `fracao` e quanto da cor se mistura com o preto
    (0 = intacta, 1 = preto puro). Ver `_misturar`."""
    return _misturar(cor, fracao, False)


def _hex_para_rgb(cor):
    """Converts a hex color (#RGB/#RRGGBB) to an (r, g, b) tuple."""
    h = (cor or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (0, 0, 0)


def paleta_escura(tema):
    """Gera a paleta do MODO ESCURO na ordem MAIS ESCURO → MAIS CLARO,
    do que está mais ao fundo para o que está mais à frente:

      1. cor geral do módulo  → 2. fundo da página → 3. fundo do card
      → 4. cor do título → 5. texto do módulo → 6. texto do card.

    O `tema` é um dict de `ler_tema` (chaves cor_botao/cor_fundo/cor_titulo/
    cor_texto_botao/cor_fundo_card/cor_texto_card). Retorna um dict com as 6
    camadas prontas para o CSS do modo escuro."""
    tema = tema or {}
    base = _hex_para_rgb(tema.get("cor_botao") or "#000000")
    luminancia = sum(base) / 3
    escuro = luminancia < 128  # cor geral escura → camadas escuras neutras
    return {
        "cor_geral": tema.get("cor_botao") or "#000000",
        "fundo_pagina": "#161616" if escuro else "#2a2a2a",
        "fundo_card": "#242424" if escuro else "#3a3a3a",
        "cor_titulo": "#c8c8c8",
        "texto_modulo": "#dcdcdc",
        "texto_card": "#f2f2f2",
    }


def _limpar_caches_tema():
    """Limpa os caches derivados de `tb_config` após gravação.

    Registrado em `bd_conexao` via `registrar_hook_config` (o núcleo
    nunca importa este módulo — sem ciclo núcleo→tema)."""
    _cfg.cache_clear()
    ler_tema.cache_clear()


try:
    from mod_skyrover import bd_conexao as _bd_conexao
    _bd_conexao.registrar_hook_config(_limpar_caches_tema)
except Exception:
    pass
