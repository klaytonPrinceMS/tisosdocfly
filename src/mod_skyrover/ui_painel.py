"""Standardized listing panels: GradeTabela (ui.grid) and PainelLista.

Componentes de listagem reutilizáveis, extraídos dos padrões reais dos
módulos (`_painel_usuarios`, `_painel_sessoes`): `GradeTabela` monta uma
`ui.grid` com cabeçalho em caption, células por linha e coluna de ações;
`PainelLista` soma o campo de busca (`aba_modulo.campo_busca`), filtro
callável e paginação client-side com rodapé de contagem e navegação
(`chevron_left`/`chevron_right`). Fail-soft: célula/ação/rodapé com falha
é registrado no loguru sem derrubar o painel. Reusa exclusivamente os
componentes da fábrica central (`ui_comum`) e o helper de busca
(`aba_modulo`) — não cria `ui.button`/`ui.input` crus.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _log():
    """Returns the loguru logger bound to the core module ("skyrover").

    Logger loguru vinculado ao módulo núcleo (`skyrover`), no padrão
    `observabilidade._FMT`. Usado nos blocos `except` dos painéis para
    registrar falhas sem derrubar a renderização (fail-soft).
    """
    from mod_skyrover import observabilidade
    return observabilidade.get_logger("skyrover")


class GradeTabela:
    """Standard `ui.grid` table (caption header + cells + action column).

    Tabela em grid padronizada: `colunas` recebe pares `(rotulo,
    largura_css)` — ex. `("Nome", "1fr")`; largura vazia vira `auto`.
    `montar(dados, celulas, acoes=None)` renderiza o cabeçalho (rótulos em
    `text-caption text-grey-7 font-bold`) e uma linha por item de `dados`:
    `celulas(dado)` cria as células (na ordem das colunas) e, quando
    `acoes` é informado, `acoes(dado, indice)` cria os `botao_icone` da
    coluna final (largura `auto`). Retorna o grid criado; falha em uma
    linha não derruba a grade (fail-soft, loguru).
    """

    def __init__(self, colunas, *, gap="0.5rem", chave_modulo="skyrover"):
        self.chave_modulo = chave_modulo
        self.gap = gap
        self.rotulos = []
        self.larguras = []
        for item in colunas:
            try:
                rotulo, largura = item
            except Exception:
                rotulo, largura = item, ""
            self.rotulos.append(str(rotulo))
            self.larguras.append(largura or "auto")

    def montar(self, dados, celulas, acoes=None, *, classes_extra=""):
        """Renders header + one row per item; returns the grid element.

        `dados` é uma sequência iterável; `celulas(dado)` deve criar
        exatamente `len(self.rotulos)` elementos (células da linha) e
        `acoes(dado, indice)` cria os botões da coluna de ações. `dados`
        vazio (ou `None`) renderiza só o cabeçalho. Falha por linha é
        registrada e a renderização segue (fail-soft).
        """
        from nicegui import ui
        com_acoes = acoes is not None
        specs = " ".join(self.larguras + (["auto"] if com_acoes else []))
        grid = ui.grid(columns=specs).classes(
            "w-full items-center" + (f" {classes_extra}" if classes_extra
                                     else "")).style(f"gap:{self.gap}")
        log = _log()
        with grid:
            for rotulo in self.rotulos:
                ui.label(rotulo).classes(
                    "text-caption text-grey-7 font-bold")
            if com_acoes:
                ui.label("").classes("text-caption text-grey-7 font-bold")
            for i, dado in enumerate(dados or ()):
                try:
                    celulas(dado)
                except Exception as e:
                    log.error(f"GradeTabela: células {i} ignoradas "
                              f"({dado!r}): {e}")
                if com_acoes:
                    try:
                        acoes(dado, i)
                    except Exception as e:
                        log.error(f"GradeTabela: ações {i} ignoradas "
                                  f"({dado!r}): {e}")
        return grid


class PainelLista:
    """Standard listing panel: search + count/pagination + GradeTabela.

    Painel de listagem completo numa coluna `w-full gap-2`: `campo_busca`
    (do `aba_modulo`, `outlined dense clearable debounce=150`) filtrando
    via `filtrar(dado, termo)` quando informado; rodapé
    "N registro(s) — página X/Y" com navegação `chevron_left`/
    `chevron_right` (`por_pagina` registros por página, desabilitados nas
    bordas); e `GradeTabela` com os registros da página. `dados` é um
    CALLABLE reavaliado a cada render — após um CRUD basta chamar
    `atualizar()`. Busca mantém foco (só o corpo é re-renderizado).
    Falhas são registradas no loguru sem derrubar o painel (fail-soft).
    """

    def __init__(self, colunas, dados, *, filtrar=None, por_pagina=10,
                 gap="0.5rem", chave_modulo="skyrover"):
        self._grade = GradeTabela(colunas, gap=gap, chave_modulo=chave_modulo)
        self._dados = dados
        self._filtrar = filtrar
        self._por_pagina = max(1, int(por_pagina))
        self._pagina = 0
        self._termo = ""
        self._celulas = None
        self._acoes = None
        self._classes_extra = ""
        self._container = None

    def montar(self, celulas, acoes=None, *, placeholder="Buscar…",
               classes_extra=""):
        """Builds the panel (search field + body); returns the container.

        `celulas`/`acoes` têm o mesmo contrato de `GradeTabela.montar` e
        ficam retidos para as re-renderizações (busca/paginação/atualizar).
        Retorna a coluna container para o caller inserir na tela.
        """
        from nicegui import ui
        from mod_skyrover.aba_modulo import campo_busca
        self._celulas = celulas
        self._acoes = acoes
        self._classes_extra = classes_extra
        container = ui.column().classes("w-full gap-2")
        self._container = container
        with container:
            campo_busca(placeholder, on_change=self._ao_buscar)
            self._corpo()
        return container

    def atualizar(self):
        """Re-renders the body (count/pagination/grade) from the first page.

        Deve ser chamado após qualquer CRUD que altere a base: `dados` é
        reavaliado e o painel volta à primeira página.
        """
        self._pagina = 0
        self._render_corpo()

    def _ao_buscar(self, e):
        try:
            self._termo = (getattr(e, "value", "") or "").strip()
            self._pagina = 0
            self._render_corpo()
        except Exception as ex:
            _log().exception(f"PainelLista: falha ao aplicar busca: {ex}")

    def _render_corpo(self):
        try:
            if self._container is None:
                return
            self._container.clear()
            with self._container:
                self._corpo()
        except Exception as e:
            _log().exception(f"PainelLista: falha ao re-renderizar corpo: {e}")

    def _base(self):
        base = self._dados() or []
        if self._filtrar and self._termo:
            base = [d for d in base if self._filtrar(d, self._termo)]
        return base

    def _corpo(self):
        from nicegui import ui
        from mod_skyrover.ui_comum import botao_icone
        base = self._base()
        total = len(base)
        total_pag = max(1, (total + self._por_pagina - 1) // self._por_pagina)
        if self._pagina >= total_pag:
            self._pagina = total_pag - 1
        if self._pagina < 0:
            self._pagina = 0
        ini = self._pagina * self._por_pagina
        pagina_dados = base[ini:ini + self._por_pagina]
        try:
            with ui.row().classes("w-full items-center justify-end") \
                    .style("gap: 0.5rem"):
                ui.label(f"{total} registro(s) — página "
                         f"{self._pagina + 1}/{total_pag}").classes(
                    "text-caption text-grey-7")
                btn_ant = botao_icone("chevron_left", on_click=self._anterior,
                                      tooltip="Página anterior")
                btn_prox = botao_icone("chevron_right",
                                       on_click=self._proxima,
                                       tooltip="Próxima página")
                if btn_ant is not None and self._pagina == 0:
                    btn_ant.props("disable")
                if btn_prox is not None and self._pagina >= total_pag - 1:
                    btn_prox.props("disable")
        except Exception as e:
            _log().error(f"PainelLista: rodapé de paginação ignorado: {e}")
        self._grade.montar(pagina_dados, self._celulas, self._acoes,
                           classes_extra=self._classes_extra)

    def _anterior(self):
        if self._pagina > 0:
            self._pagina -= 1
            self._render_corpo()

    def _proxima(self):
        self._pagina += 1
        self._render_corpo()
