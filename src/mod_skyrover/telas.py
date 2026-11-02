"""4-part system layout: header, drawer, content and footer.

Layout de 4 partes do sistema: header, drawer, conteúdo e footer.

Uso dentro de uma função @ui.page:

    from mod_skyrover.telas import pagina_restrita

    @ui.page("/blog")
    def page_blog():
        usuario = pagina_restrita("Blog", chave_modulo="blog")
        if not usuario:
            return
        # ... construir conteúdo
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import asyncio

from nicegui import ui, app, run

from mod_skyrover import politica_senha

from mod_skyrover import autenticacao
from mod_skyrover import ui_comum
from mod_skyrover.bd_conexao import get_config as _obter_config
from mod_skyrover.tema_modulo import botao as _botao_tema
from mod_skyrover.tema_modulo import notificar

# Logger do fluxo de LOGIN/troca de credenciais. A função (e não uma
# constante) porque é resolvida no 1º uso e memorizada: os call sites já
# usavam `_login_erro_log()`, que nunca foi definida — o NameError caía no
# `except Exception: pass` e TODOS os erros de login sumiam sem log.
_login_erro_logger = None


def _login_erro_log():
    """EN: Returns the login-flow logger (loguru, fail-soft).

    PT-BR: Retorna o logger do fluxo de login (loguru, fail-soft).

    Memoriza o logger na primeira chamada. Nunca levanta: se a observabilidade
    falhar, devolve o logger padrão do loguru para o `except` do chamador
    seguir funcionando."""
    global _login_erro_logger
    if _login_erro_logger is None:
        try:
            from mod_skyrover import observabilidade as _obs
            _login_erro_logger = _obs.get_logger("skyrover")
        except Exception:
            try:
                from loguru import logger as _logger_padrao
                _login_erro_logger = _logger_padrao
            except Exception:
                return None
    return _login_erro_logger


def usuario_logado():
    """Returns the session user dict or None.

    Retorna o dict do usuário da sessão ou None."""
    return app.storage.user.get("usuario")


ROTA_TROCA_OBRIGATORIA = "/troca-obrigatoria"


def _pendencia_de_troca(nome_usuario: str) -> str:
    """O que está pendente para este usuário: `credenciais`, `senha` ou "".

    Fail-soft de propósito: se a consulta ao banco falhar, devolve "" e a
    pessoa entra normalmente. Um banco instável não pode transformar o primeiro
    acesso em parede — o gestor do sistema cairia no mesmo buraco que o usuário.
    """
    try:
        if autenticacao.precisa_trocar_credenciais(nome_usuario):
            return "credenciais"
        if autenticacao.precisa_trocar_senha(nome_usuario):
            return "senha"
        return ""
    except Exception as e:
        try:
            _login_erro_log().exception(
                f"pendencia_de_troca: falha ao consultar '{nome_usuario}': {e}")
        except Exception:
            pass
        return ""


def tela_troca_obrigatoria():
    """Tela SOLTA da troca obrigatória, sem layout e sem menu.

    Fica numa rota própria (`/troca-obrigatoria`) e é de lá que `pagina_restrita`
    manda quem tem pendência. Três consequências, e todas importam:

    - **Não há o que navegar.** Sem cabeçalho, sem drawer, sem menu de módulos,
      não existe botão de módulo para clicar nem link para seguir. A pergunta
      "dá para contornar a troca?" deixa de ter resposta pela interface.
    - **Só com sessão.** Sem `usuario_logado`, vai para `/login` — a tela da
      troca não vira uma porta de entrada.
    - **Só a troca.** Se não houver pendência (a pessoa já trocou e recarregou,
      ou o `Sair` devolveu para o login), vai para `/`. Sem isso, o caminho de
      volta seria um beco sem saída: `pagina_restrita` devolveria para cá, e
      esta tela devolveria para cá.

    O passo seguinte do primeiro acesso (telefone e dados) NÃO mora aqui: ele
    roda em `/`, dentro de `_primeiro_acesso`, depois que a senha já foi
    trocada. Assim o encadeamento continua o de sempre e esta tela tem uma
    única responsabilidade.
    """
    user = usuario_logado()
    if not user:
        ui.navigate.to("/login")
        return
    nome = user.get("nome", "")
    pendencia = _pendencia_de_troca(nome)
    if not pendencia:
        ui.navigate.to("/")
        return

    # Sem `_montar_layout`: é essa a razão de a tela existir separada.
    #
    # A tela nasce no MESMO padrão do login — WhatsApp (`PADRAO_LOGIN`) — por
    # decisão do responsável (30/09/2026). É a continuação da entrada no
    # sistema: quem chegou aqui acabou de fazer login, e ver uma cor diferente
    # na tela seguinte parece dois sistemas. O fundo vem da paleta do estilo,
    # não de `cor_fundo` do admin, que é cinza e deixava a tela morta.
    try:
        from mod_skyrover import preview_estilos as _pv
        paleta = _pv.aplicar(_pv.PADRAO_LOGIN)
        fundo = (paleta or {}).get("fundo") or ui_comum.CORES["fundo"]
        ui.query("body").classes("bg-grey-2")
        ui.query("body").style(f"background:{fundo}")
        try:
            ui.query(".q-page").style(f"background-color:{fundo}")
        except Exception:
            pass
        # O token `--q-primary` do padrão só é aplicado em elemento que carrega
        # a classe `pe-<chave>` — é assim que o CSS sabe qual estilo está em
        # vigor. Sem um elemento com essa classe, a regra nunca casa e a tela
        # fica com a cor padrão do Quasar, não com a do WhatsApp.
        #
        # O elemento é invisível e ocupa nada: ele existe só para acionar o
        # seletor, inclusive o de `.q-dialog` (o diálogo do NiceGUI vive num
        # portal no `body`, fora desta página).
        ui.element("div").classes(f"pe-{_pv.PADRAO_LOGIN}") \
            .style("display: none")
    except Exception as e:
        try:
            _login_erro_log().exception(
                f"troca_obrigatoria: falha ao aplicar o padrão visual: {e}")
        except Exception:
            pass

    def _voltar_ao_inicio(_novo_nome=None):
        """Troca concluída: entra no sistema de verdade."""
        ui.navigate.to("/")

    # ======================= A TROCA É A TELA DE LOGIN (30/09/2026) =========
    # A troca de senha não é mais um cartão dentro de uma página, nem um
    # diálogo por cima dela: é a PRÓPRIA tela de login, montada pelo mesmo
    # `preview_estilos.tela_login` que monta `/login`, com o formulário da
    # troca no lugar dos campos de usuário e senha.
    #
    # Não é semelhança decorativa — é a continuação da entrada no sistema.
    # Quem chegou aqui acabou de fazer login; ver um cartão flutuando sobre um
    # fundo cinza logo depois da tela verde do WhatsApp parecia dois sistemas
    # diferentes. Aqui é a MESMA tela, com o texto da troca no lugar onde o
    # login escreve "SKYROVER Básica" — o nome do sistema desce para subtítulo,
    # porque é ele que identifica o produto, não a tarefa do momento.
    #
    # `campos` é uma CALLBACK: quem desenha é a função, e o `tela_login` só
    # entrega o invólucro. É o mesmo contrato do login, e por isso trocar de
    # padrão visual não pode quebrar a troca.
    #
    # O PRIMEIRO ACESSO DO `master` (`credenciais`) entrou no mesmo ramo em
    # 04/10/2026, por decisão do responsável: os CAMPOS dele são os de sempre
    # (os sete, com o mesmo pré-preenchimento), só mudava o padrão de
    # exibição — ele saía num cartão flutuante enquanto todo mundo else já
    # entrava pela tela de login. Dois jeitos de fazer a mesma coisa é a
    # origem de divergência de layout, e a que existia aqui já estava
    # medida quebrando a tela. As duas pendências agora são o mesmo código com
    # o formulário trocado.
    _eh_credenciais = pendencia == "credenciais"
    _formulario = (_formulario_troca_credenciais if _eh_credenciais
                   else _formulario_troca_senha)
    _titulo_troca = ("Credenciais obrigatórias" if _eh_credenciais
                     else "Troca de senha obrigatória")
    if _eh_credenciais:
        # A tela do master é a mais cheia do sistema: sete campos e dois
        # blocos informativos. Por isso ela dispensa o cabeçalho do cartão e
        # o rodapé (04/10/2026) — o nome do produto aparece no painel teal.
        #
        # A dica verde traz as REGRAS DE SENHA, as mesmas da troca comum
        # (`politica_senha.regras_para_tela`). Antes ela trazia só o texto
        # institucional e o administrador escolhia a senha sem ver o padrão
        # exigido; a indicação vale para o `master` igual vale para todos.
        _hint_troca = politica_senha.regras_para_tela()
        _cabecalho = False
        _rodape = False
        # O tooltip continua mostrando os dados do responsável, com 3s de
        # demora para não piscar a cada passagem do mouse.
        _dica_tooltip = TEXTO_DADOS_RESPONSAVEL
        _dica_atraso = DEMORA_TOOLTIP_DADOS_MS
    else:
        # A dica da tela de troca é a LISTA DE REGRAS (18/10/2026, pedido do
        # responsável: "identifique quais são as regras de senha e coloque
        # elas bem escritas no campo que atualmente temos 'você ainda está na
        # porta de entrada...'"). As regras vinham em mensagens de erro, uma
        # de cada vez — e quem escolhe a senha não tem como saber a regra
        # ANTES de errar. A frase da porta de entrada saiu: ela não é regra,
        # e a lista já diz o que fazer.
        _hint_troca = politica_senha.regras_para_tela()
        _cabecalho = True
        _rodape = True
        _dica_tooltip = ""
        _dica_atraso = 0

    try:
        from mod_skyrover import preview_estilos as _pv
        nome_sistema = (_obter_config("texto_login_titulo", "SKYROVER Básica")
                        or "SKYROVER Básica")

        def _campos():
            _formulario(nome, ao_concluir=_voltar_ao_inicio)

        _pv.tela_login(
            _pv.PADRAO_LOGIN,
            icone=(_obter_config("icone_sistema", "hub") or "hub").strip(),
            titulo=_titulo_troca,
            subtitulo=nome_sistema,
            hint=_hint_troca,
            paleta=paleta,
            campos=_campos,
            cabecalho=_cabecalho,
            rodape=_rodape,
            dica_tooltip=_dica_tooltip,
            dica_atraso_ms=_dica_atraso,
            # SEM `largura_caixa`: a troca usa o PADRÃO, o mesmo do login
            # (05/10/2026, decisão do responsável). Antes este era o lugar de
            # 880px para a tela de credenciais do `master` e 640px para a
            # troca dos outros usuários — três larguras diferentes na mesma
            # tela, dependendo de quem abria. Com o padrão em 680px e o
            # padding lateral em 12px, a coluna do `master` sai com 319px (era
            # 279px a 640px, o que obrigava a cortar o telefone) e o DDI e o
            # número cabem inteiros lado a lado. A conta está em
            # `preview_estilos.LARGURA_CAIXA_PADRAO`.
            # O painel (campo grande à esquerda) diz o que está sendo pedido;
            # a caixa branca identifica o produto. Repetir a frase da troca
            # nos dois campos era o que se via antes.
            #
            # 05/10/2026: a marca do cartão passou a ser "SKYROVER" FIXO, e
            # não mais o `nome_sistema` configurável ("SKYROVER Básica"). O
            # responsável pediu o mesmo texto que o login usa no cartão, e os
            # dois cartões precisam dizer a MESMA coisa — antes o login
            # mostrava uma marca e a troca mostrava outra, e quem passava por
            # uma tela e depois pela outra via a troca parecia outro sistema.
            # `nome_sistema` continua no painel teal, que é onde o nome por
            # extenso faz sentido.
            titulo_caixa="SKYROVER")
    except Exception as e:
        _login_erro_log().exception(
            f"troca_obrigatoria: falha ao montar a tela da troca: {e}")
        notificar("Erro ao carregar a troca de senha.", tipo="error")
        # A tela de login é o caminho padrão, mas o `master` não pode ficar
        # sem porta de entrada: se ela não montar, cai no diálogo, que é
        # feio e não é responsivo, porém funciona. Mesmo servindo de
        # reserva, o diálogo é o caminho que nunca fica sem campo.
        if _eh_credenciais:
            try:
                _dialogo_troca_credenciais(nome, ao_concluir=_voltar_ao_inicio)
            except Exception as _e_dlg:
                try:
                    _login_erro_log().exception(
                        f"troca_obrigatoria: diálogo de reserva falhou para "
                        f"'{nome}': {_e_dlg}")
                except Exception:
                    pass



def pagina_restrita(titulo_modulo: str, chave_modulo: str = None):
    """Guard de autenticação + layout completo. Retorna dict do usuário ou None.

    Se não autenticado, redireciona para /login.
    """
    user = usuario_logado()
    if not user:
        ui.navigate.to("/login")
        return None

    # Revalida contra o BD a cada request: bloqueio/exclusão/renomeio derrubam a sessão viva
    linha_bd = autenticacao.usuario_existe(user.get("nome", ""))
    if not linha_bd or not linha_bd[2]:
        app.storage.user.clear()
        notificar("Sua sessão foi encerrada pelo administrador.", tipo="warning")
        ui.navigate.to("/login")
        return None

    # Sessão revogável: se o admin encerrou esta sessão no banco, o navegador cai
    hash_sessao = user.get("sessao")
    if hash_sessao:
        if not autenticacao.sessao_ativa(user["nome"], hash_sessao):
            app.storage.user.clear()
            notificar("Sua sessão foi encerrada pelo administrador.", tipo="warning")
            ui.navigate.to("/login")
            return None
    else:
        # Sessões anteriores à rastreabilidade não têm hash amarrado:
        # adota agora (nova linha com IP/UA deste acesso) e passa a ser revogável
        user["sessao"] = autenticacao.registrar_login(user["nome"], "sistema")
        app.storage.user["usuario"] = user

    # Timeout de inatividade (24/10/2026, fase 2 do pós-pentest): cada
    # passagem pelo guard carimba `ultimo_acesso`; parado além de
    # `sessao_timeout_min` (padrão 30, 0 = desligado), a sessão cai e
    # volta ao login. É por navegação, não por tecla: aba aberta sem
    # navegar continua "parada" — documentado, não é falha.
    try:
        _limite_min = int(float(_obter_config("sessao_timeout_min", "30")))
    except Exception:
        _limite_min = 30
    if _limite_min > 0:
        try:
            import time as _tempo_sessao
            _agora = _tempo_sessao.time()
            _ultimo = (user.get("ultimo_acesso") or 0)
            if _ultimo and (_agora - float(_ultimo)) > _limite_min * 60:
                app.storage.user.clear()
                notificar("Sessão encerrada por inatividade.",
                          tipo="warning")
                ui.navigate.to("/login")
                return None
            user["ultimo_acesso"] = _agora
            app.storage.user["usuario"] = user
        except Exception:
            pass

    # ===== TROCA OBRIGATÓRIA PENDENTE: a página NÃO pode ser montada =====
    # Este é o único ponto por onde passa TODA rota protegida, então é aqui que
    # a troca obrigatória vira de verdade obrigatória.
    #
    # Antes o diálogo era só um modal sobre a página já montada: `_montar_layout`
    # rodava primeiro (cabeçalho, drawer e menu com todos os módulos), o
    # diálogo abria por cima e `pagina_restrita` devolvia o usuário — o `with`
    # do chamador continuava e desenhava a tela inteira. O `persistent` só
    # impedia FECHAR o diálogo; ele não impede NAVEGAR. O usuário relatou
    # exatamente isso: clicou em "voltar" e navegou entre páginas que o sistema
    # já tinha pré-carregado.
    #
    # A correção é do lado do servidor, não do modal: enquanto a pendência
    # existir, ninguém chega a montar layout nenhum. Botão "voltar", URL
    # digitada, link pré-carregado — todos passam por aqui e voltamos para a
    # tela da troca. Um modal que se pode contornar não é uma trava.
    if (_pendencia_de_troca(user["nome"])):
        ui.navigate.to(ROTA_TROCA_OBRIGATORIA)
        return None

    papel_mod = autenticacao.papel_no_modulo(user["nome"], chave_modulo) if chave_modulo else None
    rotulo_perfil = f"{papel_mod.replace('_', ' ')} · neste módulo" if papel_mod \
        else user.get("perfil", "comum").replace("_", " ")

    # Bloqueio de acesso por módulo: impede navegação direta por URL de quem não
    # tem permissão (ex.: usuário comum acessando /auditoria). Check centralizado
    # aqui vale para todas as rotas que passam chave_modulo. Como passa por aqui
    # apenas usuários autenticados, o registro de 'acesso_negado' não polui com
    # bots/curl (tentativa de quem realmente tem conta).
    if chave_modulo and not autenticacao.validar_acesso_modulo(user["nome"], chave_modulo):
        try:
            from mod_skyrover.bd_manipulador import audit_log
            audit_log(user["nome"], chave_modulo, "acesso_negado",
                      f"tentou abrir o módulo '{chave_modulo}' sem permissão")
        except Exception:
            pass
        notificar("Acesso negado a este módulo.", tipo="negative")
        ui.navigate.to("/")
        return None

    # MÓDULO DESLIGADO PELO ADMINISTRADOR (02/10/2026).
    #
    # O teste de cima é PERMISSÃO ("este servidor pode entrar aqui?"). Este é o
    # outro eixo: LIGADO ("o sistema liga este módulo?"). Desde que a entrega
    # sobe com tudo desligado, os dois precisam ser verificados, e a ordem é a
    # que importa: primeiro quem não podia, agora quem podia mas o módulo não
    # está de pé.
    #
    # Sem esta trava o desligamento era só de menu: o card laranja avisava, e a
    # URL digitada abria a página igual. Um sistema que se entrega desligado e
    # abre o módulo pelo link não está desligado — está escondendo.
    #
    # `administrador_geral` passa: ele é quem LIGA o módulo, e não pode ficar
    # trancado do lado de fora da tela onde liga. Para ele a porta fica aberta
    # e o que resta é a tela de Configurações.
    if chave_modulo and not autenticacao.modulo_ativo(chave_modulo):
        if autenticacao.perfil_global_de(user["nome"]) != "administrador_geral":
            try:
                from mod_skyrover.bd_manipulador import audit_log
                audit_log(user["nome"], chave_modulo, "modulo_desligado",
                          f"tentou abrir o módulo '{chave_modulo}', que está desligado")
            except Exception:
                pass
            notificar(
                f"O módulo '{autenticacao.nome_do_modulo(chave_modulo) or chave_modulo}' "
                f"está desligado. Procure o administrador.", tipo="warning")
            ui.navigate.to("/")
            return None

    _montar_layout(user["nome"], rotulo_perfil, titulo_modulo, chave_modulo)

    try:
        # Primeiro acesso: senha -> telefones. `_primeiro_acesso` encadeia os
        # dois passos e só abre o segundo quando o primeiro foi concluído.
        _primeiro_acesso(user["nome"])
    except Exception as _e_troca:
        try:
            _login_erro_log().exception(
                f"pagina_restrita: falha ao abrir troca obrigatória de '{user.get('nome','')}': {_e_troca}")
        except Exception:
            pass
        try:
            notificar("Erro ao abrir a troca obrigatória — recarregue a página.", tipo="error")
        except Exception:
            pass

    return user


def _aplicar_tema_escuro(escuro: bool, chave_modulo: str = None):
    """Applies the user's dark-theme override (per-user, non-global).

    Aplica o tema escuro individual: ativa o dark mode do Quasar e injeta CSS
    com uma paleta em variáveis, na ordem MAIS ESCURO → MAIS CLARO (do que está
    mais ao fundo para o que está mais à frente):
      cor geral do módulo → fundo da página → fundo do card → cor do título →
      texto do módulo → texto do card. O tema claro (light) é o padrão — as
      cores escolhidas pelos administradores."""
    if not escuro:
        return
    try:
        ui.dark_mode(True)
    except Exception:
        pass
    from mod_skyrover import tema_modulo
    tema = tema_modulo.ler_tema(chave_modulo or "skyrover")
    p = tema_modulo.paleta_escura(tema)
    ui.query("body").classes("skyrover-dark")
    ui.add_head_html(f"""<style>
body.skyrover-dark {{
  --cor-geral: {p['cor_geral']};
  --fundo-pagina: {p['fundo_pagina']};
  --fundo-card: {p['fundo_card']};
  --cor-titulo: {p['cor_titulo']};
  --texto-modulo: {p['texto_modulo']};
  --texto-card: {p['texto_card']};
}}
body.skyrover-dark {{ background: var(--fundo-pagina) !important; }}
body.skyrover-dark .q-page {{ background-color: var(--fundo-pagina) !important; color: var(--texto-modulo); }}
body.skyrover-dark .q-card,
body.skyrover-dark .q-drawer,
body.skyrover-dark .q-dialog,
body.skyrover-dark .q-menu,
body.skyrover-dark .q-expansion-item__content,
body.skyrover-dark .q-table {{ background-color: var(--fundo-card) !important; color: var(--texto-card); }}
body.skyrover-dark .q-footer {{ background-color: #1a1a1a !important; }}
body.skyrover-dark .bg-white {{ background-color: var(--fundo-card) !important; }}
body.skyrover-dark .bg-grey-1,
body.skyrover-dark .bg-grey-2,
body.skyrover-dark .bg-grey-3 {{ background-color: var(--fundo-pagina) !important; }}
body.skyrover-dark .cabecalho-titulo {{ color: var(--cor-titulo) !important; }}
body.skyrover-dark .text-grey-9,
body.skyrover-dark .text-grey-8,
body.skyrover-dark .text-grey-7,
body.skyrover-dark .text-black {{ color: var(--texto-modulo) !important; }}
body.skyrover-dark .q-card .text-grey-9,
body.skyrover-dark .q-card .text-grey-8,
body.skyrover-dark .q-card .text-grey-7,
body.skyrover-dark .q-card .text-black {{ color: var(--texto-card) !important; }}
body.skyrover-dark .text-grey-6,
body.skyrover-dark .text-grey-5,
body.skyrover-dark .text-grey-4,
body.skyrover-dark .text-caption {{ color: var(--texto-modulo) !important; }}
body.skyrover-dark .q-field--outlined .q-field__control,
body.skyrover-dark .q-input,
body.skyrover-dark .q-textarea,
body.skyrover-dark .q-select,
body.skyrover-dark .q-number {{ background-color: var(--fundo-card) !important; color: var(--texto-card); }}
body.skyrover-dark input,
body.skyrover-dark textarea {{ color: var(--texto-card) !important; }}
body.skyrover-dark .q-field__label {{ color: var(--texto-modulo) !important; }}
body.skyrover-dark .q-item,
body.skyrover-dark .q-tab {{ color: var(--texto-modulo) !important; }}
body.skyrover-dark .q-separator {{ background-color: #3f3f3f !important; }}
body.skyrover-dark .q-chip {{ background-color: var(--fundo-card) !important; color: var(--texto-card); }}
</style>
""")


def _alternar_tema(user_nome: str):
    """Toggles the current user's dark/light theme preference (individual)."""
    novo = not autenticacao.tema_escuro(user_nome)
    autenticacao.definir_tema_escuro(user_nome, novo)
    ui.timer(0.1, lambda: ui.navigate.reload(), once=True)


def _montar_layout(nome_usuario: str, rotulo_perfil: str, titulo_modulo: str,
                    chave_modulo: str = None):
    """Builds the 4-part layout (header, drawer, content and footer).

    Monta o layout de 4 partes: header, drawer lateral, conteúdo e rodapé,
    aplicando cor principal, fundo, título do sistema e versões no rodapé.
    Espaçamentos via `.style("gap: …")` (visual 1:1, bug #2171/Ubuntu).
    """
    cores = _obter_cor_principal()
    # Estilo visual em vigor: a ESCOLHA deste navegador (cookie). Vazio
    # significa "Padrão" — e aí NENHUM estilo é imposto, para a cor que o
    # administrador deste módulo configurou aparecer como está. Precisa ser
    # resolvido e aplicado ANTES do cabeçalho: quando há estilo, ele redefine
    # `--q-primary`, que é a cor do cabeçalho e de todo elemento `bg-primary`.
    estilo_visual_usuario = ""
    try:
        from mod_skyrover import preview_estilos as _pv_estilos
        estilo_visual_usuario = _pv_estilos.estilo_efetivo()
        if estilo_visual_usuario:
            _pv_estilos.aplicar(estilo_visual_usuario, cor_principal=cores)
    except Exception:
        try:
            import logging
            logging.getLogger(__name__).exception(
                "telas: falha ao aplicar o estilo visual")
        except Exception:
            pass
    ui.colors(primary=cores, secondary=ui_comum.CORES["cinza_escuro"],
              accent=cores)
    fundo = _obter_config('cor_fundo', ui_comum.CORES["fundo"]) \
        or ui_comum.CORES["fundo"]
    ui.query("body").classes("bg-grey-2")
    ui.query("body").style(f"background:{fundo}")
    try:
        # O Quasar pinta .q-page por cima do body: sem isso o cor_fundo
        # configurado nunca aparece na área do conteúdo.
        ui.query(".q-page").style(f"background-color:{fundo}")
    except Exception:
        pass
    # Tema escuro individual do usuário (não afeta os demais).
    _aplicar_tema_escuro(autenticacao.tema_escuro(nome_usuario), chave_modulo)
    titulo_sistema = _obter_config("titulo_sistema", "SKYROVER") or "SKYROVER"
    icone_sistema = (_obter_config("icone_sistema", "hub") or "hub").strip()
    # Título da ABA do navegador acompanha o nome configurado.
    # Exceção intencional de "sem JS direto": via `ui.run_javascript` (API
    # oficial do NiceGUI), pois `ui.page(title=...)` é fixo por rota.
    import json as _json
    ui.run_javascript(f"document.title = {_json.dumps(titulo_sistema)}")
    # favicon com cache-busting: ?v muda quando o .ico é trocado
    from mod_skyrover.bd_conexao import favicon_versao
    ui.add_head_html(
        f'<link rel="icon" type="image/x-icon" href="/favicon.ico?v={favicon_versao()}">')
    # Título da página vem do cadastro de módulos (editável em Configurações)
    if chave_modulo:
        nome_cadastrado = autenticacao.nome_do_modulo(chave_modulo)
        if nome_cadastrado:
            titulo_modulo = nome_cadastrado

    # ===== HEADER (parte 1) =====
    with ui.header(elevated=True).classes("w-full bg-primary px-3 sm:px-4 py-1").style("min-width: 0"):
        with ui.row().classes("w-full items-center justify-between flex-wrap").style("gap: 0.5rem; min-width: 0"):
            with ui.row().classes("items-center flex-wrap flex-1").style("gap: 0.5rem; min-width: 0"):
                _btn_menu = ui_comum.botao_icone("menu", on_click=lambda: drawer.toggle(),
                                     variante="icone_branco",
                                     tooltip="Abrir menu de navegação")
                if _btn_menu is not None:
                    _btn_menu.props('data-testid=menu-hamburguer aria-label="Abrir menu de navegação"')
                ui.icon(icone_sistema).classes("text-white shrink-0")
                ui.label(titulo_sistema).classes("text-h6 text-white font-bold whitespace-nowrap")
                ui.separator().props("vertical")
                ui.label(titulo_modulo).classes("text-subtitle2 text-white opacity-90 flex-1").style("min-width: 8ch; overflow-wrap: anywhere")
            with ui.row().classes("items-center flex-wrap justify-end flex-1").style("gap: 0.5rem; min-width: 0"):
                # Nome de LOGIN (matrícula) clicável -> Meu Perfil, com o nome
                # de tratamento no tooltip (29/10/2026, pedido do responsável:
                # o menu superior mostra SEMPRE o login; a saudação usa
                # "Primeiro.ultimo").
                # Um único botão sempre visível: ellipsis à direita + tooltip completo.
                # (Sem toggles `hidden sm:*` — o tailwind embutido resolve `hidden`
                #  acima do `sm:flex`, então o botão sumia em qualquer largura.)
                # O conteúdo interno do q-btn é centralizado (`justify-content:center`),
                # então o CSS escopado abaixo ancora o texto à esquerda com ellipsis.
                try:
                    ui.add_head_html("""
<style>
/* Header — nome do usuário ancorado à esquerda com ellipsis à direita */
[data-testid="header-nome-usuario"] .q-btn__content{justify-content:flex-start !important;overflow:hidden}
[data-testid="header-nome-usuario"] .q-btn__content>span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
""")
                except Exception:
                    pass
                trat = autenticacao.nome_de_tratamento(nome_usuario)
                _btn_nome = ui_comum.botao(nome_usuario, variante="texto_branco",
                               on_click=lambda: _dialogo_meu_perfil(nome_usuario),
                               tooltip=trat)
                if _btn_nome is not None:
                    _btn_nome.props('data-testid=header-nome-usuario')
                    _btn_nome.classes("min-w-0 overflow-hidden whitespace-nowrap").style("min-width: 0; max-width: min(28ch, 55vw); overflow: hidden; text-overflow: ellipsis;")
                # Tema claro/escuro (preferência individual do usuário)
                escuro_atual = autenticacao.tema_escuro(nome_usuario)
                ui_comum.botao_icone(
                    "dark_mode" if escuro_atual else "light_mode",
                    on_click=lambda: _alternar_tema(nome_usuario),
                    variante="icone_branco",
                    tooltip="Tema atual: "
                            + ("escuro" if escuro_atual else "claro")
                            + " — clique para alternar (só para você)")
                ui.badge(rotulo_perfil, color="primary-4").props("outline").classes("max-w-[12ch] truncate shrink-0").style("min-width: 0")
                ui_comum.botao_icone("logout", _logout, variante="icone_branco",
                                     tooltip="Sair")

    # ===== DRAWER/SIDEBAR (parte 2) =====
    # Por padrão o drawer abre FECHADO — o usuário abre via botão hambúrguer.
    # Visual Bootstrap list-group SEM injeção global: o Bootstrap local
    # (assets/css/frameworks/bootstrap@5.3.8.min.css, servido em
    # /css/frameworks/* via tema_css.montar_rotas_static()) tem reset global
    # que quebraria o Quasar — por isso item_menu_drawer replica o visual
    # (borda arredondada, hover, ativo) via Tailwind (.classes()) + Quasar
    # (.props()). RNF-UI-01 320/768/1024: w-full + min-width: 0, sem gap-*.
    with ui.left_drawer(bordered=True, elevated=False, value=False).classes("p-2").style("min-width: 0") as drawer:
        with ui.column().classes("w-full").style("gap: 0.25rem; min-width: 0"):
            # ===== HOME: página inicial de boas-vindas =====
            ui_comum.item_menu_drawer(
                "Home", icone="home",
                on_click=lambda: ui.navigate.to("/"),
                tooltip="Ir para a página inicial",
                chave_modulo=chave_modulo or "skyrover",
                testid="menu-home",
                ativo=(not chave_modulo))

            ui.separator().classes("w-full")

            # ===== ORDENAÇÃO HAMBÚRGUER (requisito 2026-09-19) =====
            # Home fica isolado acima (já renderizado). Demais módulos em ordem
            # alfabética por nome, exceto Blog/Usuários/Auditoria/Hora Certa
            # que são agrupados após Administração e antes de
            # Documentação/Sair.
            _CHAVES_POS_ADMIN = {"blog", "usuarios", "auditoria", "hora_certa"}
            _ORDEM_POS_ADMIN = ["blog", "usuarios", "auditoria", "hora_certa"]
            _todos = autenticacao.modulos_do_usuario(nome_usuario)
            _map_todos = {c: (c, n, ic, r, a) for c, n, ic, r, a in _todos}
            _outros = [t for t in _todos if t[0] not in _CHAVES_POS_ADMIN]
            _outros.sort(key=lambda t: t[1].lower())
            _pos_admin = [_map_todos[c] for c in _ORDEM_POS_ADMIN if c in _map_todos]

            # Definido AQUI, e não só na seção "Sistema" mais abaixo, porque
            # `_render_lista_modulos` precisa dele para decidir se o card
            # laranja do módulo desligado entra no menu. Antes ele era calculado
            # depois da primeira chamada e o drawer inteiro era desenhado sem
            # essa informação.
            _eh_admin_geral_menu = (autenticacao.perfil_global_de(nome_usuario)
                                    == "administrador_geral")

            # Quarteto que fica no fim do menu (Blog/Usuários/Auditoria/Hora
            # Certa). Para quem não é admin geral, um item DESLIGADO é
            # descartado aqui — senão a lista continuaria não-vazia, o bloco
            # "if _pos_admin" entraria e desenharia só um separador solto,
            # sem nenhum item embaixo dele.
            if not _eh_admin_geral_menu:
                _pos_admin = [t for t in _pos_admin if t[4]]

            def _card_modulo_desligado(chave, nome):
                """Draws the orange 'module off' card (admin-only information).

                Desenha o card laranja de módulo desligado (informação do
                ADMINISTRADOR). Mora numa função porque é usado SÓ dentro do
                grupo "Desativados" (14/10/2026) — antes era desenhado no meio
                da lista, poluindo o menu.
                """
                with ui.item(on_click=lambda n=nome: notificar(
                        f"⚠ '{n}' está desligado. Ligue em Configurações → Módulo.",
                        tipo="warning", position="top")) \
                        .classes("w-full rounded-lg my-0.5 bg-orange-2 border border-orange-6 cursor-pointer "
                                 "focus-visible:ring-2 focus-visible:outline-none") \
                        .style("min-width: 0") \
                        .props(f'data-testid=menu-{chave}-indisponivel aria-label="{nome} — módulo desligado"') \
                        .tooltip(f"'{nome}' está desligado — ligue em Configurações → Módulo"):
                    with ui.item_section().props("avatar"):
                        ui.icon("report_problem").classes("text-orange-9 shrink-0").props('aria-hidden="true"')
                    with ui.item_section().style("min-width: 0"):
                        ui.item_label(nome).classes("text-orange-10 font-bold truncate max-w-full").style("min-width: 0")
                        ui.item_label("Módulo desligado").classes("text-caption text-orange-9 truncate max-w-full").style("min-width: 0")

            # Desligados NÃO entram mais na lista (14/10/2026, pedido do
            # responsável): são coletados aqui e desenhados de uma vez no
            # grupo "Desativados", entre Documentação e Sair.
            _desativados = []

            def _render_lista_modulos(lista):
                """Renders a list of drawer entries (active ones inline).

                Renderiza uma lista de entradas do drawer (só as ativas, em
                linha).

                **Módulo desligado (02/10/2026, grupo próprio desde
                14/10/2026):** o card laranja é informação do ADMINISTRADOR
                — "existe, mas você não ligou". Mostrar isso a um servidor
                comum seria ruído: ele não pode ligar nada, e o que precisa
                é que o módulo simplesmente não exista para ele. Por isso a
                lista é filtrada aqui, e não em `modulos_do_usuario`: quem
                chama essa função também monta as telas de liberação de
                acesso, onde o módulo desligado PRECISA aparecer (é lá que
                se escolhe a quem dar permissão). Para admin geral, o
                desligado não é desenhado aqui: é coletado em `_desativados`
                e sai de uma vez no grupo "Desativados".
                """
                for chave, nome, icone, rota, ativa in lista:
                    if ativa:
                        ui_comum.item_menu_drawer(
                            nome, icone=icone,
                            on_click=lambda r=rota: ui.navigate.to(r),
                            tooltip=f"Abrir o módulo {nome}",
                            chave_modulo=chave_modulo or "skyrover",
                            testid=f"menu-{chave}",
                            ativo=(chave == chave_modulo))
                    elif _eh_admin_geral_menu:
                        _desativados.append((chave, nome))

            _render_lista_modulos(_outros)

            # Padrão PIC definido — exemplos de CSS removidos do menu (mantidos em disco/docs para comparação direta via URL se necessário).

            # ===== SISTEMA: Administração + trio Blog/Usuários/Auditoria + Documentação =====
            _eh_admin_geral = _eh_admin_geral_menu
            if _eh_admin_geral:
                ui.separator().classes("w-full")
                if chave_modulo:
                    _nome_mod_atual = autenticacao.nome_do_modulo(chave_modulo) or chave_modulo
                    _admin_label = "Administração"
                    _admin_tooltip = f"Configurações de {_nome_mod_atual}"
                else:
                    _admin_label = "Administração (sistema)"
                    _admin_tooltip = "Configurações gerais do sistema"
                ui_comum.item_menu_drawer(
                    _admin_label, icone="admin_panel_settings",
                    on_click=lambda cm=chave_modulo: ui.navigate.to(
                        f"/admin/{cm}" if cm else "/configuracoes"),
                    tooltip=_admin_tooltip,
                    chave_modulo=chave_modulo or "skyrover",
                    testid="menu-admin",
                    ativo=False)

            # Trio Blog/Usuários/Auditoria — sempre após Administração (se houver) e antes de Documentação/Sair
            if _pos_admin:
                if not _eh_admin_geral:
                    ui.separator().classes("w-full")
                _render_lista_modulos(_pos_admin)

            if _eh_admin_geral:
                # Documentação MkDocs servida em /documentacao (main.py monta o site/)
                ui_comum.item_menu_drawer(
                    "Documentação", icone="menu_book",
                    on_click=lambda: ui.navigate.to(
                        "/documentacao", new_tab=True),
                    tooltip="Abre a documentação técnica em nova aba",
                    chave_modulo=chave_modulo or "skyrover",
                    testid="menu-docs",
                    ativo=False)

            ui.separator().classes("w-full")
            ui_comum.item_menu_drawer(
                "Sair", icone="logout", on_click=_logout,
                tooltip="Encerrar a sessão e sair do sistema",
                chave_modulo=chave_modulo or "skyrover",
                testid="menu-sair",
                ativo=False)

            # ===== DESATIVADOS (14/10/2026, pedido do responsável) =====
            # Módulos desligados centralizados num grupo APÓS o Sair — o menu
            # deixa de exibir um card laranja no meio da lista para cada um.
            # A lista abre no hover/focus (CSS escopado, sem vazar) e o CLIQUE
            # fixa aberta para toque (remove/add de classe via API NiceGUI,
            # sem JavaScript). Só existe para admin geral e some quando não
            # há nenhum desligado.
            if _eh_admin_geral and _desativados:
                try:
                    ui.add_head_html("""
<style>
/* Grupo Desativados — lista escondida, revela no hover/focus; .lista-aberta fixa aberto (toque) */
[data-testid="menu-desativados"] .lista-desativados{display:none}
[data-testid="menu-desativados"]:hover .lista-desativados,
[data-testid="menu-desativados"]:focus-within .lista-desativados,
[data-testid="menu-desativados"] .lista-desativados.lista-aberta{display:flex}
</style>
""")
                except Exception:
                    pass
                with ui.column().classes("w-full").style(
                        "gap: 0; min-width: 0").props(
                        'data-testid=menu-desativados'):
                    with ui.column().classes("w-full").style(
                            "gap: 0; min-width: 0"):
                        ui_comum.item_menu_drawer(
                            f"Desativados ({len(_desativados)})",
                            icone="visibility_off",
                            on_click=lambda: _sub_desativados.classes(
                                toggle="lista-aberta"),
                            tooltip="Módulos desligados — passe o mouse para "
                                    "ver, clique para fixar aberto",
                            chave_modulo=chave_modulo or "skyrover",
                            testid="menu-desativados-cabecalho",
                            ativo=False)
                    with ui.column().classes(
                            "w-full lista-desativados").style(
                            "gap: 0.25rem; min-width: 0; "
                            "padding-left: 0.5rem") as _sub_desativados:
                        for _chave_des, _nome_des in _desativados:
                            _card_modulo_desligado(_chave_des, _nome_des)

    # ===== FOOTER (parte 4) =====
    # Rodapé ESCONDIDO durante a navegação, revelado no hover/focus (faixa de
    # 5px como pista). É onde mora a escolha de estilo visual — escondido para
    # não roubar altura da tela de quem está trabalhando, e um mouse na base da
    # janela abre. CSS escopado via [data-testid="rodape-sistema"], sem
    # vazamento global.
    try:
        ui.add_head_html("""
<style>
/* Rodape — escondido por padrão, revela no hover/focus */
[data-testid="rodape-sistema"]{opacity:0;transform:translateY(calc(100% - 5px));transition:opacity .25s ease,transform .25s ease}
[data-testid="rodape-sistema"]:hover,[data-testid="rodape-sistema"]:focus-within{opacity:1;transform:none}
</style>
""")
    except Exception:
        pass
    with ui.footer().classes("bg-grey-8 w-full").props('data-testid=rodape-sistema').style("min-width: 0"):
        with ui.row().classes("w-full items-center justify-between flex-wrap px-4 py-1").style("gap: 0.5rem; min-width: 0"):
            texto_rodape = _obter_config("texto_rodape", "uso interno") or "uso interno"
            ui.label(f"{titulo_sistema} Básica — {texto_rodape}").classes(
                "text-caption opacity-80")
            # Escolha de estilo visual: mora no COOKIE deste navegador, então
            # o padrão escolhido é só dele e não viaja com o usuário para
            # outra máquina. Fica no meio do rodapé para ser Achado sem caçar a
            # beira, e disponível em QUALQUER módulo.
            try:
                from mod_skyrover import preview_estilos as _pv_estilos
                _pv_estilos.barra_alternador(estilo_visual_usuario, discreto=True)
            except Exception:
                try:
                    import logging
                    logging.getLogger(__name__).exception(
                        "telas: falha ao montar a barra de estilo no rodapé")
                except Exception:
                    pass
            # Versões (esquerda -> direita): 1ª global do sistema, seguida da
            # parte do módulo atual mesclada (ocultando AAMMDD iguais).
            # Sempre exibido num rótulo único; o detalhe completo fica no tooltip.
            with ui.row().classes("items-center flex-wrap").style("gap: 0.5rem; min-width: 0"):
                versao = _obter_versao()
                versao_mod = _obter_versao_modulo(chave_modulo) if chave_modulo else None
                resultado = _formatar_versao_rodape(versao, versao_mod)
                ui.label(resultado).classes("text-caption font-bold opacity-90").tooltip(
                    f"Sistema: v{versao}\nMódulo: v{versao_mod}" if versao_mod
                    else f"Sistema: v{versao}")


def _logout():
    user = usuario_logado()
    if user:
        autenticacao.registrar_logout(user["nome"], user.get("sessao"))
    app.storage.user.clear()
    ui.navigate.to("/login")


def _dialogo_meu_perfil(nome_usuario: str):
    """Autoatendimento: edita próprios dados pessoais e troca própria senha.

    Permissões e chaves de banco NÃO são editáveis aqui (README linha 60).
    """
    row = autenticacao._gest().obter_usuario(nome_usuario)
    email_atual = row[3] or "" if row else ""
    fone_atual = row[4] or "" if row else ""
    completo_atual = row[9] or "" if row else ""

    # Diálogo de FORMULÁRIO (dados + senha + telefones + fechar): sem teto de
    # altura, ele estourava a janela e quem rolava era a página inteira. O
    # `dialogo_formulario` dá 88vw, teto de 90vh e rolagem só no miolo.
    with ui_comum.dialogo_formulario(chave_modulo="skyrover",
                                     sem_descricao=True) as (dlg, card, miolo, grade):
        ui.label("Meu Perfil").classes("text-h6 font-bold")
        ui.separator()

        ui.label("Dados pessoais").classes("text-subtitle2 text-grey-7")
        # Grade só dos três campos de dados: a ordem do DOM dos campos de SENHA
        # abaixo não pode mudar (o QA preenche por índice), e ela fica fora da
        # grade de propósito.
        with grade:
            completo = ui_comum.campo_texto(
                "Nome completo (ou social)", valor=completo_atual,
                tooltip="Nome pelo qual você será tratado no sistema. "
                        "Pode ser seu nome social (Decreto 8.727/2016)")
            email = ui_comum.campo_texto("E-mail", valor=email_atual)
            try:
                from mod_skyrover import telefone as _tel_perfil
                _campo_fone_perfil = _tel_perfil.criar_campo_telefone(valor=fone_atual)
            except Exception:
                _campo_fone_perfil = None
                fone = ui_comum.campo_texto("Telefone", valor=fone_atual)

        def _fone_perfil_valor():
            try:
                if _campo_fone_perfil is not None:
                    return _campo_fone_perfil["obter"]() or ""
                return fone.value.strip()
            except Exception:
                return ""

        def salvar_dados():
            ok, msg = autenticacao.editar_meu_perfil(
                nome_usuario, email=email.value.strip(), fone=_fone_perfil_valor(),
                nome_completo=completo.value.strip())
            notificar(msg, tipo="positive" if ok else "negative")
            if ok:
                ui.timer(0.1, lambda: ui.navigate.reload(), once=True)

        _botao_tema("Salvar dados", on_click=salvar_dados)

        ui.separator()
        ui.label("Trocar minha senha").classes("text-subtitle2 text-grey-7")
        atual = ui_comum.campo_texto("Senha atual", senha=True)
        nova = ui_comum.campo_texto("Nova senha (mín. 6)", senha=True)
        conf = ui_comum.campo_texto("Confirmar nova senha", senha=True)

        def salvar_senha():
            if nova.value != conf.value:
                notificar("As senhas não conferem", tipo="negative")
                return
            ok, msg = autenticacao.trocar_senha_propria(nome_usuario, atual.value or "", nova.value or "")
            notificar(msg, tipo="positive" if ok else "negative")
            if ok:
                atual.value = nova.value = conf.value = ""

        _botao_tema("Alterar senha", on_click=salvar_senha)

        # Segundo fator TOTP (24/10/2026, fase 2): ativação POR CONTA
        # PRÓPRIA — ninguém ativa para ninguém. O segredo nasce aqui, o
        # usuário cadastra no app do celular (Google Authenticator e
        # afins, tudo offline) e confirma digitando um código. Sem
        # confirmação, nada persiste: gerar e não confirmar é o mesmo
        # que não ter gerado.
        ui.separator()
        ui.label("Segundo fator (código do celular)").classes(
            "text-subtitle2 text-grey-7")
        try:
            from mod_skyrover import totp as _totp_perfil
            _totp_ativo = _totp_perfil.tem_segredo(nome_usuario)
        except Exception:
            _totp_ativo = False
        lbl_totp = ui.label(
            "Ativo — o login vai pedir o código do app."
            if _totp_ativo else
            "Desligado — o login pede só usuário e senha.").classes(
            "text-caption").props('data-testid=meu-perfil-totp-estado')

        if not _totp_ativo:
            segredo_caixa = {"valor": ""}
            lbl_segredo = ui.label("").classes(
                "text-caption text-mono").props(
                'data-testid=meu-perfil-totp-segredo')
            lbl_uri = ui.label("").classes(
                "text-caption text-grey-6").props(
                'data-testid=meu-perfil-totp-uri')
            campo_totp_conf = ui_comum.campo_texto(
                "Código do app (6 dígitos)")
            campo_totp_conf.visible = False
            btn_totp_conf = _botao_tema("Confirmar ativação",
                                        on_click=lambda: _confirmar_totp())
            btn_totp_conf.visible = False

            def _confirmar_totp():
                try:
                    if _totp_perfil.confirmar_ativacao(
                            nome_usuario, campo_totp_conf.value or ""):
                        notificar("Segundo fator ativado.", tipo="positive")
                        ui.timer(0.1, lambda: ui.navigate.reload(),
                                 once=True)
                    else:
                        notificar("Código não confere. Tente de novo.",
                                  tipo="negative")
                except Exception:
                    notificar("Código não confere. Tente de novo.",
                              tipo="negative")

            def _gerar_totp():
                try:
                    seg = _totp_perfil.iniciar_ativacao(nome_usuario)
                    if not seg:
                        notificar("Não foi possível gerar. Tente de novo.",
                                  tipo="negative")
                        return
                    segredo_caixa["valor"] = seg
                    lbl_segredo.text = (
                        "Cadastre no app do celular (Google Authenticator "
                        "ou similar), digitando este código: " + seg)
                    lbl_uri.text = (
                        "Ou cole no app: "
                        + _totp_perfil.uri_ativacao(seg, nome_usuario))
                    campo_totp_conf.visible = True
                    btn_totp_conf.visible = True
                    notificar("Digite no app e confirme com um código.",
                              tipo="info")
                except Exception:
                    notificar("Não foi possível gerar. Tente de novo.",
                              tipo="negative")

            _botao_tema("Ativar segundo fator", on_click=_gerar_totp)
        else:
            campo_totp_off = ui_comum.campo_texto(
                "Código do app para desativar")
            campo_totp_off.props('data-testid=meu-perfil-totp-desativa')

            def _desativar_totp():
                try:
                    from mod_skyrover import totp as _totp_off
                    seg = _totp_off._obter(nome_usuario)
                    if _totp_off.verificar(seg, campo_totp_off.value or ""):
                        _totp_off.desativar(nome_usuario)
                        notificar("Segundo fator desativado.", tipo="positive")
                        ui.timer(0.1, lambda: ui.navigate.reload(),
                                 once=True)
                    else:
                        notificar("Código não confere.", tipo="negative")
                except Exception:
                    notificar("Código não confere.", tipo="negative")

            _botao_tema("Desativar segundo fator", on_click=_desativar_totp)

        ui.separator()
        _bloco_telefones_meu_perfil(nome_usuario)

        # 04/10/2026 — os dados da folha entram no "Meu Perfil" como
        # SOMENTE TEXTO. Fica acima de "Trocar minha senha", que é o que a
        # pessoa procura quando abre esta tela: os campos de identity e
        # telefone ficam em cima (são os que se editam) e a folha embaixo
        # (é o que se lê).
        #
        # A pessoa NÃO edita nada aqui, e isso é o pedido — "sem
        # possibilidade de edição nem pelo usuário nem pelo administrador,
        # afinal esses dados devem vir do arquivo". O bloco vive em
        # `mod_gest_cad_usuario.dados_folha_tela`, o mesmo que o diálogo do
        # admin usa: uma regra em três telas precisa de UM renderizador, senão
        # a primeira correção vale para uma tela e as outras duas ficam
        # atrás.
        ui.separator()
        try:
            from mod_gest_cad_usuario import dados_folha_tela as _folha
            with ui.element("div").classes("w-full").props(
                    "data-testid=meu-perfil-dados-folha"):
                _folha.bloco_dados_folha(nome_usuario,
                                         titulo="Meus dados funcionais")
        except Exception:
            # Falha ao desenhar o bloco da folha NÃO pode impedir o
            # "Meu Perfil" de abrir: quem abriu a tela quer trocar a senha,
            # e perder a senha por causa de um bloco informativo seria trocar
            # um annoyance por um bloqueio.
            #
            # O log vem do PRÓPRIO módulo que desenha o bloco, e não de um
            # logger deste arquivo: quem sabe o que deu errado é quem tentou
            # desenhar, e é lá que a causa fica registrada.
            try:
                from mod_skyrover import observabilidade as _obs_folha
                _obs_folha.get_logger("skyrover").exception(
                    "meu_perfil: falha ao desenhar os dados da folha")
            except Exception:
                pass

        ui.separator()
        with ui.row().classes("w-full justify-end"):
            _botao_tema("Fechar", variante="texto", on_click=dlg.close)
    dlg.open()


def _bloco_telefones_meu_perfil(nome_usuario: str):
    """EN: My phones — add, change and withdraw publication consent.

    PT-BR: Meus telefones — cadastrar, corrigir e RETIRAR a autorização de
    publicação.

    POR QUE ISTO EXISTE
        No primeiro acesso o servidor escolhe o que pode aparecer na lista
        telefônica. Mas escolha nenhuma é definitiva: o número de quem
        atendia a defesa civil em março pode ser de outra pessoa em setembro.
        Pedir consentimento e não dar com o que retirá-lo é a forma mais
        rápida de um cadastro público virar dato ruim — e o dono do número é
        quem tem que decidir, não o administrador.

    O QUE NÃO É NEGOCIÁVEL
        O checkbox do celular particular e o do residencial não aparecem, e o
        do fixo da prefeitura vem travado. A regra é da prefeitura
        (`telefone_e_publicavel`), não deste formulário: repetir a regra
        aqui criaria dois lugares onde ela mora, e o formulário viraria a
        fonte da verdade no primeiro dia em que alguém o copiasse.
    """
    from mod_gest_cad_usuario import bd_manipulador as _bd_usuarios

    ui.label("Meus telefones").classes("text-subtitle2 text-grey-7")
    ui.label("O fixo da prefeitura é a linha institucional e aparece na "
             "lista telefônica. Os demais só saem se você marcar aqui.") \
        .classes("text-caption text-grey-6")

    caixa = ui.column().classes("w-full gap-1")

    def _desenhar():
        caixa.clear()
        try:
            telefones = _bd_usuarios.listar_telefones(nome_usuario)
        except Exception as e:
            lg = _login_erro_log()
            if lg:
                lg.exception(f"meu_perfil: falha ao listar telefones: {e}")
            return
        if not telefones:
            ui.label("Nenhum telefone cadastrado.").classes("text-body2 text-grey-6 italic")
            return
        # t = (id, user_nome, numero, papel, tipo, principal, visivel,
        #      recado, whatsapp, data_cadastro)
        for t in telefones:
            papel_txt = "da prefeitura" if t[3] == "empresa" else "particular"
            tipo_txt = "fixo" if t[4] == "fixo" else "celular"
            with ui.row().classes("w-full items-center no-wrap").style("gap: 0.5rem"):
                with ui.column().classes("grow").style("min-width: 0"):
                    ui.label(f"{t[2]}").classes("text-body2 truncate")
                    detalhe = f"{tipo_txt} {papel_txt}"
                    if t[4] == "fixo" and t[3] == "empresa":
                        detalhe += " · sempre na lista"
                    elif _bd_usuarios.telefone_e_publicavel(t[3], t[4], t[6]):
                        detalhe += " · aparece na lista"
                    else:
                        detalhe += " · só no seu cadastro"
                    ui.label(detalhe).classes("text-caption text-grey-6 truncate")
                # o particular não tem botão de publicar: não há o que
                # autorizar. O fixo da prefeitura também não.
                if t[3] == "empresa" and t[4] == "celular":
                    marcado = ui.checkbox("na lista")
                    marcado.props("dense data-testid=meu-perfil-visivel-{}".format(t[0]))
                    marcado.value = bool(t[6])

                    def _alternar(valor, tid=t[0]):
                        try:
                            _bd_usuarios.editar_telefone(nome_usuario, tid, visivel=bool(valor))
                            notificar("Lista telefônica atualizada.", tipo="positive")
                        except Exception as e:
                            lg = _login_erro_log()
                            if lg:
                                lg.exception(f"meu_perfil: falha ao alterar visivel do {tid}: {e}")
                            notificar("Não foi possível alterar.", tipo="error")

                    marcado.on("update:model-value", lambda ev, tid=t[0]: _alternar(ev.value, tid))
                try:
                    btn_editar_tel = ui_comum.botao_icone(
                        "edit",
                        on_click=lambda tid=t[0], tel=t: _editar(tid, tel),
                        cor="primary",
                        tooltip="Editar este telefone",
                        chave_modulo="skyrover",
                        extra_classes="shrink-0")
                    if btn_editar_tel is not None:
                        btn_editar_tel.props(
                            "data-testid=meu-perfil-editar-{}".format(t[0]))
                except Exception as e:
                    lg = _login_erro_log()
                    if lg:
                        lg.exception(f"meu_perfil: falha ao montar editar {t[0]}: {e}")
                    notificar("Não foi possível montar o botão editar.",
                              tipo="error")
                try:
                    btn_remover_tel = ui_comum.botao_icone(
                        "delete",
                        on_click=lambda tid=t[0]: _remover(tid),
                        cor="negative",
                        tooltip="Remover este telefone",
                        chave_modulo="skyrover",
                        extra_classes="shrink-0")
                    if btn_remover_tel is not None:
                        btn_remover_tel.props(
                            "data-testid=meu-perfil-remover-{}".format(t[0]))
                except Exception as e:
                    lg = _login_erro_log()
                    if lg:
                        lg.exception(f"meu_perfil: falha ao montar remover {t[0]}: {e}")
                    notificar("Não foi possível montar o botão remover.",
                              tipo="error")

    def _editar(tid, tel):
        """EN: Edit own phone (number, owner, type, visibility, main)."""
        with ui.dialog() as dlg_ed:
            with ui.card().classes("w-[380px] gap-2"):
                ui.label("Editar telefone").classes("text-h6")
                from mod_skyrover import telefone as _tel_ed
                _campo_ed = _tel_ed.criar_campo_telefone(
                    rotulo="Número", valor=tel[2] or "",
                    placeholder="(35) 9-9999-9999",
                    testid_ddi="meu-perfil-editar-ddi",
                    testid_numero="meu-perfil-editar-numero")
                if _campo_ed is not None:
                    _obter_ed = _campo_ed["obter"]
                    _ddi_ed = _campo_ed["ddi"]
                    _num_ed = _campo_ed["numero"]
                    _tem_ed = True
                else:
                    _inp_ed = ui.input("Número", value=tel[2] or "") \
                        .props("outlined dense").classes("w-full") \
                        .props("data-testid=meu-perfil-editar-numero")
                    _obter_ed = lambda: (_inp_ed.value or "").strip()
                    _ddi_ed = None
                    _num_ed = _inp_ed
                    _tem_ed = False
                _pap_ed = ui.select({"empresa": "da prefeitura", "pessoal": "particular"},
                                    label="De quem é",
                                    value=tel[3] if tel[3] in ("empresa", "pessoal") else "empresa") \
                    .props("outlined dense").classes("w-full")
                _tip_ed = ui.select({"celular": "celular", "fixo": "fixo"},
                                    label="Tipo",
                                    value=tel[4] if tel[4] in ("celular", "fixo") else "celular") \
                    .props("outlined dense").classes("w-full")
                _vis_ed = ui.checkbox("Pode aparecer na lista telefônica",
                                      value=bool(tel[6]))
                _vis_ed.props("dense data-testid=meu-perfil-editar-visivel")
                _princ_ed = ui.checkbox("Número principal", value=bool(tel[5]))
                _princ_ed.props("dense data-testid=meu-perfil-editar-principal")

                def _salvar_ed():
                    try:
                        numero = _obter_ed() or ""
                        if _tem_ed:
                            ddi = ((_ddi_ed.value or "").strip()
                                   if _ddi_ed is not None else "")
                            if not ddi or ddi.startswith("--"):
                                notificar("Escolha o DDI do telefone.",
                                          tipo="negative")
                                return
                            if ddi == _tel_ed.DDI_PADRAO and len(
                                    _tel_ed.apenas_digitos(
                                        _num_ed.value or "")) not in (10, 11):
                                notificar("Digite o número com o DDD: "
                                          "(35) 99999-9999.", tipo="negative")
                                return
                        if not _tel_ed.apenas_digitos(numero):
                            notificar("Informe o número do telefone.",
                                      tipo="negative")
                            return
                        ok, msg = _bd_usuarios.editar_telefone(
                            nome_usuario, tid, numero=numero,
                            papel=_pap_ed.value, tipo=_tip_ed.value,
                            visivel=bool(_vis_ed.value),
                            principal=bool(_princ_ed.value))
                        notificar(msg, tipo="positive" if ok else "negative")
                        if ok:
                            dlg_ed.close()
                            _desenhar()
                    except Exception as e:
                        lg = _login_erro_log()
                        if lg:
                            lg.exception(f"meu_perfil: falha ao editar telefone {tid}: {e}")
                        notificar("Erro ao alterar o telefone.", tipo="error")

                with ui.row().classes("w-full justify-end"):
                    ui_comum.botao("Cancelar", variante="texto",
                                   chave_modulo="skyrover",
                                   on_click=dlg_ed.close)
                    _botao_tema("Salvar", on_click=_salvar_ed)
        dlg_ed.open()

    def _remover(tid):
        try:
            ok, msg = _bd_usuarios.remover_telefone(nome_usuario, tid)
            notificar(msg, tipo="positive" if ok else "negative")
            if ok:
                _desenhar()
        except Exception as e:
            lg = _login_erro_log()
            if lg:
                lg.exception(f"meu_perfil: falha ao remover telefone {tid}: {e}")
            notificar("Erro ao remover o telefone.", tipo="error")

    _desenhar()

    def _adicionar():
        with ui.dialog() as dlg_add:
            with ui.card().classes("w-[380px] gap-2"):
                ui.label("Novo telefone").classes("text-h6")
                # Composto DDI+número (15/10/2026): o input cru aceitava
                # "(35)999999999" sem DDI e sem padronizar — o mesmo defeito
                # que o bloco do admin já tinha corrigido com
                # `criar_campo_telefone` (DDI obrigatório + máscara BR +
                # canônico `+DDI`+dígitos). Mesma peça aqui.
                from mod_skyrover import telefone as _tel_mp
                _campo_mp = _tel_mp.criar_campo_telefone(
                    rotulo="Número", valor="",
                    placeholder="(35) 9-9999-9999",
                    testid_ddi="meu-perfil-novo-ddi",
                    testid_numero="meu-perfil-novo-numero")
                if _campo_mp is not None:
                    _obter_mp = _campo_mp["obter"]
                    _ddi_mp = _campo_mp["ddi"]
                    _num_mp = _campo_mp["numero"]
                    _tem_mp = True
                else:
                    num = ui.input("Número").props("outlined dense").classes("w-full") \
                        .props("data-testid=meu-perfil-novo-numero")
                    _obter_mp = lambda: (num.value or "").strip()
                    _ddi_mp = None
                    _num_mp = num
                    _tem_mp = False
                pap = ui.select({"empresa": "da prefeitura", "pessoal": "particular"},
                                label="De quem é", value="empresa") \
                    .props("outlined dense").classes("w-full")
                tip = ui.select({"celular": "celular", "fixo": "fixo"},
                                label="Tipo", value="celular") \
                    .props("outlined dense").classes("w-full")
                vis = ui.checkbox("Pode aparecer na lista telefônica")
                vis.props("dense data-testid=meu-perfil-novo-visivel")

                def _salvar_add():
                    try:
                        numero = _obter_mp() or ""
                        if _tem_mp:
                            ddi = ((_ddi_mp.value or "").strip()
                                   if _ddi_mp is not None else "")
                            if not ddi or ddi.startswith("--"):
                                notificar("Escolha o DDI do telefone.",
                                          tipo="negative")
                                return
                            # DDD OBRIGATÓRIO no nacional: valida o DIGITADO
                            # (só DDD+número, sem o DDI), e não o canônico —
                            # no canônico o `55` do país se confunde com DDD.
                            # "(35)999999999" tem 11 e passa; "999999999" tem
                            # 9 e volta para digitar o DDD.
                            if ddi == _tel_mp.DDI_PADRAO and len(
                                    _tel_mp.apenas_digitos(
                                        _num_mp.value or "")) not in (10, 11):
                                notificar("Digite o número com o DDD: "
                                          "(35) 99999-9999.", tipo="negative")
                                return
                        if not _tel_mp.apenas_digitos(numero):
                            notificar("Informe o número do telefone.",
                                      tipo="negative")
                            return
                        ok, msg = _bd_usuarios.adicionar_telefone(
                            nome_usuario, nome_usuario, numero,
                            papel=pap.value,
                            tipo=tip.value, visivel=bool(vis.value))
                        notificar(msg, tipo="positive" if ok else "negative")
                        if ok:
                            dlg_add.close()
                            _desenhar()
                    except Exception as e:
                        lg = _login_erro_log()
                        if lg:
                            lg.exception(f"meu_perfil: falha ao adicionar telefone: {e}")
                        notificar("Erro ao cadastrar o telefone.", tipo="error")

                with ui.row().classes("w-full justify-end"):
                    ui_comum.botao("Cancelar", variante="texto",
                                   chave_modulo="skyrover",
                                   on_click=dlg_add.close)
                    _botao_tema("Salvar", on_click=_salvar_add)
        dlg_add.open()

    _botao_tema("Adicionar telefone", variante="secundario", on_click=_adicionar)


# ================ LAYOUT DO DIÁLOGO DE TROCA DE CREDENCIAIS =================
#
# O diálogo do primeiro acesso do `master` foi o PRIMEIRO a receber o layout de
# formulário largo, e é o que tem mais conteúdo: 7 campos, dois blocos
# informativos e um botão. Com `w-96` (384px) e `max_altura=False` ele virava uma
# coluna estreita que estourava a altura da janela — e quem rolava era a PÁGINA
# INTEIRA, uma barra de rolagem no meio do formulário, não o conteúdo do diálogo.
#
# A correção é de LAYOUT, não de estrutura: os campos continuam sendo os mesmos
# `ui_comum.campo_texto`, na MESMA ordem do DOM (o QA preenche os três campos
# de senha por índice: atual → nova → confirmar), e o que muda é o CSS.
#
# A largura e as grades NÃO são definidas aqui: moram em `ui_comum` e são
# compartilhadas por todos os diálogos de formulário da skyrover, para que este
# diálogo e o de "Novo usuário" não cresçam em direções diferentes. O que este
# módulo acrescenta são os DOIS blocos informativos lado a lado, o que a base
# comum não faz — os campos vão na grade de `miolo`, os avisos em outra.
LARGURA_DIALOGO_TROCA = ui_comum.LARGURA_DIALOGO_FORMULARIO
CSS_GRADE_CAMPOS_TROCA = ui_comum.CSS_GRADE_CAMPOS
CSS_GRADE_AVISOS_TROCA = ui_comum.CSS_GRADE_AVISOS

# Senha que o formulário de troca obrigatória JÁ PROPOSTE (30/09/2026).
#
# Só para as contas de TESTE — `qacomum` e `qamaster`, que entregam com a
# senha `123456` e são contas de fábrica publicadas na §8.2 do AGENTS.md. Não
# vale para conta real: o campo nasce vazio e a pessoa digita a senha dela.
#
# Por que preencher: obrigar a DIGITAR uma senha que já se sabe qual é é
# trabalho sem resultado — o objetivo da troca obrigatória é a pessoa entrar,
# não decorar `123456`. Com o campo preenchido, a troca é um clique. É a mesma
# lógica do diálogo de credenciais do `master`, que nasce com o nome e a
# senha do responsável.
#
# PREENCHIDA COM SENHA FORTE, E NÃO COM `123456` (30/09/2026). A proposta
# antiga virou armadilha no mesmo dia em que o piso de força foi para 0,5:
# `123456` mede 0,15, fica ABAIXO do piso, e aí o formulário nascia com uma
# senha que o próprio sistema recusa — a tela oferece um valor impossível e o
# botão "Alterar senha" nunca aparecia. Ou seja: trocar era um clique, mas o
# clique não levava a lugar nenhum. A proposta tem de passar por
# `politica_senha.acima_do_piso`, senão é enfeite.
# SENHA SUGERIDA NA TROCA: agora SORTEADA, não fixa (05/10/2026).
#
# A proposta era a constante `Prefeitura@2026`, e ela era uma armadilha dentro
# do próprio sistema: `bd_conexao` lista `("prefeitura", "Nome da instituição")`
# entre os padrões do órgão, e o validador BLOQUEIA senha que case com ele. Ou
# seja, a senha que o sistema oferecia era recusada pela regra do sistema — a
# pessoa clicava no botão e recebia "A senha contém trechos de dedução
# atrelada com palavras do próprio órgão". Nenhuma troca funcionava por esse
# caminho.
#
# A segunda armadilha era mais sutil: `123456` como proposta morre no piso de
# força (mede 15%, abaixo de 50%), então o formulário nascia com um valor
# impossível e o botão "Alterar senha" nunca aparecia.
#
# Por isso a proposta é gerada e VALIDADA antes de ser exibida: sorteada em
# `senha_aleatoria()` e conferida com `analisar_offline`. Se ainda assim não
# passasse — o que não deve acontecer, porque o sorteio tem 4 tipos e 16
# caracteres — o gerador devolve string vazia e o campo fica VAZIO, que é o
# único valor honesto: melhor pedir a senha do que oferecer uma que o próprio
# sistema recusa.
#
# `senha_aleatoria()` fica em `politica_senha`, ao lado do medidor, porque é
# conhecimento de senha e o `telas.py` não deve saber de alfabeto.
def _senha_proposta() -> str:
    """Senha sugerida, já validada. String vazia se não houver nada de válido."""
    try:
        from mod_skyrover import politica_senha as _ps
        from mod_skyrover.validador_senha import analisar_offline
        for _tentativa in range(6):
            s = _ps.senha_aleatoria()
            if not s:
                continue
            if analisar_offline(s, "").get("ok"):
                return s
        return ""
    except Exception:
        _login_erro_log().exception(
            "troca_senha: não foi possível gerar a senha sugerida")
        return ""


def _dialogo_troca_credenciais(nome_usuario: str, ao_concluir=None):
    """Opens the mandatory first-access dialog with a safe minimal fallback.

    Abre o diálogo de troca obrigatória completo (pré-preenchido); se a
    montagem falhar por qualquer motivo, abre o diálogo mínimo (campos
    simples, sem pré-preenchimento) para nunca derrubar a página. Nenhum
    caminho propaga exceção ao chamador.

    `ao_concluir` é repassado aos dois diálogos e roda só depois de uma
    troca bem-sucedida — é o que encadeia o cadastro dos telefones."""
    try:
        _dialogo_troca_credenciais_completo(nome_usuario, ao_concluir)
    except Exception as _e_full:
        try:
            _login_erro_log().exception(
                f"troca_credenciais completo falhou para '{nome_usuario}': {_e_full}")
        except Exception:
            pass
        try:
            _dialogo_troca_credenciais_minimo(nome_usuario, ao_concluir)
        except Exception as _e_min:
            try:
                _login_erro_log().exception(
                    f"troca_credenciais mínimo falhou para '{nome_usuario}': {_e_min}")
            except Exception:
                pass
            try:
                notificar("Erro ao abrir a troca de credenciais.", tipo="error")
            except Exception:
                pass


def _dialogo_troca_credenciais_minimo(nome_usuario: str, ao_concluir=None):
    """Minimal first-access dialog (plain fields, no prefill, no DDI select).

    Diálogo mínimo de primeiro acesso: campos simples vazios, sem
    pré-preenchimento e sem combobox de DDI. Fallback para garantir que o
    master sempre consiga trocar as credenciais mesmo se o diálogo completo
    falhar.

    Mesmo layout do diálogo completo (88vw, teto de 1600px, `max-h-[90vh]` com
    rolagem interna e grade auto-fit nos campos), porque um fallback que
    estoura a tela em máquina de instalação não é fallback de ninguém.

    `ao_concluir` recebe o NOVO nome de usuário, porque aqui o login muda."""
    with ui_comum.dialogo_card(largura=LARGURA_DIALOGO_TROCA,
                               max_altura=True) as (dlg, card):
        # O card vira coluna flex (`max-h-[90vh]` vem do `max_altura=True`):
        # título fica parado em cima, botão parado embaixo, e o miolo é que
        # rola. O `min-h-0` do miolo é obrigatório — sem ele o filho flex não
        # encolhe abaixo da altura do conteúdo, o `overflow-y` não pega e o
        # `max-h` do card é simplesmente ignorado.
        card.classes("flex flex-col")
        ui.label("Credenciais obrigatórias").classes("text-h6")
        ui.label("Por segurança, defina um novo nome de usuário e uma nova "
                 "senha antes de continuar.").classes("text-body2 text-grey-7")
        _miolo = ui.column().classes("w-full flex-1 min-h-0 overflow-y-auto")
        _miolo.props('role="region" tabindex="0" '
                     'aria-label="Campos da troca de credenciais"')
        with _miolo:
            # Grade responsiva: os 7 campos saem da coluna estreita e ocupam
            # várias colunas na tela larga, sem media query e sem mexer na
            # ORDEM do DOM — atual → nova → confirmar, que é o contrato do QA.
            _grade = ui.element("div").classes("w-full").style(
                CSS_GRADE_CAMPOS_TROCA)
            _grade.props('role="group" aria-label="Dados de acesso"')
            with _grade:
                novo_nome = ui_comum.campo_texto("Novo nome de usuário",
                                                 props="")
                nome_completo = ui_comum.campo_texto("Nome completo (ou social)",
                                                     props="")
                email = ui_comum.campo_texto("E-mail", props="")
                fone = ui_comum.campo_texto("Telefone", props="")
                atual = ui_comum.campo_texto("Senha atual", senha=True, props="")
                nova = ui_comum.campo_texto("Nova senha (mín. 6)", senha=True,
                                            props="")
                conf = ui_comum.campo_texto("Confirmar nova senha", senha=True,
                                            props="")

        def _v(campo):
            try:
                return getattr(campo, "value", "") or ""
            except Exception:
                return ""

        def confirmar():
            try:
                if not _v(novo_nome).strip() or _v(novo_nome).strip().lower() == "master":
                    notificar("Informe um novo nome de usuário diferente de 'master'.",
                              tipo="negative")
                    return
                if _v(nova) != _v(conf):
                    notificar("As senhas não conferem", tipo="negative")
                    return
                try:
                    ok, msg, novo = autenticacao.trocar_credenciais_master(
                        nome_usuario, _v(novo_nome), _v(atual), _v(nova),
                        nome_completo=_v(nome_completo),
                        email=_v(email), fone=_v(fone))
                except Exception as _e_cred:
                    _login_erro_log().exception(
                        f"falha ao trocar credenciais de '{nome_usuario}': {_e_cred}")
                    notificar("Erro ao trocar credenciais", tipo="negative")
                    return
                notificar(msg, tipo="positive" if ok else "negative")
                if ok:
                    try:
                        app.storage.user["usuario"]["nome"] = novo
                    except Exception:
                        pass
                    try:
                        dlg.close()
                    except Exception:
                        pass
                    ui.timer(0.2, lambda: ui.navigate.to("/"))
                    if ao_concluir:
                        try:
                            ao_concluir(novo)
                        except Exception as e:
                            _login_erro_log().exception(
                                f"troca_credenciais: callback de {novo} falhou: {e}")
            except Exception as _e_conf:
                try:
                    _login_erro_log().exception(
                        f"confirmar mínimo falhou para '{nome_usuario}': {_e_conf}")
                except Exception:
                    pass
                try:
                    notificar("Erro ao salvar credenciais.", tipo="error")
                except Exception:
                    pass

        # OS DOIS BOTÕES COM LARGURA IGUAL, lado a lado (04/10/2026).
        #
        # `grid-template-columns: 1fr 1fr` em vez de `grow` nos dois: com
        # `grow` as larguras saíam 243px e 326px, porque o `flex-grow` reparte
        # o que sobra a partir da largura do conteúdo — e o rótulo do segundo
        # botão é 83px mais comprido. Grade com duas colunas `1fr` dá metades
        # exatas, qualquer que seja o texto.
        _linha_principal = ui.element("div").classes("w-full min-w-0").style(
            "display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; "
            "margin-top: .5rem")
        with _linha_principal:
            _botao_tema("Salvar credenciais", on_click=confirmar,
                        extra_classes="w-full")
            # Mesmo rótulo curto da tela de troca de senha (18/10/2026):
            # "Sair", e a explicação do que ele faz fica no tooltip.
            _botao_tema("Sair", variante="contorno", on_click=_logout,
                        extra_classes="w-full",
                        tooltip="Sair e entrar com outro usuário")

        # ------- Apagar as contas de teste: abaixo, com o texto no tooltip ---
        #
        # Fica ABAIXO dos dois botões principais, e não dentro do formulário:
        # apagar conta de fábrica é decisão do administrador, não uma das seis
        # coisas que ele precisa preencher para entrar no sistema. O texto que
        # explicava isso — quatro linhas dentro do cartão — é agora o tooltip
        # dos botões, e aparece quando o mouse chega neles.
        _contas_teste = _contas_de_teste()
        if _contas_teste:
            _linha_apagar = ui.element("div").classes("w-full min-w-0").style(
                "display: grid; gap: .5rem; margin-top: .5rem; "
                # Uma coluna por botão onde o nome cabe ao lado; no celular
                # empilham, porque dois "Apagar ..." em 366px dariam 175px por
                # botão e o rótulo quebraria no meio.
                "grid-template-columns: repeat(auto-fit, "
                "minmax(min(180px, 100%), 1fr))")
            with _linha_apagar:
                for _c in _contas_teste:
                    _btn_excluir = ui_comum.botao(
                        f"Apagar {_c['login']}", icone="delete",
                        on_click=lambda l=_c["login"]: _apagar_conta_teste(l),
                        variante="perigo", compacto=True,
                        chave_modulo="skyrover")
                    _btn_excluir.props(
                        f'data-testid=apagar-conta-teste-{_c["login"]} '
                        f'aria-label="Apagar a conta de teste {_c["login"]}"')
                    _btn_excluir.classes("no-print w-full")
                    try:
                        ui.tooltip(TEXTO_CONTAS_DE_TESTE)
                    except Exception:
                        pass


# Contas de teste que a semente de QA cria (AGENTS.md §8.2). São as mesmas da
# documentação — o objetivo de as listar aqui é o oposto do de documentá-las:
# aqui é onde se decide se elas ficam.
CONTAS_DE_TESTE = ("qacomum", "qamaster")


def _contas_de_teste():
    """As contas de teste que ainda existem, para a tela do primeiro acesso.

    Devolve lista de dicionários `{"login", "nome", "perfil"}`. Lista vazia
    quando não há nenhuma, ou quando o cadastro não pode ser lido — e lista
    vazia é o estado NORMAL depois que o administrador já apagou, e também o
    estado de quem não tem esse módulo. Nos dois casos a tela não mostra o
    bloco, e não é erro.
    """
    saida = []
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd
        for login in CONTAS_DE_TESTE:
            try:
                linha = _bd.listar_usuarios()
            except Exception:
                return []
            achado = next((u for u in (linha or []) if u[1] == login), None)
            if not achado:
                continue
            saida.append({
                "login": login,
                "nome": (achado[9] or "").strip() or login,
                "perfil": achado[2] or "",
            })
    except Exception as e:
        try:
            _login_erro_log().exception(
                f"contas de teste: não foi possível listar: {e}")
        except Exception:
            pass
        return []
    return saida


def _apagar_conta_teste(login: str):
    """Apaga uma conta de teste a partir da tela de primeiro acesso.

    A exclusão é a DEFINITIVA (a de LGPD, com limpeza em cascata nos outros
    módulos), não uma desativação: conta de teste que fica lá, desativada, é
    conta que alguém reativa por engano daqui a seis meses. O usuário pede
    "apagar do cadastro", e apagar de verdade é o que ele espera.

    O que este botão NÃO faz é apagar conta que não é de teste. A lista vem
    de `CONTAS_DE_TESTE`, e o nome vem do botão — não de digitação livre — então
    não há como apagar `master` por este caminho. E mesmo que houvesse,
    `excluir_usuario_definitivo` recusa `master` e recusa remover o último
    administrador geral ativo: a proteção não depende desta tela.
    """
    if login not in CONTAS_DE_TESTE:
        notificar("Esta conta não é de teste.", tipo="warning")
        return
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd
        ok, msg = _bd.excluir_usuario_definitivo("master", login)
        notificar(msg or ("Conta apagada." if ok else "Não foi possível apagar."),
                  tipo="positive" if ok else "negative")
        if ok:
            # some com a linha da lista sem recarregar a página inteira: quem
            # está no meio da troca de credenciais não pode perder o que já
            # preencheu por causa de um botão ao lado.
            _REMOVIDOS_DE_TESTE.add(login)
            ui.navigate.reload()
    except Exception as e:
        try:
            _login_erro_log().exception(f"apagar conta de teste {login}: {e}")
        except Exception:
            pass
        notificar("Erro ao apagar a conta de teste.", tipo="negative")


# Contas já apagadas nesta sessão. Vive no servidor (não no navegador) porque a
# tela é re-renderizada a cada dialogo e a lista de contas é lida de novo; sem
# isto, o bloco voltaria a aparecer depois do reload, com a conta que não existe
# mais — pior do que não mostrar nada.
_REMOVIDOS_DE_TESTE = set()


def _dialogo_troca_credenciais_completo(nome_usuario: str, ao_concluir=None):
    """Full first-access dialog (prefilled + DDI phone field).

    Diálogo completo do primeiro acesso do `master` nativo: vem
    pré-preenchido com os dados do responsável pelo sistema para o futuro
    administrador conferir/ajustar antes de salvar. `persistent` (não fecha
    com ESC/clique fora) e fechamento somente após a troca bem-sucedida.

    Layout: card largo (88vw, teto de 1600px) e alto no máximo 90vh, com o
    conteúdo rolando por dentro — em vez dos 384px de antes, que faziam o
    formulário estourar a janela. Os dois blocos informativos ocupam o mesmo
    grid auto-fit (lado a lado em tela larga, empilhados no celular) e os
    campos vão para um segundo grid, SEM mudar a ordem do DOM: o QA preenche
    os três campos de senha por índice (atual → nova → confirmar).

    `ao_concluir` recebe o NOVO nome de usuário, porque aqui o login muda."""
    with ui_comum.dialogo_card(largura=LARGURA_DIALOGO_TROCA,
                               max_altura=True) as (dlg, card):
        # Mesmo esqueleto do diálogo mínimo: card em coluna flex com
        # `max-h-[90vh]`, título e botão parados nas pontas e miolo rolável
        # (`flex-1 min-h-0 overflow-y-auto`) — o `min-h-0` é o que permite ao
        # filho encolher abaixo da altura do conteúdo e o `overflow-y` pegar.
        card.classes("flex flex-col")
        ui.label("Credenciais obrigatórias").classes("text-h6")
        ui.label(f"Bem-vindo(a), {autenticacao.nome_de_tratamento(nome_usuario)}. "
                 "Por segurança, defina um novo nome de usuário e uma nova "
                 "senha antes de continuar.").classes("text-body2 text-grey-7")
        _miolo = ui.column().classes("w-full flex-1 min-h-0 overflow-y-auto")
        _miolo.props('role="region" tabindex="0" '
                     'aria-label="Conteúdo da troca de credenciais"')
        with _miolo:
            _grade_avisos = ui.element("div").classes("w-full").style(
                CSS_GRADE_AVISOS_TROCA)
            _grade_avisos.props(
                'role="group" aria-label="Informações do primeiro acesso"')
            with _grade_avisos:
                try:
                    with ui.column().classes("w-full gap-1 p-2 rounded bg-blue-1"):
                        ui.label("Administrador do sistema").classes(
                            "text-caption font-bold text-blue-10")
                        ui.label("Conta de fábrica: master").classes(
                            "text-caption text-blue-9")
                        ui.label("Defina um login e uma senha próprios.").classes(
                            "text-caption text-blue-9")
                except Exception:
                    pass
                # ------- Contas de teste: apagar ou manter, AQUI (28/09/2026) ---
                #
                # A prefeitura recebe o sistema com `qacomum` e `qamaster` já
                # cadastrados (a semente de QA, AGENTS.md §8.2). Quem entra pela
                # primeira vez com `master` é o administrador installing — é a
                # única pessoa no sistema cuja conta tem o perfil
                # `administrador_geral` de fábrica e senha conhecida. Se ele sai
                # da tela sem decidir o destino dessas duas contas, fica uma
                # prefeitura com dois administradores de senha `123456`
                # published.
                #
                # Por que AQUI e não em uma tela depois: este é o momento em que
                # a pessoa está trocando a senha do administrador porque entendeu
                # que conta de fábrica é perigosa. Um passo adiante, essa Timeout
                # já passou.
                _contas_teste = _contas_de_teste()
                if _contas_teste:
                    with ui.column().classes("w-full gap-1 p-2 rounded bg-orange-1"):
                        ui.label("Contas de teste que vieram com o sistema").classes(
                            "text-caption font-bold text-orange-10")
                        ui.label(
                            "O sistema é entregue com duas contas de teste, "
                            "para documentação e conferência. Elas entram com "
                            "a senha conhecida, então convém decidir agora o "
                            "que fazer com elas — apagar é o padrão de quem "
                            "vai usar o sistema de verdade, e manter é o de "
                            "quem ainda vai documentar.").classes(
                            "text-caption text-orange-9")
                        # a linha da conta continua com a mesma estrutura: o
                        # nome/login ocupa o que sobra (`flex: 1 1 0` +
                        # `min-width: 0`) e o botão "Apagar" nunca é espremido
                        # nem quebra em tela estreita
                        for _c in _contas_teste:
                            with ui.row().classes("w-full items-center").style(
                                    "gap: 0.5rem; min-width: 0"):
                                with ui.column().classes("gap-0").style(
                                        "min-width: 0; flex: 1 1 0"):
                                    ui.label(f"{_c['nome']}  (@{_c['login']})").classes(
                                        "text-caption text-grey-8 truncate")
                                    ui.label(f"perfil: {_c['perfil']}").classes(
                                        "text-caption text-grey-6")
                                _btn_excluir = ui_comum.botao(
                                    "Apagar", icone="delete",
                                    on_click=lambda l=_c["login"]: _apagar_conta_teste(l),
                                    variante="perigo", compacto=True,
                                    chave_modulo="skyrover")
                                _btn_excluir.props(
                                    f'data-testid=apagar-conta-teste-{_c["login"]} '
                                    f'aria-label="Apagar a conta de teste {_c["login"]}"')
                                _btn_excluir.classes("no-print")

            _grade_campos = ui.element("div").classes("w-full").style(
                CSS_GRADE_CAMPOS_TROCA)
            _grade_campos.props('role="group" aria-label="Dados de acesso"')
            with _grade_campos:
                novo_nome = ui_comum.campo_texto("Novo nome de usuário",
                                                 valor="", props="")
                nome_completo = ui_comum.campo_texto(
                    "Nome completo (ou social)", valor="", props="",
                    tooltip="Nome pelo qual você será tratado no sistema. "
                            "Pode ser seu nome social (Decreto 8.727/2016)")
                email = ui_comum.campo_texto("E-mail",
                                             valor="admin@example.com",
                                             props="")
                _campo_fone = None
                fone = None
                try:
                    from mod_skyrover import telefone as _tel
                    _campo_fone = _tel.criar_campo_telefone(valor="")
                except Exception:
                    _campo_fone = None
                if _campo_fone is None:
                    try:
                        fone = ui_comum.campo_texto("Telefone", valor="",
                                                    props="")
                    except Exception:
                        fone = None
                # a ORDEM do DOM dos três campos de senha é contrato do QA
                # (`concluir_troca` preenche por índice): atual → nova →
                # confirmar. O grid CSS preenche por linha e não reordena.
                atual = ui_comum.campo_texto("Senha atual", senha=True,
                                             valor="master", props="")
                nova = ui_comum.campo_texto("Nova senha (mín. 6)", senha=True,
                                            valor="", props="")
                conf = ui_comum.campo_texto("Confirmar nova senha", senha=True,
                                            valor="", props="")

        def _v(campo):
            try:
                return getattr(campo, "value", "") or ""
            except Exception:
                return ""

        def _fone_valor():
            try:
                if _campo_fone is not None:
                    return _campo_fone["obter"]() or ""
                return _v(fone)
            except Exception:
                return ""

        def confirmar():
            try:
                if not _v(novo_nome).strip() or _v(novo_nome).strip().lower() == "master":
                    notificar("Informe um novo nome de usuário diferente de 'master'.",
                              tipo="negative")
                    return
                if _v(nova) != _v(conf):
                    notificar("As senhas não conferem", tipo="negative")
                    return
                try:
                    ok, msg, novo = autenticacao.trocar_credenciais_master(
                        nome_usuario, _v(novo_nome), _v(atual), _v(nova),
                        nome_completo=_v(nome_completo),
                        email=_v(email), fone=_fone_valor())
                except Exception as _e_cred:
                    _login_erro_log().exception(
                        f"falha ao trocar credenciais de '{nome_usuario}': {_e_cred}")
                    notificar("Erro ao trocar credenciais", tipo="negative")
                    return
                notificar(msg, tipo="positive" if ok else "negative")
                if ok:
                    try:
                        _login_erro_log().info(
                            f"credenciais ok: '{nome_usuario}' -> '{novo}' — "
                            "atualizando sessão")
                    except Exception:
                        pass
                    try:
                        app.storage.user["usuario"]["nome"] = novo
                    except Exception as _e_sess:
                        try:
                            _login_erro_log().exception(
                                f"falha ao atualizar sessão para '{novo}': {_e_sess}")
                        except Exception:
                            pass
                    try:
                        _login_erro_log().info(
                            f"credenciais ok: '{novo}' — agendando navegação para /")
                    except Exception:
                        pass
                    ui.timer(0.2, lambda: ui.navigate.to("/"))
                    if ao_concluir:
                        try:
                            ao_concluir(novo)
                        except Exception as e:
                            _login_erro_log().exception(
                                f"troca_credenciais: callback de {novo} falhou: {e}")
            except Exception as _e_conf:
                try:
                    _login_erro_log().exception(
                        f"confirmar completo falhou para '{nome_usuario}': {_e_conf}")
                except Exception:
                    pass
                try:
                    notificar("Erro ao salvar credenciais.", tipo="error")
                except Exception:
                    pass

        # A CAUDA (botoes, dica e o bloco dos "Apagar") vem abaixo.


# Texto que explica as contas de teste que vieram com o sistema.
#
# Vira o TOOLTIP dos botões "Apagar <login>" (04/10/2026). Antes eram duas
# linhas dentro do cartão — o título em negrito e este parágrafo — que
# ocupavam altura na tela cujo formulário tem sete campos. A informação não
# pode sumir: quem vai apagar precisa ler por que está apagando. O que muda
# é que ela aparece no hover, e não empurrando o formulário para baixo.
TEXTO_CONTAS_DE_TESTE = (
    "Contas de teste que vieram com o sistema. O sistema é entregue com duas "
    "contas de teste, para documentação e conferência. Elas entram com a senha "
    "conhecida, então convém decidir agora o que fazer com elas — apagar é o "
    "padrão de quem vai usar o sistema de verdade, e manter é o de quem ainda "
    "vai documentar.")

# Tooltip da dica verde "Acesso restrito", com 3 segundos de demora (04/10/2026).
#
# Antes era o bloco azul que ocupava ~100px da tela, sempre visível, com
# quatro linhas de identificação do responsável. Virou tooltip: o texto está a
# um `hover` de distância e a tela voltou a ser quase só formulário.
#
# A DEMORA DE 3 SEGUNDOS é deliberada: os dados do responsável são
# informative, e tooltip que aparece a cada passar do mouse transforma a tela
# numa lanterna que pisca. Quem quer ler posiciona o mouse e espera; quem
# estava indo clicar no botão de baixo não cruza a dica nem percebe que ela
# existe. Os quatro campos que o formulário sugere ao abrir já são os mesmos
# dados, então nada se perde.
TEXTO_DADOS_RESPONSAVEL = (
    "Administrador do sistema\n"
    "Conta de fábrica: master\n"
    "Defina um login e uma senha próprios.")

# Quanto o mouse precisa ficar sobre a dica para o tooltip aparecer, em ms.
DEMORA_TOOLTIP_DADOS_MS = 3000


def _formulario_troca_credenciais(nome_usuario: str, ao_concluir=None):
    """Primeiro acesso do `master` nativo, no PADRÃO DA TELA DE LOGIN.

    EN: Native `master` first-access form, rendered on the login screen.

    irmão de `_formulario_troca_senha` e montado pelo mesmo
    `preview_estilos.tela_login`: os CAMPOS são os do diálogo de credenciais
    (mesmos sete, mesma ordem, mesmo pré-preenchimento, mesmos dois blocos
    informativos), mas o INVÓLUCRO é o da tela de login — não um cartão por
    cima de outra coisa.

    POR QUE DEIXOU DE SER DIÁLOGO (04/10/2026)
    ----------------------------------------
    Era `_dialogo_troca_credenciais_completo`, e o navegador medido mostrou o
    defeito: o cartão nascia com `scrollWidth` de 2.518px contra 1.267px de
    cliente no desktop (e 994px contra 342px no celular), porque o rodapé —
    "Salvar credenciais" e "Sair" — nascia FORA da largura do cartão. No
    celular o miolo inteiro saía para fora e a tela ficava com o título e o
    resto em branco. Traduzido para quem opera: o botão de salvar não estava
    visível, e o que aparecia era a coluna de campos empurrada para a direita,
    com barra de rolagem horizontal.

    Duas causas, as duas corrigidas aqui e em `ui_comum`:
      - `CSS_GRADE_AVISOS` tinha `minmax(320px, 1fr)` sem teto — a grade dos
        blocos informativos era mais larga que o cartão;
      - o esqueleto do diálogo (`dialogo_card` + `flex flex-col` + rodapé fora
        do `miolo`) é o que produz o rodapé ao lado do miolo. O
        `formulario_na_tela` é o esqueleto que já foi provado pela troca de
        senha dos outros usuários, e é ele que este usa.

    A ORDEM do DOM dos três campos de senha continua sendo contrato do QA:
    atual → nova → confirmar (`tests/qa_login_helper.py::concluir_troca`
    preenche `input[type=password]` por índice). Os campos de dados pessoais
    vêm ANTES dos de senha, como no diálogo — nenhum deles é `type=password`,
    então a contagem por índice não muda.

    `ao_concluir` recebe o NOVO nome de usuário, porque aqui o login muda.
    """
    # `25rem` medido NESTA tela (04/10/2026): o chassi — respiro da tela,
    # padding da caixa, dica verde, os dois pares de botões e os gaps — deu
    # 342 a 392px em cinco tamanhos. A troca dos outros usuários passa
    # `33rem`, porque mantém cabeçalho e rodapé.
    with ui_comum.formulario_na_tela(
            max_altura="max(200px, calc(100vh - 25rem))",
            rotulo="Formulário da troca de credenciais") as (miolo, grade):
        with miolo:
            # ------- OS DOIS BLOCOS INFORMATIVOS VIRARAM TOOLTIP -----------
            #
            # Antes, dentro do `miolo` e acima dos campos: o azul com os
            # dados do responsável e o laranja com as contas de teste. Os dois
            # saíram de lá em 04/10/2026, por decisão do responsável, e o
            # motivo não foi estética — são ~230px que o formulário de sete
            # campos precisa para caber na janela sem rolar a página.
            #
            # ONDE CADA UM FOI PARAR:
            #  - as contas de teste viraram o tooltip dos DOIS BOTÕES
            #    "Apagar", que desceram para baixo do "Salvar"/"Sair". A
            #    decisão de apagar ou manter é do administrador e o primeiro
            #    acesso é o único momento em que ele está trocando a senha do
            #    admin por ter entendido o risco — o texto tem de estar ali,
            #    mas não precisa ocupar quatro linhas para dizer isso;
            #  - os dados do analista viraram o tooltip da dica verde
            #    "Acesso restrito", com 3 segundos de demora (ver
            #    `dica_tooltip` no `tela_login`).
            #
            # O `miolo` agora contém SÓ a grade dos sete campos — que é o que
            # a pessoa precisa de fato rolar.

            # ------- Os MESMOS sete campos, DUAS COLUNAS (04/10/2026) ------
            #
            # A grade nasce com `CSS_GRADE_CAMPOS` e SEM a classe
            # `grade-campos`, ou seja, em coluna única (foi medido: é o que
            # `formulario_na_tela` entrega). Aqui ela vira DUAS colunas pelo
            # mesmo idioma do `auto-fit` com `min()`: duas enquanto houver
            # 240px para cada, uma coluna abaixo disso.
            #
            # O telefone é UM item só, mesmo parecendo dois: `criar_campo_telefone`
            # devolve o DDI e o número numa linha interna. Na grade de duas
            # colunas ele ocupa a célula da esquerda sozinho, e é por isso que
            # a última linha fecha com "Nova senha | Confirmar".
            #
            # `min(240px, 100%)` é o que impede o transbordo: sem o `min`, a
            # coluna teria 240px de piso mesmo numa caixa de 180px, e o
            # conteúdo sairia do cartão — foi o defeito do `CSS_GRADE_AVISOS`.
            # ------- DUAS COLUNAS: SENHAS À ESQUERDA, IDENTIDADE À
            # DIREITA (04/10/2026, pedido do responsável)
            #
            # Não é a grade que preenche por linha: são DOIS PAIS com seus
            # campos empilhados. A diferença é a ordem de leitura — as três
            # senhas juntas à esquerda dizem uma coisa só ("isto é uma troca
            # de credenciais") e os dados de quem é à direita dizem a outra.
            #
            # `auto-fit` com `min(260px, 100%)` continua decidindo uma ou
            # duas colunas: duas enquanto couberem 260px de cada, uma abaixo
            # disso. O `min-width: 0` nas duas colunas é o que impede a mais
            # larga de impor a sua largura mínima e empurrar a outra para
            # fora — o mesmo mecanismo do `min()` que segura o `CSS_GRADE_AVISOS`.
            #
            # O `grade` que `formulario_na_tela` entrega É o contêiner das duas
            # colunas (04/10/2026). Ele nascia vazio, ocupando uma célula e um
            # `gap` de 16px à toa, porque o desenho anterior era de campos
            # soltos dentro dele; agora quem mora nele são as DUAS colunas.
            grade.style("grid-template-columns: "
                        "repeat(auto-fit, minmax(min(260px, 100%), 1fr))")
            with grade:
                # ---------------- COLUNA ESQUERDA: as três senhas ---------
                with ui.column().classes("w-full min-w-0").style(
                        "gap: 1rem; min-width: 0"):
                    # A SENHA ATUAL VEM PRIMEIRO (04/10/2026). Não é
                    # aleatório: a pessoa entra, cai nesta tela, e a primeira
                    # coisa que precisa é provar que sabe a senha que acabou
                    # de digitar.
                    #
                    # O CONTRATO DO QA SEGUE VALENDO. `qa_login_helper
                    # .concluir_troca` preenche `input[type=password]` por
                    # índice, na ordem atual → nova → confirmar, e é a ORDEM DO
                    # DOM que conta: as três senhas são exatamente os três
                    # `type=password` da página, e nesta ordem. Os campos de
                    # identidade vêm depois e nenhum deles é `password`, então
                    # não entram na contagem.
                    atual = ui_comum.campo_texto("Senha atual", senha=True,
                                                 valor="master", props="")
                    nova = ui_comum.campo_texto("Nova senha (mín. 6)", senha=True,
                                                valor="", props="")
                    conf = ui_comum.campo_texto("Confirmar nova senha", senha=True,
                                                valor="", props="")

                # ---------------- COLUNA DIREITA: quem é ----------------
                with ui.column().classes("w-full min-w-0").style(
                        "gap: 1rem; min-width: 0"):
                    novo_nome = ui_comum.campo_texto("Novo nome de usuário",
                                                     valor="", props="")
                    email = ui_comum.campo_texto("E-mail",
                                                 valor="admin@example.com",
                                                 props="")
                    nome_completo = ui_comum.campo_texto(
                        "Nome completo (ou social)", valor="", props="",
                        tooltip="Nome pelo qual você será tratado no sistema. "
                                "Pode ser seu nome social (Decreto 8.727/2016)")
                    _campo_fone = None
                    fone = None
                    try:
                        from mod_skyrover import telefone as _tel
                        # DDI e número NA LINHA, lado a lado (04/10/2026), com
                        # o DDI em 140px — o piso do rótulo "+55 - Brasil".
                        #
                        # POR QUE 140px E NÃO MAIS CURTO (medido por SCREENSHOT
                        # do campo, varrendo a largura — 05/10/2026):
                        #
                        #   caixa   "+55 - Brasil" aparece?
                        #    88px       NÃO ("+55 - Bra:")
                        #   104px       NÃO ("+55 - Bra:")
                        #   112px       NÃO ("+55 - Bra:")
                        #   140px       SIM, inteiro
                        #
                        # E A PROVA PRECISA SER O SCREENSHOT: o QSelect usa
                        # `text-overflow: clip`, e o navegador NÃO reporta
                        # transbordo quando o texto é cortado assim. Medido: a
                        # 112px o `scrollWidth` dizia "não corta" e a imagem
                        # da tela mostrava "+55 - Bra:". Quem confiasse na
                        # métrica soltaria o campo cortado — por isso existe o
                        # piso `telefone.LARGURA_MINIMA_DDI`, que impede este
                        # chamador (e qualquer outro) de passar menos do que
                        # o rótulo precisa.
                        #
                        # E 140px CABE, porque a coluna do `master` saiu com
                        # 319px (medido) com o cartão no padrão de 680px e o
                        # padding lateral em 12px: 140 do DDI + 8 de gap +
                        # 171 do número, e o número precisa de 112px para o
                        # placeholder "(##) #####-####" — sobra 33px. É essa
                        # sobra que o cartão de 880px não dava e o de 640px
                        # tirava (aí a coluna era 279px e o número ficava com
                        # 131px).
                        _campo_fone = _tel.criar_campo_telefone(
                            valor="", largura_ddi="w-[140px]")
                    except Exception:
                        _campo_fone = None
                    if _campo_fone is None:
                        try:
                            fone = ui_comum.campo_texto("Telefone",
                                                        valor="",
                                                        props="")
                        except Exception:
                            fone = None

        def _v(campo):
            try:
                return getattr(campo, "value", "") or ""
            except Exception:
                return ""

        def _fone_valor():
            try:
                if _campo_fone is not None:
                    return _campo_fone["obter"]() or ""
                return _v(fone)
            except Exception:
                return ""

        def confirmar():
            try:
                if not _v(novo_nome).strip() or _v(novo_nome).strip().lower() == "master":
                    notificar("Informe um novo nome de usuário diferente de 'master'.",
                              tipo="negative")
                    return
                if _v(nova) != _v(conf):
                    notificar("As senhas não conferem", tipo="negative")
                    return
                try:
                    ok, msg, novo = autenticacao.trocar_credenciais_master(
                        nome_usuario, _v(novo_nome), _v(atual), _v(nova),
                        nome_completo=_v(nome_completo),
                        email=_v(email), fone=_fone_valor())
                except Exception as _e_cred:
                    _login_erro_log().exception(
                        f"falha ao trocar credenciais de '{nome_usuario}': {_e_cred}")
                    notificar("Erro ao trocar credenciais", tipo="negative")
                    return
                notificar(msg, tipo="positive" if ok else "negative")
                if ok:
                    try:
                        _login_erro_log().info(
                            f"credenciais ok: '{nome_usuario}' -> '{novo}' — "
                            "atualizando sessão")
                    except Exception:
                        pass
                    try:
                        app.storage.user["usuario"]["nome"] = novo
                    except Exception as _e_sess:
                        try:
                            _login_erro_log().exception(
                                f"falha ao atualizar sessão para '{novo}': {_e_sess}")
                        except Exception:
                            pass
                        _login_erro_log().info(
                            f"credenciais ok: '{novo}' — agendando navegação para /")
                    except Exception:
                        pass
                    ui.timer(0.2, lambda: ui.navigate.to("/"))
                    if ao_concluir:
                        try:
                            ao_concluir(novo)
                        except Exception as e:
                            _login_erro_log().exception(
                                f"troca_credenciais: callback de {novo} falhou: {e}")
            except Exception as _e_conf:
                try:
                    _login_erro_log().exception(
                        f"confirmar completo falhou para '{nome_usuario}': {_e_conf}")
                except Exception:
                    pass
                try:
                    notificar("Erro ao salvar credenciais.", tipo="error")
                except Exception:
                    pass



    # OS DOIS BOTÕES COM LARGURA IGUAL, lado a lado (04/10/2026).
    #
    # A GRADE, e não `grow` nos dois: com `grow` as larguras saíam 243px e
    # 326px, porque o `flex-grow` reparte o que sobra a partir da largura do
    # conteúdo — e o rótulo do segundo botão é 83px mais comprido. Grade dá
    # metades iguais, qualquer que seja o texto.
    #
    # `minmax(min(180px, 100%), 1fr)` e não `1fr 1fr` (05/10/2026): medido em
    # 390px, o `1fr 1fr` dava 171px por botão e o rótulo "Sair e entrar com
    # outro usuário" empurrava a grade para 368px dentro de 342px — transbordo
    # horizontal de 26px, e o documento inteiro ia a 392px numa janela de 390.
    # O `1fr` puro é `minmax(auto, 1fr)`, e o `auto` respeita o `min-content`
    # do rótulo, que é mais largo que a coluna. O `min(180px, 100%)` é o
    # mesmo idioma do `CSS_GRADE_AVISOS` e da grade de dois pais acima: duas
    # colunas enquanto houver 180px para cada, uma coluna abaixo disso — e o
    # `min(…, 100%)` é o que impede o piso de 180px de estourar uma caixa
    # menor. No desktop o resultado é o mesmo: 319px e 319px (medido).
    _linha_principal = ui.element("div").classes("w-full min-w-0").style(
        "display: grid; gap: .5rem; margin-top: .5rem; "
        "grid-template-columns: repeat(auto-fit, "
        "minmax(min(180px, 100%), 1fr))")
    with _linha_principal:
        _botao_tema("Salvar credenciais", on_click=confirmar,
                    extra_classes="w-full")
        # Mesmo rótulo curto da tela de troca de senha (18/10/2026): "Sair",
        # e a explicação do que ele faz fica no tooltip.
        _botao_tema("Sair", variante="contorno", on_click=_logout,
                    extra_classes="w-full",
                    tooltip="Sair e entrar com outro usuário")

    # ------- Apagar as contas de teste: abaixo, com o texto no tooltip ---
    #
    # Fica ABAIXO dos dois botões principais, e não dentro do formulário:
    # apagar conta de fábrica é decisão do administrador, não uma das seis
    # coisas que ele precisa preencher para entrar no sistema. O texto que
    # explicava isso — quatro linhas dentro do cartão — é agora o tooltip dos
    # botões, e aparece quando o mouse chega neles.
    _contas_teste = _contas_de_teste()
    if _contas_teste:
        _linha_apagar = ui.element("div").classes("w-full min-w-0").style(
            "display: grid; gap: .5rem; margin-top: .5rem; "
            # Uma coluna por botão onde o nome cabe ao lado; no celular
            # empilham, porque dois "Apagar ..." em 366px dariam 175px por
            # botão e o rótulo quebraria no meio.
            "grid-template-columns: repeat(auto-fit, "
            "minmax(min(180px, 100%), 1fr))")
        with _linha_apagar:
            for _c in _contas_teste:
                _btn_excluir = ui_comum.botao(
                    f"Apagar {_c['login']}", icone="delete",
                    on_click=lambda l=_c["login"]: _apagar_conta_teste(l),
                    variante="perigo", compacto=True,
                    chave_modulo="skyrover")
                _btn_excluir.props(
                    f'data-testid=apagar-conta-teste-{_c["login"]} '
                    f'aria-label="Apagar a conta de teste {_c["login"]}"')
                _btn_excluir.classes("no-print w-full")
                try:
                    ui.tooltip(TEXTO_CONTAS_DE_TESTE)
                except Exception:
                    pass


def _formulario_troca_senha(nome_usuario: str, ao_concluir=None):
    """Formulário da troca obrigatória, montado no slot da TELA DE LOGIN.

    EN: Renders the mandatory password-change form into the login screen slot.

    Não abre diálogo e não cria cartão (30/09/2026): quem chama é o callback
    `campos` do `preview_estilos.tela_login`, e o formulário aparece onde o
    login escreve usuário e senha. A troca é a continuação da entrada no
    sistema — mesmo invólucro, mesmo padrão verde, mesma caixa branca.

    O "fechar" também mudou de forma: não há modal para fechar. Concluir a
    troca é navegar para `/`, que é o que `ao_concluir` já fazia.

    `ao_concluir` roda DEPOIS da troca bem-sucedida, e é o que abre o passo
    seguinte do primeiro acesso (o cadastro dos telefones). Se a troca
    falhar, o callback não roda — senão o servidor cadastraria o telefone
    e continuaria com a senha provisória.

    A ORDEM do DOM dos três campos de senha (atual → nova → confirmar) é
    preservada: o QA preenche por índice em
    `tests/qa_login_helper.py::concluir_troca`.

    SENHA PROPOSTA PRÉ-PREENCHIDA (30/09/2026, decisão do responsável).
    `qacomum` e `qamaster` são contas de teste que ENTREGAM com a senha
    `123456` (§8.2 do AGENTS.md), e a troca obrigatória existe para quem
    entra. Deixar o campo vazio obriga a pessoa a DIGITAR uma senha que já
    se sabe qual é — trabalho sem resultado. O formulário nasce preenchido
    com `123456` nos dois campos, como o diálogo de credenciais do `master`
    nasce com o nome e a senha do responsável: a troca vira um clique.

    A senha ATUAL continua vazia de propósito: ela é o que se está
    substituindo, e vir preenchida tiraria a prova de que a pessoa sabe a
    senha de entrada.
    """
    # `34rem` é o teto DESTA tela (04/10/2026), e não o mesmo da tela do master
    # por um motivo concreto: aqui o cabeçalho do cartão e o rodapé existem
    # (~125px a mais), porque foi pedido que saíssem só na tela do master.
    # Medido: chassi de 494 a 521px aqui e de 342 a 392px na tela do master.
    # Com o `25rem` do master, a página desta transbordava em três dos cinco
    # tamanhos medidos (817px numa janela de 800, 831 numa de 768, 823 numa de
    # 740). Um número único não serve para as duas telas — e a lição é a mesma
    # de sempre: o teto descreve a moldura, e cada moldura tem a sua.
    with ui_comum.formulario_na_tela(
            max_altura="max(200px, calc(100vh - 34rem))",
            rotulo="Formulário da troca de senha") as (miolo, grade):
        # Os três campos na MESMA caixa e na MESMA posição do login: o `grade`
        # é o `CSS_GRADE_CAMPOS` de sempre, que no login seguraria usuário e
        # senha lado a lado em tela larga. Aqui são três senhas — e o
        # `auto-fit minmax(300px, 1fr)` empilha numa coluna de ~640px.
        with miolo:
            with grade:
                atual = ui_comum.campo_texto("Senha atual", senha=True, props="")
                # A sugestão é sorteada por navegador e JÁ validada
                # (05/10/2026) — ver `_senha_proposta`. Os dois campos
                # recebem a MESMA string, senão a confirmação nasce
                # diferente da senha e a pessoa não entende o erro.
                _proposta = _senha_proposta()
                nova = ui_comum.campo_texto("Nova senha (mín. 6)", senha=True,
                                            valor=_proposta,
                                            props="")
                conf = ui_comum.campo_texto("Confirmar nova senha", senha=True,
                                            valor=_proposta, props="")
            # --- Medidor de dificuldade + vazamento, enquanto digita (30/09) --
            # `on("update:model-value")` chega a cada tecla; o `ui.timer` de 0,8s
            # segura o que está digitando e dispara UMA vez ao parar, no mesmo
            # padrão do "Por página" do agregador.
            #
            # O requisito de rede local mora aqui: o que roda no event-loop é só
            # a troca de rótulo. A consulta sai por `run.io_bound`, porque pode
            # falar com a internet — e uma espera de socket na fila do
            # event-loop trava a tela inteira, sem internet até o fim do tempo
            # máximo. Fora da fila, o pior caso é um rótulo que não muda.
            #
            # A BARRA é o que responde "mas ela vazou e ainda assim…": vazamento
            # é um aviso, e dificuldade é a MEDIDA. Uma senha pode vazar e ser
            # forte (`Tr@nsit0#2026` não está em nenhum corpus), ou não vazar e
            # ser fraca (`nome_da_cidade@2026` é adivinhável e está intacta).
            # São duas leituras, e a pessoa precisa das duas.

            # --- Aceite de risco: checkbox + confirmação dupla (30/09) ----
            # Aparece SÓ quando a senha é fraca ou vazada. A partir daí o
            # servidor pode usá-la — mas precisa marcar que leu e que assume.
            # É o que o responsável pediu: a escolha é do servidor, e o que o
            # sistema registra é que ele soube do risco, não que ele aceitou
            # ser impedido.
            aceite = {"exigido": False, "salvar": None,
                      "confirmacao": None, "painel": None, "termo": None,
                      "medidor": None, "medidor_visivel": False,
                      "abaixo_do_piso": False, "medidor_dado": None}

            # O CHECKBOX QUE EXISTIA AQUI FOI TIRADO (30/09/2026, decisão do
            # responsável). Ele não autorizava nada sozinho: marcar a caixa
            # só revelava a palavra, e ainda era preciso DIGITAR "ESTOU
            # CIENTE". Duas confirmações para o mesmo ato, e a primeira era a
            # mais barata de todas — Bastava digitar. Quem escreve a palavra
            # já leu o termo, então a caixa não acrescentava nada.
            #
            # A ASSINATURA É A PALAVRA DIGITADA. Sem risco residual não há o
            # que assinar e o botão "Salvar" aparece direto; com risco
            # residual, ele só aparece depois de "ESTOU CIENTE".

            # 1) MEDIDOR — sempre visível
            # --- Medidor: SEMPRE VISÍVEL (30/09/2026) ---
            # O responsável pediu que a medidor e a contagem de vazamentos
            # apareçam permanentemente. Ficaram escondidas atrás do checkbox
            # numa versão anterior — e esconder a informação que decide se a
            # senha pode ser usada é o contrário de informar: a pessoa só
            # descobria que a senha era fraca DEPOIS de marcar a caixa.
            with ui.column().classes("w-full").style(
                    "gap: .5rem; min-width: 0") as painel_medidor:
                with ui.row().classes("w-full items-center no-wrap").style(
                        "gap: .6rem; min-width: 0"):
                    ui.label("Força da senha").classes(
                        "text-caption text-grey-7 shrink-0")
                    barra = ui.linear_progress(
                        value=0, show_value=False, size="10px").classes(
                        "grow").style("min-width: 0")
                # SEM rótulo de faixa (18/10/2026, pedido do responsável: "a
                # senha forte é irrelevante"). A barra colorida logo acima já
                # diz a mesma coisa, e a palavra "Forte" ao lado do "0
                # vezes" fazia a tela anunciar três notícias de duas coisas
                # diferentes. Quem não alcança o piso ouve o motivo nas
                # mensagens de bloqueio, que dizem o que falta.
                rotulo_nivel = ui.label("").classes(
                    "hidden").style("min-width: 0")
                # `overflow-wrap: anywhere` no rótulo de vazamento é o que
                # impede o defeito reportado: sem ele, o texto longo ("Esta
                # senha apareceu 210.461.208 vezes…") impõe a própria largura
                # mínima e empurra o cartão para fora da janela — o clássico
                # "filho largo estoura o pai em vez de encolher".
                rotulo_veredito = ui.label("").classes(
                    "text-body2").style(
                    "min-width: 0; overflow-wrap: anywhere")
                # VAZAMENTO: LINHA PRÓPRIA, COM A CONTAGEM (30/09/2026).
                # O servidor digita a senha procurando o NÚMERO — quantas
                # vezes ela apareceu — e esse número se perdia dentro do
                # veredito em prosa (que trunca em 3 bloqueios) ou sumia
                # inteiro quando a senha estava abaixo do piso, porque a
                # tela trocava o veredito por "não pode ser usada".
                #
                # Então é uma linha só, com o número à vista, logo abaixo da
                # barra. Três desfechos, e o terceiro é o honesto: quando a
                # consulta não aconteceu, diz que NÃO SE SABE.
                # `white-space: pre-line` (18/10/2026): o texto do veredito
                # são DUAS linhas — a contagem e a consequência — separadas por
                # `\n`, e sem isto o HTML junta as duas num parágrafo. Era
                # exatamente o que o responsável pediu: primeiro o número,
                # depois, na linha de baixo, se a senha foi liberada.
                rotulo_vazamento = ui.label("").classes(
                    "text-body2 font-bold").style(
                    "min-width: 0; overflow-wrap: anywhere; "
                    "white-space: pre-line")
            painel_medidor.set_visibility(True)
            aceite["medidor"] = painel_medidor

            # 2) TEXTO DO ACEITE — escondido
            aceite["painel"] = ui.column().classes(
                "w-full q-pa-md rounded-borders").style(
                "gap: .5rem; min-width: 0; border: 1px solid #E0E0E0;"
                "background: #FAFAFA")
            with aceite["painel"]:
                ui.label("Você ainda pode usar esta senha, assumindo o "
                         "risco").classes("text-subtitle2 font-bold").style(
                    "min-width: 0")
                # `white-space: pre-line` preserva as quebras do texto;
                # `min-width: 0` impede que a linha mais longa imponha a
                # largura mínima do painel. As duas juntas seguram o termo de
                # responsabilidade dentro da coluna.
                #
                # O TEXTO MUDA com a consulta de vazamento (18/10/2026): sem
                # vazamento, o item do vazamento sai e os outros quatro são
                # renumerados — ver `politica_senha.texto_aceite`.
                aceite["termo"] = ui.label(
                    politica_senha.texto_aceite(vazou=True)).classes(
                    "text-body2").style(
                    # SEM hifenização e SEM `overflow-wrap: anywhere`
                    # (18/10/2026, pedido do responsável): os dois cortavam
                    # palavras no meio da linha — "auto-" / "rizados" —, e um
                    # termo de responsabilidade cortado no meio da palavra
                    # lê como erro de montagem. `break-word` só quebra quando
                    # a palavra realmente não cabe, que é o caso que ele
                    # existe para resolver.
                    #
                    # `text-align: justify` (30/09/2026) continua: o termo é
                    # PROSA com número de artigo, e a margem direita reta é
                    # como documento legal se lê.
                    "white-space: pre-line; min-width: 0; "
                    "text-align: justify; overflow-wrap: break-word")
                # O rótulo pede o ENTER de propósito (18/10/2026): a última
                # tecla digitada não chega ao servidor (ver o `change` que
                # fecha a conta, mais abaixo), e sem esse gesto o botão
                # ficaria desativado sem ninguém entender por quê. Dizer o
                # caminho é melhor do que deixar a pessoa experimentando.
                aceite["confirmacao"] = ui.input(
                    label="Digite ESTOU CIENTE e pressione Enter",
                    placeholder="ESTOU CIENTE",
                ).props("outlined dense").classes("w-full")
                ui.label("Nada aqui impede você de escolher outra senha — "
                         "esta tela continua aqui enquanto você quiser."
                         ).classes("text-caption text-grey-7")
            aceite["painel"].set_visibility(False)

            def _revelar_risco():
                """Mostra o texto do aceite, se a senha estiver acima do piso.

                **Nada é criado aqui.** O painel, o medidor e o checkbox já
                nasceram dentro do `with miolo:`, e só a visibilidade muda.

                A primeira versão criava os elementos de dentro de
                `_avaliar_senha`, que roda num `ui.timer`. Quando o timer
                dispara, o "slot corrente" do NiceGUI já não é o do diálogo —
                então o painel nascia fora do cartão e o checkbox não aparecia
                nem com senha fraca de verdade.
                """
                try:
                    aceite["painel"].set_visibility(
                        bool(aceite["exigido"]
                             and aceite["medidor_visivel"]))
                except Exception:
                    pass

            async def _avaliar_senha():
                """Medidor + veredito, fora do event-loop.

                Falha aqui não trava a troca: a checagem é ajuda, não portão.
                """
                from mod_skyrover.validador_senha import (
                    analisar_online, texto_para_usuario, texto_vazamento)
                senha = nova.value or ""
                if len(senha) < 4:
                    rotulo_veredito.set_text("")
                    rotulo_vazamento.set_text("")
                    rotulo_nivel.set_text("")
                    # A barra volta ao estado inicial: zerada e VERMELHA. Sem
                    # o reset, ela ficaria com a cor da senha anterior e a
                    # pessoa leria a força de uma senha que já não está mais no
                    # campo.
                    barra.set_value(0)
                    barra.props(
                        f"color={politica_senha.COR_BARRA_FRACA}")
                    aceite["exigido"] = False
                    aceite["abaixo_do_piso"] = True
                    aceite["painel"].set_visibility(False)
                    _atualizar_botao_salvar()
                    return
                try:
                    r, med = await asyncio.gather(
                        run.io_bound(analisar_online, senha, nome_usuario),
                        run.io_bound(politica_senha.medidor, senha))
                    r = r or {}
                    med = med or {}
                    barra.set_value(med.get("percentual", 0) / 100.0)
                    # A COR da barra segue a faixa (vermelho / amarelo /
                    # verde) e o RÓTULO é só a palavra — "Muito fraca", sem
                    # os BITS. O número de bits é medida de entropia: serve
                    # para o validador decidir, e não diz nada a quem digita.
                    # "Muito fraca — 15.5 bits" é o mesmo problema de jargão
                    # que `texto_para_usuario` já evita: a pessoa precisa
                    # ler "fraca", não a contagem por trás dela.
                    barra.props(f"color={politica_senha.cor_da_barra(med)}")
                    # `rotulo_nivel` é o elemento Vazio acima: ele existe
                    # para o `set_text("")` do estado inicial não quebrar, e
                    # não recebe mais texto (ver o comentário da criação).

                    # PISO DE 0,5 (decisão do responsável, 30/09/2026):
                    # abaixo disso a senha não é usável, e nenhum aceite
                    # destrava. `inaceitavel` é o que o serviço lê.
                    #
                    # O ATALHO (18/10/2026, mesmo responsável) tira a parede:
                    # com no mínimo `senha_tamanho_minimo` caracteres, pelo
                    # menos dois dos quatro tipos e SEM vazamento, a senha
                    # passa a ser usável mesmo com a barra no vermelho — e o
                    # que se exige então é o aceite de risco, o mesmo da faixa
                    # amarela. A barra continua vermelha: a senha continua
                    # fraca, ela só deixa de ser recusada.
                    #
                    # `vazou` entra no cálculo porque "não ter vazado" é uma
                    # das três condições — e o vazamento só é conhecido depois
                    # da consulta, que é o que `analisar_online` acabou de
                    # fazer.
                    abaixo = not politica_senha.acima_do_piso(med)
                    _vazou = bool((r or {}).get("vazou"))
                    assumivel = politica_senha.minimo_essencial(
                        senha, vazou=_vazou)
                    bloqueada = bool(abaixo and not assumivel)
                    aceite["abaixo_do_piso"] = bloqueada
                    aceite["medidor_dado"] = med

                    if bloqueada:
                        rotulo_veredito.set_text("Esta senha não pode ser "
                                                  "usada.")
                        rotulo_veredito.classes(
                            remove="text-grey-7 text-positive text-warning",
                            add="text-negative")
                    else:
                        texto = texto_para_usuario(r)
                        # 05/10/2026: quem passa é AMARELO, não verde.
                        #
                        # A faixa que passou é a amarela do validador
                        # (passou de 50% de força com os quatro tipos), e ela
                        # exige o termo de responsabilidade. Verde aqui
                        # diria "aprovada, vá em frente" para uma senha que o
                        # responsável decidiu tratar como risco assumido — e
                        # é a cor que a barra NÃO usa quando ela está forte,
                        # então as duas peças da tela deixavam de falar a
                        # mesma língua.
                        rotulo_veredito.set_text(texto)
                        rotulo_veredito.classes(
                            remove="text-grey-7 text-positive text-negative",
                            add=("" if not texto else
                                 "text-negative" if not r.get("ok")
                                 else "text-warning"))

                    # A LINHA DO VAZAMENTO é montada SEMPRE, antes mesmo do
                    # `if abaixo`: o servidor está digitando a senha para
                    # descobrir se ela vazou, e a resposta não pode depender
                    # de a senha ser forte. Quando a senha está abaixo do
                    # piso, `texto_para_usuario` nem roda — então o número
                    # que ele traria sumiria; aqui ele vem direto do veredito.
                    _pintar_vazamento(r)
                    # O TERMO acompanha a consulta: com a senha limpa, sai o
                    # item do vazamento e os números são refeitos (18/10/2026).
                    # Fica junto da linha de vazamento porque é a mesma
                    # informação que manda: foi encontrada ou não foi.
                    try:
                        if aceite.get("termo") is not None:
                            aceite["termo"].set_text(
                                politica_senha.texto_aceite(
                                    vazou=bool((r or {}).get("vazou"))))
                    except Exception:
                        pass

                    # O ACEITE (o termo + o "ESTOU CIENTE") é exigido em DOIS
                    # casos, e não só no vazamento (05/10/2026):
                    #
                    # 1. a senha VAZOU — como desde 30/09/2026;
                    # 2. a senha está na FAIXA AMARELA — passou de 50% de
                    #    força com os quatro tipos, e o responsável pediu o
                    #    alerta de risco e LGPD exatamente nessa faixa.
                    #
                    # Antes entrava qualquer "risco residual": vazamento, ou
                    # palavra do órgão, ou ano, ou o nome do usuário. Isso
                    # produzia a tela que ninguém conseguia ler: o termo
                    # citava "vazamentos públicos conhecidos" com número de
                    # artigo LGPD ao lado de um veredito dizendo que a senha
                    # NÃO estava em nenhum vazamento. Duas frases que se
                    # negam, na mesma tela.
                    #
                    # O termo trata de RISCO ASSUMIDO pela pessoa, e tanto o
                    # vazamento quanto a faixa amarela são isso: "você sabe o
                    # que está fazendo?". Lembrar que a senha está na palavra
                    # do órgão não precisa de termo; precisa de senha melhor.
                    #
                    # `excecao` (conta de teste) nunca assina termo nenhum.
                    faixa_amarela = str(r.get("faixa") or "") == "amarela"
                    # O aceite é exigido em TRÊS casos (18/10/2026): a senha
                    # vazou, a faixa é a amarela, ou a senha entrou pelo ATALHO
                    # — barra vermelha, mas com o mínimo essencial. O último
                    # é o que faz do atalho uma troca por assinatura, e não uma
                    # porta aberta: sem escrever "ESTOU CIENTE" o botão segue
                    # travado, exatamente como nos outros dois.
                    aceite["exigido"] = bool(
                        (r.get("vazou") or faixa_amarela
                         or (abaixo and assumivel))
                        and not r.get("excecao")
                        and not bloqueada)
                    _revelar_risco()
                    _atualizar_botao_salvar()
                except Exception as e:
                    lg = _login_erro_log()
                    if lg:
                        lg.exception(f"troca_senha: veredito falhou: {e}")
                    rotulo_veredito.set_text("")

            def _aceite_valido() -> bool:
                """A autorização é a PALAVRA DIGITADA — e só quando há termo.

                O checkbox que existia antes foi tirado: ele não liberava nada
                sozinho, só revelava a palavra. Quem escreve "ESTOU CIENTE" já
                leu o termo, então a caixa era redundante.

                Não havendo termo — senha boa e sem vazamento — não há o que
                assinar, e a troca está liberada.
                """
                if not aceite["exigido"]:
                    return True
                if aceite["confirmacao"] is None:
                    return False
                texto = (aceite["confirmacao"].value or "").strip().upper()
                return texto == "ESTOU CIENTE"

            def _atualizar_botao_salvar():
                """O "Alterar senha" fica LIVRE ou DESATIVADO — nunca some.

                A regra é do responsável (30/09/2026), e a escolha de mostrar
                ou esconder é dela que vem: botão que aparece e desaparece
                deixa a pessoa sem saber se falta digitar mais alguma coisa ou
                se o sistema já recusou. Um botão **desativado** diz as duas
                coisas ao mesmo tempo — e é o que o Quasar já desenha sozinho,
                esmaecido.

                | segurança | vazamento | "Alterar senha"                        |
                |:----------|:----------|:---------------------------------------|
                | < 0,5     | qualquer  | **desativado** (a senha não serve)     |
                | ≥ 0,5     | não       | livre — troca e sai                    |
                | ≥ 0,5     | sim       | desativado até escrever "ESTOU CIENTE",|
                |           |           | depois **livre** — o termo é que assina|

                O termo e o campo de confirmação só existem no terceiro caso:
                sem vazamento não há risco a assinar. Ver `aceite["exigido"]`.

                A referência vem de `aceite["salvar"]`, e não de `globals()`:
                a variável é LOCAL desta função, e `globals()` só enxerga o
                módulo — nunca a achava, e o botão ficava sempre visível.
                """
                try:
                    if aceite["salvar"] is None:
                        return
                    aceite["medidor"].set_visibility(True)
                    aceite["medidor_visivel"] = True
                    if aceite["abaixo_do_piso"] or not _aceite_valido():
                        aceite["salvar"].disable()
                    else:
                        aceite["salvar"].enable()
                except Exception:
                    pass

            def _registrar_aceite_agora():
                """Grava o aceite no momento em que o "Salvar" é clicado.

                Chamado de dentro de `confirmar`, e não por um botão próprio:
                o botão "Salvar" só aparece quando o aceite já é válido, então
                chegar até ele É a confirmação dupla.

                O registro é o que muda a co-responsabilidade de afirmação para
                fato. A senha NUNCA entra no registro — só quem assinou,
                quando, e que o texto da LGPD foi apresentado.
                """
                try:
                    med = aceite.get("medidor_dado") or {}
                    autenticacao.registrar_aceite_risco(
                        nome_usuario, "senha",
                        detalhe=f"forca={med.get('percentual', 0)}% "
                                f"bits={med.get('bits', 0)} "
                                f"nivel={med.get('nivel', '')}; "
                                f"aceite assinado")
                    autenticacao.marcar_senha_aceita(nome_usuario, True)
                    return True
                except Exception as e:
                    lg = _login_erro_log()
                    if lg:
                        lg.exception(f"troca_senha: aceite falhou: {e}")
                    return False

            _pendente_veredito = {"timer": None}

            # Cada tecla nos campos reavalia o botão. Sem isto a autorização só mudaria
            # de estado quando a pessoa voltasse a mexer na senha.
            def _reavaliar_aceite(_=None):
                """Um toque em qualquer campo: reavalia o botão.

                Quem reavalia é `_atualizar_botao_salvar`, porque é ela que
                decide mostrar o "Alterar senha" — e é também ela que
                REVELA o termo de responsabilidade quando sobra risco. Um
                lugar só para a decisão evita os dois caminhos divergirem,
                que foi como o botão acabou aparecendo sem autorização.
                """
                try:
                    aceite["medidor_visivel"] = True
                    if aceite["medidor_dado"]:
                        _revelar_risco()
                    _atualizar_botao_salvar()
                except Exception:
                    pass

            for _campo in (aceite["confirmacao"], nova, conf):
                try:
                    _campo.on("update:model-value", _reavaliar_aceite)
                except Exception:
                    pass



            # Primeira passada: o botão nasce DESATIVADO, não escondido. Sem esta
            # chamada ele ficaria CLICÁVEL no instante em que a tela abre,
            # antes de qualquer senha ter sido avaliada — e o clique passaria
            # por cima do piso de força.
            try:
                aceite["salvar"].disable()
            except Exception:
                pass
            _atualizar_botao_salvar()

            def _agendar_veredito(_=None):
                t = _pendente_veredito.get("timer")
                if t is not None:
                    try:
                        t.delete()
                    except Exception:
                        pass
                _pendente_veredito["timer"] = ui.timer(
                    0.8, _avaliar_senha, once=True)

            nova.on("update:model-value", _agendar_veredito)
            # A ÚLTIMA TECLA NÃO CHEGA AO SERVIDOR (18/10/2026, medido).
            #
            # O NiceGUI desta versão perde o último `update:model-value` de uma
            # digitação: em dez teclas ele entrega nove. Medido num app
            # isolado, sem nada deste projeto: digitar "abcdefghij" deixa o
            # servidor com "abcdefghi", e o texto só completa quando o usuário
            # mexe de novo no campo.
            #
            # Aqui isso NÃO era um detalhe: no aceite, o valor conferido é
            # "ESTOU CIENTE", e faltando a última letra a conferida nunca
            # passava — o "Alterar senha" ficava desativado para sempre, sem
            # mensagem que explicasse o motivo. Era a tela trancada sem causa.
            #
            # O `change` (que dispara ao sair do campo ou apertar Enter) traz
            # o valor FINAL, e é ele que fecha a conta: sem nenhuma tecla a
            # mais, digitar a frase e sair do campo já destrava o botão.
            #
            # Nos campos de senha o mesmo `change` refaz a avaliação com o
            # texto completo — senão o veredito que a pessoa lê é o da senha
            # sem a última letra.
            try:
                aceite["confirmacao"].on(
                    "change", _reavaliar_aceite, args=["value"],
                    js_handler="(evt) => emit(evt.value)")
                nova.on("change", _agendar_veredito, args=["value"],
                        js_handler="(evt) => emit(evt.value)")
            except Exception as e:
                lg = _login_erro_log()
                if lg:
                    lg.exception(f"troca_senha: 'change' nao registrado: {e}")

            # Primeira avaliação: o formulário já nasce preenchido, e a pessoa
            # precisa do veredito sem ter que mexer em algum campo.
            _agendar_veredito()

        def _pintar_vazamento(r):
            """Escreve a linha de vazamento (com a CONTAGEM) a partir do veredito.

            Fica separada porque tem TRÊS desfechos que não podem ser
            confundidos — e a confusão seria mentira na tela:

            - **encontrada** → o número de vezes, e o fato de a senha já ter
              sido usada por outras pessoas;
            - **não encontrada** → a consulta respondeu e a senha não está em
              nenhum vazamento conhecido;
            - **não consultada** → sem internet, consulta desligada ou serviço
              fora do ar. Aqui **não se sabe**, e é isso que a linha diz.
              Pintar de verde esse desfecho seria afirmar que a senha está
              limpa sem ter perguntado a ninguém.

            Vermelho só quando encontrou. O verde é o "não encontrou" — que
            é uma boa notícia, mas uma notícia sobre uma consulta que
            aconteceu de verdade.
            """
            try:
                from mod_skyrover.validador_senha import (
                    texto_vazamento as _texto_vazamento)
                texto = _texto_vazamento(r or {})
                rotulo_vazamento.set_text(texto)
                if not texto:
                    rotulo_vazamento.classes(
                        remove="text-negative text-positive text-grey-7")
                elif (r or {}).get("vazou"):
                    rotulo_vazamento.classes(
                        remove="text-positive text-grey-7",
                        add="text-negative")
                elif (r or {}).get("consulta_online") in ("ok", "cache",
                                                           "vazia"):
                    rotulo_vazamento.classes(
                        remove="text-negative text-grey-7",
                        add="text-positive")
                else:
                    rotulo_vazamento.classes(
                        remove="text-negative text-positive",
                        add="text-grey-7")
            except Exception as e:
                # AGENTS.md 3.2: nunca engolir em silencio. Um pass aqui
                # escondeu um NameError por exatamente o tempo de uma sessao
                # inteira, com a tela parecendo funcionar.
                try:
                    _login_erro_log().exception(
                        f"troca_senha: linha de vazamento falhou: {e}")
                except Exception:
                    pass

        def confirmar():
            if nova.value != conf.value:
                notificar("As senhas não conferem", tipo="negative")
                return
            # O botão só chega até aqui quando o aceite já é válido, então
            # chegar nele É a autorização. Registrar agora, e não antes: é este
            # clique que a pessoa fez sabendo.
            try:
                if aceite["exigido"]:
                    _registrar_aceite_agora()
            except Exception:
                pass
            # A EXCEÇÃO é o serviço, não a tela: `trocar_senha_propria` chama
            # `veredito_bloqueante` e recusa. Aqui só existe o caminho que
            # permite senha fraca — o aceite assinado. Sem ele assinado, o
            # serviço recusa de novo, e é isso que fecha o círculo.
            try:
                if not autenticacao.senha_aceita_por_aceite(nome_usuario):
                    autenticacao.marcar_senha_aceita(nome_usuario, True)
            except Exception:
                pass
            ok, msg = autenticacao.trocar_senha_propria(nome_usuario, atual.value or "", nova.value or "")
            notificar(msg, tipo="positive" if ok else "negative")
            if ok:
                try:
                    autenticacao.marcar_senha_aceita(nome_usuario, False)
                except Exception:
                    pass
                ui.navigate.to("/")
                if ao_concluir:
                    try:
                        ao_concluir()
                    except Exception as e:
                        lg = _login_erro_log()
                        if lg:
                            lg.exception(
                                f"troca_senha: callback de {nome_usuario} falhou: {e}")

        # "Alterar senha" e "Sair" na MESMA LINHA (18/10/2026, pedido do
        # responsável: "colocar o botão alterar senha e sair na mesma linha,
        # reescrever o texto do botão sair para apenas Sair").
        #
        # Estavam empilhados e separados por um `ui.separator`, que fazia "Sair"
        # parecer uma seção diferente da tela — quando os dois botões são a
        # mesma coisa: as duas saídas que a pessoa tem daqui. A grade é a
        # mesma das duas telas acima (`auto-fit` com piso de 180px), que é a
        # que não transborda em tela de 390px.
        # ---- "Sair": a saída para MÁQUINA COMPARTILHADA ----
        # A troca obrigatória hoje deixava a pessoa sem porta de saída: ou ela
        # troca a senha de alguém else's, ou fica presa. Em balcão de
        # atendimento, recepção e sala compartilhada isso é o caminho natural —
        # a pessoa abriu o sistema, viu que não pode ficar com a senha alheia e
        # precisa simplesmente liberar a máquina para o próximo.
        #
        # Sai de verdade: encerra a sessão no banco e limpa o `storage.user`
        # (é o mesmo `_logout` do cabeçalho). Voltar ao login não bastaria — a
        # sessão continuaria viva e quem viesse depois entraria direto, sem
        # passar pela tela de login.
        #
        # 05/10/2026: o rótulo "Não quer trocar agora?" SAIU, o botão ficou.
        # O responsável pediu a remoção do texto e manteve a saída — que é o
        # que importa, porque é a única forma de liberar a máquina. O texto
        # repetia a pergunta que a tela já faz sozinha (o painel teal diz o
        # que está sendo pedido) e ocupava uma linha da área de rolagem do
        # formulário, que é o recurso escasso desta tela.
        ui.separator().classes("w-full")
        _linha_troca = ui.element("div").classes("w-full min-w-0").style(
            "display: grid; gap: .5rem; margin-top: .5rem; "
            "grid-template-columns: repeat(auto-fit, "
            "minmax(min(180px, 100%), 1fr))")
        with _linha_troca:
            # Os DOIS botões na mesma linha, e na ordem em que se lê: salvar
            # primeiro (é o que a tela pede), sair depois.
            aceite["salvar"] = _botao_tema(
                "Alterar senha", on_click=confirmar, extra_classes="w-full")
            # O rótulo é só "Sair" (18/10/2026): "e entrar com outro usuário"
            # explicava o que o botão já faz — e era o que empurrava a grade
            # para fora do cartão em tela estreita (o transbordo de 26px
            # medido em 390px, que está escrito nas linhas de cima).
            _botao_tema("Sair", variante="contorno", on_click=_logout,
                        extra_classes="w-full",
                        tooltip="Sair e entrar com outro usuário")

    # Não há `dlg.props("persistent")` nem `dlg.open()`: a troca virou a
    # própria tela de login, não um modal. Não há ESC para fechar, e não há
    # clique fora — a troca é realmente obrigatória, agora pela ausência de
    # porta de saída em vez de pela propriedade do diálogo.


def _dialogo_telefones(nome_usuario: str, ao_concluir=None):
    """Força o cadastro dos telefones no primeiro acesso (persistent).

    EN: First-access phone registration. The transparency portal publishes
    name, unit and role — but no extension. So the extension only exists if
    the server types it here, which is why this dialog is mandatory.

    PT-BR: Cadastro dos telefones no primeiro acesso. O portal da
    transparência publica nome, unidade e cargo — mas não o ramal. Então o
    número só existe se o servidor o informar aqui, e é por isso que este
    diálogo é obrigatório.

    A CONSENTIMENTO — cada linha da prefeitura é escolha de quem atende:

    - **celular particular**: começa desmarcado, e é assim que o prefeito
      resolve não ter o número na lista. Ninguém precisa explicar nada a
      ninguém.
    - **celular da prefeitura**: começa desmarcado também, e é assim que o
      responsável pela defesa civil resolve aparecer para todos. Quem atende
      emergência liga de qualquer lugar; precisa ser achado.
    - **fixo da prefeitura**: a caixa vem **travada marcada**. Linha
      institucional existe para ser encontrada — é o número que a prefeitura
      divulga em visita de rotina. Guardá-lo tornaria o cadastro inútil para
      o fim a que ele serve.
    - **residencial**: não tem caixa nenhuma. Telefone de casa não entra em
      cadastro de servidor, ponto.
    """
    from mod_gest_cad_usuario import bd_manipulador as _bd_usuarios

    # Diálogo de FORMULÁRIO: 4 campos, 4 caixas de consentimento e texto longo
    # de instrução. A 620px ele virava uma coluna alta; agora tem 88vw, teto de
    # 90vh e só o miolo rola. Os `data-testid` das caixas de consentimento são
    # contrato do QA (`tests/test_primeiro_acesso_e2e.py`) e ficam como
    # estavam.
    with ui_comum.dialogo_formulario(
            chave_modulo="skyrover", sem_descricao=True) as (dlg, card, miolo, grade):
        ui.label("Seus telefones").classes("text-h6")
        ui.label(f"{autenticacao.nome_de_tratamento(nome_usuario)}, "
                 "falta o passo que faz você aparecer na lista telefônica. "
                 "Preencha o que quiser e marque o que pode ficar público.").classes(
            "text-body2 text-grey-7")

        # Grade só dos CAMPOS. Cada par (campo + caixa) é uma célula: a caixa
        # fica logo abaixo do seu campo, e o par inteiro ocupa uma coluna —
        # juntar os quatro campos numa linha e as caixas noutra desamarraria
        # quem responde "pode aparecer?" de qual número é.
        with grade:
            with ui.column().classes("w-full gap-1"):
                # ---- celular particular ----
                cel_pessoal = ui_comum.campo_texto(
                    "Celular particular", props="outlined dense",
                    placeholder="(35) 99999-0000")
                chk_pessoal = ui.checkbox("Pode aparecer na lista telefônica")
                chk_pessoal.props("dense data-testid=primeiro-acesso-chk-pessoal") \
                    .classes("text-body2")

            with ui.column().classes("w-full gap-1"):
                # ---- celular da prefeitura ----
                cel_empresa = ui_comum.campo_texto(
                    "Celular da prefeitura", props="outlined dense",
                    placeholder="(35) 99999-0000")
                chk_empresa = ui.checkbox("Pode aparecer na lista telefônica")
                chk_empresa.props("dense data-testid=primeiro-acesso-chk-empresa") \
                    .classes("text-body2")

            with ui.column().classes("w-full gap-1"):
                # ---- fixo da prefeitura ----
                fixo_empresa = ui_comum.campo_texto(
                    "Telefone fixo da prefeitura", props="outlined dense",
                    placeholder="(00) 3591-5100")
                chk_fixo = ui.checkbox("Aparece na lista telefônica")
                # Marcada E travada. A ordem importa: `value` antes de `disable`,
                # senão o NiceGUI aplica `disable` e a atribuição seguinte é
                # ignorada — e a tela mostrava uma caixa vazia ao lado de um texto
                # que dizia que ela apareceria. A regra que manda é a de
                # `telefone_e_publicavel`, não a do formulário; aqui só se
                # mostra o que ela faz.
                chk_fixo.props("dense disable data-testid=primeiro-acesso-chk-fixo") \
                    .classes("text-body2 text-grey-6")
                chk_fixo.value = True

            with ui.column().classes("w-full gap-1"):
                # ---- telefone de recado ----
                chk_recado = ui.checkbox(
                    "Não tenho linha própria: este é o telefone do setor, para recado")
                chk_recado.props("dense data-testid=primeiro-acesso-chk-recado") \
                    .classes("text-body2")

                # ---- residencial ----
                fixo_pessoal = ui_comum.campo_texto(
                    "Telefone residencial (opcional)", props="outlined dense",
                    placeholder="(00) 3800-0000")
                ui.label("O residencial fica só no seu cadastro — nunca sai na "
                         "lista telefônica.").classes("text-caption text-grey-6")

        # fora da grade: as explicações e o aviso de faixa são texto corrido e
        # ocupam a largura toda, não uma coluna estreita da grade
        ui.label("Marque quando for o telefone do SETOR: a garagem, a "
                 "secretaria da escola, a unidade de saúde, o almoxarifado. "
                 "Quem receber a ligação anota o recado e passa adiante — "
                 "é assim que a lista telefônica funciona para quem não "
                 "atende.").classes("text-caption text-grey-6")

        # aviso de faixa, preenchido enquanto o servidor digita
        aviso_faixa = ui.label("").classes("text-caption text-orange-8")

        def _montar_contatos():
            """Os 4 campos viram a lista que o cadastro grava."""
            contatos = []
            if (cel_pessoal.value or "").strip():
                contatos.append({"numero": cel_pessoal.value, "papel": "pessoal",
                                 "tipo": "celular", "visivel": chk_pessoal.value})
            if (cel_empresa.value or "").strip():
                contatos.append({"numero": cel_empresa.value, "papel": "empresa",
                                 "tipo": "celular", "visivel": chk_empresa.value})
            if (fixo_empresa.value or "").strip():
                # visivel=1 fixo: é a regra da prefeitura
                # (telefone_e_publicavel) — o checkbox travado acima é só o
                # espelho visual dela, a decisão real fica no banco.
                contatos.append({"numero": fixo_empresa.value, "papel": "empresa",
                                 "tipo": "fixo", "visivel": True,
                                 "recado": bool(chk_recado.value)})
            if (fixo_pessoal.value or "").strip():
                contatos.append({"numero": fixo_pessoal.value, "papel": "pessoal",
                                 "tipo": "fixo", "visivel": False})
            return contatos

        def _reavaliar_faixa(_evento=None):
            """Avisa, ENQUANTO digita, se o fixo está fora das faixas.

            Mostrar o aviso depois de salvar é tarde: o servidor já salvou, já
            recebeu o "telefones registrados" e só depois descobre que o
            número estava errado. A faixa existe para pegar o erro no dedo,
            não no relatório.

            Registrado com `on_value_change`, que é o caminho do próprio
            projeto (`campo_texto(ao_mudar=...)`); `on("update:model-value")`
            também funcionaria, mas mistura duas formas de fazer a mesma
            coisa no mesmo arquivo."""
            try:
                num = (fixo_empresa.value or "").strip()
                if not num:
                    aviso_faixa.set_text("")
                    return
                avalio = _bd_usuarios.avaliar_telefones_primeiro_acesso(
                    [{"numero": num, "papel": "empresa", "tipo": "fixo"}])
                fora = avalio.get("fora_da_faixa") or []
                if not fora:
                    aviso_faixa.set_text("")
                    return
                perto = fora[0][1] if len(fora[0]) > 1 else ""
                aviso_faixa.set_text(
                    f"Atenção: {num} está fora das faixas de telefone da "
                    f"prefeitura."
                    + (f" A faixa mais próxima é a {perto} — confira o número."
                       if perto else " Confira o número."))
            except Exception as e:
                lg = _login_erro_log()
                if lg:
                    lg.exception(f"primeiro_acesso: aviso de faixa falhou: {e}")
                aviso_faixa.set_text("")

        fixo_empresa.on_value_change(_reavaliar_faixa)

        def _salvar(liberacao_provisoria=False):
            """Grava. `liberacao_provisoria` é o paliativo do servidor que não
            sabe o próprio número — só chega True depois das DUAS confirmações."""
            contatos = _montar_contatos()
            try:
                ok, msg, detalhes = _bd_usuarios.registrar_contatos_primeiro_acesso(
                    nome_usuario, nome_usuario, contatos,
                    liberacao_provisoria=liberacao_provisoria)
            except Exception as e:
                lg = _login_erro_log()
                if lg:
                    lg.exception(
                        f"primeiro_acesso: falha ao gravar telefones de {nome_usuario}: {e}")
                notificar("Erro ao salvar os telefones — tente de novo.", tipo="error")
                return
            if not ok:
                notificar(msg, tipo="negative")
                return
            notificar(msg, tipo="positive")
            fora = (detalhes or {}).get("fora_da_faixa") or []
            if fora:
                # o salvou, mas o número não é nosso: fala alto, porque o
                # próximo passo do servidor é justamente confiar no número
                notificar(
                    f"{len(fora)} telefone(s) fora das faixas da prefeitura — "
                    f"veja o aviso no formulário e ajuste depois.",
                    tipo="warning")
            if (detalhes or {}).get("provisorio"):
                dias = _bd_usuarios.DIAS_LIBERACAO_PROVISORIA
                _aviso_provisorio(nome_usuario, dias)
            dlg.close()
            if ao_concluir:
                try:
                    ao_concluir()
                except Exception as e:
                    lg = _login_erro_log()
                    if lg:
                        lg.exception(
                            f"primeiro_acesso: falha no pós-conclusão de {nome_usuario}: {e}")

        def _confirmar():
            """Primeira trava: pergunta pelo telefone da prefeitura."""
            try:
                avalio = _bd_usuarios.avaliar_telefones_primeiro_acesso(
                    _montar_contatos())
            except Exception as e:
                lg = _login_erro_log()
                if lg:
                    lg.exception(f"primeiro_acesso: avaliação falhou: {e}")
                _salvar()
                return
            if avalio.get("tem_da_prefeitura"):
                _salvar()
                return
            if not avalio.get("particulares"):
                notificar("Informe também um telefone particular de contato.",
                          tipo="negative")
                return
            _travas_falta_numero(nome_usuario, _salvar)

        _botao_tema("Salvar telefones", on_click=_confirmar,
                    extra_classes="w-full mt-2")
    dlg.props("persistent")
    dlg.open()


def _travas_falta_numero(nome_usuario, ao_confirmar):
    """As DUAS travas quando o servidor não sabe o número da prefeitura.

    A primeira pergunta se ele quer sair e descobrir o número. A segunda
    confirma que ele entendeu o preço: acesso por 4 dias, e depois a conta
    fecha até o DTI abrir.

    Duas travas em vez de uma não é desconfiança do servidor — é o contrário.
    A única falha que sobra é o clique apressado numa tela de advertência, e
    ele passa por duas. Um servidor que leu o aviso duas vezes e seguiu em
    frente é alguém que entendeu; alguém que clicou uma vez pode ter só
    lido a primeira linha."""
    with ui.dialog() as dlg_t:
        with ui.card().classes("w-[520px] gap-3"):
            ui.label("Falta um telefone da prefeitura").classes("text-h6")
            ui.label(
                "Todo servidor da prefeitura está ligado a uma secretaria ou "
                "a um setor, e todo setor tem telefone. O sistema precisa de um "
                "número institucional para você constar na lista telefônica.") \
                .classes("text-body2 text-grey-7")
            ui.label("Se você não tem linha própria, use o telefone do seu "
                     "setor e marque como telefone de recado: a garagem, a "
                     "secretaria da escola, a unidade de saúde, o "
                     "almoxarifado. Quem receber anota e passa adiante.") \
                .classes("text-body2 text-grey-7")
            with ui.row().classes("w-full justify-end").style("gap: 0.5rem"):
                ui_comum.botao("Informar o telefone do setor", variante="texto",
                               chave_modulo="skyrover", on_click=dlg_t.close)
                _botao_tema("Não sei meu número", on_click=lambda: _travas_confirmar(
                    nome_usuario, ao_confirmar, dlg_t),
                    variante="secundario")
    dlg_t.open()


def _travas_confirmar(nome_usuario, ao_confirmar, dlg_anterior):
    """Segunda trava: o preço, escrito."""
    from mod_gest_cad_usuario import bd_manipulador as _bd

    dias = _bd.DIAS_LIBERACAO_PROVISORIA
    with ui.dialog() as dlg_c:
        with ui.card().classes("w-[520px] gap-3"):
            ui.label("Acesso temporário").classes("text-h6")
            ui.label(
                f"Sem o número, seu acesso fica liberado por {dias} dias. "
                f"Depois disso a conta é bloqueada e só o DTI consegue "
                f"reabrir.").classes("text-body2 text-grey-7")
            ui.label(
                "Use esses 4 dias para descobrir o seu número: pergunte na "
                "secretaria da sua escola, na unidade de saúde onde você "
                "trabalha, no setor de empilhadeiras, na garagem ou no "
                "almoxarifado. Depois, volte aqui pelo seu perfil e atualize "
                "o telefone — o acesso fica definitivo.").classes(
                "text-body2 text-grey-7")
            with ui.row().classes("w-full justify-end").style("gap: 0.5rem"):
                ui_comum.botao("Voltar e informar o número", variante="texto",
                               chave_modulo="skyrover", on_click=dlg_c.close)
                _botao_tema("Entendo, liberar por enquanto",
                            on_click=lambda: (
                                dlg_c.close(), dlg_anterior.close(),
                                ao_confirmar(True)),
                            variante="primario")
    dlg_c.open()


def _aviso_provisorio(nome_usuario, dias):
    """O bilhete que fica na tela depois de entrar em liberação temporária."""
    try:
        with ui.dialog() as dlg_p:
            with ui.card().classes("w-[480px] gap-2"):
                ui.label("Acesso liberado por enquanto").classes("text-h6")
                ui.label(f"Você tem {dias} dias para descobrir o seu número de "
                         f"contato na prefeitura e atualizar o cadastro. "
                         f"Depois disso o acesso será bloqueado.").classes(
                    "text-body2 text-grey-7")
                ui.label("Enquanto o acesso é temporário, seu nome aparece na "
                         "lista telefônica, mas sem número — a prefeitura "
                         "ainda não sabe como falar com você.").classes(
                    "text-caption text-grey-6")
                _botao_tema("Entendi", on_click=dlg_p.close)
        dlg_p.open()
    except Exception as e:
        lg = _login_erro_log()
        if lg:
            lg.exception(f"aviso provisório falhou: {e}")


def _dialogo_dados_pendentes(nome_usuario: str, ao_concluir=None):
    """Avisa que a folha de pagamento trouxe dado diferente do cadastro.

    A folha é atualizada todo mês e traz secretaria, departamento e cargo. O
    sistema NÃO sobrescreve o cadastro de quem já existe: marca a pendência e
    pergunta à própria pessoa. A pergunta é o ponto — setor tem dois donos
    possíveis (a folha e a pessoa), e só a pessoa sabe qual é o certo.

    Dá para recusar ("continua como está"), e isso também é resposta: a folha
    pode estar errada, e uma pessoa que discorda de um sistema tem razão para
    discordar.
    """
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd_usuarios
        info = _bd_usuarios.informacao_pendencia(nome_usuario)
        if not info.get("tem"):
            if ao_concluir:
                ao_concluir()
            return
        descricao = info.get("descricao") or "seus dados funcionais mudaram"
        dias = int(info.get("dias") or 0)
    except Exception as e:
        lg = _login_erro_log()
        if lg:
            lg.exception(f"dialogo de pendência: leitura falhou para "
                         f"{nome_usuario}: {e}")
        if ao_concluir:
            ao_concluir()
        return

    def _salvar(novo_depto: str, novo_cargo: str, unidade: str):
        """Grava o que a pessoa confirmou. Falhou, a pendência fica."""
        try:
            ok, msg = _bd_usuarios.confirmar_pendencia_dados(
                nome_usuario, nome_usuario, unidade=unidade or None,
                lotacao=novo_depto or None, cargo=novo_cargo or None)
            notificar(msg or ("Dados atualizados." if ok
                              else "Não foi possível atualizar."),
                      tipo="positive" if ok else "negative")
        except Exception as e:
            lg = _login_erro_log()
            if lg:
                lg.exception(f"diálogo de pendência: gravar falhou para "
                             f"{nome_usuario}: {e}")
            notificar("Não foi possível atualizar seus dados agora.",
                      tipo="negative")
        finally:
            if ao_concluir:
                ao_concluir()

    try:
        with ui.dialog() as dlg_d:
            with ui.card().classes("w-[560px] gap-3"):
                ui.label("A folha de pagamento mudou o seu cadastro").classes("text-h6")
                # Só a PRIMEIRA letra desce. `descricao.lower()` inteiro
                # quebraria o nome próprio do setor — "Obras" viraria "obras" —
                # e a pessoa lê o próprio departamento com letra minúscula
                # como se fosse erro de digitação do sistema.
                meio = descricao[:1].lower() + descricao[1:]
                ui.label(f"A folha de pagamento foi atualizada e {meio} Por isso "
                         f"o cadastro só muda com a sua confirmação — o sistema "
                         f"não sobrescreve o que está gravado por causa de um "
                         f"arquivo.").classes("text-body2 text-grey-7")
                if dias > 7:
                    ui.label(f"Esta pendência está aberta há {dias} dias. Se "
                             f"estiver correta, confirme; se não estiver, "
                             f"avise o DTI para corrigir a folha.").classes(
                        "text-caption text-orange-8")
                # O que o servidor responde: como é hoje, para ele escrever.
                # Em branco = mantém o que já está gravado, sem apagar.
                inp_unidade = ui.input("Secretaria").props("outlined dense") \
                    .classes("w-full").props("data-testid=pendencia-dados-unidade")
                inp_depto = ui.input("Departamento").props("outlined dense") \
                    .classes("w-full").props("data-testid=pendencia-dados-departamento")
                inp_cargo = ui.input("Cargo").props("outlined dense") \
                    .classes("w-full").props("data-testid=pendencia-dados-cargo")

                def _confirmar():
                    _salvar((inp_depto.value or "").strip(),
                            (inp_cargo.value or "").strip(),
                            (inp_unidade.value or "").strip())
                    dlg_d.close()

                def _manter():
                    try:
                        _bd_usuarios.confirmar_pendencia_dados(
                            nome_usuario, nome_usuario)
                        notificar("Cadastro mantido como estava. Avise o DTI "
                                  "se a folha estiver errada.", tipo="warning")
                    except Exception as e:
                        lg = _login_erro_log()
                        if lg:
                            lg.exception(f"diálogo de pendência: manter falhou "
                                         f"para {nome_usuario}: {e}")
                    finally:
                        dlg_d.close()
                        if ao_concluir:
                            ao_concluir()

                with ui.row().classes("w-full justify-end").style("gap: 0.5rem"):
                    _botao_tema("Está certo, confirmar", on_click=_confirmar) \
                        .props("data-testid=pendencia-dados-confirmar")
                    _botao_tema("Manter como está", on_click=_manter,
                                variante="secundario") \
                        .props("data-testid=pendencia-dados-manter")
        dlg_d.open()
    except Exception as e:
        lg = _login_erro_log()
        if lg:
            lg.exception(f"diálogo de pendência: abrir falhou para "
                         f"{nome_usuario}: {e}")
        if ao_concluir:
            ao_concluir()


def _primeiro_acesso(nome_usuario: str):
    """Encadeia os passos obrigatórios do primeiro acesso.

    Ordem: senha -> telefones. Não dá para pular a senha; e não dá para
    cadastrar telefone de quem ainda entra com a senha provisória
    `123456`, que todo servidor da prefeitura conhece. Cada passo só abre
    o próximo quando o anterior foi realmente concluído — um diálogo de
    senha que fecha sem trocar deixaria o telefone para trás, e o servidor
    entraria no sistema com a pendência e sem saber por quê."""
    def abrir_telefones(novo_nome=None):
        """Abre o cadastro de telefones se ainda estiver pendente.

        `novo_nome` vem dos diálogos de credenciais, em que o login muda de
        `master` para o nome escolhido — a pendência do telefone está no
        usuário NOVO, não no `master` que já saiu de cena.

        A pendência de DADOS vem DEPOIS da do telefone, e só se o telefone
        estiver resolvido. A ordem não é estética: são duas perguntas para a
        mesma pessoa, no mesmo minuto, e quem responde a segunda já não está
        mais ledindo o formulário da primeira."""
        try:
            from mod_gest_cad_usuario import bd_manipulador as _bd_usuarios
            alvo = novo_nome or nome_usuario
            if _bd_usuarios.telefone_pendente(alvo):
                _dialogo_telefones(alvo, ao_concluir=lambda: _abrir_dados(alvo))
                return
            _abrir_dados(alvo)
        except Exception as e:
            lg = _login_erro_log()
            if lg:
                lg.exception(
                    f"primeiro_acesso: falha ao verificar telefone de "
                    f"{novo_nome or nome_usuario}: {e}")

    def _abrir_dados(alvo):
        """A pendência de dados, quando existir, com o telefone já resolvido."""
        try:
            _dialogo_dados_pendentes(alvo)
        except Exception as e:
            lg = _login_erro_log()
            if lg:
                lg.exception(f"primeiro_acesso: falha ao verificar pendência "
                             f"de dados de {alvo}: {e}")

    # NÃO TENTA ABRIR OS DIÁLOGOS DE SENHA AQUI (30/09/2026).
    # Quem tem pendência nunca chega a este ponto: `pagina_restrita` já mandou
    # para `ROTA_TROCA_OBRIGATORIA` antes de montar o layout. Deixá-los aqui
    # daria a impressão de que a troca é aplicada sobre a página montada —
    # que é exatamente o furo que o usuário achou: clicou em "voltar" e navegou.
    # Aqui só sobra o que vem DEPOIS da troca: telefone e dados.
    try:
        abrir_telefones()
    except Exception as e:
        lg = _login_erro_log()
        if lg:
            lg.exception(
                f"primeiro_acesso: falha ao montar o fluxo de {nome_usuario}: {e}")


def _obter_cor_principal():
    """Reads the system primary color from config, falling back to the palette.

    Lê a cor principal do sistema em `tb_config` (chave `cor_principal`);
    em ausência do valor ou falha de conexão usa `ui_comum.CORES["primaria"]`.
    """
    from mod_skyrover.bd_conexao import get_connection
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT valor FROM tb_config WHERE chave='cor_principal'")
        row = cur.fetchone()
        conn.close()
        return row[0] if row else ui_comum.CORES["primaria"]
    except Exception:
        return ui_comum.CORES["primaria"]


def _obter_versao():
    from mod_skyrover.bd_conexao import get_connection
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT valor FROM tb_config WHERE chave='versao_sistema'")
        row = cur.fetchone()
        conn.close()
        return row[0] if row else "1.0"
    except Exception:
        return "1.0"


def _obter_versao_modulo(chave_modulo):
    """Versão individual do módulo (chave 'versao_modulo:<chave>' em tb_config).

    Formato 1.0.AAMMDD, no mesmo estilo da versão do sistema. Se o módulo ainda
    não tem versão registrada, retorna a padrão '1.0'.
    """
    from mod_skyrover.bd_conexao import get_connection
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT valor FROM tb_config WHERE chave=?",
                    (f"versao_modulo:{chave_modulo}",))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else "1.0"
    except Exception:
        return "1.0"


def _parse_versao(v: str):
    """Parse 'X.Y.AAMMDD' ou 'X.Y' -> (major, minor, patch)."""
    parts = v.split(".")
    major = int(parts[0]) if parts else 1
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = parts[2] if len(parts) > 2 else ""
    return major, minor, patch


def _mesclar_patch(patch_sis: str, patch_mod: str) -> str:
    """Mescla patches AAMMDD conforme regras: oculta ano/mês/dia iguais."""
    if not patch_sis or not patch_mod or patch_sis == patch_mod:
        return patch_sis
    aa1, mm1, dd1 = patch_sis[:2], patch_sis[2:4], patch_sis[4:6]
    aa2, mm2, dd2 = patch_mod[:2], patch_mod[2:4], patch_mod[4:6]
    if aa1 == aa2:
        if mm1 == mm2:
            return f"{patch_sis}.{dd2}"
        return f"{patch_sis}.{mm2}{dd2}"
    return f"{patch_sis}.{patch_mod}"


def _formatar_versao_rodape(versao_sistema: str, versao_modulo: str = None):
    """Retorna sempre uma única string com a versão mesclada para exibição.

    Formato: v{major}.{minor}.{patch_sis}[.{parte_mod}]
    - Sem módulo: v{versao_sistema}
    - major.minor iguais: mescla ocultando AAMMDD iguais (v1.0.260829.28,
      v1.0.260829.0717, v1.0.260828.250412)
    - major.minor diferentes: mostra ambos separados por ' · '
    """
    if not versao_modulo:
        return f"v{versao_sistema}"

    major_sis, minor_sis, patch_sis = _parse_versao(versao_sistema)
    major_mod, minor_mod, patch_mod = _parse_versao(versao_modulo)

    if major_sis != major_mod or minor_sis != minor_mod:
        return f"v{versao_sistema} · v{versao_modulo}"

    base = f"v{major_sis}.{minor_sis}"
    if patch_sis and patch_mod:
        mesclado = _mesclar_patch(patch_sis, patch_mod)
        return f"{base}.{mesclado}"
    if patch_sis or patch_mod:
        return f"{base}.{patch_sis or patch_mod}"
    return base
