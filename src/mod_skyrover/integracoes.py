"""Fachada de integração entre módulos — API pública do núcleo.

EN: Facade for cross-module integration — the single public seam that lets a
    business module reach another module WITHOUT importing it directly.
    Keeps the DAS rule of AGENTS.md §2 ("never cross-query between databases"):
    a module talks to `mod_skyrover`, and the core owns the coupling. Every
    function is fail-soft: if the target module is absent, disabled or raises,
    it returns a neutral value and logs — it NEVER breaks the caller's screen.

PT-BR: Fachada de integração entre módulos — costura pública única para um
    módulo de negócio alcançar outro SEM importá-lo diretamente. Preserva a
    regra do AGENTS.md §2 ("nunca faça cross-query entre bancos"): o módulo
    fala com o `mod_skyrover`, e o núcleo possui o acoplamento. Toda função é
    fail-soft: se o módulo de destino estiver ausente, desabilitado ou lançar
    exceção, devolve valor neutro e registra no log — NUNCA quebra a tela.

Usage:
    from mod_skyrover import integracoes
    integracoes.listar_usuarios_gestao(filtro_ativo=True)

Imports are LAZY (inside the functions) on purpose: a top-level import of a
business module here would close a top-level import cycle with `main.py`.
"""
import logging

logger = logging.getLogger(__name__)


# ================== Gestão de usuários (mod_gest_cad_usuario) ==================


def obter_usuario_gestao(user_nome: str):
    """EN: One user row from the user registry, or None.

    PT-BR: Uma linha da cadastro de usuários pelo nome, ou None. Usado por
    Filas e Lista Telefônica sem que eles conheçam o módulo de gestão."""
    try:
        nome = (user_nome or "").strip()
        if not nome:
            return None
        from mod_gest_cad_usuario.bd_manipulador import obter_usuario
        return obter_usuario(nome)
    except Exception as exc:
        logger.warning("integracoes.obter_usuario_gestao('%s'): falha (%s) — devolvendo None",
                       user_nome, exc)
        return None


def listar_usuarios_gestao(filtro_ativo=None) -> list:
    """EN: User rows from the registry (per-module access aggregated).

    PT-BR: Linhas do cadastro de usuários (acesso por módulo agregado). Lista
    vazia em qualquer falha — a tela que chama decide o que fazer."""
    try:
        from mod_gest_cad_usuario.bd_manipulador import listar_usuarios
        return list(listar_usuarios(filtro_ativo=filtro_ativo) or [])
    except Exception as exc:
        logger.warning("integracoes.listar_usuarios_gestao(filtro_ativo=%s): falha (%s) — devolvendo []",
                       filtro_ativo, exc)
        return []


# ================== Agregador de notícias (mod_agregador_noticias) ==================


def agregador_habilitado() -> bool:
    """EN: Whether the news aggregator is switched on in its own config.

    PT-BR: Se o agregador de notícias está ligado na configuração do módulo.
    Falso quando o módulo não responde — a TV Filas cai no aviso de pausa."""
    try:
        from mod_agregador_noticias.bd_manipulador import habilitado
        return bool(habilitado())
    except Exception as exc:
        logger.warning("integracoes.agregador_habilitado: falha (%s) — devolvendo False", exc)
        return False


def listar_noticias_para_tv(limite: int = 200) -> list:
    """EN: Up to `limite` recent headlines for the Filas TV carousel (censorship filtered).

    PT-BR: Até `limite` manchetes recentes para o carrossel da TV Filas
    (censura já filtrada na origem). Lista vazia em qualquer falha."""
    try:
        from mod_agregador_noticias.bd_manipulador import listar_para_tv
        return list(listar_para_tv(limite=limite) or [])
    except Exception as exc:
        logger.warning("integracoes.listar_noticias_para_tv(limite=%s): falha (%s) — devolvendo []",
                       limite, exc)
        return []


def limpar_noticias_censuradas() -> int:
    """EN: Drop already-collected headlines whose title is censored; returns how many.

    PT-BR: Remove as notícias já coletadas cujo título está censurado e devolve
    quantas saíram. Usado pelo admin do Blog ao salvar a lista de censura —
    quem orquestra é o núcleo, não o Blog conhecendo o Agregador."""
    try:
        from mod_agregador_noticias.bd_manipulador import limpar_censuradas
        return int(limpar_censuradas() or 0)
    except Exception as exc:
        logger.warning("integracoes.limpar_noticias_censuradas: falha (%s) — devolvendo 0", exc)
        return 0


# ================== Lista telefônica (mod_lista_telefonica) ==================


def obter_organograma_base():
    """EN: The shared organogram seed (secretaria -> sector -> subsector).

    PT-BR: A semente do organograma compartilhado (secretaria → setor → subsetor),
    fonte única das cotas por área. Devolve `None` quando o módulo não responde,
    para o chamador manter o seu próprio fallback local."""
    try:
        from mod_lista_telefonica.bd_manipulador import ORGANOGRAMA_BASE
        return ORGANOGRAMA_BASE
    except Exception as exc:
        logger.warning("integracoes.obter_organograma_base: falha (%s) — devolvendo None", exc)
        return None


def espelhar_cadastro_na_lista_telefonica(ator="sistema") -> dict:
    """EN: Mirror registered servers into the phone directory.

    PT-BR: Espelha no diretório telefônico os servidores cadastrados.

    ESTA FUNÇÃO É A COSTURA
        O cadastro de usuários é dono de nome, matrícula, secretaria, cargo e
        do telefone que a pessoa autorizou; a lista telefônica é dona dos
        contatos. Nenhum dos dois pode abrir o banco do outro. Então quem
        busca é o módulo do cadastro (que só publica o que é público e
        autorizado), quem grava é o da lista (que só escreve no banco dele),
        e a ligação entre os dois acontece AQUI, no núcleo — o único lugar do
        sistema autorizado a conhecer os dois de perto.

    Devolve o resumo `{criados, atualizados, sem_unidade, sem_telefone,
    ja_iguais}`. Em qualquer falha, devolve o mesmo formato com `erro=True` e
    zeros — a tela que chama decide o que fazer, e uma falha aqui nunca pode
    derrubar a lista.
    """
    vazio = {"criados": 0, "atualizados": 0, "sem_unidade": 0,
             "sem_telefone": 0, "ja_iguais": 0}
    try:
        from mod_gest_cad_usuario import leitura_lista
        servidores = leitura_lista.listar_para_lista_telefonica()
        from mod_lista_telefonica.bd_manipulador import sincronizar_contatos_do_cadastro
        return sincronizar_contatos_do_cadastro(servidores, ator=ator)
    except Exception as exc:
        logger.warning("integracoes.espelhar_cadastro_na_lista_telefonica: "
                       "falha (%s)", exc)
        return {**vazio, "erro": True}


def telefones_de_recado_para_lista() -> dict:
    """EN: `{user_nome: True}` — who answers on the SECTOR's line (message phone).

    PT-BR: Quem atende no telefone do SETOR (deixa recado).

    Existe pela mesma razão de `espelhar_cadastro_na_lista_telefonica`: a lista
    telefônica precisa saber, para cada cartão, se o número é da pessoa ou do
    setor — e não pode abrir o banco do cadastro. A costura é aqui.

    A chave é a **matrícula** (`user_nome`), que é o que o contato vinculado
    guarda — por isso o cartão resolve o "deixe recado" sem tocar em banco
    nenhum durante o desenho."""
    try:
        from mod_gest_cad_usuario import leitura_lista
        return {u["user_nome"]: True
                for u in leitura_lista.listar_para_lista_telefonica()
                if u.get("recado")}
    except Exception as exc:
        logger.warning("integracoes.telefones_de_recado_para_lista: falha (%s)",
                       exc)
        return {}


def atualizar_telefone_vinculado(ator, user_nome, numero_antigo,
                                 numero_novo) -> tuple:
    """EN: Edit a linked contact's number through the registry (source of truth).

    PT-BR: Altera o número de um contato vinculado pelo cadastro (fonte
    da verdade).

    O espelhamento (`sincronizar_contatos_do_cadastro`) sobrescreve o
    telefone do vinculado a cada ciclo — editar só a cópia do diretório
    (`tb_contato`) seria revertido em minutos. Por isso o card da lista,
    ao editar um vinculado, passa por AQUI: acha no cadastro o telefone
    com os mesmos dígitos do antigo e altera para o novo. Sem dobra de
    banco: a lista telefônica nunca abre o banco do cadastro (§2).

    Devolve `(True, msg)` ou `(False, motivo)` — e nunca levanta.
    """
    try:
        from mod_gest_cad_usuario import bd_manipulador as gest
        if not (user_nome or "").strip() or not (numero_novo or "").strip():
            return False, "Dados insuficientes."
        def _dig(s):
            return "".join(c for c in str(s or "") if c.isdigit())
        alvo = _dig(numero_antigo)
        tels = gest.listar_telefones(user_nome) or []
        cand = [t for t in tels if alvo and _dig(t[2]) == alvo]
        if not cand:
            return False, ("Telefone não encontrado no cadastro do "
                           "servidor — ajuste no perfil do usuário.")
        return gest.editar_telefone(ator or "sistema", cand[0][0],
                                    numero=numero_novo)
    except Exception as exc:
        logger.warning("integracoes.atualizar_telefone_vinculado: falha (%s)",
                       exc)
        return False, "Erro interno. Tente novamente."


# ================== Módulos do sistema ==================


def modulo_habilitado(chave: str) -> bool:
    """EN: Whether a business module is switched on (`tb_modulos.ativo`).

    PT-BR: Se um módulo de negócio está ligado (`tb_modulos.ativo`).
    Módulo desconhecido conta como desligado."""
    try:
        from mod_skyrover.autenticacao import modulos_registrados
        alvo = (chave or "").strip()
        if not alvo:
            return False
        for linha in modulos_registrados() or []:
            # linha = (chave, nome, icone, rota, ativo)
            if len(linha) >= 5 and linha[0] == alvo:
                return bool(linha[4])
        return False
    except Exception as exc:
        logger.warning("integracoes.modulo_habilitado('%s'): falha (%s) — devolvendo False",
                       chave, exc)
        return False


def registrar_auditoria(usuario, modulo, acao, descricao):
    """EN: Writes one audit row on behalf of a business module (fail-soft).

    PT-BR: Grava UM registro de auditoria em nome de um módulo de negócio
    (fail-soft). Existe para que o módulo de negócio NUNCA importe
    `mod_skyrover.bd_manipulador`: quem possui o acoplamento é o núcleo, e
    a função devolve `True`/`False` em vez de propagar a exceção — uma
    auditoria que falhou não pode derrubar a tela do servidor."""
    try:
        from mod_skyrover.bd_manipulador import audit_log
        audit_log(usuario or "sistema", modulo, acao, descricao)
        return True
    except Exception as exc:
        logger.warning("integracoes.registrar_auditoria('%s', '%s'): "
                       "falha (%s) — devolvendo False", modulo, acao, exc)
        return False


def buscar_usuarios_gestao(termo="", limite=50):
    """EN: Active users matching `termo` — dicts with display name and unit.

    PT-BR: Usuários ATIVOS que casam com o termo — dicionários com nome de
    exibição (primeiro + último), cargo, unidade e lotação. Serve para o
    seletor de quem participa de um quadro/convite: a tela mostra o nome que
    a pessoa deve ler e a unidade dela, nunca a matrícula crua sozinha. Lista
    vazia em qualquer falha — o seletor fica vazio, a tela não quebra."""
    try:
        from mod_gest_cad_usuario import leitura_lista
        return list(leitura_lista.buscar_usuarios_para_lista(termo=termo,
                                                             limite=limite) or [])
    except Exception as exc:
        logger.warning("integracoes.buscar_usuarios_gestao(termo=%r): "
                       "falha (%s) — devolvendo []", termo, exc)
        return []


def dados_usuario_lista_gestao(user_nome):
    """EN: One user's public directory data (name, job, unit, phone), or None.

    PT-BR: Os dados de diretório de UM usuário (nome, cargo, unidade, telefone
    da empresa), ou None.serve à lista telefônica para mostrar quem recebeu a
    partilha como CARTÃO DE CONTATO — o mesmo desenho da grade geral — em vez
    de login cru. Mesmo gateway de sempre: quem pede não conhece o módulo de
    gestão, e a leitura sai do banco DELE.
    """
    try:
        nome = (user_nome or "").strip()
        if not nome:
            return None
        from mod_gest_cad_usuario import leitura_lista
        return leitura_lista.obter_usuario_para_lista(nome)
    except Exception as exc:
        logger.warning("integracoes.dados_usuario_lista_gestao('%s'): "
                       "falha (%s) — devolvendo None", user_nome, exc)
        return None


def conceder_acesso_gestao(ator, user_nome, modulo_chave, papel="comum"):
    """EN: Grants/revokes a user's per-module role in the user registry.

    PT-BR: Concede (ou remove) o papel do usuário num módulo, no cadastro de
    usuários. `papel=None` remove o vínculo. O módulo de negócio só pede —
    quem escreve em `tb_acesso_usuario` é o módulo dono do cadastro.
    Devolve (ok, mensagem); em falha, o mesmo formato com erro."""
    try:
        from mod_gest_cad_usuario.bd_manipulador import definir_acesso
        return definir_acesso(ator, user_nome, modulo_chave, papel)
    except Exception as exc:
        logger.warning("integracoes.conceder_acesso_gestao(%r, %r): "
                       "falha (%s)", user_nome, modulo_chave, exc)
        return (False, "Erro ao alterar o acesso do servidor")


def obter_papel_gestao(user_nome, modulo_chave):
    """EN: The user's effective role in a module, or None.

    PT-BR: Papel efetivo do usuário no módulo, ou None quando não tem
    vínculo. None também quando o cadastro não responde (fail-soft)."""
    try:
        from mod_gest_cad_usuario.bd_manipulador import obter_papel_no_modulo
        return obter_papel_no_modulo(user_nome, modulo_chave)
    except Exception as exc:
        logger.warning("integracoes.obter_papel_gestao(%r, %r): falha (%s)",
                       user_nome, modulo_chave, exc)
        return None


# ================== Unidades do organograma (mod_lista_telefonica) ==================


def sincronizar_organograma_cadastro(plano, aplicar=True, ator="sistema"):
    """EN: Writes the organogram coming from the payroll sheet into the phone
    directory. The core is the one that stitches, per AGENTS.md §2.

    PT-BR: Grava no organograma da lista telefônica o plano que a folha de
    servidores trouxe. `plano` é uma lista flat de
    `(nome, tipo, nome_do_pai_ou_None, ordem)`, de raiz para a folha.

    Existe porque o módulo de cadastro de usuários tem a FOLHA e o módulo da
    lista telefônica tem o BANCO, e nenhum dos dois pode falar direto com o
    outro. Quem tem o banco expõe a escrita (`sincronizar_organograma`); quem
    tem a folha monta o plano; o núcleo costura. Nenhum dado de servidor
    atravessa direto — só o organograma, que é estrutura, não cadastro.
    """
    vazio = {"secretarias_criadas": 0, "setores_criados": 0,
             "reativadas": 0, "desativadas": 0, "erros": []}
    try:
        from mod_lista_telefonica.bd_manipulador import sincronizar_organograma
        return sincronizar_organograma(plano, aplicar=aplicar, ator=ator)
    except Exception as exc:
        logger.warning("integracoes.sincronizar_organograma_cadastro: falha (%s) "
                       "— organograma nao alterado", exc)
        return {**vazio, "erros": [str(exc)]}


def listar_unidades_organograma(tipo=None, ativo=1):
    """EN: Organogram units of the phone directory as dicts (id, name, kind...).

    PT-BR: Unidades do organograma da lista telefônica como dicionários
    (`id`, `nome`, `tipo`, `parent_id`, `ordem`, `telefone`, `ativo`).
    É o seletor de unidade do quadro de ordens de serviço: cada secretaria,
    setor ou subsetor pode ter o seu. Lista vazia em qualquer falha — o
    quadro particular continua disponível."""
    try:
        from mod_lista_telefonica.bd_manipulador import listar_todas_unidades
        saida = []
        for linha in listar_todas_unidades() or []:
            if not linha or len(linha) < 7:
                continue
            if tipo and linha[2] != tipo:
                continue
            if ativo is not None and not linha[6]:
                continue
            saida.append({"id": linha[0], "nome": linha[1], "tipo": linha[2],
                          "parent_id": linha[3], "ordem": linha[4],
                          "telefone": linha[5], "ativo": linha[6]})
        return saida
    except Exception as exc:
        logger.warning("integracoes.listar_unidades_organograma(tipo=%r): "
                       "falha (%s) — devolvendo []", tipo, exc)
        return []


def _norm_unidade(texto):
    """Compara nomes de unidade sem acento e sem pontuação (NFKD + [a-z0-9])."""
    try:
        import re
        import unicodedata
        limpo = unicodedata.normalize("NFKD", str(texto or "")) \
            .encode("ascii", "ignore").decode().lower()
        return " ".join(re.findall(r"[a-z0-9]+", limpo))
    except Exception:
        return str(texto or "").lower()


def unidades_por_usuario_gestao():
    """EN: `{matricula: {nome_exibicao, unidade, lotacao, cargo}}` for the organogram.

    PT-BR: `{matricula: {nome_exibicao, unidade, lotacao, cargo}}` — quem é o
    servidor e de qual setor ele é, para o quadro da unidade saber a quem se
    mostrar.

    O nome da unidade guardado é o do CADASTRO do servidor (lotação, com a
    unidade como reserva); casar isso com as unidades do organograma é tarefa
    do módulo que DETÉM o organograma, não deste. Por isso o campo `unidade`
    sai com o valor do cadastro e quem compara é o chamador, com a normalização
    que ele quiser. Dicionário vazio em qualquer falha."""
    try:
        from mod_gest_cad_usuario import leitura_lista
        saida = {}
        for servidor in leitura_lista.listar_para_lista_telefonica() or []:
            matricula = servidor.get("user_nome")
            if not matricula:
                continue
            saida[matricula] = {
                "nome_exibicao": servidor.get("nome_exibicao") or matricula,
                "unidade": servidor.get("unidade") or "",
                "lotacao": servidor.get("lotacao") or "",
                "cargo": servidor.get("cargo") or "",
            }
        return saida
    except Exception as exc:
        logger.warning("integracoes.unidades_por_usuario_gestao: "
                       "falha (%s) — devolvendo {}", exc)
        return {}


def unidades_do_organograma_por_nome():
    """EN: `{nome normalizado: {id, nome, tipo}}` of the ACTIVE units.

    PT-BR: `{nome normalizado: {id, nome, tipo}}` das unidades ATIVAS do
    organograma, com o nome já normalizado (sem acento, sem pontuação).

    É a peça que fecha o casamento: o cadastro do servidor traz `lotacao`/
    `unidade` como TEXTO, e o organograma tem a unidade com id. Casa-se por
    nome normalizado — a lotação tem precedência, porque é o setor onde a
    pessoa trabalha de fato. Dicionário vazio em qualquer falha."""
    try:
        consulta = {}
        for unidade in listar_unidades_organograma(ativo=1):
            chave = _norm_unidade(unidade.get("nome"))
            if chave and chave not in consulta:
                consulta[chave] = {"id": unidade.get("id"),
                                   "nome": unidade.get("nome"),
                                   "tipo": unidade.get("tipo")}
        return consulta
    except Exception as exc:
        logger.warning("integracoes.unidades_do_organograma_por_nome: "
                       "falha (%s) — devolvendo {}", exc)
        return {}


# ================== Solicitação de Impressão (config local do módulo) ==================


def obter_config_solicita_impressao(chave: str, padrao: str = "") -> str:
    """EN: One local config key of the print module (its own tb_configuracoes_modulo).

    PT-BR: Uma chave LOCAL do módulo de impressão (tb_configuracoes_modulo
    dele). Existe porque esse módulo não usa a tb_config central para
    `tempo_expira_rascunho_min`/`tempo_exclui_impresso_min` — o espelho do Hora
    Certa precisa ler/gravar lá sem importar o módulo (AGENTS.md §2: a costura
    é do núcleo). Fail-soft: devolve `padrao` em qualquer falha."""
    try:
        nome = (chave or "").strip()
        if not nome:
            return padrao
        from mod_solicita_impressao.bd_manipulador import obter_config
        return obter_config(nome, padrao)
    except Exception as exc:
        logger.warning("integracoes.obter_config_solicita_impressao(%r): falha (%s) — devolvendo padrão",
                       chave, exc)
        return padrao


def definir_config_solicita_impressao(chave: str, valor) -> bool:
    """EN: Writes one local config key of the print module (fail-soft bool).

    PT-BR: Grava uma chave LOCAL do módulo de impressão. Par do leitor acima:
    o Hora Certa espelha por aqui. Devolve True/False, nunca levanta."""
    try:
        nome = (chave or "").strip()
        if not nome:
            return False
        from mod_solicita_impressao.bd_manipulador import definir_config
        return bool(definir_config(nome, valor))
    except Exception as exc:
        logger.warning("integracoes.definir_config_solicita_impressao(%r): falha (%s) — devolvendo False",
                       chave, exc)
        return False


# ================== Agregador de notícias (espelho Hora Certa) ==================

def obter_agregador(chave: str, padrao: str = "") -> str:
    """EN: One schedule key of the news module (its own database).

    PT-BR: Uma chave de agendamento do módulo de notícias (banco dele):
    `habilitado`, `intervalo_min`, `hora_reinicio`. O espelho do Hora Certa
    lê por aqui sem importar o módulo (AGENTS.md §2: a costura é do núcleo).
    Fail-soft: devolve `padrao` em qualquer falha."""
    try:
        nome = (chave or "").strip()
        if not nome:
            return padrao
        from mod_agregador_noticias import bd_manipulador as _ag
        if nome == "habilitado":
            return "1" if _ag.habilitado() else "0"
        if nome == "intervalo_min":
            return str(_ag.intervalo_min())
        if nome == "hora_reinicio":
            return _ag.obter_hora_reinicio()
        return padrao
    except Exception as exc:
        logger.warning("integracoes.obter_agregador(%r): falha (%s) — devolvendo padrão",
                       chave, exc)
        return padrao


def definir_agregador(chave: str, valor) -> bool:
    """EN: Writes one schedule key of the news module (fail-soft bool).

    PT-BR: Grava uma chave de agendamento do módulo de notícias. Par do
    leitor acima: o Hora Certa espelha por aqui, com ator `hora_certa` para
    a auditoria dizer quem mudou. Devolve True/False, nunca levanta."""
    try:
        nome = (chave or "").strip()
        if not nome:
            return False
        from mod_agregador_noticias import bd_manipulador as _ag
        if nome == "habilitado":
            return bool(_ag.definir_habilitado(str(valor) == "1", ator="hora_certa"))
        if nome == "intervalo_min":
            ok, _v = _ag.definir_intervalo(int(valor or 60), ator="hora_certa")
            return bool(ok)
        if nome == "hora_reinicio":
            ok, _v = _ag.definir_hora_reinicio(str(valor or "09:00"), ator="hora_certa")
            return bool(ok)
        return False
    except Exception as exc:
        logger.warning("integracoes.definir_agregador(%r): falha (%s) — devolvendo False",
                       chave, exc)
        return False


# ================== Blog (mod_blog) ==================


def obter_blog_carrossel_tempo(padrao: str = "10") -> str:
    """EN: Carousel slide interval (seconds) of the blog module (its own database).

    PT-BR: Segundos por slide do carrossel do Blog (banco dele).
    O espelho do Hora Certa lê por aqui sem importar o módulo (AGENTS.md
    §2: a costura é do núcleo). Fail-soft: devolve `padrao` em falha."""
    try:
        from mod_blog import bd_manipulador as _bg
        return str(_bg.obter_carrossel_tempo())
    except Exception as exc:
        logger.warning("integracoes.obter_blog_carrossel_tempo: falha (%s) — devolvendo padrão",
                       exc)
        return padrao


def definir_blog_carrossel_tempo(valor) -> bool:
    """EN: Writes the blog carousel interval (fail-soft bool).

    PT-BR: Grava os segundos por slide do carrossel do Blog. Par do leitor
    acima: o Hora Certa espelha por aqui. Devolve True/False, nunca levanta."""
    try:
        from mod_blog import bd_manipulador as _bg
        return bool(_bg.definir_carrossel_tempo(valor))
    except Exception as exc:
        logger.warning("integracoes.definir_blog_carrossel_tempo(%r): falha (%s) — devolvendo False",
                       valor, exc)
        return False


# ================== Dados abertos (mod_dados_abertos) ==================


def folha_de_servidores_publica() -> dict:
    """EN: The server sheet as published, straight from the file.

    PT-BR: A folha de servidores como a FONTE a publica, lida do arquivo.

    É o que alimenta o card "Servidores Públicos" do módulo de Dados Abertos.
    Devolve o dicionário cru (`origem`, `url`, `competencia`, `coletado_em`,
    `total`, `aviso`, `servidores`) — **sem** gravar, **sem** auditar e
    **sem** passar pelo cadastro: o dado aberto mostra o que a fonte
    publica, não o que o sistema gravou depois.

    A costura existe porque o arquivo mora em
    `mod_gest_cad_usuario/dados/`, e Dados Abertos não pode abrir a pasta de
    outro módulo (AGENTS.md §2). Quem sabe o caminho e o formato do arquivo é
    o módulo que o coletou — por isso o `import` é de
    `mod_gest_cad_usuario.carga_folha`, lazy, e não do `bd_manipulador`: a
    folha é um ARQUIVO, não uma tabela do banco de usuários.

    `{}` em qualquer falha, e um dicionário com `erro` preenchido quando a
    folha existe mas veio vazia — quem chama mostra "fonte indisponível" em
    vez de um zero que parece dado.
    """
    try:
        from mod_gest_cad_usuario.carga_folha import folha_arquivo_atual
        folha = folha_arquivo_atual()
        if not folha:
            return {"erro": "folha de servidores indisponivel ou vazia",
                    "servidores": []}
        return folha
    except Exception as exc:
        logger.warning("integracoes.folha_de_servidores_publica: falha (%s) "
                       "— devolvendo folha vazia", exc)
        return {"erro": str(exc), "servidores": []}


def cadastro_publico() -> dict:
    """EN: The user registry as counts, never as people.

    PT-BR: O cadastro de usuários como CONTAGEM, nunca como pessoas.

    Segunda costura para Dados Abertos, pelo mesmo motivo da primeira: o banco
    de usuários é do outro módulo e não pode ser consultado de lá (AGENTS.md
    §2).

    **O que NÃO sai daqui**: nome, matrícula, e-mail, telefone, CPF, senha,
    login. Sai o QUANTO — por perfil, por situação, por liberação do DTI — que
    é o que o painel de dado aberto pode mostrar. É a regra do módulo, e ela
    é a razão de esta função devolver agregados e não linhas.
    """
    saida = {"contas": 0, "por_perfil": [], "por_situacao": [],
             "liberados_dti": 0, "bloqueados": 0, "ativos": 0,
             "telefone_pendente": 0, "erro": ""}
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd
        saida["contas"] = _bd.contar_usuarios_total()
        _det = _bd.resumo_cadastro()
        saida["por_perfil"] = _det.get("por_perfil") or []
        saida["por_situacao"] = _det.get("por_situacao") or []
        saida["liberados_dti"] = _det.get("liberados_dti", 0)
        saida["bloqueados"] = _det.get("bloqueados", 0)
        saida["ativos"] = _det.get("ativos", 0)
        saida["telefone_pendente"] = _det.get("telefone_pendente", 0)
    except Exception as exc:
        logger.warning("integracoes.cadastro_publico: falha (%s)", exc)
        saida["erro"] = str(exc)
    return saida


def contracheques_publicos(competencia: str = "") -> dict:
    """EN: The captured payslips as totals and a breakdown of allowances.

    PT-BR: Os contracheques capturados como TOTAIS e o demonstrativo de verbas.

    Terceira costura para Dados Abertos. Semelhante às outras duas: o dado mora
    em `mod_gest_cad_usuario` e sai daqui só agregado. O demonstrativo de
    verbas é o que responde "quanto a folha paga de auxílio alimentação, de hora
    extra, de INSS" — que é a leitura de quem lê, e nunca a leitura de uma
    pessoa.

    Sem competência informada, usa a mais recente com contracheque.
    """
    saida = {"competencia": competencia or "", "fichas": 0, "pessoas": 0,
             "proventos_total": 0.0, "descontos_total": 0.0, "liquido_total": 0.0,
             "salario_base_total": 0.0, "por_verba": [],
             "acima_do_salario": 0, "acima_2x": 0, "erro": ""}
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd
        _r = _bd.resumo_contracheques(competencia)
        saida.update({k: v for k, v in _r.items() if k in saida})
    except Exception as exc:
        logger.warning("integracoes.contracheques_publicos: falha (%s)", exc)
        saida["erro"] = str(exc)
    return saida


def comissao_publica(competencia: str = "") -> dict:
    """EN: How much of the pay is commission, in counts and totals.

    PT-BR: Quanto da remuneração é comissão, em contagens e totais.

    Quarta costura, e a que responde ao CONTROLE INTERNO: quantos recebem por
    cargo em comissão/extras mais que o salário, e quantos mais que o dobro.

    O saldo é entre a soma das verbas de comissão **e extras** e o salário do
    contrato. Comissão sozinha nunca passa do salário nesta prefeitura — e
    isso é um ACHADO, não ausência de dado: é por isso que a métrica vem com
    a lista de quem está acima, e não só com o número.
    """
    saida = {"competencia": competencia or "", "erro": ""}
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd
        _r = _bd.estatisticas_comissao(competencia)
        saida.update(_r)
    except Exception as exc:
        logger.warning("integracoes.comissao_publica: falha (%s)", exc)
        saida["erro"] = str(exc)
    return saida


def diarias_publicas() -> dict:
    """EN: Yearly travel-allowance aggregates, with the nominal list.

    PT-BR: Agregados anuais das diárias, com a lista nominal.

    Quinta costura para Dados Abertos, pelo mesmo motivo das outras: a tabela
    `tb_diarias` é do banco de usuários e não pode ser consultada de lá
    (AGENTS.md §2). Sai por ano — total, maior, menor, média, mediana, moda,
    nº de favorecidos — mais nome + valor pago de cada um, que é o que o
    portal publica abertamente. O que NÃO sai: CPF parcial, `user_nome`,
    `cd_fornecedor`.
    """
    saida = {"disponivel": False, "motivo": "", "anos": [],
             "coletado_em": "", "erro": ""}
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd
        _r = _bd.resumo_diarias_publico()
        saida.update({k: v for k, v in _r.items() if k in saida})
    except Exception as exc:
        logger.warning("integracoes.diarias_publicas: falha (%s)", exc)
        saida["erro"] = str(exc)
    return saida


def comissao_por_verba(competencia: str = "") -> dict:
    """EN: Commission payees grouped by allowance name, with amounts.

    PT-BR: Quem recebe por cada rubrica de comissão, com valor (sexta
    costura). Mesmo motivo das outras: `tb_detalhe_ficha` é do banco de
    usuários (AGENTS.md §2). Sai um bloco por rubrica ("CARGO EM COMISSAO"
    e "DIF CARGO COMISSAO/FUNC G" = diferença de cargo em comissão ou
    Função Gratificada) — pessoas, total e lista nominal. O que NÃO sai:
    matrícula, CPF, `user_nome`.
    """
    saida = {"disponivel": False, "motivo": "", "competencia": "",
             "verbas": [], "erro": ""}
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd
        _r = _bd.resumo_comissao_por_verba(competencia)
        saida.update({k: v for k, v in _r.items() if k in saida})
    except Exception as exc:
        logger.warning("integracoes.comissao_por_verba: falha (%s)", exc)
        saida["erro"] = str(exc)
    return saida


def proventos_por_cargo(cargo: str = "") -> dict:
    """EN: Same-role pay comparison, aggregates only, no names.

    PT-BR: Agregados por cargo para o dado aberto (sétima costura): cargo,
    média, mediana e as contagens nas faixas ±R$ 1.000 da mediana, com o
    split concursado/contratado — SEM nomes (decisão do responsável de
    12/10/2026: no aberto vai o cargo, não o funcionário). `cargo=""`
    traz todos; com cargo, só ele. Sem `user_nome`, sem matrícula, sem CPF.
    """
    saida = {"disponivel": False, "motivo": "", "competencia": "",
             "cargos": [], "total_cargos": 0, "total_pessoas": 0, "erro": ""}
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd
        _r = _bd.comparar_todos_os_cargos() or {}
        cargos = []
        for bloco in (_r.get("cargos") or []):
            try:
                if (cargo or "").strip() and bloco.get("cargo") != cargo.strip():
                    continue
                copia = {k: v for k, v in bloco.items() if k != "pares"}
                cargos.append(copia)
            except Exception:
                continue
        saida.update({"disponivel": bool(cargos),
                      "motivo": "" if cargos else "sem cargos com pares",
                      "competencia": _r.get("competencia") or "",
                      "cargos": cargos, "total_cargos": len(cargos),
                      "total_pessoas": sum(int(b.get("total") or 0)
                                           for b in cargos)})
    except Exception as exc:
        logger.warning("integracoes.proventos_por_cargo: (%s)", exc)
        saida["erro"] = str(exc)
    return saida


def proventos_por_cargo_todos(competencia: str = "") -> dict:
    """EN: All comparable roles grouped, in one pass.

    PT-BR: Todos os cargos comparáveis agrupados (oitava costura). A mesma
    conta cargo a cargo, em 3 consultas — existe porque a lista completa
    não cabe em 58 idas ao banco. Sem `user_nome`, sem matrícula, sem CPF.
    """
    saida = {"disponivel": False, "motivo": "", "competencia": "",
             "cargos": [], "total_cargos": 0, "total_pessoas": 0, "erro": ""}
    try:
        from mod_gest_cad_usuario import bd_manipulador as _bd
        _r = _bd.comparar_todos_os_cargos(competencia)
        saida.update({k: v for k, v in _r.items() if k in saida})
    except Exception as exc:
        logger.warning("integracoes.proventos_por_cargo_todos: (%s)", exc)
        saida["erro"] = str(exc)
    return saida


# ================== Vídeos (mod_video) ==================

def listar_videos_publicados(limite: int = 100) -> list:
    """EN: System library videos (no expiry) for other modules (e.g. filas TV).

    PT-BR: Vídeos da biblioteca do sistema (sem expiração) para outros
    módulos (ex.: TV das filas). Cada item: id/titulo/plataforma/url_midia
    (`/midia_video/<arquivo>`)/tamanho_bytes. Lista vazia em falha."""
    try:
        from mod_video import bd_manipulador as _bd
        itens = _bd.listar_biblioteca(limite=limite) or []
        saida = []
        for item in itens:
            try:
                saida.append({
                    "id": item.get("id"),
                    "titulo": item.get("titulo") or "",
                    "plataforma": item.get("plataforma") or "",
                    "url_midia": _bd.url_biblioteca(item.get("arquivo") or ""),
                    "tamanho_bytes": item.get("tamanho_bytes") or 0,
                })
            except Exception:
                pass
        return saida
    except Exception as exc:
        logger.warning("integracoes.listar_videos_publicados: (%s)", exc)
        return []


# ================== WhatsApp (mod_zap) ==================

def vozes_whatsapp() -> list:
    """EN: Available PT voices for WhatsApp audio. PT-BR: vozes PT
    disponíveis para áudio de WhatsApp. Lista de (chave, id, rotulo)."""
    try:
        from mod_zap import servico_voz as _voz
        return [(c, v, r) for c, v, r in (_voz.VOZES or [])]
    except Exception as exc:
        logger.warning("integracoes.vozes_whatsapp: (%s)", exc)
        return []


def sintetizar_voz_whatsapp(texto, voz="eliana", user_nome=""):
    """EN: Text → MP3 for WhatsApp audio. PT-BR: texto → MP3 para áudio de
    WhatsApp. Devolve (ok, caminho, msg)."""
    try:
        from mod_zap import servico_voz as _voz
        return _voz.sintetizar(texto, voz=voz, user_nome=user_nome)
    except Exception as exc:
        logger.warning("integracoes.sintetizar_voz_whatsapp: (%s)", exc)
        return False, "", "Voz indisponível."


async def enviar_whatsapp_texto(user_nome, numero, texto):
    """EN: Sends WhatsApp text via automation. PT-BR: envia texto de
    WhatsApp pela automação. Devolve (ok, detalhe)."""
    try:
        from mod_zap import motor_zap as _motor
        return await _motor.enviar(user_nome, numero, texto)
    except Exception as exc:
        logger.warning("integracoes.enviar_whatsapp_texto: (%s)", exc)
        return False, "Envio indisponível."


async def enviar_whatsapp_audio(user_nome, numero, caminho_mp3):
    """EN: Attaches and sends an MP3 via WhatsApp Web. PT-BR: anexa e envia
    um MP3 pelo WhatsApp Web. Devolve (ok, detalhe)."""
    try:
        from mod_zap import motor_zap as _motor
        return await _motor.enviar_audio(user_nome, numero, caminho_mp3)
    except Exception as exc:
        logger.warning("integracoes.enviar_whatsapp_audio: (%s)", exc)
        return False, "Envio indisponível."
