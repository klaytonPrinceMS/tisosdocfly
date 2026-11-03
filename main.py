"""T! SOS DocFly — entrypoint NiceGUI (boot, rotas centrais e ligação dos módulos).

Ponto de entrada da aplicação: inicializa os bancos, a observabilidade e a
documentação; define as rotas centrais (login, dashboard `/`, configurações
`/configuracoes`, usuários `/users` e administração `/admin/{chave_modulo}`).

Layout (AGENTS.md §2): `main.py` fica na RAIZ e o código dos módulos vive em
`src/mod_*/`. `DIR_PROJETO` é a raiz (bancos, logs, site, docs) e `DIR_SRC` é
o que o Python importa; `DIR_ASSETS` guarda CSS/favicon/imagens.
"""
import os
import sys

# ================== LAYOUT src/ ==================
DIR_PROJETO = os.path.dirname(os.path.abspath(__file__))
DIR_SRC = os.path.join(DIR_PROJETO, "src")
DIR_ASSETS = os.path.join(DIR_SRC, "assets")
for _dir in (DIR_PROJETO, DIR_SRC):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

from nicegui import app, ui
from fastapi import Request

# Patch de timers cujo slot já foi deletado (evita warning no navegador).
from mod_tisosdocfly.nicegui_patch import aplicar as _aplicar_nicegui_patch
_aplicar_nicegui_patch()

from mod_tisosdocfly import autenticacao, observabilidade
from mod_tisosdocfly.bd_conexao import get_config
from mod_tisosdocfly.tema_modulo import notificar

# Configuração de boot: sem assistente interativo. O backend é o persistido
# (SQLite por padrão; PostgreSQL quando `banco_tipo=postgres`).
ESPERA_DOCS = os.environ.get("TISOSDOCFLY_DOCS_ATIVO", "1") != "0"
PORTA = int(os.environ.get("TISOSDOCFLY_PORTA", "0") or 0)
HOST = os.environ.get("TISOSDOCFLY_HOST", "127.0.0.1")
_HTTPS_ONLY = os.environ.get("TISOSDOCFLY_HTTPS_ONLY", "") == "1"
_SEGREDO = (os.environ.get("TISOSDOCFLY_STORAGE_SECRET", "")
            or "tisosdocfly-secret-2026-mude-isto")


def _cfg_porta() -> int:
    """Porta do site: env > tb_config > 8080."""
    if PORTA:
        return PORTA
    try:
        return int(get_config("porta_site", "8080") or 8080)
    except Exception:
        return 8080


# ================== LOGIN ==================
@ui.page("/login")
def page_login(request: Request):
    """Monta a tela de login (com o alternador de 4 padrões visuais).

    Lê os textos e cores configuráveis (`texto_login_titulo`,
    `texto_login_subtitulo`, `texto_login_hint`, `icone_sistema`,
    `cor_principal`, `cor_fundo`) e escolhe o padrão visual pelo query param
    `?estilo=`. Mantém os `data-testid` de produção e o mesmo `tentar_login`.

    EN: Builds the login page; the 4-style switcher is a temporary prototype.
    """
    try:
        from mod_tisosdocfly.bd_conexao import get_config
        cor = get_config("cor_principal", "#000000") or "#000000"
        icone = (get_config("icone_sistema", "hub") or "hub").strip()
        titulo_login = get_config("texto_login_titulo", "T! SOS DOCFLY Básica") or "T! SOS DOCFLY Básica"
        subtitulo = get_config("texto_login_subtitulo", "Acesso restrito a usuários autorizados")
        hint = get_config("texto_login_hint",
                          "Novos usuários? Procure o DTI para realizar o seu cadastro.")
        ui.colors(primary=cor)
        fundo_login = get_config("cor_fundo", "#EEEEEE") or "#EEEEEE"

        # ===== LOGIN SEMPRE NO PADRÃO DO WHATSAPP (decisão do responsável) =====
        # O login é FIXO no estilo `verde`, por decisão do responsável: ele não
        # segue a preferência do usuário nem aceita `?estilo=`, e NEM a cor
        # configurada pelo administrador.
        #
        # Por isso `cor_principal` e `cor_fundo` são passados VAZIOS. Passá-los
        # preenchidos foi o que deixou o login preto em 30/09/2026: o `aplicar`
        # via a cor do admin quando o padrão pedido colidia com o padrão do
        # admin, e `#000000` cobria o teal do WhatsApp. Quem pede um estilo
        # CONCRETO não recebe cor de administrador — essa é a regra agora.
        from mod_tisosdocfly import preview_estilos as _pv
        padrao_visual = _pv.PADRAO_LOGIN
        paleta = _pv.aplicar(padrao_visual)
        fundo_login = (paleta or {}).get("fundo") or fundo_login
        # ===== FIM =====

        ui.query("body").style(f"background:{fundo_login}")
        try:
            ui.query(".q-page").style(f"background-color:{fundo_login}")
        except Exception:
            pass
        import json as _json
        ui.run_javascript(f"document.title = {_json.dumps(titulo_login)}")
        # favicon com cache-busting: ?v muda quando o .ico é trocado
        from mod_tisosdocfly.bd_conexao import favicon_versao
        ui.add_head_html(
            f'<link rel="icon" type="image/x-icon" href="/favicon.ico?v={favicon_versao()}">')

        # Se já logado, vai direto pro dashboard. O estilo NÃO vai na URL: ele
        # mora no cookie do navegador e é resolvido na renderização da Home.
        if app.storage.user.get("usuario"):
            ui.navigate.to("/")
            return

        def _campos():
            """Cria os campos e o botão de login (data-testid de produção).

            Recebe a marcação do layout do `preview_estilos`; o conteúdo é
            idêntico ao original — só a classe `preview-campo`/`preview-entrar`
            foi somada para o CSS do padrão dar forma aos componentes Quasar.
            """
            try:
                usuario = ui.input("Usuário", placeholder="master").props("outlined dense").classes("w-full preview-campo") \
                    .props('data-testid=login-usuario')
                senha = ui.input("Senha", password=True, password_toggle_button=True,
                                 placeholder="master").props(
                    "outlined dense"
                ).classes("w-full preview-campo") \
                    .props('data-testid=login-senha')

                # Captcha local + 2o fator TOTP (24/10/2026, pos-pentest).
                # Criados ocultos: o captcha so aparece quando o IP acumula
                # falhas (`captcha_apos_falhas`, padrao 3); o codigo TOTP so
                # aparece para quem ativou o segundo fator. Elemento oculto
                # nao quebra o QA (preenche por indice/testid quando visivel).
                import base64 as _b64
                captcha_caixa = {"png": b"", "pergunta": ""}
                img_captcha = ui.image("").props(
                    'data-testid=login-captcha-imagem')
                img_captcha.visible = False
                campo_captcha = ui.input(
                    "Quanto e? (anti-robo)",
                    placeholder="resultado da conta").props(
                    "outlined dense").classes("w-full preview-campo") \
                    .props('data-testid=login-captcha-resposta')
                campo_captcha.visible = False
                campo_totp = ui.input(
                    "Codigo do app (6 digitos)",
                    placeholder="000000").props(
                    "outlined dense").classes("w-full preview-campo") \
                    .props('data-testid=login-totp-codigo')
                campo_totp.visible = False
                pendente_totp = {}

                def _mostrar_captcha(ip):
                    """Gera o desafio para o IP e exibe. Falha = segue sem."""
                    try:
                        from mod_tisosdocfly import captcha as _cap
                        png, pergunta = _cap.gerar_para(ip)
                        if not png:
                            return
                        captcha_caixa["png"] = png
                        captcha_caixa["pergunta"] = pergunta
                        img_captcha.set_source(
                            "data:image/png;base64," + _b64.b64encode(
                                png).decode())
                        try:
                            img_captcha.props(
                                f'alt="Captcha: {pergunta}"')
                        except Exception:
                            pass
                        img_captcha.visible = True
                        campo_captcha.visible = True
                        campo_captcha.value = ""
                    except Exception:
                        pass

                def _precisa_captcha(ip):
                    try:
                        from mod_tisosdocfly import captcha as _cap
                        from mod_tisosdocfly import autenticacao as _a2
                        return (_a2._falhas_ip_recentes(ip)
                                >= _cap.limite_falhas())
                    except Exception:
                        return False

                def _ip_cliente() -> str:
                    """IP de quem clicou em Entrar, ou "" se não der.

                    O NiceGUI 3 expõe em `context.client.request`; sem isso
                    o rate limit por IP vira zero e o fluxo segue igual —
                    IP desconhecido nunca pode travar login legítimo.
                    """
                    try:
                        from nicegui import context as _ctx
                        _req = getattr(_ctx, "request", None)
                        if _req is None:
                            _req = getattr(getattr(_ctx, "client", None),
                                           "request", None)
                        _cli = getattr(_req, "client", None)
                        return str(getattr(_cli, "host", "") or "").strip()
                    except Exception:
                        return ""

                def tentar_login():
                    try:
                        # Segundo passo do TOTP: a senha ja passou e o `nome`
                        # esta guardado em `pendente_totp` — agora e so o
                        # codigo de 6 digitos do app do celular (offline).
                        if pendente_totp.get("nome"):
                            try:
                                from mod_tisosdocfly import totp as _totp2
                                _seg = _totp2._obter(pendente_totp["nome"])
                                if _totp2.verificar(
                                        _seg, campo_totp.value or ""):
                                    _nome2 = pendente_totp["nome"]
                                    _perfil2 = pendente_totp["perfil"]
                                    _sessao2 = autenticacao.registrar_login(
                                        _nome2, "sistema")
                                    try:
                                        from mod_tisosdocfly.bd_conexao import incrementar_contador_acessos as _inc2
                                        _inc2()
                                    except Exception:
                                        pass
                                    try:
                                        autenticacao.zerar_falhas_ip(
                                            _ip_cliente())
                                    except Exception:
                                        pass
                                    import time as _t2
                                    app.storage.user["usuario"] = {
                                        "nome": _nome2, "perfil": _perfil2,
                                        "sessao": _sessao2,
                                        "ultimo_acesso": _t2.time()}
                                    pendente_totp.clear()
                                    notificar(f"Bem-vindo(a), {_nome2}!",
                                              type="positive")
                                    ui.navigate.to("/")
                                    return
                            except Exception:
                                pass
                            try:
                                _espera2 = autenticacao.registrar_falha_ip(
                                    _ip_cliente())
                                if _espera2 > 0:
                                    import time as _time2
                                    _time2.sleep(min(float(_espera2), 5.0))
                            except Exception:
                                pass
                            notificar("Código inválido. Tente de novo.",
                                      type="negative", position="top")
                            return
                        # `nome` é o login CANÔNICO devolvido por `autenticar`,
                        # não o que foi digitado (04/10/2026). A pessoa pode
                        # entrar por qualquer uma das matrículas que a folha
                        # registra como dela, e o que vai para a sessão precisa
                        # ser a conta — uma sessão aberta com a matrícula
                        # secundária é uma sessão de um usuário que não existe,
                        # e o efeito é o servidor aceitar a senha e devolver
                        # a pessoa para o login sem dizer por quê.
                        ok, msg, nome = autenticacao.autenticar(
                            usuario.value or "", senha.value or "",
                            com_login_canonico=True)
                        # Observabilidade: registra a tentativa de login (métrica OTel)
                        try:
                            from mod_tisosdocfly.otel_integracao import registrar_login_observabilidade
                            registrar_login_observabilidade(nome or usuario.value or "", ok)
                        except Exception:
                            pass
                        # Captcha local (24/10/2026): com falhas
                        # acumuladas no IP, a resposta tem que bater ANTES
                        # da senha — robo que chuta senha nunca chega nela.
                        # Legitimo que errou o captcha ganha outro desafio.
                        if _precisa_captcha(_ip_cliente()):
                            try:
                                from mod_tisosdocfly import captcha as _cap3
                                if not _cap3.verificar(
                                        _ip_cliente(),
                                        campo_captcha.value or ""):
                                    _mostrar_captcha(_ip_cliente())
                                    notificar("Confira o resultado da conta "
                                              "e tente de novo.",
                                              type="negative",
                                              position="top")
                                    return
                                img_captcha.visible = False
                                campo_captcha.visible = False
                            except Exception:
                                pass
                        if not ok:
                            # Item 5 do pós-pentest (24/10/2026): a espera é
                            # REAL — dorme antes de responder, no teto de 5 s.
                            # Sem isso o "Aguarde N segundos" era só texto e a
                            # rajada passava sem custo. Handler sync roda em
                            # thread do executor, então o sleep não trava a
                            # interface de quem está usando.
                            try:
                                _espera = autenticacao.registrar_falha_ip(
                                    _ip_cliente())
                                if _espera > 0:
                                    import time as _time
                                    _time.sleep(min(float(_espera), 5.0))
                            except Exception:
                                pass
                            notificar(msg, type="negative", position="top")
                            return
                        perfil = msg  # autenticar retorna o perfil na msg quando ok
                        # Segundo fator TOTP (24/10/2026): quem ativou na
                        # propria conta ("Meu perfil") para aqui — o codigo
                        # do app decide. Sem codigo certo, sem sessao: o
                        # `registrar_login` so roda depois dele.
                        try:
                            from mod_tisosdocfly import totp as _totp3
                            if _totp3.tem_segredo(nome):
                                pendente_totp["nome"] = nome
                                pendente_totp["perfil"] = perfil
                                campo_totp.visible = True
                                campo_totp.value = ""
                                notificar("Digite o código do app "
                                          "autenticador.", type="info")
                                return
                        except Exception:
                            pass
                        # hash amarra o cookie do navegador à linha da sessão no banco:
                        # encerrar a sessão pelo admin derruba este navegador no próximo request
                        sessao = autenticacao.registrar_login(nome, "sistema")
                        # Contador padronizado — só logins, nunca navegações/refreshs
                        try:
                            from mod_tisosdocfly.bd_conexao import incrementar_contador_acessos
                            incrementar_contador_acessos()
                        except Exception:
                            pass
                        try:
                            autenticacao.zerar_falhas_ip(_ip_cliente())
                        except Exception:
                            pass
                        import time as _tlogin
                        app.storage.user["usuario"] = {"nome": nome, "perfil": perfil, "sessao": sessao, "ultimo_acesso": _tlogin.time()}
                        notificar(f"Bem-vindo(a), {nome}!", type="positive")
                        # A Home lê o estilo do cookie do navegador; não é
                        # preciso (nem cabe) levar o padrão pela URL.
                        ui.navigate.to("/")
                    except Exception as e:
                        observabilidade.get_logger("tisosdocfly").exception(
                            "tentar_login: falha ao autenticar: %s", e)
                        notificar("Erro ao tentar entrar. Tente novamente.", tipo="error")

                with ui.column().classes("w-full mt-4").style("gap: .5rem"):
                    from mod_tisosdocfly.tema_modulo import botao as _botao_tema
                    _botao_tema("Entrar", on_click=tentar_login, extra_classes="w-full preview-entrar") \
                        .props('data-testid=login-entrar')

                senha.on("keydown.enter", tentar_login)
            except Exception as e:
                observabilidade.get_logger("tisosdocfly").exception(
                    "_campos: falha ao montar os campos de login: %s", e)
                notificar("Erro ao montar o formulário de login.", tipo="error")

        _pv.tela_login(padrao_visual, icone=icone, titulo=titulo_login,
                       subtitulo=subtitulo, hint=hint, paleta=paleta,
                       campos=_campos,
                       # 05/10/2026: o cartão branco passa a trazer o nome do
                       # produto CENTRALIZADO, e o painel teal segue com o nome
                       # completo (`titulo_login`). São duas coisas diferentes de
                       # propósito: no painel é o título do produto; no cartão é
                       # a identificação mínima, e ela existe porque no
                       # dispositivo em que o fundo verde não aparece a tela
                       # ficaria uma coluna branca sem nome nenhum.
                       #
                       # "T! SOS DOCFLY" é fixo aqui, e não o `titulo_login`
                       # configurável, porque o responsável pediu esse texto
                       # exato. Para deixar configurável, é uma linha: troque
                       # por `get_config("texto_login_marca", "T! SOS DOCFLY")`.
                       titulo_caixa="T! SOS DOCFLY")
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_login: erro ao renderizar a página de login: %s", e)
        notificar("Erro ao carregar a página de login.", tipo="error")



# ================== DASHBOARD ==================
@ui.page("/")
def page_dashboard(request: Request):
    """Home: saudação + cards dos módulos liberados para o usuário."""
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Início")
        if not user:
            return
        nome = user["nome"]
        perfil = user.get("perfil", "")

        with ui.column().classes("w-full").style("gap: 1.25rem"):
            try:
                from mod_tisosdocfly.bd_manipulador import nome_de_tratamento
                _tratamento = nome_de_tratamento(nome)
            except Exception:
                _tratamento = nome
            ui.label(f"Olá, {_tratamento}").classes("text-h5")
            ui.label("Bem-vindo(a) ao T! SOS DocFly — laudos de voo.").classes(
                "text-subtitle1 text-grey-7")

            modulos = autenticacao.modulos_do_usuario(nome)
            if not modulos:
                with ui.card().classes("w-full"):
                    ui.label("Nenhum módulo liberado para a sua conta.") \
                        .classes("text-body1")
                    ui.label("Procure o administrador para solicitar acesso.") \
                        .classes("text-caption text-grey-7")
            else:
                with ui.row().classes("w-full").style("gap: 1rem"):
                    for chave, rotulo, icone, rota, ativa in modulos:
                        with ui.card().classes("cursor-pointer").style(
                                "min-width: 220px; max-width: 320px"):
                            with ui.row().classes("items-center").style("gap: .75rem"):
                                ui.icon(icone).classes("text-3xl")
                                with ui.column().style("gap: 0"):
                                    ui.label(rotulo).classes("text-subtitle1")
                                    ui.label(
                                        "Ativo" if ativa else "Desligado"
                                    ).classes(
                                        "text-caption "
                                        + ("text-positive" if ativa
                                           else "text-warning"))
                            ui.label(
                                "Abrir módulo" if ativa
                                else "Aguarda liberação do administrador."
                            ).classes("text-caption text-grey-7")
                            if ativa:
                                ui.on("click", lambda _=None, r=rota: (
                                    ui.navigate.to(r)
                                    if r and r != "#" else None))

            # Núcleo: voos e laudos. Funcionalidade do núcleo (não é módulo de
            # negócio), por isso não entra em MODULOS_SISTEMA nem em
            # tb_modulos — mas precisa aparecer na home para todo usuário.
            with ui.card().classes("cursor-pointer").style(
                    "min-width: 220px; max-width: 320px") \
                    .props("data-testid=home-card-voos"):
                with ui.row().classes("items-center").style("gap: .75rem"):
                    ui.icon("flight_takeoff").classes("text-3xl")
                    with ui.column().style("gap: 0"):
                        ui.label("Voos e laudos").classes("text-subtitle1")
                        ui.label("Núcleo · Onda 1").classes(
                            "text-caption text-positive")
                ui.label(
                    "Cliente, propriedade, voo, upload de fotos/vídeos e "
                    "laudo base.").classes("text-caption text-grey-7")
                ui.on("click", lambda _=None: ui.navigate.to("/voos"))

            with ui.card().classes("cursor-pointer").style(
                    "min-width: 220px; max-width: 320px") \
                    .props("data-testid=home-card-riscos"):
                with ui.row().classes("items-center").style("gap: .75rem"):
                    ui.icon("monitor_heart").classes("text-3xl")
                    with ui.column().style("gap: 0"):
                        ui.label("Painel de riscos").classes("text-subtitle1")
                        ui.label("Municipal · corporativo").classes(
                            "text-caption text-positive")
                ui.label(
                    "Defesa civil, ambiental, obras, segurança e inspeção "
                    "em um só resumo."
                ).classes("text-caption text-grey-7")
                ui.on("click", lambda _=None: ui.navigate.to("/riscos"))

            ui.label(f"Perfil: {perfil or 'comum'}").classes(
                "text-caption text-grey-6")
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_dashboard: erro: %s", e)
        notificar("Erro ao carregar a página inicial.", tipo="error")


# ================== MÓDULO: USUÁRIOS ==================
@ui.page("/users")
def page_users():
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Gestão de Usuários", chave_modulo="usuarios")
        if not user:
            return
        from mod_gest_cad_usuario.telas import mostrar_tela
        mostrar_tela(user["nome"], user.get("perfil", ""))
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_users: erro: %s", e)
        notificar("Erro ao carregar a Gestão de Usuários.", tipo="error")


# ================== VOOS E LAUDOS (NÚCLEO) ==================
@ui.page("/voos")
def page_voos():
    """Onda 1 do núcleo: cliente → propriedade → voo → upload → laudo."""
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Voos e laudos")
        if not user:
            return
        from mod_tisosdocfly.telas_voos import mostrar_tela
        mostrar_tela(user["nome"], user.get("perfil", ""))
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_voos: erro: %s", e)
        notificar("Erro ao carregar a tela de voos.", tipo="error")


# ================== MÓDULOS DE NEGÓCIO ==================
@ui.page("/agro")
def page_agro():
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Agropecuário", chave_modulo="agro")
        if not user:
            return
        from mod_agro.telas import mostrar_tela
        mostrar_tela(user["nome"], user.get("perfil", ""))
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_agro: erro: %s", e)
        notificar("Erro ao carregar o módulo Agropecuário.", tipo="error")


@ui.page("/vistoria-predial")
def page_vistoria_predial():
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Vistoria Predial",
                               chave_modulo="vistoria_predial")
        if not user:
            return
        from mod_vistoria_predial.telas import mostrar_tela
        mostrar_tela(user["nome"], user.get("perfil", ""))
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_vistoria_predial: erro: %s", e)
        notificar("Erro ao carregar o módulo Vistoria Predial.",
                  tipo="error")


@ui.page("/seguranca")
def page_seguranca():
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Segurança Pública", chave_modulo="seguranca")
        if not user:
            return
        from mod_seguranca.telas import mostrar_tela
        mostrar_tela(user["nome"], user.get("perfil", ""))
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_seguranca: erro: %s", e)
        notificar("Erro ao carregar o módulo Segurança Pública.",
                  tipo="error")


@ui.page("/ambiental")
def page_ambiental():
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Ambiental", chave_modulo="ambiental")
        if not user:
            return
        from mod_ambiental.telas import mostrar_tela
        mostrar_tela(user["nome"], user.get("perfil", ""))
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_ambiental: erro: %s", e)
        notificar("Erro ao carregar o módulo Ambiental.", tipo="error")


@ui.page("/obras")
def page_obras():
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Obras", chave_modulo="obras")
        if not user:
            return
        from mod_obras.telas import mostrar_tela
        mostrar_tela(user["nome"], user.get("perfil", ""))
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_obras: erro: %s", e)
        notificar("Erro ao carregar o módulo Obras.", tipo="error")


@ui.page("/mapeamento")
def page_mapeamento():
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Mapeamento", chave_modulo="mapeamento")
        if not user:
            return
        from mod_mapeamento.telas import mostrar_tela
        mostrar_tela(user["nome"], user.get("perfil", ""))
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_mapeamento: erro: %s", e)
        notificar("Erro ao carregar o módulo Mapeamento.", tipo="error")


@ui.page("/defesa-civil")
def page_defesa_civil():
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Defesa Civil", chave_modulo="defesa_civil")
        if not user:
            return
        from mod_defesa_civil.telas import mostrar_tela
        mostrar_tela(user["nome"], user.get("perfil", ""))
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_defesa_civil: erro: %s", e)
        notificar("Erro ao carregar o módulo Defesa Civil.", tipo="error")


@ui.page("/inspecao-industrial")
def page_inspecao_industrial():
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Inspeção Industrial",
                               chave_modulo="inspecao_industrial")
        if not user:
            return
        from mod_inspecao_industrial.telas import mostrar_tela
        mostrar_tela(user["nome"], user.get("perfil", ""))
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_inspecao_industrial: erro: %s", e)
        notificar("Erro ao carregar o módulo Inspeção Industrial.",
                  tipo="error")


@ui.page("/perimetro")
def page_perimetro():
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Perímetro e Segurança",
                               chave_modulo="perimetro")
        if not user:
            return
        from mod_perimetro.telas import mostrar_tela
        mostrar_tela(user["nome"], user.get("perfil", ""))
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_perimetro: erro: %s", e)
        notificar("Erro ao carregar o módulo Perímetro.", tipo="error")


@ui.page("/eventos")
def page_eventos():
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Eventos", chave_modulo="eventos")
        if not user:
            return
        from mod_eventos.telas import mostrar_tela
        mostrar_tela(user["nome"], user.get("perfil", ""))
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_eventos: erro: %s", e)
        notificar("Erro ao carregar o módulo Eventos.", tipo="error")


# ================== PAINEL DE RISCOS ==================
@ui.page("/riscos")
def page_riscos():
    """Painel gerencial de riscos municipal/corporativo."""
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Painel de Riscos")
        if not user:
            return
        from mod_tisosdocfly.painel_riscos import coletar
        dados = coletar()
        with ui.column().classes("w-full").style("gap: 1.25rem"):
            with ui.row().classes("w-full items-center"):
                with ui.column().style("gap: 0"):
                    ui.label("Painel de Riscos").classes("text-h5")
                    ui.label(
                        "Monitoramento agregado de defesa civil, ambiental, "
                        "obras, segurança e inspeção industrial."
                    ).classes("text-caption text-grey-7")
            with ui.row().classes("w-full").style("gap: 1rem"):
                for rotulo, valor, icone in (
                        ("Análises", dados["total_analises"], "analytics"),
                        ("Ocorrências", dados["total_ocorrencias"],
                         "warning"),
                        ("Revisão pendente", dados["pendentes_revisao"],
                         "fact_check")):
                    with ui.card().style("min-width: 200px; flex: 1 1 200px"):
                        with ui.row().classes("items-center").style("gap: .5rem"):
                            ui.icon(icone).classes("text-2xl")
                            with ui.column().style("gap: 0"):
                                ui.label(str(valor)).classes("text-h5")
                                ui.label(rotulo).classes(
                                    "text-caption text-grey-7")
            with ui.row().classes("w-full").style("gap: 1rem"):
                for item in dados["modulos"]:
                    with ui.card().style(
                            "min-width: 220px; flex: 1 1 220px"):
                        with ui.row().classes("items-center").style("gap: .5rem"):
                            ui.icon(item["icone"]).classes("text-3xl")
                            with ui.column().style("gap: 0"):
                                ui.label(item["nome"]).classes("text-subtitle1")
                                ui.label(
                                    f"{item['total']} análise(s) · "
                                    f"{item['ocorrencias']} ocorrência(s)"
                                ).classes("text-caption text-grey-7")
                        if item["pendentes_revisao"]:
                            ui.badge(
                                f"{item['pendentes_revisao']} revisão pendente"
                            ).props("color=orange")
                        ui.link("Abrir módulo", item["rota"])
            ui.label(
                "Agregação por API pública de cada módulo; nenhum banco é "
                "consultado por outro módulo."
            ).classes("text-caption text-grey-6")
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_riscos: erro: %s", e)
        notificar("Erro ao carregar o Painel de Riscos.", tipo="error")


# ================== CONFIGURAÇÕES ==================
@ui.page("/configuracoes")
def page_configuracoes():
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        user = pagina_restrita("Administração")
        if not user:
            return
        from mod_tisosdocfly.tela_configuracoes import mostrar_tela
        mostrar_tela(user["nome"], user.get("perfil", ""))
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_configuracoes: erro: %s", e)
        notificar("Erro ao carregar as Configurações.", tipo="error")


# ================== TROCA OBRIGATÓRIA ==================
@ui.page("/troca-obrigatoria")
def page_troca_obrigatoria():
    try:
        from mod_tisosdocfly.telas import tela_troca_obrigatoria
        tela_troca_obrigatoria()
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_troca_obrigatoria: erro: %s", e)
        notificar("Erro ao abrir a troca de senha — recarregue a página.",
                  tipo="error")


# ================== ADMINISTRAÇÃO POR MÓDULO ==================
@ui.page("/admin/{chave_modulo}")
def page_admin_modulo(chave_modulo: str):
    """Painel de administração standalone do módulo."""
    try:
        from mod_tisosdocfly.telas import pagina_restrita
        nome_modulo = (autenticacao.nome_do_modulo(chave_modulo)
                       or "Administração")
        user = pagina_restrita(nome_modulo, chave_modulo=chave_modulo)
        if not user:
            return
        perfil = user.get("perfil", "")
        nome = user["nome"]

        if chave_modulo == "usuarios":
            eh_admin = (perfil == "administrador_geral"
                        or autenticacao.eh_admin_do_modulo(nome, "usuarios"))
            from mod_tisosdocfly.tema_modulo import ler_tema
            tema = ler_tema("usuarios", cor_botao="#000000",
                            cor_texto_botao="#FFFFFF")
            ui.colors(primary=tema["cor_botao"])
            if not eh_admin:
                notificar("Acesso restrito a administradores",
                          tipo="negative")
                ui.navigate.to("/users")
                return
            from mod_gest_cad_usuario.telas_administracao import (
                mostrar_administracao,
            )
            with ui.column().classes("w-full"):
                mostrar_administracao(nome)
        elif chave_modulo in (
                "agro", "vistoria_predial", "seguranca", "ambiental",
                "obras", "mapeamento", "defesa_civil",
                "inspecao_industrial", "eventos", "perimetro"):
            _mapa = {
                "agro": ("mod_agro", "/agro", "#2E7D32",
                         "Agropecuário"),
                "vistoria_predial": ("mod_vistoria_predial",
                                     "/vistoria-predial", "#1565C0",
                                     "Vistoria Predial"),
                "seguranca": ("mod_seguranca", "/seguranca", "#455A64",
                              "Segurança Pública"),
                "ambiental": ("mod_ambiental", "/ambiental", "#1B5E20",
                              "Ambiental"),
                "obras": ("mod_obras", "/obras", "#EF6C00", "Obras"),
                "mapeamento": ("mod_mapeamento", "/mapeamento", "#6A1B9A",
                               "Mapeamento"),
                "defesa_civil": ("mod_defesa_civil", "/defesa-civil",
                                 "#C62828", "Defesa Civil"),
                "inspecao_industrial": ("mod_inspecao_industrial",
                                        "/inspecao-industrial", "#37474F",
                                        "Inspeção Industrial"),
                "eventos": ("mod_eventos", "/eventos", "#00838F",
                            "Eventos"),
                "perimetro": ("mod_perimetro", "/perimetro", "#37474F",
                              "Perímetro e Segurança"),
            }
            _pacote, _rota, _cor, _nome = _mapa[chave_modulo]
            eh_admin = (perfil == "administrador_geral"
                        or autenticacao.eh_admin_do_modulo(
                            nome, chave_modulo))
            from mod_tisosdocfly.tema_modulo import ler_tema
            tema = ler_tema(chave_modulo, cor_botao=_cor,
                            cor_texto_botao="#FFFFFF")
            ui.colors(primary=tema["cor_botao"])
            if not eh_admin:
                notificar("Acesso restrito a administradores",
                          tipo="negative")
                ui.navigate.to(_rota)
                return
            from importlib import import_module
            _adm = import_module(
                f"{_pacote}.telas_administracao")
            with ui.column().classes("w-full"):
                _adm.mostrar_administracao(nome)
        else:
            notificar("Módulo sem painel de administração.",
                      tipo="warning")
            ui.navigate.to("/")
    except Exception as e:
        observabilidade.get_logger("tisosdocfly").exception(
            "page_admin_modulo: erro: %s", e)
        notificar("Erro ao carregar a administração do módulo.",
                  tipo="error")


# ================== DOCUMENTAÇÃO ==================
def _montar_documentacao():
    """Constrói e monta /documentacao (fail-soft)."""
    if not ESPERA_DOCS:
        return
    try:
        from mod_tisosdocfly.documentacao import (
            construir_e_montar_documentacao,
        )
        construir_e_montar_documentacao(logar=True)
    except Exception as e:
        try:
            observabilidade.get_logger("tisosdocfly").warning(
                "documentação não montada (fail-soft): %s", e)
        except Exception:
            pass


# ================== BOOT ==================
def _garantir_favicon():
    import shutil
    import nicegui as _nicegui_pkg
    destino = os.path.join(DIR_ASSETS, "favicon_atual.ico")
    origem = os.path.join(os.path.dirname(_nicegui_pkg.__file__),
                          "static", "favicon.ico")
    if not os.path.exists(destino):
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        try:
            shutil.copy2(origem, destino)
        except Exception:
            pass
    return destino


observabilidade.configurar()
try:
    observabilidade.instalar_excepthook()
    observabilidade.registrar_excecoes_nicegui(app)
except Exception as _e_obs:
    print(f"[observabilidade] aviso: {_e_obs}")

from mod_tisosdocfly.bd_criador import inicializar_bancos
inicializar_bancos()

FAVICON_ATUAL = _garantir_favicon()

# ================== CSS DOS PADRÕES VISUAIS ==================
# O `<link>` do login aponta para `/assets/css/preview-estilos-v1.css`.
# Sem este mount o arquivo responde 404 e NENHUMA regra do padrão WhatsApp é
# aplicada — o sintoma é a tela "sem graça", mesmo com o código do login certo.
try:
    from mod_tisosdocfly import preview_estilos as _pv_rotas
    _pv_rotas.montar_rotas_static()
    _pv_rotas.montar_rota_troca()
except Exception as _e_pv:
    print(f"[preview] aviso: CSS/rota do padrão visual não montados: {_e_pv}")

# CSS opcional dos frameworks (Bulma/DaisyUI/Pico/Picnic) em /css/frameworks.
try:
    from mod_tisosdocfly import tema_css
    tema_css.montar_rotas_static()
except Exception as _e_css:
    print(f"[css] aviso: /css/frameworks não montado: {_e_css}")

# ================== LAUDOS PDF ==================
# O pipeline grava em `src/mod_tisosdocfly/laudos/` (ou TISOSDOCFLY_DIR_LAUDOS).
# A rota autenticada do diálogo de voos aponta para `/laudos/<arquivo>`.
try:
    from mod_tisosdocfly import voos as _voos_laudos
    _dir_laudos = _voos_laudos.diretorio_laudos()
    os.makedirs(_dir_laudos, exist_ok=True)
    app.add_static_files("/laudos", _dir_laudos)
except Exception as _e_laudos:
    print(f"[laudos] aviso: /laudos não montado: {_e_laudos}")

app.on_startup(_montar_documentacao)

if __name__ in ("__main__", "__mp_main__"):
    _porta = _cfg_porta()
    ui.run(
        title=get_config("texto_login_titulo", "T! SOS DOCFLY") or "T! SOS DOCFLY",
        favicon=FAVICON_ATUAL,
        storage_secret=_SEGREDO,
        session_middleware_kwargs={"https_only": _HTTPS_ONLY},
        reload=False,
        host=HOST,
        port=_porta,
        show=False,
        language="pt-BR",
        timeout_graceful_shutdown=5,
    )
