"""Central authentication, sessions and module registry (LGPD traceable).

Autenticação central, sessões revogáveis e cadastro de módulos (rastreável LGPD).

EN: bcrypt login, revocable sessions (cookie_hash via secrets), per-module
role checks delegating user data to mod_gest_cad_usuario, tb_modulos registry
with order/route editing and indispensable-module guard.
PT: login bcrypt, sessões revogáveis (cookie_hash via secrets), checagem de
papel por módulo delegando dados ao mod_gest_cad_usuario, cadastro tb_modulos
com edição de ordem/roda e guarda de módulos indispensáveis."""
import bcrypt
import os
import hashlib
import re
import threading
import time

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from mod_tisosdocfly.bd_conexao import get_connection
from mod_tisosdocfly.bd_manipulador import audit_log
from mod_tisosdocfly.repositorio import Repositorio

SESSION_COOKIE_NAME = "tisosdocfly_session"

MODULOS_SISTEMA = [
    ("usuarios", "Usuários", "manage_accounts", "/users"),
    ("agro", "Agropecuário", "agriculture", "/agro"),
    ("vistoria_predial", "Vistoria Predial", "apartment",
     "/vistoria-predial"),
    ("seguranca", "Segurança Pública", "shield", "/seguranca"),
    ("ambiental", "Ambiental", "forest", "/ambiental"),
    ("obras", "Obras", "construction", "/obras"),
    ("mapeamento", "Mapeamento", "map", "/mapeamento"),
    ("defesa_civil", "Defesa Civil", "emergency", "/defesa-civil"),
    ("inspecao_industrial", "Inspeção Industrial",
     "precision_manufacturing", "/inspecao-industrial"),
    ("eventos", "Eventos", "groups", "/eventos"),
    ("perimetro", "Perímetro e Segurança", "security", "/perimetro"),
]

CHAVE_POR_ROTA = {rota.strip("/"): chave for chave, _, _, rota in MODULOS_SISTEMA}

# Módulos que NASCEM ativos e nunca podem ser desligados (02/10/2026).
#
# Antes esta lista era {"auditoria", "blog", "usuarios"}. A regra do responsável
# mudou: na entrega, o sistema sobe com **todos** os módulos desligados e quem
# liga é o `master`, um por um. Só ficam de pé os três que o próprio sistema
# precisa para existir — o cadastro de usuários (quem entra), a auditoria (a
# trilha de quem fez o quê) e o núcleo `tisosdocfly`, que nem entra nesta tabela.
#
# `blog` saiu daqui de propósito: ele é conteúdo, não mecanismo. Um município
# que não publica nothing continua com um sistema íntegro; um município sem
# auditoria ou sem cadastro não tem sistema.
# (07/10) `hora_certa` entra por decisão do responsável: a hora oficial é
# mecanismo, tal qual cadastro e trilha — sem ela não há referência comum.
MODULOS_INDISPENSAVEIS = {"usuarios"}

# Módulos que NASCEM LIGADOS, mas podem ser desligados pelo administrador.
# `MODULOS_INDISPENSAVEIS` é o conjunto que não pode ser desligado; este é o
# conjunto que já vem disponível na entrega do produto. Os três módulos de
# negócio (agro, vistoria, segurança) nascem ligados para o cliente usar;
# módulos futuros acrescentados depois continuam nascendo desligados.
MODULOS_ATIVOS_POR_PADRAO = {
    "usuarios", "agro", "vistoria_predial", "seguranca",
    "ambiental", "obras", "mapeamento", "defesa_civil",
    "inspecao_industrial", "eventos", "perimetro",
}

_modulos_ok = False


def _garantir_tb_modulos():
    """Creates/populates tb_modulos once per process (idempotent migration).

    Cria a tabela `tb_modulos` (incluindo a coluna `ordem`) e a semeia com os
    módulos nativos de `MODULOS_SISTEMA`, uma única vez por processo.

    **Nascimento dos módulos (02/10/2026):** a entrega sobe com tudo desligado
    e quem liga é o `master`. Só `MODULOS_INDISPENSAVEIS` nascem ligados; os
    demais entram com `ativo=0`. Como o INSERT é `OR IGNORE`, banco em uso não
    é reescrito — o que o administrador já ligou continua ligado, e só um
    módulo acrescentado depois a `MODULOS_SISTEMA` nasce desligado.

    Em bancos antigos aplica migração idempotente: adiciona a coluna `ordem` via
    `ALTER TABLE` e numera SOMENTE as linhas com `ordem=0` — nativos zerados
    seguem `MODULOS_SISTEMA` e não-nativos zerados ficam após os numerados em
    ordem alfabética. Linhas já numeradas (ordem do usuário via ↑/↓) NUNCA são
    reescritas aqui, então a personalização sobrevive a reinícios. Falhas são
    registradas via loguru e re-lançadas (o cadastro de módulos é crítico).
    Usa `Repositorio` (SQLAlchemy ORM) para operações no banco.
    """
    global _modulos_ok
    if _modulos_ok:
        return
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_modulos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chave TEXT NOT NULL UNIQUE,
                nome TEXT NOT NULL,
                icone TEXT DEFAULT 'extension',
                rota TEXT NOT NULL,
                ativo INTEGER NOT NULL DEFAULT 1,
                nativo INTEGER NOT NULL DEFAULT 0,
                ordem INTEGER NOT NULL DEFAULT 0
            )
        """)
        for chave, nome, icone, rota in MODULOS_SISTEMA:
            # 02/10/2026 — o módulo nasce LIGADO só se for indispensável; os
            # demais nascem desligados e esperam o `master` ligá-los.
            #
            # `INSERT OR IGNORE` é o que mantém isto seguro nas duas direções:
            # banco novo recebe `ativo=0`; banco em uso NÃO é tocado, porque a
            # linha já existe e o IGNORE a preserva. É o mesmo cuidado das
            # contas de fábrica (AGENTS.md §8.2.0): o sistema não redecide por
            # conta própria o que o administrador já ligou. E um módulo NOVO
            # acrescentado a `MODULOS_SISTEMA` depois entra desligado, que é
            # exatamente o que se espera de uma entrega incremental.
            _ativo = 1 if chave in MODULOS_ATIVOS_POR_PADRAO else 0
            cur.execute(
                "INSERT OR IGNORE INTO tb_modulos "
                "(chave, nome, icone, rota, nativo, ativo, ordem) "
                "VALUES (?, ?, ?, ?, 1, ?, 0)",
                (chave, nome, icone, rota, _ativo),
            )
        colunas = {row[1] for row in cur.execute("PRAGMA table_info(tb_modulos)").fetchall()}
        if "ordem" not in colunas:
            cur.execute("ALTER TABLE tb_modulos ADD COLUMN ordem INTEGER NOT NULL DEFAULT 0")
        cur.execute("SELECT COUNT(*) FROM tb_modulos WHERE ordem=0")
        if cur.fetchone()[0] > 0:
            # Preenche SOMENTE as linhas zeradas, preservando a ordem do usuário:
            # nativos zerados seguem MODULOS_SISTEMA; demais, após os numerados.
            cur.execute("SELECT COALESCE(MAX(ordem), 0) FROM tb_modulos WHERE ordem<>0")
            proxima = cur.fetchone()[0] + 1
            for chave, _, _, _ in MODULOS_SISTEMA:
                cur.execute("SELECT 1 FROM tb_modulos WHERE chave=? AND ordem=0", (chave,))
                if cur.fetchone():
                    cur.execute("UPDATE tb_modulos SET ordem=? WHERE chave=?", (proxima, chave))
                    proxima += 1
            cur.execute("SELECT chave FROM tb_modulos WHERE ordem=0 ORDER BY nome")
            for (chave,) in cur.fetchall():
                cur.execute("UPDATE tb_modulos SET ordem=? WHERE chave=?", (proxima, chave))
                proxima += 1
        # Migração 260918 — nova ordem padrão dos nativos: [editar_pdf,
        # empenhos, solicita_impressao, blog, usuarios, auditoria] (blog/
        # usuarios/auditoria juntos no fim). Aplica SOMENTE quando as ordens
        # atuais reproduzem exatamente a sequência antiga 1..6 (instalação
        # sem personalização e sem módulos extras entre os nativos);
        # qualquer ordem personalizada NUNCA é tocada. Idempotente por
        # construção (após migrar, a sequência já não é a antiga).
        cur.execute("SELECT chave, ordem FROM tb_modulos WHERE nativo=1")
        ordens = {c: o for c, o in cur.fetchall()}
        antiga = {"blog": 1, "editar_pdf": 2, "empenhos": 3,
                  "solicita_impressao": 4, "usuarios": 5, "auditoria": 6}
        if ordens == antiga:
            cur.execute("SELECT COUNT(*) FROM tb_modulos WHERE nativo=0 AND ordem BETWEEN 1 AND 6")
            if cur.fetchone()[0] == 0:
                nova = {"editar_pdf": 1, "empenhos": 2, "solicita_impressao": 3,
                        "blog": 4, "usuarios": 5, "auditoria": 6}
                for chave, ordem in nova.items():
                    cur.execute("UPDATE tb_modulos SET ordem=? WHERE chave=?", (ordem, chave))
        conn.commit()
        _modulos_ok = True
    except Exception:
        from mod_tisosdocfly import observabilidade
        observabilidade.get_logger("tisosdocfly").exception(
            "falha ao garantir tb_modulos (criação/migração da coluna ordem)")
        raise
    finally:
        conn.close()


def nome_do_modulo(chave):
    """Nome de exibição cadastrado para a página (editável em Configurações)."""
    _garantir_tb_modulos()
    with Repositorio() as repo:
        mod = repo.obter_modulo(chave)
        return mod.nome if mod else None


def modulo_ativo(chave):
    """True se o módulo está LIGADO em `tb_modulos` (02/10/2026).

    Complementa `validar_acesso_modulo`, que responde a outra pergunta: não é
    "o usuário tem este módulo?" mas "o sistema liga este módulo?". São eixos
    independentes e o guarda de página precisa dos dois — permissão sem o
    módulo ligado deixa o servidor entrar numa página que o administrador
    desligou de propósito.

    Chave vazia ou ausente conta como **ativa**: quem chama sem `chave_modulo`
    (a Home, o `/configuracoes`) não está entrando em módulo nenhum, e tratá-la
    como desligada trancaria a tisosdocfly inteira por causa de uma configuração.

    FALHA DE LEITURA DEVOLVE `True`, e é deliberado: `tb_modulos` é cadastro,
    não dado de negócio. Se o banco não responde, o melhor palpite é não trancar
    o servidor na porta — o acesso segue barrado pela permissão, que é a trava
    que realmente protege dado.
    """
    alvo = (chave or "").strip()
    if not alvo:
        return True
    try:
        _garantir_tb_modulos()
        with Repositorio() as repo:
            mod = repo.obter_modulo(alvo)
        if mod is None:
            # Chave fora do cadastro: o módulo não existe para o sistema, e o
            # que não existe não trava a tela de quem entrou por outra via.
            return True
        return bool(mod.ativo)
    except Exception:
        from mod_tisosdocfly import observabilidade
        observabilidade.get_logger("tisosdocfly").warning(
            f"modulo_ativo('{alvo}'): falha ao ler tb_modulos — assume ativa")
        return True


def modulos_registrados(somente_ativos=False):
    """[(chave, nome, icone, rota, ativo)] — ALL registered modules, ordered.

    Retorna TODOS os módulos cadastrados em `tb_modulos`, incluindo os
    registrados depois (nativos ou criados pelo administrador), ordenados
    pela coluna `ordem` (editável em Configurações → Módulo) e, em empate,
    por nome. Em falha de leitura, registra loguru e retorna lista vazia
    (fail-soft). Usa `Repositorio` (SQLAlchemy ORM).
    """
    _garantir_tb_modulos()
    with Repositorio() as repo:
        mods = repo.listar_modulos(somente_ativos=somente_ativos)
        return [(m.chave, m.nome, m.icone, m.rota, m.ativo) for m in mods]


def registrar_modulo(ator, chave, nome, icone="extension", rota="#", ativo=False):
    """Registers a NEW (future) module, born unavailable until activated.

    Cadastra um módulo NOVO (futuro). Por padrão nasce INDISPONÍVEL até que
    o administrador o ative (quando a rota/página passar a existir).
    Aparece imediatamente nas liberações de usuário. A ordem de exibição
    nasce como `max(ordem)+1` (fica no fim da lista). Audita
    `registrar_modulo` e retorna `(ok, msg)`; falhas são registradas via
    loguru e reportadas como chave duplicada.
    Usa `Repositorio` (SQLAlchemy ORM).
    """
    chave = (chave or "").strip().lower().replace(" ", "_")
    if not chave or not nome:
        return False, "Chave e nome são obrigatórios"
    _garantir_tb_modulos()
    with Repositorio() as repo:
        ok = repo.registrar_modulo(
            chave=chave, nome=nome.strip(),
            icone=icone.strip() or "extension",
            rota=rota.strip() or "#",
            ativo=ativo, nativo=False,
        )
    if ok:
        audit_log(ator, "tisosdocfly", "registrar_modulo",
                  f"{chave} ({nome}) rota={rota} {'ativo' if ativo else 'indisponível'}")
        return True, f"Módulo '{nome}' registrado — já disponível nas liberações"
    return False, f"Chave '{chave}' já existe"


def reordenar_modulos(ator, chaves_ordenadas):
    """Reorder display order of modules (sidebar, user management).

    Reordena a ordem de exibição dos módulos no menu lateral e nas
    liberações de usuário. Recebe a lista COMPLETA de chaves na nova ordem;
    a posição (1-based) de cada chave é gravada na coluna `ordem` de
    `tb_modulos`. Audita `modulos_reordenados` com a sequência final.
    Retorna `(ok, msg)`.
    Usa `Repositorio` (SQLAlchemy ORM).
    """
    _garantir_tb_modulos()
    with Repositorio() as repo:
        todas = {m.chave for m in repo.listar_modulos()}
        faltam = todas - set(chaves_ordenadas)
        if faltam:
            chaves_ordenadas = list(chaves_ordenadas) + sorted(faltam)
        ok = repo.reordenar_modulos(chaves_ordenadas)
    if ok:
        audit_log(ator, "tisosdocfly", "modulos_reordenados",
                  ",".join(chaves_ordenadas))
        return True, "Ordem dos módulos atualizada"
    return False, "Erro ao reordenar módulos"


def alterar_rota_modulo(ator, chave, nova_rota):
    """Changes a module's page route (URL) and re-registers it live.

    Altera a rota/URL de um módulo em `tb_modulos` e re-registra a página no
    servidor NiceGUI imediatamente (via `rotas_modulos.registrar_modulo`).
    A `chave` (identificador interno) permanece inalterada. Valida a rota
    (não vazia, caracteres permitidos, sem conflito com outro módulo),
    audita `modulo_rota_alterada` e retorna `(ok, msg)`. Falhas são
    registradas via loguru.
    Usa `Repositorio` (SQLAlchemy ORM).
    """
    nova_rota = "/" + (nova_rota or "").strip().strip("/").lower().replace(" ", "-")
    while "//" in nova_rota:
        nova_rota = nova_rota.replace("//", "/")
    if nova_rota == "/":
        return False, "A URL da página não pode ficar vazia"
    if not re.fullmatch(r"[a-z0-9_\-/]+", nova_rota):
        return False, "URL inválida: use apenas letras, números, hífen, sublinhado e barra"
    _garantir_tb_modulos()
    with Repositorio() as repo:
        conflitante = repo.listar_modulos()
        if any(m.rota == nova_rota for m in conflitante if m.chave != chave):
            return False, f"A URL '{nova_rota}' já está em uso por outro módulo"
        ok = repo.atualizar_modulo(chave, rota=nova_rota)
    if ok:
        from mod_tisosdocfly import rotas_modulos
        rotas_modulos.registrar_modulo(chave, nova_rota)
        audit_log(ator, "tisosdocfly", "modulo_rota_alterada", f"{chave}: {nova_rota}")
        return True, f"URL da página '{chave}' alterada para {nova_rota}"
    return False, f"Erro ao alterar a URL do módulo '{chave}'"


def excluir_modulo(ator, chave):
    """Remove módulo NÃO-nativo do cadastro.

    Usa `Repositorio` (SQLAlchemy ORM).
    """
    _garantir_tb_modulos()
    with Repositorio() as repo:
        mod = repo.obter_modulo(chave)
        if mod is None:
            return False, "Módulo não encontrado"
        if mod.nativo:
            return False, "Módulos nativos do código não podem ser excluídos"
        repo.excluir_modulo(chave)
    audit_log(ator, "tisosdocfly", "excluir_modulo", chave)
    return True, f"Módulo '{chave}' removido do cadastro"


def set_modulo_ativo(ator, chave, ativo=True):
    """Activates/deactivates a module, blocking deactivation of essential ones.

    Ativa ou desativa um módulo em `tb_modulos`. Módulos indispensáveis
    (`MODULOS_INDISPENSAVEIS`) nunca podem ser desativados: a tentativa é
    recusada com `(False, msg)` e registrada em auditoria como
    `modulo_desativado_bloqueado`, sem tocar no banco. Em sucesso retorna
    `(True, "ok")` e audita `modulo_desativado`/`moduloreativado`.
    Usa `Repositorio` (SQLAlchemy ORM).
    """
    if not ativo and chave in MODULOS_INDISPENSAVEIS:
        audit_log(ator, "tisosdocfly", "modulo_desativado_bloqueado", chave)
        return False, f"Módulo '{chave}' é indispensável ao sistema e não pode ser desativado"
    _garantir_tb_modulos()
    with Repositorio() as repo:
        repo.atualizar_modulo(chave, ativo=ativo)
    audit_log(ator, "tisosdocfly", "modulo_desativado" if not ativo else "moduloreativado", chave)
    return True, "ok"


def chaves_nativas():
    """Chaves dos módulos nativos do código (não excluíveis via interface)."""
    _garantir_tb_modulos()
    with Repositorio() as repo:
        mods = repo.listar_modulos()
        return {m.chave for m in mods if m.nativo}


def verificar_senha(texto_plano, hash_senha):
    return bcrypt.checkpw(texto_plano.encode("utf-8"), hash_senha.encode("utf-8"))


def gerar_hash_senha(senha_plana):
    return bcrypt.hashpw(senha_plana.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _gest():
    from mod_gest_cad_usuario import bd_manipulador as g
    return g


def usuario_existe(user_nome):
    """Retorna (senha_hash, perfil, ativo) ou None — lê o BD do módulo de usuários.

    **Fail-soft, e o motivo é o import tardio (03/10/2026).** `_gest()` faz
    `from mod_gest_cad_usuario import bd_manipulador` na hora da chamada, e
    esse import NÃO é garantido: o módulo de usuários roda `init_db()` no topo
    do arquivo, então um banco travado, um schema pela metade ou um reload de
    tela faz a importação falhar aqui. Sem o `try`, a exceção subia pelo
    `autenticar()` — e `autenticar()` é chamado pelo botão da tela de login:
    o servidor devolvia "sistema desconectado" para todo mundo, inclusive para
    quem digitava a senha certa.

    `obter_usuario` já é fail-soft (devolve None em falha de banco); o elo que
    faltava era o `_gest()` e o unpack da tupla, que vivem AQUI e ficavam de
    fora. Devolver `None` é a direção segura: "não achei a conta" nega o login,
    e `perfil_global_de`/`listar_modulos_permitidos` recebem `None` e negam o
    acesso — falha de infraestrutura nunca vira permissão.
    """
    try:
        row = _gest().obter_usuario(user_nome)
        if not row:
            return None
        return (row[2], row[5], row[6])
    except Exception as e:
        from mod_tisosdocfly import observabilidade
        observabilidade.get_logger("tisosdocfly").exception(
            f"usuario_existe('{user_nome}'): falha ao ler o cadastro; "
            "tratando como conta inexistente (login e acesso negados)")
        return None


def listar_usuarios_ativos():
    """Lista usuários ativos para seleção nas telas dos módulos.

    Delega ao módulo de gestão de usuários (núcleo → módulo obrigatório,
    carregado pelo main.py): tuplas (id, user_nome, user_perfil, ...) —
    mesmo formato de `listar_usuarios`. Em falha devolve [] (fail-soft,
    a tela exibe o seletor vazio)."""
    try:
        return _gest().listar_usuarios(filtro_ativo=True)
    except Exception:
        return []


def obter_email_usuario(user_nome):
    """E-mail cadastrado do usuário ("" quando ausente).

    Delega ao módulo de gestão de usuários (núcleo → módulo obrigatório).
    Usado para pré-preencher destinatários nas telas dos módulos."""
    try:
        row = _gest().obter_usuario(user_nome)
        if row and len(row) > 3 and (row[3] or "").strip():
            return (row[3] or "").strip()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
#  Falhas por IP (item 5 do pós-pentest, 24/10/2026)
# ---------------------------------------------------------------------------
# O atraso por usuário ("Aguarde N segundos") era só MENSAGEM — nada dormia
# de verdade no caminho do login, então rajada de tentativas passava sem
# custo. Este bloco fecha a conta: cada falha soma o IP numa janela
# deslizante de 5 minutos (só memória, sem schema novo e sem cross-query),
# e a resposta dorme de verdade antes de voltar.
#
# Sem bloqueio, como manda a decisão de 30/09/2026: conta legítima nunca é
# trancada, e NAT compartilhado só paga espera nas FALHAS — acerto zera e
# segue sem espera. Falha aqui nunca derruba o login: sem IP ou sem relógio,
# o atraso é zero e o fluxo segue igual.
_FALHAS_IP = {}
_FALHAS_IP_TRAV = threading.Lock()
JANELA_IP_SEG = 300
TETO_IP_SEG = 5.0


def _falhas_ip_recentes(ip: str) -> int:
    try:
        ip = (ip or "").strip()
        if not ip:
            return 0
        agora = time.monotonic()
        with _FALHAS_IP_TRAV:
            marcas = [t for t in _FALHAS_IP.get(ip, [])
                      if agora - t < JANELA_IP_SEG]
            _FALHAS_IP[ip] = marcas
            return len(marcas)
    except Exception:
        return 0


def registrar_falha_ip(ip: str) -> float:
    """Soma uma falha do IP e devolve a espera real, em segundos.

    0 na primeira falha (erro de digitação não paga nada); depois rampa de
    ~0,5 s por falha até o teto de 5 s. Quem chama dorme esse tempo ANTES de
    responder — é a espera que o atraso por usuário só anunciava.
    """
    try:
        ip = (ip or "").strip()
        if not ip:
            return 0.0
        with _FALHAS_IP_TRAV:
            _FALHAS_IP.setdefault(ip, []).append(time.monotonic())
        n = _falhas_ip_recentes(ip)
        if n <= 1:
            return 0.0
        return round(min(0.5 * (n - 1), TETO_IP_SEG), 1)
    except Exception:
        return 0.0


def zerar_falhas_ip(ip: str) -> bool:
    """Acerto limpa a conta do IP — sem espera na próxima."""
    try:
        ip = (ip or "").strip()
        if not ip:
            return False
        with _FALHAS_IP_TRAV:
            _FALHAS_IP.pop(ip, None)
        return True
    except Exception:
        return False


def autenticar(user_nome, senha, com_login_canonico=False):
    """Retorna (ok: bool, msg: str). Em caso de sucesso msg é o perfil.

    **Tentativas de login (30/09/2026):** login errado não bloqueia a conta —
    aumenta a espera. Quem erra três vezes espera alguns segundos; um ataque de
    dicionário espera cada vez mais, até o teto, e a conta continua existindo
    para o dia em que a pessoa lembrar a senha. A decisão é do responsável
    (30/09/2026): bloqueio por tentativas vira chamado no DTI toda vez que um
    servidor troca de senha e digita a antiga duas vezes.

    A mensagem é a **mesma** em qualquer falha — "Usuário ou senha inválidos" —
    porque dizer qual dos dois falhou entrega ao atacante a lista de logins
    válidos. O atraso, esse, é intencional e não é informação de nada.

    **LOGIN POR QUALQUER MATRÍCULA (04/10/2026).** Aceita também uma matrícula
    que NÃO é o login da pessoa, desde que a folha registre essa matrícula
    como dela. É a resposta ao caso real de quem tem dois contratos: as duas
    matrículas são dele, e trancar a segunda seria trancar a pessoa por causa
    de um número. A sessão, o perfil e o histórico usam o login canônico (o do
    contrato principal), nunca a matrícula digitada — se usassem, a pessoa
    entraria numa conta que não existe.

    A troca é feita por MATRÍCULA, e nunca por nome: a matrícula é o
    identificador que o portal garante, e nome é ambíguo (a aba Folha tem 5
    casos de nome repetido esperando confirmação). E a falha conta nos DOIS
    nomes, para que trocar de matrícula não compre uma tentativa nova — ver
    `_contar_falha_dos_dois`.

    **POR QUE EXISTE `com_login_canonico`.** Quem chama precisa do login
    CANÔNICO para montar a sessão, e não para adivinhar: com a matrícula
    secundária, `user_nome` aqui é a matrícula digitada, e uma sessão criada
    com ela é uma sessão de uma conta que não existe — o servidor aceitaria
    a senha e depois devolveria a pessoa para o login, sem explicação. Foi
    exatamente o que aconteceu na primeira medição: `autenticar` devolvia
    `True` e a tela voltava para `/login`.

    Devolver um terceiro valor em todos os retornos quebraria os outros
    chamadores (são vários, e nenhum deles quer o login canônico), então o
    desvio é explícito: `com_login_canonico=True` devolve
    `(ok, msg, login_canonico)`. O padrão continua com dois valores.
    """
    if not user_nome or not senha:
        return _saida(False, "Informe usuário e senha", com_login_canonico)
    user_nome = user_nome.strip()

    # LOGIN POR QUALQUER MATRÍCULA (04/10/2026).
    #
    # A pessoa pode ter mais de uma matrícula na folha — foi ativo e demitido
    # em contratos diferentes, ou tem dois contratos no mesmo período. Medido
    # em 09/2026: 5 pessoas assim, 10 registros. O login delas é UMA das
    # matrículas (a do contrato principal), e as outras são matriculas
    # igualmente válidas: quem mudou de secretaria e achou o número novo não
    # deve ficar trancado fora por causa disso.
    #
    # `digitado` fica guardado porque a contagem de falhas precisaldbdo os
    # dois nomes — ver o comentário em `_contar_falha_dos_dois`.
    digitado = user_nome
    if not usuario_existe(user_nome):
        alvo = _login_pela_matricula(user_nome)
        if alvo:
            user_nome = alvo

    row = usuario_existe(user_nome)
    if not row:
        # Conta inexistente também conta tentativa: sem isso o atacante
        # testaria logins inexistentes de graça, e é assim que se descobre a
        # lista de usuários válidos.
        #
        # 03/10/2026: este caminho contava a falha mas devolvia a mensagem
        # SEM o aviso de atraso, enquanto o caminho de conta existente
        # devolvia "Usuário ou senha inválidos. <aviso>". A contagem já
        # estava certa (corrigida em mod_gest_cad_usuario); o que sobrava
        # era a diferença de MENSAGEM — e ela é canal: quem não tem conta
        # percebia que o sistema responde diferente, o que devolve a
        # informação de enumeração que o atraso existia para fechar.
        # Agora os dois caminhos montam a mesma frase.
        #
        # `audit_log` NÃO é chamado aqui de propósito: um login inventado não
        # é um usuário, e gravar evento em nome dele fabricaria registro de
        # auditoria para alguém que não existe.
        falhas = _contar_falha_dos_dois(digitado, user_nome)
        aviso = _texto_atraso_login(falhas)
        return _saida(False, (f"Usuário ou senha inválidos. {aviso}" if aviso
                             else "Usuário ou senha inválidos"),
                      com_login_canonico)
    senha_bd, perfil, ativo = row
    try:
        if not verificar_senha(senha, senha_bd):
            falhas = _contar_falha_dos_dois(digitado, user_nome)
            audit_log(user_nome, "tisosdocfly", "login_falha", f"Tentativa de login inválida para {user_nome}")
            aviso = _texto_atraso_login(falhas)
            return _saida(False, (f"Usuário ou senha inválidos. {aviso}"
                                  if aviso else "Usuário ou senha inválidos"),
                          com_login_canonico)
    except Exception:
        return _saida(False, "Erro interno ao validar credenciais",
                      com_login_canonico)
    # Login certo zera a contagem: sem isso a penalidade vazaria para a sessão
    # seguinte de quem entrou corretamente. Nos DOIS nomes, porque a entrada
    # pode ter vindo por uma matrícula que não é o login.
    _zerar_tentativas_das_dois(digitado, user_nome)
    if not ativo:
        return _saida(False, "Usuário bloqueado. Procure o administrador.",
                      com_login_canonico)

    # Liberação TEMPORÁRIA vencida (27/09/2026). O servidor que entrou sem
    # saber o próprio número teve 4 dias para descobrir — perguntando na
    # secretaria da escola, na unidade de saúde, na garagem ou no almoxarifado.
    # Passados os 4 dias, a conta fecha aqui, no login, que é onde a janela
    # se cumpre. Checar mais tarde (rotina noturna) existiria: o paliativo
    # viraria norma sem ninguém perceber.
    try:
        _gest_ = _gest()
        if _gest_ is not None and _gest_.bloqueio_provisorio_pendente(user_nome):
            _gest_.bloquear_usuario("sistema", user_nome, True)
            audit_log(user_nome, "tisosdocfly", "acesso_provisorio_expirado",
                      "Prazo da liberação temporária de 4 dias vencido; "
                      "conta bloqueada até o DTI liberar")
            return _saida(False, ("Seu acesso temporário de 4 dias terminou. "
                                 "Procure o DTI para liberar seu cadastro "
                                 "depois de atualizar seu telefone."),
                          com_login_canonico)
    except Exception:
        # Falha na checagem NÃO bloqueia ninguém: um erro de banco aqui
        # transformaria todo servidor em "usuário bloqueado" no primeiro dia.
        pass
    return _saida(True, perfil, com_login_canonico, user_nome)


def marcar_senha_aceita(user_nome, aceito=True):
    """Marca (ou desmarca) que a pessoa assinou o aceite de senha fraca.

    A marca vive na sessão, não no banco: vale para a troca que está em curso.
    Gravar "esta pessoa usa senha fraca" para sempre no cadastro seria um
    estigma que ninguém pediu e que ninguém consegue apagar — e ela não é
    verdade: a pessoa pode trocar a senha amanhã. O que fica PARA sempre é o
    **registro do aceite** (quem assinou, quando, sobre o quê), que é prova do
    aviso, não rótulo permanente da pessoa.
    """
    try:
        from nicegui import app as _app
        if aceito:
            _app.storage.user["senha_aceita"] = True
        else:
            # A marca é da SESSÃO e vale só para a troca em curso. Trocar a
            # senha forte de novo não pode carregar pendência nenhuma.
            _app.storage.user.pop("senha_aceita", None)
        return True
    except Exception as e:
        try:
            import logging
            logging.getLogger(__name__).warning(
                f"autenticacao: falha ao marcar aceite de {user_nome}: {e}")
        except Exception:
            pass
        return False


def senha_aceita_por_aceite(user_nome=""):
    """A pessoa assinou o aceite nesta sessão?"""
    try:
        from nicegui import app as _app
        return bool(_app.storage.user.get("senha_aceita"))
    except Exception:
        return False


def registrar_aceite_risco(user_nome, escopo="senha", detalhe=""):
    """Grava o aceite na auditoria. A SENHA NUNCA entra no registro.

    O que fica é: quem assinou, quando, em que tela e que o texto da LGPD foi
    apresentado. É o documento que comprova o dever do controlador (Art. 6º,
    VI e VII, e Art. 46) e a ciência do servidor — os dois lados da questão.
    """
    try:
        from mod_tisosdocfly.bd_manipulador import audit_log
        audit_log(user_nome, "tisosdocfly", "aceite_risco_senha",
                  f"Aceite de senha de risco — escopo={escopo}. "
                  f"LGPD: Art. 6º VI/VII e Art. 46 (medidas de segurança do "
                  f"controlador) + co-responsabilidade do titular. "
                  f"Detalhe: {detalhe[:200] if detalhe else 'sem detalhe'}")
        return True
    except Exception as e:
        try:
            import logging
            logging.getLogger(__name__).exception(
                f"autenticacao: falha ao registrar aceite de {user_nome}: {e}")
        except Exception:
            pass
        return False


def _contar_falha_login(user_nome):
    """Conta o erro e devolve o total na janela. 0 se a contagem falhar."""
    try:
        from mod_tisosdocfly import politica_senha as _ps
        return int(_ps.registrar_falha(user_nome) or 0)
    except Exception:
        try:
            import logging
            logging.getLogger(__name__).warning(
                "autenticacao: não foi possível contar tentativa de login de "
                f"{user_nome}")
        except Exception:
            pass
        return 0


def _saida(ok, msg, com_login_canonico, login_canonico=None):
    """Monta o retorno de `autenticar` no formato pedido pelo chamador.

    Existe para que os sete `return` da função não repitam a condição, e
    para o formato de três valores não existir em dois lugares: acrescentar
    uma linha aqui vale para todos os caminhos, inclusive o de exceção
    interna — e o caminho de exceção é justamente o que ninguém revisa.

    Na falha o login canônico é o que foi digitado: ele não resolveu nada,
    e devolver `None` faria quem chama abrir sessão de usuário `None`.
    """
    if not com_login_canonico:
        return ok, msg
    return ok, msg, (login_canonico or "")


def _login_pela_matricula(entrada):
    """A conta de quem tem esta matrícula, ou `None`.

    Só é chamada quando `usuario_existe` já disse que o nome digitado NÃO é
    login — ou seja, quando nenhum login pode ter esse nome. É o filtro que
    impede a função de virar uma tabela de tradução que reescreve login de
    verdade para o dono de um contrato.

    Fail-soft e devolve `None` em qualquer falha: quem chama trata como
    "conta inexistente", que é a resposta segura.
    """
    try:
        return _gest().login_por_matricula(entrada)
    except Exception:
        from mod_tisosdocfly import observabilidade
        observabilidade.get_logger("tisosdocfly").exception(
            f"_login_pela_matricula('{entrada}'): falha ao resolver matrícula; "
            "tratando como conta inexistente (login negado)")
        return None


def _contar_falha_dos_dois(digitado, resolvido):
    """Conta a falha nos DOIS nomes e devolve o MAIOR total.

    É aqui que está a parte que não é óbvia (04/10/2026). Com login por
    qualquer matrícula, a mesma pessoa atende por DOIS nomes — a matrícula do
    contrato principal e a de qualquer outro contrato dela. Se a contagem
    ficasse só no nome digitado, o atacante ganharia uma margem nova a cada
    matrícula — erra 4 vezes com uma, vira para a outra e começa do zero. O
    atraso existiria, mas valeria a metade do que vale.

    Por isso os dois contam e o que volta é o MAIOR: quem espera o atraso
    espera o maior dos dois, e trocar de matrícula não compra nem uma
    tentativa. Contar nos dois (e não no maior) seria o mesmo efeito com
    uma leitura errada do total — o contador não é só um aviso, ele
    alimenta a tela de bloqueio do administrador.

    Nomes iguais não contam duas vezes: `digitado == resolvido` é o caso de
    quem digitou o login mesmo, e somar ali inflaria a própria penalidade de
    quem errou a senha de uma conta comum.
    """
    total = _contar_falha_login(digitado)
    if resolvido and resolvido != digitado:
        try:
            alt = _contar_falha_login(resolvido)
            if alt is not None and alt > total:
                total = alt
        except Exception:
            pass
    return total


def _zerar_tentativas_das_dois(digitado, resolvido):
    """Zera a contagem nos dois nomes, pelo mesmo motivo da contagem dupla."""
    for nome in {n for n in (digitado, resolvido) if n}:
        try:
            from mod_tisosdocfly import politica_senha as _ps
            _ps.zerar_tentativas(nome)
        except Exception:
            pass


def _texto_atraso_login(falhas):
    """O aviso de 'muitas tentativas', ou "" quando ainda não é o caso."""
    try:
        from mod_tisosdocfly import politica_senha as _ps
        if int(falhas or 0) < _ps.tentativas_maximas():
            return ""
        return _ps.texto_atraso(_ps.calcular_atraso(falhas))
    except Exception:
        return ""


def _podar_sessoes(user_nome):
    """Retenção LGPD: mantém as N sessões mais recentes por usuário.

    Configuração 'sessao_retencao' na tb_config central (padrão 50;
    valor 0 = manter para sempre).
    Usa `Repositorio` (SQLAlchemy ORM).
    """
    try:
        with Repositorio() as repo:
            limite_str = repo.obter_config("sessao_retencao", "50")
            limite = int(limite_str) if limite_str and str(limite_str).strip().lstrip("-").isdigit() else 50
            if limite > 0:
                repo.podar_sessoes(user_nome, limite)
    except Exception:
        pass


def registrar_login(user_nome, modulo=""):
    """Registra sessão e devolve o cookie_hash.

    Usa `Repositorio` (SQLAlchemy ORM) para operações no banco central.
    """
    from .bd_manipulador import garantir_rastreabilidade
    from .contexto import contexto_atual, rotulo_dispositivo, mac_best_effort
    garantir_rastreabilidade()
    ctx = contexto_atual()
    ip = ctx.get("ip")
    ua = ctx.get("ua")
    dispositivo = rotulo_dispositivo(ua) if ua else None
    mac = mac_best_effort(ip)
    timestamp = __import__("datetime").datetime.now()
    cookie_hash = hashlib.sha256(
        f"{user_nome}|{timestamp.strftime('%Y%m%d%H%M%S')}|{__import__('secrets').token_hex(16)}".encode()
    ).hexdigest()[:16]
    with Repositorio() as repo:
        repo.registrar_sessao(
            usuario=user_nome, modulo=modulo,
            cookie_hash=cookie_hash,
            login_timestamp=timestamp,
            ip=ip, user_agent=ua,
            dispositivo=dispositivo, mac=mac,
        )
    audit_log(user_nome, "tisosdocfly", "login",
              f"Login realizado ({modulo or 'sistema'})"
              + (f" de {ip}" if ip else ""))
    _podar_sessoes(user_nome)
    return cookie_hash


def sessao_ativa(user_nome, cookie_hash):
    """True se existe linha de sessão ABERTA com esse hash no banco central.

    Usado pelo guard para revogar navegadores vivos quando o admin encerra
    a sessão (individual ou 'todas').
    Usa `Repositorio` (SQLAlchemy ORM).
    """
    if not cookie_hash:
        return False
    with Repositorio() as repo:
        return repo.sessao_ativa(user_nome, cookie_hash)


def registrar_logout(user_nome, cookie_hash=None):
    """Fecha a sessão deste navegador; sem hash, fecha todas (comportamento antigo)."""
    with Repositorio() as repo:
        if cookie_hash:
            repo.fechar_sessao(user_nome, cookie_hash)
        else:
            repo.fechar_todas_sessoes(user_nome)
    audit_log(user_nome, "tisosdocfly", "logout", "Logout realizado")


def precisa_trocar_senha(user_nome):
    """Verifica flag de troca obrigatória de senha (primeiro acesso).

    Usa `Repositorio` (SQLAlchemy ORM).
    """
    with Repositorio() as repo:
        val = repo.obter_config(f"forcar_troca:{user_nome}", "0")
        return val == "1"


def usuarios_com_troca_pendente():
    """Conjunto de usuários com senha provisória ainda não trocada.

    Usa `Repositorio` (SQLAlchemy ORM).
    """
    with Repositorio() as repo:
        configs = repo.listar_config()
        return {
            c.chave.split(":", 1)[1]
            for c in configs
            if c.valor == "1" and c.chave.startswith("forcar_troca:")
        }


def marcar_trocar_senha(user_nome, forcar=True):
    """Define ou remove a flag de troca obrigatória de senha.

    Usa `Repositorio` (SQLAlchemy ORM).
    """
    with Repositorio() as repo:
        repo.definir_config(f"forcar_troca:{user_nome}", "1" if forcar else "0")


def marcar_trocar_credenciais(user_nome, forcar=True):
    """Define ou remove a flag de troca obrigatória de USUÁRIO + SENHA.

    Usada no primeiro acesso do `master` nativo (força renomear o usuário
    além de trocar a senha). Usa `Repositorio` (SQLAlchemy ORM)."""
    with Repositorio() as repo:
        repo.definir_config(f"forcar_troca_credenciais:{user_nome}",
                            "1" if forcar else "0")


def precisa_trocar_credenciais(user_nome):
    """True se o usuário precisa trocar usuário E senha no primeiro acesso.

    Aplicável ao `master` nativo recém-criado (senha padrão ainda em uso).
    Usa `Repositorio` (SQLAlchemy ORM)."""
    with Repositorio() as repo:
        val = repo.obter_config(f"forcar_troca_credenciais:{user_nome}", "0")
        return val == "1"


def tema_escuro(user_nome):
    """True se o usuário prefere o tema escuro (config per-usuário).

    Preferência de tema individual (não afeta os demais usuários). Chave
    `tema_escuro:<user>` na tb_config central; padrão claro (light)."""
    with Repositorio() as repo:
        val = repo.obter_config(f"tema_escuro:{user_nome}", "0")
        return val == "1"


def definir_tema_escuro(user_nome, escuro):
    """Define a preferência de tema (escuro/claro) do usuário."""
    with Repositorio() as repo:
        repo.definir_config(f"tema_escuro:{user_nome}", "1" if escuro else "0")


def trocar_senha_propria(user_nome, senha_atual, nova_senha):
    """Troca a própria senha, recusando senha fraca ou vazada.

    A regra de força vem de `validador_senha.veredito_bloqueante`, que é
    OFFLINE por contrato: o caminho que decide se a senha é aceita não
    consulta a internet. Numa prefeitura em rede fechada isso não é
    detalhe — se a gravação dependesse da rede, trocar senha dependeria da
    rede, e sem rede o servidor ficaria esperando.

    O veredito de vazamento entra só se a senha já tiver sido consultada antes
    (cache em memória ou em `tb_senha_vazamento_cache`), o que resolve sem
    rede. Nunca é o que impede a troca: quem decide é a análise de força.

    Contas de teste do seed (`qacomum`/`qamaster`) ficam de fora da regra e
    podem manter a própria senha — sem isso a troca obrigatória delas viraria
    beco sem saída. Ver `validador_senha.CONTAS_DE_TESTE`.
    """
    ok, msg = autenticar(user_nome, senha_atual)
    if not ok:
        return False, "Senha atual incorreta"
    if len(nova_senha) < 6:
        return False, "Nova senha deve ter no mínimo 6 caracteres"
    try:
        from mod_tisosdocfly.validador_senha import (CONTAS_DE_TESTE,
                                                 veredito_bloqueante)
        if (user_nome or "").strip().lower() not in CONTAS_DE_TESTE:
            veredito = veredito_bloqueante(nova_senha, user_nome)
            # ACEITE ASSINADO (30/09/2026): senha fraca ou vazada é recusada
            # por padrão, mas a pessoa PODE usar assim mesmo — desde que
            # tenha lido o texto da LGPD e confirmado que assume. A troca de
            # senha é decisão do servidor; o que o sistema registra é que ele
            # soube do risco antes de decidir.
            #
            # O aceite é DA SESSÃO e valida só esta troca: não vira rótulo
            # permanente no cadastro, porque amanhã a pessoa pode trocar a
            # senha e a marca antiga não deve pesar.
            if (veredito is not None and not veredito.get("ok")):
                # PISO DE FORÇA: abaixo de 0,5 a senha não é usável e
                # NENHUM aceite destrava — `inaceitavel` é a diferença que
                # separa "não pode" de "pode, se você assinar".
                if veredito.get("inaceitavel"):
                    motivos = veredito.get("bloqueios") or ["Senha fraca demais."]
                    return False, motivos[0]
                if not senha_aceita_por_aceite(user_nome):
                    motivos = veredito.get("bloqueios") or ["Senha fraca demais."]
                    return False, motivos[0]
            # Troca forçada que mantém a mesma senha não é troca nenhuma: é
            # o usuário passando pela tela sem mudar nada. Não precisa
            # reautenticar: o `autenticar` do topo já confirmou `senha_atual`.
            if (nova_senha or "") == (senha_atual or ""):
                return (False, "A nova senha é igual à senha atual. Escolha "
                        "outra.")
    except Exception:
        # A checagem nunca pode trancar o usuário fora da própria senha: se o
        # validador falhar, a troca segue. O problema fica no log.
        try:
            import logging
            logging.getLogger(__name__).exception(
                "autenticacao: validador de senha falhou; troca prosseguindo")
        except Exception:
            pass
    gest = _gest()
    conn = gest.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tb_usuarios SET user_senha=? WHERE user_nome=?",
            (gerar_hash_senha(nova_senha), user_nome),
        )
        conn.commit()
    finally:
        conn.close()
    marcar_trocar_senha(user_nome, False)
    audit_log(user_nome, "gest_cad_usuario", "trocar_senha", "Usuário alterou a própria senha")
    return True, "Senha alterada com sucesso"


def trocar_credenciais_master(nome_atual, novo_nome, senha_atual, nova_senha,
                              nome_completo="", email="", fone=""):
    """Primeiro acesso do `master` nativo: renomeia o usuário, troca a senha
    e atualiza dados pessoais (nome completo/social, e-mail, telefone).

    Retorna (ok, msg, novo_nome). Só é acionado quando a flag
    `forcar_troca_credenciais:master` está ativa (instalação nova/legado com
    a senha padrão ainda em uso)."""
    ok, msg = autenticar(nome_atual, senha_atual)
    if not ok:
        return False, "Senha atual incorreta", nome_atual
    novo = (novo_nome or "").strip()
    if not novo:
        return False, "Informe um novo nome de usuário", nome_atual
    if novo.lower() == "master":
        return False, "O novo nome de usuário não pode ser 'master'", nome_atual
    if len(nova_senha or "") < 6:
        return False, "Nova senha deve ter no mínimo 6 caracteres", nome_atual
    gest = _gest()
    ok, msg = gest.renomear_usuario(nome_atual, nome_atual, novo,
                                    permitir_master=True)
    if not ok:
        return False, msg, nome_atual
    conn = gest.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tb_usuarios SET user_senha=? WHERE user_nome=?",
            (gerar_hash_senha(nova_senha), novo),
        )
        conn.commit()
    finally:
        conn.close()
    # Dados pessoais (nome completo/social, e-mail, telefone) — opcionais.
    if (nome_completo and nome_completo.strip()) or \
            (email and email.strip()) or (fone and fone.strip()):
        ok_dados, msg_dados = gest.editar_usuario(
            novo, novo,
            email=(email or "").strip() or "__NULO__",
            fone=(fone or "").strip() or "__NULO__",
            nome_completo=(nome_completo or "").strip() or "__NULO__",
            auditar=False)
        if not ok_dados:
            return False, msg_dados, novo
    # limpa as flags (a chave antiga `:master` sai da lista de pendentes)
    marcar_trocar_senha(nome_atual, False)
    marcar_trocar_credenciais(nome_atual, False)
    audit_log(novo, "gest_cad_usuario", "primeiro_acesso",
              f"master renomeado para '{novo}' e senha alterada no primeiro acesso")
    return True, "Credenciais alteradas com sucesso", novo


def editar_meu_perfil(user_nome, email="__NULO__", fone="__NULO__",
                      nome_completo="__NULO__"):
    """Autoatendimento: usuário edita próprios dados pessoais (nunca permissões)."""
    return _gest().editar_usuario(user_nome, user_nome, email=email, fone=fone,
                                  nome_completo=nome_completo)


def nome_de_tratamento(user_nome):
    """Nome exibido para tratamento do usuário (nome completo ou social)."""
    return _gest().nome_de_tratamento(user_nome)


def chaves_desativadas():
    """Chaves de módulos marcados como removidos/desativados."""
    return {c for c, n, i, r, a in modulos_registrados() if not a}


def set_chaves_desativadas(ator, chaves):
    """Compatibilidade: define quais chaves ficam desativadas; demais reativadas.

    Define o conjunto de módulos desativados em `tb_modulos`. Módulos
    indispensáveis (`MODULOS_INDISPENSAVEIS`) são sempre removidos do alvo
    antes da gravação, garantindo que nunca sejam desativados por esta via.
    Audita `modulos_desativados` com a lista final (ou "(nenhum)").
    Usa `Repositorio` (SQLAlchemy ORM).
    """
    alvo = set(chaves) - MODULOS_INDISPENSAVEIS
    with Repositorio() as repo:
        mods = repo.listar_modulos()
        for m in mods:
            repo.atualizar_modulo(m.chave, ativo=(m.chave not in alvo))
    audit_log(ator, "tisosdocfly", "modulos_desativados", ",".join(sorted(alvo)) or "(nenhum)")


def chaves_ativas():
    return [c for c, n, i, r, a in modulos_registrados(somente_ativos=True)]


def papel_no_modulo(user_nome, modulo_chave):
    """'administrador', 'comum' ou None. Delega ao módulo de usuários."""
    try:
        return _gest().obter_papel_no_modulo(user_nome, modulo_chave)
    except Exception:
        return None


def eh_admin_do_modulo(user_nome, modulo_chave):
    return papel_no_modulo(user_nome, modulo_chave) == "administrador"


def perfil_global_de(user_nome):
    """Perfil global do usuário ('comum'|'administrador_modulo'|'administrador_geral')."""
    row = usuario_existe(user_nome)
    return row[1] if row else None


def pode_publicar_no_blog(user_nome):
    """Usuário comum só lê o blog; publicar/comentar/excluir é de administradores."""
    if perfil_global_de(user_nome) == "administrador_geral":
        return True
    return eh_admin_do_modulo(user_nome, "blog")


def validar_acesso_modulo(user_nome, modulo_chave):
    try:
        return _gest().validar_acesso_modulo(user_nome, modulo_chave)
    except Exception:
        return False


def listar_modulos_permitidos(user_nome):
    """Módulos ATIVOS liberados para o usuário (chave, nome, ícone, rota)."""
    row = usuario_existe(user_nome)
    if not row or not row[2]:
        return []
    ativos = {(c, n, i, r) for c, n, i, r, a in modulos_registrados(somente_ativos=True)}
    return [m for m in sorted(ativos) if validar_acesso_modulo(user_nome, m[0])]


def modulos_do_usuario(user_nome):
    """[(chave, nome, icone, rota, ativa)] — TODOS os módulos registrados aos quais
    o usuário tem vínculo; módulos desativados vêm sinalizados (ativa=False),
    para que a interface os destaque com alerta."""
    row = usuario_existe(user_nome)
    if not row or not row[2]:
        return []
    resultado = []
    for chave, nome, icone, rota, ativo in modulos_registrados():
        if validar_acesso_modulo(user_nome, chave):
            resultado.append((chave, nome, icone, rota, bool(ativo)))
    return resultado
