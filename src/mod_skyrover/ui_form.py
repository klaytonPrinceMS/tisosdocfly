"""Fluent form builder over the central UI factory (ui_comum) fields.

Construtor fluente de formulários padronizados: acumula especificações de
campos (`campo_texto`, `campo_senha`, `campo_selecao`, `campo_numero`,
`campo_data`) e os monta de uma vez dentro de um container
`ui.column().classes('w-full gap-2')` em `build()`. Cada campo delega à
fábrica central (`ui_comum.campo_texto`/`campo_selecao` — props
`outlined dense`, largura `w-full`, fail-soft com loguru), garantindo a
mesma aparência dos formulários de módulo. `valores()`/`valor(nome)`/
`elemento(nome)` devolvem os inputs por nome de campo, eliminando o
padrão de closures `inp_xxx` repetido nos diálogos CRUD dos módulos.
Campos com falha de montagem são ignorados com registro no loguru
(fail-soft) e simplesmente não entram em `valores()`.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _log():
    """Returns the loguru logger bound to the core module ("skyrover").

    Logger loguru vinculado ao módulo núcleo (`skyrover`), no padrão
    `observabilidade._FMT`. Usado nos blocos `except` do builder para
    registrar falhas de montagem sem derrubar o formulário (fail-soft).
    """
    from mod_skyrover import observabilidade
    return observabilidade.get_logger("skyrover")


class FormularioBuilder:
    """Fluent builder of standardized forms (fields created in `build()`).

    Uso típico dentro de um `dialogo_card`::

        form = (FormularioBuilder()
                .campo_texto("nome", "Nome *", valor=nome)
                .campo_senha("senha", "Senha *")
                .campo_selecao("perfil", "Perfil", ["comum", "admin"]))
        form.build()
        ...
        form.salvar_com(lambda: gest.criar_usuario(**form.valores()))

    As especificações só são executadas em `build()` — os campos nascem
    dentro do container do formulário (ordem de chamada = ordem visual).
    `props`/`largura` são os defaults de fábrica (`outlined dense`,
    `w-full`); `chave_modulo` é repassado quando o campo de baixo nível
    aceitar tema. `valores()` devolve `{nome: value}` apenas dos campos
    montados com sucesso.
    """

    def __init__(self, *, props="outlined dense", largura="w-full"):
        self.props = props
        self.largura = largura
        self._especificacoes = []
        self._campos = []

    def campo_texto(self, nome, rotulo, *, valor=None, chave=None,
                    padrao="", ao_mudar=None, tooltip=None, senha=False,
                    multiline=False, placeholder=None, cor_texto=None,
                    cor_fundo=None):
        """Registers a text/password/multiline field (ui_comum.campo_texto).

        `nome` identifica o campo em `valores()`/`valor()`/`elemento()`;
        os demais parâmetros são repassados à fábrica central
        (`senha=True` cria input com botão exibir/ocultar; `multiline=True`
        cria `ui.textarea`). Encadeável (retorna `self`).
        """
        from mod_skyrover.ui_comum import campo_texto

        def criar():
            return campo_texto(rotulo, valor, chave=chave, padrao=padrao,
                               ao_mudar=ao_mudar, tooltip=tooltip,
                               cor_texto=cor_texto, cor_fundo=cor_fundo,
                               largura=self.largura, multiline=multiline,
                               props=self.props, senha=senha,
                               placeholder=placeholder)
        self._especificacoes.append((nome, criar))
        return self

    def campo_senha(self, nome, rotulo, *, valor=None, tooltip=None,
                    ao_mudar=None):
        """Registers a password field (toggle exibir/ocultar incluso)."""
        return self.campo_texto(nome, rotulo, valor=valor, senha=True,
                                tooltip=tooltip, ao_mudar=ao_mudar)

    def campo_selecao(self, nome, rotulo, opcoes, *, valor=None, chave=None,
                      padrao=None, ao_mudar=None, tooltip=None):
        """Registers a select field (ui_comum.campo_selecao). Encadeável."""
        from mod_skyrover.ui_comum import campo_selecao

        def criar():
            return campo_selecao(rotulo, opcoes, valor, chave=chave,
                                 padrao=padrao, ao_mudar=ao_mudar,
                                 largura=self.largura, props=self.props,
                                 tooltip=tooltip)
        self._especificacoes.append((nome, criar))
        return self

    def campo_numero(self, nome, rotulo, *, valor=None, minimo=None,
                     maximo=None, passo=1, ao_mudar=None, tooltip=None):
        """Registers a numeric field (`ui.number` com min/max/step).

        Mesmo padrão visual dos demais (`props`/`largura` do builder,
        tooltip e `ao_mudar`); falha de montagem registra exception no
        loguru e o campo é ignorado (fail-soft).
        """
        from nicegui import ui

        def criar():
            campo = ui.number(rotulo, value=valor, min=minimo, max=maximo,
                              step=passo)
            if self.props:
                campo.props(self.props)
            if self.largura:
                campo.classes(self.largura)
            if tooltip:
                campo.tooltip(tooltip)
            if ao_mudar:
                campo.on_value_change(ao_mudar)
            return campo
        self._especificacoes.append((nome, criar))
        return self

    def campo_data(self, nome, rotulo, *, valor=None, ao_mudar=None,
                   tooltip=None, mascara="date"):
        """Registers an ISO date field (`ui.input` + máscara Quasar `date`).

        Campo de texto com máscara `date` do Quasar (formato AAAA-MM-DD,
        dígitos posicionais) — evita dependência de picker; `mascara=""`
        desativa. Mesmo padrão visual/soft-fail dos demais campos.
        """
        from mod_skyrover.ui_comum import campo_texto

        def criar():
            campo = campo_texto(rotulo, valor, ao_mudar=ao_mudar,
                                tooltip=tooltip, largura=self.largura,
                                props=self.props)
            if campo is not None and mascara:
                campo.props(f'mask="{mascara}"')
            return campo
        self._especificacoes.append((nome, criar))
        return self

    def build(self):
        """Creates the container and mounts all registered fields.

        Monta `ui.column().classes('w-full gap-2')` com os campos na ordem
        de registro (especificações executadas agora — nada é criado antes
        de `build()`). Campos com falha são ignorados com registro no
        loguru (fail-soft). Retorna `self` para encadeamento.
        """
        from nicegui import ui
        self._campos = []
        container = ui.column().classes("w-full gap-2")
        with container:
            for nome, criar in self._especificacoes:
                try:
                    campo = criar()
                except Exception as e:
                    _log().error(f"FormularioBuilder: campo '{nome}' "
                                 f"ignorado ({criar!r}): {e}")
                    campo = None
                if campo is not None:
                    self._campos.append((nome, campo))
        return self

    def elemento(self, nome):
        """Returns the mounted element for `nome` (or `None`)."""
        for n, campo in self._campos:
            if n == nome:
                return campo
        return None

    def valor(self, nome):
        """Returns the current value of the field `nome` (or `None`)."""
        campo = self.elemento(nome)
        return campo.value if campo is not None else None

    def valores(self):
        """Returns `{nome: value}` of all successfully mounted fields."""
        return {n: c.value for n, c in self._campos}
