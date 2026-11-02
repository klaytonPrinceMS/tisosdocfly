"""User management screen — soft CRUD with per-module access control.

Tela de Gestão de Cadastro de Usuários — soft CRUD completo. Barra superior
fixa (abas | busca instantânea | botão Novo usuário) e tudo no topo da
página — sem precisar rolar a lista para acessar controles. Componentes,
diálogos, ações de linha, rodapés, tema/aparência e notificações seguem o
padrão central: `mod_skyrover.ui_comum` (`botao`, `botao_icone`,
`dialogo_card`, `rodape_dialogo`) e `mod_skyrover.tema_modulo`
(`ler_tema`, `notificar` — timeout configurável em `notificacao_timeout`).
Botões seguem o tema do sistema por padrão: chaves `usuarios_cor_botao`,
`usuarios_cor_texto_botao` e `usuarios_btn_tamanho` vazias herdam as chaves
`skyrover_*` ("Botões do sistema" em /configuracoes); os campos do cupê
Administração são o override do módulo. Acesso: administrador geral ou
administrador do módulo 'usuarios'.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import math
import re
import unicodedata

from nicegui import ui

from mod_skyrover import autenticacao
from mod_skyrover import observabilidade
from mod_skyrover.bd_manipulador import audit_log
from mod_skyrover.aba_modulo import cabecalho, campo_busca
from mod_skyrover import tema_modulo
from mod_skyrover.tema_modulo import ler_tema, notificar
from mod_skyrover.ui_comum import botao, botao_icone, dialogo_card, \
    dialogo_formulario, rodape_dialogo, rodape_salvar_restaurar
from mod_gest_cad_usuario import bd_manipulador as gest
# 04/10/2026 — os campos da folha no cadastro, somente texto. Importado no
# topo (e não dentro da função) porque a lista de usuários renderiza vinte
# linhas por página: importar dentro do laço faria o Python resolver o mesmo
# módulo vinte vezes, e o custo é de um `sys.path` + um `import` por linha.
from mod_gest_cad_usuario import dados_folha_tela
from mod_gest_cad_usuario.dados_folha_tela import bloco_dados_folha_resumido as _folha_resumido

log = observabilidade.get_logger("gest_cad_usuario")

# Grade responsiva dos cartões de telefone do admin (16/10/2026): 3 colunas
# em tela grande, 2 em média (≤1100px) e 1 no celular (≤720px). CSS injetado
# UMA vez no `<head>` (guarda global: o bloco é instanciado a cada abertura
# do diálogo de edição, e sem a guarda o `<style>` duplicaria).
_CSS_GRADE_TELS = """
<style>
.grade-tels-admin{display:grid;gap:.5rem;grid-template-columns:repeat(4,minmax(0,1fr))}
@media (max-width:1100px){.grade-tels-admin{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:720px){.grade-tels-admin{grid-template-columns:minmax(0,1fr)}}
</style>
"""
_GRADE_TELS_CSS_OK = False


def _css_grade_tels_admin():
    """Garante o CSS da grade 4→2→1 no `<head>` (uma vez por processo)."""
    global _GRADE_TELS_CSS_OK
    try:
        if _GRADE_TELS_CSS_OK:
            return
        ui.add_head_html(_CSS_GRADE_TELS)
        _GRADE_TELS_CSS_OK = True
    except Exception as e:
        log.exception(f"_css_grade_tels_admin: CSS não injetado | {e}")


# Linha de adicionar telefone em telas pequenas (16/10/2026, pedido do
# responsável): composto, checkboxes e Adicionar em linha CHEIA (≤640px).
# O `!important` é obrigatório: os itens carregam `flex`/`min-width` inline,
# que ganha de qualquer regra da folha sem ele.
_CSS_TEL_NOVO = """
<style>
@media (max-width: 640px){
  .tel-novo-linha > .tel-novo-comp,
  .tel-novo-linha > .tel-novo-check,
  .tel-novo-linha > .tel-novo-add{flex:1 1 100% !important;max-width:100% !important;min-width:0 !important}
}
</style>
"""
_TEL_NOVO_CSS_OK = False


def _injetar_css_tel_novo():
    """Garante o CSS da linha de adicionar no `<head>` (uma vez por processo)."""
    global _TEL_NOVO_CSS_OK
    try:
        if _TEL_NOVO_CSS_OK:
            return
        ui.add_head_html(_CSS_TEL_NOVO)
        _TEL_NOVO_CSS_OK = True
    except Exception as e:
        log.exception(f"_injetar_css_tel_novo: CSS não injetado | {e}")


def _fundo_card_tel():
    """Fundo do cartão na cor do módulo, bem clara (16/10/2026).

    Lê a cor padrão do usuário/módulo (`ler_tema("usuarios")` → `cor_botao`)
    e clareia ~85% com `tom_clara` — o cartão carrega a identidade do tema
    sem brigar com o texto escuro. Fail-soft: vazio = cartão padrão.
    """
    try:
        tema = ler_tema("usuarios")
        base = (tema.get("cor_botao") or "").strip()
        claro = tema_modulo.tom_clara(base, 0.85) if base else ""
        return f"background:{claro};" if claro else ""
    except Exception as e:
        log.exception(f"_fundo_card_tel: sem fundo do tema | {e}")
        return ""

OPCOES_PAPEL = {"": "— sem acesso —", "comum": "Comum", "administrador": "Administrador do módulo"}
ROTULOS_PAPEL = {"comum": "Comum", "administrador": "Administrador"}
_MAP_MODULOS = {}  # cache lazy: {chave: (nome, icone)}

def _nomes_modulos():
    """Mapa chave → (nome, icone) dos módulos registrados — populado na primeira chamada."""
    if not _MAP_MODULOS:
        try:
            for chave, nome, icone, _rota, _ativo in autenticacao.modulos_registrados():
                _MAP_MODULOS[chave] = (nome, icone)
        except Exception as e:
            log.exception(f"_nomes_modulos: falha ao popular mapa de módulos | {e}")
    return _MAP_MODULOS

def _norm(s):
    """Accents/punctuation-insensitive lowercase for search matching.

    Minúsculas, sem acentos e com pontuação vira espaço —
    buscar 'jose' acha 'José'; 'silva social' acha 'Silva-Social'."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", s))

# ============ FICHA DO USUÁRIO — cores dos selos de acesso ============
# Pedido (10/10/2026): administrador geral com fundo VERMELHO e LETRA BRANCA;
# administrador de um módulo, LARANJA com letra preta; comum, VERDE com letra
# preta; e os fundos em tons claros.
#
# A cor vem do PAPEL QUE A PESSOA TEM NAQUELE MÓDULO, e não do perfil global:
# alguém que administra o Blog e é comum nos demais precisa enxergar, de uma
# olhada, que pode mexer num e não nos outros. Uma cor só para a pessoa
# inteira apagaria essa diferença — que é a informação.
#
# "Tom claro" e "letra branca" não cabem juntos, e a escolha está registrada
# aqui porque é uma escolha, não um descaso. Onde a letra é PRETA (laranja e
# verde) o tom claro funciona muito bem e foi usado: `#FFB74D` e `#A5D6A7`.
# Onde a letra é BRANCA, um fundo claro derruba o rótulo: `#FFCDD2` com
# branco dá 2,2:1 de contraste e o texto some — o mesmo defeito que o badge
# de "senha provisória" já teve aqui (ver o bloco dele na lista). Então o
# vermelho para só até `#D32F2F`, o vermelho mais claro que ainda dá 4,9:1
# com o branco e continua reconhecível como vermelho. Preferi letra legível
# a cumprir "tons claros" às cegas.
CORES_ACESSO = {
    "administrador_geral": "#D32F2F",  # fundo vermelho + LETRA BRANCA
    "administrador": "#FFB74D",       # fundo laranja + LETRA PRETA
    "comum": "#A5D6A7",               # fundo verde   + LETRA PRETA
}
TEXTO_ACESSO = {
    "administrador_geral": "#FFFFFF",
    "administrador": "#000000",
    "comum": "#000000",
}

def _cor_do_acesso(papel, eh_geral):
    """(fundo, letra) do selo: geral > administrador do módulo > comum."""
    chave = ("administrador_geral" if eh_geral
             else "administrador" if (papel or "").strip() == "administrador"
             else "comum")
    return CORES_ACESSO[chave], TEXTO_ACESSO[chave]

def _rotulo_do_papel(papel, eh_geral):
    """Nome do papel em texto — é o que o tooltip do selo mostra.

    A cor carrega o papel de relance, mas cor sozinha não serve para quem
    não distingue laranja de verde (e o verde do vermelho é justamente o par
    mais comum de daltonismo). O texto no tooltip devolve a informação a
    quem precisa dela sem mudar o desenho que foi pedido.
    """
    if eh_geral:
        return "Administrador geral — acesso a todos os módulos"
    chave = "administrador" if (papel or "").strip() == "administrador" else "comum"
    return f"{ROTULOS_PAPEL.get(chave, chave)} deste módulo"

def _selo_modulo(nome_mod, papel, eh_geral):
    """Selo colorido do módulo, dentro da ficha do usuário.

    `style()` e não `bg-color`/`text-color`: medido nesta tela, essas props do
    Quasar não pegam e o fundo fica transparente (o mesmo achado do badge de
    "senha provisória"). `style` é CSS direto e leva a cor exata.
    """
    fundo, letra = _cor_do_acesso(papel, eh_geral)
    return ui.label(nome_mod).classes(
        "text-caption font-medium no-wrap rounded-md px-2 py-1"
    ).style(f"background:{fundo};color:{letra}").tooltip(
        _rotulo_do_papel(papel, eh_geral))

def _campo_par(rotulo, valor):
    """Metade de uma linha da grade de duas colunas da ficha."""
    with ui.column().classes("gap-0 min-w-0"):
        ui.label(rotulo).classes("text-caption text-grey-6 leading-none")
        ui.label((valor or "—")).classes(
            "text-body2 font-medium break-words")

def _rotulo_situacao(ativo, deletado):
    """Situação da conta em texto — usada na lista e na ficha do usuário."""
    if deletado:
        return "excluído (soft)"
    return "ativo" if ativo else "bloqueado"

def _telefone_exibicao(fone):
    """Telefone formatado para leitura, com queda para o bruto."""
    try:
        from mod_skyrover import telefone as _tel_fmt
        return _tel_fmt.formatar_para_exibicao(fone) or "—"
    except Exception:
        return fone or "—"

def _grade_modulos(acessos, eh_geral):
    """Os módulos da pessoa, em grade de duas colunas, cada selo colorido.

    O texto do selo é o NOME do módulo (o que a pessoa lê) e a cor é o PAPEL
    que ela tem nele: verde para comum, laranja para administrador do módulo,
    vermelho para o administrador geral, que acessa tudo.
    """
    mapa_mod = _nomes_modulos()
    selos = []
    for trecho in (acessos or "").split(","):
        trecho = trecho.strip()
        if ":" not in trecho:
            continue
        chave_mod, papel_mod = trecho.rsplit(":", 1)
        nome_mod, _icone_mod = mapa_mod.get(chave_mod, (chave_mod, "extension"))
        selos.append((nome_mod, papel_mod))
    if not selos:
        # Admin geral não tem vínculo linha a linha: o acesso vem do perfil.
        # Mesmo assim ele precisa do SELO vermelho/branco — é a leitura que
        # responde "esta pessoa mexe em tudo?" de relance, e trocar o selo por
        # uma frase cinza fazia o administrador geral parecer o mais restrito
        # dos três, que é o oposto do que ele é.
        if eh_geral:
            ui.label("Administrador geral — acesso a todos os módulos").classes(
                "text-caption font-medium no-wrap rounded-md px-2 py-1"
            ).style(f"background:{CORES_ACESSO['administrador_geral']};"
                    f"color:{TEXTO_ACESSO['administrador_geral']}")
        else:
            ui.label("—").classes("text-caption text-grey-6")
        return
    with ui.grid(columns=2).classes("w-full").style("gap: 0.5rem 0.75rem"):
        for nome_mod, papel_mod in selos:
            _selo_modulo(nome_mod, papel_mod, eh_geral)

def _dlg_dados_usuario(nome, *, perfil, ativo, email, fone, cadastro,
                       acessos, deletado):
    """Abre a ficha completa da pessoa — o que era tooltip de hover (10/10/2026).

    A troca é de tipo de dado, não de gosto: tooltip é para UMA linha. O que
    esta ficha carrega é a identidade inteira da pessoa (grade de cadastro +
    folha completa + módulos), e o overlay tinha dois defeitos que o clique
    resolve de uma vez — sumia no primeiro movimento do mouse (quem tentava
    ler a remuneração perdia a linha) e sumia junto com a página no scroll da
    lista. Diálogo também é o que torna o clique acessível por teclado: um
    tooltip só existe para quem tem mouse, e a lista é lida por quem
    administra.

    Os dados chegam por parâmetro em vez de nova consulta: a linha da lista já
    os tem, e reabrir a ficha não deve custar uma leitura ao banco.
    """
    try:
        with dialogo_card(largura="w-[88vw] max-w-[900px]",
                          chave_modulo="usuarios") as (dlg, card):
            with ui.column().classes("w-full gap-3"):
                ui.label(f"@{nome}").classes("text-h6 font-bold")
                ui.separator().classes("my-0")

                # --- grade de DUAS COLUNAS: o par pedido, linha a linha ---
                with ui.grid(columns=2).classes("w-full").style(
                        "gap: 0.75rem 2rem"):
                    _campo_par("Usuário", f"@{nome}")
                    _campo_par("Data do cadastro", cadastro)
                    _campo_par("Perfil global", (perfil or "").replace("_", " "))
                    _campo_par("Situação", _rotulo_situacao(ativo, deletado))
                    _campo_par("E-mail", email)
                    _campo_par("Telefone", _telefone_exibicao(fone))

                # --- folha inteira (secretaria, cargo, remuneração...) ---
                _folha_resumido(nome)

                # --- módulos, em duas colunas ---
                ui.separator().classes("my-0")
                ui.label("Acesso aos módulos").classes(
                    "text-subtitle2 font-bold text-grey-8")
                _grade_modulos(acessos, eh_geral=(perfil == "administrador_geral"))
            dlg.open()
    except Exception as e:
        log.exception(f"_dlg_dados_usuario: falha ao montar a ficha de {nome} | {e}")
        notificar(f"Erro ao abrir os dados de '{nome}'.", tipo="negative")

def mostrar_tela(user_nome: str, perfil_global: str = ""):
    """Renders the user management screen (admin-only entry point).

    Renderiza a tela de gestão de usuários (somente administradores).
    Entry point protegido: delega a `_mostrar_tela_segura` com
    try/except + notificação."""
    try:
        _mostrar_tela_segura(user_nome, perfil_global)
    except Exception:
        log.exception("mostrar_tela: falha ao montar a tela de usuários")
        notificar("Erro ao carregar a tela de usuários", tipo="error")

def _mostrar_tela_segura(user_nome: str, perfil_global: str = ""):
    """Safe body of `mostrar_tela` (access gate + full layout).

    Corpo de `mostrar_tela`, isolado para o entry point proteger.

    Monta a tela completa: bloqueio de acesso para não administradores,
    tema/aparência do módulo `usuarios` via `ler_tema` (cor primária
    configurável em `usuarios_cor_botao`; vazia, herda o tema do sistema
    `skyrover_*`, padrão #000000), cabeçalho, barra superior com
    abas/busca/botão Novo usuário e os painéis de usuários, sessões ativas
    e administração.
    """
    if not (perfil_global == "administrador_geral"
            or autenticacao.eh_admin_do_modulo(user_nome, "usuarios")):
        _acesso_negado()
        return
    eh_admin_geral = (perfil_global == "administrador_geral"
                      or autenticacao.perfil_global_de(user_nome) == "administrador_geral")

    tema = ler_tema("usuarios", cor_botao="#000000", cor_texto_botao="#FFFFFF",
                    texto_header="Cadastro de usuários, papéis e acessos por módulo (soft CRUD · LGPD).")
    ui.colors(primary=tema["cor_botao"])

    t_cor_botao = tema["cor_botao"]
    t_cor_titulo = tema["cor_titulo"]
    t_cor_fundo_cab = tema["cor_fundo"]
    t_texto_header = tema["texto_header"]

    estado_busca = {"valor": ""}
    refreshers = {}  # nome -> função de atualização (registrada por cada aba)

    def ao_digitar(e):
        try:
            estado_busca["valor"] = e.value or ""
            for chave in ("usuarios",):
                if chave in refreshers:
                    try:
                        refreshers[chave]()
                    except Exception as ex:
                        log.exception(f"ao_digitar: falha ao atualizar aba '{chave}' | {ex}")
        except Exception:
            log.exception("ao_digitar: falha ao processar busca")
            notificar("Erro ao processar busca", tipo="negative")

    def novo_usuario():
        try:
            _dlg_novo(user_nome, lambda: [refreshers[k]() for k in
                                          ("usuarios",) if k in refreshers])
        except Exception:
            log.exception("novo_usuario: falha ao abrir diálogo de criação")
            notificar("Erro ao abrir criação de usuário", tipo="negative")

    with ui.column().classes("w-full p-6 gap-4"):
        cabecalho("Gestão de Usuários",
                   t_texto_header,
                   chave_modulo="usuarios", cor_titulo=t_cor_titulo, cor_fundo=t_cor_fundo_cab)

        # ===== BARRA SUPERIOR (linha única, inline sem quebra): abas à esquerda | busca + botão à direita =====
        with ui.row().classes("w-full items-center justify-between gap-4 flex-nowrap bg-white rounded-lg shadow-sm px-3 py-1").style("min-width: 0"):
            # Terceira aba — FOLHA: contratos para revisar, histórico de
            # movimentos e evolução salarial. Existe porque a folha deixou de
            # ser um script de boot e passou a ser um dado com histórico: a
            # demissão é movimento, o salário tem evolução, e o nome igual
            # pode ser homônimo. Tudo isso precisa de um lugar para ser lido.
            #
            # O contador de "para revisar" fica na aba porque uma decisão
            # pendente que não aparece no rótulo é uma decisão que não acontece.
            try:
                _tem_folha = gest.folha_tem_dados()
                _revisar = (gest.contar_contratos_para_revisar()
                            if _tem_folha else 0)
            except Exception:
                log.exception("mostrar_tela: falha ao consultar dados da folha")
                _tem_folha = False
                _revisar = 0
            with ui.tabs().props("dense inline-label").classes(
                    "min-w-0 overflow-x-auto shrink") as tabs:
                tab_users = ui.tab("Usuários", icon="people")
                tab_sessoes = ui.tab("Sessões Ativas", icon="wifi")
                # A aba Folha só existe quando há dado de folha carregado.
                # Sem `dados/` nem `fonte_folha.json`, uma aba vazia é ruído
                # e uma consulta a tabela vazia pode falhar.
                tab_folha = None
                if _tem_folha:
                    rotulo_folha = (f"Folha ({_revisar})" if _revisar
                                    else "Folha")
                    tab_folha = ui.tab(rotulo_folha, icon="fact_check")
                    if _revisar:
                        tab_folha.props("warning").tooltip(
                            f"{_revisar} contrato(s) com nome igual a outra pessoa "
                            f"aguardando confirmação do administrador")
            with ui.row().classes("items-center gap-2 flex-nowrap shrink-0").style(
                    "width:min(46%, 620px)"):
                campo_busca("🔍  Buscar… login, nome, matrícula, e-mail, telefone, "
                    "secretaria, lotação, cargo, vínculo, situação ou salário "
                    "(3.470,83)", ao_digitar,
                    tooltip="Busca NO SERVIDOR, em todos os campos: login, nome, "
                            "matrícula, e-mail, telefone, secretaria, lotação, cargo, "
                            "vínculo, situação e remuneração (aceita 'R$ 3.470,83' "
                            "ou '3470,83'). Palavras-chave de estado: 'provisório' "
                            "(senha a trocar), 'bloqueado', 'sessão', 'excluído'. "
                            "Sem acentos e maiúsculas.") \
                    .props('data-testid=usuarios-busca')
                botao("Novo usuário", icone="person_add", on_click=novo_usuario,
                      chave_modulo="usuarios", extra_classes="shrink-0",
                      tooltip="Criar usuário definindo perfil e liberação por módulo") \
                    .props('data-testid=usuarios-novo')

        with ui.tab_panels(tabs, value=tab_users).classes("w-full bg-transparent"):
            with ui.tab_panel(tab_users):
                _painel_usuarios(user_nome, estado_busca, refreshers)
            with ui.tab_panel(tab_sessoes):
                _painel_sessoes(user_nome, refreshers)
            if _tem_folha and tab_folha is not None:
                with ui.tab_panel(tab_folha):
                    _painel_folha(user_nome, refreshers)

def _acesso_negado():
    """Renders the 'access restricted' panel for non-admin users."""
    with ui.column().classes("w-full items-center p-12 gap-3"):
        ui.icon("block", size="64px").classes("text-red-8")
        ui.label("Acesso restrito").classes("text-h6")
        ui.label("Somente administradores gerais e administradores do módulo de usuários.").classes(
            "text-body2 text-grey-7")

# ==================== ABA 3: FOLHA (contratos, movimentos, salário) ====================

def _painel_folha(ator: str, refreshers=None):
    """Contratos para revisar + histórico de movimentos + evolução salarial.

    São TRÊS coisas que a folha deixou de ser depois de 03/10/2026, e
    cada uma precisa de um lugar para ser lida:

    - **contratos para revisar**: nome igual pode ser a mesma pessoa com
      dois contratos ou dois homônimos. O sistema não decide — ele
      mostra os sinais e deixa a decisão com quem conhece a prefeitura;
    - **movimentos**: demissão, afastamento e mudança de cargo/secretaria
      por competência. É a resposta a "ele trabalhava quando foi
      demitido?", que antes morria no `UPDATE`;
    - **evolução salarial**: o gráfico do salário por competência.

    O gráfico é o lugar onde a folha é lida por quem não é técnico, e por
    isso ele trata explicitamente o caso de UM ponto só (ver
    `_opcao_grafico_salarial`): servidor com salário estável tem uma
    linha no histórico, e uma linha só não desenha linha nenhuma.
    """
    try:
        _painel_folha_seguro(ator, refreshers)
    except Exception:
        log.exception("painel_folha: falha ao renderizar a aba da folha")
        notificar("Erro ao carregar os dados da folha", tipo="negative")

def _painel_folha_seguro(ator, refreshers):
    """Corpo de `_painel_folha`, isolado para o entry point proteger."""
    container = ui.column().classes("w-full gap-4")
    # Só o ANO e a ÁREA sobrevivem a um redesenho. `usuario` foi removido
    # porque não era usado em lugar nenhum — a pessoa vivia no
    # `ui.input`, e um dicionário que guarda o mesmo dado em dois lugares
    # é a divergência esperando acontecer.
    local = {"ano": "", "area": None}

    def render():
        try:
            _render_folha()
        except Exception:
            log.exception("painel_folha: falha ao renderizar")
            notificar("Erro ao atualizar a aba da folha", tipo="negative")

    def _render_folha():
        container.clear()
        with container:
            _secao_revisar(container, ator, local, render)
            _secao_grafico(container, local, render)
            _secao_movimentos(container)

    if refreshers is not None:
        refreshers["folha"] = render
    render()

def _secao_revisar(container, ator, local, render):
    """Os contratos que colidem em nome, com os sinais e as duas saídas.

    Um homônimo confirmado é Separate: a matrícula vira login de pessoa
    nova, e as duas passam a ter ficha própria. Uma pessoa confirmada
    continua uma pessoa só. As DUAS saídas precisam existir — sem a
    segunda, "são homônimos" não tem resposta e a única forma de
    desfazer seria editar o banco à mão.
    """
    try:
        pendentes = gest.listar_contratos_para_revisar()
        with ui.column().classes("w-full gap-2"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.icon("rule").classes("text-orange-8")
                ui.label("Contratos com nome igual a outra pessoa").classes(
                    "text-h6 text-orange-9")
                ui.badge(str(len(pendentes)), color="orange-3").props(
                    "text-color=orange-10 outline dense")
            ui.label(
                "Nome igual pode ser a mesma pessoa com dois contratos, ou "
                "duas pessoas diferentes. O sistema não decide isso — quem "
                "conhece a prefeitura decide. Os sinais abaixo ajudam, mas "
                "não provam nada."
            ).classes("text-body2 text-grey-7")
            if not pendentes:
                ui.label("Nenhum contrato aguardando confirmação.").classes(
                    "text-body2 text-grey-6 p-4")
                return
            with ui.column().classes("w-full gap-2"):
                for c in pendentes:
                    _linha_revisar(c, ator, render)
    except Exception:
        log.exception("_secao_revisar: falha ao montar a lista de revisão")
        notificar("Erro ao carregar os contratos para revisar", tipo="negative")

def _linha_revisar(contrato, ator, refresh):
    """Uma linha da fila de revisão: o que colide, os sinais e as ações."""
    with ui.column().classes("w-full bg-orange-1 rounded-lg px-3 py-2 gap-1"):
        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
            ui.label(gest.nome_de_tratamento(contrato["user_nome"])).classes(
                "font-medium")
            ui.icon("arrow_forward").classes("text-grey-5 text-caption")
            ui.label(f"matrícula {contrato['matricula']}").classes(
                "text-caption font-medium")
            sinais = contrato.get("sinais") or {}
            cor = {"forte": "green-3", "fraca": "amber-3",
                   "indeterminada": "grey-4"}.get(sinais.get("forca"), "grey-4")
            rotulo = {"forte": "sinais fortes", "fraca": "sinais fracos",
                      "indeterminada": "sem sinal"}.get(sinais.get("forca"), "")
            ui.badge(rotulo, color=cor).props(
                f"text-color={cor}-10 outline dense").tooltip(
                sinais.get("resumo") or "")
        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
            ui.label(f"colide com @{contrato.get('mesmo_nome_de')} · "
                     f"{contrato.get('pessoa_nome') or '—'}").classes(
                         "text-caption text-grey-7")
            ui.label(f"{contrato.get('unidade') or '—'}").classes(
                "text-caption text-grey-6")
            ui.label(f"{contrato.get('cargo') or '—'}").classes(
                "text-caption text-grey-6")
            ui.label(f"admissão {contrato.get('admissao') or '—'}").classes(
                "text-caption text-grey-6")
        with ui.row().classes("w-full items-center gap-2"):
            def _mesma():
                try:
                    ok, msg = gest.resolver_contrato(ator, contrato["matricula"], True)
                    notificar(msg, tipo="positive" if ok else "negative")
                    if ok:
                        refresh()
                except Exception:
                    log.exception("linha_revisar: falha ao confirmar contrato")
                    notificar("Erro ao confirmar o contrato", tipo="negative")

            def _homonymo():
                try:
                    ok, msg = gest.resolver_contrato(ator, contrato["matricula"], False)
                    notificar(msg, tipo="positive" if ok else "negative")
                    if ok:
                        refresh()
                except Exception:
                    log.exception("linha_revisar: falha ao separar homônimo")
                    notificar("Erro ao separar o homônimo", tipo="negative")

            botao("É a mesma pessoa", icone="person_check", on_click=_mesma,
                  chave_modulo="usuarios").props(
                "data-testid=contrato-mesma-pessoa").tooltip(
                "Os contratos ficam juntos e a marca some")
            botao("São pessoas diferentes", icone="call_split", on_click=_homonymo,
                  chave_modulo="usuarios", cor="orange-8").props(
                "data-testid=contrato-homonimo").tooltip(
                "A matrícula vira login de uma pessoa nova")

def _secao_grafico(container, local, refresh):
    """Pessoa + gráfico da evolução salarial, com filtro de período.

    O filtro de período é preenchido com os ANOS QUE TÊM REGISTRO para
    a pessoa digitada, e não com os anos do calendário: oferecer 2024
    para um servidor que só tem 2026 faria a tela virar um gráfico
    vazio sem explicação.

    **O ANO É UM `ui.select` COMO QUALQUER OUTRO, RECONSTRUÍDO A CADA
    DESENHO** — a lista depende de quem é a pessoa, e isso não se sabe
    antes de ela ser digitada. O `on_change` do seletor de ANO é
    recriado junto, senão ele continuaria disparando o desenho contra
    uma pessoa que não é mais a da tela.
    """
    try:
        # A seção tem a SUA própria coluna, e é nela que o desenho
        # acontece. Passar a coluna do painel inteiro — que era o que o
        # código fazia — e limpar nela no desenho apagava a fila de
        # revisão, o seletor de ano e a lista de movimentos: depois do
        # primeiro "Desenhar" a aba Folha ficava com o gráfico e nada
        # mais. Sem erro, sem exceção, sem aviso.
        with ui.column().classes("w-full gap-2") as secao:
            with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                ui.icon("show_chart").classes("text-blue-8")
                ui.label("Evolução salarial").classes("text-h6")
            with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                entrada = ui.input("Matrícula ou login do servidor") \
                    .props("outlined dense").classes("min-w-[240px]") \
                    .props("data-testid=usuario-grafico-alvo")
                sel_ano = ui.select({"": "Todos os anos"}, value="",
                                    label="Ano") \
                    .props("outlined dense label").classes("min-w-[150px]") \
                    .props("data-testid=usuario-grafico-ano")
                botao("Desenhar", icone="query_stats",
                      on_click=lambda _: _desenhar_salario(entrada, sel_ano,
                                                           local, secao),
                      chave_modulo="usuarios").props(
                    "data-testid=usuario-grafico-buscar")
                entrada.on("keydown.enter",
                           lambda _: _desenhar_salario(entrada, sel_ano,
                                                       local, secao))
            # A área do gráfico é criada ANTES e guardada na `local`, e é
            # por essa referência que o desenho limpa e redesenha. Criar
            # a cada desenho e procurar por `data-testid` na árvore
            #roubava a tela (ver a nota em `_desenhar_grafico_salarial`).
            local["area"] = ui.column().classes("w-full") \
                .style("min-height: 260px") \
                .props("data-testid=usuario-grafico-area")
    except Exception:
        log.exception("_secao_grafico: falha ao montar a seção do gráfico")
        notificar("Erro ao montar o gráfico salarial", tipo="negative")

def _desenhar_salario(entrada, sel_ano, local, secao):
    """Desenha o gráfico e REFAZ a lista de anos da pessoa digitada.

    `secao` entra só para manter a assinatura estável entre os handlers
    da seção; o desenho acontece em `local['area']`, que é a única coisa
    que muda de conteúdo. Ver a nota em `_desenhar_grafico_salarial`.
    """
    try:
        alvo = (entrada.value or "").strip()
        if not alvo:
            notificar("Informe a matrícula ou o login do servidor",
                      tipo="warning")
            return
        user_nome = gest.resolver_login_ou_matricula(alvo)
        anos = gest.competencias_do_historico(user_nome) if user_nome else []
        # `set_options` e não `update_options`: `update_options` é o nome
        # do NiceGUI 2.x e NÃO EXISTE nesta versão — a chamada estourava
        # `AttributeError` dentro do handler, o gráfico não desenhava e a
        # tela ficava em silêncio, sem erro visível para quem clicou.
        sel_ano.set_options({"": "Todos os anos",
                             **{str(a): str(a) for a in anos}})
        ano_atual = local.get("ano") or ""
        if ano_atual and ano_atual not in {str(a) for a in anos}:
            ano_atual = ""
        sel_ano.value = ano_atual
        local.update(ano=ano_atual)
        # O `on_value_change` é (re)ligado a cada desenho, para o seletor
        # não ficar mudo nem apontar para a pessoa anterior.
        sel_ano.on_value_change(
            lambda e: _aplicar_ano(e.value, entrada, local))
        _desenhar_grafico_salarial(local, user_nome, alvo, ano_atual)
    except Exception:
        log.exception("_desenhar_salario: falha ao desenhar o gráfico")
        notificar("Erro ao desenhar o gráfico", tipo="negative")

def _aplicar_ano(valor, entrada, local):
    """Filtra o gráfico por ano (o `on_value_change` do seletor)."""
    try:
        local.update(ano=str(valor or ""))
        alvo = (entrada.value or "").strip()
        if not alvo:
            return
        user_nome = gest.resolver_login_ou_matricula(alvo)
        _desenhar_grafico_salarial(local, user_nome, alvo, local["ano"])
    except Exception:
        log.exception("_aplicar_ano: falha ao filtrar o gráfico por ano")
        notificar("Erro ao filtrar o gráfico", tipo="negative")

def _desenhar_grafico_salarial(local, user_nome, alvo, ano):
    """Desenha o `ui.echart` da evolução salarial de uma pessoa.

    Busca pelo LOGIN e pela MATRÍCULA: o usuário do sistema digita a
    matrícula que conhece, e o administrador pode digitar o login.

    **O QUE É LIMPO, E POR QUÊ SÓ A ÁREA DO GRÁFICO.** A versão
    primeira recebia a coluna da seção e chamava `secao.clear()` — o que
    apagava o campo de matrícula, o seletor de ano e o botão, e o desenho
    seguinte rodava sobre elementos destruídos. Sem erro, sem exceção, sem
    aviso: depois do primeiro clique a aba Folha ficava só com o gráfico.
    """
    alvo = (alvo or "").strip()
    # A ÁREA é passada na mão, e não procurada na árvore.
    #
    # A primeira versão procurava `secao.descendants` por `data-testid`, e
    # `descendants` é um ITERADOR no NiceGUI atual — chamá-lo sem consumir
    # levanta `TypeError: 'method' object is not iterable` e o desenho
    # morre dentro do handler sem aparecer na tela. Como a referência é
    # conhecida de antemão (é o `local['area']` criado na montagem),
    # guardá-la é mais simples do que depender da forma do objeto.
    area = local.get("area") if local else None
    if area is None or getattr(area, "is_deleted", False):
        area = ui.column().classes("w-full").style("min-height: 260px")
        area.props("data-testid=usuario-grafico-area")
    area.clear()
    with area:
        if not user_nome:
            ui.label(f"Nenhum servidor com a matrícula ou o login "
                     f"'{alvo}'.").classes("text-body2 text-grey-6 p-2")
            return
        linhas = gest.historico_salarial(user_nome, ano=ano or None)
        _cabecalho_salario(user_nome, linhas, ano)
        if not linhas:
            ui.label("Sem registro de salário para o período escolhido.").classes(
                "text-body2 text-grey-6")
            return
        ui.echart(options=_opcao_grafico_salarial(linhas)).classes("w-full") \
            .style("height: 260px").props("data-testid=usuario-grafico-salario")
        if len(linhas) == 1:
            # A linha é SÓ quando o salário mudou (ver `registrar_salario`),
            # então um servidor estável tem UM registro. Dizer isso em texto é
            # o que separa "o gráfico tem um ponto" de "o gráfico quebrou".
            ui.label("Um único registro: o salário não mudou desde "
                     f"{linhas[0].get('competencia')}. A linha entra na "
                     f"competência em que o valor MUDA.").classes(
                         "text-caption text-grey-6")

def _cabecalho_salario(user_nome, linhas, ano):
    """Nome, salário vigente e quantos registros o gráfico está mostrando."""
    with ui.row().classes("w-full items-center gap-2 flex-wrap"):
        ui.label(gest.nome_de_tratamento(user_nome)).classes("font-medium")
        if linhas:
            ultimo = linhas[-1]
            ui.badge(ultimo.get("remuneracao") or "—", color="green-3").props(
                "text-color=green-10 outline dense").tooltip(
                f"Valor mais recente: {ultimo.get('competencia')}")
            ui.label(f"{len(linhas)} registro(s)"
                     + (f" em {ano}" if ano else "")).classes(
                         "text-caption text-grey-6")

def _opcao_grafico_salarial(linhas):
    """Monta a opção do ECharts da evolução salarial.

    **O CASO DE UM PONTO SÓ.** Um servidor com salário estável tem UMA
    linha no histórico — o registro é gravado só quando o valor muda (ver
    `registrar_salario`). E um `line` com um ponto não desenha linha
    nenhuma: a tela mostra o eixo e um vazio, e quem não sabe da regra
    conclui que o gráfico quebrou. Por isso, com um ponto só, a série vira
    `scatter` — um ponto é um ponto visível — e o texto abaixo diz que só
    há um registro, para ninguém achar que faltou mês.

    **SEM JAVASCRIPT.** `tooltip` usa `formatter` só quando é possível
    evitá-lo; aqui a variação percentual entra como uma SEGUNDA série
    (invisível, `lineStyle.opacity: 0`) e aparece no tooltip no
    `trigger: 'axis'` sem nenhuma função. O §5 do AGENTS.md proíbe
    JavaScript direto, e um `formatter` seria exatamente isso.
    """
    try:
        pontos = [(l.get("competencia") or "", l.get("remuneracao_num"))
                  for l in (linhas or [])
                  if l.get("remuneracao_num") is not None]
        competencias = [l.get("competencia") or "" for l in (linhas or [])]
        percentuais = [l.get("variacao_percentual") for l in (linhas or [])]
        um_ponto = len(pontos) <= 1
        serie = {
            "name": "Remuneração",
            "type": "scatter" if um_ponto else "line",
            "data": [p[1] for p in pontos],
            "smooth": False,
            "symbolSize": 9,
            "lineStyle": {"width": 3, "color": "#1565C0"},
            "itemStyle": {"color": "#1565C0"},
            "areaStyle": None if um_ponto else {"opacity": 0.12, "color": "#1565C0"},
        }
        # Série invisível que carrega o percentual no tooltip. `axis`
        # mostra TODAS as séries do eixo, então o número aparece sem
        # `formatter` — e sem JavaScript.
        serie_pct = {
            "name": "Variação",
            "type": "line",
            "data": percentuais,
            "lineStyle": {"opacity": 0},
            "itemStyle": {"opacity": 0},
            "symbol": "none",
            "silent": True,
            "tooltip": {"show": True},
        }
        return {
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "line"}},
            "legend": {"data": ["Remuneração"]},
            "grid": {"left": 70, "right": 24, "top": 30, "bottom": 46},
            "xAxis": {"type": "category", "data": competencias,
                      "axisLabel": {"rotate": 40, "fontSize": 10}},
            "yAxis": {"type": "value", "name": "R$",
                      "axisLabel": {"formatter": "{value}"}},
            "series": [serie, serie_pct],
        }
    except Exception as e:
        log.exception(f"_opcao_grafico_salarial: falha ao montar o gráfico | {e}")
        return {}

def _secao_movimentos(container, limite=50):
    """Movimentos recentes do cadastro inteiro.

    Sem `tipo`, devolve todos em ordem cronológica inversa. É a lista que
    responde "o que mudou na folha deste mês?" sem precisar saber o nome
    de ninguém.
    """
    try:
        linhas = gest.listar_movimentos_recentes(limite=limite)
        with ui.column().classes("w-full gap-2"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.icon("history").classes("text-grey-7")
                ui.label("Movimentos da folha").classes("text-h6")
                ui.label("demissão, retorno, afastamento e mudanças de "
                         "secretaria, cargo ou salário").classes(
                             "text-caption text-grey-6")
            if not linhas:
                ui.label("Nenhum movimento registrado.").classes(
                    "text-body2 text-grey-6 p-4")
                return
            with ui.grid(columns="180px 1fr 130px 1fr 1fr").classes(
                    "w-full bg-grey-1 rounded-t-lg px-3 py-2 text-caption "
                    "font-bold text-grey-8"):
                for c in ("Competência", "Servidor", "Movimento", "Situação",
                          "O que mudou"):
                    ui.label(c)
            for m in linhas:
                with ui.grid(columns="180px 1fr 130px 1fr 1fr").classes(
                        "w-full border-b border-grey-2 px-3 py-1 text-caption "
                        "items-center"):
                    ui.label(m.get("competencia") or "—")
                    ui.label(f"{gest.nome_de_tratamento(m.get('user_nome') or '')}"
                             f" @{m.get('user_nome')}").classes("font-medium")
                    ui.badge(m.get("tipo_movimento") or "—",
                             color=_COR_MOVIMENTO.get(m.get("tipo_movimento"),
                                                      "grey-4")).props(
                        "outline dense")
                    ui.label(f"{m.get('situacao_anterior') or '—'} → "
                             f"{m.get('situacao_nova') or '—'}")
                    ui.label(_resumo_mudanca(m)).classes("text-grey-7")
    except Exception:
        log.exception("_secao_movimentos: falha ao montar a lista de movimentos")
        notificar("Erro ao carregar os movimentos da folha", tipo="negative")

_COR_MOVIMENTO = {
    "demissao": "red-3",
    "retorno_ativo": "green-3",
    "afastamento": "amber-3",
    "alteracao_remuneracao": "blue-3",
    "alteracao_cargo": "purple-3",
    "alteracao_unidade": "teal-3",
    "vinculacao": "grey-5",
}

def _resumo_mudanca(linha):
    """O que mudou, em uma linha curta: `'remuneracao: R$ 3.470,83 -> R$ 3.900,00'`.

    Só os DOIS primeiros campos, porque a coluna da tabela tem largura
    fixa: um movimento de vinculação muda doze campos, e listar todos
    transformaria a linha em um parágrafo ilegível. O que não couber
    continua no histórico — a tela é o resumo, não o arquivo.
    """
    try:
        antes = linha.get("dados_anterior") or {}
        depois = linha.get("dados_novo") or {}
        partes = []
        for chave, novo_valor in depois.items():
            velho = antes.get(chave)
            if velho != novo_valor:
                partes.append(f"{chave}: {velho or '-'} -> {novo_valor or '-'}")
        return "; ".join(partes[:2]) or "-"
    except Exception as e:
        log.warning(f"_resumo_mudanca: falha ao resumir movimento | {e}")
        return "-"

# ==================== COMPONENTES COMPARTILHADOS DE ACESSO ====================

# 02/10/2026 — CONTEÚDO DE CADA CARTÃO DE ACESSO, por cargo do servidor.
#
# A ordem dentro de cada lista é a do responsável, não a do banco: os cartões
# são lidos por quem administra, e a ordem de frequência de uso diz mais do que
# a alfabética. Um módulo fora destas listas NÃO desaparece — cai no cartão de
# gestão (ver `_seletores_de_acesso`).
CARTOS_ACESSO = {
    # Uso diário de quem atende: notícia, telefone, impressão, empenho.
    "ferramentas": ("agregador_noticias", "lista_telefonica",
                    "solicita_impressao", "empenhos"),
    # Administração do município: pessoas, itens e ordens de serviço.
    "gestao": ("tecnico", "os", "estoque", "edit_pdf", "filas"),
    # Sempre ativos e de uso restrito a administrador (ver
    # `autenticacao.MODULOS_INDISPENSAVEIS`). `usuarios` e `auditoria` são os
    # dois que a §4.2 do AGENTS.md exige de pé; `blog` entra aqui por decisão
    # do responsável, que o trata como essencial de comunicação interna.
    "essenciais": ("usuarios", "auditoria", "blog"),
}

def _linha_acesso(chave, nome, icone, ativo, papel_atual, selecoes):
    """Uma linha do cartão de acesso: identificação | listbox de papel.

    Nome e listbox ficam na MESMA linha (02/10/2026). Empilhar o listbox
    embaixo alongava o clique-alvo e afastava o nome do seu papel; deixar o
    listbox no fim da linha, com `justify-between`, deixava a dúvida de a qual
    nome ele pertencia. Na mesma linha, a dúvida não existe.

    `min-w-0` + `truncate` no nome — é a parte que pode faltar espaço — e
    largura FIXA no listbox, que não pode encolher porque "sem acesso" precisa
    caber inteiro.
    """
    try:
        indisponivel = not ativo
        with ui.row().classes("w-full min-w-0 items-center gap-2 no-wrap"):
            with ui.row().classes("items-center gap-2 min-w-0 grow"):
                ui.icon(icone).classes(
                    "text-primary shrink-0" if not indisponivel
                    else "text-orange-9 shrink-0")
                ui.label(nome).classes("text-body2 truncate min-w-0").tooltip(nome)
                if indisponivel:
                    ui.badge("INDISPONÍVEL", color="orange-2").props(
                        "text-color=orange-10 outline dense").classes(
                        "shrink-0").tooltip(
                        "Desativado ou ainda sem rota ativa — "
                        "vínculo já pode ser definido agora")
            s = ui.select(OPCOES_PAPEL, value=papel_atual,
                          on_change=None).props(
                "outlined dense").classes("w-[180px] shrink-0")
            selecoes[chave] = s
    except Exception:
        log.exception(f"_linha_acesso: falha ao montar a linha do módulo {chave}")
        notificar(f"Erro ao montar o acesso de '{nome}'.", tipo="negative")

def _seletores_de_acesso(container, nome_usuario=None):
    """Per-module role selectors inside `container` (all registered modules).

    Monta um seletor de papel por módulo dentro de `container`.
    Itera TODOS os módulos registrados no banco — existentes e futuros.
    Novo usuário (nome_usuario=None): pré-seleciona o padrão de criação
    (`ACESSO_PADRAO_NOVO_USUARIO` com papel 'comum'; restritos nascem
    sem acesso)."""
    try:
        atual = {c: "" for c, n, i, r, a in autenticacao.modulos_registrados()}
        if nome_usuario is None:
            for c in gest.ACESSO_PADRAO_NOVO_USUARIO:
                if c in atual:
                    atual[c] = "comum"
        meta = {}
        if nome_usuario:
            for chave, papel, liberado_por, data in gest.listar_acessos(nome_usuario):
                atual[chave] = papel
                meta[chave] = f"{liberado_por} · {(data or '')[:16]}"
        desat = {c for c, n, i, r, a in autenticacao.modulos_registrados() if not a}
        selecoes = {}
        modulos = autenticacao.modulos_registrados()
        # 02/10/2026 — CARDS EM LINHA, com conteúdo definido por cargo.
        #
        # O agrupamento não é mais "N módulos por card" (ceil), e por CARGO, e
        # isso responde à pergunta que a lista corrida deixava sem resposta:
        # "de quem é a linha que eu toco?". Um card por intenção administrativa.
        #
        #   1) FERRAMENTAS DO SERVIDOR — quem trabalha com documento, telefone,
        #      fila e movimento. É o card do uso diário.
        #   2) GESTÃO DO MUNICÍPIO — quem administra pessoas, itens e ordens.
        #   3) ESSENCIAIS — usuários, auditoria e blog: não podem ser desligados
        #      e o acesso padrão é só de ADMINISTRADOR.
        #
        # Os essenciais vão por ÚLTIMO de propósito: são os que o administrador
        # precisa conferir, e o olho os encontra no fim da leitura.
        #
        # A ORDEM dentro do card 1 é a do responsável, não a do banco: notícias,
        # lista telefônica, solicitação de impressão, empenhos. São os quatro em
        # que o servidor mais trabalha, e uma lista por frequência de uso serve
        # mais do que uma por ordem de nome.
        #
        # Um módulo que não caia em nenhum cargo (módulo futuro) não some: vai
        # para o card de gestão, que é o chão de qualquer lista.

        def _pega(*chaves):
            """Módulos na ordem pedida, sem repetir nem inventar."""
            achados = []
            for c in chaves:
                m = next((x for x in modulos if x[0] == c), None)
                if m and m not in achados:
                    achados.append(m)
            return achados

        card_ferramentas = _pega(*CARTOS_ACESSO["ferramentas"])
        card_gestao = _pega(*CARTOS_ACESSO["gestao"])
        card_essenciais = _pega(*CARTOS_ACESSO["essenciais"])
        # Falta classificada? Módulo futuro não pode sumir da tela — cai na
        # gestão, que é o cartão de qualquer coisa que ainda não tem cargo.
        card_gestao = card_gestao + [
            m for m in modulos
            if m not in card_ferramentas and m not in card_gestao
            and m not in card_essenciais]

        # Cartão vazio é ruído: só entra na tela quem tem módulo.
        grupos = [(titulo, grupo) for titulo, grupo in (
            ("Ferramentas do servidor", card_ferramentas),
            ("Gestão do município", card_gestao),
            ("Essenciais — só administrador", card_essenciais),
        ) if grupo]

        with container:
            with ui.element("div").classes("w-full min-w-0 grade-cartoes"):
                for titulo, grupo in grupos:
                    with ui.column().classes(
                            "w-full min-w-0 gap-1 rounded-lg border border-grey-3 "
                            "bg-grey-1/40 px-2 py-2").style("gap: .5rem") as _cartao:
                        _cartao.props('role="group" aria-label="%s"' % titulo)
                        ui.label(titulo).classes(
                            "text-subtitle2 text-grey-7 font-bold").style(
                            "margin-bottom: .25rem")
                        for chave, nome, icone, rota, ativo in grupo:
                            _linha_acesso(chave, nome, icone, ativo,
                                          atual.get(chave, ""), selecoes)
        return selecoes, meta
    except Exception:
        log.exception(f"_seletores_de_acesso: falha ao montar seletores de {nome_usuario}")
        notificar("Erro ao carregar acessos por módulo", tipo="negative")
        return {}, {}

def _aplicar_acessos(ator, nome_usuario, selecoes):
    """Diffs selectors vs current grants and applies only changes.

    Compara seletores com o estado atual e aplica só as diferenças."""
    try:
        atual_map = {c: None for c, n, i, r, a in autenticacao.modulos_registrados()}
        for chave, papel, *_ in gest.listar_acessos(nome_usuario):
            atual_map[chave] = papel
        erros, mudou = [], 0
        for chave, s in selecoes.items():
            novo = s.value or None
            if novo != atual_map.get(chave):
                ok, msg = gest.definir_acesso(ator, nome_usuario, chave, novo)
                if ok:
                    mudou += 1
                else:
                    erros.append(msg)
        return mudou, erros
    except Exception:
        log.exception(f"_aplicar_acessos: falha ao aplicar acessos de {nome_usuario} por {ator}")
        notificar("Erro inesperado ao aplicar acessos", tipo="negative")
        return 0, ["Erro inesperado ao aplicar acessos"]

# ==================== ABA 1: USUÁRIOS ====================

def _painel_usuarios(ator: str, termo_compartilhado=None, refreshers=None):
    """Paginated user list with filters (renders only the visible page).

    Lista paginada com filtros. Busca/botão vivem na BARRA SUPERIOR (mostrar_tela).
    Renderiza só a página visível — suporta milhares de usuários sem travar."""
    estado = termo_compartilhado if termo_compartilhado is not None else {"valor": ""}
    local = {"pagina": 1, "por_pagina": 20, "situacao": "", "perfil": "", "ordem": "nome"}
    container = ui.column().classes("w-full gap-2")

    # Tema DESTE módulo, lido aqui porque é neste escopo que o rótulo
    # "senha provisória" nasce (04/10/2026). A cor do rótulo segue a cor de
    # ação do módulo — verde no tema verde, roxo no roxo — para não ser o
    # único elemento âmbar de uma linha que é toda da cor do tema.
    _tema_usuarios = ler_tema("usuarios", cor_botao="#000000",
                              cor_texto_botao="#FFFFFF")
    cor_provisoria = _tema_usuarios["cor_botao"] or ""
    # Fundo na cor do tema ESCURECIDA e texto quase branco. Ver o comentário
    # do badge para por que e este o lado que muda.
    fundo_provisoria = (tema_modulo.tom_escura(cor_provisoria, 0.55)
                        or "grey-8")
    texto_provisoria = (tema_modulo.tom_clara(cor_provisoria, 0.95)
                        or "#FFFFFF")

    SIT_OPCOES = {"": "Todas", "ativos": "Ativos", "bloqueados": "Bloqueados", "excluidos": "Excluídos"}
    PERFIL_OPCOES = {"": "Todos"} | {p: p.replace("_", " ") for p in gest.PERFIS_GLOBAIS}
    ORDEM_OPCOES = {"nome": "A→Z (nome)", "id": "Numérica (ID)"}

    def _consultar():
        """A consulta da lista. TODA no servidor (03/10/2026).

        Devolve `(linhas, total, pagina_efetiva)`. Os tokens de estado
        ('provisório', 'bloqueado', 'sessão', 'excluído') são resolvidos
        AQUI porque vivem em outros bancos, e entregues prontos para
        `buscar_usuarios` montar o `WHERE` — a consulta continua toda no
        `bd_manipulador`, que é o único que fala com banco.

        **O QUE SAIU DAQUI (03/10/2026).** A versão anterior chamava
        `listar_usuarios()`, trazia as 1.162 linhas INTEIRAS para o
        navegador e filtrava em Python a cada tecla. Duas consequências
        medidas: o payload ia inteiro a cada tecla digitada, e o filtro
        por cargo, secretaria, lotação ou remuneração era IMPOSSÍVEL,
        porque `listar_usuarios` não devolvia esses campos. Além disso,
        o total exibido vinha de `len()` da lista local — ou seja, do
        resultado do filtro, não do total do banco.
        """
        termo = estado.get("valor") or ""
        ativo_por_login, excluidos = gest.logins_por_situacao()
        especiais = gest.tokens_de_estado_atingidos(
            termo,
            autenticacao.usuarios_com_troca_pendente(),
            gest.sessoes_ativas_por_usuario(),
            excluidos, ativo_por_login)
        linhas, total, pagina = gest.buscar_usuarios(
            termo, situacao=local["situacao"], perfil=local["perfil"],
            pagina=local["pagina"], por_pagina=local["por_pagina"],
            logins_especiais=especiais)
        return linhas, total, pagina

    def render():
        try:
            _render_seguro()
        except Exception:
            log.exception("painel_usuarios: falha ao renderizar lista de usuários")
            notificar("Erro ao atualizar a lista de usuários", tipo="error")

    def _render_seguro():
        container.clear()
        pendentes = autenticacao.usuarios_com_troca_pendente()
        sessoes_cnt = gest.sessoes_ativas_por_usuario()
        # A consulta já devolve SÓ a página pedida, com o total REAL do
        # banco. `ordem` só reordena o que veio — trocar a fonte da
        # ordenação por memória exigiria trazer tudo de volta, que é o
        # que esta mudança acabou de remover.
        linhas, total, pag = _consultar()
        local["pagina"] = pag
        por = local["por_pagina"]
        paginas = max(1, math.ceil(total / por))
        fatia = list(linhas)
        if local["ordem"] == "id":
            fatia.sort(key=lambda l: l[0])
        else:
            def _chave(linha):
                _uid, nome, _perfil, _ativo, _email, _fone, _cad, _aces, _del, completo, _motivo, _tipo, _cliente = linha
                trat = (completo or "").strip() or nome
                return (_norm(trat), _norm(nome))
            fatia.sort(key=_chave)
        ini = (pag - 1) * por

        with container:
            # ---- linha de filtros + paginação ----
            with ui.row().classes("w-full items-center justify-between flex-wrap gap-2 "
                                  "bg-white rounded-lg shadow-sm px-3 py-1"):
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    ui.icon("filter_alt").classes("text-grey-6 text-caption")
                    ui.select(SIT_OPCOES, value=local["situacao"], label="Situação",
                              on_change=lambda e: (local.update(situacao=e.value, pagina=1), render())) \
                        .props("outlined dense label").classes("min-w-[170px]") \
                        .props('data-testid=usuarios-filtro-situacao') \
                        .tooltip("Filtra por situação: Ativos, Bloqueados ou Excluídos (soft-delete)")
                    ui.select(PERFIL_OPCOES, value=local["perfil"], label="Perfil global",
                              on_change=lambda e: (local.update(perfil=e.value, pagina=1), render())) \
                        .props("outlined dense label").classes("min-w-[170px]")
                    ui.select(ORDEM_OPCOES, value=local["ordem"], label="Ordenar por",
                              on_change=lambda e: (local.update(ordem=e.value, pagina=1), render())) \
                        .props("outlined dense label").classes("min-w-[160px]")
                    botao_icone("restart_alt", on_click=lambda: (
                        local.update(pagina=1, situacao="", perfil="", ordem="nome"), render()),
                        cor="grey-7", tooltip="Limpar filtros", chave_modulo="usuarios")
                with ui.row().classes("items-center gap-1"):
                    ui.select({10: "10", 20: "20", 50: "50", 100: "100"},
                              value=por, label="Por página", on_change=lambda e: (
                                  local.update(por_pagina=int(e.value), pagina=1), render())) \
                        .props("outlined dense label").classes("min-w-[120px]")
                    botao_icone("chevron_left", on_click=lambda: (
                        local.update(pagina=max(1, pag - 1)), render()),
                        chave_modulo="usuarios").props(f"disabled={pag <= 1}")
                    ui.label(f"{(ini + 1) if fatia else 0}–{ini + len(fatia)} de {total}"
                             f"  ·  pág. {pag}/{paginas}") \
                        .classes("text-caption text-grey-8 min-w-[190px] text-center")
                    botao_icone("chevron_right", on_click=lambda: (
                        local.update(pagina=min(paginas, pag + 1)), render()),
                        chave_modulo="usuarios").props(f"disabled={pag >= paginas}")

            # ---- tabela (colunas enxutas: ID | Tratamento | Ações) ----
            # A regra de Situação mora no módulo (`_rotulo_situacao`), e não
            # aqui dentro: era uma função aninhada que a lista usava e que,
            # com a ficha em diálogo, ninguém mais chamava — e duas cópias
            # da mesma regra divergem na primeira mudança.

            cab = ("ID", "Tratamento", "Senha provisória", "Ações")
            with ui.grid(columns="60px 1fr 150px 220px").classes(
                    "w-full bg-grey-1 rounded-t-lg px-3 py-2 text-caption font-bold text-grey-8"):
                for c in cab:
                    ui.label(c)
            if not fatia:
                ui.label("Nenhum usuário encontrado para os filtros atuais.").classes(
                    "text-grey-6 p-4")
            for row in fatia:
                uid, nome, perfil, ativo, email, fone, cadastro, acessos, deletado, completo, _motivo, tipo_conta, cliente_id = row
                trat = (completo or "").strip() or nome
                tem_provisoria = nome in pendentes and not deletado

                with ui.grid(columns="60px 1fr 150px 220px").classes(
                        "w-full border-b border-grey-2 px-3 py-2 items-center hover:bg-blue-50/50"):
                    ui.label(str(uid)).classes("text-caption text-grey-6")

                    # Tratamento com CLIQUE -> ficha completa da pessoa
                    # (10/10/2026). Era um `ui.tooltip` de hover: os dados
                    # apareciam ao passar o mouse e sumiam no primeiro
                    # movimento, o que tornava impossível ler a remuneração
                    # sem correr atrás da linha. O `cursor-pointer` e o
                    # `tabindex` não são enfeite — sem eles o clique não tem
                    # alvo visível nem é alcançável pelo teclado, e um
                    # tooltip de qualquer jeito nunca é.
                    with ui.element("div").classes(
                            "cursor-pointer inline-block").props(
                            "tabindex=0 role=button") as _alvo_ficha:
                        with ui.row().classes("items-center gap-2"):
                            ui.label(trat).classes("font-medium")
                            if tipo_conta == "cliente":
                                ui.badge("cliente").props(
                                    "outline dense color=teal").tooltip(
                                    f"Cliente vinculado ao ID {cliente_id or '—'}")
                            ui.icon("info_outline").classes(
                                "text-grey-5 text-xs").tooltip(
                                "Clique para ver todos os dados")
                        # Fecha a lista dentro do `for`: sem o parâmetro
                        # default, todo botão do LAÇO apontaria para o
                        # último usuário (late binding do Python).
                        #
                        # `_alvo_ficha.on(...)`, e NÃO `ui.on(...)`: no
                        # NiceGUI 3.x `ui.on` assina o evento no LAYOUT (é
                        # global) e `Element.on` assina no elemento. Com
                        # `ui.on`, as 20 linhas da página registravam 20
                        # assinaturas GLOBAIS, e um clique em qualquer lugar
                        # abriria 20 fichas — foi o que aconteceu na
                        # primeira versão deste código.
                        def _abrir(_n=nome, _r=(perfil, ativo, email, fone,
                                                cadastro, acessos, deletado)):
                            _dlg_dados_usuario(
                                _n, perfil=_r[0], ativo=_r[1], email=_r[2],
                                fone=_r[3], cadastro=_r[4], acessos=_r[5],
                                deletado=_r[6])
                        _alvo_ficha.on("click", _abrir)
                        _alvo_ficha.on("keydown.enter", _abrir)

                    # coluna própria "Senha provisória" (tabulada à esquerda da Ações)
                    #
                    # A COR SEGUE O TEMA do módulo, e não um âmbar fixo
                    # (04/10/2026, pedido do responsável): o rótulo é lido
                    # junto dos ícones de ação da MESMA linha, que já são
                    # na cor do módulo, e um âmbar solto no meio de uma linha
                    # toda da cor do tema é o elemento que não pertence à
                    # tela. Verde no tema verde, roxo no roxo.
                    #
                    # Fundo clareado e texto na cor cheia (o inverso ficaria
                    # ilegível: texto na cor do módulo sobre o fundo da mesma
                    # cor). `tom_clara` mantém a matiz, então a perceived
                    # continua sendo "a cor do sistema" e não um cinza.
                    if tem_provisoria:
                        # `cor_provisoria` e `fundo_provisoria` vêm do topo
                        # de `_painel_usuarios`, que é o escopo deste
                        # aninhamento: o badge nasce dentro de
                        # `_render_seguro`, a função que redesenha a lista a
                        # cada busca e a cada paginação, e recalcular a cor a
                        # cada render seria trabalho repetido.
                        # O texto é a cor do TEMA e o fundo é a MESMA cor
                        # ESCURECIDA — e não o contrário. Clarear o fundo e
                        # deixar o texto na cor cheia é o desenho que parece
                        # certo e não é: medido, o contraste fica em 3.26:1 no
                        # verde, 2.42:1 no roxo, 2.48:1 no preto e **1.00:1
                        # no branco** — ou seja, o rótulo some. Escurecer o
                        # fundo mantém a matiz (o preenchimento continua sendo
                        # "a cor do sistema", que é o que o pedido quer) e
                        # garante leitura em qualquer tema. Os dois valores
                        # abaixo são recalculados por `tom_clara` com o
                        # contraste medido, não escolhidos a olho.
                        # O par vai em `style`, e não em `bg-color`/`text-color`: medido, essas
                        # props NÃO pegam no `q-badge` — o fundo continuava
                        # transparente e o texto preto, e a cor do tema não
                        # aparecia na tela. `style` é CSS direto e vai no
                        # elemento certo.
                        _badge_prov = ui.badge("senha provisória").props(
                            "outline dense").style(
                            f"background-color: {fundo_provisoria} !important; "
                            f"color: {texto_provisoria} !important")
                        _badge_prov.tooltip(
                            "Troca obrigatória ainda não realizada")
                    else:
                        ui.label("").classes("text-caption")

                    with ui.row().style("gap: 0.25rem"):
                        botao_icone("edit", on_click=lambda _, n=nome: _dlg_editar(ator, n, render),
                                    tooltip="Editar dados e acessos",
                                    chave_modulo="usuarios").props(
                            f'data-testid=editar-{nome}')
                        botao_icone("content_copy",
                                    on_click=lambda _, n=nome: _dlg_duplicar(ator, n, render),
                                    tooltip="Duplicar usuário e suas configurações de acesso",
                                    chave_modulo="usuarios")
                        botao_icone("devices_other",
                                    on_click=lambda _, n=nome: _dlg_sessoes(ator, n),
                                    tooltip=f"Sessões: {sessoes_cnt.get(nome, 0)} ativa(s) + histórico recente",
                                    chave_modulo="usuarios")
                        if nome != ator:
                            if not deletado and ativo:
                                botao_icone("vpn_key", on_click=lambda _, n=nome: _dlg_senha(ator, n),
                                            tooltip="Redefinir senha (provisória)",
                                            chave_modulo="usuarios")
                                botao_icone("block",
                                            on_click=lambda _, n=nome: (_gest_bloq(ator, n, True), render()),
                                            tooltip="Bloquear",
                                            chave_modulo="usuarios")
                            else:
                                botao_icone("settings_backup_restore",
                                            on_click=lambda _, n=nome: (_gest_bloq(ator, n, False), render()),
                                            tooltip="Restaurar conta" +
                                                    (" (remove exclusão lógica)" if deletado else ""),
                                            chave_modulo="usuarios")
                            if deletado:
                                botao_icone("delete_forever",
                                            on_click=lambda _, n=nome: _dlg_excluir_definitivo(ator, n, render),
                                            tooltip="Excluir definitivamente (LGPD — irreversível)",
                                            chave_modulo="usuarios")
                            else:
                                botao_icone("delete_outline",
                                            on_click=lambda _, n=nome: _dlg_excluir(ator, n, render),
                                            tooltip="Excluir (lógico) — pede motivo e move para a lista de excluídos",
                                            chave_modulo="usuarios")
                        else:
                            ui.icon("person_pin").classes("text-grey-5 self-center") \
                                .tooltip("Sua própria conta — use 'Meu Perfil' (menu superior)")

    if refreshers is not None:
        refreshers["usuarios"] = render
    render()

def _gest_bloq(ator, nome, bloquear):
    """Blocks or restores a user account and notifies the outcome.

    Bloqueia/restaura a conta via `gest.bloquear_usuario`, registra falha
    no loguru e notifica o resultado (positivo/negativo) com o timeout
    configurado (`notificacao_timeout`).
    """
    try:
        ok, msg = gest.bloquear_usuario(ator, nome, bloquear)
        if not ok:
            log.error(f"_gest_bloq: falha ao {'bloquear' if bloquear else 'restaurar'} {nome} por {ator} | {msg}")
        notificar(msg, tipo="positive" if ok else "negative")
    except Exception:
        log.exception(f"_gest_bloq: falha ao {'bloquear' if bloquear else 'restaurar'} {nome}")
        notificar("Erro inesperado ao operar a conta", tipo="error")

def _dlg_sessoes(ator, nome):
    """User traceability dialog: active sessions + recent history.

    Diálogo de rastreabilidade do usuário: sessões ativas + histórico
    recente (IP, dispositivo e MAC), shell de FORMULÁRIO
    (`dialogo_formulario`: o corpo são duas tabelas longas, que estouravam a
    janela) e ações de encerramento padronizadas (`botao_icone` na grade,
    `botao` primário compacto no rodapé às extremidades).
    """
    try:
        _dlg_sessoes_seguro(ator, nome)
    except Exception:
        log.exception(f"_dlg_sessoes: falha ao abrir sessões de {nome}")
        notificar("Erro ao abrir sessões do usuário", tipo="negative")

def _dlg_sessoes_seguro(ator, nome):
    """Body of `_dlg_sessoes`, isolated so the entry point can protect it."""
    from datetime import datetime

    def _duracao(entrada, saida):
        try:
            fmt = "%Y-%m-%d %H:%M:%S"
            delta = datetime.strptime(saida[:19], fmt) - datetime.strptime(entrada[:19], fmt)
            mins = int(delta.total_seconds() // 60)
            return f"{mins // 60}h{mins % 60:02d}min" if mins >= 60 else f"{mins}min"
        except Exception as e:
            log.warning(f"_duracao: falha ao calcular duração de sessão | {e}")
            return "—"

    with dialogo_formulario(f"Sessões — {gest.nome_de_tratamento(nome)}",
                            chave_modulo="usuarios",
                            descricao=f"@{nome} · rastreabilidade LGPD: IP, dispositivo e MAC "
                                      "(quando resolvível na rede local)"
                            ) as (dlg, card, miolo, grade):
        with miolo:
            if nome == ator:
                ui.badge("sua conta — encerrar a sessão atual deslogará você",
                         color="amber-3").props("text-color=amber-10 outline dense")

            # ---- ativas ----
            box_ativas = ui.column().classes("w-full mt-2")
            ui.separator()
            # ---- histórico ----
            ui.label("Histórico recente (últimas 10 encerradas)").classes(
                "text-subtitle2 font-bold mt-1")
            box_hist = ui.column().classes("w-full")

            def refresh_interno():
                try:
                    _pintar_sessoes()
                except Exception:
                    log.exception(f"_dlg_sessoes: falha ao atualizar sessões de {nome}")
                    notificar("Erro ao atualizar sessões de usuário", tipo="error")

            def _pintar_sessoes():
                box_ativas.clear()
                ativas = gest.listar_sessoes_ativas(nome)
                with box_ativas:
                    ui.label(f"Ativas agora ({len(ativas)})").classes("text-subtitle2 font-bold")
                    if not ativas:
                        ui.label("Nenhuma sessão ativa no momento.").classes(
                            "text-caption text-grey-6 italic")
                    else:
                        with ui.grid(columns="auto 0.9fr 1.4fr 0.9fr 1fr auto").classes(
                                "w-full bg-grey-1 rounded px-2 py-1 text-caption font-bold"):
                            for c in ("#", "Módulo", "Dispositivo", "IP", "MAC", ""):
                                ui.label(c)
                        for sid, _u, modulo, login, cookie, ip, disp, mac in ativas:
                            with ui.grid(columns="auto 0.9fr 1.4fr 0.9fr 1fr auto").classes(
                                    "w-full border-b border-grey-2 px-2 py-1 items-center"):
                                ui.label(str(sid)).classes("text-caption text-grey-6")
                                ui.label(modulo or "sistema").classes("text-caption")
                                ui.label(disp).classes("text-caption")
                                ui.label(ip).classes("text-caption font-mono")
                                ui.label(mac).classes("text-caption font-mono text-grey-6")
                                botao_icone("logout", on_click=lambda _, i=sid: (
                                    gest.encerrar_sessao(ator, i), refresh_interno()),
                                    tooltip=f"Encerrar (entrada {login[:16]})",
                                    chave_modulo="usuarios")

                hist = gest.listar_historico_sessoes(nome, limite=10)
                box_hist.clear()
                with box_hist:
                    if not hist:
                        ui.label("Sem histórico encerrado.").classes(
                            "text-caption text-grey-6 italic")
                    else:
                        with ui.grid(columns="auto 0.9fr 1.3fr 0.9fr 0.7fr 1fr").classes(
                                "w-full bg-grey-1 rounded px-2 py-1 text-caption font-bold"):
                            for c in ("#", "Módulo", "Entrada → Saída", "Duração", "IP", "Dispositivo"):
                                ui.label(c)
                        for sid, modulo, entrada, saida, ip, disp, mac in hist:
                            with ui.grid(columns="auto 0.9fr 1.3fr 0.9fr 0.7fr 1fr").classes(
                                    "w-full border-b border-grey-2 px-2 py-1 items-center"):
                                ui.label(str(sid)).classes("text-caption text-grey-6")
                                ui.label(modulo or "sistema").classes("text-caption")
                                ui.label(f"{entrada[5:16]} → {saida[5:16]}").classes("text-caption")
                                ui.label(_duracao(entrada, saida)).classes("text-caption text-grey-7")
                                ui.label(ip).classes("text-caption font-mono")
                                ui.label(disp).classes("text-caption")

            refresh_interno()

            with ui.row().classes("w-full justify-between mt-3"):
                botao("Encerrar TODAS as sessões", variante="primario", compacto=True,
                      icone="sensors_off",
                      on_click=lambda: (gest.encerrar_todas_sessoes(ator, nome),
                                        refresh_interno()),
                      chave_modulo="usuarios")
                botao("Fechar", on_click=dlg.close, variante="texto",
                      chave_modulo="usuarios")
    dlg.open()

def _dlg_novo(ator, refresh):
    """Create-user dialog: basic data, provisional password, module access.

    Diálogo de criação de usuário: dados básicos, senha provisória
    (troca obrigatória no primeiro acesso) e seletores de acesso por
    módulo; shell de FORMULÁRIO (`dialogo_formulario`: 88vw, teto de
    1600px, `max-h-[90vh]` com o miolo rolável), os campos no `grade`
    auto-fit e o rodapé ancorado na base, notificações via `notificar` e
    rodapé padrão (`rodape_dialogo`) com "Criar usuário" (primário
    compacto do tema).
    """
    try:
        _dlg_novo_seguro(ator, refresh)
    except Exception:
        log.exception(f"_dlg_novo: falha ao abrir criação de usuário por {ator}")
        notificar("Erro ao abrir criação de usuário", tipo="negative")

def _dlg_novo_seguro(ator, refresh):
    """Body of `_dlg_novo`, isolated so the entry point can protect it."""
    with dialogo_formulario("Novo usuário", chave_modulo="usuarios",
                            descricao="Senha provisória — troca obrigatória no "
                                     "primeiro acesso (padrão inicial: 123456)."
                            ) as (dlg, card, miolo, grade):
        with grade:
            nome = ui.input("Nome de usuário (login) *").props("outlined dense").classes("w-full") \
                .tooltip("Usado apenas para entrar — não aparece como tratamento")
            completo = ui.input("Nome completo ou social *", placeholder="ex.: Maria Aparecida da Silva") \
                .props("outlined dense").classes("w-full") \
                .tooltip("Nome para tratamento nas telas. Pode ser o nome social "
                         "(Decreto 8.727/2016). Deve ser diferente do login")
            senha = ui.input(f"Senha provisória * (mín. {gest.senha_minima()})",
                             password=True, password_toggle_button=True,
                             value="123456") \
                .props("outlined dense").classes("w-full")
            email = ui.input("E-mail").props("outlined dense").classes("w-full")
            try:
                from mod_skyrover import telefone as _tel
                _campo_fone_novo = _tel.criar_campo_telefone(valor="")
            except Exception:
                _campo_fone_novo = None
                fone = ui.input("Telefone").props("outlined dense").classes("w-full")
            perfil = ui.select(gest.PERFIS_GLOBAIS, value="comum", label="Perfil global",
                               with_input=True).props("outlined dense").classes("w-full")
            tipo = ui.select(
                {"interno": "Interno — equipe Skyrover",
                 "cliente": "Cliente — contratante do laudo"},
                value="interno", label="Tipo de conta",
                on_change=lambda _e: _tipo_mudou()) \
                .props("outlined dense").classes("w-full") \
                .tooltip("Conta cliente nasce com perfil comum e sem acesso "
                         "ao módulo administrativo de usuários.")
            cliente_id = ui.number("ID do cliente (opcional)", min=1,
                                   precision=0) \
                .props("outlined dense").classes("w-full") \
                .tooltip("Referência lógica ao cliente cadastrado no núcleo. "
                         "Não consulta o banco do núcleo.")
            cliente_id.visible = False

        with miolo:
            ui.separator()
            bloco_acessos = ui.column().classes("w-full gap-0")
            with bloco_acessos:
                ui.label("Acesso aos módulos (padrão: Comum em Editor PDF, Empenhos e Solicitação de Impressão)").classes(
                    "text-subtitle2 text-grey-8")
                box = ui.column().classes("w-full gap-0")
                selecoes, _meta = _seletores_de_acesso(box)
            aviso_cliente = ui.label(
                "Conta cliente nasce com perfil comum e SEM acesso ao módulo "
                "administrativo de usuários. Os módulos contratados são "
                "liberados depois, um a um, pelo administrador.").classes(
                "text-caption text-orange-9 bg-orange-1 p-2 rounded")
            aviso_cliente.visible = False

            def _tipo_mudou():
                """Ajusta a tela ao tipo escolhido, sem depender do backend."""
                eh_cliente = (tipo.value or "interno") == "cliente"
                cliente_id.visible = eh_cliente
                bloco_acessos.visible = not eh_cliente
                aviso_cliente.visible = eh_cliente
                if eh_cliente:
                    perfil.value = "comum"
                    perfil.disable()
                else:
                    perfil.enable()

            _tipo_mudou()

            def _fone_novo_valor():
                try:
                    if _campo_fone_novo is not None:
                        return _campo_fone_novo["obter"]() or None
                    return fone.value.strip() or None
                except Exception:
                    return None

            def salvar():
                try:
                    tipo_conta = (tipo.value or "interno")
                    cliente_ref = None
                    if tipo_conta == "cliente" and cliente_id.value not in (None, ""):
                        try:
                            cliente_ref = int(cliente_id.value)
                        except Exception:
                            notificar("ID do cliente deve ser um número inteiro",
                                      tipo="negative")
                            return
                    perfil_valor = ("comum" if tipo_conta == "cliente"
                                    else (perfil.value or "comum"))
                    senha_padrao = (senha.value or "").strip() or "123456"
                    ok, msg = gest.criar_usuario(ator, nome.value or "", senha_padrao,
                                                 email=email.value.strip() or None,
                                                 fone=_fone_novo_valor(),
                                                 perfil=perfil_valor,
                                                 nome_completo=completo.value,
                                                 tipo_conta=tipo_conta,
                                                 cliente_id=cliente_ref)
                    if not ok:
                        log.error(f"novo_usuario: falha ao criar '{nome.value}' por {ator} | {msg}")
                        notificar(msg, tipo="negative")
                        return
                    if tipo_conta == "cliente":
                        # Cliente não recebe acesso administrativo nem por
                        # engano da tela: os seletores nem são aplicados.
                        mudou, erros = 0, []
                    else:
                        mudou, erros = _aplicar_acessos(ator, nome.value.strip(), selecoes)
                    if erros:
                        notificar(f"Usuário criado, mas houve erros nos acessos: {' | '.join(erros)}",
                                  tipo="warning")
                    else:
                        notificar(f"Usuário '{nome.value.strip()}' criado" +
                                  (f" com {mudou} acesso(s)" if mudou else ""), type="positive")
                    dlg.close()
                    refresh()
                except Exception:
                    log.exception(f"novo_usuario: falha ao criar usuário por {ator}")
                    notificar("Erro inesperado ao criar usuário", tipo="error")

            rodape_dialogo(dlg, acoes=[("Criar usuário", salvar)],
                           chave_modulo="usuarios", classes_extra="mt-3")
    dlg.open()

def _bloco_telefones_admin(nome_usuario: str, ator: str = "sistema"):
    """EN: Admin view of a user's phones (fix errors, unblock a stuck account).

    PT-BR: Visão dos telefones de um usuário (corrigir erro, destravar conta).

    POR QUE O ADMIN VÊ ISSO
        O servidor cadastra o próprio telefone no primeiro acesso, mas há
        dois casos em que ele não consegue: quem digita o número errado e
        fecha o navegador antes de corrigir, e quem é cadastrado pelo RH às
        pressas e fica com a pendência ligada. Sem esta tela, a conta ficaria
        presa no primeiro acesso sem saída pela interface.

    A ESCOLHA DE PUBLICAÇÃO CONTINUA SENDO DO SERVIDOR
        O admin pode corrigir o NÚMERO, mas a caixa de "aparece na lista"
        continua sendo do titular. O administrador não amplia a exposição de
        ninguém por conveniência própria — e o botão de adicionar já nasce
        desmarcado, para a escolha partir de quem atende o telefone.
    """
    ui.label("Telefones").classes("text-subtitle2 text-grey-8")
    ui.label("O servidor escolhe o que sai na lista telefônica. O fixo da "
             "prefeitura sempre sai — é linha institucional.").classes(
        "text-caption text-grey-6")

    # ---- LIBERAÇÃO TEMPORÁRIA ----
    # O servidor que entrou sem saber o próprio número ficou com 4 dias de
    # prazo. Vencido, a conta fecha e ele vem aqui. O botão só aparece
    # quando faz sentido aparecer — e o texto diz por quê, para o técnico
    # não liberar às cegas.
    try:
        info_prov = gest.informacao_acesso_provisorio(nome_usuario)
    except Exception:
        info_prov = {"provisorio": False, "ate": None, "vencido": False,
                     "bloqueado": False, "dias_restantes": None}
    if info_prov.get("provisorio"):
        dias = info_prov.get("dias_restantes")

        def _liberar_definitivo():
            """DTI confirma que o servidor descobriu o número."""
            try:
                ok, msg = gest.liberar_acesso_definitivo(ator, nome_usuario)
                notificar(msg, tipo="positive" if ok else "negative")
            except Exception as e:
                log.exception(
                    f"_bloco_telefones_admin: falha ao liberar {nome_usuario}: {e}")
                notificar("Erro ao liberar o acesso.", tipo="negative")

        with ui.row().classes(
                "w-full items-center no-wrap rounded bg-orange-1 px-2 py-1") \
                .style("gap: 0.5rem"):
            if info_prov.get("vencido"):
                ui.label("Acesso temporário VENCIDO — a conta está bloqueada "
                         "desde que o prazo passou.").classes(
                    "text-caption text-orange-10 grow")
            else:
                ui.label(f"Acesso temporário: restam {dias} dia(s) "
                         f"(até {info_prov.get('ate')}).").classes(
                    "text-caption text-orange-10 grow")
            botao("Liberar em definitivo", icone="verified_user",
                  on_click=_liberar_definitivo, variante="primario",
                  chave_modulo="usuarios",
                  extra_classes="shrink-0 no-caps")
    elif info_prov.get("bloqueado"):
        ui.label("Conta bloqueada.").classes("text-caption text-grey-6")

    caixa = ui.element("div").classes("w-full grade-tels-admin")
    _css_grade_tels_admin()

    def _desenhar():
        caixa.clear()
        try:
            telefones = gest.listar_telefones(nome_usuario)
            pendente = gest.telefone_pendente(nome_usuario)
        except Exception as e:
            log.exception(f"_bloco_telefones_admin: falha ao ler telefones de {nome_usuario}: {e}")
            return
        # 16/10/2026 — tudo DENTRO de `with caixa:`: sem isso os elementos
        # caíam no contexto pai (fora da coluna), o `clear()` não limpava a
        # lista antiga e o telefone recém-gravado não aparecia onde deveria.
        with caixa:
            if pendente:
                ui.label("Pendente: o servidor ainda não cadastrou os telefones "
                         "no primeiro acesso.").classes("text-caption text-orange-8")
            if not telefones:
                ui.label("Nenhum telefone cadastrado.").classes("text-body2 text-grey-6 italic")
                return
            n_tels = len(telefones)
            # `1 / -1`: o contador ocupa a fileira inteira — sem isso ele
            # virava a primeira CÉLULA da grade e empurrava o 1º cartão para
            # o lado (16/10/2026).
            ui.label(f"{n_tels} telefone(s) cadastrado(s).").classes(
                "text-caption text-grey-6").style("grid-column: 1 / -1")
            # t = (id, user_nome, numero, papel, tipo, principal, visivel,
            #      recado, whatsapp, data_cadastro)
            _fundo = _fundo_card_tel()
            for t in telefones:
                eh_prefeitura = (t[3] == "empresa")
                tipo_txt = "fixo" if t[4] == "fixo" else "celular"
                cor_origem = "negative" if eh_prefeitura else "positive"
                na_agenda = bool(gest.telefone_e_publicavel(t[3], t[4], t[6]))
                try:
                    from mod_skyrover import telefone as _tel_fmt
                    # Exibição COMPLETA com DDI: `+55 (35) 9 8818-3288`.
                    numero_txt = _tel_fmt.formatar_para_exibicao(t[2] or "")
                except Exception:
                    numero_txt = t[2]
                with ui.card().classes("gap-1 min-w-0") \
                        .style(f"min-width: 0; {_fundo}"):
                    ui.label(f"{numero_txt}").classes("text-body2 truncate")
                    ui.label(tipo_txt
                             + (" · principal" if t[5] else "")).classes(
                        "text-caption text-grey-6 truncate")
                    with ui.row().classes("w-full flex-wrap").style("gap: 0.25rem"):
                        ui.badge("Prefeitura" if eh_prefeitura else "Particular",
                                 color=cor_origem) \
                            .props("data-testid=admin-tel-origem-{}".format(t[0])) \
                            .tooltip("Telefone da prefeitura" if eh_prefeitura
                                     else "Telefone particular")
                        if na_agenda:
                            ui.badge("Na agenda", color="positive") \
                                .props("data-testid=admin-tel-agenda-{}".format(t[0])) \
                                .tooltip("Aparece no card da agenda telefônica")
                        else:
                            ui.badge("Restrito", color="grey") \
                                .props("data-testid=admin-tel-agenda-{}".format(t[0])) \
                                .tooltip("Só no cadastro — fora da agenda")
                        eh_whats = bool(t[8]) if len(t) > 8 else False
                        if eh_whats:
                            ui.badge("WhatsApp", color="positive") \
                                .props("data-testid=admin-tel-whats-{}".format(t[0])) \
                                .tooltip("Este número é WhatsApp")
                    with ui.row().classes("w-full justify-end").style("gap: 0.25rem"):
                        try:
                            btn_editar_tel = botao_icone(
                                "edit",
                                on_click=lambda tid=t[0], tel=t: _editar(tid, tel),
                                cor="primary",
                                tooltip="Editar",
                                chave_modulo="usuarios",
                                extra_classes="shrink-0")
                            if btn_editar_tel is not None:
                                btn_editar_tel.props(
                                    "data-testid=admin-tel-editar-{}".format(t[0]))
                        except Exception as e:
                            log.exception(f"_bloco_telefones_admin: falha ao montar editar {t[0]}: {e}")
                            notificar("Não foi possível montar o botão editar.",
                                      tipo="error")
                        try:
                            btn_remover_tel = botao_icone(
                                "delete",
                                on_click=lambda tid=t[0]: _remover(tid),
                                cor="negative",
                                tooltip="Remover",
                                chave_modulo="usuarios",
                                extra_classes="shrink-0")
                            if btn_remover_tel is not None:
                                btn_remover_tel.props(
                                    "data-testid=admin-tel-remover-{}".format(t[0]))
                        except Exception as e:
                            log.exception(f"_bloco_telefones_admin: falha ao montar remover {t[0]}: {e}")
                            notificar("Não foi possível montar o botão remover.",
                                      tipo="error")

    def _editar(tid, tel):
        """EN: Edit one phone (number, owner, type, visibility, main)."""
        try:
            with dialogo_card(titulo="Editar telefone", largura="w-[420px]",
                               chave_modulo="usuarios") as (dlg, card):
                inp_num = ui.input("Número", value=tel[2] or "") \
                    .props("outlined dense").classes("w-full") \
                    .props("data-testid=admin-tel-editar-numero")
                sel_papel = ui.select({"empresa": "prefeitura", "pessoal": "particular"},
                                      label="De quem é",
                                      value=tel[3] if tel[3] in ("empresa", "pessoal") else "empresa") \
                    .props("outlined dense").classes("w-full") \
                    .props("data-testid=admin-tel-editar-papel")
                sel_tipo = ui.select({"celular": "celular", "fixo": "fixo"},
                                     label="Tipo",
                                     value=tel[4] if tel[4] in ("celular", "fixo") else "celular") \
                    .props("outlined dense").classes("w-full") \
                    .props("data-testid=admin-tel-editar-tipo")
                chk_vis = ui.checkbox("Publicar na lista telefônica",
                                      value=bool(tel[6])) \
                    .props("data-testid=admin-tel-editar-visivel") \
                    .tooltip("Compartilhar este número na lista. Marcando, o "
                             "número aparece no card da agenda e pode receber "
                             "mensagens/notificações.")
                chk_whats_ed = ui.checkbox("É WhatsApp",
                                           value=bool(tel[8]) if len(tel) > 8 else False) \
                    .props("data-testid=admin-tel-editar-whatsapp") \
                    .tooltip("Marcar se este número é WhatsApp — outros "
                             "módulos usam isso para escolher o canal de aviso.")
                chk_princ = ui.checkbox("Principal",
                                        value=bool(tel[5])) \
                    .props("data-testid=admin-tel-editar-principal")

                def _salvar_edicao():
                    try:
                        ok, msg = gest.editar_telefone(
                            ator, tid, numero=(inp_num.value or "").strip(),
                            papel=sel_papel.value, tipo=sel_tipo.value,
                            visivel=bool(chk_vis.value),
                            whatsapp=bool(chk_whats_ed.value),
                            principal=bool(chk_princ.value))
                        notificar(msg, tipo="positive" if ok else "negative")
                        if ok:
                            dlg.close()
                            _desenhar()
                    except Exception as e:
                        log.exception(f"_bloco_telefones_admin: falha ao editar {tid}: {e}")
                        notificar("Erro ao alterar o telefone.", tipo="error")

                with ui.row().classes("w-full justify-end mt-2").style("gap: 0.5rem"):
                    botao("Cancelar", variante="texto", chave_modulo="usuarios",
                          on_click=dlg.close)
                    botao("Salvar", icone="save", on_click=_salvar_edicao,
                          variante="primario", chave_modulo="usuarios") \
                        .props("data-testid=admin-tel-editar-salvar")
            dlg.open()
        except Exception as e:
            log.exception(f"_bloco_telefones_admin: falha ao abrir edição {tid}: {e}")
            notificar("Erro ao abrir edição do telefone.", tipo="error")

    def _remover(tid):
        try:
            ok, msg = gest.remover_telefone(ator, tid)
            notificar(msg, tipo="positive" if ok else "negative")
            if ok:
                _desenhar()
        except Exception as e:
            log.exception(f"_bloco_telefones_admin: falha ao remover {tid}: {e}")
            notificar("Erro ao remover o telefone.", tipo="error")

    _desenhar()

    # ---- ADICIONAR TELEFONE ----
    # 16/10/2026 — ordem e padrões pedidos pelo responsável: [De quem é
    # (particular), Tipo (celular), DDI (20ch fixo), Número (23ch),
    # Disponibilizar, WhatsApp, Adicionar]. DDD obrigatório no BR e exibição
    # (xx) xxxx-xxxx no fixo / (xx) 9 xxxx-xxxx no celular, com DDI via
    # `formatar_para_exibicao` (`+55 (35) 9 8818-3288`).
    # O "Disponibilizar" é o consentimento (`visivel`): marcado, publica na
    # agenda — com confirmação dupla avisando de mensagens/notificações e da
    # remoção a qualquer momento.
    #
    # RESPONSIVO (kbp-web-design, 16/10/2026): nada aqui tem largura RÍGIDA
    # (`flex: 0 0 X` + `shrink-0` estourava a fileira em ≤768px e o diálogo
    # cortava o conteúdo: "+55 - Brasi", "il Número", "tsApp"). Todo item
    # tem base + piso e pode encolher; o que não couber QUEBRA para a linha
    # de baixo inteira (`flex-wrap` + checkbox com `shrink-0`), em vez de
    # ser espremido até cortar o texto. Em telas pequenas (≤640px) a folha
    # `CSS_TEL_NOVO` abaixo força composto, checkboxes e botão em linha
    # cheia — pedido do responsável: checkbox e Adicionar na linha de
    # baixo, ocupando toda a linha.
    _injetar_css_tel_novo()
    with ui.row().classes("w-full items-start flex-wrap tel-novo-linha").style("gap: 0.5rem; min-width: 0"):
        pap = ui.select({"empresa": "prefeitura", "pessoal": "particular"},
                        label="De quem é", value="pessoal") \
            .props("outlined dense no-caps").classes("shrink-0") \
            .style("flex: 0 1 130px; min-width: 104px") \
            .props("data-testid=admin-tel-novo-papel")
        tip = ui.select({"celular": "celular", "fixo": "fixo"},
                        label="Tipo", value="celular") \
            .props("outlined dense no-caps").classes("shrink-0") \
            .style("flex: 0 1 110px; min-width: 88px") \
            .props("data-testid=admin-tel-novo-tipo")
        from mod_skyrover import telefone as _tel
        _campo = _tel.criar_campo_telefone(
            rotulo="Número", valor="",
            placeholder="(35) 99999-9999",
            largura_ddi="w-[160px]",
            classes_linha="grow shrink basis-[19rem] min-w-0 gap-2 flex-nowrap items-start tel-novo-comp",
            testid_ddi="admin-tel-novo-ddi",
            testid_numero="admin-tel-novo-numero")
        if _campo is not None:
            _num = _campo["numero"]
            _ddi = _campo["ddi"]
            _obter = _campo["obter"]
            _tem_campo_completo = True
            try:
                _ddi.style("flex: 1 1 20ch; min-width: 140px; max-width: 100%")
                _num.style("flex: 2 1 23ch; min-width: 9rem; max-width: 100%")
                _num.props("maxlength=15")
            except Exception:
                pass
        else:
            _num = ui.input("Número").props("outlined dense maxlength=15") \
                .classes("shrink-0").style("flex: 2 1 23ch; min-width: 9rem") \
                .props("data-testid=admin-tel-novo-numero")
            _ddi = None
            _obter = lambda: (_num.value or "").strip()
            _tem_campo_completo = False
            try:
                _num.style("flex: 2 1 23ch; min-width: 9rem")
            except Exception:
                pass
        chk_pub = ui.checkbox("Disponibilizar na agenda") \
            .classes("shrink-0 tel-novo-check") \
            .props("data-testid=admin-tel-novo-visivel") \
            .tooltip("Marcando, o número aparece no card da agenda telefônica, "
                     "pode receber mensagens/notificações e pode ser retirado "
                     "da lista a qualquer momento.")
        chk_whats = ui.checkbox("É WhatsApp") \
            .classes("shrink-0 tel-novo-check") \
            .props("data-testid=admin-tel-novo-whatsapp") \
            .tooltip("Marcar se este número é WhatsApp — outros módulos usam "
                     "isso para escolher o canal de aviso.")
        try:
            chk_pub.value = False
            chk_whats.value = False
        except Exception:
            pass

        def _gravar_publicado(numero, ddi_ok):
            try:
                ok, msg = gest.adicionar_telefone(
                    ator, nome_usuario, numero, papel=pap.value,
                    tipo=tip.value, visivel=bool(chk_pub.value),
                    whatsapp=bool(chk_whats.value))
                notificar(msg, tipo="positive" if ok else "negative")
                if ok:
                    try:
                        _num.value = ""
                    except Exception:
                        pass
                    if _tem_campo_completo and _ddi is not None:
                        try:
                            _ddi.value = _tel.DDI_PADRAO
                        except Exception:
                            pass
                    try:
                        chk_pub.value = False
                        chk_whats.value = False
                    except Exception:
                        pass
                    _desenhar()
            except Exception as e:
                log.exception(f"_bloco_telefones_admin: falha ao adicionar: {e}")
                notificar("Erro ao cadastrar o telefone.", tipo="error")

        def _adicionar():
            try:
                numero = _obter() or ""
                if _tem_campo_completo:
                    ddi = ((_ddi.value or "").strip() if _ddi is not None else "")
                    if not ddi or ddi.startswith("--"):
                        notificar("Escolha o DDI do telefone.", tipo="negative")
                        return
                    if ddi == _tel.DDI_PADRAO:
                        dig_nac = _tel.apenas_digitos(_num.value or "")
                        if len(dig_nac) not in (10, 11):
                            notificar("Digite o número com o DDD: "
                                      "(35) 9999-9999 no fixo, "
                                      "(35) 99999-9999 no celular.",
                                      tipo="negative")
                            return
                        if (tip.value or "celular") == "fixo" and len(dig_nac) != 10:
                            notificar("Fixo usa (xx) xxxx-xxxx: DDD + 8 dígitos.",
                                      tipo="negative")
                            return
                        if (tip.value or "celular") == "celular" and len(dig_nac) != 11:
                            notificar("Celular usa (xx) xxxxx-xxxx: DDD + 9 dígitos.",
                                      tipo="negative")
                            return
                if not _tel.apenas_digitos(numero):
                    notificar("Informe o número do telefone.", tipo="negative")
                    return
                if bool(chk_pub.value):
                    with dialogo_card(titulo="Publicar na agenda?",
                                       largura="w-[420px]",
                                       chave_modulo="usuarios") as (dlg, card):
                        ui.label("Este número vai aparecer no card da agenda "
                                 "telefônica do sistema e poderá ser usado para "
                                 "enviar mensagens e notificações. Você pode "
                                 "removê-lo da lista a qualquer momento.") \
                            .classes("text-body2")
                        with ui.row().classes("w-full justify-end mt-2").style("gap: 0.5rem"):
                            botao("Voltar", variante="texto",
                                  chave_modulo="usuarios", on_click=dlg.close)
                            botao("Confirmar e publicar", icone="publish",
                                  on_click=lambda: (dlg.close(), _gravar_publicado(numero, True)),
                                  variante="primario", chave_modulo="usuarios") \
                                .props("data-testid=admin-tel-novo-confirmar")
                    dlg.open()
                    return
                _gravar_publicado(numero, True)
            except Exception as e:
                log.exception(f"_bloco_telefones_admin: falha ao adicionar: {e}")
                notificar("Erro ao cadastrar o telefone.", tipo="error")

        botao("Adicionar", icone="add", on_click=_adicionar, variante="primario",
              chave_modulo="usuarios", extra_classes="shrink-0 tel-novo-add")

def _dlg_editar(ator, nome_atual, refresh):
    """Edit-user dialog: identity, global profile and per-module access.

    Diálogo de edição: renomear login, e-mail, telefone, nome de
    tratamento, perfil global e acessos por módulo. Título e separator
    permanecem manuais (vivem dentro do `card_section` — o helper
    `titulo=` os posicionaria no card, alterando o espaçamento); shell
    via `dialogo_card`, notificações via `notificar` e rodapé padrão com
    "Salvar alterações" (primário compacto do tema + ícone save).
    """
    try:
        _dlg_editar_seguro(ator, nome_atual, refresh)
    except Exception:
        log.exception(f"_dlg_editar: falha ao abrir edição de {nome_atual} por {ator}")
        notificar("Erro ao abrir edição de usuário", tipo="negative")

def _dlg_editar_seguro(ator, nome_atual, refresh):
    """Body of `_dlg_editar`, isolated so the entry point can protect it."""
    row = gest.obter_usuario(nome_atual)
    if not row:
        notificar("Usuário não encontrado", tipo="negative")
        return
    _, _, _, email, fone, perfil, _, _, _deletado, completo = row[:10]
    tipo_atual = (row[10] if len(row) > 10 and row[10] else "interno")
    cliente_atual = row[11] if len(row) > 11 else None

    with dialogo_formulario(f"Editar — {gest.nome_de_tratamento(nome_atual)}",
                            chave_modulo="usuarios",
                            descricao="Identidade (chave primária ID preservada)"
                            ) as (dlg, card, miolo, grade):
        with grade:
            novo_nome = ui.input("Nome de usuário (login)", value=nome_atual).props("outlined dense").classes("w-full")
            if nome_atual == "master":
                novo_nome.disable().tooltip("A conta master nativa não pode ser renomeada")

            completo_i = ui.input("Nome completo ou social *", value=completo or "",
                                  placeholder="Nome para tratamento — pode ser nome social") \
                .props("outlined dense").classes("w-full")
            email_i = ui.input("E-mail", value=email or "").props("outlined dense").classes("w-full")
            try:
                from mod_skyrover import telefone as _tel_edit
                _campo_fone_edit = _tel_edit.criar_campo_telefone(valor=fone or "")
                _fone_edit_input = None
            except Exception:
                _campo_fone_edit = None
                fone_i = ui.input("Telefone", value=fone or "").props("outlined dense").classes("w-full")
                _fone_edit_input = fone_i
            perf_i = ui.select(gest.PERFIS_GLOBAIS, value=perfil, label="Perfil global",
                               with_input=True).props("outlined dense").classes("w-full")
            tipo_i = ui.select(
                {"interno": "Interno — equipe Skyrover",
                 "cliente": "Cliente — contratante do laudo"},
                value=tipo_atual, label="Tipo de conta",
                on_change=lambda _e: _tipo_edit_mudou()) \
                .props("outlined dense").classes("w-full")
            cliente_i = ui.number("ID do cliente (opcional)",
                                  value=cliente_atual, min=1, precision=0) \
                .props("outlined dense").classes("w-full")
            cliente_i.visible = (tipo_atual == "cliente")

        with miolo:
            ui.separator()
            _bloco_telefones_admin(nome_atual, ator)

            # 04/10/2026 — os dados da folha entram no cadastro e são
            # SOMENTE TEXTO, para o administrador também. O pedido foi
            # "sem possibilidade de edição nem pelo usuário nem pelo
            # administrador, afinal esses dados devem vir do arquivo": um
            # campo da folha que o admin consegue apagar deixa de ser da
            # folha no instante em que ele edita, e a próxima carga volta
            # com o valor antigo — o cadastro passa a discordar da folha
            # sem ninguém ter tocado em nada.
            ui.separator()
            # O login usado aqui é o ATUAL, e não o digitado no campo de
            # renomear: a renomeação só se aplica ao salvar, e mostrar os
            # dados da pessoa antiga enquanto o campo já mostra outro
            # login é o tipo de divergência que ninguém sabe explicar.
            try:
                with ui.element("div").classes("w-full").props(
                        "data-testid=editar-dados-folha"):
                    dados_folha_tela.bloco_dados_folha(nome_atual)
            except Exception:
                # Sem a folha distribuída, esta seção é opcional: o cadastro
                # continua editável e a tela não estoura.
                log.exception(
                    f"_dlg_editar_seguro: dados da folha indisponíveis para "
                    f"{nome_atual}")
                ui.label("Dados da folha indisponíveis para esta conta.").classes(
                    "text-caption text-grey-6")

            ui.separator()
            bloco_acessos_edit = ui.column().classes("w-full gap-0")
            with bloco_acessos_edit:
                ui.label("Acesso aos módulos — papel em cada um").classes(
                    "text-subtitle2 text-grey-8")
                box = ui.column().classes("w-full gap-0")
                selecoes, meta = _seletores_de_acesso(box, nome_atual)
            aviso_cliente_edit = ui.label(
                "Conta cliente mantém perfil comum e sem acesso ao módulo "
                "administrativo de usuários.").classes(
                "text-caption text-orange-9 bg-orange-1 p-2 rounded")
            aviso_cliente_edit.visible = (tipo_atual == "cliente")

            def _tipo_edit_mudou():
                """Espelha no formulário a regra de backend do tipo cliente."""
                eh_cliente = (tipo_i.value or "interno") == "cliente"
                cliente_i.visible = eh_cliente
                bloco_acessos_edit.visible = not eh_cliente
                aviso_cliente_edit.visible = eh_cliente
                if eh_cliente:
                    perf_i.value = "comum"
                    perf_i.disable()
                else:
                    perf_i.enable()

            _tipo_edit_mudou()

            def _fone_edit_valor():
                try:
                    if _campo_fone_edit is not None:
                        return _campo_fone_edit["obter"]() or ""
                    return _fone_edit_input.value.strip()
                except Exception:
                    return ""

            def salvar():
                try:
                    erros = []
                    alvo = nome_atual
                    tipo_conta = (tipo_i.value or "interno")
                    if tipo_conta == "cliente":
                        cliente_ref = None
                        if cliente_i.value not in (None, ""):
                            try:
                                cliente_ref = int(cliente_i.value)
                            except Exception:
                                notificar("ID do cliente deve ser um número inteiro",
                                          tipo="negative")
                                return
                        perfil_valor = "comum"
                    else:
                        cliente_ref = None  # conta interna não guarda vínculo
                        perfil_valor = perf_i.value
                    if (novo_nome.value or "").strip() != nome_atual:
                        ok_r, msg_r = gest.renomear_usuario(ator, nome_atual, novo_nome.value.strip())
                        if not ok_r:
                            erros.append(msg_r)
                        else:
                            alvo = novo_nome.value.strip()
                    ok_e, msg_e = gest.editar_usuario(
                        ator, alvo, email=email_i.value.strip(),
                        fone=_fone_edit_valor(), perfil=perfil_valor,
                        nome_completo=completo_i.value,
                        tipo_conta=tipo_conta, cliente_id=cliente_ref)
                    if not ok_e:
                        erros.append(msg_e)
                    if tipo_conta == "cliente":
                        # O backend já removeu o acesso a `usuarios`; não
                        # reaplicar os seletores evita regredir a garantia.
                        mudou, erros_a = 0, []
                    else:
                        mudou, erros_a = _aplicar_acessos(ator, alvo, selecoes)
                    erros.extend(erros_a)
                    if erros:
                        log.error(f"editar_usuario: falha ao atualizar {nome_atual} por {ator} | {' | '.join(erros)}")
                        notificar(" | ".join(erros), tipo="negative")
                    else:
                        notificar("Usuário atualizado" +
                                  (f" ({mudou} acesso(s) alterado(s))" if mudou else ""), type="positive")
                        dlg.close()
                        refresh()
                except Exception:
                    log.exception(f"editar_usuario: falha ao atualizar {nome_atual} por {ator}")
                    notificar("Erro inesperado ao atualizar usuário", tipo="error")

            rodape_dialogo(dlg, acoes=[("Salvar alterações", salvar, {"icone": "save"})],
                           chave_modulo="usuarios", classes_extra="mt-3")
    dlg.open()

# ==================== ABA 3: ADMINISTRAÇÃO (exclusiva do admin geral) ====================

def _dlg_senha(ator, nome):
    """Password reset dialog: sets a new provisional password.

    Diálogo de redefinição de senha: define nova senha provisória (troca
    obrigatória no próximo acesso); shell padronizado (`dialogo_card`) e
    rodapé padrão com "Redefinir" (cor amber-8 byte-idêntica). O label do
    campo mostra o mínimo vigente via `gest.senha_minima()` (chave
    `usuarios_senha_min`).
    """
    try:
        _dlg_senha_seguro(ator, nome)
    except Exception:
        log.exception(f"_dlg_senha: falha ao abrir redefinição de senha de {nome} por {ator}")
        notificar("Erro ao abrir redefinição de senha", tipo="negative")

def _dlg_senha_seguro(ator, nome):
    """Body of `_dlg_senha`, isolated so the entry point can protect it."""
    with dialogo_card(largura="w-[380px]", chave_modulo="usuarios",
                      max_altura=False) as (dlg, card):
        ui.label(f"Redefinir senha — {nome}").classes("text-h6")
        ui.label("O usuário receberá senha provisória e deverá trocá-la no próximo acesso.").classes(
            "text-caption text-orange-9 bg-orange-1 p-2 rounded")
        nova = ui.input(f"Nova senha provisória (mín. {gest.senha_minima()})", password=True,
                        password_toggle_button=True).props("outlined dense").classes("w-full")

        def salvar():
            try:
                ok, msg = gest.alterar_senha_admin(ator, nome, nova.value or "")
                if not ok:
                    log.error(f"redefinir_senha: falha para {nome} por {ator} | {msg}")
                notificar(msg, tipo="positive" if ok else "negative")
                if ok:
                    dlg.close()
            except Exception:
                log.exception(f"redefinir_senha: falha para {nome} por {ator}")
                notificar("Erro inesperado ao redefinir senha", tipo="error")

        rodape_dialogo(dlg, acoes=[("Redefinir", salvar, {"cor": "amber-8"})],
                       chave_modulo="usuarios", classes_extra="mt-2")
    dlg.open()

def _dlg_excluir(ator, nome, refresh):
    """Stage 1: LOGICAL delete — asks for the reason and soft-deletes.

    Estágio 1: exclusão LÓGICA — pede o motivo e move o usuário para a
    lista de excluídos (reversível via 'Restaurar'); a exclusão PERMANENTE
    (LGPD) só existe dentro da lista de excluídos. Card com borda laranja
    (`dialogo_card` + classes extras); rodapé às extremidades mantido cru
    (`justify-between` não é o padrão do `rodape_dialogo`), com a ação via
    `botao` primário compacto.
    """
    try:
        _dlg_excluir_seguro(ator, nome, refresh)
    except Exception:
        log.exception(f"_dlg_excluir: falha ao abrir exclusão lógica de {nome} por {ator}")
        notificar("Erro ao abrir exclusão de usuário", tipo="negative")

def _dlg_excluir_seguro(ator, nome, refresh):
    """Body of `_dlg_excluir`, isolated so the entry point can protect it."""
    with dialogo_card(largura="w-[440px]", chave_modulo="usuarios",
                      max_altura=False) as (dlg, card):
        card.classes("border-2 border-orange-5")
        ui.label("Excluir usuário").classes("text-h6 text-orange-9")
        ui.label(
            f"'{nome}' será movido para a lista de Excluídos: perde o acesso "
            "imediatamente e suas sessões são encerradas.\n"
            "Nada é apagado do banco — a exclusão é reversível via 'Restaurar'.\n"
            "A exclusão PERMANENTE (LGPD) só fica disponível dentro da lista de excluídos."
        ).classes("text-body2 whitespace-pre-line")
        motivo = ui.textarea("Motivo da exclusão *",
                             placeholder="ex.: desligamento da empresa a pedido do RH",
                             validation=lambda v: "Informe o motivo (mín. 3 caracteres)"
                             if len((v or "").strip()) < 3 else None) \
            .props("outlined dense autogrow").classes("w-full")

        def excluir():
            try:
                ok, msg = gest.soft_delete_usuario(ator, nome, motivo.value)
                if not ok:
                    log.error(f"excluir_usuario: falha na exclusão lógica de {nome} por {ator} | {msg}")
                notificar(msg, tipo="positive" if ok else "negative")
                if ok:
                    dlg.close()
                    refresh()
            except Exception:
                log.exception(f"excluir_usuario: falha na exclusão lógica de {nome} por {ator}")
                notificar("Erro inesperado ao excluir usuário", tipo="error")

        with ui.row().classes("w-full justify-between mt-2"):
            botao("Cancelar", on_click=dlg.close, variante="texto",
                  chave_modulo="usuarios")
            botao("Excluir (lógico)", variante="primario", compacto=True,
                  icone="delete_outline", on_click=excluir,
                  chave_modulo="usuarios")
    dlg.open()

def _dlg_excluir_definitivo(ator, nome, refresh):
    """Stage 2 (deleted list only): permanent removal (LGPD).

    Estágio 2 (apenas na lista de excluídos): remoção PERMANENTE do banco
    (LGPD — direito ao esquecimento), protegida por confirmação digitada;
    remove também postagens/comentários do Blog, arquivos PDF e cota, com
    autoria de empenhos anonimizada e auditoria preservada. Card com borda
    vermelha (`dialogo_card` + classes extras); rodapé às extremidades
    mantido cru, ação via `botao` primário compacto.
    """
    try:
        _dlg_excluir_definitivo_seguro(ator, nome, refresh)
    except Exception:
        log.exception(f"_dlg_excluir_definitivo: falha ao abrir exclusão definitiva de {nome} por {ator}")
        notificar("Erro ao abrir exclusão definitiva", tipo="negative")

def _dlg_excluir_definitivo_seguro(ator, nome, refresh):
    """Body of `_dlg_excluir_definitivo`, isolated so the entry point can protect it."""
    with dialogo_card(largura="w-[440px]", chave_modulo="usuarios",
                      max_altura=False) as (dlg, card):
        card.classes("border-2 border-red-6")
        ui.label("⚠ Exclusão definitiva").classes("text-h6 text-red-9")
        ui.label(
            f"Esta ação apaga PERMANENTEMENTE '{nome}' do banco de dados "
            "(conformidade LGPD — direito ao esquecimento).\n"
            "Também serão removidos: postagens e comentários do Blog, "
            "arquivos PDF do editor (físicos) e respectiva cota; registros de empenhos "
            "serão preservados com autoria anonimizada.\n"
            "Histórico de auditoria é preservado. Esta ação não pode ser desfeita."
        ).classes("text-body2 whitespace-pre-line")
        confirmacao = ui.input(f'Digite "{nome}" para confirmar').props("outlined dense").classes("w-full")

        def excluir():
            try:
                if confirmacao.value != nome:
                    notificar("Confirmação não corresponde", tipo="negative")
                    return
                ok, msg = gest.excluir_usuario_definitivo(ator, nome)
                if not ok:
                    log.error(f"excluir_definitivo: falha ao excluir {nome} por {ator} | {msg}")
                notificar(msg, tipo="positive" if ok else "negative")
                if ok:
                    dlg.close()
                    refresh()
            except Exception:
                log.exception(f"excluir_definitivo: falha ao excluir {nome} por {ator}")
                notificar("Erro inesperado ao excluir definitivamente", tipo="error")

        with ui.row().classes("w-full justify-between mt-2"):
            botao("Cancelar", on_click=dlg.close, variante="texto",
                  chave_modulo="usuarios")
            botao("Excluir definitivamente", variante="primario", compacto=True,
                  icone="warning", cor="negative", on_click=excluir,
                  chave_modulo="usuarios")
    dlg.open()

# ==================== ABA 1.5: EXCLUÍDOS (SOFT) ====================

def _dlg_duplicar(ator, origem, refresh):
    """Duplicate-user dialog: clones profile and per-module access.

    Diálogo de duplicação: novo login herda o perfil global e os acessos
    por módulo do usuário origem (pré-selecionados); shell padronizado
    (`dialogo_card`), notificações via `notificar` e rodapé padrão com
    "Duplicar usuário" (ícone `content_copy`, **sem cor fixa** — segue a cor
    escolhida por quem está usando; ver `preview_estilos.cor_do_botao`). O
    label do campo de senha mostra o mínimo vigente via `gest.senha_minima()`.
    """
    try:
        _dlg_duplicar_seguro(ator, origem, refresh)
    except Exception:
        log.exception(f"_dlg_duplicar: falha ao abrir duplicação de {origem} por {ator}")
        notificar("Erro ao abrir duplicação de usuário", tipo="negative")

def _dlg_duplicar_seguro(ator, origem, refresh):
    """Body of `_dlg_duplicar`, isolated so the entry point can protect it."""
    row = gest.obter_usuario(origem)
    if not row:
        notificar("Usuário origem não encontrado", tipo="negative")
        return
    origem_perfil = row[5]
    acessos = gest.listar_acessos(origem)

    with dialogo_formulario(f"Duplicar usuário — @{origem}", chave_modulo="usuarios",
                            descricao="O novo usuário herdará o perfil global e os acessos por módulo "
                                      "do usuário origem, que já vêm pré-selecionados abaixo."
                            ) as (dlg, card, miolo, grade):
        with miolo:
            ui.label(f"Origem: @{origem} · perfil {origem_perfil.replace('_', ' ')}"
                     f" · {len(acessos)} acesso(s) por módulo") \
                .classes("text-caption bg-teal-1 text-teal-9 px-2 py-1 rounded")

        with grade:
            nome = ui.input("Nome de usuário (login) *").props("outlined dense").classes("w-full") \
                .tooltip("Usado apenas para entrar — não aparece como tratamento")
            completo = ui.input("Nome completo ou social *", placeholder="ex.: Maria Aparecida da Silva") \
                .props("outlined dense").classes("w-full") \
                .tooltip("Nome para tratamento nas telas. Pode ser o nome social "
                         "(Decreto 8.727/2016). Deve ser diferente do login")
            senha = ui.input(f"Senha provisória * (mín. {gest.senha_minima()})", password=True,
                             password_toggle_button=True,
                             value="123456").props("outlined dense").classes("w-full")
            email = ui.input("E-mail").props("outlined dense").classes("w-full")
            try:
                from mod_skyrover import telefone as _tel_dup
                _campo_fone_dup = _tel_dup.criar_campo_telefone(
                    rotulo="Telefone (opcional)", valor="")
            except Exception:
                _campo_fone_dup = None
                fone = ui.input("Telefone (opcional)").props("outlined dense").classes("w-full")

        with miolo:
            ui.separator()
            ui.label(f"Acessos por módulo (copiados de @{origem})").classes(
                "text-subtitle2 text-grey-8")
            box = ui.column().classes("w-full gap-0")
            selecoes, _meta = _seletores_de_acesso(box, origem)

            def _fone_dup_valor():
                try:
                    if _campo_fone_dup is not None:
                        return _campo_fone_dup["obter"]() or None
                    return fone.value.strip() or None
                except Exception:
                    return None

            def salvar():
                try:
                    senha_padrao = (senha.value or "").strip() or "123456"
                    ok, msg = gest.duplicar_usuario(ator, origem, nome.value or "",
                                                    senha_padrao,
                                                    email=email.value.strip() or None,
                                                    fone=_fone_dup_valor(),
                                                    nome_completo=completo.value)
                    if not ok:
                        log.error(f"duplicar_usuario: falha ao duplicar '{nome.value}' por {ator} | {msg}")
                        notificar(msg, tipo="negative")
                        return
                    mudou, erros = _aplicar_acessos(ator, nome.value.strip(), selecoes)
                    if erros:
                        notificar(f"Usuário duplicado, mas houve erros nos acessos: {' | '.join(erros)}",
                                  tipo="warning")
                    else:
                        notificar(f"Usuário '{nome.value.strip()}' duplicado de @{origem}"
                                  + (f" · {mudou} acesso(s)" if mudou else ""), type="positive")
                    dlg.close()
                    refresh()
                except Exception:
                    log.exception(f"duplicar_usuario: falha ao duplicar '{nome.value}' por {ator}")
                    notificar("Erro inesperado ao duplicar usuário", tipo="error")

            rodape_dialogo(dlg, acoes=[("Duplicar usuário", salvar,
                                        {"icone": "content_copy", "cor": "teal-8"})],
                           chave_modulo="usuarios", classes_extra="mt-3")
    dlg.open()

# ==================== ABA 2: SESSÕES ATIVAS ====================

def _painel_sessoes(ator: str, refreshers=None):
    """Active sessions tab with per-row terminate actions.

    Aba Sessões Ativas: contagem, botão "Atualizar" (mantido cru — nenhuma
    variante padronizada é byte-idêntica ao `flat no-caps icon=refresh`) e
    grade de sessões com ações de encerramento padronizadas
    (`botao_icone`).
    """
    box = ui.column().classes("w-full gap-2")

    def refresh():
        try:
            box.clear()
            sessoes = gest.listar_sessoes_ativas()
            with box:
                with ui.row().classes("w-full justify-between items-center flex-wrap"):
                    ui.label(f"{len(sessoes)} sessão(ões) ativa(s)").classes("text-subtitle1 font-bold")
                    botao("Atualizar", icone="refresh", on_click=refresh,
                        variante="texto", chave_modulo="usuarios")
                if not sessoes:
                    ui.label("Nenhuma sessão ativa no momento.").classes("text-grey-6")
                with ui.grid(columns="auto 1fr 0.9fr 1.2fr 1fr auto auto").classes(
                        "w-full bg-grey-1 rounded-lg px-3 py-2 text-caption font-bold text-grey-8"):
                    for c in ("#", "Usuário", "Origem", "Login", "IP", "Dispositivo", "", ""):
                        ui.label(c)
                for sid, usuario, modulo, login, cookie, ip, disp, mac in sessoes:
                    with ui.grid(columns="auto 1fr 0.9fr 1.2fr 1fr auto auto").classes(
                            "w-full border-b border-grey-2 px-3 py-1.5 items-center"):
                        with ui.column().classes("gap-0 leading-tight items-start"):
                            ui.label(str(sid)).classes("text-caption text-grey-6")
                            if mac and mac != "—":
                                ui.icon("fingerprint").classes("text-grey-5 text-xs") \
                                    .tooltip(f"MAC: {mac}")
                        ui.label(usuario).classes("font-medium")
                        ui.label(modulo or "sistema").classes("text-caption")
                        ui.label((login or "").replace("T", " ")[:19]).classes("text-caption")
                        ui.label(ip).classes("text-caption font-mono")
                        ui.label(disp).classes("text-caption")
                        botao_icone("cancel_schedule_send", on_click=lambda _, u=usuario: (
                            gest.encerrar_todas_sessoes(ator, u), refresh()),
                            tooltip=f"Encerrar TODAS as sessões de {usuario}",
                            chave_modulo="usuarios")
                        botao_icone("logout", on_click=lambda _, i=sid: (
                            gest.encerrar_sessao(ator, i), refresh()),
                            tooltip="Encerrar esta sessão",
                            chave_modulo="usuarios")
        except Exception:
            log.exception("painel_sessoes: falha ao atualizar sessões ativas")
            notificar("Erro ao atualizar sessões ativas", tipo="error")

    refresh()
