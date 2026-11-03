"""User registration management module — full soft CRUD.

Módulo Gestão de Cadastro de Usuários — soft CRUD completo.

BD próprio: db_mod_gest_cad_usuario.db (WAL).
Tabelas: tb_usuarios, tb_acesso_usuario (perfis POR módulo), tb_modulo_perfil.
Auditoria central com ATOR (quem fez) conforme LGPD.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import time
import re
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_PROJETO = os.path.dirname(BASE_DIR)
DB_CAD_PATH = os.path.join(DIR_PROJETO, "db_mod_gest_cad_usuario.db")

# `administrador_modulo` é perfil GLOBAL, não papel de módulo (03/10/2026,
# comentário escrito porque os dois nomes se pareciam e a auditoria deu o
# aviso). Os dois eixos são independentes:
#
#   perfil global (`tb_usuarios.user_perfil`, validado aqui em PERFIS_GLOBAIS):
#     comum | administrador_modulo | administrador_geral
#   papel no módulo (`tb_acesso_usuario.papel`, validado em PAPEIS_MODULO):
#     comum | administrador
#
# `administrador_modulo` NÃO é synonymo do papel `administrador`: ele existe
# no eixo global e vale para coisas de leitura ampla (o painel do `main.py`,
# `politica_senha.PERFIS_ADMIN`), mas **não** dá escrita em módulo nenhum —
# `definir_papel` recusa qualquer papel fora de PAPEIS_MODULO, e é por papel
# que `obter_papel_no_modulo` autoriza. Ou seja: o perfil global serve, e
# quem escreve em cada módulo continua precisando da linha em
# `tb_acesso_usuario`. Um `administrador_modulo` sem nenhuma linha de acesso
# não escreve nada — que é o padrão seguro.
PERFIS_GLOBAIS = ["comum", "administrador_modulo", "administrador_geral"]
PAPEIS_MODULO = ["comum", "administrador"]
# Tipo de conta (02/11/2026). O produto T! SOS DocFly atende dois públicos:
#
#   interno — equipe que opera a plataforma (cadastro, laudos, administração);
#   cliente — quem contrata o laudo e só enxerga os módulos contratados.
#
# O tipo é um eixo PRÓPRIO, independente do perfil global e do papel por
# módulo. `cliente_id` é uma referência LÓGICA ao cliente cadastrado no
# núcleo (`tb_clientes`), guardada só como inteiro: este módulo nunca faz
# cross-query no banco do núcleo (AGENTS §2.4).
TIPOS_CONTA = ("interno", "cliente")
# Módulos com acesso 'comum' liberado por padrão a todo usuário novo.
#
# A lista é o TRABALHO DIÁRIO de quem trabalha na prefeitura (27/09/2026):
# consultar empenho, editar documento, pedir impressão, achar o ramal de um
# colega, ver as notícias do município e abrir quadro de ordens de serviço do
# próprio setor, e falar no WhatsApp do setor (17/10/2026). Um servidor que
# chega e não tem nenhum destes liberados cai em tela vazia e acha que o
# sistema quebrou.
#
# Ficam de FORA: `usuarios`, `auditoria` e `blog`.
#   - `usuarios` e `auditoria` mexem em conta e registro de todo mundo; são do
#     administrador, concedidos à mão.
#   - `blog` foi deixado de fora deliberadamente: publicar na tisosdocfly é ato de
#     comunicação do município, não privilégio de estar com matrícula ativa.
#     Se a prefeitura quiser, o administrador libera na tela de usuários —
#     e é melhor que a liberação seja uma decisão visível do que um padrão
#     que ninguém nota.
# No T! SOS DocFly só existe o módulo `usuarios` (administrativo), então usuário
# novo nasce SEM acesso a módulo — o administrador libera à mão.
ACESSO_PADRAO_NOVO_USUARIO = ()

# =====================================================================
#  CAMPOS DA FOLHA — A LISTA ÚNICA (03/10/2026)
# =====================================================================
# POR QUE UMA LISTA, E NÃO UM `if` EM CADA LUGAR
#
# O `teto_maximo_mb` do `solicita_impressao` virou decorativo exatamente
# assim: a tela gravava a chave `teto_maximo_mb`, o `bd_manipulador`
# lia `teto_max_mb` e o relatório lia uma terceira. Três lados, três
# nomes, e o defeito só apareceu em produção — com o valor gravado,
# configurado e nunca lido.
#
# Aqui são TRÊS coisas que têm de concordar, e uma lista só que as amarra:
#   1. a DDL das colunas (`_init_db_seguro`, que deriva o `ALTER TABLE
#      ADD COLUMN` check-then-add desta tupla);
#   2. a gravação da carga (`gravar_dados_folha`, que itera os campos);
#   3. a PROTEÇÃO — `editar_usuario` recusa o que estiver nesta lista, e
#      a tela mostra como somente-leitura.
#
# A matrícula NÃO está aqui, e a omissão é deliberada: a matrícula É o
# `user_nome`, o login. Uma coluna `matricula` em `tb_usuarios` seria
# uma segunda fonte para o mesmo dado, e as duas iam divergir no
# primeiro renomeio de credenciais. A matrícula mora em `tb_contratos`
# (onde há N por pessoa) e em `user_nome` (a matrícula do contrato
# principal).
#
# `remuneracao` e `ficha_contracheque` são TEXTO, não número: dinheiro em
# ponto flutuante perde centavo, e o valor entra como o portal publica
# (28/09/2026). O número vem por conta própria, em
# `remuneracao_num`, para o gráfico e para a busca.
CAMPOS_FONTE_FOLHA = (
    ("unidade", "TEXT DEFAULT ''"),            # secretaria
    ("lotacao", "TEXT DEFAULT ''"),            # departamento/setor
    ("cargo", "TEXT DEFAULT ''"),              # cargo
    ("vinculo", "TEXT DEFAULT ''"),            # efetivo, contratado, pensionista...
    ("situacao", "TEXT DEFAULT ''"),           # ativo, férias, demitido, licença...
    ("tipo", "TEXT DEFAULT ''"),               # "Folha do Mês"
    ("admissao", "TEXT DEFAULT ''"),           # data de admissão
    ("exoneracao", "TEXT DEFAULT ''"),         # SEMPRE VAZIA no portal (medido)
    ("regime", "TEXT DEFAULT ''"),             # SEMPRE VAZIO no portal (medido)
    ("carga_horaria", "TEXT DEFAULT ''"),      # SEMPRE VAZIA no portal (medido)
    ("remuneracao", "TEXT DEFAULT ''"),        # "R$ 3.470,83" — texto do portal
    ("ficha_contracheque", "TEXT DEFAULT ''"), # nº da ficha do mês
)

# Os DOIS lados que a folha grava em `tb_usuarios` mas NÃO são "campo da
# folha" no sentido do portal: o carimbo da competência e a situação da
# folha como moteur histórico. `folha_situacao_atual`/`_anterior` e
# `data_movimento` são o que permite responder "ele estava ativo quando
# foi demitido?" — a demissão é um MOVIMENTO (03/10/2026), e movimento
# sem data inicial não tem histórico.
CAMPOS_ESPELHO_FOLHA = (
    ("remuneracao_competencia", "TEXT DEFAULT ''"),
    ("folha_situacao_atual", "TEXT DEFAULT ''"),
    ("folha_situacao_anterior", "TEXT DEFAULT ''"),
    ("data_movimento", "DATETIME"),
)

# Colunas de `tb_usuarios` que NÃO vêm da folha — são do cadastro e
# continuam editáveis. Continuam aqui porque o `ALTER TABLE` check-then-add
# precisa das três listas juntas para ser um laço só.
CAMPOS_CADASTRO = (
    # 1 = o servidor ainda não registrou os telefones.
    # O portal da transparência não publica ramal, então o número só
    # existe se ele mesmo informar no 1º acesso.
    ("telefone_pendente", "INTEGER NOT NULL DEFAULT 0"),
    # Liberação TEMPORÁRIA (27/09/2026). O servidor que não sabe o
    # próprio número entra com 4 dias de prazo e um telefone particular
    # obrigatório; depois disso a conta fecha e só o DTI reabre. Precisa de
    # `provisorio_ate` porque `acesso_provisorio` sozinho não guarda QUANDO
    # o prazo vence.
    ("acesso_provisorio", "INTEGER NOT NULL DEFAULT 0"),
    ("provisorio_ate", "DATETIME"),
    # ---- LIBERAÇÃO PELO DTI (06/10/2026) ----
    # Todo servidor que vem da folha nasce BLOQUEADO (`user_ativo=0`) e só
    # entra depois de passar pelo DTI. Esta coluna é o registro dessa
    # liberação, e existe por um motivo concreto: sem ela a folha reabria
    # tudo a cada boot.
    #
    # `_bloquear_apos_espelho` tem um CAMINHO DE VOLTA — quando a folha deixa
    # de dizer que a pessoa está de fora e a conta está fechada, ela
    # desbloqueia (o pensionista que o RH recontratou). Com a regra nova,
    # "a folha não mandou bloquear" é verdade para os 1.076 servidores
    # Ativos, e o caminho de volta viraria "o DTI fecha, o boot abre". Um
    # servidor que passara pelo DTI perderia o acesso na madrugada, sem
    # erro e sem aviso.
    #
    # Por isso o bloqueio do DTI é AUTORITATIVO: `liberado_pelo_dti=1` diz que
    # alguém passou por lá, e a folha não mexe mais nessa conta. Sem essa
    # coluna, a única forma de respeitar a liberação seria a folha nunca
    # desbloquear — e aí o pensionista recontratado ficaria preso, que é o
    # defeito que o caminho de volta existe para corrigir.
    ("liberado_pelo_dti", "INTEGER NOT NULL DEFAULT 0"),
    ("liberado_dti_em", "DATETIME"),
    ("liberado_dti_por", "TEXT DEFAULT ''"),
    # ---- Pendência de atualização dos dados (28/09/2026) ----
    # O portal da transparência publica a secretaria, o departamento e o
    # cargo. Quando um servidor muda de setor, o sistema NÃO sobrescreve:
    # MARCA, e quem confirma é a própria pessoa (ver `gravar_dados_folha`,
    # que é quem grava a pendência).
    ("pendencia_dados", "TEXT DEFAULT ''"),
    ("pendencia_em", "DATETIME"),
)

# A PROTEÇÃO é derivada, nunca digitada: tudo o que a folha escreve em
# `tb_usuarios` é somente-leitura para quem usa o sistema. Um campo que
# entra em `CAMPOS_FONTE_FOLHA`/`CAMPOS_ESPELHO_FOLHA` fica protegido
# no mesmo instante, sem ninguém lembrar de acrescentar na proteção.
CAMPOS_PROTEGIDOS_FOLHA = (
    tuple(campo for campo, _ in CAMPOS_FONTE_FOLHA)
    + tuple(campo for campo, _ in CAMPOS_ESPELHO_FOLHA)
)

# Coluna de busca: o "haystack" minúsculo e sem acento de UM usuário, com
# os campos da folha, os de cadastro e os identificadores. É por ela que
# a busca roda no SERVIDOR (03/10/2026) em vez de trazer 1.162 usuários
# para o navegador filtrar.
#
# POR QUE UMA COLUNA E NÃO `LOWER(campo) LIKE ?` EM CADA CAMPO
#   `LOWER()` não tira acento, e nem SQLite nem PostgreSQL tiram — então
#   'jose' não acharia 'José' sem um `REPLACE` por acento em cada coluna
#   (12 colunas × ~10 acentos, dentro do SQL, divergindo entre os dois
#   backends). Com a coluna pronta, o SQL é um `LIKE` só, é o mesmo nos
#   dois backends, e a busca por acento funciona.
# É DERIVADA: nada além de `_recalcular_busca_norm` a escreve, e ela
# sempre a reescreve a partir do valor de origem.
COLUNA_BUSCA = "busca_norm"


def campos_folha_nomes():
    """Os nomes dos campos da folha, sem os tipos (uso em log/mensagem)."""
    return [campo for campo, _ in CAMPOS_FONTE_FOLHA]


def _sem_acento(texto):
    """Minúsculo, sem acento, só letras, dígitos e espaços.

    A forma de comparar é a mesma da carga da folha (`_sem_acento`, em
    `carga_folha.py`): o portal grava tudo em caixa alta e sem acento, e
    o cadastro pode ter a grafia certa — comparar sem normalizar dava
    diferença em metade da prefeitura por causa de acento.

    **O FILTRO DE `isalnum()` TAMBÉM TIRA O QUE NÃO É LETRA.** E é
    proposital na busca: `%`, `_` e `!` desaparecem, e uma agulha de
    `LIKE` feita só de coringas não casa com "tudo" — casa com o texto
    inteiro. `carga_folha._sem_acento` é a MESMA regra, e é por isso
    que uma linha de folha com acento no nome casa com a pessoa
    cadastro sem o acento, nas duas direções.
    """
    import unicodedata
    try:
        base = unicodedata.normalize("NFKD", str(texto or ""))
        limpo = "".join(c for c in base if not unicodedata.combining(c))
        return " ".join("".join(c for c in limpo if c.isalnum() or c == " ")
                        .lower().split())
    except Exception:
        return str(texto or "").lower().strip()


def _so_digitos(texto):
    """Só os dígitos do texto — para casar salário com '3470,83' e '3.470,83'.

    A folha publica `R$ 3.470,83`; quem procura digita qualquer um dos
    dois jeitos, e os dois precisam achar. Separar os dígitos resolve sem
    precisar interpretar a moeda: o ponto e a vírgula somem dos dois lados
    e sobra a mesma sequência.
    """
    return "".join(c for c in str(texto or "") if c.isdigit())


def _so_palavras(texto):
    """Só letras e dígitos, minúsculo, espaços normalizados.

    Igual a `_sem_acento` neste módulo. Existe separada porque as DUAS
    normalizações precisam ser idênticas — a coluna `busca_norm` é
    montada com uma, e a agulha é montada com a outra. Se divergirem,
    a busca falha em silêncio: a coluna tem "secretaria municipal de
    educacao" e a agulha vira "secretaria  municipal  de  educacao", o
    `LIKE` não casa, e a tela mostra "nenhum usuário encontrado" para
    um termo que está escrito certo.
    """
    return _sem_acento(texto)


def _normalizar_remuneracao(texto):
    """O salário em duas formas de busca: com separador e só com dígitos.

    `R$ 3.470,83` -> `3.470,83 r$ 3470,83` e `347083`. Guardar as três
    formas no `busca_norm` faz 'professor' achar por cargo, `3470,83`
    achar por salário e `3.470,83` também — sem três colunas e sem
    `LIKE` composto.
    """
    bruto = str(texto or "").strip()
    if not bruto:
        return ""
    partes = [bruto.lower()]
    limpo = _sem_acento(bruto)
    if limpo and limpo != bruto.lower():
        partes.append(limpo)
    digitos = _so_digitos(bruto)
    if digitos and digitos not in partes:
        partes.append(digitos)
    return " ".join(p for p in partes if p)


def _montar_busca_norm(linha, folha_contratos=()):
    """Monta o `busca_norm` de UM usuário a partir de uma linha do banco.

    `folha_contratos` são dicionários com as colunas de `tb_contratos` —
    entra tudo, porque uma pessoa com dois contratos é buscada por
    qualquer um deles (o contrato secundário é o que costuma trazer o
    cargo novo).
    """
    try:
        dados = linha if isinstance(linha, dict) else {}
        campos = []
        for chave in ("user_nome", "user_nome_completo", "user_email",
                      "user_fone", "user_perfil"):
            valor = dados.get(chave)
            if valor:
                campos.append(str(valor))
        if dados.get("telefone_pendente"):
            campos.append("telefone pendente")
        # os campos da folha entram pela LISTA ÚNICA, não por nome solto:
        # acrescentar um campo em CAMPOS_FONTE_FOLHA passa a ser buscável
        # aqui no mesmo instante, sem esquecer nada.
        for chave, _def in CAMPOS_FONTE_FOLHA:
            valor = dados.get(chave)
            if valor:
                campos.append(str(valor))
        for contrato in folha_contratos or ():
            if not isinstance(contrato, dict):
                continue
            for chave, _def in CAMPOS_FONTE_FOLHA:
                valor = contrato.get(chave)
                if valor:
                    campos.append(str(valor))
            if contrato.get("matricula"):
                campos.append(str(contrato["matricula"]))
        rem = _normalizar_remuneracao(dados.get("remuneracao"))
        if rem:
            campos.append(rem)
        texto = " ".join(_sem_acento(c) for c in campos if c)
        return " ".join(texto.split())
    except Exception as e:
        _log().exception(f"_montar_busca_norm: falha ao montar | {e}")
        return ""


def _colunas_de_busca():
    """As colunas que `_recalcular_busca_norm` lê, em ordem fixa.

    Lista explícita e NÃO `SELECT *`: `cur.description` nem sempre vem
    populado no proxy do PostgreSQL depois do `fetchone`, e o nome da
    coluna é o que a busca depende — uma coluna faltando aqui é uma
    coluna que some da busca sem erro nenhum.
    """
    fixas = ("user_nome", "user_nome_completo", "user_email", "user_fone",
             "user_perfil", "telefone_pendente")
    return fixas + tuple(campo for campo, _ in CAMPOS_FONTE_FOLHA)


def _recalcular_busca_norm(cur, user_nome):
    """Reescreve `busca_norm` de UM usuário, com o cursor já aberto.

    Chamada em todo ponto que mexe em campo pesquisável — é o que segura
    a promessa de que a busca não fica velha. `reindexar_busca()` faz o
    passe completo, para o caso de um dado que entrou por fora (restauração
    de backup, `INSERT` manual).
    """
    try:
        # `", ".join` e NÃO o tuple cru: `SELECT ('a', 'b')` é uma LINHA em
        # SQLite, não uma lista de colunas, e o erro que sobe é "row value
        # misused" — que não diz nada sobre a causa.
        cur.execute(f"SELECT {', '.join(_colunas_de_busca())} "
                    f"FROM tb_usuarios WHERE user_nome=?", (user_nome,))
        linha = cur.fetchone()
        if not linha:
            return False
        dados = dict(zip(_colunas_de_busca(), linha))
        cur.execute("SELECT * FROM tb_contratos WHERE user_nome=?", (user_nome,))
        contratos = []
        colunas_contrato = [c for c, _ in CAMPOS_FONTE_FOLHA] + ["matricula"]
        for c in cur.fetchall() or ():
            contratos.append(dict(zip(colunas_contrato, c)))
        texto = _montar_busca_norm(dados, contratos)
        cur.execute(f"UPDATE tb_usuarios SET {COLUNA_BUSCA}=? WHERE user_nome=?",
                    (texto, user_nome))
        return True
    except Exception as e:
        _log().exception(f"_recalcular_busca_norm: falha em {user_nome} | {e}")
        return False


def reindexar_busca(ator="sistema"):
    """Reescreve `busca_norm` de TODO mundo. Passe completo.

    Roda em `init_db` e está exposto para quando um dado entrou por fora
    (restauração de backup, carga antiga, `INSERT` manual). Custa o que
    uma varredura de mil e poucas linhas custa: medido em
    `tests/test_carga_contratos.py`.
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_nome FROM tb_usuarios")
        nomes = [r[0] for r in (cur.fetchall() or ()) if r and r[0]]
        for nome in nomes:
            _recalcular_busca_norm(cur, nome)
        _commit_com_retry(conn, contexto="reindexar_busca")
        _log().info(f"busca reindexada: {len(nomes)} usuário(s) por {ator}")
        return True, f"{len(nomes)} usuário(s) reindexado(s) para a busca."
    except Exception as e:
        _rollback_seguro(conn, contexto="reindexar_busca")
        _log().exception(f"reindexar_busca: falha | {e}")
        return False, "Erro ao reindexar a busca."
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def get_connection():
    """Opens a connection to the module's own database (FKs enabled).

    Conexão via `banco_conexao.conexao` — SQLite (db_mod_gest_cad_usuario.db,
    WAL) ou PostgreSQL (DATABASE `db_mod_gest_cad_usuario`). O
    `busy_timeout=5000`+WAL+`foreign_keys=ON` já vêm herdados do núcleo
    (`mod_tisosdocfly.banco_conexao.conexao`); os PRAGMAs abaixo são
    reaplicação idempotente (no PG o proxy os neutraliza sem efeito)."""
    try:
        from mod_tisosdocfly.banco_conexao import conexao
        conn = conexao("usuarios")
        if conn is None:
            raise RuntimeError("Falha ao abrir conexão do módulo Gestão de Usuários")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    except Exception as e:
        _log().exception(f"get_connection: falha ao abrir conexão | {e}")
        raise


def _eh_violacao_unicidade(exc):
    """True para violação de unicidade em SQLite e PostgreSQL.

    SQLite: `sqlite3.IntegrityError: UNIQUE constraint failed`.
    PostgreSQL (psycopg2): `UniqueViolation` / SQLSTATE 23505 /
    `duplicate key value`. Fallback genérico por mensagem para não
    importar `sqlite3`/`psycopg2` aqui (compatível com o proxy PG)."""
    try:
        nome = type(exc).__name__ or ""
        if nome in ("IntegrityError", "UniqueViolation"):
            texto = str(exc).lower()
            if ("unique" in texto or "duplicate" in texto
                    or "23505" in texto or "already exists" in texto):
                return True
            # IntegrityError sem mensagem clara: presume unicidade apenas
            # se o nome for UniqueViolation; senão deixa o chamador decidir.
            return nome == "UniqueViolation"
        texto = str(exc).lower()
        return ("unique constraint" in texto or "uniqueviolation" in texto
                or "duplicate key" in texto or "23505" in texto)
    except Exception:
        return False


def _eh_bloqueio_banco(exc):
    """True quando o erro é contenção transitória do SQLite."""
    try:
        return "database is locked" in str(exc).lower()
    except Exception:
        return False


def _rollback_seguro(conn, contexto=""):
    """Rollback best-effort que nunca derruba o chamador (AGENTS §3.2)."""
    try:
        if conn is not None:
            conn.rollback()
    except Exception as e:
        try:
            _log().warning(f"_rollback_seguro[{contexto}]: {e}")
        except Exception:
            pass


def _commit_com_retry(conn, contexto="", tentativas=3, espera_s=0.05):
    """Commit com retry curto em `database is locked` (SQLite/WAL).

    Tenta `conn.commit()` até `tentativas` vezes quando a falha for
    contenção transitória; outra falha propaga ao chamador (que faz
    rollback + `logger.exception`, AGENTS §3.2). `busy_timeout=5000`
    já vem herdado de `banco_conexao.conexao` — o retry cobre apenas
    a janela residual de contenção."""
    try:
        ultima = None
        for tentativa in range(1, tentativas + 1):
            try:
                conn.commit()
                return True
            except Exception as e:
                ultima = e
                if _eh_bloqueio_banco(e) and tentativa < tentativas:
                    try:
                        time.sleep(espera_s * tentativa)
                    except Exception:
                        pass
                    continue
                raise
        if ultima is not None:
            raise ultima
        return True
    except Exception:
        raise


def _conexao_segura():
    """Opens the module connection logging the failure (returns None on error).

    Versão fail-soft de `get_connection`: em falha loga a causa e devolve
    None — os chamadores tratam None como estado de erro sem derrubar."""
    try:
        return get_connection()
    except Exception as e:
        _log().exception(f"_conexao_segura: falha ao abrir conexão | {e}")
        return None


def _central():
    """Opens a connection to the CENTRAL database (sessions/config only)."""
    try:
        from mod_tisosdocfly.bd_conexao import get_connection as gc
        return gc()
    except Exception as e:
        _log().exception(f"_central: falha ao abrir conexão central | {e}")
        raise


def _audit(ator, acao, alvo, detalhe=""):
    """Writes a central audit record for this module (LGPD trail)."""
    try:
        from mod_tisosdocfly.bd_manipulador import audit_log
        audit_log(ator or "sistema", "gest_cad_usuario", acao,
                  f"Alvo: {alvo}" + (f" | {detalhe}" if detalhe else ""))
    except Exception as e:
        _log().exception(f"_audit: falha ao registrar auditoria | {e}")


def _log():
    """Logger central (loguru) — arquivo dedicado logs/gest_cad_usuario_<data>.log."""
    from mod_tisosdocfly import observabilidade
    return observabilidade.get_logger("gest_cad_usuario")


def senha_minima():
    """Minimum password length (characters) configured for the module.

    Política de senha mínima (em caracteres) do módulo, editável em
    tb_config central na chave `usuarios_senha_min` (painel Administração
    da Gestão de Usuários, 4–32, padrão 6). Fail-soft: em falha de leitura
    registra warning no loguru e retorna 6."""
    try:
        from mod_tisosdocfly.bd_conexao import get_config
        return max(4, int(get_config("usuarios_senha_min", "6")))
    except Exception as e:
        _log().warning(f"senha_minima: falha ao ler config; usando padrão 6 | {e}")
        return 6


def _troca_de_credencial_do_master_concluida():
    """True quando o `master` nativo JÁ foi renomeado no primeiro acesso.

    Lê a chave `forcar_troca_credenciais:master` do `tb_config` central. Ela
    vale '1' enquanto a troca está PENDENTE e '0' quando a troca CONCLUÍ
    (`autenticacao.trocar_credenciais_master` zera no fim, depois do rename).

    Serve de MARCADOR para o seed de `init_db`: sem ele, o seed recria
    `master/master` a cada reinício depois da troca, porque o rename tira o
    nome da tabela e a guarda `not obter_usuario("master")` volta a ser
    verdadeira (29/09/2026).

    Fail-soft: em falha de leitura devolve False — ou seja, SEMEIA. Semear
    numa instalação que já trocou é um transtorno; deixar de semear numa
    instalação nova tranca o admin para fora sem a conta de fábrica. Na
    dúvida, a conta existe.
    """
    try:
        from mod_tisosdocfly.bd_conexao import get_config
        return (get_config("forcar_troca_credenciais:master", "") or "").strip() == "0"
    except Exception as e:
        _log().warning(f"_troca_de_credencial_do_master_concluida: falha ao ler "
                       f"a marca; assumindo troca pendente | {e}")
        return False


# Contas de fábrica que a semente de `init_db` cria (04/10/2026).
#
# A lista é a fonte da verdade das DUAS coisas que precisam concordar entre
# si: quem a semente cria, e quem recebe o marcador de "removido pelo
# administrador" na exclusão. Estando em dois lugares, o botão "Apagar" da
# tela de credenciais poderia apagar `qacomum` e a semente trazer de volta no
# boot seguinte — que foi exatamente o que aconteceu.
#
# `master` NÃO está aqui de propósito: ele é de fábrica, mas a proteção dele é
# outra e mais antiga, `_troca_de_credencial_do_master_concluida`, porque o
# master é RENOMEADO e não apagado — e o `excluir_usuario_definitivo` recusa
# `master` de qualquer forma.
CONTAS_DE_FABRICA = ("qacomum", "qamaster")


def conta_de_fabrica_removida(login: str) -> bool:
    """True quando o ADMINISTRADOR já apagou esta conta de fábrica.

    Lê a chave `conta_fabrica_removida:<login>` do `tb_config` central. Ela
    é gravada com '1' por `excluir_usuario_definitivo` no momento da
    exclusão, e é o que impede a semente de `init_db` de recriar a conta no
    boot seguinte.

    POR QUE UM MARCADOR, E NÃO SÓ A AUSÊNCIA (04/10/2026, pedido do
    responsável): sem ele, apagar `qacomum`/`qamaster` da tela de credenciais
    do `master` não resolvia nada — a semente é idempotente eIOCRIA a conta a
    cada reinício enquanto ela não existir, então o botão voltaria no boot
    seguinte. É o mesmo mecanismo de `_troca_de_credencial_do_master_concluida`
    (que usa `forcar_troca_credenciais:master`), e pelo mesmo motivo: uma vez
    gravado, o estado não volta atrás sozinho.

    O QUE ISSO NÃO É: remoção automática. A conta só some porque o
    ADMINISTRADOR apertou o botão — o AGENTS.md §8.2.0 proíbe o código de
    apagar conta de fábrica por conta própria, e nada aqui faz isso. O
    marcador registra uma decisão já tomada; não toma a decisão.

    Fail-soft: em falha de leitura devolve False, e aí a conta é semeada.
    Na dúvida entre "não criar" e "criar", criar é o erro menor — uma conta de
    teste a mais incomoda; a conta que o administrador não conseguiu criar
    tranca a ele para fora da própria instalação.
    """
    try:
        from mod_tisosdocfly.bd_conexao import get_config
        return (get_config(f"conta_fabrica_removida:{login}", "") or "").strip() == "1"
    except Exception as e:
        _log().warning(f"conta_de_fabrica_removida: falha ao ler a marca de "
                       f"'{login}'; assumindo conta presente | {e}")
        return False


def init_db():
    """Creates/migrates the schema and seeds (idempotent bootstrap).

    Cria `tb_usuarios` e `tb_acesso_usuario` (FK CASCADE/UPDATE CASCADE),
    aplica migrações idempotentes (soft delete `user_deletado`,
    `user_nome_completo`, `user_motivo_exclusao`), migra legados (usuários do
    banco central, CSV de módulos), semeia `master`/`master` com troca
    obrigatória (auto-cura enquanto a senha padrão existir) e os usuários de
    teste QA (`qacomum`/`qamaster`). Executado no import e pelo bootstrap.

    Fecha com `reindexar_busca()`: o `busca_norm` é DERIVADO, e uma coluna
    derivada que ninguém reconstrói é uma coluna que fica velha. O boot é
    o único lugar em que um passe completo de 1.162 linhas é aceitável —
    no dia a dia quem atualiza é `_recalcular_busca_norm`, na própria
    gravação.
    """
    try:
        _init_db_seguro()
    except Exception as e:
        _log().exception(f"init_db: falha no bootstrap | {e}")
    try:
        reindexar_busca(ator="init_db")
    except Exception as e:
        _log().exception(f"init_db: falha ao reindexar a busca | {e}")


SENHA_PROVISORIA_LOCAL = "123456"


def _assegurar_troca_de_senha_provisoria(conn, user_nome):
    """Reassina a troca obrigatória de quem AINDA tem a senha provisória.

    EN: Re-signs the forced change for whoever still holds the provisional
    password.

    PT-BR: Reassina a troca obrigatória de quem ainda tem a senha provisória.

    **A regra:** a troca é exigida enquanto a senha for a provisória, e
    NUNCA depois de trocada. Por isso a conferência é pelo **hash** (bcrypt
    compara, não descriptografa) e não pela ausência da chave — uma chave
    que sumiu tem de dar direito a quem já trocou, e não a quem nunca trocou.

    Quem já trocou tem a flag em '0' (é o que `marcar_trocar_senha(nome, False)`
    grava ao concluir) e sai daqui intocado.

    O custo é uma comparação bcrypt por conta, e por isso isto roda só onde a
    conta está em dúvida — na reconciliação do seed. Fazer isso para as 650
    contas da folha a cada boot custaria minutos de CPU para provar o que já
    está provado: elas são criadas com a flag (`criar_usuario`,
    `bd_manipulador.py:1846`), e a troca concluída grava o '0'.

    Nunca levanta: uma falha aqui não pode derrubar o `init_db`.

    Contas de teste (15/10/2026, decisão do responsável): `qacomum` e
    `qamaster` NUNCA reasssinam — são usadas pelos testes e scripts com a
    senha padrão `123456`, sem fluxo de login. Produção não é afetada: as
    contas reais continuam reasssinando como sempre.
    """
    try:
        if user_nome in ("qacomum", "qamaster"):
            return False
        cur = conn.cursor()
        cur.execute("SELECT user_senha FROM tb_usuarios WHERE user_nome=?",
                    (user_nome,))
        linha = cur.fetchone()
        if not linha or not linha[0]:
            return False
        import bcrypt
        bruto = linha[0].encode() if isinstance(linha[0], str) else linha[0]
        if not bcrypt.checkpw(SENHA_PROVISORIA_LOCAL.encode(), bruto):
            return False
        from mod_tisosdocfly.autenticacao import marcar_trocar_senha
        marcar_trocar_senha(user_nome, True)
        _log().info(
            f"{user_nome}: senha ainda e a provisoria — troca obrigatoria "
            f"reassinada")
        return True
    except Exception as e:
        try:
            _log().warning(
                f"_assegurar_troca_de_senha_provisoria({user_nome}): {e}")
        except Exception:
            pass
        return False


def _init_db_seguro():
    """Runs the real init_db bootstrap inside a protected wrapper.

    Executa o bootstrap de init_db isolado para receber o try/except do
    entry point — falha nunca deve derrubar o import do módulo. Cada
    bloco usa check-then-add idempotente (portável SQLite↔PG via proxy
    `PRAGMA table_info`→`information_schema`; `INSERT OR IGNORE`→
    `ON CONFLICT DO NOTHING`) com `_commit_com_retry` (busy_timeout
    herdado + retry em `database is locked`) e rollback em falha
    parcial. Seed `master`/`qacomum`/`qamaster` preservado idempotente
    (AGENTS §8.2). Sem CrudBase aqui por risco no seed (fila futura)."""
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_nome TEXT NOT NULL UNIQUE,
                user_senha TEXT NOT NULL,
                user_email TEXT,
                user_fone TEXT,
                user_perfil TEXT NOT NULL DEFAULT 'comum',
                user_ativo INTEGER NOT NULL DEFAULT 1,
                data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
                -- `modulo_acesso` é COLUNA DE MIGRAÇÃO, não campo vivo (03/10/2026).
                -- Ela existe porque a migração única "BD central -> BD do módulo"
                -- (mais abaixo, nesta função) lia uma lista de módulos separada por
                -- vírgula e a transformava em linhas de `tb_acesso_usuario`. Desde
                -- então o acesso vive em `tb_acesso_usuario`, e ninguém escreve
                -- nem lê esta coluna fora daquela migração — o que é o esperado:
                -- apagá-la quebraria a migração em toda instalação que ainda
                -- tiver `tb_usuarios` no banco central. Mantida, e só por isso.
                modulo_acesso TEXT DEFAULT NULL,
                -- Tipo de conta: 'interno' (equipe T! SOS DocFly) ou 'cliente'
                -- (contratante do laudo). `cliente_id` aponta logicamente
                -- para o cliente do núcleo, sem FK entre bancos.
                user_tipo TEXT DEFAULT 'interno',
                cliente_id INTEGER
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_acesso_usuario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_nome TEXT NOT NULL REFERENCES tb_usuarios(user_nome) ON DELETE CASCADE,
                modulo_chave TEXT NOT NULL,
                papel TEXT NOT NULL DEFAULT 'comum',
                liberado_por TEXT,
                data_liberacao DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_nome, modulo_chave)
            )
        """)
        _commit_com_retry(conn, contexto="init_db:ddl_base")

        # ---- Telefones múltiplos por usuário (27/09/2026) ----
        # Antes cabia UM telefone em `tb_usuarios.user_fone`, e a lista
        # telefônica só conseguia mostrar esse. Um servidor tem, no mínimo,
        # celular particular, celular da empresa e fixo da empresa, e é o
        # telefone DA EMPRESA que pode entrar na lista. Por isso a tabela
        # separada, com `papel` dizendo a quem o número pertence.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_telefone_usuario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_nome TEXT NOT NULL REFERENCES tb_usuarios(user_nome) ON DELETE CASCADE,
                numero TEXT NOT NULL,
                papel TEXT NOT NULL DEFAULT 'empresa',
                tipo TEXT NOT NULL DEFAULT 'celular',
                principal INTEGER NOT NULL DEFAULT 0,
                visivel INTEGER NOT NULL DEFAULT 0,
                recado INTEGER NOT NULL DEFAULT 0,
                whatsapp INTEGER NOT NULL DEFAULT 0,
                data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ---- Consentimento de exibição do telefone (27/09/2026) ----
        # Ser servidor público não significa ter o número publicado: o prefeito
        # não quer o celular particular na lista, e o responsável pela defesa
        # civil precisa que o seu apareça para todos ligarem. Então a publicação
        # é ESCOLHA de cada um — `visivel` — e não padrão do sistema.
        cur.execute("PRAGMA table_info(tb_telefone_usuario)")
        cols_tel = {r[1] for r in cur.fetchall()}
        if "visivel" not in cols_tel:
            cur.execute("ALTER TABLE tb_telefone_usuario "
                        "ADD COLUMN visivel INTEGER NOT NULL DEFAULT 0")
        # ---- Telefone de recado (27/09/2026) ----
        # Quem não tem linha própria dá o telefone do SETOR, onde alguém
        # anota a mensagem e passa adiante: o da coleta de lixo é o da
        # garagem, o da merenda escolar é o da secretaria da escola. Sem esta
        # marcação, o número do setor entra na lista parecendo linha pessoal
        # de quem não atende — e a pessoa é desconsiderada por isso.
        if "recado" not in cols_tel:
            cur.execute("ALTER TABLE tb_telefone_usuario "
                        "ADD COLUMN recado INTEGER NOT NULL DEFAULT 0")
        # ---- Marca WhatsApp (16/10/2026) ----
        # Diz se o número é WhatsApp — outros módulos (avisos, agenda)
        # usam isso para escolher o canal. Coluna portátil como as demais
        # (`INTEGER ... DEFAULT 0` vale nos dois backends).
        if "whatsapp" not in cols_tel:
            cur.execute("ALTER TABLE tb_telefone_usuario "
                        "ADD COLUMN whatsapp INTEGER NOT NULL DEFAULT 0")
        _commit_com_retry(conn, contexto="init_db:consentimento_telefone")

        # ---- Tentativas de login (30/09/2026) ----
        # Uma linha por usuário, com a contagem e a última falha. Existe para
        # o ATRASO progressivo de `mod_tisosdocfly/politica_senha`: o login errado
        # não trava a conta, mas espera mais a cada erro, o que encarece o
        # ataque de dicionário sem fechar o acesso de quem só esqueceu a senha.
        #
        # `janela_min` é a hora da ÚLTIMA falha, e a contagem só vale dentro da
        # janela (15 min). Sem isso a conta ficaria lenta para sempre depois de
        # um período ruim de digitação — e a pessoa aprenderia a reclamar do
        # sistema, não a escolher senha melhor.
        # ---- Tentativas de login (30/09/2026) ----
        # UMA LINHA por usuário, com a contagem e a última falha. É para o
        # ATRASO progressivo de `mod_tisosdocfly/politica_senha`: o login errado
        # não trava a conta, mas espera mais a cada erro.
        #
        # Decisão do responsável (30/09/2026): SEM BLOQUEIO, só atraso. Travar a
        # conta por tentativas transforma "troquei a senha e digitei a antiga
        # duas vezes" em chamado no DTI — e quem mais digita a senha errada é
        # justamente quem trabalha com ela o dia inteiro. A espera encarece o
        # ataque de dicionário sem fechar a conta de servidor nenhum.
        #
        # `ultima_falha` marca a janela (15 min). Passada a janela a contagem
        # vale zero: a conta não fica lenta para sempre depois de um período
        # ruim de digitação. Login CERTO zera na hora — senão a penalidade
        # vazaria para a sessão seguinte de quem entrou corretamente.
        #
        # `bloqueada_ate` NÃO é usada e não é escrita (decisão de 30/09/2026:
        # atraso progressivo, nunca bloqueio). A coluna fica de propósito: ela
        # existia desde a versão com bloqueio, e "remover a coluna" num banco
        # que não é versionado exigiria `ALTER TABLE ... DROP COLUMN` em
        # SQLite e PostgreSQL, para apagar um dado que é sempre NULL e não
        # custa nada. Ver `tests/test_login_atraso_progressivo.py`, que trava
        # a decisão: nenhuma tela, nenhuma função escreve esta coluna.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_login_tentativas (
                user_nome TEXT PRIMARY KEY
                    REFERENCES tb_usuarios(user_nome) ON DELETE CASCADE,
                falhas INTEGER NOT NULL DEFAULT 0,
                ultima_falha DATETIME DEFAULT CURRENT_TIMESTAMP,
                bloqueada_ate DATETIME
            )
        """)
        _commit_com_retry(conn, contexto="init_db:tentativas_login")

        # ---- Histórico de remuneração (28/09/2026) ----
        # Uma linha por competência, só quando o VALOR MUDA. Guardar todo mês
        # mesmo sem mudança encheria a tabela de repetição; e guardar só o
        # valor atual perderia o histórico, que é a única coisa que interessa
        # quando se pergunta "quanto ele recebeu em março?". A tisosdocfly roda
        # o sync mensalmente, então a linha do mês é o registro.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_remuneracao_historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_nome TEXT NOT NULL REFERENCES tb_usuarios(user_nome)
                    ON DELETE CASCADE,
                competencia TEXT NOT NULL,
                remuneracao TEXT NOT NULL DEFAULT '',
                ficha_contracheque TEXT DEFAULT '',
                registrado_em DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_remuneracao_historico "
                    "ON tb_remuneracao_historico(user_nome, competencia)")

        # =================================================================
        #  PESSOA × CONTRATO, HISTÓRICO DE MOVIMENTOS E HISTÓRICO SALARIAL
        #  (03/10/2026)
        # =================================================================
        #
        # `tb_usuarios` é a PESSOA e sempre foi. O que mudou é que uma
        # pessoa pode ter MAIS DE UM contrato com a prefeitura — e o
        # portal publica um registro por matrícula, não por pessoa.
        # Medido em 09/2026: 1.159 matrículas distintas em 1.159 linhas
        # (matrícula não se repete) e CINCO nomes normalizados repetidos
        # em matrículas diferentes. São esses cinco que exigem a tabela:
        # sem ela, a segunda matrícula de um professor que acumula um
        # contrato vira uma PESSOA nova, com login novo, telefone novo e
        # senha nova — o mesmo ser humano entrando duas vezes no sistema.
        #
        # `matricula` é UNIQUE porque é o identificador que o portal
        # garante; `principal` marca de qual delas é o LOGIN (a de menor
        # número), para o administrador ver sem precisar contar.
        # `mesmo_nome_de` é a MARCA DE DÚVIDA: nome igual pode ser a mesma
        # pessoa ou homônimo, e o sistema não decide isso sozinho — ele
        # registra com quem colide e entrega a decisão para a tela.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_contratos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_nome TEXT NOT NULL REFERENCES tb_usuarios(user_nome)
                    ON DELETE CASCADE ON UPDATE CASCADE,
                matricula TEXT NOT NULL UNIQUE,
                unidade TEXT DEFAULT '',
                lotacao TEXT DEFAULT '',
                cargo TEXT DEFAULT '',
                vinculo TEXT DEFAULT '',
                situacao TEXT DEFAULT '',
                tipo TEXT DEFAULT '',
                admissao TEXT DEFAULT '',
                exoneracao TEXT DEFAULT '',
                regime TEXT DEFAULT '',
                carga_horaria TEXT DEFAULT '',
                remuneracao TEXT DEFAULT '',
                ficha_contracheque TEXT DEFAULT '',
                competencia TEXT DEFAULT '',
                data_carga DATETIME DEFAULT CURRENT_TIMESTAMP,
                -- `principal` marca o contrato cujo número é o LOGIN da
                -- pessoa (o de MENOR matrícula, ver
                -- `definir_principal_por_menor_matricula`). Começa valendo
                -- 1 porque uma pessoa com UM contrato tem, por definição,
                -- aquele como principal — e o valor errado aqui só é
                -- corrigido no segundo passo da carga.
                principal INTEGER NOT NULL DEFAULT 1,
                mesmo_nome_de TEXT DEFAULT '',
                busca_norm TEXT DEFAULT ''
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_contratos_user "
                    "ON tb_contratos(user_nome)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_contratos_revisar "
                    "ON tb_contratos(mesmo_nome_de)")

        # ---- Ficha detalhada por matrícula (09/10/2026) ----
        # `coleta_kbp.py` busca `ServidorDetalhes` (CPF parcial + base /
        # proventos / descontos / líquido + verbas) e o loader
        # `carregar_detalhe_ficha` grava aqui: UMA LINHA POR FICHA (chave
        # `ficha`), idempotente por (ficha, competencia) — recarregar o
        # mesmo arquivo não duplica nada. O CPF parcial mora também no
        # espelho da pessoa (`tb_usuarios.cpf_parcial`, abaixo) porque a
        # regra "mesmo CPF = mesma pessoa" decide no LOGIN, não na ficha.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_detalhe_ficha (
                ficha TEXT PRIMARY KEY,
                matricula TEXT NOT NULL DEFAULT '',
                user_nome TEXT NOT NULL DEFAULT '',
                cpf_parcial TEXT NOT NULL DEFAULT '',
                nascimento TEXT NOT NULL DEFAULT '',
                salario_base TEXT NOT NULL DEFAULT '',
                proventos TEXT NOT NULL DEFAULT '',
                descontos TEXT NOT NULL DEFAULT '',
                liquido TEXT NOT NULL DEFAULT '',
                n_itens INTEGER NOT NULL DEFAULT 0,
                itens_json TEXT NOT NULL DEFAULT '[]',
                competencia TEXT NOT NULL DEFAULT '',
                atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_detalhe_mat "
                    "ON tb_detalhe_ficha(matricula)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_detalhe_cpf "
                    "ON tb_detalhe_ficha(cpf_parcial)")
        _commit_com_retry(conn, contexto="init_db:detalhe_ficha")

        # ---- Diárias por favorecido por ano (11/10/2026) ----
        # UMA LINHA POR FAVORECIDO POR ANO (chave `ano + cd_fornecedor`):
        # o grid do portal (`DespesasGetFornecedorGrid`) devolve o consolidado
        # anual (`idExercicio` + `vlPago` do ano inteiro), e o mesmo
        # `cd_fornecedor` volta em 2025 e 2026 com valores diferentes.
        # `cpf_parcial` é a LIGAÇÃO (mesmo formato mascarado que
        # `tb_usuarios.cpf_parcial` guarda); `user_nome` é o vínculo resolvido
        # na gravação — linha sem servidor correspondente continua gravada
        # (com `user_nome` vazio) para o painel somar o gasto total mesmo de
        # quem não está no cadastro.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_diarias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ano TEXT NOT NULL,
                cd_fornecedor TEXT NOT NULL DEFAULT '',
                nome_portal TEXT NOT NULL DEFAULT '',
                cpf_parcial TEXT NOT NULL DEFAULT '',
                user_nome TEXT NOT NULL DEFAULT '',
                vl_empenhado REAL NOT NULL DEFAULT 0,
                vl_liquidado REAL NOT NULL DEFAULT 0,
                vl_pago REAL NOT NULL DEFAULT 0,
                coletado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ano, cd_fornecedor)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_diarias_user "
                    "ON tb_diarias(user_nome, ano)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_diarias_cpf "
                    "ON tb_diarias(cpf_parcial)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_diarias_ano "
                    "ON tb_diarias(ano)")
        _commit_com_retry(conn, contexto="init_db:diarias")

        # ---- CPF parcial no espelho da pessoa (09/10/2026) ----
        # Check-then-add portável (`PRAGMA table_info` traduzido no PG).
        cur.execute("PRAGMA table_info(tb_usuarios)")
        cols_pessoa = {r[1] for r in cur.fetchall()}
        if "cpf_parcial" not in cols_pessoa:
            cur.execute("ALTER TABLE tb_usuarios ADD COLUMN "
                        "cpf_parcial TEXT NOT NULL DEFAULT ''")
        if "data_nascimento" not in cols_pessoa:
            cur.execute("ALTER TABLE tb_usuarios ADD COLUMN "
                        "data_nascimento TEXT NOT NULL DEFAULT ''")
        _commit_com_retry(conn, contexto="init_db:cpf_pessoa")

        # ---- Histórico de movimentos (03/10/2026) ----
        # DEMISSÃO É MOVIMENTO, NÃO SUMIÇO. A pergunta que a prefeitura
        # faz não é "ele ainda trabalha?" (essa é a folha de hoje) e sim
        # "ele trabalhava quando foi demitido?" — e a resposta morre no
        # instante em que o `UPDATE` sobrescreve a situação. Por isso a
        # linha ANTERIOR fica aqui, com o JSON do que era, do que ficou,
        # e em que competência a mudança aconteceu.
        #
        # Aparece por competência e não por data porque é por competência
        # que o RH pergunta: "o que mudou entre a folha de agosto e a de
        # setembro?". `dados_anterior`/`dados_novo` são JSON porque os
        # campos que mudam não são sempre os mesmos — salário, cargo e
        # secretaria entram pelo mesmo caminho, e uma coluna para cada um
        # seria uma coluna para cada alteração que a prefeitura inventar
        # daqui a três anos.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_historico_movimentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_nome TEXT NOT NULL REFERENCES tb_usuarios(user_nome)
                    ON DELETE CASCADE ON UPDATE CASCADE,
                matricula TEXT DEFAULT '',
                competencia TEXT NOT NULL DEFAULT '',
                tipo_movimento TEXT NOT NULL DEFAULT '',
                situacao_anterior TEXT DEFAULT '',
                situacao_nova TEXT DEFAULT '',
                dados_anterior TEXT DEFAULT '',
                dados_novo TEXT DEFAULT '',
                data_registro DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimentos_user "
                    "ON tb_historico_movimentos(user_nome, competencia)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimentos_tipo "
                    "ON tb_historico_movimentos(tipo_movimento)")

        # ---- Histórico salarial (03/10/2026) ----
        # Uma linha por competência em que o VALOR MUDA. Ver
        # `registrar_salario` para por que não é uma linha por mês.
        # `remuneracao_num` é o número ao lado do texto do portal, para o
        # gráfico ordenar e para a busca casar '3470,83' — o texto
        # continua sendo a verdade (é o que o portal publica).
        # `variacao`/`variacao_percentual` são calculados na gravação: o
        # percentual é relativo à LINHA ANTERIOR, e recalcular isso na
        # leitura daria um número diferente se alguém corrigisse a folha
        # antiga depois.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_historico_salarial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_nome TEXT NOT NULL REFERENCES tb_usuarios(user_nome)
                    ON DELETE CASCADE ON UPDATE CASCADE,
                matricula TEXT DEFAULT '',
                competencia TEXT NOT NULL,
                remuneracao TEXT NOT NULL DEFAULT '',
                remuneracao_num REAL,
                variacao REAL,
                variacao_percentual REAL,
                data_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_nome, competencia)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_salarial_user "
                    "ON tb_historico_salarial(user_nome, competencia)")
        _commit_com_retry(conn, contexto="init_db:contratos_e_historicos")

        # ---- Foto mensal (07/10/2026) ----
        # UMA LINHA POR PESSOA POR COMPETÊNCIA CARREGADA, sempre — mesmo
        # quando nada mudou. É o que responde "quanto ele recebeu em 05/2026?",
        # "onde ele estava lotado?", "com que cargo?" sem juntar tabelas por
        # proximidade de data: a foto já traz unidade, lotação, cargo,
        # vínculo, situação e remuneração COMO ESTAVAM naquela carga.
        #
        # Por que NÃO reaproveitar `tb_historico_salarial`: ela só grava quando
        # o VALOR muda (uma linha por salário real), então um servidor estável
        # tem UM ponto, não doze — e a pergunta "onde ele estava em maio?" não
        # tem resposta nela. A foto custa ~1.160 linhas por competência
        # (~14 mil/ano): nada para o SQLite, tudo para a trajetória.
        #
        # Idempotência: `UNIQUE(user_nome, competencia)` + UPDATE quando a
        # mesma competência é recarregada (mesmo padrão de `registrar_salario`).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_foto_mensal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_nome TEXT NOT NULL REFERENCES tb_usuarios(user_nome)
                    ON DELETE CASCADE ON UPDATE CASCADE,
                matricula TEXT DEFAULT '',
                competencia TEXT NOT NULL,
                unidade TEXT DEFAULT '',
                lotacao TEXT DEFAULT '',
                cargo TEXT DEFAULT '',
                vinculo TEXT DEFAULT '',
                situacao TEXT DEFAULT '',
                remuneracao TEXT NOT NULL DEFAULT '',
                remuneracao_num REAL,
                ficha_contracheque TEXT DEFAULT '',
                data_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_nome, competencia)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_foto_mensal_user "
                    "ON tb_foto_mensal(user_nome, competencia)")
        _commit_com_retry(conn, contexto="init_db:foto_mensal")

        # ---- Registro de cargas da folha (07/10/2026) ----
        # UMA LINHA POR CARGA EXECUTADA: qual competência entrou, de onde veio
        # (origem/url do envelope), quando foi coletada e quantos registros
        # trouxe/criou/atualizou. É a proveniência do dado — "esta foto de
        # 09/2026 veio de qual arquivo?" — que hoje mora só no
        # `.ultima_carga.json` em disco (fora do banco e fora do git).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_cargas_folha (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                competencia TEXT NOT NULL,
                origem TEXT DEFAULT '',
                url TEXT DEFAULT '',
                coletado_em TEXT DEFAULT '',
                total INTEGER NOT NULL DEFAULT 0,
                criados INTEGER NOT NULL DEFAULT 0,
                atualizados INTEGER NOT NULL DEFAULT 0,
                data_registro DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cargas_competencia "
                    "ON tb_cargas_folha(competencia)")
        _commit_com_retry(conn, contexto="init_db:cargas_folha")

        # ---- Dados funcionais públicos (27/09/2026) ----
        # Matrícula, nome, secretaria e cargo são informação pública (portal da
        # transparência), e o cadastro não tinha onde guardar. `matricula` não
        # entra como coluna: o PRÓPRIO `user_nome` é a matrícula.
        #
        # A LISTA É DERIVADA (03/10/2026), não digitada aqui: o que a folha
        # escreve vem de `CAMPOS_FONTE_FOLHA`, o que o cadastro escreve vem
        # de `CAMPOS_CADASTRO`, e a proteção em `editar_usuario` lê as
        # mesmas duas. Antes desta Mudança a coluna vivia escrita neste laço
        # E em outro lugar da gravação — que é a receita do `teto_maximo_mb`
        # que já virou decorativo uma vez neste projeto.
        cur.execute("PRAGMA table_info(tb_usuarios)")
        cols_usuario = {r[1] for r in cur.fetchall()}
        for _col, _def in (CAMPOS_FONTE_FOLHA + CAMPOS_ESPELHO_FOLHA
                           + CAMPOS_CADASTRO + ((COLUNA_BUSCA,
                                                 "TEXT DEFAULT ''"),)):
            if _col not in cols_usuario:
                cur.execute(f"ALTER TABLE tb_usuarios ADD COLUMN {_col} {_def}")
        _commit_com_retry(conn, contexto="init_db:dados_funcionais")

        # Migração de esquema: garante FK com ON UPDATE CASCADE (renomeio).
        # Portável: no SQLite inspeciona `sqlite_master`; no PG o proxy
        # devolve vazio p/ `sqlite_master` (inalcançável) e o `_ddl_postgres`
        # remove REFERENCES — integridade gerida na aplicação (UPDATE manual
        # em `renomear_usuario` + limpeza de órfãos). Por isso a guarda usa
        # `PRAGMA table_info` (traduzido p/ information_schema no PG) e só
        # executa o rebuild no backend SQLite.
        try:
            from mod_tisosdocfly.banco_conexao import sgbd_ativo
            _backend = sgbd_ativo()
        except Exception:
            _backend = "sqlite"
        if _backend != "postgres":
            cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tb_acesso_usuario'")
            sql_row = cur.fetchone()
            if sql_row and "ON UPDATE" not in (sql_row[0] or "").upper():
                cur.executescript("""
                    ALTER TABLE tb_acesso_usuario RENAME TO tb_acesso_usuario_old;
                    CREATE TABLE tb_acesso_usuario (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_nome TEXT NOT NULL REFERENCES tb_usuarios(user_nome) ON DELETE CASCADE ON UPDATE CASCADE,
                        modulo_chave TEXT NOT NULL,
                        papel TEXT NOT NULL DEFAULT 'comum',
                        liberado_por TEXT,
                        data_liberacao DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_nome, modulo_chave)
                    );
                    INSERT INTO tb_acesso_usuario SELECT * FROM tb_acesso_usuario_old;
                    DROP TABLE tb_acesso_usuario_old;
                """)
                _commit_com_retry(conn, contexto="init_db:fk_update_cascade")
        else:
            # PG: apenas garante que a tabela existe (marcador portável).
            cur.execute("PRAGMA table_info(tb_acesso_usuario)")
            _ = cur.fetchall()

        # Migração: flags finas de permissão por módulo (JSON em tb_acesso_usuario).
        # Padrão check-then-add (portável; duplicata concorrente tolerada no proxy).
        cur.execute("PRAGMA table_info(tb_acesso_usuario)")
        cols_acesso = {r[1] for r in cur.fetchall()}
        if "flags" not in cols_acesso:
            cur.execute("ALTER TABLE tb_acesso_usuario ADD COLUMN flags TEXT NOT NULL DEFAULT '{}'")
            _commit_com_retry(conn, contexto="init_db:flags")

        # Migração única: usuários do BD central -> BD do módulo (legado).
        # Só roda se o BD central AINDA tiver tb_usuarios; em instalação nova
        # essa tabela não existe mais, então a migração é pulada com segurança
        # (evita quebrar o bootstrap "criar do zero" do PLANO.md).
        cur.execute("SELECT COUNT(*) FROM tb_usuarios")
        if cur.fetchone()[0] == 0:
            c = _central()
            try:
                cc = c.cursor()
                cc.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tb_usuarios'")
                if cc.fetchone():
                    cc.execute("SELECT user_nome, user_senha, user_email, user_fone, user_perfil, user_ativo, data_cadastro, modulo_acesso FROM tb_usuarios")
                    for r in cc.fetchall():
                        cur.execute(
                            """INSERT INTO tb_usuarios
                               (user_nome, user_senha, user_email, user_fone, user_perfil, user_ativo, data_cadastro, modulo_acesso)
                               VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?)""",
                            r,
                        )
                        # converte legado CSV -> linhas de acesso com papel 'comum'
                        for chave in [x.strip() for x in (r[7] or "").split(",") if x.strip()]:
                            cur.execute(
                                "INSERT OR IGNORE INTO tb_acesso_usuario (user_nome, modulo_chave, papel, liberado_por) VALUES (?, ?, 'comum', 'migracao')",
                                (r[0], chave),
                            )
                    _commit_com_retry(conn, contexto="init_db:migracao_legado")
            finally:
                c.close()

        # Migração: coluna de soft-delete explícita (check-then-add portável).
        cur.execute("PRAGMA table_info(tb_usuarios)")
        cols = [r[1] for r in cur.fetchall()]
        if "user_deletado" not in cols:
            cur.execute("ALTER TABLE tb_usuarios ADD COLUMN user_deletado INTEGER NOT NULL DEFAULT 0")
            _commit_com_retry(conn, contexto="init_db:user_deletado")
        # Migração: nome de exibição/tratamento (pode ser o nome social — Decreto 8.727/2016)
        cur.execute("PRAGMA table_info(tb_usuarios)")
        cols = [r[1] for r in cur.fetchall()]
        if "user_nome_completo" not in cols:
            cur.execute("ALTER TABLE tb_usuarios ADD COLUMN user_nome_completo TEXT")
            cur.execute("UPDATE tb_usuarios SET user_nome_completo='Usuário Master' WHERE user_nome='master'")
            _commit_com_retry(conn, contexto="init_db:nome_completo")
        # Migração: motivo registrado no momento da exclusão lógica (check-then-add).
        cur.execute("PRAGMA table_info(tb_usuarios)")
        cols = [r[1] for r in cur.fetchall()]
        if "user_motivo_exclusao" not in cols:
            cur.execute("ALTER TABLE tb_usuarios ADD COLUMN user_motivo_exclusao TEXT")
            _commit_com_retry(conn, contexto="init_db:motivo_exclusao")
        # Migração 06/10/2026: a LIBERAÇÃO PELO DTI. Check-then-add, uma coluna
        # por vez, porque `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` não é
        # portátil para os dois backends e o §4.1 exige que a migração rode em
        # SQLite E PostgreSQL. Ver `CAMPOS_CADASTRO` para o que cada coluna
        # significa e por que existe.
        cur.execute("PRAGMA table_info(tb_usuarios)")
        cols = [r[1] for r in cur.fetchall()]
        for _col, _def in (("liberado_pelo_dti",
                            "INTEGER NOT NULL DEFAULT 0"),
                           ("liberado_dti_em", "DATETIME"),
                           ("liberado_dti_por", "TEXT DEFAULT ''")):
            if _col not in cols:
                cur.execute(f"ALTER TABLE tb_usuarios ADD COLUMN {_col} {_def}")
                _commit_com_retry(conn, contexto=f"init_db:{_col}")

        # ---- Tipo de conta e vínculo com cliente (02/11/2026) ----
        # Check-then-add portátil (PRAGMA table_info → information_schema no
        # PostgreSQL). A coluna nova nasce com default 'interno' e a carga
        # abaixo normaliza linhas legadas gravadas sem tipo. Duas execuções
        # de `init_db` não alteram schema nem dados: na segunda rodada as
        # colunas já existem e o UPDATE não encontra linha para corrigir.
        cur.execute("PRAGMA table_info(tb_usuarios)")
        cols = [r[1] for r in cur.fetchall()]
        if "user_tipo" not in cols:
            cur.execute("ALTER TABLE tb_usuarios ADD COLUMN "
                        "user_tipo TEXT DEFAULT 'interno'")
        if "cliente_id" not in cols:
            cur.execute("ALTER TABLE tb_usuarios ADD COLUMN cliente_id INTEGER")
        cur.execute("UPDATE tb_usuarios SET user_tipo='interno' "
                    "WHERE user_tipo IS NULL OR TRIM(user_tipo)=''")
        _commit_com_retry(conn, contexto="init_db:tipo_conta")
    except Exception as e:
        try:
            _rollback_seguro(conn, contexto="init_db_seguro")
        except Exception:
            pass
        try:
            _log().exception(f"_init_db_seguro: falha no bootstrap DDL | {e}")
        except Exception:
            pass
        raise
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass

    # Segurança: se o master AINDA usa a senha padrão 'master' (instalação nova
    # ou legado), força a troca no primeiro logon — idempotente e auto-cura:
    # depois que ele trocar, a flag nunca mais é rearmada. No primeiro acesso,
    # além da senha, o master nativo deve renomear o usuário (credenciais).
    try:
        from mod_tisosdocfly import autenticacao as _auth
        linha = _auth.usuario_existe("master")
        if linha and _auth.verificar_senha("master", linha[0]):
            _auth.marcar_trocar_senha("master", True)
            _auth.marcar_trocar_credenciais("master", True)
    except Exception as e:
        _log().exception(f"init_db: falha ao verificar senha padrão do master | {e}")

    # Garante master (seed idempotente AGENTS §8.2 — sem CrudBase aqui).
    #
    # A guarda tem DUAS condições, e a segunda é a que impede a ressurreição
    # da conta de fábrica (29/09/2026).
    #
    # O primeiro acesso do master é um RENOMEAR (`renomear_usuario` faz UPDATE
    # e preserva o id), então `master` sai da tabela e a guarda
    # `not obter_usuario("master")` volta a ser verdadeira no boot seguinte:
    # o seed recria a conta com a senha de fábrica, perfil administrador_geral
    # e as duas flags de troca rearmadas. O admin troca as credenciais, e no
    # próximo reinício master/master está de volta — observado nesta instalação
    # em 29/09/2026, 16:48:35, um minuto depois da troca concluída às 16:47:13.
    #
    # A segunda condição é o marcador: `forcar_troca_credenciais:master` é
    # gravada como '1' quando a troca é pedida e como '0' quando ela CONCLUÍ
    # (`autenticacao.trocar_credenciais_master` chama `marcar_trocar_credenciais(
    # nome_atual, False)`). Então "a chave existe e vale 0" quer dizer, sem
    # ambiguidade, "o master nativo já foi renomeado" — e um nome de usuário
    # que não existe mais é justamente o que NÃO deve ser ressuscitado.
    # Mesmo padrão do marcador de migração do versionamento (§4.2): uma vez
    # gravado, o estado não volta atrás sozinho.
    if not _troca_de_credencial_do_master_concluida() and not obter_usuario("master"):
        from mod_tisosdocfly.autenticacao import gerar_hash_senha, marcar_trocar_senha, marcar_trocar_credenciais
        conn = None
        try:
            conn = get_connection(); cur = conn.cursor()
            cur.execute(
                "INSERT INTO tb_usuarios (user_nome, user_senha, user_perfil, user_ativo, user_tipo) VALUES (?, ?, 'administrador_geral', 1, 'interno')",
                ("master", gerar_hash_senha("master")),
            )
            _commit_com_retry(conn, contexto="init_db:seed_master")
            marcar_trocar_senha("master", True)
            marcar_trocar_credenciais("master", True)
        except Exception as e:
            _rollback_seguro(conn, contexto="init_db:seed_master")
            _log().exception(f"init_db: falha ao semear master | {e}")
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

    # Garante usuários de teste de QA (docs) — qacomum (comum) e qamaster (administrador_geral).
    # qacomum segue o padrão de criação vigente (comum em editar_pdf,
    # empenhos e solicita_impressao; SEM acesso a blog/usuarios/auditoria).
    from mod_tisosdocfly.autenticacao import gerar_hash_senha, marcar_trocar_senha
    conn = None
    try:
        conn = get_connection(); cur = conn.cursor()
        # `conta_de_fabrica_removida` é a decisão do ADMINISTRADOR, e ela vale
        # acima da criação: quem apagou `qacomum` na tela de credenciais não
        # quer a conta de volta no próximo reinício. Banco novo é outra
        # conversa — ele não tem o marcador, e aí a semente roda normal.
        #
        # A guarda do `master` é a MESMA coisa com outro nome: ele não volta
        # porque `forcar_troca_credenciais:master` vale '0'. Aqui o marcador
        # é próprio, porque a exclusão de `qacomum`/`qamaster` não passa
        # por troca de credencial nenhuma.
        if conta_de_fabrica_removida("qacomum"):
            _log().info("init_db: qacomum removido pelo administrador — "
                        "semente nao recria")
        elif not obter_usuario("qacomum"):
            cur.execute(
                "INSERT INTO tb_usuarios (user_nome, user_senha, user_perfil, user_ativo, user_nome_completo, user_tipo) VALUES (?, ?, 'comum', 1, ?, 'interno')",
                ("qacomum", gerar_hash_senha("123456"), "Usuário de Teste QA Comum"),
            )
            for chave in ACESSO_PADRAO_NOVO_USUARIO:
                cur.execute(
                    "INSERT OR IGNORE INTO tb_acesso_usuario (user_nome, modulo_chave, papel, liberado_por) VALUES (?, ?, 'comum', 'sistema')",
                    ("qacomum", chave),
                )
            _commit_com_retry(conn, contexto="init_db:seed_qacomum")
            # Contas de teste (15/10/2026): qacomum/qamaster nascem com a
            # troca JÁ concluída (flag '0') — os testes e scripts usam
            # `123456` direto, sem fluxo de login.
            marcar_trocar_senha("qacomum", False)
        else:
            # Reconcilia o qacomum existente com o padrão vigente (idempotente):
            # garante os acessos comuns e remove o legado 'blog' concedido
            # pelo seed ('sistema') — concessões manuais do admin são mantidas.
            for chave in ACESSO_PADRAO_NOVO_USUARIO:
                cur.execute(
                    "INSERT OR IGNORE INTO tb_acesso_usuario (user_nome, modulo_chave, papel, liberado_por) VALUES (?, ?, 'comum', 'sistema')",
                    ("qacomum", chave),
                )
            cur.execute("DELETE FROM tb_acesso_usuario WHERE user_nome='qacomum' AND modulo_chave='blog' AND liberado_por='sistema'")
            _commit_com_retry(conn, contexto="init_db:reconcilia_qacomum")
            # ASSIMILA A FALHA DE SENHA (01/10/2026). O `marcar_trocar_senha`
            # acima só roda na CRIAÇÃO. Numa instalação em que a conta já
            # existia — recriada de um backup, restaurada, ou o caso real de
            # 01/10/2026, em que o banco central foi recriado e as chaves
            # `forcar_troca:*` foram com ele — o seed reconcilia os ACESSOS e
            # nunca a senha. Resultado: a conta de fábrica entrava na tisosdocfly
            # com `123456` e sem troca obrigatória, que é o oposto do que o
            # AGENTS.md §8.2 documenta para ela.
            #
            # Só reassina quando a senha AINDA é a provisória. Quem já trocou
            # tem a flag em '0' e não é tocado — e é por isso que a conferência
            # é pelo hash, e não pela ausência da chave.
            _assegurar_troca_de_senha_provisoria(conn, "qacomum")
        if conta_de_fabrica_removida("qamaster"):
            _log().info("init_db: qamaster removido pelo administrador — "
                        "semente nao recria")
        elif not obter_usuario("qamaster"):
            cur.execute(
                "INSERT INTO tb_usuarios (user_nome, user_senha, user_perfil, user_ativo, user_nome_completo, user_tipo) VALUES (?, ?, 'administrador_geral', 1, ?, 'interno')",
                ("qamaster", gerar_hash_senha("123456"), "Usuário de Teste QA Master"),
            )
            _commit_com_retry(conn, contexto="init_db:seed_qamaster")
            # Idem qacomum acima: conta de teste, sem troca forçada.
            marcar_trocar_senha("qamaster", False)
        else:
            # Mesma assimilação da senha provisória, mesmo motivo acima.
            _assegurar_troca_de_senha_provisoria(conn, "qamaster")
    except Exception as e:
        _rollback_seguro(conn, contexto="init_db:seed_qa")
        _log().exception(f"init_db: falha ao semear QA | {e}")
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass

    # T! SOS DocFly: sem módulos de vídeo/WhatsApp — as migrações de acesso
    # padrão desses módulos foram removidas junto com eles.


# ================= CONSULTAS =================

def _normalizar_data(valor):
    """Normalizes a date value to 'YYYY-MM-DD HH:MM:SS' string.

    No SQLite `data_cadastro`/`data_liberacao` já vêm como string; no
    PostgreSQL o driver retorna `datetime.datetime`. Padroniza para string
    para que o consumo (telas) não precise saber o backend."""
    if valor is None:
        return None
    if isinstance(valor, (datetime,)):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    return str(valor)


def listar_usuarios(filtro_ativo=None):
    """Lists users with per-module access aggregated (GROUP_CONCAT).

    Retorna tuplas (id, user_nome, user_perfil, user_ativo, user_email,
    user_fone, data_cadastro, acessos 'modulo:papel, …', user_deletado,
    user_nome_completo, user_motivo_exclusao, user_tipo, cliente_id).
    `filtro_ativo` filtra por `user_ativo` quando informado; ordenado por
    login. `data_cadastro` é normalizada para string (backend-agnóstico).
    GROUP BY completo (portável SQLite↔PG — o PG exige todas as colunas não
    agregadas; `GROUP_CONCAT`→`STRING_AGG` via proxy). As duas últimas
    colunas foram acrescentadas AO FINAL (02/11/2026) para preservar os
    leitores posicionais antigos."""
    conn = _conexao_segura()
    if conn is None:
        return []
    try:
        cur = conn.cursor()
        sql = """SELECT u.id, u.user_nome, u.user_perfil, u.user_ativo,
                        u.user_email, u.user_fone, u.data_cadastro,
                        GROUP_CONCAT(a.modulo_chave || ':' || a.papel, ', '),
                        u.user_deletado, u.user_nome_completo, u.user_motivo_exclusao,
                        u.user_tipo, u.cliente_id
                 FROM tb_usuarios u
                 LEFT JOIN tb_acesso_usuario a ON a.user_nome = u.user_nome
                 WHERE 1=1"""
        params = []
        if filtro_ativo is not None:
            sql += " AND u.user_ativo=?"
            params.append(1 if filtro_ativo else 0)
        sql += (" GROUP BY u.id, u.user_nome, u.user_perfil, u.user_ativo,"
                " u.user_email, u.user_fone, u.data_cadastro,"
                " u.user_deletado, u.user_nome_completo, u.user_motivo_exclusao,"
                " u.user_tipo, u.cliente_id"
                " ORDER BY u.user_nome")
        cur.execute(sql, params)
        linhas = []
        for r in cur.fetchall():
            linha = list(r)
            linha[6] = _normalizar_data(linha[6])
            linhas.append(tuple(linha))
        return linhas
    except Exception as e:
        _log().exception(f"listar_usuarios: falha ao listar usuários | {e}")
        return []
    finally:
        conn.close()


# Tokens de ESTADO que a busca aceita por palavra-chave. São computados
# pelo chamador e entregues como lista de logins — a busca continua no
# `bd_manipulador` (que é o único lugar que fala com o banco), mas quem
# sabe das pendências e das sessões é o núcleo.
TOKENS_ESTADO = ("provisor", "bloque", "sess", "exclu")

# Colunas que `listar_usuarios` e `buscar_usuarios` devolvem, na MESMA
# ordem. A tela descompacta por posição (`uid, nome, perfil, ativo, ...`)
# e uma coluna a mais ou a menos aqui quebra o descompactamento em
# silêncio — daí a constante, e daí o teste que compara os dois.
COLUNAS_USUARIO = ("id", "user_nome", "user_perfil", "user_ativo",
                   "user_email", "user_fone", "data_cadastro", "acessos",
                   "user_deletado", "user_nome_completo", "user_motivo_exclusao",
                   "user_tipo", "cliente_id")


def _select_usuarios(extra_where="", extra_params=(), limite=None,
                     offset=0, contagem=False):
    """Monta o SELECT de usuários com os filtros, a página ou o total.

    Três coisas acontecem aqui para o SQL não divergir entre a busca e a
    listagem:

    - o mesmo GROUP BY completo nos dois casos (o PostgreSQL exige TODAS
      as colunas não agregadas no grupo, e o `GROUP_CONCAT`→`STRING_AGG`
      é traduzido pelo proxy);
    - o `WHERE` é montado por `_condicoes_busca`, que é o único lugar
      que decide o que a busca alcança;
    - `LIMIT`/`OFFSET` só entram quando pedidos, porque o PostgreSQL
      aceita mas o SQLite também — e a contagem nunca os leva, senão o
      "de 1.162" viraria "de 20".

    Devolve `(linhas, total)`. `total` é o número REAL de quem passa pelo
    filtro, e é o que a paginação precisa para saber quantas páginas
    existem.
    """
    sql_base = """FROM tb_usuarios u
                 LEFT JOIN tb_acesso_usuario a ON a.user_nome = u.user_nome"""
    select = """SELECT u.id, u.user_nome, u.user_perfil, u.user_ativo,
                       u.user_email, u.user_fone, u.data_cadastro,
                       GROUP_CONCAT(a.modulo_chave || ':' || a.papel, ', '),
                       u.user_deletado, u.user_nome_completo, u.user_motivo_exclusao,
                       u.user_tipo, u.cliente_id
                """
    group = (""" GROUP BY u.id, u.user_nome, u.user_perfil, u.user_ativo,
                        u.user_email, u.user_fone, u.data_cadastro,
                        u.user_deletado, u.user_nome_completo, u.user_motivo_exclusao,
                        u.user_tipo, u.cliente_id""")
    conn = _conexao_segura()
    if conn is None:
        return [], 0
    try:
        cur = conn.cursor()
        params = list(extra_params)
        where = f" WHERE {extra_where}" if extra_where else ""
        if contagem:
            # `COUNT(DISTINCT u.id)`, e não `COUNT(*)`. A contagem roda
            # sobre o MESMO `FROM` da listagem, que tem `LEFT JOIN
            # tb_acesso_usuario` — e um usuário com 7 acessos aparece 7
            # vezes. Medido: `contar_usuarios()` devolvia **8.087** num
            # cadastro de 1.157, porque 1.157 × 7 = 8.099 e o LIMIT
            # "funcionava". O `DISTINCT` é o que faz a contagem contar
            # PESSOAS, que é o que o "de 1.162" da tela promete.
            cur.execute(f"SELECT COUNT(DISTINCT u.id) {sql_base}{where}",
                        tuple(params))
            total = int(cur.fetchone()[0] or 0)
            if limite is None:
                return [], total
        else:
            total = 0
        sql = f"{select} {sql_base}{where}{group}"
        if limite is not None:
            sql += " ORDER BY u.user_nome LIMIT ? OFFSET ?"
            params.extend([int(limite), max(0, int(offset or 0))])
        else:
            sql += " ORDER BY u.user_nome"
        cur.execute(sql, tuple(params))
        linhas = []
        for r in cur.fetchall():
            linha = list(r)
            linha[6] = _normalizar_data(linha[6])
            linhas.append(tuple(linha))
        return linhas, total
    except Exception as e:
        _log().exception(f"_select_usuarios: falha ao consultar | {e}")
        return [], 0
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def _condicoes_busca(termo, situacao="", perfil="", logins_especiais=()):
    """Monta o `WHERE` da busca. Um lugar só, para busca e contagem baterem.

    `termo` é o que a pessoa digitou. A comparação é por `busca_norm` —
    minúsculo, sem acento, com o salário nas três formas — então 'jose'
    acha 'José' e '3470,83' acha 'R$ 3.470,83'.

    `logins_especiais` são os logins que casaram com um token de ESTADO
    ('provisório', 'bloqueado', 'sessão', 'excluído'). Vêm prontos do
    chamador porque dependem de pendências e sessões, que vivem fora
    deste banco — mas a consulta continua toda aqui.

    **Acento e `LIKE`:** o `LIKE` do SQLite é case-insensitive só para
    ASCII, e o do PostgreSQL é case-sensitive; por isso a coluna já está
    normalizada e a agulha também, e nenhum dos dois precisou de
    `LOWER()`.

    Sem ESCAPE a agulha seria um padrão, não um texto: um `100%` ou um
    `_` digitado por engano faria o `LIKE` casar qualquer coisa, e a lista
    viraria "tudo" — pior do que não achar. O `ESCAPE` é o mesmo
    caractere nos dois backends.
    """
    bruto = str(termo or "")
    termo = _sem_acento(bruto)
    logins = [x for x in (logins_especiais or ()) if x]
    if bruto.strip() and not termo:
        # Digitou ALGUMA COISA que não sobrevive à normalização ('%',
        # '_', '!!!'). Termo vazio aqui seria "sem filtro" e traria o
        # cadastro inteiro — o oposto de procurar. `1=0`: um termo que
        # não existe não casa com ninguém, e é portátil nos dois
        # backends sem depender do NULL no `LIKE`.
        return "1=0", []

    # ---- O TERMO E O TOKEN SÃO OU, NÃO E ----
    # Esta é a diferença entre a busca funcionar e não funcionar, e ela
    # é de precedência: `texto AND user_nome IN (tokens)` exige as DUAS
    # coisas, e quem casou só pelo token não tem "bloqueado" escrito em
    # lugar nenhum do cadastro — o estado é uma COLUNA, não um texto. O
    # sintoma era `buscar_usuarios("bloque", logins_especiais=[...])`
    # devolver 0 linhas mesmo com o token certo: a pessoa estava na lista
    # e a consulta a descartava.
    # O comportamento antigo (client-side) era `or`, e é o que a tela
    # promete: digitar "bloqueado" traz os bloqueados.
    if termo and logins:
        agulha = "%" + termo.replace("\\", "\\\\") \
            .replace("%", "\\%").replace("_", "\\_") + "%"
        marcas = ",".join("?" * len(logins))
        params = [agulha, agulha] + list(logins) + list(logins)
        casou = (f"(u.{COLUNA_BUSCA} LIKE ? ESCAPE '\\' OR EXISTS ("
                 f"   SELECT 1 FROM tb_contratos c"
                 f"   WHERE c.user_nome = u.user_nome"
                 f"     AND c.busca_norm LIKE ? ESCAPE '\\')"
                 f"  OR u.user_nome IN ({marcas}))")
        visivel = f"(u.user_deletado=0 OR u.user_nome IN ({marcas}))"
        extra = []
        if situacao == "ativos":
            extra.append("u.user_ativo=1 AND u.user_deletado=0")
        elif situacao == "bloqueados":
            extra.append("u.user_ativo=0 AND u.user_deletado=0")
        elif situacao == "excluidos":
            extra.append("u.user_deletado=1")
        if perfil:
            extra.append("u.user_perfil=?")
            params.append(perfil)
        partes = [casou, visivel] + extra
        return " AND ".join(partes), params

    condicoes, params = [], []
    if termo:
        agulha = "%" + termo.replace("\\", "\\\\") \
            .replace("%", "\\%").replace("_", "\\_") + "%"
        condicoes.append(
            f"(u.{COLUNA_BUSCA} LIKE ? ESCAPE '\\' OR EXISTS ("
            f"  SELECT 1 FROM tb_contratos c"
            f"  WHERE c.user_nome = u.user_nome"
            f"    AND c.busca_norm LIKE ? ESCAPE '\\'))")
        params.extend([agulha, agulha])
        # O `deletado` é decidido no bloco de `situacao`, e só lá. Se os
        # dois colocassem a condição, o filtro "Excluídos" receberia
        # `deletado=0 AND deletado=1` e devolveria sempre zero.
        if logins and not situacao:
            marcas = ",".join("?" * len(logins))
            condicoes.append("(u.user_deletado=0 OR u.user_nome IN ("
                             + marcas + "))")
            params.extend(logins)
    elif logins:
        marcas = ",".join("?" * len(logins))
        condicoes.append("u.user_nome IN (" + marcas + ")")
        params.extend(logins)
    # ---- O filtro de situação é quem decide sobre o soft-delete ----
    if situacao == "ativos":
        condicoes.append("u.user_ativo=1 AND u.user_deletado=0")
    elif situacao == "bloqueados":
        condicoes.append("u.user_ativo=0 AND u.user_deletado=0")
    elif situacao == "excluidos":
        condicoes.append("u.user_deletado=1")
    elif termo and logins:
        marcas = ",".join("?" * len(logins))
        condicoes.append("(u.user_deletado=0 OR u.user_nome IN ("
                         + marcas + "))")
        params.extend(logins)
    else:
        # "Todas" ESCONDE os excluídos — é o comportamento antigo, e é
        # proposital: a exclusão lógica é uma lista à parte, com as suas
        # próprias ações (restaurar, excluir de vez). Quem está lá foi
        # posto lá pelo ADMINISTRADOR.
        condicoes.append("u.user_deletado=0")
    if perfil:
        condicoes.append("u.user_perfil=?")
        params.append(perfil)
    return (" AND ".join(condicoes) or "1=1"), params


def buscar_usuarios(termo="", situacao="", perfil="", pagina=1,
                    por_pagina=20, logins_especiais=()):
    """Busca NO SERVIDOR, com paginação e total real. Devolve (linhas, total).

    ONDE ESTA BUSCA MUDOU (03/10/2026)
        A busca era feita no NAVEGADOR: a tela chamava
        `listar_usuarios()`, trazia as 1.162 linhas inteiro, e filtrava em
        Python a cada tecla. Duas consequências medidas: o payload ia
        inteiro a cada tecla digitada, e o filtro por Cargo/Unidade era
        IMPOSSÍVEL porque `listar_usuarios` não devolvia esses campos.

    O QUE ELA ALCANÇA
        Login, nome completo, matrícula (a do login E a das matrículas
        adicionais, via `tb_contratos`), e-mail, telefone, perfil,
        secretaria (unidade), lotação, cargo, função (o próprio cargo — no
        português do cadastro é o mesmo dado), vínculo, situação da folha,
        situação da conta e remuneração — essa última casando por
        '3.470,83', '3470,83' e 'R$ 3.470,83', porque `_normalizar_remuneracao`
        põe as três formas na coluna.

    `logins_especiais` recebe os logins que casaram com token de estado
    ('provisório', 'bloqueado', 'sessão', 'excluído'), resolvidos fora
    deste banco. Quem chama é `_painel_usuarios`, em `telas.py`.

    Devolve `(linhas, total, pagina_efetiva)`. O TERCEIRO valor existe
    porque a página pedida pode não existir — o total cai entre o clique
    e a consulta, e a resposta honesta é a última página que existe, com
    o número corrigido para a tela mostrar. Devolver a linha vazia com a
    página 59 é o que faz o usuário achar que o cadastro sumiu.

    EN: Server-side search with pagination and a real total.
    """
    try:
        por_pagina = max(1, min(int(por_pagina or 20), 200))
        pagina = max(1, int(pagina or 1))
        where, params = _condicoes_busca(termo, situacao, perfil,
                                         logins_especiais)
        linhas, total = _select_usuarios(where, params, limite=por_pagina,
                                         offset=(pagina - 1) * por_pagina,
                                         contagem=True)
        if not linhas and pagina > 1 and total:
            # Página além do fim (o total caiu depois do clique): devolve a
            # última página que existe em vez de uma lista vazia — que é o
            # que o usuário veria como "o cadastro sumiu".
            pagina = max(1, -(-total // por_pagina))
            linhas, total = _select_usuarios(where, params, limite=por_pagina,
                                             offset=(pagina - 1) * por_pagina,
                                             contagem=True)
        return linhas, total, pagina
    except Exception as e:
        _log().exception(f"buscar_usuarios: falha ao buscar '{termo}' | {e}")
        return [], 0


def contar_usuarios(situacao="", perfil="", logins_especiais=()):
    """Quantos usuários passam pelo filtro — sem trazer nenhuma linha.

    A tela precisa do total para mostrar "de 1.162" e para o botão
    "próxima página" saber se ainda há o que ver; sem isto ela contava
    em memória, o que obrigava a trazer tudo de volta.
    """
    try:
        where, params = _condicoes_busca("", situacao, perfil, logins_especiais)
        _linhas, total = _select_usuarios(where, params, contagem=True)
        return total
    except Exception as e:
        _log().exception(f"contar_usuarios: falha | {e}")
        return 0


def tokens_de_estado_atingidos(termo, logins_pendentes, sessoes_por_usuario,
                               logins_excluidos, mapa_por_ativo=None):
    """Logins que casaram com as palavras-chave de ESTADO da busca.

    A busca aceita digitar 'provisório', 'bloqueado', 'sessão' e
    'excluído' e achar a pessoa pelo estado, não pelo nome. Isso não dá
    para fazer em SQL aqui: pendência de troca de senha e sessão ativa
    vivem no banco CENTRAL e no de auditoria, e este módulo não faz
    cross-query (§2 do AGENTS.md).

    Por isso a função é pura — recebe os conjuntos já prontos e devolve
    os logins — e quem tem os dados monta antes de chamar
    `buscar_usuarios(..., logins_especiais=...)`. A consulta continua toda
    no `bd_manipulador`; só a FONTE dos dados de estado é de fora, como
    já era antes desta mudança.

    Os quatro conjuntos, e o que cada token precisa:
      `logins_pendentes`    -> 'provisor' (senha a trocar; vem do CENTRAL)
      `sessoes_por_usuario` -> 'sess'     (mapa login -> nº de sessões)
      `logins_excluidos`    -> 'exclu'    (soft-delete) E 'bloque'
      `mapa_por_ativo`      -> 'bloque'   (mapa login -> ativo; opcional)

    Devolve `[]` quando o termo não é nenhum dos tokens — um termo normal
    ('jose') não pode trazer o cadastro inteiro junto, e é o que
    aconteceria se o conjunto dos tokens fosse somado sem checar antes se
    algum casava.
    """
    try:
        # `_so_palavras` e não `_sem_acento`: os tokens são comparados
        # por substring ('provisor' dentro de 'provisorio'), e o que
        # importa aqui é que o termo esteja normalizado — não que tenha
        # os espaços preservados.
        alvo = _so_palavras(termo).replace(" ", "")
        if not alvo:
            return []
        marcados = set()
        if "provisor" in alvo:
            marcados.update(logins_pendentes or ())
        if "bloque" in alvo:
            # `logins_excluidos` também entra: quem foi excluído
            # logicamente está com `user_ativo=0`, e quem procura
            # "bloqueado" quer achar essa conta fechada, não só as
            # bloqueadas pela folha. Sem esta linha, o administrador
            # procurava o servidor que ele mesmo deletou e não achava.
            bloqueados = {x for x in (logins_excluidos or ()) if x}
            bloqueados.update(k for k, v in (mapa_por_ativo or {}).items()
                              if not v)
            marcados.update(bloqueados)
        if "sess" in alvo:
            marcados.update(k for k, v in (sessoes_por_usuario or {}).items()
                            if v)
        if "exclu" in alvo:
            marcados.update(logins_excluidos or ())
        return sorted(x for x in marcados if x)
    except Exception as e:
        _log().exception(f"tokens_de_estado_atingidos: falha | {e}")
        return []


def logins_por_situacao():
    """Login -> ativo, e a lista de excluídos, para os tokens de estado.

    Sai de `listar_usuarios` e não de queries novas porque é o mesmo
    dado, e uma query nova aqui seria um segundo lugar onde o estado da
    conta é lido — e dois lugares discordando é o que o `teto_maximo_mb`
    virou neste projeto.

    Devolve `(ativo_por_login, excluidos)`. Um dicionário só não daria
    para os dois tokens: 'bloqueado' precisa do `user_ativo` e
    'excluído' precisa do `user_deletado`, e são colunas diferentes.
    """
    try:
        ativo, excluidos = {}, []
        for l in (listar_usuarios() or ()):
            if len(l) < 9:
                continue
            ativo[l[1]] = bool(l[3])
            if l[8]:
                excluidos.append(l[1])
        return ativo, excluidos
    except Exception as e:
        _log().exception(f"logins_por_situacao: falha | {e}")
        return {}, []


def folha_de_usuario(user_nome):
    """Os campos da folha de UMA pessoa: o que está em `tb_usuarios` mais
    os contratos dela.

    Devolve dicionário com as 12 colunas de `CAMPOS_FONTE_FOLHA`, o
    espelho (`folha_situacao_atual`/`_anterior`/`data_movimento`), os
    contratos e a lista de movimentos. A tela de evolução e o diálogo de
    edição leem daqui para mostrar os campos como SOMENTE LEITURA — sem
    isto, a proteção de `editar_usuario` seria uma regra invisível.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            nomes = ([c for c, _ in CAMPOS_FONTE_FOLHA]
                     + [c for c, _ in CAMPOS_ESPELHO_FOLHA]
                     + ["user_nome", "user_nome_completo"])
            cur.execute(f"SELECT {', '.join(nomes)} FROM tb_usuarios "
                        f"WHERE user_nome=?", (user_nome,))
            linha = cur.fetchone()
            if not linha:
                return None
            dados = dict(zip(nomes, linha))
            cur.execute("SELECT * FROM tb_contratos WHERE user_nome=? "
                        "ORDER BY principal DESC, matricula", (user_nome,))
            contratos = [dict(zip([c for c, _ in CAMPOS_FONTE_FOLHA]
                                  + ["matricula", "competencia", "principal",
                                     "mesmo_nome_de", "id"], c))
                         for c in (cur.fetchall() or ())]
        finally:
            conn.close()
        dados["contratos"] = contratos
        dados["movimentos"] = historico_movimentos(user_nome)
        return dados
    except Exception as e:
        _log().exception(f"folha_de_usuario: falha em {user_nome} | {e}")
        return None


def historico_movimentos(user_nome, limite=50):
    """Movimentos do cadastro de uma pessoa, do mais recente para o mais antigo.

    Devolve lista de dicionários com `competencia`, `tipo_movimento`,
    `situacao_anterior`, `situacao_nova`, os dois JSON já abertos e a data.
    JSON aberto aqui e não na tela porque quem lê é o gráfico de linha do
    tempo e a lista de "revisar" — nenhum dos dois quer lidar com string.
    """
    import json as _json
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT competencia, tipo_movimento, situacao_anterior, "
                        "situacao_nova, dados_anterior, dados_novo, "
                        "data_registro, matricula FROM tb_historico_movimentos "
                        "WHERE user_nome=? ORDER BY competencia DESC, id DESC "
                        "LIMIT ?", (user_nome, int(limite or 50)))
            linhas = cur.fetchall() or []
        finally:
            conn.close()
        saida = []
        for l in linhas:
            antes, depois = {}, {}
            for bruto, destino in ((l[4], antes), (l[5], depois)):
                if not bruto:
                    continue
                try:
                    destino.update(_json.loads(bruto))
                except Exception:
                    pass
            saida.append({"competencia": l[0] or "", "tipo_movimento": l[1] or "",
                          "situacao_anterior": l[2] or "", "situacao_nova": l[3] or "",
                          "dados_anterior": antes, "dados_novo": depois,
                          "data_registro": _normalizar_data(l[6]), "matricula": l[7] or ""})
        return saida
    except Exception as e:
        _log().exception(f"historico_movimentos: falha em {user_nome} | {e}")
        return []


def historico_salarial(user_nome, ano=None):
    """Histórico salarial, em ordem cronológica, para o gráfico de evolução.

    Uma linha por competência em que o valor MUDOU (ver
    `registrar_salario`). Devolve lista de dicionários com `competencia`,
    `remuneracao` (texto do portal), `remuneracao_num`,
    `variacao_percentual` e `data_registro`.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            sql = ("SELECT competencia, remuneracao, remuneracao_num, variacao, "
                   "variacao_percentual, data_registro FROM tb_historico_salarial "
                   "WHERE user_nome=?")
            params = [user_nome]
            if ano:
                # A competência é 'MM/AAAA'; o ano é o TAIL, não a cabeça.
                # Filtrar por cabeça seria o jeito bonito de não achar nada.
                sql += " AND competencia LIKE ?"
                params.append(f"%/{int(ano)}")
            sql += " ORDER BY competencia"
            cur.execute(sql, tuple(params))
            linhas = cur.fetchall() or []
        finally:
            conn.close()
        return [{"competencia": l[0] or "", "remuneracao": l[1] or "",
                 "remuneracao_num": l[2], "variacao": l[3],
                 "variacao_percentual": l[4],
                 "data_registro": _normalizar_data(l[5])} for l in linhas]
    except Exception as e:
        _log().exception(f"historico_salarial: falha em {user_nome} | {e}")
        return []


def competencias_do_historico(user_nome):
    """Anos que têm linha no histórico salarial, do mais novo para o mais velho.

    Alimenta o filtro de período do gráfico. Vem do banco (e não dos anos
    do calendário) para não oferecer um ano que devolve uma tela vazia.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT competencia FROM tb_historico_salarial "
                        "WHERE user_nome=? AND competencia LIKE '%/%'",
                        (user_nome,))
            anos = set()
            for (comp,) in cur.fetchall() or ():
                try:
                    anos.add(int(str(comp).split("/")[-1].strip()))
                except Exception:
                    continue
        finally:
            conn.close()
        return sorted(anos, reverse=True)
    except Exception as e:
        _log().exception(f"competencias_do_historico: falha em {user_nome} | {e}")
        return []


def _numero_remuneracao(texto):
    """`'R$ 3.470,83'` -> `3470.83`. `None` quando não há número.

    Converte pela convenção BR: ponto é milhar, vírgula é decimal. Numa
    folha onde `exoneracao` e `regime` nunca vêm preenchidos, a única
    coluna com número é esta — e é dela que sai o eixo do gráfico.
    """
    limpo = str(texto or "").strip()
    if not limpo:
        return None
    digitos = "".join(c for c in limpo if c.isdigit() or c in ".,")
    if not digitos or not any(c.isdigit() for c in digitos):
        return None
    digitos = digitos.replace(".", "").replace(",", ".")
    try:
        return float(digitos)
    except Exception:
        return None


def registrar_salario(ator, user_nome, remuneracao, competencia, matricula=""):
    """Grava UMA linha no histórico salarial — SÓ QUANDO O VALOR MUDA.

    **A ESCOLHA, E POR QUE (03/10/2026).** A alternativa era gravar uma
    linha por competência, sempre. A escolha é gravar só quando o valor
    muda, e o motivo é o que a pergunta "quando subiu o salário?" exige:

    - gravando sempre, o servidor com salário constante gera 12 linhas
      idênticas por ano, e `tb_historico_salarial` vira 1.162 × 12 ≈
      14 mil linhas por ano para responder "não mudou";
    - gravando só na mudança, a tabela tem uma linha por SALÁRIO REAL, e
      a pergunta "em que competência o salário dele mudou, e quanto foi"
      é respondida direto.

    A consequência — e ela é real, e por isso o gráfico trata de um
    ponto só sem quebrar — é que um servidor estável tem UM ponto, não
    doze. O gráfico não inventa competência que o dado não tem: ele
    mostra o valor que se sabe e diz que só há um registro.

    **Idempotência:** `UNIQUE(user_nome, competencia)` mais o
    "UPDATE quando já existe" — rodar a mesma folha duas vezes não
    duplica nem mexe na linha anterior. E o percentual é calculado
    contra a última linha ANTES desta competência, para a variação ser
    sempre em relação ao valor anterior e não ao valor reescrito.
    """
    conn = None
    try:
        comp = (competencia or "").strip()
        rem = (remuneracao or "").strip()
        if not comp or not rem:
            return False, "Competência ou remuneração vazia — nada gravado."
        numero = _numero_remuneracao(rem)
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_usuarios WHERE user_nome=?",
                        (user_nome,))
            if not (cur.fetchone()[0] or 0):
                return False, "Usuário não encontrado."
            cur.execute("SELECT id, competencia, remuneracao, remuneracao_num "
                        "FROM tb_historico_salarial WHERE user_nome=? "
                        "AND competencia < ? ORDER BY competencia DESC "
                        "LIMIT 1", (user_nome, comp))
            anterior = cur.fetchone()
            num_anterior = anterior[3] if anterior else None
            # A LINHA É GRAVADA SÓ QUANDO O VALOR MUDA, e a comparação é
            # com a última linha ANTERIOR a esta competência — não com a
            # linha da própria competência, e não com `tb_usuarios`.
            #
            # O texto do portal é a autoridade (`'R$ 3.470,83'`), e a
            # comparação é de TEXTO, porque `'3.470,83'` e `'3470,83'`
            # são o mesmo valor e o portal pode escrever qualquer um dos
            # dois. Comparar os NÚMEROS daria o mesmo resultado e
            # dependeria de `_numero_remuneracao`, que aqui seria uma
            # segunda fonte de verdade para a mesma comparação.
            #
            # Sem esta comparação, gravar SEMPRE funciona e ninguém
            # percebe: a tabela enche de 12 linhas idênticas por ano
            # (1.162 × 12 ≈ 14 mil linhas/ano) e a pergunta "quando subiu
            # o salário?" continua respondida — por uma tabela que não
            # distingue nada.
            if anterior and (anterior[2] or "") == rem:
                return True, ("Salário sem mudança desde "
                              f"{anterior[1]} — nada a gravar.")
            variacao = None
            pct = None
            if numero is not None and num_anterior is not None:
                variacao = round(numero - float(num_anterior), 2)
                if float(num_anterior):
                    pct = round((numero - float(num_anterior))
                                / float(num_anterior) * 100.0, 2)
            cur.execute("SELECT id, remuneracao FROM tb_historico_salarial "
                        "WHERE user_nome=? AND competencia=?", (user_nome, comp))
            ja_existe = cur.fetchone()
            if ja_existe and (ja_existe[1] or "") == rem:
                return True, "Salário desta competência já estava registrado."
            if ja_existe:
                cur.execute("UPDATE tb_historico_salarial SET remuneracao=?, "
                            "remuneracao_num=?, variacao=?, "
                            "variacao_percentual=?, data_registro="
                            "CURRENT_TIMESTAMP, matricula=? WHERE id=?",
                            (rem, numero, variacao, pct, matricula or "",
                             ja_existe[0]))
            else:
                cur.execute("INSERT INTO tb_historico_salarial (user_nome, "
                            "matricula, competencia, remuneracao, "
                            "remuneracao_num, variacao, variacao_percentual) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (user_nome, matricula or "", comp, rem, numero,
                             variacao, pct))
            _commit_com_retry(conn, contexto="registrar_salario")
            _audit(ator, "historico_salarial", user_nome,
                   f"{comp}: {rem}" + (f" ({pct:+.2f}%)" if pct is not None else ""))
            return True, "Histórico salarial atualizado."
        finally:
            conn.close()
    except Exception as e:
        _rollback_seguro(conn, contexto="registrar_salario")
        _log().exception(f"registrar_salario: falha em {user_nome} | {e}")
        return False, "Erro ao gravar o histórico salarial."


def registrar_foto_mensal(ator, user_nome, competencia, dados=None):
    """Grava a FOTO do mês em `tb_foto_mensal` — SEMPRE, mudou ou não.

    Uma linha por pessoa por competência carregada, com unidade, lotação,
    cargo, vínculo, situação e remuneração COMO ESTAVAM naquela carga. É o
    que responde "quanto ele recebeu em 05/2026?", "onde estava lotado?" e
    "com que cargo?" sem juntar tabelas por proximidade de data — e o que
    alimenta `trajetoria_servidor`.

    `dados` traz as chaves `matricula, unidade, lotacao, cargo, vinculo,
    situacao, remuneracao, ficha_contracheque` (o contrato principal, como
    a carga o leu). Idempotente: `UNIQUE(user_nome, competencia)` + UPDATE
    quando a mesma competência é recarregada.
    """
    conn = None
    try:
        comp = (competencia or "").strip()
        if not comp:
            return False, "Competência vazia — foto não gravada."
        dados = dados or {}
        rem = (dados.get("remuneracao") or "").strip()
        numero = _numero_remuneracao(rem) if rem else None
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_usuarios WHERE user_nome=?",
                        (user_nome,))
            if not (cur.fetchone()[0] or 0):
                return False, "Usuário não encontrado."
            valores = (user_nome, (dados.get("matricula") or ""), comp,
                       (dados.get("unidade") or ""),
                       (dados.get("lotacao") or ""),
                       (dados.get("cargo") or ""),
                       (dados.get("vinculo") or ""),
                       (dados.get("situacao") or ""), rem, numero,
                       (dados.get("ficha_contracheque") or ""))
            cur.execute("SELECT id FROM tb_foto_mensal "
                        "WHERE user_nome=? AND competencia=?",
                        (user_nome, comp))
            ja_existe = cur.fetchone()
            if ja_existe:
                cur.execute("UPDATE tb_foto_mensal SET matricula=?, unidade=?, "
                            "lotacao=?, cargo=?, vinculo=?, situacao=?, "
                            "remuneracao=?, remuneracao_num=?, "
                            "ficha_contracheque=?, data_registro="
                            "CURRENT_TIMESTAMP WHERE id=?",
                            (valores[1], valores[3], valores[4], valores[5],
                             valores[6], valores[7], valores[8], valores[9],
                             valores[10], ja_existe[0]))
            else:
                cur.execute("INSERT INTO tb_foto_mensal (user_nome, matricula, "
                            "competencia, unidade, lotacao, cargo, vinculo, "
                            "situacao, remuneracao, remuneracao_num, "
                            "ficha_contracheque) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", valores)
            _commit_com_retry(conn, contexto="registrar_foto_mensal")
            _audit(ator, "foto_mensal", user_nome, f"{comp}")
            return True, "Foto mensal atualizada."
        finally:
            conn.close()
    except Exception as e:
        _rollback_seguro(conn, contexto="registrar_foto_mensal")
        _log().exception(f"registrar_foto_mensal: falha em {user_nome} | {e}")
        return False, "Erro ao gravar a foto mensal."


def registrar_carga_folha(ator, competencia, origem="", url="",
                          coletado_em="", total=0, criados=0, atualizados=0):
    """Grava UMA linha por carga executada em `tb_cargas_folha`.

    É a proveniência do dado — "esta foto de 09/2026 veio de qual arquivo,
    coletado quando, com quantos registros?" — que hoje mora só no
    `.ultima_carga.json` em disco (fora do banco e fora do git). Uma linha
    por carga (sem UNIQUE): recarregar a mesma competência registra de novo,
    e é assim que se vê que ela foi carregada duas vezes.
    """
    conn = None
    try:
        comp = (competencia or "").strip()
        if not comp:
            return False, "Competência vazia — carga não registrada."
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO tb_cargas_folha (competencia, origem, url, "
                        "coletado_em, total, criados, atualizados) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (comp, origem or "", url or "", coletado_em or "",
                         int(total or 0), int(criados or 0),
                         int(atualizados or 0)))
            _commit_com_retry(conn, contexto="registrar_carga_folha")
            _audit(ator, "cargas_folha", comp,
                   f"total={int(total or 0)} criados={int(criados or 0)}")
            return True, "Carga registrada."
        finally:
            conn.close()
    except Exception as e:
        _rollback_seguro(conn, contexto="registrar_carga_folha")
        _log().exception(f"registrar_carga_folha: falha em {competencia} | {e}")
        return False, "Erro ao registrar a carga."


def trajetoria_servidor(user_nome):
    """Trajetória funcional: unidade, cargo e salário por competência.

    De onde veio, para onde foi, com que cargo e quanto recebia — uma linha
    por competência carregada, em ordem cronológica, direto da
    `tb_foto_mensal`. É o que a tela de evolução do servidor vai ler.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT competencia, unidade, lotacao, cargo, vinculo, "
                        "situacao, remuneracao, remuneracao_num, "
                        "ficha_contracheque, data_registro FROM tb_foto_mensal "
                        "WHERE user_nome=? ORDER BY competencia", (user_nome,))
            linhas = cur.fetchall() or []
        finally:
            conn.close()
        return [{"competencia": l[0] or "", "unidade": l[1] or "",
                 "lotacao": l[2] or "", "cargo": l[3] or "",
                 "vinculo": l[4] or "", "situacao": l[5] or "",
                 "remuneracao": l[6] or "", "remuneracao_num": l[7],
                 "ficha_contracheque": l[8] or "",
                 "data_registro": _normalizar_data(l[9])} for l in linhas]
    except Exception as e:
        _log().exception(f"trajetoria_servidor: falha em {user_nome} | {e}")
        return []


def listar_cargas_folha(limite=20):
    """Cargas executadas, da mais nova para a mais velha.

    Proveniência para a tela: qual competência entrou, de onde veio e quantos
    registros trouxe/criou/atualizou.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT competencia, origem, url, coletado_em, total, "
                        "criados, atualizados, data_registro FROM tb_cargas_folha "
                        "ORDER BY id DESC LIMIT ?", (int(limite or 20),))
            linhas = cur.fetchall() or []
        finally:
            conn.close()
        return [{"competencia": l[0] or "", "origem": l[1] or "",
                 "url": l[2] or "", "coletado_em": l[3] or "",
                 "total": l[4] or 0, "criados": l[5] or 0,
                 "atualizados": l[6] or 0,
                 "data_registro": _normalizar_data(l[7])} for l in linhas]
    except Exception as e:
        _log().exception(f"listar_cargas_folha: falha | {e}")
        return []


def registrar_movimento(ator, user_nome, competencia, tipo_movimento,
                         situacao_anterior="", situacao_nova="",
                         dados_anterior=None, dados_novo=None, matricula=""):
    """Grava UM movimento no histórico. Nunca apaga — só acrescenta.

    A folha é quem diz que a pessoa foi demitida; o que o sistema faz é
    GUARDAR a transição, com o valor de antes e o de depois. É esta linha
    que responde "se recebeu salário X, deve constar salário X": o
    histórico é o que impede que a pergunta fique sem resposta depois do
    `UPDATE`.
    """
    import json as _json
    conn = None
    try:
        comp = (competencia or "").strip()
        tipo = (tipo_movimento or "").strip()
        if not comp or not tipo:
            return False, "Competência ou tipo de movimento vazio — nada gravado."
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tb_historico_movimentos (user_nome, matricula, "
                "competencia, tipo_movimento, situacao_anterior, "
                "situacao_nova, dados_anterior, dados_novo) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_nome, matricula or "", comp, tipo,
                 situacao_anterior or "", situacao_nova or "",
                 _json.dumps(dados_anterior or {}, ensure_ascii=False),
                 _json.dumps(dados_novo or {}, ensure_ascii=False)))
            _commit_com_retry(conn, contexto="registrar_movimento")
            _audit(ator, f"movimento_{tipo}", user_nome,
                   f"[{comp}] {situacao_anterior or '(sem situação)'} -> "
                   f"{situacao_nova or '(sem situação)'}")
            return True, "Movimento registrado."
        finally:
            conn.close()
    except Exception as e:
        _rollback_seguro(conn, contexto="registrar_movimento")
        _log().exception(f"registrar_movimento: falha em {user_nome} | {e}")
        return False, "Erro ao gravar o movimento."


def _busca_norm_contrato(reg):
    """O `busca_norm` de uma linha de contrato, sem o usuário."""
    partes = []
    for campo, _def in CAMPOS_FONTE_FOLHA:
        valor = (reg or {}).get(campo)
        if valor:
            partes.append(str(valor))
    if (reg or {}).get("matricula"):
        partes.append(str(reg["matricula"]))
    rem = _normalizar_remuneracao((reg or {}).get("remuneracao"))
    if rem:
        partes.append(rem)
    return " ".join(_sem_acento(p) for p in partes if p)


def gravar_contrato(ator, user_nome, dados, competencia="", principal=True,
                    mesmo_nome_de=""):
    """Grava (ou atualiza) a matrícula como CONTRATO da pessoa `user_nome`.

    Idempotente por `matricula`, que é UNIQUE: a mesma matrícula reenviada
    pelo portal atualiza a linha existente em vez de criar outra. É o que
    faz "rodar a carga duas vezes não duplica nada" valer para os
    contratos também, e não só para os usuários.

    **SÓ GRAVA QUANDO MUDA.** A folha tem 1.159 linhas e o agendador roda
    todo dia; uma escrita que não muda nada não é inofensiva, porque cada
    escrita paga a auditoria (medido: 211 ms por registro, o banco de
    auditoria é outro arquivo). Com auditoria incondicional, a carga de
    uma folha INALTERADA levava 4 minutos para não mudar nada — e o log
    de auditoria registrava 1.159 "contrato gravado" que não gravaram
    contrato nenhum. A trilha fica para o que aconteceu.
    """
    conn = None
    try:
        matricula = str((dados or {}).get("matricula") or "").strip()
        comp = str(competencia or "").strip()
        if not matricula or not user_nome:
            return False, "Matrícula ou usuário vazio."
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_usuarios WHERE user_nome=?",
                        (user_nome,))
            if not (cur.fetchone()[0] or 0):
                return False, "Usuário não encontrado."
            campos = [c for c, _ in CAMPOS_FONTE_FOLHA]
            valores = [str((dados or {}).get(c) or "").strip() for c in campos]
            busca = _busca_norm_contrato(dados)
            principal_v = 1 if principal else 0
            marca_v = mesmo_nome_de or ""
            cur.execute(
                "SELECT id, " + ", ".join(campos)
                + ", competencia, principal, mesmo_nome_de FROM tb_contratos "
                  "WHERE matricula=?", (matricula,))
            existente = cur.fetchone()
            if existente:
                _id = existente[0]
                antes = existente[1:]
                depois = (*valores, comp, principal_v, marca_v)
                if tuple(str(x if x is not None else "") for x in antes) == \
                        tuple(str(x) for x in depois):
                    return True, "Contrato sem mudança."
                cur.execute(
                    "UPDATE tb_contratos SET user_nome=?, unidade=?, "
                    "lotacao=?, cargo=?, vinculo=?, situacao=?, tipo=?, "
                    "admissao=?, exoneracao=?, regime=?, carga_horaria=?, "
                    "remuneracao=?, ficha_contracheque=?, competencia=?, "
                    "data_carga=CURRENT_TIMESTAMP, principal=?, "
                    "mesmo_nome_de=?, busca_norm=? WHERE id=?",
                    (user_nome, *valores, comp, principal_v, marca_v, busca,
                     _id))
            else:
                # `matricula` entra NA COLUNA: ela é a chave UNIQUE do
                # contrato e a única coisa que a linha carrega que não
                # derive de `dados`. Deixá-la de fora dava "NOT NULL
                # constraint failed: tb_contratos.matricula" em TODA
                # pessoa nova — a tabela inteira ficava vazia.
                colunas_insert = (["user_nome", "matricula"] + campos
                                  + ["competencia", "principal",
                                     "mesmo_nome_de", "busca_norm"])
                marcas = ",".join("?" * len(colunas_insert))
                cur.execute(
                    f"INSERT INTO tb_contratos ({', '.join(colunas_insert)}) "
                    f"VALUES ({marcas})",
                    (user_nome, matricula, *valores, comp, 1 if principal else 0,
                     mesmo_nome_de or "", busca))
            _reindexar(cur, user_nome)
            _commit_com_retry(conn, contexto=f"gravar_contrato:{matricula}")
            _audit(ator, "contrato_gravado", user_nome,
                   f"matrícula {matricula}"
                   + (f" | colide com {mesmo_nome_de}" if mesmo_nome_de else ""))
            return True, "Contrato gravado."
        except Exception:
            # Rollback AQUI, com a conexão ainda aberta. Com o
            # `rollback` no `except` de fora, ele roda DEPOIS do `finally`
            # que fecha a conexão — e o log enchia de "Cannot operate on a
            # closed database", que é o sintoma de um rollback que não
            # rollbackou. O sintoma aparecia; a transação ficava pela
            # metade, com o `INSERT` pendurado.
            _rollback_seguro(conn, contexto=f"gravar_contrato:{matricula}")
            raise
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
    except Exception as e:
        _log().exception(f"gravar_contrato: falha em {user_nome} | {e}")
        return False, "Erro ao gravar o contrato."


def listar_contratos(user_nome):
    """Todos os contratos de uma pessoa, o principal primeiro.

    `principal` sai como INTEIRO (0/1), e não como booleano, e o
    desempate é pela menor matrícula. O motivo é concreto: a carga grava
    a coluna com `1`/`0` via `sqlite3`/`psycopg2`, e o PostgreSQL pode
    devolver `True` — que `== 1` seria verdade, mas `is True` não, e um
    check escrito com `is` passa vazio numa tabela e falha na outra. E o
    desempate garante que a ordem da folha não muda a resposta.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM tb_contratos WHERE user_nome=? "
                        "ORDER BY principal DESC, matricula", (user_nome,))
            linhas = cur.fetchall() or []
        finally:
            conn.close()
        colunas = (["id", "user_nome", "matricula"]
                   + [c for c, _ in CAMPOS_FONTE_FOLHA]
                   + ["competencia", "data_carga", "principal", "mesmo_nome_de",
                      "busca_norm"])
        saida = []
        for l in linhas:
            d = dict(zip(colunas, l))
            d["data_carga"] = _normalizar_data(d.get("data_carga"))
            d["principal"] = 1 if d.get("principal") else 0
            saida.append(d)
        saida.sort(key=lambda d: (-d["principal"], _chave_de_matricula(d["matricula"])))
        return saida
    except Exception as e:
        _log().exception(f"listar_contratos: falha em {user_nome} | {e}")
        return []


def contrato_por_matricula(matricula):
    """O contrato de uma matrícula, como dicionário, ou `None`.

    É a consulta que decide para quem é a linha da folha: a matrícula é
    o identificador que o portal garante, então um contrato gravado
    vence qualquer hipótese feita sobre o nome.
    """
    try:
        if not matricula:
            return None
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM tb_contratos WHERE matricula=?",
                        (str(matricula).strip(),))
            linha = cur.fetchone()
        finally:
            conn.close()
        if not linha:
            return None
        colunas = (["id", "user_nome", "matricula"]
                   + [c for c, _ in CAMPOS_FONTE_FOLHA]
                   + ["competencia", "data_carga", "principal", "mesmo_nome_de",
                      "busca_norm"])
        return dict(zip(colunas, linha))
    except Exception as e:
        _log().exception(f"contrato_por_matricula: falha em {matricula} | {e}")
        return None


def login_por_matricula(matricula):
    """A conta (login) de quem tem ESTA matrícula, ou `None`.

    Existe porque uma pessoa pode ter mais de uma matrícula na folha e o
    login é só uma delas — a do contrato principal. As outras continuam
    sendo matriculas dela, e é justo que ela entre por qualquer uma
    (04/10/2026, pedido do responsável: "permitir o login com qualquer das
    matrículas").

    A resposta é uma CONSULTA, não uma migração: `tb_contratos.matricula`
    já guarda o `user_nome` de quem é a pessoa, então a matrícula secundária
    sabe dizer sozinha a quem pertence. Foi a mesma estrutura que mostrou
    que duas matrículas de uma mesma pessoa são da mesma pessoa.

    (Os números concretos dos casos medidos não entram aqui: matrícula é
    dado de servidor real, e o AGENTS.md §8.3 é categórico sobre isso. O
    padrão do caso — a menor matrícula contra a primeira do arquivo — é o
    que está descrito acima, e é o que o código corrige.)

    **CONTRATO DE SEGURANÇA, e ele é o motivo de a função existir em vez
    de uma busca por nome.** A matrícula é o identificador que o portal
    garante; o nome não. Casar login por nome abriria a porta para dois
    homônimos partilharem a mesma senha — e a aba Folha já tem 5 casos
    pendentes de confirmação justamente por causa de nome repetido. Por
    matrícula não há ambiguidade possível.

    Devolve `None` quando a matrícula não existe, e também quando a pessoa
    foi excluída (`user_deletado`): matricula de quem saiu não vira chave
    de login. Bloqueio (`user_ativo`) NÃO é consultado aqui — quem decide
    bloqueio é o `autenticar`, depois de conferir a senha, e consultar duas
    vezes o mesmo estado é como os dois discordam.
    """
    try:
        if not matricula:
            return None
        texto = str(matricula).strip()
        if not texto:
            return None
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT c.user_nome FROM tb_contratos c "
                "JOIN tb_usuarios u ON u.user_nome = c.user_nome "
                "WHERE c.matricula = ? AND (u.user_deletado IS NULL "
                "OR u.user_deletado = 0) LIMIT 1", (texto,))
            linha = cur.fetchone()
        finally:
            conn.close()
        if not linha:
            return None
        alvo = (linha[0] or "").strip()
        return alvo or None
    except Exception as e:
        # Falha aqui NÃO pode derrubar o login: devolver None faz o caminho
        # cair em "conta inexistente", que é a resposta segura (login e
        # acesso negados) em vez de erro interno para todo mundo.
        _log().exception(f"login_por_matricula: falha em {matricula} | {e}")
        return None


def recalcular_principal(user_nome):
    """Recalcula qual contrato é o PRINCIPAL da pessoa; devolve a matrícula.

    O principal é o de MENOR número — e não o primeiro que chegou. A
    ordem de chegada depende de quando a folha foi coletada e de como o
    portal devolveu as linhas; o menor número não depende de nada disso,
    então rodar a carga duas vezes com folhas em ordens diferentes dá o
    mesmo principal. E a matrícula mais antiga é a que o servidor já
    reconhecia como login.

    Uma matrícula nova MENOR que a atual muda o principal. Isso é
    informação, não defeito — por isso a tela mostra qual é o principal
    em vez de escondê-lo.
    """
    conn = None
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            principal = definir_principal_por_menor_matricula(cur, user_nome)
            _commit_com_retry(conn, contexto=f"recalcular_principal:{user_nome}")
        finally:
            conn.close()
        return principal
    except Exception as e:
        _rollback_seguro(conn, contexto=f"recalcular_principal:{user_nome}")
        _log().exception(f"recalcular_principal: falha em {user_nome} | {e}")
        return None


def recalcular_principais_em_lote(user_nomes):
    """`recalcular_principal` para muita pessoa, NUMA conexão só.

    Existe porque a carga chama isso 1.159 vezes, e uma conexão por
    pessoa saía cara de um jeito que não tem a ver com a lógica: o
    `commit` e o `close` de cada uma fazia checkpoint do WAL a cada
    chamada. Medido em SQLite: **114 ms por pessoa** com uma conexão por
    chamada, contra **0,3 ms** em lote — os dois números são da mesma
    máquina, mesmo banco, mesmos dados. Em 1.159 pessoas são 132 s contra
    0,35 s, e o carga da folha deixou de passar de meio dia.

    Devolve `{user_nome: matricula_principal}` só com quem TINHA
    contrato. Quem não tem fica de fora de propósito: o chamador decide
    o que fazer com isso, e esta função não inventa principal para
    ninguém.
    """
    try:
        nomes = sorted({str(n).strip() for n in (user_nomes or ()) if n})
        if not nomes:
            return {}
        saida = {}
        conn = get_connection()
        try:
            cur = conn.cursor()
            for nome in nomes:
                principal = definir_principal_por_menor_matricula(cur, nome)
                if principal:
                    saida[nome] = principal
            _commit_com_retry(conn, contexto="recalcular_principais_em_lote")
        except Exception:
            _rollback_seguro(conn, contexto="recalcular_principais_em_lote")
            raise
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
        return saida
    except Exception as e:
        _log().exception(f"recalcular_principais_em_lote: falha | {e}")
        return {}


def resolver_login_ou_matricula(alvo):
    """Achar a pessoa pelo LOGIN ou por qualquer uma das MATRÍCULAS.

    A tela do gráfico pede "matrícula ou login" porque as duas coisas são
    o mesmo número para quase toda pessoa — `user_nome` É a matrícula do
    contrato principal. Não é para o caso de dois contratos: a segunda
    matrícula não é login de ninguém, e é por isso que a busca por
    matrícula tem de olhar `tb_contratos`.

    Devolve o login da pessoa, ou `''` se não achar.
    """
    try:
        bruto = str(alvo or "").strip()
        if not bruto:
            return ""
        digitos = _so_digitos(bruto)
        for candidato in (bruto, digitos):
            if not candidato:
                continue
            if obter_usuario(candidato):
                return candidato
            contrato = contrato_por_matricula(candidato)
            if contrato and contrato.get("user_nome"):
                return contrato["user_nome"]
        return ""
    except Exception as e:
        _log().exception(f"resolver_login_ou_matricula: falha em {alvo} | {e}")
        return ""


def contar_contratos(user_nome):
    """Quantos contratos a pessoa tem."""
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_contratos WHERE user_nome=?",
                        (user_nome,))
            return int(cur.fetchone()[0] or 0)
        finally:
            conn.close()
    except Exception as e:
        _log().exception(f"contar_contratos: falha em {user_nome} | {e}")
        return 0


def listar_contratos_para_revisar(limite=100):
    """Contratos que colidem em nome com outra pessoa — PARA REVISAR.

    Nome igual pode ser a mesma pessoa com dois contratos ou dois
    homônimos, e a diferença não está no dado: está no conhecimento de
    quem trabalha na prefeitura. O sistema não escolhe — ele mostra,
    com os SINAIS que ajudam a decidir (mesma secretaria? mesma lotação?
    admissões próximos?) e deixa a decisão com o administrador.

    Chamar isso "revisar" em vez de "erro" é o que faz a tela ser útil:
    quem lê não está olhando defeito, está olhando uma decisão pendente.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            campos = [c for c, _ in CAMPOS_FONTE_FOLHA]
            # Os sinais (P) comparam o contrato com a PESSOA que tem o mesmo
            # nome, e por isso o SELECT traz dela o que a comparação usa.
            cur.execute(
                "SELECT c.*, u.user_nome_completo, u.unidade, u.lotacao, "
                "u.situacao, u.admissao "
                "FROM tb_contratos c JOIN tb_usuarios u "
                "ON u.user_nome=c.user_nome "
                "WHERE TRIM(COALESCE(c.mesmo_nome_de,'')) <> '' "
                "ORDER BY c.matricula LIMIT ?", (int(limite or 100),))
            linhas = cur.fetchall() or []
        finally:
            conn.close()
        base = (["id", "user_nome", "matricula"] + campos
                + ["competencia", "data_carga", "principal", "mesmo_nome_de",
                   "busca_norm"])
        saida = []
        for l in linhas:
            d = dict(zip(base + ["pessoa_nome", "pessoa_unidade",
                                 "pessoa_lotacao", "pessoa_situacao",
                                 "pessoa_admissao"], l))
            d["data_carga"] = _normalizar_data(d.get("data_carga"))
            d["sinais"] = sinais_de_colisao(d)
            saida.append(d)
        return saida
    except Exception as e:
        _log().exception(f"listar_contratos_para_revisar: falha | {e}")
        return []


def sinais_de_colisao(contrato):
    """O que ajuda a decidir se o nome igual é a mesma pessoa.

    TRÊS SINAIS, NUNCA UMA DECISÃO (03/10/2026):

    - `mesma_unidade`: mesma secretaria. É o sinal mais forte que existe
      na folha, porque dois homônimos em secretarias diferentes são
      comuns e dois homônimos na mesma secretaria com o mesmo cargo são
      raros.
    - `mesma_lotacao`: mesmo departamento dentro da secretaria.
    - `admissao_perto`: admissões dentro de 180 dias. Este sinal serve
      para DESFAZER a hipótese tanto quanto para fazê-la: duas pessoas
      admitidas no mesmo dia na mesma secretaria quase certamente são
      duas.

    Devolve dicionário com `mesma_unidade`, `mesma_lotacao`,
    `admissao_perto`, `dias_admissao`, `forca` ('forte' | 'fraca' |
    'indeterminada') e `resumo` — o texto que a tela mostra.
    `forca='fraca'` é o caso que mais precisa de olho humano: mesma
    secretaria, admissão distante.
    """
    try:
        dados = contrato or {}
        unidade = _sem_acento(dados.get("unidade"))
        pessoa_unidade = _sem_acento(dados.get("pessoa_unidade"))
        pessoa_lotacao = _sem_acento(dados.get("pessoa_lotacao"))
        lotacao = _sem_acento(dados.get("lotacao"))
        mesma_unidade = bool(unidade) and unidade == pessoa_unidade
        mesma_lotacao = bool(lotacao) and lotacao == pessoa_lotacao \
            and mesma_unidade
        dias = _dias_entre_admissoes(dados.get("admissao"),
                                     dados.get("pessoa_admissao"))
        perto = dias is not None and dias <= JANELA_ADMISSAO_DIAS
        if not unidade or not pessoa_unidade:
            forca = "indeterminada"
        elif mesma_lotacao:
            forca = "forte"
        elif mesma_unidade and perto:
            forca = "forte"
        elif mesma_unidade:
            forca = "fraca"
        else:
            forca = "indeterminada"
        resumo = ["mesma secretaria" if mesma_unidade
                  else "secretarias diferentes"]
        if mesma_lotacao:
            resumo.append("mesmo departamento")
        if dias is not None:
            resumo.append(f"admissões com {dias} dia(s) de diferença")
        elif dados.get("admissao"):
            resumo.append("admissões distantes")
        return {"mesma_unidade": mesma_unidade, "mesma_lotacao": mesma_lotacao,
                "admissao_perto": perto, "dias_admissao": dias,
                "forca": forca, "resumo": "; ".join(resumo)}
    except Exception as e:
        _log().exception(f"sinais_de_colisao: falha | {e}")
        return {"mesma_unidade": False, "mesma_lotacao": False,
                "admissao_perto": False, "dias_admissao": None,
                "forca": "indeterminada", "resumo": ""}


# Duas admissões dentro desta janela estão no mesmo "lote" de contratação
# da prefeitura. Fora dela, a admissão não diz nada — e o sinal vira
# "fraca", não "iguais".
JANELA_ADMISSAO_DIAS = 180


def _parse_data_br(texto):
    """`'01/09/1991'` -> `date`, ou None. A folha publica `DD/MM/AAAA`."""
    try:
        bruto = str(texto or "").strip()
        if not bruto or "/" not in bruto:
            return None
        partes = bruto.split("/")
        if len(partes) != 3:
            return None
        return datetime(int(partes[2]), int(partes[1]), int(partes[0])).date()
    except Exception:
        return None


def _dias_entre_admissoes(admissao_contrato, admissao_pessoa):
    """Dias entre as duas admissões, em valor absoluto. `None` se falta uma.

    `None` e não `0`: "não deu para comparar" é diferente de "foram no
    mesmo dia", e um sinal que se apresenta como ausência quando não sabe
    é pior do que um sinal ausente.
    """
    try:
        d1 = _parse_data_br(admissao_contrato)
        d2 = _parse_data_br(admissao_pessoa)
        if d1 is None or d2 is None:
            return None
        return abs((d1 - d2).days)
    except Exception as e:
        _log().warning(f"_dias_entre_admissoes: falha | {e}")
        return None


def resolver_contrato(ator, matricula, mesma_pessoa):
    """Fecha o caso de nome igual: confirma a fusão, ou separa os homônimos.

    `mesma_pessoa=True`  — é a mesma pessoa: limpa a marca e o contrato
                           continua na pessoa com quem colidia.
    `mesma_pessoa=False` — são homônimos: o contrato vai para uma PESSOA
                           NOVA, que nasce com esta matrícula como login.

    Separar é a operação que protege a prefeitura: sem ela, "são
    pessoas diferentes" não tem NENHUMA saída, e a única saída visível
    seria editar o banco na mão.
    """
    conn = None
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM tb_contratos WHERE matricula=?",
                        (matricula,))
            linha = cur.fetchone()
            if not linha:
                return False, "Contrato não encontrado."
            colunas = ["id", "user_nome", "matricula"] + \
                [c for c, _ in CAMPOS_FONTE_FOLHA] + \
                ["competencia", "data_carga", "principal", "mesmo_nome_de",
                 "busca_norm"]
            contrato = dict(zip(colunas, linha))
            pessoa_atual = contrato.get("user_nome")
            if mesma_pessoa:
                cur.execute("UPDATE tb_contratos SET mesmo_nome_de='' "
                            "WHERE matricula=?", (matricula,))
                _reindexar(cur, pessoa_atual)
                _commit_com_retry(conn, contexto="resolver_contrato:mesma")
                _audit(ator, "contrato_confirmado", pessoa_atual,
                       f"matrícula {matricula} é da mesma pessoa")
                return True, "Contrato confirmado como sendo da mesma pessoa."
        finally:
            conn.close()
        # ---- caso homônimo: a matrícula vira login de pessoa nova ----
        if obter_usuario(matricula):
            return False, (f"A matrícula {matricula} já é o login de "
                           f"outro usuário.")
        nome_pessoa = dados_nome_contrato(contrato) or contrato.get("cargo") or matricula
        ok, msg = criar_usuario(ator, matricula, SENHA_PROVISORIA_LOCAL,
                                perfil="comum", nome_completo=nome_pessoa,
                                exigir_telefone=True)
        if not ok:
            return False, msg
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE tb_contratos SET user_nome=?, principal=1, "
                        "mesmo_nome_de='' WHERE matricula=?", (matricula, matricula))
            _reindexar(cur, matricula)
            _commit_com_retry(conn, contexto="resolver_contrato:homonimo")
            _audit(ator, "contrato_homonimo", matricula,
                   f"matrícula {matricula} separada de {pessoa_atual}")
        finally:
            conn.close()
        return True, (f"{matricula} separada como pessoa própria "
                       f"(antes colidia com {pessoa_atual}).")
    except Exception as e:
        _rollback_seguro(conn, contexto="resolver_contrato")
        _log().exception(f"resolver_contrato: falha em {matricula} | {e}")
        return False, "Erro ao resolver o contrato."


def dados_nome_contrato(contrato):
    """O nome completo da pessoa a quem o contrato pertence, lido do banco.

    Falha-soft: devolve `''` quando não dá para ler. Existe para
    `resolver_contrato` não ter `None` no lugar do nome de exibição na
    hora de criar o login do homônimo.
    """
    try:
        user_nome = (contrato or {}).get("user_nome")
        if not user_nome:
            return ""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT user_nome_completo FROM tb_usuarios "
                        "WHERE user_nome=?", (user_nome,))
            l = cur.fetchone()
        finally:
            conn.close()
        return (l[0] if l else "") or ""
    except Exception as e:
        _log().exception(f"dados_nome_contrato: falha | {e}")
        return ""


def _chave_de_matricula(matricula):
    """Ordena matrícula por NÚMERO; a sem dígitos vai para o fim.

    A matrícula do portal é numérica, mas uma instalação editada à mão
    pode ter uma com letra. A que não tem número vai depois de todas, em
    ordem alfabética, para não roubar o principal de quem tem número —
    que é o caso comum e o que o servidor reconhece.
    """
    digitos = _so_digitos(matricula)
    return (0, int(digitos), str(matricula)) if digitos else (1, 0, str(matricula))


def definir_principal_por_menor_matricula(cur, user_nome):
    """Marca como PRINCIPAL o contrato de menor número da pessoa.

    O login é a matrícula do contrato principal. A escolha é a de MENOR
    NÚMERO — e não a primeira que chegou — porque é a única que não
    depende da ordem em que o portal publicou nem de quando a carga rodou:
    rodar a folha de novo, em ordem diferente, dá o mesmo principal. A
    matrícula mais antiga é também a que o servidor reconhece, porque é a
    que ele já usava.
    """
    try:
        # SEMPRE recalcula pela menor matrícula, mesmo que já exista uma
        # marcada. A tentativa de respeitar a marca existente é o que
        # quebrava o teste da folha em ordem invertida: o contrato maior
        # chegava primeiro e nascia `principal=1`, e a marca valida
        # impedia a correção quando o menor chegava depois. O resultado
        # era o espelho da pessoa refletindo a ordem da folha em vez da
        # regra. Nenhuma tela deixa o administrador marcar principal à
        # mão (`resolver_contrato` define, e define o único contrato), e
        # "sempre a menor" é a regra que não depende de nada externo.
        cur.execute("SELECT matricula FROM tb_contratos WHERE user_nome=?",
                    (user_nome,))
        matriculas = [r[0] for r in cur.fetchall() or () if r and r[0]]
        if not matriculas:
            return None
        principal = sorted(matriculas, key=_chave_de_matricula)[0]
        cur.execute("UPDATE tb_contratos SET principal=0 WHERE user_nome=?",
                    (user_nome,))
        cur.execute("UPDATE tb_contratos SET principal=1 WHERE matricula=?",
                    (principal,))
        return principal
    except Exception as e:
        _log().exception(f"definir_principal_por_menor_matricula: "
                         f"falha em {user_nome} | {e}")
        return None


def pessoas_por_nome_normalizado():
    """Mapa nome-normalizado -> login, das pessoas que têm folha.

    Montado UMA vez por carga (`sincronizar`), e é o que permite reconhecer
    que a matrícula nova pertence a alguém que já existe sem varrer a
    tabela a cada linha da folha — 1.159 linhas × 1.159 usuários seria
    1,3 milhão de comparações por carga.

    Quando duas pessoas têm o mesmo nome normalizado, o mapa guarda a
    lista com as DUAS: escolher uma delas silenciosamente seria a decisão
    que o sistema não tem o direito de tomar. Em vez disso, quem chama
    recebe a lista e marca a colisão para revisão.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT user_nome, user_nome_completo FROM tb_usuarios")
            mapa = {}
            for login, nome in cur.fetchall() or ():
                chave = _sem_acento(nome)
                if not chave:
                    continue
                mapa.setdefault(chave, []).append(login)
        finally:
            conn.close()
        return mapa
    except Exception as e:
        _log().exception(f"pessoas_por_nome_normalizado: falha | {e}")
        return {}


def gravar_dados_folha(ator, user_nome, dados, competencia="",
                       matricula="", permitir_pendencia=True):
    """Grava TODOS os campos da folha numa pessoa e devolve o que mudou.

    É o caminho ÚNICO de escrita dos campos da folha: a carga da folha
    (`sincronizar`) e a conferência manual passam por aqui. Nenhuma das
    duas grava coluna por coluna, e nenhuma delas pode esquecer um campo
    — o laço é sobre `CAMPOS_FONTE_FOLHA`.

    **A CONTA NÃO É DESLIGADA PELA FOLHA.** Demissão é MOVIMENTO, e o
        desligamento do acesso é decisão do administrador — a §4.2 do
        AGENTS.md separa as duas coisas, e mistur-las fazia a folha
        desligar a conta de um servidor sem ninguém pedir. O que fica
        gravado é `folha_situacao_atual`/`folha_situacao_anterior`/
        `data_movimento` + a linha em `tb_historico_movimentos`, que é o
        que permite ao administrador desligar — com o motivo e a data na
        mão. `user_deletado`/`user_motivo_exclusao` são a exclusão LÓGICA
        do administrador (LGPD), e são outra coisa: um servidor demitido
        pela folha continua no cadastro, com histórico.

        **`tb_usuarios` ESPELHA O CONTRATO PRINCIPAL, E SO.** Uma pessoa
        com dois contratos tem dois valores de salário e dois cargos, e
        uma linha de pessoa só tem uma coluna de cada. Quem escreve é o
        contrato de MENOR matrícula (`definir_principal_por_menor_
        matricula`), e por isso gravar pelos dois fazia o espelho
        INVERTER a cada carga — 1.159 linhas, duas delas alternando, e o
        histórico registering a troca do tempo todo. O dado completo de
        cada contrato fica em `tb_contratos`, sem soma e sem invenção:
        cada valor que aparece em qualquer tela veio de uma matrícula
        específica, e a tela mostra qual.

        **PRIMEIRO REGISTRO ≠ MUDANÇA.** Uma pessoa que nunca teve dado
        de folha não "mudou de cargo": foi cadastrada. O que se grava
        nesse caso é UM movimento do tipo `vinculacao`, com a foto
        inteira — não quatro movimentos de cargo/remuneração/unidade, e
        não uma pendência para a pessoa confirmar um valor que ela
        nunca viu. Medido: com as duas coisas erradas, a primeira carga
        abria 1.157 pendências e 4.626 movimentos que não significavam
        nada.

    Devolve dicionário com `campos_alterados` (lista de
    `[(campo, de, para)]`), `movimentos` (tipos registrados), `pendencia`
    (texto marcado, ou `''`), `primeiro_registro`, `situacao_anterior`,
    `situacao_nova` e `ok`.
    """
    conn = None
    try:
        comp = (competencia or "").strip()
        dados = dados or {}
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT {', '.join(c for c, _ in CAMPOS_FONTE_FOLHA)}, "
                        f"remuneracao_competencia, folha_situacao_atual, "
                        f"folha_situacao_anterior FROM tb_usuarios "
                        f"WHERE user_nome=?", (user_nome,))
            antes_linha = cur.fetchone()
            if not antes_linha:
                return {"ok": False, "motivo": "Usuário não encontrado.",
                        "campos_alterados": [], "movimentos": [],
                        "situacao_anterior": "", "situacao_nova": ""}
            nomes = ([c for c, _ in CAMPOS_FONTE_FOLHA]
                     + ["remuneracao_competencia", "folha_situacao_atual",
                        "folha_situacao_anterior"])
            antes = dict(zip(nomes, antes_linha))

            # PRIMEIRO REGISTRO ou MUDANÇA? A pessoa nunca teve dado de
            # folha, ou tem — e as duas coisas pedem coisas opostas do
            # histórico. Ver a docstring.
            primeiro_registro = not any(
                str(antes.get(c) or "").strip()
                for c, _ in CAMPOS_FONTE_FOLHA)

            alterados = []
            sets, params = [], []
            for campo, _def in CAMPOS_FONTE_FOLHA:
                novo = str(dados.get(campo) or "").strip()
                velho = str(antes.get(campo) or "").strip()
                # Sem acento não é mudança: o portal grava "Educacao" e o
                # cadastro pode ter "Educação" — sem esta tolerância, meia
                # prefeitura ganhava pendência por causa de acento.
                if _sem_acento(velho) == _sem_acento(novo) and velho == novo:
                    continue
                if velho == novo:
                    continue
                sets.append(f"{campo}=?")
                params.append(novo)
                alterados.append((campo, velho, novo))
            if comp:
                if (antes.get("remuneracao_competencia") or "") != comp:
                    sets.append("remuneracao_competencia=?")
                    params.append(comp)

            situacao_nova = str(dados.get("situacao") or "").strip()
            situacao_anterior = (antes.get("folha_situacao_atual")
                                 or antes.get("situacao") or "").strip()
            houve_mudanca_situacao = bool(
                situacao_nova and _sem_acento(situacao_anterior)
                != _sem_acento(situacao_nova))
            if houve_mudanca_situacao:
                # O espelho ANTES de gravar — `data_movimento` só entra
                # quando há movimento, para a coluna não fingir que a
                # primeira carga é uma demissão de "sem situação".
                sets.append("folha_situacao_anterior=?")
                params.append(situacao_anterior)
                sets.append("folha_situacao_atual=?")
                params.append(situacao_nova)
                sets.append("data_movimento=CURRENT_TIMESTAMP")

            if sets:
                params.append(user_nome)
                cur.execute(f"UPDATE tb_usuarios SET {', '.join(sets)} "
                            f"WHERE user_nome=?", tuple(params))
            _commit_com_retry(conn, contexto=f"gravar_dados_folha:{user_nome}")

            # ---- MOVIMENTOS ----
            movimentos = []
            foto_nova = {c: str(dados.get(c) or "").strip()
                         for c, _ in CAMPOS_FONTE_FOLHA}
            if primeiro_registro:
                # PRIMEIRO REGISTRO: UM movimento com a foto inteira.
                # Quatro movimentos de "mudança" aqui seriam mentira — o
                # valor anterior era vazio, não era outro. E é este o
                # registro que responde "a partir de quando essa pessoa
                # está na folha".
                ok_m, _msg_m = registrar_movimento(
                    ator, user_nome, comp, TIPO_MOVIMENTO_VINCULACAO,
                    situacao_anterior="",
                    situacao_nova=foto_nova.get("situacao", ""),
                    dados_anterior={}, dados_novo=foto_nova,
                    matricula=matricula)
                movimentos.append(TIPO_MOVIMENTO_VINCULACAO if ok_m
                                  else f"{TIPO_MOVIMENTO_VINCULACAO} (falhou)")
            else:
                if houve_mudanca_situacao:
                    tipo = _classificar_movimento(situacao_anterior, situacao_nova)
                    ok_m, _msg_m = registrar_movimento(
                        ator, user_nome, comp, tipo,
                        situacao_anterior=situacao_anterior,
                        situacao_nova=situacao_nova,
                        dados_anterior={c: v for c, v in antes.items()
                                        if c in [x for x, _ in CAMPOS_FONTE_FOLHA]},
                        dados_novo=foto_nova, matricula=matricula)
                    movimentos.append(tipo if ok_m else f"{tipo} (falhou)")
                # Salário, cargo e secretaria também são movimento: é o que
                # responde "se recebeu salário X, deve constar salário X".
                for campo, tipo in (("remuneracao", "alteracao_remuneracao"),
                                    ("cargo", "alteracao_cargo"),
                                    ("unidade", "alteracao_unidade"),
                                    ("lotacao", "alteracao_lotacao")):
                    mudado = [a for a in alterados if a[0] == campo]
                    if not mudado:
                        continue
                    _velho, _velho_txt, novo_txt = mudado[0]
                    ok_m, _msg_m = registrar_movimento(
                        ator, user_nome, comp, tipo,
                        situacao_anterior=situacao_anterior,
                        situacao_nova=situacao_nova,
                        dados_anterior={campo: _velho_txt},
                        dados_novo={campo: novo_txt}, matricula=matricula)
                    movimentos.append(tipo if ok_m else f"{tipo} (falhou)")

            if alterados or houve_mudanca_situacao:
                _reindexar(cur, user_nome)
                _commit_com_retry(conn, contexto=f"gravar_dados_folha:busca:{user_nome}")
                _audit(ator, "dados_folha_gravados", user_nome,
                       ", ".join(f"{c}: {v or '(vazio)'} -> {n}"
                                 for c, v, n in alterados))
            pendencia_texto = ""
            if alterados and permitir_pendencia and not primeiro_registro:
                # A pendência do servidor continua valendo para o que é
                # DADO DA PESSOA (setor, cargo, departamento): a folha é a
                # fonte do setor, mas quem trabalha lá é quem confirma. No
                # PRIMEIRO registro não há o que confirmar — a pessoa nunca
                # viu um valor anterior, e perguntar "seu cargo mudou de
                # (vazio) para X" é ruído para mil pessoas.
                pendencia_texto = _texto_pendencia_folha(alterados)
                if pendencia_texto:
                    _ok_p, _msg_p = marcar_pendencia_dados(ator, user_nome,
                                                           pendencia_texto)
            return {"ok": True, "motivo": "", "campos_alterados": alterados,
                    "movimentos": movimentos, "pendencia": pendencia_texto,
                    "primeiro_registro": primeiro_registro,
                    "situacao_anterior": situacao_anterior,
                    "situacao_nova": situacao_nova}
        except Exception:
            _rollback_seguro(conn, contexto=f"gravar_dados_folha:{user_nome}")
            raise
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
    except Exception as e:
        _log().exception(f"gravar_dados_folha: falha em {user_nome} | {e}")
        return {"ok": False, "motivo": "Erro ao gravar os dados da folha.",
                "campos_alterados": [], "movimentos": [], "pendencia": "",
                "primeiro_registro": False,
                "situacao_anterior": "", "situacao_nova": ""}


# O movimento da primeira vez que a pessoa aparece na folha. Nome próprio,
# e não uma reclassificação: "alteracao_situacao" diria que houve mudança
# quando não houve — o valor anterior era vazio.
TIPO_MOVIMENTO_VINCULACAO = "vinculacao"


def _reindexar(cur, user_nome):
    """Reescreve o `busca_norm` — atalho de `_recalcular_busca_norm`."""
    return _recalcular_busca_norm(cur, user_nome)


def _classificar_movimento(anterior, nova):
    """Dá NOME ao movimento, a partir das duas situações.

    O nome importa porque é por ele que a tela filtra e que o relatório
    conta: "demissão" e "afastamento" são coisas que o RH trata
    diferente, mesmo sendo as duas uma mudança de `situacao`.
    """
    try:
        de = _sem_acento(anterior)
        para = _sem_acento(nova)
    except Exception:
        return "alteracao_situacao"
    if para in ("demitido", "demissao", "exonerado", "exoneracao"):
        return "demissao"
    if para in ("ativo",):
        return "retorno_ativo"
    if para in ("funcionario de ferias", "licenca maternidade",
                "licenca para tratamento de saude", "licenca sem remuneracao"):
        return "afastamento"
    if de in ("demitido", "demissao", "exonerado", "exoneracao") \
            and para not in ("", "ativo"):
        return "alteracao_situacao"
    return "alteracao_situacao"


def _texto_pendencia_folha(alterados):
    """Texto da pendência para o servidor confirmar, ou '' se não há o que perguntar.

    Só entram `unidade`, `lotacao` e `cargo`: são os campos que a pessoa
    conhece melhor do que o portal — ela sabe em que sala trabalha, e o
    portal publica a secretaria. Remuneração e situação NÃO entram: são
    publicação oficial, e não há o que a pessoa confirme.
    """
    rotulos = {"unidade": "secretaria", "lotacao": "departamento",
               "cargo": "cargo"}
    partes = []
    for campo, velho, novo in alterados or ():
        if campo not in rotulos:
            continue
        if not novo:
            continue
        if not velho:
            partes.append(f"o seu {rotulos[campo]} agora é \"{novo}\"")
        else:
            partes.append(f"seu {rotulos[campo]} mudou de \"{velho}\" "
                          f"para \"{novo}\"")
    if not partes:
        return ""
    return "; ".join(partes).capitalize() + "."


def gravar_salario_da_folha(ator, user_nome, remuneracao, competencia,
                            matricula=""):
    """Folha -> `tb_historico_salarial`. Atalho sobre `registrar_salario`.

    Existe com este nome para a carga ler como o que é — a gravação da
    folha — e para que o histórico continue tendo um só caminho de
    escrita, igual à regra de `gravar_dados_folha`.
    """
    try:
        return registrar_salario(ator, user_nome, remuneracao, competencia,
                                 matricula=matricula)
    except Exception as e:
        _log().exception(f"gravar_salario_da_folha: falha em {user_nome} | {e}")
        return False, "Erro ao gravar o histórico salarial."


def contar_contratos_para_revisar() -> int:
    """Quantos contratos estão esperando decisão do administrador."""
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_contratos "
                        "WHERE TRIM(COALESCE(mesmo_nome_de,'')) <> ''")
            return int(cur.fetchone()[0] or 0)
        finally:
            conn.close()
    except Exception as e:
        _log().exception(f"contar_contratos_para_revisar: falha | {e}")
        return 0


def folha_tem_dados() -> bool:
    """Diz se existe QUALQUER dado de folha carregado no banco do módulo.

    EN: Returns True when at least one payroll row exists.

    PT-BR: A aba Folha de `/users` só aparece quando há conteúdo real
    (contrato, movimento ou histórico salarial). Sem a folha antiga — que
    deixou de ser distribuída com o produto — a aba vazia era ruído e, pior,
    podia falhar ao consultar tabelas sem linhas. Qualquer exceção aqui vira
    `False`: a tela de usuários continua utilizável mesmo com o banco em
    estado parcial.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            for tabela in ("tb_contratos", "tb_historico_movimentos",
                           "tb_historico_salarial"):
                cur.execute(f"SELECT 1 FROM {tabela} LIMIT 1")
                if cur.fetchone():
                    return True
            return False
        finally:
            conn.close()
    except Exception as e:
        _log().warning(f"folha_tem_dados: assumindo vazio | {e}")
        return False


def listar_movimentos_recentes(limite=100, tipo=""):
    """Movimentos recentes do cadastro inteiro, para a tela de histórico.

    Sem `tipo`, devolve todos em ordem cronológica inversa. É a lista que
    responde "o que mudou na folha deste mês?" sem precisar saber o nome
    de ninguém.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            sql = ("SELECT user_nome, matricula, competencia, tipo_movimento, "
                   "situacao_anterior, situacao_nova, data_registro "
                   "FROM tb_historico_movimentos ")
            params = []
            if tipo:
                sql += "WHERE tipo_movimento=? "
                params.append(tipo)
            sql += "ORDER BY competencia DESC, id DESC LIMIT ?"
            params.append(int(limite or 100))
            cur.execute(sql, tuple(params))
            linhas = cur.fetchall() or []
        finally:
            conn.close()
        return [{"user_nome": l[0], "matricula": l[1] or "",
                 "competencia": l[2] or "", "tipo_movimento": l[3] or "",
                 "situacao_anterior": l[4] or "", "situacao_nova": l[5] or "",
                 "data_registro": _normalizar_data(l[6])} for l in linhas]
    except Exception as e:
        _log().exception(f"listar_movimentos_recentes: falha | {e}")
        return []


def obter_usuario(user_nome):
    """Fetches one user row (incl. senha/perfil/ativo/deletado/nome_completo).

    Retorna a tupla completa do usuário ou None. Usada pelo núcleo
    (`autenticacao.usuario_existe`) para validar login/sessão a cada request.
    `user_tipo` e `cliente_id` foram acrescentados AO FINAL (02/11/2026), de
    modo que os índices históricos (senha=2, perfil=5, ativo=6) continuam
    válidos."""
    conn = _conexao_segura()
    if conn is None:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, user_nome, user_senha, user_email, user_fone,
                      user_perfil, user_ativo, data_cadastro,
                      user_deletado, user_nome_completo,
                      user_tipo, cliente_id
               FROM tb_usuarios WHERE user_nome=?""",
            (user_nome,),
        )
        return cur.fetchone()
    except Exception as e:
        _log().exception(f"obter_usuario: falha ao obter usuário {user_nome} | {e}")
        return None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
#  Telefones do usuário e dados funcionais (27/09/2026)
# ---------------------------------------------------------------------------
# Um servidor tem mais de um telefone: celular particular, celular da empresa,
# fixo da empresa. Só o telefone DA EMPRESA pode entrar na lista telefônica, e
# é por isso que `papel` existe — é ele que separa o que a prefeitura publica
# do que é do servidor. A lista telefônica LÊ estes telefones (ver
# `mod_lista_telefonica`); aqui mora a fonte.
PAPEIS_TELEFONE = ("empresa", "pessoal")
TIPOS_TELEFONE = ("celular", "fixo")


def _validar_papel(papel) -> str:
    """Normaliza o `papel` do telefone; desconhecido vira 'empresa'.

    O default é 'empresa' de propósito: o caminho seguro é o número ser
    publicável. Um papel corrompido virando 'pessoal' publicaria um número
    particular sem ninguém pedir."""
    p = (papel or "empresa").strip().lower()
    return p if p in PAPEIS_TELEFONE else "empresa"


def _validar_tipo(tipo) -> str:
    """Normaliza o `tipo` do telefone; desconhecido vira 'celular'."""
    t = (tipo or "celular").strip().lower()
    return t if t in TIPOS_TELEFONE else "celular"


def telefone_e_publicavel(papel, tipo, visivel) -> bool:
    """Diz se um telefone pode sair na lista telefônica.

    Regra vigente (16/10/2026, pedido do responsável):

    - **fixo da prefeitura SEMPRE sai**. É a linha institucional, o número
      que a prefeitura divulga em papel de visitation e em editais. Se o
      servidor informou o ramal, é porque quer ser localizado por ele — a
      lista telefônica é justamente o instrumento de localização pública, e
      um fixo institucional guardado é um fixo inútil para a Gemeinde.
    - **todo o resto SÓ sai se o dono marcar "Disponibilizar"**. Celular da
      prefeitura e qualquer número particular publicam com consentimento
      explícito — e a tela avisa em confirmação dupla que o número aparece
      na lista, pode receber mensagens/notificações e pode ser retirado a
      qualquer momento.
    """
    if _validar_papel(papel) == 'empresa' and _validar_tipo(tipo) == 'fixo':
        return True
    return bool(visivel)


def telefone_de_recado(numero, papel, tipo) -> bool:
    """Diz se este telefone é o do SETOR, usado para recado.

    O servidor sem linha própria dá o telefone do setor: o da coleta de lixo
    é o da garagem, o da merenda escolar é o da secretaria da escola. Para o
    diretório, o número é o mesmo — o que muda é o que está escrito ao lado,
    porque "Fulano, 3591-5150" faz a pessoa achar que é a linha dela."""
    try:
        return _eh_telefone_da_prefeitura(papel, tipo)
    except Exception:
        return False


def telefone_e_recado(user_nome) -> bool:
    """O telefone que a lista telefônica vai mostrar é um recado?

    É o número que a pessoa **não atende** e em que alguém anota a mensagem.
    A lista escreve "deixe recado" ao lado do nome, para quem liga não
    procurar a pessoa por dez minutos antes de descobrir que ela não atende
    o próprio ramal."""
    try:
        tels = listar_telefones(user_nome, apenas_empresa=True)
    except Exception:
        return False
    principal = next((t for t in tels if t[5]), tels[0]) if tels else None
    if not principal:
        return False
    # t = (id, user, numero, papel, tipo, principal, visivel, recado, data)
    return bool(principal[7]) if len(principal) > 7 else False


def telefones_de_recado_em_lote(user_nomes) -> dict:
    """Quem tem telefone de recado — uma consulta só.

    Mesmo papel de `telefones_publicaveis_em_lote`: a lista telefônica monta
    mais de mil cartões sem abrir mais de mil conexões. Devolve
    `{user_nome: True}` só para quem tem número de recado marcado."""
    try:
        nomes = [str(n) for n in (user_nomes or []) if n]
        if not nomes:
            return {}
        conn = get_connection()
        try:
            cur = conn.cursor()
            marcas = ",".join("?" * len(nomes))
            cur.execute(
                "SELECT user_nome, numero, principal, papel, tipo, visivel, recado "
                f"FROM tb_telefone_usuario WHERE user_nome IN ({marcas})",
                nomes)
            linhas = cur.fetchall()
        finally:
            conn.close()
        melhores = {}
        for user_nome, numero, principal, papel, tipo, visivel, recado in linhas:
            if not telefone_e_publicavel(papel, tipo, visivel):
                continue
            chave = (0 if principal else 1, str(numero or ""))
            atual = melhores.get(user_nome)
            if atual is None or chave < atual[0]:
                melhores[user_nome] = (chave, bool(recado))
        return {k: v[1] for k, v in melhores.items()}
    except Exception as e:
        _log().exception(f"telefones_de_recado_em_lote: falha | {e}")
        return {}


def listar_telefones(user_nome, apenas_empresa: bool = False):
    """Telefones do usuário, principal primeiro e os demais por número.

    Devolve linhas `(id, user_nome, numero, papel, tipo, principal, visivel,
    recado, whatsapp, data_cadastro)`. `apenas_empresa=True` devolve só os PUBLICÁVEIS —
    é o que a lista telefônica usa, para nunca vazar número particular. A
    filtragem fica em Python por `telefone_e_publicavel` (e não em
    `SQL WHERE papel=...`) para que a regra do fixo institucional valha igual
    nos dois backends. `recado` diz que o número é o do SETOR, usado para
    deixar recado — a lista telefônica escreve isso ao lado do nome.
    `whatsapp` (índice 8) diz se o número é WhatsApp — outros módulos leem
    daqui para escolher o canal de aviso.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, user_nome, numero, papel, tipo, principal, visivel, "
                "recado, whatsapp, data_cadastro FROM tb_telefone_usuario WHERE user_nome=?",
                (user_nome,))
            linhas = cur.fetchall()
            if apenas_empresa:
                linhas = [t for t in linhas
                          if telefone_e_publicavel(t[3], t[4], t[6])]
            return sorted(linhas, key=lambda r: (0 if r[5] else 1, r[2] or ""))
        finally:
            conn.close()
    except Exception as e:
        _log().exception(f"listar_telefones: falha ao listar de {user_nome} | {e}")
        return []


def telefone_empresa_principal(user_nome):
    """Telefone publicável marcado como principal, ou o primeiro publicável.

    A lista telefônica usa este para ligar um contato que é um servidor
    cadastrado. `None` quando o usuário não liberou nenhum número — e aí o
    contato fica sem telefone, o que é honesto: nem todo servidor quer ser
    localizado no celular particular, e a lista respeita isso."""
    tels = listar_telefones(user_nome, apenas_empresa=True)
    if not tels:
        return None
    principal = next((t for t in tels if t[5]), tels[0])
    return principal[2]


def telefones_publicaveis_em_lote(user_nomes) -> dict:
    """Telefone publicável de vários usuários, NORMALMENTE em uma consulta.

    Existe por causa de um número: a prefeitura tem ~1.200 servidores, e
    `telefone_empresa_principal` por pessoa abria ~1.200 conexões para montar
    a mesma tela. Com 60 usuários de demonstração ninguém notava; com a
    folha real, a tela da lista telefônica deixava de abrir.

    Devolve `{user_nome: numero}` só para quem tem número publicável — quem
    não liberou simplesmente não aparece no dicionário, que é o mesmo
    significado de "sem telefone" que o resto do sistema usa.
    """
    try:
        nomes = [str(n) for n in (user_nomes or []) if n]
        if not nomes:
            return {}
        conn = get_connection()
        try:
            cur = conn.cursor()
            # `IN` com placeholders portátil: o proxy traduz para o PG, e os
            # valores vão sempre por parâmetro — não há concatenação de texto.
            marcas = ",".join("?" * len(nomes))
            cur.execute(
                "SELECT user_nome, numero, papel, tipo, principal, visivel "
                f"FROM tb_telefone_usuario WHERE user_nome IN ({marcas})",
                nomes)
            linhas = cur.fetchall()
        finally:
            conn.close()
        melhores = {}
        for user_nome, numero, papel, tipo, principal, visivel in linhas:
            if not telefone_e_publicavel(papel, tipo, visivel):
                continue
            chave = (0 if principal else 1, str(numero or ""))
            atual = melhores.get(user_nome)
            if atual is None or chave < atual[0]:
                melhores[user_nome] = (chave, numero)
        return {k: v[1] for k, v in melhores.items()}
    except Exception as e:
        _log().exception(f"telefones_publicaveis_em_lote: falha em {len(user_nomes or [])} usuário(s) | {e}")
        return {}


def telefones_publicaveis_todos_em_lote(user_nomes) -> dict:
    """ALL publishable phones per user (multi-number directory cards).

    PT-BR: TODOS os telefones publicáveis por usuário (cards com vários
    números). Mesma consulta única de `telefones_publicaveis_em_lote`,
    mas devolve a lista em vez do melhor: `{user_nome: [{numero,
    whatsapp, principal}]}` ordenada com o principal primeiro. Quem não
    liberou nenhum continua fora do dicionário.
    """
    try:
        nomes = [str(n) for n in (user_nomes or []) if n]
        if not nomes:
            return {}
        conn = get_connection()
        try:
            cur = conn.cursor()
            marcas = ",".join("?" * len(nomes))
            cur.execute(
                "SELECT user_nome, numero, papel, tipo, principal, visivel, "
                "whatsapp "
                f"FROM tb_telefone_usuario WHERE user_nome IN ({marcas})",
                nomes)
            linhas = cur.fetchall()
        finally:
            conn.close()
        por_user = {}
        for user_nome, numero, papel, tipo, principal, visivel, whats in linhas:
            try:
                if not telefone_e_publicavel(papel, tipo, visivel):
                    continue
                por_user.setdefault(user_nome, []).append({
                    "numero": numero or "",
                    "whatsapp": bool(whats),
                    "principal": bool(principal),
                })
            except Exception:
                continue
        for lst in por_user.values():
            lst.sort(key=lambda d: (not d["principal"], d["numero"] or ""))
        return por_user
    except Exception as e:
        _log().exception(f"telefones_publicaveis_todos_em_lote: falha em {len(user_nomes or [])} usuário(s) | {e}")
        return {}


def telefones_empresa_em_lote() -> dict:
    """EN: `{user_nome: numero}` of the company phone for EVERYONE, one query.

    PT-BR: `{user_nome: numero}` do telefone da empresa de TODO MUNDO, em
    uma consulta só. Mesma regra de `telefone_empresa_principal`
    (publicável marcado como principal, ou o primeiro publicável) sem
    abrir uma conexão por usuário — `buscar_usuarios_para_lista` chamava
    uma por linha e, com a folha real, cada tecla digitada na busca
    virava mais de mil conexões: a lista de resultados nunca chegava.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            # Sem `WHERE papel=...`: a filtragem fica em Python por
            # `telefone_e_publicavel`, como em `listar_telefones` — a
            # regra do fixo institucional vale igual nos dois backends.
            cur.execute("SELECT user_nome, numero, papel, tipo, principal, "
                        "visivel FROM tb_telefone_usuario")
            linhas = cur.fetchall()
        finally:
            conn.close()
        melhores = {}
        for user_nome, numero, papel, tipo, principal, visivel in linhas:
            try:
                if (papel or "") != "empresa":
                    continue
                if not telefone_e_publicavel(papel, tipo, visivel):
                    continue
                chave = (0 if principal else 1, str(numero or ""))
                atual = melhores.get(user_nome)
                if atual is None or chave < atual[0]:
                    melhores[user_nome] = (chave, numero)
            except Exception:
                continue
        return {k: v[1] for k, v in melhores.items()}
    except Exception as e:
        _log().exception(f"telefones_empresa_em_lote: falha | {e}")
        return {}


def adicionar_telefone(ator, user_nome, numero, papel="empresa",
                       tipo="celular", principal=False, visivel=None,
                       whatsapp=False):
    """Cadastra um telefone do usuário. Devolve (True, msg) ou (False, motivo).

    `principal=True` desmarca os outros, para só haver um principal por vez —
    senão a lista telefônica não saberia qual mostrar. Número é normalizado
    aqui, e não na tela, para que a mesma regra valha para toda escrita.

    `visivel` é o CONSENTIMENTO de exibição. `None` (o padrão) deixa a decisão
    para `telefone_e_publicavel`: fixo da prefeitura publica sozinho, celular
    da empresa só se o servidor disser que pode.

    `whatsapp` marca se o número é WhatsApp — outros módulos leem em
    `listar_telefones` (índice 8) para escolher o canal de aviso.
    """
    try:
        numero_limpo = _normalizar_telefone_cadastro(numero)
        if not numero_limpo:
            return False, "Telefone inválido."
        papel_n = _validar_papel(papel)
        tipo_n = _validar_tipo(tipo)
        visivel_n = 0 if visivel is None else (1 if visivel else 0)
        whats_n = 1 if whatsapp else 0
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_usuarios WHERE user_nome=?",
                        (user_nome,))
            if not (cur.fetchone()[0] or 0):
                return False, "Usuário não encontrado."
            if principal:
                cur.execute("UPDATE tb_telefone_usuario SET principal=0 "
                            "WHERE user_nome=?", (user_nome,))
            cur.execute(
                "INSERT INTO tb_telefone_usuario "
                "(user_nome, numero, papel, tipo, principal, visivel, whatsapp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_nome, numero_limpo, papel_n, tipo_n,
                 1 if principal else 0, visivel_n, whats_n))
            _commit_com_retry(conn, contexto="adicionar_telefone")
            _limpar_pendencia_telefone(cur, user_nome)
            _commit_com_retry(conn, contexto="adicionar_telefone:pendencia")
            _audit(ator, "telefone_cadastrado", user_nome,
                   f"{numero_limpo} ({papel_n}/{tipo_n})"
                   f"{' principal' if principal else ''}"
                   f"{' publicado' if telefone_e_publicavel(papel_n, tipo_n, visivel_n) else ' restrito'}")
            return True, "Telefone cadastrado."
        finally:
            conn.close()
    except Exception as e:
        _log().exception(f"adicionar_telefone: falha em {user_nome} | {e}")
        return False, "Erro ao cadastrar o telefone."


def editar_telefone(ator, telefone_id, numero=None, papel=None, tipo=None,
                    principal=None, visivel=None, whatsapp=None):
    """Altera um telefone do usuário. Devolve (True, msg) ou (False, motivo)."""
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT user_nome FROM tb_telefone_usuario WHERE id=?",
                        (telefone_id,))
            linha = cur.fetchone()
            if not linha:
                return False, "Telefone não encontrado."
            user_nome = linha[0]
            numero_limpo = None
            if numero is not None:
                numero_limpo = _normalizar_telefone_cadastro(numero)
                if not numero_limpo:
                    return False, "Telefone inválido."
            if principal:
                cur.execute("UPDATE tb_telefone_usuario SET principal=0 "
                            "WHERE user_nome=?", (user_nome,))
            campos, valores = [], []
            if numero_limpo is not None:
                campos.append("numero=?")
                valores.append(numero_limpo)
            if papel is not None:
                campos.append("papel=?")
                valores.append(_validar_papel(papel))
            if tipo is not None:
                campos.append("tipo=?")
                valores.append(_validar_tipo(tipo))
            if principal is not None:
                campos.append("principal=?")
                valores.append(1 if principal else 0)
            if visivel is not None:
                campos.append("visivel=?")
                valores.append(1 if visivel else 0)
            if whatsapp is not None:
                campos.append("whatsapp=?")
                valores.append(1 if whatsapp else 0)
            if not campos:
                return True, "Nada a alterar."
            valores.append(telefone_id)
            cur.execute(f"UPDATE tb_telefone_usuario SET {', '.join(campos)} "
                        f"WHERE id=?", valores)
            _commit_com_retry(conn, contexto="editar_telefone")
            _audit(ator, "telefone_alterado", user_nome,
                   f"id={telefone_id}")
            return True, "Telefone alterado."
        finally:
            conn.close()
    except Exception as e:
        _log().exception(f"editar_telefone: falha no id {telefone_id} | {e}")
        return False, "Erro ao alterar o telefone."


def remover_telefone(ator, telefone_id):
    """Remove um telefone do usuário. Devolve (True, msg) ou (False, motivo)."""
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT user_nome FROM tb_telefone_usuario WHERE id=?",
                        (telefone_id,))
            linha = cur.fetchone()
            if not linha:
                return False, "Telefone não encontrado."
            cur.execute("DELETE FROM tb_telefone_usuario WHERE id=?",
                        (telefone_id,))
            _commit_com_retry(conn, contexto="remover_telefone")
            _audit(ator, "telefone_removido", linha[0], f"id={telefone_id}")
            return True, "Telefone removido."
        finally:
            conn.close()
    except Exception as e:
        _log().exception(f"remover_telefone: falha no id {telefone_id} | {e}")
        return False, "Erro ao remover o telefone."


def marcar_pendencia_dados(ator, user_nome, descricao):
    """Marca que os dados funcionais do servidor mudaram no portal.

    O texto da `descricao` é o que o servidor vai ler no alerta ("seu
    departamento mudou de A para B"), então deve ser escrito para a pessoa,
    não para o técnico.

    Não sobrescreve nada: `unidade`, `lotacao` e `cargo` continuam como
    estão até a pessoa confirmar. É a diferença entre "o sistema atualiza" e
    "o sistema pergunta" — e perguntar é o certo aqui, porque quem responde é
    quem sabe.

    A marca **não acumula**: chamar de novo substitui o texto e a data. Um
    servidor que mudou duas vezes no mesmo mês precisa de um alerta, não de
    dois, e o segundo sobrecreveria a informação do primeiro.
    """
    try:
        descricao = (descricao or "").strip()
        if not descricao:
            return True, "Nada a marcar."
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_usuarios WHERE user_nome=?",
                        (user_nome,))
            if not (cur.fetchone()[0] or 0):
                return False, "Usuário não encontrado."
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("UPDATE tb_usuarios SET pendencia_dados=?, "
                        "pendencia_em=? WHERE user_nome=?",
                        (descricao, agora, user_nome))
            _commit_com_retry(conn, contexto="marcar_pendencia_dados")
            _audit(ator, "pendencia_dados", user_nome, descricao)
            _log().info(f"pendência de dados marcada para {user_nome}: "
                        f"{descricao}")
            return True, "Dados marcados para revisão."
        finally:
            conn.close()
    except Exception as e:
        _log().exception(f"marcar_pendencia_dados: falha em {user_nome} | {e}")
        return False, "Erro ao marcar a pendência."


def _limpar_pendencia_dados(cur, user_nome):
    """Baixa a pendência de dados (chamado com o cursor aberto)."""
    try:
        cur.execute("UPDATE tb_usuarios SET pendencia_dados='', "
                    "pendencia_em=NULL WHERE user_nome=?", (user_nome,))
    except Exception as e:
        _log().warning(f"não foi possível baixar a pendência de dados "
                       f"de {user_nome}: {e}")


def informacao_pendencia(user_nome) -> dict:
    """EN: Pending data-change state of one account.

    PT-BR: O estado da pendência de atualização dos dados de uma conta.

    `varios_dias` é o que o alerta do DTI usa para cobrar quem está há
    semanas sem confirmar — a pendência sozinha não diz que está parada, e
    uma pendência parada é uma pendência que ninguém vai resolver."""
    vazio = {"tem": False, "descricao": "", "desde": None, "dias": 0}
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT pendencia_dados, pendencia_em FROM tb_usuarios "
                        "WHERE user_nome=?", (user_nome,))
            linha = cur.fetchone()
        finally:
            conn.close()
        if not linha or not (linha[0] or "").strip():
            return vazio
        dias = 0
        if linha[1]:
            try:
                marca = datetime.strptime(str(linha[1])[:19], "%Y-%m-%d %H:%M:%S")
                dias = max(0, (datetime.now() - marca).days)
            except (ValueError, TypeError):
                dias = 0
        return {"tem": True, "descricao": linha[0], "desde": linha[1],
                "dias": dias}
    except Exception as e:
        _log().exception(f"informacao_pendencia: falha em {user_nome} | {e}")
        return vazio


def listar_pendencias_dados(limite=50) -> list:
    """Contas com dado funcional mudado e ainda não confirmado.

    Serve ao alerta do DTI na Home. Ordenada pela mais antiga primeiro: a
    pendência de quem está há 3 semanas é o problema, e a de quem abriu
    yesterday é ruído. Devolve dicionários com `user_nome`, `nome_completo`,
    `descricao`, `desde` e `dias`.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""SELECT user_nome, user_nome_completo, pendencia_dados,
                                  pendencia_em, user_ativo
                           FROM tb_usuarios
                           WHERE pendencia_dados IS NOT NULL
                             AND pendencia_dados <> ''
                           ORDER BY (pendencia_em IS NULL), pendencia_em ASC
                           LIMIT ?""", (int(limite or 50),))
            linhas = cur.fetchall()
        finally:
            conn.close()
        saida = []
        for u, nome, desc, desde, ativo in linhas:
            dias = 0
            if desde:
                try:
                    marca = datetime.strptime(str(desde)[:19], "%Y-%m-%d %H:%M:%S")
                    dias = max(0, (datetime.now() - marca).days)
                except (ValueError, TypeError):
                    dias = 0
            saida.append({
                "user_nome": u,
                "nome_completo": nome or "",
                "descricao": desc or "",
                "desde": desde,
                "dias": dias,
                "ativo": bool(ativo),
            })
        return saida
    except Exception as e:
        _log().exception(f"listar_pendencias_dados: falha | {e}")
        return []


def contar_pendencias_dados() -> int:
    """Quantas contas estão com dado funcional aguardando confirmação."""
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_usuarios "
                        "WHERE pendencia_dados IS NOT NULL "
                        "AND pendencia_dados <> ''")
            return int((cur.fetchone()[0] or 0))
        finally:
            conn.close()
    except Exception as e:
        _log().exception(f"contar_pendencias_dados: falha | {e}")
        return 0


def definir_remuneracao(ator, user_nome, remuneracao=None, competencia=None,
                       ficha_contracheque=None):
    """Grava a remuneração vinda do portal e registra no histórico.

    Chamado pelo sync mensal, com a `competencia` da folha (ex.: "08/2026").

    A REMUNERAÇÃO É OBJETIVA E NÃO VIRA PERGUNTA
        O aviso de mudança de setor existe porque setor tem dois donos
        possíveis e um deles é a pessoa. Remuneração não: é o valor oficial
        publicado, e não há o que a pessoa confirme — ela sabe quanto ganha,
        mas quem registra é o RH e o portal. Por isso aqui se ATUALIZA e se
        guarda o histórico, em vez de marcar e esperar.

    O HISTÓRICO SÓ GRAVA QUANDO O VALOR MUDA
        Rodar o sync todo mês com o mesmo valor criaria 12 linhas idênticas
        por ano, e a pergunta "quando subiu o salário?" deixaria de ter
        resposta. A linha entra na competência em que o valor mudou — que é
        também a linha que interessa.
    """
    try:
        comp = (competencia or "").strip()
        rem = (remuneracao or "").strip() if remuneracao is not None else None
        ficha = (ficha_contracheque or "").strip() \
            if ficha_contracheque is not None else None
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_usuarios WHERE user_nome=?",
                        (user_nome,))
            if not (cur.fetchone()[0] or 0):
                return False, "Usuário não encontrado."
            if rem is None and ficha is None and not comp:
                return True, "Nada a atualizar."
            cur.execute("SELECT remuneracao, ficha_contracheque FROM tb_usuarios "
                        "WHERE user_nome=?", (user_nome,))
            antes = cur.fetchone() or ("", "")
            rem_final = rem if rem is not None else (antes[0] or "")
            ficha_final = ficha if ficha is not None else (antes[1] or "")
            cur.execute("UPDATE tb_usuarios SET remuneracao=?, "
                        "remuneracao_competencia=?, ficha_contracheque=? "
                        "WHERE user_nome=?",
                        (rem_final, comp or None, ficha_final, user_nome))
            mudou = (antes[0] or "") != rem_final
            if mudou and comp:
                # já existe linha desta competência? então atualiza, não duplica
                cur.execute("SELECT id FROM tb_remuneracao_historico "
                            "WHERE user_nome=? AND competencia=?",
                            (user_nome, comp))
                linha = cur.fetchone()
                if linha:
                    cur.execute("UPDATE tb_remuneracao_historico "
                                "SET remuneracao=?, ficha_contracheque=?, "
                                "registrado_em=CURRENT_TIMESTAMP WHERE id=?",
                                (rem_final, ficha_final, linha[0]))
                else:
                    cur.execute("INSERT INTO tb_remuneracao_historico "
                                "(user_nome, competencia, remuneracao, "
                                "ficha_contracheque) VALUES (?, ?, ?, ?)",
                                (user_nome, comp, rem_final, ficha_final))
                _audit(ator, "remuneracao_atualizada", user_nome,
                       f"{antes[0] or '(vazio)'} -> {rem_final} "
                       f"[{comp or 'sem competência'}]")
            _commit_com_retry(conn, contexto="definir_remuneracao")
            return True, ("Remuneração atualizada." if mudou
                          else "Remuneração conferida, sem mudança.")
        finally:
            conn.close()
    except Exception as e:
        _log().exception(f"definir_remuneracao: falha em {user_nome} | {e}")
        return False, "Erro ao gravar a remuneração."


def definir_vinculo(ator, user_nome, vinculo=None, situacao=None):
    """Grava o vínculo (efetivo, concursado, terceirizado...) e a situação.

    Chamado pelo sync mensal, com o que a folha traz do portal.

    É OBJETIVO, COMO A REMUNERAÇÃO, E TAMBÉM NÃO VIRA PERGUNTA
        "Esta pessoa é efetiva?" não tem dois donos possíveis: a folha é a
        fonte e o dado é publicado por lei. A pergunta é para setor, cargo e
        departamento, onde a folha e a pessoa discordam às vezes. Aqui o
        sistema grava e pronto.

    POR QUE EXISTE
        A lista telefônica precisa responder "é efetivo?" e "está ativo?" para
        quem não autorizou telefone. Sem estas duas colunas no cadastro, a
        resposta seria "não sei" — e a pessoa desapareceria da busca, que é
        exatamente o que a busca não deve fazer.

    Só os campos informados mudam (`None` = manter), para uma competência que
        traga o vínculo e não traga a situação não apagar a situação anterior.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            campos, valores = [], []
            for campo, valor in (("vinculo", vinculo), ("situacao", situacao)):
                if valor is not None:
                    campos.append(f"{campo}=?")
                    valores.append(str(valor or "").strip())
            if not campos:
                return True, "Nada a gravar."
            valores.append(user_nome)
            cur.execute(f"UPDATE tb_usuarios SET {', '.join(campos)} "
                        f"WHERE user_nome=?", valores)
            _commit_com_retry(conn, contexto="definir_vinculo")
            _audit(ator, "vinculo_atualizado", user_nome,
                   ", ".join(f"{c}={v}" for c, v in zip(campos, valores[:-1])))
            return True, "Vínculo atualizado."
        finally:
            conn.close()
    except Exception as e:
        _log().exception(f"definir_vinculo: falha em {user_nome} | {e}")
        return False, "Erro ao gravar o vínculo."


def historico_remuneracao(user_nome, limite=24) -> list:
    """Histórico de remuneração do servidor, do mais recente para o mais antigo."""
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT competencia, remuneracao, ficha_contracheque, "
                        "registrado_em FROM tb_remuneracao_historico "
                        "WHERE user_nome=? ORDER BY competencia DESC LIMIT ?",
                        (user_nome, int(limite or 24)))
            linhas = cur.fetchall()
        finally:
            conn.close()
        return [{"competencia": l[0], "remuneracao": l[1],
                 "ficha_contracheque": l[2] or "", "registrado_em": l[3]}
                for l in linhas]
    except Exception as e:
        _log().exception(f"historico_remuneracao: falha em {user_nome} | {e}")
        return []


def _limpar_pendencia_telefone(cur, user_nome):
    """Baixa a pendência de telefone do usuário (usado com o cursor aberto).

    Fica em SQL cru e recebe o cursor porque quem chama já está numa
    transação — abrir outra conexão aqui perderia o trabalho em curso."""
    try:
        cur.execute("UPDATE tb_usuarios SET telefone_pendente=0 "
                    "WHERE user_nome=?", (user_nome,))
    except Exception as e:
        _log().warning(f"não foi possível baixar a pendência de telefone "
                       f"de {user_nome}: {e}")


def telefone_pendente(user_nome) -> bool:
    """True se o servidor ainda precisa registrar os telefones.

    O portal da transparência publica matrícula, nome, secretaria e cargo —
    mas NÃO o ramal. Ou seja: sem esse passo, um servidor recém-cadastrado
    entraria na lista telefônica sem número nenhum. Por isso a pendência
    acompanha a troca de senha no primeiro acesso."""
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT telefone_pendente FROM tb_usuarios "
                        "WHERE user_nome=?", (user_nome,))
            linha = cur.fetchone()
            return bool(linha and linha[0])
        finally:
            conn.close()
    except Exception as e:
        _log().exception(f"telefone_pendente: falha em {user_nome} | {e}")
        return False


# Prazo da liberação temporária, em dias. Depois dele a conta fecha e só o
# DTI reabre — o prazo curto é o ponto: quatro dias é o bastante para o
# servidor descobrir o número perguntando à secretaria da escola, à unidade de
# saúde, à garagem ou ao almoxarifado, e curto o bastante para que a conta não
# vire cadastro órfão no sistema.
DIAS_LIBERACAO_PROVISORIA = 4


def _eh_telefone_da_prefeitura(papel, tipo) -> bool:
    """Fixo da prefeitura — o número institucional.

    Celular da prefeitura NÃO conta: celular é a pessoa, e o que a
    prefeitura precisa garantir é que exista uma **linha** que toque em
    algum lugar do prédio. É por isso que a exigência é de um fixo, e não de
    "um telefone da prefeitura" em geral."""
    return _validar_papel(papel) == 'empresa' and _validar_tipo(tipo) == 'fixo'


def avaliar_telefones_primeiro_acesso(contatos):
    """EN: Evaluates the phones before saving — what is missing, what is out
    of range. PT-BR: Avalia os telefones antes de gravar.

    Devolve um dicionário para o chamador, sem gravar nada:

    ```
    {
      "tem_da_prefeitura": bool,   # existe fixo da prefeitura (próprio ou recado)
      "particulares":     int,     # quantos particulares o servidor informou
      "fora_da_faixa":    [(numero, descricao_da_faixa_mais_proxima)],
      "pode_prosseguir":  bool,
    }
    ```

    Separar a avaliação da gravação é o que permite à tela mostrar o aviso de
    "fora da faixa" **enquanto** o servidor digita, e não só depois que ele
    já salvou e descobriu que errou."""
    try:
        from mod_tisosdocfly import telefone_faixas as _fx
        tem_prefeitura = False
        particulares = 0
        fora = []
        for c in (contatos or []):
            if not isinstance(c, dict):
                continue
            num = _normalizar_telefone_cadastro(c.get("numero"))
            if not num:
                continue
            if _eh_telefone_da_prefeitura(c.get("papel"), c.get("tipo")):
                tem_prefeitura = True
                dentro, _faixa = _fx.numero_dentro_da_faixa(num)
                if not dentro:
                    perto = _fx.faixa_mais_proxima(num)
                    fora.append((num, (perto or {}).get("descricao", "")))
            else:
                particulares += 1
        return {
            "tem_da_prefeitura": tem_prefeitura,
            "particulares": particulares,
            "fora_da_faixa": fora,
            "pode_prosseguir": tem_prefeitura or particulares > 0,
        }
    except Exception as e:
        _log().exception(f"avaliar_telefones_primeiro_acesso: falha | {e}")
        return {"tem_da_prefeitura": False, "particulares": 0,
                "fora_da_faixa": [], "pode_prosseguir": False}


def registrar_contatos_primeiro_acesso(ator, user_nome, contatos,
                                       liberacao_provisoria=False):
    """Grava de uma vez os telefones do primeiro acesso.

    `contatos` é uma lista de dicionários com `numero`, `papel`
    ('empresa'/'pessoal'), `tipo` ('celular'/'fixo'), `visivel` e `recado`.
    Tudo numa transação só: ou entra o conjunto inteiro, ou nada — um cadastro
    pela metade é pior do que um cadastro recusado, porque o servidor fica sem
    saber o que já preencheu.

    A EXIGÊNCIA DE UM TELEFONE DA PREFEITURA
        Todo servidor está atrelado a uma secretaria ou a um setor, e todo
        setor tem linha. Então o sistema pede um **fixo da prefeitura** — o
        próprio ou o de recado. Celular particular e celular da prefeitura
        não satisfazem: os dois vão para o celular de quem atende, e quem
        precisa é a prefeitura ser localizada.

    A LIBERAÇÃO TEMPORÁRIA (o paliativo)
        Quando o servidor não sabe o número — e é mais comum do que parece,
        porque a maioria não tem linha própria — ele confirma duas vezes que
        não sabe, e aí entra com prazo: `liberacao_provisoria=True` grava
        `acesso_provisorio` com `DIAS_LIBERACAO_PROVISORIA` de validade e
        **exige um telefone particular**. Passado o prazo, `bloqueio_provisorio_pendente`
        fecha a conta e só o DTI reabre.

    O QUE NÃO É BLOQUEADO
        Telefone fora das faixas da prefeitura: é avisado, não recusado. Ver
        `avaliar_telefones_primeiro_acesso`.

    Devolve `(ok, msg, detalhes)` — `detalhes` traz `provisorio` e
    `fora_da_faixa` para a tela mostrar o que precisa mostrar.
    """
    detalhes = {"provisorio": False, "fora_da_faixa": [],
                "ate": None, "pode_prosseguir": False}
    try:
        monta = []
        for c in (contatos or []):
            if not isinstance(c, dict):
                continue
            if not _normalizar_telefone_cadastro(c.get("numero")):
                continue  # campo em branco: o servidor optou por não informar
            monta.append(c)

        avalio = avaliar_telefones_primeiro_acesso(monta)
        detalhes["fora_da_faixa"] = avalio["fora_da_faixa"]
        detalhes["pode_prosseguir"] = avalio["pode_prosseguir"]

        if not monta:
            return False, ("Informe ao menos um telefone — sem ele você não "
                           "aparece na lista telefônica."), detalhes

        if not avalio["tem_da_prefeitura"]:
            if not liberacao_provisoria:
                return False, ("Falta um telefone da prefeitura (fixo). "
                               "Se você usa o telefone do setor para recado, "
                               "marque-o como telefone de recado."), detalhes
            # paliativo: entra com prazo, mas SÓ com particular informado
            if avalio["particulares"] <= 0:
                return False, ("Para liberar o acesso por um período você "
                               "precisa informar um telefone particular de "
                               "contato."), detalhes
            detalhes["provisorio"] = True

        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_usuarios WHERE user_nome=?",
                        (user_nome,))
            if not (cur.fetchone()[0] or 0):
                return False, "Usuário não encontrado.", detalhes
            cur.execute("DELETE FROM tb_telefone_usuario WHERE user_nome=?",
                        (user_nome,))
            principal_definido = any(bool(c.get("principal")) for c in monta)
            for i, c in enumerate(monta):
                papel_n = _validar_papel(c.get("papel"))
                tipo_n = _validar_tipo(c.get("tipo"))
                principal = 1 if (c.get("principal") or (i == 0 and not principal_definido)) else 0
                if principal:
                    cur.execute("UPDATE tb_telefone_usuario SET principal=0 "
                                "WHERE user_nome=?", (user_nome,))
                cur.execute(
                    "INSERT INTO tb_telefone_usuario "
                    "(user_nome, numero, papel, tipo, principal, visivel, recado, whatsapp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_nome, _normalizar_telefone_cadastro(c.get("numero")),
                     papel_n, tipo_n, principal,
                     1 if c.get("visivel") else 0,
                     1 if c.get("recado") else 0,
                     1 if c.get("whatsapp") else 0))
            if detalhes["provisorio"]:
                dias = DIAS_LIBERACAO_PROVISORIA
                cur.execute(
                    "UPDATE tb_usuarios SET acesso_provisorio=1, "
                    "provisorio_ate=? WHERE user_nome=?",
                    (_prazo(dias), user_nome))
                cur.execute("SELECT provisorio_ate FROM tb_usuarios "
                            "WHERE user_nome=?", (user_nome,))
                linha_prazo = cur.fetchone()
                detalhes["ate"] = linha_prazo[0] if linha_prazo else None
            else:
                # TEM um telefone nosso: a liberação é definitiva e o prazo
                # anterior (se houve) deixa de valer.
                cur.execute("UPDATE tb_usuarios SET acesso_provisorio=0, "
                            "provisorio_ate=NULL WHERE user_nome=?", (user_nome,))
            _limpar_pendencia_telefone(cur, user_nome)
            _commit_com_retry(conn, contexto="registrar_contatos_primeiro_acesso")
            _audit(ator, "contatos_primeiro_acesso", user_nome,
                   f"{len(monta)} telefone(s)"
                   + (" | LIBERACAO PROVISORIA" if detalhes["provisorio"] else ""))
            _log().info(f"contatos do 1º acesso de {user_nome}: {len(monta)}"
                        + (f" (provisório até {detalhes['ate']})"
                           if detalhes["provisorio"] else ""))
            if detalhes["provisorio"]:
                return True, (f"Telefones registrados. Acesso liberado por "
                               f"{DIAS_LIBERACAO_PROVISORIA} dias — depois "
                               f"disso a conta fica bloqueada até o DTI "
                               f"liberar."), detalhes
            return True, "Telefones registrados.", detalhes
        finally:
            conn.close()
    except Exception as e:
        _log().exception(f"registrar_contatos_primeiro_acesso: "
                         f"falha em {user_nome} | {e}")
        return False, "Erro ao registrar os telefones.", detalhes


def _prazo(dias):
    """Data/hora em que a liberação temporária vence, no mesmo formato do
    banco. Sem `strftime` do SQLite para continuar funcionando no Postgres
    pelo proxy."""
    try:
        return (datetime.now() + timedelta(days=int(dias))).strftime(
            "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def bloqueio_provisorio_pendente(user_nome) -> bool:
    """True se a liberação temporária desta conta JÁ VENCEU e ela está ativa.

    Chamado no login: é aí que a janela de 4 dias se cumpre. Sem essa
    checagem, a liberação temporária seria um prazo que ninguém nunca
    fiscaliza — a conta entraria para sempre, e o paliativo viraria norma."""
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT acesso_provisorio, provisorio_ate, user_ativo "
                        "FROM tb_usuarios WHERE user_nome=?", (user_nome,))
            linha = cur.fetchone()
        finally:
            conn.close()
        if not linha or not linha[0] or not linha[1]:
            return False
        if not linha[2]:
            return False  # já está bloqueada: nada a fazer
        try:
            prazo = datetime.strptime(str(linha[1])[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return False
        return datetime.now() > prazo
    except Exception as e:
        _log().exception(f"bloqueio_provisorio_pendente: falha em {user_nome} | {e}")
        return False


def confirmar_pendencia_dados(ator, user_nome, unidade=None, lotacao=None,
                              cargo=None):
    """O servidor confirmou a mudança: grava os valores novos e baixa a marca.

    A confirmação é da PESSOA, não do técnico. Quando ela confirma, o que
    ela está dizendo é "é isso mesmo, meu departamento mudou" — e a partir
    daí o banco passa a refletir isso.

    Só os campos informados mudam (`None` = manter), para que a confirmação
    não apague o campo que o portal não trouxe.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_usuarios WHERE user_nome=?",
                        (user_nome,))
            if not (cur.fetchone()[0] or 0):
                return False, "Usuário não encontrado."
            campos, valores = [], []
            for campo, valor in (("unidade", unidade), ("lotacao", lotacao),
                                 ("cargo", cargo)):
                if valor is not None:
                    campos.append(f"{campo}=?")
                    valores.append(str(valor or "").strip())
            if campos:
                valores.append(user_nome)
                cur.execute(f"UPDATE tb_usuarios SET {', '.join(campos)} "
                            f"WHERE user_nome=?", valores)
            _limpar_pendencia_dados(cur, user_nome)
            _commit_com_retry(conn, contexto="confirmar_pendencia_dados")
            _audit(ator, "pendencia_dados_confirmada", user_nome,
                   ", ".join(campos) if campos else "sem alteração de valor")
            _log().info(f"pendência de dados confirmada por {user_nome}: "
                        f"{', '.join(campos) or 'nenhum campo'}")
            return True, "Dados atualizados."
        finally:
            conn.close()
    except Exception as e:
        _log().exception(f"confirmar_pendencia_dados: falha em {user_nome} | {e}")
        return False, "Erro ao confirmar a atualização."


def definir_dados_funcionais(ator, user_nome, unidade=None, lotacao=None,
                             cargo=None):
    """Grava unidade, lotação e cargo do usuário (informação pública).

    Só os campos informados são alterados (`None` = manter). Devolve
    (True, msg) ou (False, motivo).
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_usuarios WHERE user_nome=?",
                        (user_nome,))
            if not (cur.fetchone()[0] or 0):
                return False, "Usuário não encontrado."
            campos, valores = [], []
            for campo, valor in (("unidade", unidade), ("lotacao", lotacao),
                                 ("cargo", cargo)):
                if valor is not None:
                    campos.append(f"{campo}=?")
                    valores.append(str(valor or "").strip())
            if not campos:
                return True, "Nada a alterar."
            valores.append(user_nome)
            cur.execute(f"UPDATE tb_usuarios SET {', '.join(campos)} "
                        f"WHERE user_nome=?", valores)
            _commit_com_retry(conn, contexto="definir_dados_funcionais")
            _audit(ator, "dados_funcionais_alterados", user_nome,
                   ", ".join(campos))
            return True, "Dados funcionais salvos."
        finally:
            conn.close()
    except Exception as e:
        _log().exception(
            f"definir_dados_funcionais: falha em {user_nome} | {e}")
        return False, "Erro ao salvar os dados funcionais."


def _normalizar_telefone_cadastro(numero):
    """Normaliza para apenas dígitos e `+`, para gravar e comparar.

    Aceita o que o usuário digita ('(00) 3591-5101', '00 3591 5101', '+55 00
    ...') e devolve uma forma canônica. Regra local de propósito: o módulo
    não pode depender do `mod_tisosdocfly.telefone` (que é do núcleo) para gravar,
    e a comparação de duplicidade precisa de uma forma só.
    """
    try:
        bruto = re.sub(r"[^0-9+]", "", str(numero or ""))
        if not bruto:
            return ""
        # '+' só no começo; '+55' duplicado vira um só. O corte só vale
        # acima de 13 dígitos: `+55` + nacional de 11 = 13 (canônico
        # correto, ex. `+5531999999999` — NÃO cortar); duplicado de verdade
        # (`+55+55` + 11 = 15) cai aqui e perde um `55`. Com `> 12` o
        # canônico correto de 13 era mutilado para `+31999999999` — que a
        # exibição lia como Bulgária (`+359 88183288`). (16/10/2026)
        tem_mais = bruto.startswith("+")
        digitos = re.sub(r"[^0-9]", "", bruto)
        if tem_mais and digitos.startswith("55") and len(digitos) > 13:
            digitos = digitos[2:]
        if not digitos:
            return ""
        return ("+" + digitos) if tem_mais else digitos
    except Exception:
        return ""


def _primeiro_e_ultimo(nome_completo):
    """"Ana Beatriz Souza Rocha" -> "Ana.rocha".

    Função LOCAL, e não importada de `leitura_lista.nome_para_exibicao`, pelo
    mesmo motivo daquele arquivo: `leitura_lista` importa este módulo, e o
    caminho inverso fecharia um ciclo de import.

    Formato 29/10/2026 (pedido do responsável, vale em TODA saudação do
    sistema): primeiro nome capitalizado + "." + último nome em minúsculas
    ("ana beatriz souza rocha" -> "Ana.rocha"). Parte única sai
    capitalizada; sem nome, "" (o chamador cai para o login).

    A regra é a mesma da lista telefônica: ninguém é tratado pelo nome
    inteiro em voz alta. Na saudação, "Ana.rocha" diz quem é; "Ana Beatriz
    Souza Rocha" ocupa a tela toda; e a matrícula "MT-1234" não diz nada sobre
    a pessoa. (Exemplo fictício, e a matrícula também.)"""
    partes = [p for p in str(nome_completo or "").split() if p]
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0].capitalize()
    return f"{partes[0].capitalize()}.{partes[-1].lower()}"
    return f"{partes[0]} {partes[-1]}"


def nome_de_tratamento(user_nome):
    """Display name for greetings/screens — "Primeiro.ultimo".

    Nome usado para tratamento nas telas — **primeiro e último nome** do
    cadastro (que guarda o nome completo ou social, Decreto 8.727/2016),
    no formato "Primeiro.ultimo" (29/10/2026: "ana beatriz souza rocha" ->
    "Ana.rocha").

    POR QUE PRIMEIRO E ÚLTIMO, E NÃO O NOME TODO
        O nome de usuário desta prefeitura é a **matrícula** (`MT-1234`).
        Mostrar isso na saudação é mostrar um código de barras com nome de
        pessoa: não diz nada, e a pessoa se reconhece no número como se
        reconhece numa placa. E o nome completo em tela cheia empurra o
        rótulo do perfil para fora. Primeiro e último é o que a pessoa ouve
        quando é chamada.

    O CABEÇALHO é a exceção: mostra sempre o login (matrícula), com este
    nome só no tooltip — ver `mod_tisosdocfly/telas.py`.

    Cai para o login só quando não existe nome completo — nesse caso não há
    outra coisa a mostrar, e o nome de login é melhor do que um campo vazio."""
    try:
        row = obter_usuario(user_nome)
        completo = (row[9] or "").strip() if row and len(row) > 9 else ""
        curto = _primeiro_e_ultimo(completo)
        return curto or completo or user_nome
    except Exception as e:
        _log().exception(f"nome_de_tratamento: falha para {user_nome} | {e}")
        return user_nome


def listar_acessos(user_nome):
    """Lists the user's per-module grants (modulo_chave, papel, liberado_por, data)."""
    conn = _conexao_segura()
    if conn is None:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT modulo_chave, papel, liberado_por, data_liberacao
               FROM tb_acesso_usuario WHERE user_nome=? ORDER BY modulo_chave""",
            (user_nome,),
        )
        linhas = []
        for r in cur.fetchall():
            linha = list(r)
            linha[3] = _normalizar_data(linha[3])
            linhas.append(tuple(linha))
        return linhas
    except Exception as e:
        _log().exception(f"listar_acessos: falha ao listar acessos de {user_nome} | {e}")
        return []
    finally:
        conn.close()


# ================= CRUD =================

def _validar_nome_completo(nome_completo, user_nome):
    """Validates the display/social name (min 3 chars, different from login)."""
    nc = (nome_completo or "").strip()
    if len(nc) < 3:
        return None, "Nome completo/social é obrigatório (mín. 3 caracteres)"
    if nc.lower() == (user_nome or "").strip().lower():
        return None, "O nome de exibição deve ser diferente do nome de login"
    return nc, None


def _validar_tipo_conta(tipo) -> str:
    """Normaliza o tipo de conta; desconhecido vira 'interno'.

    EN: Normalizes the account type; unknown values fall back to internal.

    PT-BR: O default seguro é `interno` porque um valor corrompido não pode
    transformar uma conta da equipe em conta de cliente (ou o contrário).
    """
    t = (tipo or "interno").strip().lower()
    return t if t in TIPOS_CONTA else "interno"


def _validar_cliente_id(cliente_id):
    """Valida o vínculo lógico com o cliente do núcleo.

    Devolve `(valor, erro)`. Vazio/None vira `(None, None)`; texto não
    numérico ou número não positivo vira erro — sem consultar o banco do
    núcleo, porque este módulo não faz cross-query (AGENTS §2.4)."""
    if cliente_id in (None, "", "__NULO__"):
        return None, None
    try:
        valor = int(str(cliente_id).strip())
        if valor <= 0:
            return None, "ID do cliente deve ser um número inteiro positivo"
        return valor, None
    except Exception:
        return None, "ID do cliente deve ser um número inteiro"


def criar_usuario(ator, user_nome, senha, email=None, fone=None, perfil="comum",
                   nome_completo="", exigir_telefone=True,
                   tipo_conta="interno", cliente_id=None):
    """Creates a user with a provisional password (mandatory first-login change).

    Valida login, senha mínima (`senha_minima`), perfil global e nome de
    exibição; grava hash bcrypt, libera o acesso padrão 'comum'
    (`ACESSO_PADRAO_NOVO_USUARIO`), marca `forcar_troca` e audita
    `criar_usuario`. Senha vazia/None cai no padrão inicial ``123456``.

    `tipo_conta` distingue `interno` (equipe T! SOS DocFly) de `cliente`
    (contratante do laudo). Conta `cliente` nasce SEMPRE com perfil global
    `comum` e sem acesso ao módulo `usuarios`, mesmo que o chamador tente
    passar um perfil administrativo. `cliente_id` é opcional e guarda apenas
    o inteiro de referência lógica — sem consulta ao banco do núcleo.

    `exigir_telefone=True` (padrão) marca `telefone_pendente`, e o primeiro
    acesso pede os telefones depois da troca de senha: o portal da
    transparência não publica ramal, então o telefone da lista só existe se o
    próprio servidor informar. Contas de serviço (robô, integração) passam
    `False` — não têm pessoa para atender o telefone.
    Retorna `(ok, msg)`."""
    from mod_tisosdocfly.autenticacao import gerar_hash_senha, marcar_trocar_senha
    senha = (senha or "").strip() or "123456"
    if not user_nome or not user_nome.strip():
        return False, "Nome de usuário é obrigatório"
    if len(senha or "") < senha_minima():
        return False, f"Senha provisória deve ter no mínimo {senha_minima()} caracteres"
    tipo_conta = _validar_tipo_conta(tipo_conta)
    cliente_id, erro_cliente = _validar_cliente_id(cliente_id)
    if erro_cliente:
        return False, erro_cliente
    if tipo_conta == "cliente":
        # Cliente nunca nasce administrador: o perfil global é rebaixado
        # aqui, no backend, e não apenas escondido na tela.
        perfil = "comum"
    if perfil not in PERFIS_GLOBAIS:
        return False, f"Perfil inválido: {perfil}"
    nome_c, erro = _validar_nome_completo(nome_completo, user_nome)
    if erro:
        return False, erro
    conn = _conexao_segura()
    if conn is None:
        return False, "Falha ao conectar no banco de usuários"
    try:
        cur = conn.cursor()
        hash_s = gerar_hash_senha(senha)
        cur.execute(
            """INSERT INTO tb_usuarios
               (user_nome, user_senha, user_email, user_fone, user_perfil, user_ativo,
                user_nome_completo, telefone_pendente, user_tipo, cliente_id)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
            (user_nome.strip(), hash_s, email, fone, perfil, nome_c,
             1 if exigir_telefone else 0, tipo_conta, cliente_id),
        )
        if tipo_conta != "cliente":
            for chave in ACESSO_PADRAO_NOVO_USUARIO:
                cur.execute(
                    "INSERT INTO tb_acesso_usuario (user_nome, modulo_chave, papel, liberado_por) VALUES (?, ?, 'comum', ?)",
                    (user_nome.strip(), chave, ator),
                )
        _commit_com_retry(conn, contexto=f"criar_usuario:{user_nome}")
        # A pessoa nasce com o nome de exibição preenchido, e o nome é o
        # que a busca casa primeiro — sem este índice o servidor recién
        # criado só apareceria na busca depois do próximo `init_db`.
        _reindexar(cur, user_nome.strip())
        _commit_com_retry(conn, contexto=f"criar_usuario:busca:{user_nome}")
        marcar_trocar_senha(user_nome.strip(), True)
        _audit(ator, "criar_usuario", user_nome.strip(),
               f"perfil={perfil} | tipo={tipo_conta} | cliente_id={cliente_id or '-'} | exibição: {nome_c}")
        _log().info(f"usuário criado: {user_nome.strip()} perfil={perfil} "
                    f"tipo={tipo_conta} por {ator}")
        return True, "Usuário criado (senha provisória — troca obrigatória no 1º acesso)"
    except Exception as e:
        if _eh_violacao_unicidade(e):
            _rollback_seguro(conn, contexto=f"criar_usuario:{user_nome}")
            _log().warning(f"criar_usuario: nome já existe: {user_nome}")
            return False, "Nome de usuário já existe"
        _rollback_seguro(conn, contexto=f"criar_usuario:{user_nome}")
        _log().exception(f"criar_usuario: falha ao criar usuário {user_nome} | {e}")
        return False, "Erro inesperado ao criar usuário"
    finally:
        conn.close()


def editar_usuario(ator, user_nome, email="__NULO__", fone="__NULO__",
                   perfil=None, ativo=None, deletado=None, nome_completo="__NULO__",
                   auditar=True, tipo_conta=None, cliente_id="__NULO__",
                   **campos_folha):
    """Edits personal data/global profile (RF-26 last-admin guard).

    Edita dados pessoais/perfil global. Use '__NULO__' p/ manter campo.
    Protege o último `administrador_geral` ativo (RF-26) e veda
    auto-rebaixamento/auto-desativação.

    **OS CAMPOS DA FOLHA NÃO SE GRAVAM AQUI (03/10/2026).**
    Tudo o que está em `CAMPOS_PROTEGIDOS_FOLHA` — secretaria, lotação,
    cargo, vínculo, situação, tipo, admissão, exoneração, regime, carga
    horária, remuneração, ficha de contracheque e o espelho da folha — é
    recusado aqui, no BACKEND, e não só escondido na tela.

    Por que no backend: a tela é a interface, e interface é o que o
    usuário contorna. `editar_usuario` é chamada pelo painel, pela carga
    da folha e por qualquer coisa que importe este módulo; se a trava
    vivesse só na UI, um `curl` na API, uma tela nova, ou um teste
    escreveriam por cima da folha — e o cadastro passaria a discordar do
    portal da transparência, que é o documento que a prefeitura publica
    e que o Ministério Público pede.

    A recusa é por NOME, lida da lista única, e devolve mensagem dizendo
    qual é a fonte. `**campos_folha` aceita qualquer chave: quem chamar
    tentando gravar `cargo='Diretor'` recebe o erro em vez de gravar.

    `tipo_conta` (`interno`/`cliente`) e `cliente_id` são os campos do
    vínculo de produto (02/11/2026). Ao converter para `cliente`, o perfil
    global é forçado para `comum` e o acesso ao módulo `usuarios` é
    removido na mesma transação.

    EN: Refuses the staff-sheet fields; they belong to the sheet, not to
    whoever is logged in.
    """
    conn = _conexao_segura()
    if conn is None:
        return False, "Falha ao conectar no banco de usuários"
    try:
        proibidos = [c for c in campos_folha
                     if c in CAMPOS_PROTEGIDOS_FOLHA and campos_folha[c] is not None]
        if proibidos:
            _log().warning(
                f"editar_usuario: recusa de campo da folha em {user_nome} por "
                f"{ator}: {', '.join(sorted(proibidos))} — a fonte é a folha "
                f"de servidores, não o cadastro manual")
            return False, (
                f"Campo da folha não pode ser alterado aqui: "
                f"{', '.join(sorted(proibidos))}. A fonte é a folha de "
                f"servidores do portal da transparência.")
        cur = conn.cursor()
        cur.execute("SELECT id FROM tb_usuarios WHERE user_nome=?", (user_nome,))
        if not cur.fetchone():
            return False, "Usuário não existe"
        # RF-26: outro administrador não pode rebaixar nem bloquear o último
        # administrador_geral ativo do sistema.
        if ator != user_nome:
            cur.execute("SELECT user_perfil, user_ativo FROM tb_usuarios WHERE user_nome=?", (user_nome,))
            linha = cur.fetchone()
            if linha and linha[0] == "administrador_geral" and linha[1] == 1:
                vai_rebaixar = perfil is not None and perfil != "administrador_geral"
                vai_bloquear = ativo is not None and not ativo
                if vai_rebaixar or vai_bloquear:
                    cur.execute(
                        "SELECT COUNT(*) FROM tb_usuarios "
                        "WHERE user_perfil='administrador_geral' AND user_ativo=1")
                    if cur.fetchone()[0] <= 1:
                        return False, "Não é possível rebaixar/bloquear o último administrador geral ativo"
        sets, params, mudancas = [], [], []
        if tipo_conta is not None:
            tipo_norm = _validar_tipo_conta(tipo_conta)
            if tipo_norm == "cliente":
                # Conta de cliente não pode carregar perfil administrativo:
                # o rebaixamento vale para edição, não só para criação.
                perfil = "comum"
            sets.append("user_tipo=?"); params.append(tipo_norm)
            mudancas.append(f"tipo={tipo_norm}")
        if cliente_id != "__NULO__":
            cid, erro_cliente = _validar_cliente_id(cliente_id)
            if erro_cliente:
                return False, erro_cliente
            sets.append("cliente_id=?"); params.append(cid)
            mudancas.append(f"cliente_id={cid or '-'}")
        if nome_completo != "__NULO__":
            nc, erro = _validar_nome_completo(nome_completo, user_nome)
            if erro:
                return False, erro
            sets.append("user_nome_completo=?"); params.append(nc)
            mudancas.append(f"nome de exibição: {nc}")
        if email != "__NULO__":
            sets.append("user_email=?"); params.append(email or None); mudancas.append("email")
        if fone != "__NULO__":
            sets.append("user_fone=?"); params.append(fone or None); mudancas.append("telefone")
        if perfil:
            if perfil not in PERFIS_GLOBAIS:
                return False, f"Perfil inválido: {perfil}"
            if ator == user_nome:
                cur.execute("SELECT user_perfil FROM tb_usuarios WHERE user_nome=?", (user_nome,))
                atual = cur.fetchone()
                if atual and atual[0] == "administrador_geral" and perfil != "administrador_geral":
                    return False, "Você não pode remover o próprio perfil de administrador geral"
            sets.append("user_perfil=?"); params.append(perfil); mudancas.append(f"perfil={perfil}")
        if ativo is not None:
            if ator == user_nome and not ativo:
                return False, "Você não pode desativar a própria conta"
            sets.append("user_ativo=?"); params.append(1 if ativo else 0)
            mudancas.append("ativo" if ativo else "inativo")
        if deletado is not None:
            if ator == user_nome and deletado:
                return False, "Você não pode excluir a própria conta"
            sets.append("user_deletado=?"); params.append(1 if deletado else 0)
            mudancas.append("restaurado" if not deletado else "soft")
        if not sets:
            return True, "Nada a alterar"
        if tipo_conta is not None and _validar_tipo_conta(tipo_conta) == "cliente":
            # Garantia de backend: conta de cliente não mantém o acesso ao
            # módulo administrativo de usuários, mesmo que alguém tente
            # concedê-lo pela tela de acessos no mesmo instante.
            cur.execute("DELETE FROM tb_acesso_usuario "
                        "WHERE user_nome=? AND modulo_chave='usuarios'",
                        (user_nome,))
        params.append(user_nome)
        cur.execute(f"UPDATE tb_usuarios SET {', '.join(sets)} WHERE user_nome=?", tuple(params))  # nosec B608 — sets só literais fixos "col=?"; valores via ?
        _commit_com_retry(conn, contexto=f"editar_usuario:{user_nome}")
        # E-mail, telefone, perfil e nome de exibição são todos campos que a
        # busca alcança: mudados aqui, o `busca_norm` fica velho no mesmo
        # instante se ninguém reescrever. Uma linha por edição.
        _reindexar(cur, user_nome)
        _commit_com_retry(conn, contexto=f"editar_usuario:busca:{user_nome}")
        if auditar:
            _audit(ator, "editar_usuario", user_nome, ", ".join(mudancas))
        _log().info(f"usuário editado: {user_nome} | {', '.join(mudancas)} por {ator}")
        return True, "Usuário atualizado"
    except Exception as e:
        _rollback_seguro(conn, contexto=f"editar_usuario:{user_nome}")
        _log().exception(f"editar_usuario: falha ao editar {user_nome} | {e}")
        return False, "Erro inesperado ao editar usuário"
    finally:
        conn.close()


# Tabelas que carregam o login e por isso precisam do mesmo UPDATE
# quando o login muda. Declaradas aqui para que a propagação e a limpeza
# de órfãos leiam a MESMA lista — foi assim que `tb_login_tentativas` e
# `tb_remuneracao_historico` ficaram de fora do renomeio quando as duas
# tabelas novas nasceram. `tb_foto_mensal` entra (tem `user_nome`);
# `tb_cargas_folha` NÃO entra (é por competência, sem coluna `user_nome` —
# o UPDATE/DELETE do laço falharia com "no such column").
_TABELAS_POR_LOGIN = ("tb_login_tentativas", "tb_remuneracao_historico",
                      "tb_contratos", "tb_historico_movimentos",
                      "tb_historico_salarial", "tb_foto_mensal")


def _propagar_renomeio(cur, nome_atual, novo_nome):
    """Repassa o login novo para as tabelas que o guardam.

    Idempotente e sem transação própria: quem chama já está numa
    transação (`renomear_usuario`), e um commit aqui cortaria o renomeio
    pela metade se a próxima etapa falhasse.
    """
    for tabela in _TABELAS_POR_LOGIN:
        try:
            cur.execute(f"UPDATE {tabela} SET user_nome=? WHERE user_nome=?",
                        (novo_nome, nome_atual))
        except Exception as e:
            # Uma tabela que ainda não existe numa base antiga não pode
            # derrubar o renomeio do login — o usuário ficaria com o
            # login novo e o histórico no nome velho, que é o cenário
            # pior. Registra e segue; o `init_db` recria a tabela.
            _log().warning(f"_propagar_renomeio: falhou em {tabela} | {e}")
    try:
        cur.execute("DELETE FROM tb_acesso_usuario WHERE user_nome NOT IN "
                    "(SELECT user_nome FROM tb_usuarios)")
    except Exception as e:
        _log().warning(f"_propagar_renomeio: falha na limpeza de órfãos | {e}")
    return True


def _apagar_por_login(cur, user_nome):
    """Apaga as linhas das tabelas por login. Paridade com o CASCADE do PG.

    No SQLite a FK `ON DELETE CASCADE` faz isso sozinha; no PostgreSQL o
    `_ddl_postgres` remove a REFERENCES e quem apaga é a aplicação. Se
    isto sumir, a exclusão definitiva no PostgreSQL deixa o histórico da
    pessoa — e é a exclusão definitiva que é a ação de LGPD, a única em
    que apagar o histórico é o comportamento CORRETO.
    """
    for tabela in _TABELAS_POR_LOGIN:
        try:
            cur.execute(f"DELETE FROM {tabela} WHERE user_nome=?", (user_nome,))
        except Exception as e:
            _log().warning(f"_apagar_por_login: falhou em {tabela} | {e}")
    return True


def renomear_usuario(ator, nome_atual, novo_nome, permitir_master=False):
    """Renames the login keeping the PK id, propagating to dependents.

    Renomeia mantendo o ID (chave primária), replicando nas tabelas
    dependentes (`tb_acesso_usuario`, sessões centrais e autorias nos
    demais módulos). `permitir_master=True` libera a renomeação do
    `master` nativo — usado EXCLUSIVAMENTE no primeiro acesso (troca de
    credenciais obrigatória). Paridade PG: o `_ddl_postgres` do núcleo
    remove `REFERENCES ... ON DELETE/UPDATE CASCADE` — a integridade é
    gerida na aplicação (UPDATE manual nas duas tabelas + limpeza de
    órfãos abaixo); commit com retry em `database is locked` e rollback
    em falha parcial (AGENTS §3.2)."""
    novo_nome = (novo_nome or "").strip()
    if not novo_nome:
        return False, "Novo nome vazio"
    if nome_atual == "master" and not permitir_master:
        return False, "A conta master nativa não pode ser renomeada"
    conn = _conexao_segura()
    if conn is None:
        return False, "Falha ao conectar no banco de usuários"
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM tb_usuarios WHERE user_nome=?", (novo_nome,))
        if cur.fetchone():
            # Mensagem que diz o que fazer: o diálogo de troca de credenciais
            # traz o nome pré-preenchido com um valor fixo, e se esse nome já
            # estiver em uso o rename falha. Como as flags de troca SÓ caem
            # depois de um rename bem-sucedido (`autenticacao.py`), a recusa
            # aqui abre um ciclo — o diálogo reabre no boot seguinte e falha
            # igual, sem caminho de saída (29/09/2026). Dizer "já existe" sem
            # orientar deixa quem instala sem saber que basta trocar o nome.
            return False, (f"'{novo_nome}' já é o login de outro usuário. "
                           f"Escolha um nome de usuário diferente.")
        cur.execute("SELECT id FROM tb_usuarios WHERE user_nome=?", (nome_atual,))
        if not cur.fetchone():
            return False, "Usuário não existe"
        cur.execute("UPDATE tb_usuarios SET user_nome=? WHERE user_nome=?", (novo_nome, nome_atual))
        cur.execute("UPDATE tb_acesso_usuario SET user_nome=? WHERE user_nome=?", (novo_nome, nome_atual))
        # Contratos, movimentos e histórico salarial (03/10/2026). A FK
        # `ON UPDATE CASCADE` cobre o SQLite; estas linhas cobrem o
        # PostgreSQL, onde o `_ddl_postgres` remove as REFERENCES e a
        # integridade é gerida na aplicação. Sem elas, um renomeio de
        # credenciais deixaria o histórico órfão — e a exclusão
        # definitiva apagaria a pessoa sem o histórico que a acompanha.
        _propagar_renomeio(cur, nome_atual, novo_nome)
        # Limpeza manual de órfãos (PG sem FKs — ver docstring): remove
        # vínculos cujo user_nome não existe mais em tb_usuarios.
        try:
            cur.execute("DELETE FROM tb_acesso_usuario WHERE user_nome NOT IN (SELECT user_nome FROM tb_usuarios)")
        except Exception as e_orf:
            _log().warning(f"renomear_usuario: falha na limpeza de órfãos | {e_orf}")
        _commit_com_retry(conn, contexto=f"renomear_usuario:{nome_atual}->{novo_nome}")
        _audit(ator, "renomear_usuario", nome_atual, f"→ {novo_nome} (ID preservado)")
        # reflete também nas sessões do banco central
        try:
            c = _central(); cc = c.cursor()
            cc.execute("UPDATE tb_sessoes SET usuario=? WHERE usuario=? AND logout_timestamp IS NULL",
                       (novo_nome, nome_atual))
            c.commit(); c.close()
        except Exception as e:
            _log().warning(f"renomear_usuario: falha ao refletir em sessões centrais | {e}")
        _vinculos_cruzados_renomear(nome_atual, novo_nome)
        _log().info(f"usuário renomeado: {nome_atual} -> {novo_nome} por {ator}")
        return True, f"Renomeado para '{novo_nome}'"
    except Exception as e:
        if _eh_violacao_unicidade(e):
            _rollback_seguro(conn, contexto=f"renomear_usuario:{nome_atual}")
            _log().warning(f"renomear_usuario: conflito de unicidade para '{novo_nome}'")
            return False, "Conflito de unicidade"
        _rollback_seguro(conn, contexto=f"renomear_usuario:{nome_atual}")
        _log().exception(f"renomear_usuario: falha ao renomear {nome_atual} | {e}")
        return False, "Erro inesperado ao renomear usuário"
    finally:
        conn.close()


def alterar_senha_admin(ator, user_nome, nova_senha):
    """Admin password reset (provisional, forces change, drops sessions).

    Troca administrativa de senha (reenvio provisório): valida o mínimo
    (`senha_minima`), marca `forcar_troca` e encerra todas as sessões."""
    if len(nova_senha or "") < senha_minima():
        return False, f"Mínimo {senha_minima()} caracteres"
    from mod_tisosdocfly.autenticacao import gerar_hash_senha, marcar_trocar_senha
    conn = _conexao_segura()
    if conn is None:
        return False, "Falha ao conectar no banco de usuários"
    try:
        cur = conn.cursor()
        cur.execute("UPDATE tb_usuarios SET user_senha=? WHERE user_nome=?",
                    (gerar_hash_senha(nova_senha), user_nome))
        if cur.rowcount == 0:
            return False, "Usuário não existe"
        _commit_com_retry(conn, contexto=f"alterar_senha_admin:{user_nome}")
        marcar_trocar_senha(user_nome, True)
        _fechar_sessoes_central(user_nome)  # senha redefinida -> todas as sessões caem
        _audit(ator, "alterar_senha", user_nome, "senha provisória definida pelo admin; sessões encerradas")
        _log().info(f"senha redefinida (admin): {user_nome} por {ator}")
        return True, "Senha redefinida — sessões encerradas e troca obrigatória no próximo acesso"
    except Exception as e:
        _rollback_seguro(conn, contexto=f"alterar_senha_admin:{user_nome}")
        _log().exception(f"alterar_senha_admin: falha ao redefinir senha de {user_nome} | {e}")
        return False, "Erro inesperado ao redefinir senha"
    finally:
        conn.close()


def liberar_acesso_definitivo(ator, user_nome):
    """Libera em definitivo uma conta que estava em liberação temporária.

    É o botão do DTI — o contrário de `bloqueio_provisorio_pendente`.
    O servidor entra, o prazo de 4 dias vence, a conta fecha; ele vai ao
    departamento de tecnologia, descobre o número do setor e o técnico libera
    aqui. Sem esta função, a conferência seria feita direto no banco, e
    cadastro de servidor não se arruma direto no banco.

    A liberação é definitiva: a conta volta a ser normal. Se o servidor
    estiver sem telefone da prefeitura ainda hoje, o DTI precisa
    cadastrar o número **antes** de chamar esta função — a verificação é
    feita aqui, não na tela, para que a conta não fique "liberada" e
    sem telefone. Se o DTI liberar sem telefone, o paliativo recomeça.
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tb_usuarios WHERE user_nome=?",
                        (user_nome,))
            if not (cur.fetchone()[0] or 0):
                return False, "Usuário não encontrado."
            tem_prefeitura = cur.execute(
                "SELECT COUNT(*) FROM tb_telefone_usuario "
                "WHERE user_nome=? AND papel='empresa' AND tipo='fixo'",
                (user_nome,)).fetchone()[0]
            pendente = cur.execute(
                "SELECT telefone_pendente FROM tb_usuarios WHERE user_nome=?",
                (user_nome,)).fetchone()[0]
        finally:
            conn.close()
        if not tem_prefeitura:
            return False, ("Este cadastro ainda não tem telefone da "
                           "prefeitura (fixo). Cadastre o número — o próprio "
                           "ou o do setor como recado — antes de liberar.")
        cur2 = get_connection()
        try:
            c2 = cur2.cursor()
            # `liberado_pelo_dti` (06/10/2026) é gravado junto, e é o que
            # torna a liberação AUTORITATIVA: `carga_folha._bloquear_apos_
            # espelho` tem um caminho de volta que reabre conta fechada, e sem
            # esta marca o servidor perderia o acesso de novo no próximo boot
            # — a folha desfazendo o que o DTI fez, sozinha e sem erro.
            c2.execute("UPDATE tb_usuarios SET acesso_provisorio=0, "
                       "provisorio_ate=NULL, telefone_pendente=0, "
                       "user_ativo=1, liberado_pelo_dti=1, "
                       "liberado_dti_em=CURRENT_TIMESTAMP, "
                       "liberado_dti_por=? WHERE user_nome=?",
                       (str(ator or "dti"), user_nome))
            _commit_com_retry(cur2, contexto="liberar_acesso_definitivo")
        finally:
            cur2.close()
        _audit(ator, "liberar_acesso_definitivo", user_nome,
               "liberado em definitivo" + (" (tinha telefone pendente)"
                                           if pendente else ""))
        _log().info(f"acesso liberado em definitivo para {user_nome} por {ator}")
        return True, "Acesso liberado em definitivo."
    except Exception as e:
        _log().exception(f"liberar_acesso_definitivo: falha em {user_nome} | {e}")
        return False, "Erro ao liberar o acesso."


def informacao_acesso_provisorio(user_nome) -> dict:
    """EN: The temporary-release state of an account, for screens and the DTI.

    PT-BR: O estado da liberação temporária de uma conta, para as telas e
    para o DTI ver quem está no prazo e quem já venceu."""
    vazio = {"provisorio": False, "ate": None, "vencido": False,
             "bloqueado": True, "dias_restantes": None}
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT acesso_provisorio, provisorio_ate, user_ativo "
                        "FROM tb_usuarios WHERE user_nome=?", (user_nome,))
            linha = cur.fetchone()
        finally:
            conn.close()
        if not linha:
            return vazio
        bloqueado = not bool(linha[2])
        if not linha[0] or not linha[1]:
            # sem liberação temporária: a conta é normal. `bloqueado` continua
            # valendo, porque é o que a tela do DTI quer mostrar.
            return {**vazio, "bloqueado": bloqueado}
        try:
            prazo = datetime.strptime(str(linha[1])[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return {**vazio, "bloqueado": bloqueado}
        restante = prazo - datetime.now()
        return {"provisorio": True, "ate": linha[1],
                # `vencido` é o PRAZO. A conta estar bloqueada é outra
                # coisa — no começo estes dois campos eram o mesmo, e uma
                # conta liberada aparecia como vencida no primeiro dia.
                "vencido": restante.total_seconds() <= 0,
                "bloqueado": bloqueado,
                "dias_restantes": max(0, restante.days)}
    except Exception as e:
        _log().exception(f"informacao_acesso_provisorio: falha em {user_nome} | {e}")
        return vazio


def bloquear_usuario(ator, user_nome, bloquear=True):
    """Blocks/unblocks an account (unblock also clears soft-delete).

    Bloqueia (ativo=0). Desbloquear também restaura soft-delete (limpa
    `user_motivo_exclusao`) e ganha trilha dedicada (`bloquear_usuario` /
    `desbloquear_usuario`)."""
    if ator == user_nome and bloquear:
        return False, "Você não pode bloquear a si mesmo"
    try:
        kw = {"deletado": False} if not bloquear else {}
        # 'auditar=False': a ação ganha trilha DEDICADA abaixo (bloquear_usuario ou
        # desbloquear_usuario) em vez de um 'editar_usuario' genérico.
        ok, msg = editar_usuario(ator, user_nome, ativo=(not bloquear), auditar=False, **kw)
        if ok:
            if not bloquear:  # restauração limpa o motivo da exclusão lógica
                conn = _conexao_segura()
                if conn is not None:
                    try:
                        conn.execute("UPDATE tb_usuarios SET user_motivo_exclusao=NULL WHERE user_nome=?",
                                     (user_nome,))
                        _commit_com_retry(conn, contexto=f"bloquear_usuario:{user_nome}")
                    except Exception as e2:
                        _rollback_seguro(conn, contexto=f"bloquear_usuario:{user_nome}")
                        _log().exception(f"bloquear_usuario: falha ao limpar motivo de {user_nome} | {e2}")
                    finally:
                        conn.close()
            if bloquear:
                _fechar_sessoes_central(user_nome)
            _audit(ator, "bloquear_usuario" if bloquear else "desbloquear_usuario",
                   user_nome, "conta bloqueada" if bloquear else "conta restaurada (inclui soft delete)")
            _log().info(f"usuário {'bloqueado' if bloquear else 'restaurado'}: {user_nome} por {ator}")
        return ok, msg
    except Exception as e:
        _log().exception(f"bloquear_usuario: falha para {user_nome} | {e}")
        return False, "Erro inesperado ao bloquear/restaurar conta"


def soft_delete_usuario(ator, user_nome, motivo=None):
    """Logical delete with mandatory reason — moves to the deleted list.

    Exclusão LÓGICA com motivo obrigatório — vai para a lista de
    excluídos. Não apaga nada: reversível via 'Restaurar'. A exclusão
    permanente (LGPD) é ação separada, disponível apenas na lista de
    excluídos."""
    if user_nome == "master":
        return False, "A conta master nativa não pode ser excluída"
    if ator == user_nome:
        return False, "Você não pode excluir a própria conta"
    motivo = (motivo or "").strip()
    if len(motivo) < 3:
        return False, "Informe o motivo da exclusão (mín. 3 caracteres)"
    try:
        ok, msg = editar_usuario(ator, user_nome, ativo=False, deletado=True)
        if not ok:
            return ok, msg
        conn = _conexao_segura()
        if conn is not None:
            try:
                conn.execute("UPDATE tb_usuarios SET user_motivo_exclusao=? WHERE user_nome=?",
                             (motivo, user_nome))
                _commit_com_retry(conn, contexto=f"soft_delete:{user_nome}")
            except Exception as e2:
                _rollback_seguro(conn, contexto=f"soft_delete:{user_nome}")
                _log().exception(f"soft_delete_usuario: falha ao gravar motivo de {user_nome} | {e2}")
            finally:
                conn.close()
        _fechar_sessoes_central(user_nome)
        _audit(ator, "soft_delete", user_nome, f"motivo: {motivo}")
        _log().info(f"exclusão lógica: {user_nome} por {ator} | motivo: {motivo}")
        return True, f"'{user_nome}' movido para a lista de excluídos"
    except Exception as e:
        _log().exception(f"soft_delete_usuario: falha para {user_nome} | {e}")
        return False, "Erro inesperado ao excluir usuário"


def _vinculos_cruzados_excluir(user_nome):
    """Removes/anonymizes the user's references in other modules (LGPD).

    Remove/anonimiza referências do usuário nos demais módulos (LGPD).
    Blog: postagens e comentários apagados. EditorPDF: arquivos físicos,
    registros e cota apagados. Empenhos: registros públicos preservados
    com autoria anonimizada.

    Isolamento total: cada módulo limpa o PRÓPRIO banco através de sua
    API pública — nunca há cross-query entre bancos."""
    det = []
    try:
        from mod_blog import bd_manipulador as _blog
        n = _blog.remover_vinculos_usuario(user_nome)
        if n:
            det.append(f"{n} postagem(ns)")
    except Exception as e:
        det.append("blog: falhou")
        _log().exception(f"_vinculos_cruzados_excluir: blog falhou para {user_nome} | {e}")
    try:
        from mod_edit_pdf import bd_manipulador as _pdf
        removidos, nomes = _pdf.remover_vinculos_usuario(user_nome)
        if removidos or nomes:
            det.append(f"{removidos} arquivo(s) PDF")
    except Exception as e:
        det.append("pdf: falhou")
        _log().exception(f"_vinculos_cruzados_excluir: pdf falhou para {user_nome} | {e}")
    try:
        from mod_renomear_empenho import bd_manipulador as _emp
        n = _emp.anonimizar_usuario(user_nome)
        if n:
            det.append(f"{n} empenho(s) anonimizado(s)")
    except Exception as e:
        det.append("empenhos: falhou")
        _log().exception(f"_vinculos_cruzados_excluir: empenhos falhou para {user_nome} | {e}")
    return det


def _vinculos_cruzados_renomear(nome_atual, novo_nome):
    """Propagates a rename to authorship columns in other modules.

    Propaga o renomeio para colunas de autoria nos demais módulos
    (Blog, EditorPDF, Empenhos).

    Isolamento total: cada módulo atualiza o PRÓPRIO banco através de
    sua API pública — nunca há cross-query entre bancos."""
    try:
        from mod_blog import bd_manipulador as _blog
        _blog.renomear_autor(nome_atual, novo_nome)
    except Exception as e:
        _log().warning(f"_vinculos_cruzados_renomear: falha ao propagar {nome_atual}->{novo_nome} | {e}")
    try:
        from mod_edit_pdf import bd_manipulador as _pdf
        _pdf.renomear_usuario(nome_atual, novo_nome)
    except Exception as e:
        _log().warning(f"_vinculos_cruzados_renomear: falha ao propagar {nome_atual}->{novo_nome} | {e}")
    try:
        from mod_renomear_empenho import bd_manipulador as _emp
        _emp.renomear_usuario(nome_atual, novo_nome)
    except Exception as e:
        _log().warning(f"_vinculos_cruzados_renomear: falha ao propagar {nome_atual}->{novo_nome} | {e}")


def excluir_usuario_definitivo(ator, user_nome):
    """Permanently deletes a user (LGPD) with cross-module cleanup.

    Exclusivo do `administrador_geral` (revalidado no backend). Remove
    postagens/comentários do Blog, arquivos/cota do editorPDF e anonimiza
    autoria de empenhos (`_vinculos_cruzados_excluir`), apaga acessos e o
    usuário, encerra sessões e audita `excluir_definitivo`. `master` e a
    própria conta do ator são protegidos; o último admin geral ativo também.
    Retorna `(ok, msg)`."""
    conn = None
    try:
        from mod_tisosdocfly import autenticacao  # import tardio: evita ciclo de imports
        if autenticacao.perfil_global_de(ator) != "administrador_geral":
            return False, "Apenas o administrador geral do sistema pode excluir definitivamente (LGPD)"
        if user_nome == "master":
            return False, "A conta master nativa não pode ser excluída"
        if ator == user_nome:
            return False, "Você não pode excluir a própria conta"
        conn = _conexao_segura()
        if conn is None:
            return False, "Falha ao conectar no banco de usuários"
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM tb_usuarios WHERE user_perfil='administrador_geral' AND user_ativo=1 AND user_nome=?",
            (user_nome,),
        )
        if cur.fetchone()[0] > 0:
            cur.execute("SELECT COUNT(*) FROM tb_usuarios WHERE user_perfil='administrador_geral' AND user_ativo=1")
            if cur.fetchone()[0] <= 1:
                return False, "Não é possível excluir o último administrador ativo"
        detalhes = _vinculos_cruzados_excluir(user_nome)
        cur.execute("DELETE FROM tb_acesso_usuario WHERE user_nome=?", (user_nome,))
        # Contratos, movimentos e histórico salarial: o CASCADE do SQLite
        # faz sozinho, e aqui é o que faz no PostgreSQL (ver
        # `_apagar_por_login`). Esta é a única operação em que apagar o
        # histórico é o comportamento certo — é a exclusão definitiva de
        # LGPD, pedida pelo titular.
        _apagar_por_login(cur, user_nome)
        cur.execute("DELETE FROM tb_usuarios WHERE user_nome=?", (user_nome,))
        _commit_com_retry(conn, contexto=f"excluir_definitivo:{user_nome}")
        _fechar_sessoes_central(user_nome)
        # CONTA DE FÁBRICA APAGADA: grava o marcador que impede a semente de
        # `init_db` de recriá-la no próximo boot (04/10/2026, pedido do
        # responsável). Sem isto, apagar `qacomum`/`qamaster` da tela de
        # credenciais do `master` não resolvia nada — a semente é idempotente e
        # recria a conta a cada reinício enquanto ela não existir, e o botão
        # voltaria sozinho.
        #
        # É o mesmo mecanismo de `_troca_de_credencial_do_master_concluida`, e
        # pelo mesmo motivo: uma vez gravado, o estado não volta atrás sozinho.
        # E não é remoção automática — a conta só some porque o ADMINISTRADOR
        # pediu agora, à frente desta linha. Nada aqui apaga conta sozinho
        # (§8.2.0 do AGENTS.md).
        #
        # Só as de fábrica recebe marca: apagar um servidor comum é um caso
        # diferente, e a marca seria mentira — a semente não o recriaria mesmo.
        if user_nome in CONTAS_DE_FABRICA:
            try:
                from mod_tisosdocfly.bd_conexao import set_config as _set_cfg
                _set_cfg(f"conta_fabrica_removida:{user_nome}", "1")
                _log().info(f"conta de fábrica '{user_nome}' marcada como "
                            f"removida — não voltará no próximo boot")
            except Exception as _e_marca:
                # Falha na MARCA não desfaz a exclusão já confirmada no banco:
                # a conta some, e no máximo volta na semente. Registrar e
                # seguir é melhor que reverter um DELETE físico.
                _log().warning(f"não foi possível gravar a marca de "
                               f"conta de fábrica removida para "
                               f"'{user_nome}': {_e_marca}")
        extra = f" | {', '.join(detalhes)}" if detalhes else ""
        _audit(ator, "excluir_definitivo", user_nome, f"DELETE físico (LGPD){extra}")
        _log().info(f"exclusão definitiva (LGPD): {user_nome} por {ator}{extra}")
        msg = "Usuário excluído definitivamente"
        if detalhes:
            msg += f" ({', '.join(detalhes)})"
        return True, msg
    except Exception as e:
        try:
            _rollback_seguro(conn, contexto=f"excluir_definitivo:{user_nome}")
        except Exception:
            pass
        _log().exception(f"excluir_usuario_definitivo: falha ao excluir {user_nome} | {e}")
        return False, "Erro inesperado ao excluir definitivamente"
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def duplicar_usuario(ator, usuario_origem, novo_nome, senha, email=None,
                     fone=None, nome_completo=""):
    """Duplicates a user with all per-module access (profile + flags).

    Duplica um usuário existente e todas as suas configurações de acesso.
    Copia o perfil global e o papel do usuário origem em cada módulo
    (tb_acesso_usuario, incluindo flags finas). O novo usuário é criado
    exigindo apenas os dados essenciais (login, nome, senha e email) —
    as permissões vêm da origem. Senha vazia/None cai no padrão inicial
    ``123456``.
    """
    try:
        senha = (senha or "").strip() or "123456"
        origem = obter_usuario(usuario_origem)
        if not origem:
            return False, "Usuário origem não encontrado"
        perfil_origem = origem[5]
        ok, msg = criar_usuario(ator, novo_nome, senha,
                                email=email, fone=fone, perfil=perfil_origem,
                                nome_completo=nome_completo)
        if not ok:
            return False, msg
        # replica acessos por módulo (perfil) da origem
        for chave, papel, _liberado, _data in listar_acessos(usuario_origem):
            gest_sys = definir_acesso(ator, novo_nome, chave, papel)
            if not gest_sys[0]:
                _log().warning(f"duplicar_usuario: falha ao replicar acesso {chave} "
                               f"para {novo_nome} | {gest_sys[1]}")
            else:
                _flags_origem = obter_flags(usuario_origem, chave)
                if _flags_origem:
                    ok_f, msg_f = definir_flags(ator, novo_nome, chave, _flags_origem)
                    if not ok_f:
                        _log().warning(f"duplicar_usuario: falha ao replicar flags {chave} "
                                       f"para {novo_nome} | {msg_f}")
        _audit(ator, "duplicar_usuario", novo_nome,
               f"origem={usuario_origem} | perfil={perfil_origem}")
        _log().info(f"usuário duplicado: {novo_nome} a partir de {usuario_origem} por {ator}")
        return True, "Usuário duplicado com as permissões da origem"
    except Exception as e:
        _log().exception(f"duplicar_usuario: falha ao duplicar {novo_nome} a partir de {usuario_origem} | {e}")
        return False, "Erro inesperado ao duplicar usuário"

# ================= PERFIS POR MÓDULO =================

def definir_acesso(ator, user_nome, modulo_chave, papel):
    """Grants a per-module role ('comum'|'administrador'). None removes it.

    Atribui papel do usuário num módulo ('comum'|'administrador'). None
    remove (delega a `remover_acesso`). Upsert idempotente com auditoria
    `definir_acesso`."""
    if papel is None:
        return remover_acesso(ator, user_nome, modulo_chave)
    if papel not in PAPEIS_MODULO:
        return False, f"Papel inválido: {papel}"
    conn = _conexao_segura()
    if conn is None:
        return False, "Falha ao conectar no banco de usuários"
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tb_acesso_usuario (user_nome, modulo_chave, papel, liberado_por, data_liberacao)
               VALUES (?, ?, ?, ?, datetime('now','localtime'))
               ON CONFLICT(user_nome, modulo_chave) DO UPDATE SET
                   papel=excluded.papel, liberado_por=excluded.liberado_por,
                   data_liberacao=excluded.data_liberacao""",
            (user_nome, modulo_chave, papel, ator),
        )
        _commit_com_retry(conn, contexto=f"definir_acesso:{user_nome}@{modulo_chave}")
        _audit(ator, "definir_acesso", user_nome, f"{modulo_chave}={papel}")
        _log().info(f"acesso definido: {user_nome} {modulo_chave}={papel} por {ator}")
        return True, f"{modulo_chave}: {papel}"
    except Exception as e:
        _rollback_seguro(conn, contexto=f"definir_acesso:{user_nome}")
        _log().exception(f"definir_acesso: falha ao definir acesso {user_nome}@{modulo_chave} | {e}")
        return False, "Erro inesperado ao definir acesso"
    finally:
        conn.close()


def remover_acesso(ator, user_nome, modulo_chave):
    """Removes the user's grant on a module and audits it. Returns (ok, msg)."""
    conn = _conexao_segura()
    if conn is None:
        return False, "Falha ao conectar no banco de usuários"
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tb_acesso_usuario WHERE user_nome=? AND modulo_chave=?",
                    (user_nome, modulo_chave))
        _commit_com_retry(conn, contexto=f"remover_acesso:{user_nome}@{modulo_chave}")
        _audit(ator, "remover_acesso", user_nome, f"módulo {modulo_chave}")
        _log().info(f"acesso removido: {user_nome} módulo {modulo_chave} por {ator}")
        return True, f"Acesso a '{modulo_chave}' removido"
    except Exception as e:
        _rollback_seguro(conn, contexto=f"remover_acesso:{user_nome}")
        _log().exception(f"remover_acesso: falha ao remover acesso {user_nome}@{modulo_chave} | {e}")
        return False, "Erro inesperado ao remover acesso"
    finally:
        conn.close()


def obter_papel_no_modulo(user_nome, modulo_chave):
    """Effective role in a module ('administrador'|'comum'|None).

    Retorna 'administrador', 'comum' ou None. O `administrador_geral`
    ativo sempre resolve como 'administrador' em qualquer módulo."""
    conn = _conexao_segura()
    if conn is None:
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_perfil FROM tb_usuarios WHERE user_nome=? AND user_ativo=1",
                    (user_nome,))
        row = cur.fetchone()
        if row and row[0] == "administrador_geral":
            return "administrador"
        cur.execute("SELECT papel FROM tb_acesso_usuario WHERE user_nome=? AND modulo_chave=?",
                    (user_nome, modulo_chave))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        _log().exception(f"obter_papel_no_modulo: falha para {user_nome}@{modulo_chave} | {e}")
        return None
    finally:
        conn.close()


def validar_acesso_modulo(user_nome, modulo_chave):
    """True if the user may access the module (used by the core page guard).

    RF-35: o módulo de Auditoria é exclusivo do `administrador_geral`.
    Demais módulos: basta existir vínculo em `tb_acesso_usuario` (o papel
    `administrador` em qualquer módulo é concedido ao admin geral)."""
    try:
        # RF-35: o módulo de Auditoria é exclusivo do administrador geral do sistema.
        if modulo_chave == "auditoria":
            from mod_tisosdocfly import autenticacao
            return autenticacao.perfil_global_de(user_nome) == "administrador_geral"
        return obter_papel_no_modulo(user_nome, modulo_chave) is not None
    except Exception as e:
        _log().exception(f"validar_acesso_modulo: falha para {user_nome}@{modulo_chave} | {e}")
        return False


# ================= FLAGS FINAS DE PERMISSÃO (JSON) =================

FLAGS_PERMISSAO = {
    "blog.publicar": "Publicar e editar postagens do blog",
    "blog.comentar": "Comentar nas postagens do blog",
    "blog.configurar": "Configurar exibição e aparência do blog",
}


def _flags_validas(flags):
    """Validates a flags dict against the allowlist catalog.

    Valida o dicionário de flags contra o catálogo (allowlist
    `FLAGS_PERMISSAO`): chaves conhecidas e valores booleanos."""
    if not isinstance(flags, dict):
        return False, "flags deve ser um dicionário {flag: bool}"
    desconhecidas = [k for k in flags if k not in FLAGS_PERMISSAO]
    if desconhecidas:
        return False, f"flags desconhecidas: {', '.join(desconhecidas)}"
    if any(not isinstance(v, bool) for v in flags.values()):
        return False, "valores das flags devem ser booleanos"
    return True, ""


def obter_flags(user_nome, modulo_chave):
    """Reads the fine-grained flags of a grant (dict, fail-soft {}).

    Lê as flags finas do vínculo (dict). Fail-soft: ausente/erro/JSON
    inválido devolve {}."""
    try:
        conn = get_connection()
    except Exception as e:
        _log().exception(f"obter_flags: falha ao conectar para {user_nome}@{modulo_chave} | {e}")
        return {}
    try:
        cur = conn.cursor()
        cur.execute("SELECT flags FROM tb_acesso_usuario WHERE user_nome=? AND modulo_chave=?",
                    (user_nome, modulo_chave))
        row = cur.fetchone()
        if not row or not row[0]:
            return {}
        try:
            import json
            dados = json.loads(row[0])
        except (ValueError, TypeError):
            return {}
        return dados if isinstance(dados, dict) else {}
    except Exception as e:
        _log().exception(f"obter_flags: falha ao ler flags de {user_nome}@{modulo_chave} | {e}")
        return {}
    finally:
        conn.close()


def definir_flags(ator, user_nome, modulo_chave, flags):
    """Replaces the fine-grained flags of a grant (catalog-validated).

    Substitui as flags finas do vínculo (validadas pelo catálogo
    `FLAGS_PERMISSAO`). Exige vínculo pré-existente em
    `tb_acesso_usuario`."""
    ok, msg = _flags_validas(flags)
    if not ok:
        return False, msg
    conn = _conexao_segura()
    if conn is None:
        return False, "Falha ao conectar no banco de usuários"
    try:
        import json
        cur = conn.cursor()
        cur.execute("SELECT id FROM tb_acesso_usuario WHERE user_nome=? AND modulo_chave=?",
                    (user_nome, modulo_chave))
        if not cur.fetchone():
            return False, f"sem vínculo {user_nome}@{modulo_chave} (libere o acesso primeiro)"
        cur.execute("UPDATE tb_acesso_usuario SET flags=? WHERE user_nome=? AND modulo_chave=?",
                    (json.dumps(flags, sort_keys=True), user_nome, modulo_chave))
        _commit_com_retry(conn, contexto=f"definir_flags:{user_nome}@{modulo_chave}")
        _audit(ator, "definir_flags", user_nome, f"{modulo_chave}={sorted(flags)}")
        _log().info(f"flags definidas: {user_nome} {modulo_chave}={sorted(flags)} por {ator}")
        return True, f"{modulo_chave}: {len(flags)} flag(s)"
    except Exception as e:
        _rollback_seguro(conn, contexto=f"definir_flags:{user_nome}")
        _log().exception(f"definir_flags: falha para {user_nome}@{modulo_chave} | {e}")
        return False, "Erro inesperado ao definir flags"
    finally:
        conn.close()


def tem_flag(user_nome, modulo_chave, flag):
    """True when the user holds a fine-grained flag (admins pass by role).

    True se o usuário tem a flag (admin global/modular passam pelo papel
    'administrador' sem precisar da flag explícita)."""
    try:
        if obter_papel_no_modulo(user_nome, modulo_chave) == "administrador":
            return True
        return bool(obter_flags(user_nome, modulo_chave).get(flag))
    except Exception:
        return False


# ================= SESSÕES ATIVAS =================

def _fechar_sessoes_central(user_nome):
    """Closes ALL open central sessions of the user (block/delete/password reset)."""
    try:
        c = _central(); cc = c.cursor()
        cc.execute("UPDATE tb_sessoes SET logout_timestamp=datetime('now','localtime') WHERE usuario=? AND logout_timestamp IS NULL",
                   (user_nome,))
        c.commit(); c.close()
    except Exception as e:
        _log().warning(f"_fechar_sessoes_central: falha ao encerrar sessões de {user_nome} | {e}")


def registrar_tentativa_login(user_nome):
    """Conta um login errado e devolve o total **dentro da janela**.

    A janela é de 15 min (`mod_tisosdocfly.politica_senha.JANELA_TENTATIVAS_SEG`):
    passando dela, a contagem zera sozinha. É o que impede a conta de ficar
    lenta para sempre depois de um período ruim de digitação — e o que impede
    o atacante de só esperar a contagem cair, porque 15 min é pouco tempo para
    girar um dicionário grande.

    Login de usuário que **não existe** também conta, e é de propósito: a
    mensagem de resposta é a mesma nos dois casos ("Usuário ou senha
    inválidos"), então sem contar aqui o atacante testaria logins inexistentes
    de graça — e é assim que se descobre a lista de quem tem conta. A
    `tb_login_tentativas` tem chave estrangeira para `tb_usuarios`, então
    inexistente não tem onde ser gravado: o atraso sai de uma contagem em
    memória (`_tentativas_fantasma`), e só para esta requisição.

    **O DEFEXTO QUE A CONTAGEM FANTASMA TINHA (corrigido em 03/10/2026).**
    A contagem em memória era escrita como `_tentativas_fantasma[login] = 1` e
    devolvia `1` — sempre, em toda tentativa. `tentativas_login()` nem olhava
    o dicionário. A soma saía 1, 1, 1, 1 em vez de 1, 2, 3, 4, e o leitor
    devolvia 0. Ou seja: **login inexistente nunca pagava o atraso progressivo,
    e login existente pagava** — que é exatamente o oráculo que a contagem
    fantasma existe para fechar. O atacante batia três vezes em um login
    inventado e três vezes em um login real, comparava as respostas e levava
    a lista de quem tem conta. Quem trava isso, em teste, é
    `tests/test_login_atraso_progressivo.py`.

    Devolve 0 em qualquer falha: perder a contagem só faz o atacante ganhar
    tempo, e um erro aqui jamais pode barrar o servidor legítimo.
    """
    try:
        # Foreign key: usuário inexistente não tem linha em tb_usuarios, e
        # `tb_login_tentativas.user_nome` referencia essa tabela. Gravar
        # falharia com "FOREIGN KEY constraint failed" a cada tentativa — e
        # encher o log de warning a cada erro de digitação.
        if not _usuario_existe_para_tentativa(user_nome):
            # Mesmo efeito, sem tocar no banco: um erro contra um login
            # inexistente não pode custar mais que um erro contra um existente.
            return _fantasma_registrar(user_nome)
        conn = get_connection()
        if conn is None:
            return 0
        cur = conn.cursor()
        cur.execute("SELECT falhas, ultima_falha FROM tb_login_tentativas "
                    "WHERE user_nome=?", (user_nome,))
        linha = cur.fetchone()
        from mod_tisosdocfly import politica_senha as ps
        falhas = _contar_na_janela(linha, ps.JANELA_TENTATIVAS_SEG) if linha else 0
        falhas += 1
        cur.execute("INSERT INTO tb_login_tentativas "
                    "(user_nome, falhas, ultima_falha) VALUES (?, ?, ?) "
                    "ON CONFLICT (user_nome) DO UPDATE SET "
                    "falhas=excluded.falhas, ultima_falha=excluded.ultima_falha",
                    (user_nome, falhas, datetime.now().isoformat()))
        _commit_com_retry(conn, contexto=f"tentativa:{user_nome}")
        conn.close()
        _tentativas_fantasma.pop(str(user_nome), None)
        return falhas
    except Exception as e:
        _log().warning(f"registrar_tentativa_login: falha ao contar tentativa "
                       f"de {user_nome} | {e}")
        return 0


# Contagem em memória para login de usuário INEXISTENTE. Precisa existir
# porque a tabela tem chave estrangeira para `tb_usuarios`, e o usuário que não
# existe é justamente o que o atacante testa de graça. É deliberadamente
# descartável: se o processo reiniciar, a contagem volta a zero e o atacante
# ganha um pouco de tempo — o que não é perda de segurança, porque a resposta
# do sistema é idêntica com e sem ela.
#
# O valor é `(falhas, ultima_falha_iso)`, o mesmo par que a linha do banco
# tem: assim `_contar_na_janela` é a MESMA regra para os dois caminhos, e
# "login que não existe custa como login que existe" vale também para a
# janela de 15 min, não só para a soma.
_tentativas_fantasma: dict[str, tuple] = {}

# Teto de entradas em memória. Sem ele, o próprio mecanismo de defesa vira o
# vetor: um atacante que varia o login a cada tentativa (o que faria de
# qualquer forma, para não ser limitado a um login por vez) guardaria uma
# entrada para cada nome testado, para sempre — enquanto o atraso, que é o
# que ele de fato quer evitar, já está no teto de 30 s. O corte é
# comportamento, não só memória: passados 2.048 logins diferentes, a
# contagem dos mais antigos some, e o atacante que passou por mais de 2.048
# nomes já pagou 2.048 atrasos crescentes para não descobrir nada.
FANTASMA_LIMITE = 2048

# Marca d'água da poda: a varredura só roda acima deste tamanho. Abaixo dele
# quase nada há para descartar, e a poda existe para o caso de muitas
# entradas, não para o uso comum. Ver `_fantasma_podar`.
FANTASMA_PODAR_ACIMA = 512


def _contar_na_janela(registro, janela_seg):
    """`(falhas, ultima_iso)` -> total dentro da janela; 0 fora dela.

    Mesma regra para linha de banco e entrada em memória, para que a janela
    que vale para quem tem conta valha para quem não tem. Data ilegível conta
    como 0 (sem contagem) em vez de estourar: perder a contagem só faz o
    atacante ganhar tempo, e um erro aqui jamais pode barrar o servidor.
    """
    try:
        if not registro:
            return 0
        falhas, ultima = registro[0], registro[1]
        quando = datetime.fromisoformat(str(ultima))
        if datetime.now() - quando > timedelta(seconds=janela_seg):
            return 0
        return int(falhas or 0)
    except Exception as e:
        _log().warning(f"_contar_na_janela: registro ilegível, contando 0 | {e}")
        return 0


def _fantasma_podar(agora=None):
    """Joga fora o que passou da janela e corta no teto.

    **Só roda acima da marca d'água** (`FANTASMA_LIMITE // 4`), e não a cada
    registro. Varrer o dicionário inteiro em cada login é O(n) no caminho
    quente, e o dicionário pode ter 2.048 entradas: uma varredura por login
    são ~2 milhões de operações a cada tentativa de login só para descobrir
    que quase nada expirou. Podar por marcas de água é a forma usual de
    manter esse custo constante: no uso normal (poucos logins por processo) a
    varredura quase nunca roda, e quando roda limpa o que já podia ir.

    O efeito para quem espera é o mesmo — o teto continua valendo de
    imediato, porque o corte por `len(...) > FANTASMA_LIMITE` é verificado
    sempre, e a expiração por janela só adia em minutos, não em tentativas.
    """
    try:
        if len(_tentativas_fantasma) < FANTASMA_PODAR_ACIMA:
            return
        from mod_tisosdocfly import politica_senha as ps
        momento = agora or datetime.now()
        janela = timedelta(seconds=ps.JANELA_TENTATIVAS_SEG)
        for chave in [k for k, v in _tentativas_fantasma.items()
                      if not _data_dentro_da_janela(v, momento, janela)]:
            _tentativas_fantasma.pop(chave, None)
        if len(_tentativas_fantasma) > FANTASMA_LIMITE:
            # Mais velho primeiro: as entradas que sobrevivem ao corte são as
            # que ainda estão dentro da janela, e o corte é do começo porque
            # é o começo que o atacante já deixou de usar.
            for chave, _v in sorted(
                    _tentativas_fantasma.items(),
                    key=lambda par: str(par[1][1]))[:len(_tentativas_fantasma)
                                                        - FANTASMA_LIMITE]:
                _tentativas_fantasma.pop(chave, None)
    except Exception as e:
        _log().warning(f"_fantasma_podar: não foi possível podar as contagens "
                       f"fantasma | {e}")


def _data_dentro_da_janela(registro, agora, janela):
    """`(falhas, ultima_iso)` está dentro da janela? Data ruim conta como fora."""
    try:
        return (agora - datetime.fromisoformat(str(registro[1]))) <= janela
    except Exception:
        return False


def _fantasma_registrar(user_nome):
    """Soma uma falha de login INEXISTENTE e devolve o total na janela.

    Devolve ao menos 1: um erro contra login que não existe custa pelo menos
    o mesmo que o primeiro erro contra login que existe. Se nem isso
    conseguir, devolve 1 mesmo assim — a resposta do sistema é a mesma nos
    dois casos, e é por isso que ela não pode depender de a conta existir.
    """
    try:
        from mod_tisosdocfly import politica_senha as ps
        chave = str(user_nome)
        agora = datetime.now()
        falhas = _contar_na_janela(_tentativas_fantasma.get(chave),
                                   ps.JANELA_TENTATIVAS_SEG) + 1
        _tentativas_fantasma[chave] = (falhas, agora.isoformat())
        _fantasma_podar(agora)
        return falhas
    except Exception as e:
        _log().warning(f"_fantasma_registrar: falha ao contar tentativa de "
                       f"{user_nome}; devolvendo 1 | {e}")
        return 1


def _usuario_existe_para_tentativa(user_nome):
    """O login existe em `tb_usuarios`? Falha de banco conta como 'não'."""
    try:
        conn = get_connection()
        if conn is None:
            return False
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tb_usuarios WHERE user_nome=? LIMIT 1",
                    (user_nome,))
        achou = cur.fetchone() is not None
        conn.close()
        return achou
    except Exception as e:
        _log().warning(f"_usuario_existe_para_tentativa: falha ao checar "
                       f"{user_nome}; tratando como inexistente | {e}")
        return False


def zerar_tentativas_login(user_nome):
    """Login certo: zera a contagem. Sem isso a penalidade vazaria para a sessão
    seguinte de quem entrou certo."""
    try:
        conn = get_connection()
        if conn is None:
            return False
        cur = conn.cursor()
        cur.execute("DELETE FROM tb_login_tentativas WHERE user_nome=?",
                    (user_nome,))
        _commit_com_retry(conn, contexto=f"zerar_tentativas:{user_nome}")
        conn.close()
        _tentativas_fantasma.pop(str(user_nome), None)
        return True
    except Exception as e:
        _log().warning(f"zerar_tentativas_login: falha ao zerar contagem de "
                       f"{user_nome} | {e}")
        return False


def tentativas_login(user_nome):
    """Falhas dentro da janela agora. 0 fora dela."""
    try:
        from mod_tisosdocfly import politica_senha as ps
        chave = str(user_nome)
        # Contagem em memória PRIMEIRO, e sem consultar o banco. Se há entrada
        # aqui, o login não existe (é o que `registrar_tentativa_login`
        # garantiu ao criar a entrada) — e o banco, com a chave estrangeira,
        # não teria linha nenhuma para ele. Sem este desvio, o atraso
        # progressivo valia só para quem tem conta, e a diferença entre "a
        # conta existe" e "a conta não existe" ficava visível na resposta.
        registro = _tentativas_fantasma.get(chave)
        if registro:
            return _contar_na_janela(registro, ps.JANELA_TENTATIVAS_SEG)
        conn = get_connection()
        if conn is None:
            return 0
        cur = conn.cursor()
        cur.execute("SELECT falhas, ultima_falha FROM tb_login_tentativas "
                    "WHERE user_nome=?", (user_nome,))
        linha = cur.fetchone()
        conn.close()
        return _contar_na_janela(linha, ps.JANELA_TENTATIVAS_SEG)
    except Exception as e:
        _log().warning(f"tentativas_login: falha ao ler contagem de "
                       f"{user_nome} | {e}")
        return 0


def zerar_tentativas_todos():
    """Zera as contagens de todo mundo (admin, no painel de usuários)."""
    try:
        conn = get_connection()
        if conn is None:
            return 0
        cur = conn.cursor()
        cur.execute("DELETE FROM tb_login_tentativas")
        total = cur.rowcount or 0
        _commit_com_retry(conn, contexto="zerar_tentativas: todos")
        conn.close()
        _tentativas_fantasma.clear()
        return total
    except Exception as e:
        _log().warning(f"zerar_tentativas_todos: falha ao zerar contagens | {e}")
        return 0


def listar_sessoes_ativas(usuario=None):
    """Open sessions (no logout) with IP/device/MAC traceability.

    Sessões abertas (sem logout), agora com rastreabilidade
    IP/dispositivo/MAC (colunas do `tb_sessoes` central)."""
    try:
        c = _central()
    except Exception as e:
        _log().exception(f"listar_sessoes_ativas: falha ao abrir conexão central | {e}")
        return []
    try:
        cur = c.cursor()
        sql = """SELECT id, usuario, modulo, login_timestamp, cookie_hash,
                        COALESCE(ip,'—'), COALESCE(dispositivo,'—'), COALESCE(mac,'—')
                 FROM tb_sessoes WHERE logout_timestamp IS NULL"""
        params = []
        if usuario:
            sql += " AND usuario=?"
            params.append(usuario)
        sql += " ORDER BY login_timestamp DESC"
        cur.execute(sql, params)
        return cur.fetchall()
    except Exception as e:
        _log().exception(f"listar_sessoes_ativas: falha ao listar sessões | {e}")
        return []
    finally:
        c.close()


def contar_sessoes_ativas(usuario):
    """Counts the user's open sessions (logout_timestamp IS NULL)."""
    try:
        c = _central()
    except Exception as e:
        _log().exception(f"contar_sessoes_ativas: falha ao abrir conexão central | {e}")
        return 0
    try:
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM tb_sessoes WHERE usuario=? AND logout_timestamp IS NULL",
                    (usuario,))
        return cur.fetchone()[0]
    except Exception as e:
        _log().exception(f"contar_sessoes_ativas: falha para {usuario} | {e}")
        return 0
    finally:
        c.close()


def sessoes_ativas_por_usuario():
    """{usuario: qtd_ativas} — uma única consulta para a tabela inteira."""
    try:
        c = _central()
    except Exception as e:
        _log().exception(f"sessoes_ativas_por_usuario: falha ao abrir conexão central | {e}")
        return {}
    try:
        cur = c.cursor()
        cur.execute("""SELECT usuario, COUNT(*) FROM tb_sessoes
                       WHERE logout_timestamp IS NULL GROUP BY usuario""")
        return dict(cur.fetchall())
    except Exception as e:
        _log().exception(f"sessoes_ativas_por_usuario: falha ao agrupar sessões | {e}")
        return {}
    finally:
        c.close()


def listar_historico_sessoes(usuario, limite=10):
    """Last CLOSED sessions of a user (LGPD traceability).

    Últimas sessões ENCERRADAS do usuário (rastreabilidade LGPD: entrada,
    saída, duração calculada na tela, IP/dispositivo/MAC)."""
    try:
        c = _central()
    except Exception as e:
        _log().exception(f"listar_historico_sessoes: falha ao abrir conexão central | {e}")
        return []
    try:
        cur = c.cursor()
        cur.execute(
            """SELECT id, modulo, login_timestamp, logout_timestamp,
                      COALESCE(ip,'—'), COALESCE(dispositivo,'—'), COALESCE(mac,'—')
               FROM tb_sessoes
               WHERE usuario=? AND logout_timestamp IS NOT NULL
               ORDER BY id DESC LIMIT ?""",
            (usuario, int(limite)),
        )
        return cur.fetchall()
    except Exception as e:
        _log().exception(f"listar_historico_sessoes: falha para {usuario} | {e}")
        return []
    finally:
        c.close()


def encerrar_sessao(ator, sessao_id):
    """Closes ONE open session by id and audits it. Returns (ok, msg)."""
    try:
        c = _central()
    except Exception as e:
        _log().exception(f"encerrar_sessao: falha ao abrir conexão central | {e}")
        return False, "Falha ao conectar no banco central"
    try:
        cur = c.cursor()
        cur.execute("SELECT usuario FROM tb_sessoes WHERE id=? AND logout_timestamp IS NULL", (sessao_id,))
        row = cur.fetchone()
        if not row:
            return False, "Sessão já encerrada"
        cur.execute("UPDATE tb_sessoes SET logout_timestamp=datetime('now','localtime') WHERE id=?", (sessao_id,))
        c.commit()
        _audit(ator, "encerrar_sessao", row[0], f"sessão #{sessao_id}")
        _log().info(f"sessão encerrada: #{sessao_id} de {row[0]} por {ator}")
        return True, "Sessão encerrada"
    except Exception as e:
        _log().exception(f"encerrar_sessao: falha ao encerrar sessão #{sessao_id} | {e}")
        return False, "Erro inesperado ao encerrar sessão"
    finally:
        c.close()


def encerrar_todas_sessoes(ator, user_nome):
    """Closes ALL open sessions of the user and audits the bulk action."""
    try:
        _fechar_sessoes_central(user_nome)
        _audit(ator, "encerrar_todas_sessoes", user_nome)
        return True, f"Sessões de {user_nome} encerradas"
    except Exception as e:
        _log().exception(f"encerrar_todas_sessoes: falha para {user_nome} | {e}")
        return False, "Erro inesperado ao encerrar sessões"


# ================= VÍNCULOS ÓRFÃOS =================


def classificar_vinculos(chaves_ativas, chaves_registradas):
    """Classifica os vínculos de `tb_acesso_usuario` em dois grupos.

    **Por que isto existe (03/10/2026).** A função anterior tratava
    "módulo não está ATIVO" como "módulo não EXISTE", e as duas coisas não são
    a mesma. A entrega sobe com 11 dos 13 módulos desligados por padrão
    (decisão de 02/10/2026), então *todo* vínculo para eles era contado como
    órfão. A tela de Configurações desenhava essa lista inteira dentro do
    event-loop, o que travava a tela e derrubava o WebSocket ("sistema
    desconectado") a cada abertura de `/configuracoes`. Pior: rotulava tudo
    como "vínculo órfão" e oferecia **Excluir permissão órfã** — seguir essa
    sugestão apagaria vínculos que o sistema criou de propósito.

    A distinção que importa:
    - **inativo**: o módulo está REGISTRADO e apenas desligado. Não é órfão.
      Desaparece sozinho quando o módulo é ligado; é o estado esperado, não
      um defeito.
    - **orfao**: o módulo não está registrado de verdade — foi removido ou
      nunca existiu. Só este grupo é problema e só este admite exclusão.

    Args:
        chaves_ativas: chaves com `ativo=1` em `tb_modulos`.
        chaves_registradas: TODAS as chaves de `tb_modulos` (ligadas ou não).

    Returns:
        dict com `inativos`, `orfaos` (listas de `(user_nome, modulo_chave,
        papel)`) e `contagem_por_modulo`.
    """
    vazio = {"inativos": [], "orfaos": [], "contagem_por_modulo": {}}
    conn = _conexao_segura()
    if conn is None:
        return vazio
    try:
        registro = set(chaves_registradas or [])
        ativos = set(chaves_ativas or [])
        cur = conn.cursor()
        cur.execute("SELECT user_nome, modulo_chave, papel FROM tb_acesso_usuario")
        inativos, orfaos, contagem = [], [], {}
        for u, m, p in cur.fetchall():
            if m in ativos:
                continue
            contagem[m] = contagem.get(m, 0) + 1
            # Desligado não é órfão: o módulo existe, só não está ligado.
            (inativos if m in registro else orfaos).append((u, m, p))
        return {"inativos": inativos, "orfaos": orfaos, "contagem_por_modulo": contagem}
    except Exception as e:
        _log().exception(f"classificar_vinculos: falha ao classificar vínculos | {e}")
        return vazio
    finally:
        if conn is not None:
            conn.close()


def listar_vinculos_orfaos(chaves_registradas):
    """Somente os vínculos para módulos que NÃO estão registrados (órfãos reais).

    Compatibilidade: a assinatura mudou de sentido. Antes recebia
    `chaves_ativas` e devolvia tudo que não estivesse ativo — o que
    classificava como órfão o vínculo para módulo desligado. Agora recebe as
    chaves **registradas** (ligadas ou não) e devolve só o que realmente não
    existe mais no registro. Use `classificar_vinculos` quando precisar dos
    dois grupos e dos contadores.
    """
    return classificar_vinculos([], chaves_registradas)["orfaos"]


# ================= FICHA DETALHADA (CPF parcial, 09/10/2026) =================

# Logins que a regra de CPF nunca toca: sementes e conta de fábrica. Fundir
# ou dividir um desses com contrato da folha seria apagar identidade de
# teste/administração por causa de coincidência de dado público.
LOGINS_INTOCATAVEIS_CPF = ("master", "qacomum", "qamaster")

CAMPOS_DETALHE = ("ficha", "matricula", "nome", "cpf_parcial", "nascimento",
                  "unidade", "lotacao", "cargo", "funcao", "vinculo",
                  "situacao", "regime", "tipo", "competencia", "admissao",
                  "exoneracao", "termino_contrato", "carga_horaria",
                  "carga_horaria_mensal", "salario_base", "proventos",
                  "descontos", "liquido", "grupo_calculo", "n_itens")


def _login_intocavel(login):
    """True para sementes/conta de fábrica (nunca fundir/dividir)."""
    try:
        return (login or "").strip() in LOGINS_INTOCATAVEIS_CPF
    except Exception:
        return True


def _cpf_valido(cpf):
    """CPF parcial utilizável na regra (não vazio, com ao menos um dígito)."""
    try:
        texto = str(cpf or "").strip()
        return bool(texto) and any(c.isdigit() for c in texto)
    except Exception:
        return False


def ler_arquivo_detalhe(caminho):
    """Lê o arquivo gerado pelo `coleta_kbp.py` (JSON ou CSV).

    JSON: usa `fichas` (com `itens` aninhados). CSV: `DictReader` com
    `;`, e a coluna `verbas` volta a lista via `json.loads`. Devolve
    `(fichas, competencia, formato)`, onde cada ficha tem as chaves de
    `CAMPOS_DETALHE` + `itens` (lista). Falha devolve ([], "", "") com
    o motivo no log — nunca levanta (AGENTS §3.2).
    """
    import json
    try:
        if not caminho or not os.path.exists(caminho):
            return [], "", ""
        if caminho.lower().endswith(".json"):
            try:
                with open(caminho, encoding="utf-8") as f:
                    bruto = json.load(f)
            except Exception as e:
                _log().exception(f"ler_arquivo_detalhe: JSON ilegível | {e}")
                return [], "", ""
            fichas = []
            for reg in (bruto.get("fichas") or []):
                try:
                    if not isinstance(reg, dict) or not reg.get("ficha"):
                        continue
                    ficha = {c: str(reg.get(c) or "").strip()
                             for c in CAMPOS_DETALHE if c != "n_itens"}
                    try:
                        ficha["n_itens"] = int(reg.get("n_itens") or 0)
                    except (TypeError, ValueError):
                        ficha["n_itens"] = 0
                    itens = reg.get("itens") or []
                    ficha["itens"] = [i for i in itens
                                      if isinstance(i, dict)]
                    fichas.append(ficha)
                except Exception:
                    continue
            return fichas, str(bruto.get("competencia") or ""), "json"
        # CSV: o que o `coleta_kbp.py` grava (uma linha por ficha).
        import csv
        fichas = []
        comp = ""
        try:
            with open(caminho, encoding="utf-8-sig", newline="") as f:
                for linha in csv.DictReader(f, delimiter=";"):
                    try:
                        if not (linha.get("ficha") or "").strip():
                            continue
                        ficha = {
                            c: str(linha.get(c) or "").strip()
                            for c in CAMPOS_DETALHE if c != "n_itens"}
                        try:
                            ficha["n_itens"] = int(
                                linha.get("n_itens") or 0)
                        except (TypeError, ValueError):
                            ficha["n_itens"] = 0
                        try:
                            itens = json.loads(linha.get("verbas") or "[]")
                            ficha["itens"] = [i for i in itens
                                              if isinstance(i, dict)]
                        except Exception:
                            ficha["itens"] = []
                        fichas.append(ficha)
                        comp = comp or str(
                            linha.get("competencia") or "").strip()
                    except Exception:
                        continue
        except Exception as e:
            _log().exception(f"ler_arquivo_detalhe: CSV ilegível | {e}")
            return [], "", ""
        return fichas, comp, "csv"
    except Exception as e:
        try:
            _log().exception(f"ler_arquivo_detalhe: falha | {e}")
        except Exception:
            pass
        return [], "", ""


def _cpf_do_login(cur, login):
    """CPF parcial espelhado no login ("" quando ausente)."""
    try:
        cur.execute("SELECT cpf_parcial FROM tb_usuarios WHERE user_nome=?",
                    (login,))
        linha = cur.fetchone()
        return str((linha[0] if linha else "") or "").strip()
    except Exception:
        return ""


def _cpfs_dos_contratos(cur, login):
    """Mapa matricula → cpf da ficha carregada, para os contratos do login."""
    try:
        cur.execute("SELECT c.matricula, d.cpf_parcial FROM tb_contratos c "
                    "LEFT JOIN tb_detalhe_ficha d ON d.matricula=c.matricula "
                    "WHERE c.user_nome=? ORDER BY c.matricula", (login,))
        return [(str(m or "").strip(), str(c or "").strip())
                for m, c in (cur.fetchall() or [])]
    except Exception:
        return []


def _recomputar_principal(cur, login):
    """Principal = contrato de menor matrícula do login (padrão da carga)."""
    try:
        cur.execute("UPDATE tb_contratos SET principal=0 WHERE user_nome=?",
                    (login,))
        cur.execute("UPDATE tb_contratos SET principal=1 WHERE user_nome=? "
                    "AND matricula=(SELECT MIN(matricula) FROM tb_contratos "
                    "WHERE user_nome=?)", (login, login))
    except Exception:
        pass


def _fundir_login(cur, velho, novo, ator):
    """Move tudo de `velho` para `novo` e apaga `velho` (mesmo CPF).

    UPDATE linha a linha em vez de DELETE em cascata: as FKs variam por
    instalação (com/sem CASCADE conforme a migração de esquema), e UPDATE
    funciona igual em todas. Conflito de UNIQUE resolve a favor de quem
    fica (`novo`): a linha duplicada do `velho` é descartada.
    """
    try:
        # Acessos: quem fica já tem o módulo → a linha do velho sai.
        cur.execute("SELECT modulo_chave FROM tb_acesso_usuario "
                    "WHERE user_nome=?", (novo,))
        tem = {r[0] for r in (cur.fetchall() or [])}
        cur.execute("SELECT modulo_chave, papel, liberado_por "
                    "FROM tb_acesso_usuario WHERE user_nome=?", (velho,))
        for mod, papel, por in (cur.fetchall() or []):
            try:
                if mod in tem:
                    cur.execute("DELETE FROM tb_acesso_usuario "
                                "WHERE user_nome=? AND modulo_chave=?",
                                (velho, mod))
                else:
                    cur.execute("UPDATE tb_acesso_usuario SET user_nome=? "
                                "WHERE user_nome=? AND modulo_chave=?",
                                (novo, velho, mod))
            except Exception:
                continue
        # Tentativas: PK é o login — fica a de quem recebe.
        cur.execute("SELECT COUNT(*) FROM tb_login_tentativas "
                    "WHERE user_nome=?", (novo,))
        if (cur.fetchone()[0] or 0):
            cur.execute("DELETE FROM tb_login_tentativas WHERE user_nome=?",
                        (velho,))
        else:
            cur.execute("UPDATE tb_login_tentativas SET user_nome=? "
                        "WHERE user_nome=?", (novo, velho))
        # O resto move direto (sem UNIQUE por login).
        for tabela in ("tb_telefone_usuario", "tb_remuneracao_historico",
                       "tb_historico_movimentos", "tb_historico_salarial",
                       "tb_foto_mensal", "tb_contratos", "tb_detalhe_ficha"):
            try:
                cur.execute(f"UPDATE {tabela} SET user_nome=? "  # nosec B608 — tabela de lista fixa acima, nunca input
                            "WHERE user_nome=?", (novo, velho))
            except Exception:
                continue
        _reindexar(cur, novo)
        cur.execute("DELETE FROM tb_usuarios WHERE user_nome=?", (velho,))
        return True
    except Exception as e:
        _log().exception(f"_fundir_login {velho}->{novo}: falha | {e}")
        return False


def contar_detalhes_financeiros():
    """Quantos contracheques estão capturados, de quantas pessoas, de que mês.

    É o número que responde "já entrou alguém?" durante a coleta. Antes ele
    não tinha de onde sair: o painel lia só o arquivo em disco, e um arquivo
    parcial só diz quanto o script planejou ler, não quanto entrou no banco.
    Fail-soft: tudo zero.
    """
    saida = {"fichas": 0, "pessoas": 0, "competencia": ""}
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT user_nome) "
                    "FROM tb_detalhe_ficha")
        linha = cur.fetchone()
        saida["fichas"] = int((linha[0] if linha else 0) or 0)
        saida["pessoas"] = int((linha[1] if linha else 0) or 0)
        cur.execute("SELECT MAX(competencia) FROM tb_detalhe_ficha")
        linha = cur.fetchone()
        saida["competencia"] = str((linha[0] if linha else "") or "")
        conn.close()
    except Exception as e:
        _log().exception(f"contar_detalhes_financeiros: {e}")
    return saida


def contar_usuarios_total():
    """Quantas contas existem no cadastro (exclui as excluídas por LGPD)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM tb_usuarios "
                    "WHERE COALESCE(user_deletado, 0)=0")
        total = int((cur.fetchone() or [0])[0] or 0)
        conn.close()
        return total
    except Exception as e:
        _log().exception(f"contar_usuarios_total: {e}")
        return 0


def resumo_cadastro():
    """Contagens do cadastro: perfil, situação, liberação do DTI.

    Existe para o dado aberto e devolve **somar contagens**, nunca pessoas.
    `telefone_pendente` entrou porque é o número que o DTI quer: é a fila de
    quem ainda não pode ser liberado porque não tem ramal cadastrado.
    Fail-soft: tudo zero.
    """
    saida = {"por_perfil": [], "por_situacao": [], "liberados_dti": 0,
             "bloqueados": 0, "ativos": 0, "telefone_pendente": 0}
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(user_perfil,''), COUNT(*) FROM tb_usuarios "
                    "WHERE COALESCE(user_deletado,0)=0 GROUP BY user_perfil "
                    "ORDER BY COUNT(*) DESC")
        saida["por_perfil"] = [(str(r[0] or "(não informado)"), int(r[1]))
                               for r in cur.fetchall()]
        cur.execute("SELECT CASE WHEN COALESCE(user_deletado,0)=1 THEN 'excluído' "
                    "            WHEN COALESCE(user_ativo,0)=1 THEN 'ativo' "
                    "            ELSE 'bloqueado' END, COUNT(*) "
                    "FROM tb_usuarios GROUP BY 1 ORDER BY COUNT(*) DESC")
        saida["por_situacao"] = [(str(r[0] or ""), int(r[1]))
                                 for r in cur.fetchall()]
        cur.execute("SELECT COALESCE(liberado_pelo_dti,0), "
                    "COALESCE(user_ativo,0), COALESCE(telefone_pendente,0) "
                    "FROM tb_usuarios WHERE COALESCE(user_deletado,0)=0")
        for l, a, t in cur.fetchall():
            saida["liberados_dti"] += 1 if l else 0
            saida["bloqueados"] += 0 if a else 1
            saida["ativos"] += 1 if a else 0
            saida["telefone_pendente"] += 1 if t else 0
        conn.close()
    except Exception as e:
        _log().exception(f"resumo_cadastro: {e}")
    return saida


# Rótulos de verba que somam AO SALÁRIO — comissão, horas extras, adicionais
# e benefícios. É a leitura que o controle interno chama de "cargos
# comissionados e extras", e é a que compara com o salário do contrato.
PALAVRAS_EXTRAS = ("comissao", "hora extra", "horas extras", "adicional",
                   "adic.", "complemento", "aux", "ferias", "gratific",
                   "anuenio", "especializacao", "graduacao", "aposentadoria")


def _parece_verba_extra(descricao):
    """True se a verba soma ao salário (comissão, extra, adicional, benefício)."""
    try:
        texto = _sem_acentos(str(descricao or "")).lower()
        return any(palavra in texto for palavra in PALAVRAS_EXTRAS)
    except Exception:
        return False


def resumo_contracheques(competencia=""):
    """Totais dos contracheques capturados e o demonstrativo por verba.

    O `salario_base` da FICHA é vazio nas 1.159 (medido em 09/2026 — o portal
    não publica o campo), então o total de salário vem do contrato, que a
    folha preenche. Devolve `por_verba` já ordenado por valor, que é a leitura
    de quem lê: "quanto a folha paga de auxílio alimentação" antes de "qual
    verba aparece menos".

    `acima_do_salario` aqui inclui comissão **e extras** — comissão sozinha
    nunca passa do salário nesta prefeitura, e a métrica que o controle
    interno precisa é a soma.
    """
    import json as _json
    saida = {"competencia": competencia or "", "fichas": 0, "pessoas": 0,
             "proventos_total": 0.0, "descontos_total": 0.0,
             "liquido_total": 0.0, "salario_base_total": 0.0,
             "por_verba": [], "acima_do_salario": 0, "acima_2x": 0}
    try:
        conn = get_connection()
        cur = conn.cursor()
        if not competencia:
            cur.execute("SELECT MAX(competencia) FROM tb_detalhe_ficha")
            _l = cur.fetchone()
            competencia = str((_l[0] if _l else "") or "")
            saida["competencia"] = competencia
        if not competencia:
            return saida
        cur.execute(
            "SELECT d.matricula, d.proventos, d.descontos, d.liquido, "
            "d.itens_json, c.remuneracao "
            "FROM tb_detalhe_ficha d "
            "LEFT JOIN tb_contratos c ON c.matricula = d.matricula "
            "WHERE d.competencia=?", (competencia,))
        linhas = cur.fetchall()
        saida["fichas"] = len(linhas)
        contagem, valores = {}, {}
        pessoas = set()
        for linha in linhas:
            try:
                pessoas.add(str(linha[0] or ""))
                saida["proventos_total"] += _valor_numerico(linha[1])
                saida["descontos_total"] += _valor_numerico(linha[2])
                saida["liquido_total"] += _valor_numerico(linha[3])
                base = _valor_numerico(linha[5])
                saida["salario_base_total"] += base
                try:
                    itens = _json.loads(linha[4] or "[]")
                except Exception:
                    itens = []
                extras = 0.0
                for item in (itens if isinstance(itens, list) else []):
                    try:
                        if not isinstance(item, dict):
                            continue
                        rotulo = str(item.get("descricao")
                                     or item.get("cdVerba") or "").strip()
                        valor = _valor_numerico(item.get("valor"))
                        contagem[rotulo] = contagem.get(rotulo, 0) + 1
                        valores[rotulo] = valores.get(rotulo, 0.0) + valor
                        if _parece_verba_extra(rotulo):
                            extras += valor
                    except Exception:
                        continue
                if base > 0:
                    if extras > base:
                        saida["acima_do_salario"] += 1
                    if extras > base * 2:
                        saida["acima_2x"] += 1
            except Exception:
                continue
        saida["pessoas"] = len([p for p in pessoas if p])
        saida["por_verba"] = sorted(
            ({"rotulo": rotulo,
              "ocorrencias": contagem.get(rotulo, 0),
              "total": round(valores.get(rotulo, 0.0), 2)}
             for rotulo in contagem),
            key=lambda d: -d["total"])
        conn.close()
    except Exception as e:
        _log().exception(f"resumo_contracheques({competencia}): {e}")
    return saida


def listar_detalhes_financeiros(user_nome):
    """Os detalhes financeiros capturados da pessoa, um por competência.

    É a leitura que ALIMENTA a tela: `tb_detalhe_ficha` guardava os valores
    (salário base, proventos, descontos, líquido e as verbas) e **nenhuma tela
    os mostrava** — o dado era capturado, guardado e invisível. O "Meu Perfil"
    e a ficha do usuário mostravam só o contrato (`tb_contratos`), que tem
    salário mas não tem provento nem desconto.

    Volta da competência mais recente para a mais antiga, e traz as verbas já
    desserializadas (código, descrição, referência, tipo, valor), que é onde
    estão o auxílio alimentação, o INSS e o vencimento. Fail-soft: `[]`.
    """
    import json as _json
    saida = []
    try:
        conn = get_connection()
        cur = conn.cursor()
        # Busca por TRÊS caminhos, porque o `user_nome` da ficha nem sempre
        # vem preenchido:
        #   1. pelo próprio `user_nome` gravado na ficha;
        #   2. pelo dono da matrícula, em `tb_contratos` (é o caminho normal,
        #      e o que faz a pessoa ver o contracheque dela);
        #   3. pela MATRÍCULA, porque o login É a matrícula no resto do
        #      sistema. Sem este, uma ficha capturada antes do contrato
        #      existir ficaria com `user_nome` vazio e o contracheque seria
        #      invisível para o próprio dono — dado no banco que ninguém vê.
        cur.execute(
            "SELECT d.ficha, d.matricula, d.competencia, d.salario_base, "
            "d.proventos, d.descontos, d.liquido, d.cpf_parcial, d.itens_json "
            "FROM tb_detalhe_ficha d "
            "LEFT JOIN tb_contratos c ON c.matricula = d.matricula "
            "WHERE COALESCE(NULLIF(d.user_nome,''), c.user_nome)=? "
            "   OR d.matricula=? "
            "ORDER BY d.competencia DESC", (user_nome, user_nome))
        for linha in cur.fetchall():
            try:
                try:
                    itens = _json.loads(linha[8] or "[]")
                except Exception:
                    itens = []
                saida.append({
                    "ficha": linha[0], "matricula": linha[1],
                    "competencia": linha[2] or "",
                    "salario_base": linha[3] or "", "proventos": linha[4] or "",
                    "descontos": linha[5] or "", "liquido": linha[6] or "",
                    "cpf_parcial": linha[7] or "",
                    "itens": [i for i in (itens if isinstance(itens, list) else [])
                              if isinstance(i, dict)],
                })
            except Exception:
                continue
        conn.close()
    except Exception as e:
        _log().exception(f"listar_detalhes_financeiros({user_nome}): {e}")
    return saida


def listar_fichas_por_competencia(competencia):
    """(lista_de_registros, conjunto_de_fichas) já gravadas na competência.

    Serve a DOIS consumidores, e é por isso que volta as duas coisas:

    - `coleta_kbp.py` usa o CONJUNTO para não pedir de novo ao portal uma
      ficha que já tem, e usa a LISTA para devolver ao JSON uma folha
      completa mesmo numa execução que só buscou as pendentes;
    - a conferência manual usa a LISTA para conferir o que o banco tem.

    Cada registro volta no MESMO formato que o `coleta_kbp.py` monta
    (`itens` como lista de dicts), para quem salva um e lê o outro não ter
    que converter nada. Falha-soft: `([], set())`.
    """
    import json as _json
    registros, vistas = [], set()
    try:
        if not competencia:
            return registros, vistas
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT ficha, matricula, user_nome, cpf_parcial, nascimento, "
            "salario_base, proventos, descontos, liquido, itens_json "
            "FROM tb_detalhe_ficha WHERE competencia=?", (competencia,))
        for linha in cur.fetchall():
            try:
                ficha = str(linha[0] or "")
                if not ficha:
                    continue
                try:
                    itens = _json.loads(linha[9] or "[]")
                except Exception:
                    itens = []
                # `unidade`/`cargo` NÃO são colunas de `tb_detalhe_ficha`:
                # quem guarda o vínculo é `tb_contratos`. Aqui vão vazios, e
                # quem precisar do cargo junta pelo `matricula`. Foi assim
                # que a primeira versão quebrou: `no such column: unidade`.
                registros.append({
                    "ficha": ficha, "matricula": linha[1], "user_nome": linha[2],
                    "cpf_parcial": linha[3], "nascimento": linha[4],
                    "salario_base": linha[5], "proventos": linha[6],
                    "descontos": linha[7], "liquido": linha[8],
                    "unidade": "", "cargo": "", "vinculo": "", "situacao": "",
                    "itens": itens if isinstance(itens, list) else [],
                })
                vistas.add(ficha)
            except Exception:
                continue
        conn.close()
    except Exception as e:
        _log().exception(f"listar_fichas_por_competencia({competencia}): {e}")
    return registros, vistas


def _valor_numerico(valor):
    """'4.500,00' → 4500.0. Tolera R$, espaço, ponto e vírgula."""
    try:
        texto = str(valor or "").strip().replace("R$", "").replace(" ", "")
        if not texto:
            return 0.0
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        return abs(float(texto))
    except Exception:
        return 0.0


# Verbas que o controle interno acompanha: cargo em comissão e funções que
# pagam ACIMA do salário. A lista é curta e é Configuration, não código
# solto — é o que o responsável pediu para filtrar (10/10/2026).
# O que a pessoa digita no filtro NÃO entra na comparação: aqui só há
# comparação por palavra-chave, e a decisão final é sempre humana.
PALAVRAS_COMISSAO = ("comissao", "funcao gratificada", "funcao g",
                      "cargo comissao", "diretor", "secretario", "presidente",
                      "gratificacao", "funcao de confianca")


def _sem_acentos(texto):
    """Minúsculas sem acento — para comparar descrição de verba por palavra.

    `unicodedata` em vez do `NFKD` do `carga_folha` porque aqui a comparação
    é por palavra-chave numa string do portal, e a forma é o que importa.
    """
    try:
        import unicodedata
        base = unicodedata.normalize("NFKD", str(texto or ""))
        return "".join(c for c in base if not unicodedata.combining(c)).lower()
    except Exception:
        return str(texto or "").lower()


def _parece_verba_de_comissao(descricao):
    """True se a descrição da verba parece cargo/função em comissão."""
    try:
        texto = _sem_acentos(str(descricao or "")).lower()
        return any(palavra in texto for palavra in PALAVRAS_COMISSAO)
    except Exception:
        return False


# As duas rubricas de comissão que o portal publica (medido em 10/2026):
# "CARGO EM COMISSAO" (quem ocupa cargo comissionado) e "DIF CARGO
# COMISSAO/FUNC G" (a DIFERENÇA paga a quem assume cargo em comissão ou
# Função Gratificada — em geral efetivo designado, que recebe a diferença
# entre o base e o valor do cargo). Chave normalizada sem acento, porque o
# portal varia caixa e acento entre competências.
VERBAS_COMISSAO_ALVO = ("cargo em comissao", "dif cargo comissao/func g")


def resumo_comissao_por_verba(competencia=""):
    """Quem recebe por cada rubrica de comissão, com valor (controle interno).

    EN: Per-allowance commission payees with amounts. PT-BR: para a
    competência pedida (padrão: a mais recente com detalhe), um bloco por
    rubrica de `VERBAS_COMISSAO_ALVO` — quantas pessoas e a lista nominal
    (nome de tratamento + valor da verba, do maior para o menor).

    A lista é nominal DE PROPÓSITO (dado de controle interno, como as
    diárias) e NÃO vai ao payload JS — sai pela costura, para seção
    NiceGUI. O que NÃO sai: matrícula, CPF, `user_nome`.
    Fail-soft: `{"disponivel": False, ...}` sem detalhe capturado.
    """
    import json as _json
    vazio = {"disponivel": False, "motivo": "", "competencia": "",
             "verbas": []}
    try:
        conn = get_connection()
        cur = conn.cursor()
        if not (competencia or "").strip():
            cur.execute("SELECT MAX(competencia) FROM tb_detalhe_ficha")
            linha = cur.fetchone()
            competencia = str((linha[0] if linha else "") or "")
        competencia = (competencia or "").strip()
        if not competencia:
            try:
                conn.close()
            except Exception:
                pass
            return {**vazio, "motivo": "nenhuma competência com detalhe"}
        cur.execute("SELECT user_nome, itens_json FROM tb_detalhe_ficha "
                    "WHERE competencia=?", (competencia,))
        linhas = cur.fetchall() or []
        cur.execute("SELECT user_nome, user_nome_completo FROM tb_usuarios")
        nomes = {str(r[0] or ""): (str(r[1] or "").strip() or str(r[0] or ""))
                 for r in (cur.fetchall() or [])}
        try:
            conn.close()
        except Exception:
            pass
        blocos = {alvo: [] for alvo in VERBAS_COMISSAO_ALVO}
        for user_nome, itens_json in linhas:
            try:
                itens = _json.loads(itens_json or "[]")
            except Exception:
                continue
            for item in (itens if isinstance(itens, list) else []):
                try:
                    if not isinstance(item, dict):
                        continue
                    descricao = str(item.get("descricao")
                                    or item.get("dsVerba") or "")
                    chave = _sem_acentos(descricao).lower().strip()
                    if chave not in blocos:
                        continue
                    blocos[chave].append({
                        "nome": nomes.get(str(user_nome or ""),
                                          str(user_nome or "")),
                        "valor": round(_valor_numerico(item.get("valor")), 2),
                        "verba": descricao,
                    })
                except Exception:
                    continue
        saida_verbas = []
        for alvo in VERBAS_COMISSAO_ALVO:
            try:
                gente = sorted(blocos[alvo], key=lambda p: -p["valor"])
                saida_verbas.append({
                    "verba": alvo.upper(),
                    "pessoas": len(gente),
                    "total": round(sum(p["valor"] for p in gente), 2),
                    "lista": gente,
                })
            except Exception:
                continue
        return {"disponivel": True, "motivo": "", "competencia": competencia,
                "verbas": saida_verbas}
    except Exception as e:
        try:
            _log().exception(f"resumo_comissao_por_verba: {e}")
        except Exception:
            pass
        return {**vazio, "motivo": "falha ao ler a comissão"}


def estatisticas_comissao(competencia=None):
    """Quanto a folha paga de comissão A CIMA do salário — para o controle interno.

    Responde, para a competência pedida (padrão: a mais recente com detalhe),
    quantos servidores recebem por cargo em comissão/extras MAIS DO QUE o
    próprio salário, e quantos recebem MAIS QUE O DOBRO. É o pedido do
    controle interno de 10/10/2026: onde a folha paga por função acima do
    salário, e o tamanho disso.

    A conta é sobre as VERBAS (as linhas do contracheque em
    `tb_detalhe_ficha.itens_json`), não sobre o total: o que interessa ao
    controle é quanto da remuneração vem de cargo em comissão — e isolar isso
    só é possível olhando a verba, porque `proventos` não separa.

    Devolve dicionário com `competencia`, `servidores`, `comissao_acima`,
    `comissao_acima_2x`, valores agregados e `por_pessoa` (os casos, para
    revisão humana). Falha-soft: dicionário vazio.
    """
    import json as _json
    saida = {"competencia": competencia or "", "servidores": 0,
             "comissao_acima": 0, "comissao_acima_2x": 0,
             "salario_base_total": 0.0, "comissao_total": 0.0,
             "por_pessoa": [], "erro": ""}
    try:
        conn = get_connection()
        cur = conn.cursor()
        if not competencia:
            cur.execute("SELECT MAX(competencia) FROM tb_detalhe_ficha")
            linha = cur.fetchone()
            competencia = str((linha[0] if linha else "") or "")
            saida["competencia"] = competencia
        if not competencia:
            saida["erro"] = "nenhuma competência com detalhe capturado"
            conn.close()
            return saida
        cur.execute(
            "SELECT d.matricula, d.user_nome, d.cpf_parcial, d.salario_base, "
            "d.proventos, d.itens_json, c.remuneracao "
            "FROM tb_detalhe_ficha d "
            "LEFT JOIN tb_contratos c ON c.matricula = d.matricula "
            "WHERE d.competencia=?",
            (competencia,))
        linhas = cur.fetchall()
        conn.close()
        for linha in linhas:
            try:
                # A BASE da comparação é o salário do CONTRATO, e não o
                # `salario_base` da ficha. Medido em 09/2026: as 1.159 fichas
                # têm `salario_base` VAZIO — o portal não publica esse campo —
                # e a versão anterior comparava contra zero, o que zerava a
                # estatística em silêncio e ainda pareceria "ninguém recebe
                # comissão acima do salário". `tb_contratos.remuneracao` vem
                # da folha e está preenchida nas 1.159.
                base = _valor_numerico(linha[3]) or _valor_numerico(linha[6])
                try:
                    itens = _json.loads(linha[5] or "[]")
                except Exception:
                    itens = []
                comissao = 0.0
                verbas_comissao = []
                for item in (itens if isinstance(itens, list) else []):
                    try:
                        if not isinstance(item, dict):
                            continue
                        descricao = (item.get("descricao")
                                     or item.get("dsVerba") or "")
                        if not _parece_verba_de_comissao(descricao):
                            continue
                        valor = _valor_numerico(item.get("valor"))
                        comissao += valor
                        verbas_comissao.append(
                            f"{descricao}: {item.get('valor')}")
                    except Exception:
                        continue
                saida["servidores"] += 1
                saida["salario_base_total"] += base
                saida["comissao_total"] += comissao
                # "> salário" e "> dobro" usam o salário BASE como referência:
                # é o que a folha paga pelo cargo efetivo, e é contra ele que
                # a comissão se compara.
                if base > 0 and comissao > base:
                    saida["comissao_acima"] += 1
                    if comissao > base * 2:
                        saida["comissao_acima_2x"] += 1
                    saida["por_pessoa"].append({
                        "matricula": linha[0], "user_nome": linha[1],
                        "cpf_parcial": linha[2], "salario_base": base,
                        "comissao": comissao,
                        "multiplo": round(comissao / base, 2) if base else 0,
                        "verbas": verbas_comissao,
                    })
            except Exception:
                continue
        saida["por_pessoa"].sort(key=lambda p: -p.get("multiplo", 0))
        return saida
    except Exception as e:
        _log().exception(f"estatisticas_comissao({competencia}): {e}")
        saida["erro"] = str(e)
        return saida


def carregar_detalhe_ficha(fichas, ator, competencia=""):
    """Grava as fichas do `coleta_kbp.py` e aplica a regra de CPF.

    Por ficha (idempotente): `tb_detalhe_ficha` por (ficha, competencia)
    — mesma ficha e competência reenviada não grava de novo; e espelha
    `cpf_parcial`/`data_nascimento` no login dono da matrícula.

    Regra de pessoa (só com CPF parcial válido, nunca em semente):
    - mesmo CPF em dois logins → UMA pessoa: funde no menor login e
      limpa `mesmo_nome_de` (a evidência resolveu a dúvida);
    - mesmo nome normalizado com CPFs diferentes → PESSOAS DIFERENTES:
      cada grupo de CPF ganha o próprio login (a matrícula, como no
      resto do sistema), com senha provisória e troca obrigatória, e
      o `mesmo_nome_de` sai dos contratos separados.

    Devolve resumo com contadores (gravadas, inalteradas, fundidos,
    separados, mesma_pessoa, homonimos, sem_cpf, erros). Nunca levanta.
    """
    import json
    resumo = {"fichas": 0, "gravadas": 0, "inalteradas": 0,
              "fundidos": 0, "separados": 0, "mesma_pessoa": 0,
              "homonimos": 0, "sem_cpf": 0, "erros": []}
    conn = None
    try:
        fichas = fichas or []
        resumo["fichas"] = len(fichas)
        if not fichas:
            return resumo
        conn = get_connection()
        cur = conn.cursor()
        tocados = set()
        for ficha in fichas:
            try:
                cd = str((ficha or {}).get("ficha") or "").strip()
                mat = str((ficha or {}).get("matricula") or "").strip()
                if not cd or not mat:
                    continue
                comp = str((ficha or {}).get("competencia")
                           or competencia or "").strip()
                cpf = str((ficha or {}).get("cpf_parcial") or "").strip()
                nasc = str((ficha or {}).get("nascimento") or "").strip()
                try:
                    itens = json.dumps((ficha or {}).get("itens") or [],
                                       ensure_ascii=False)
                except Exception:
                    itens = "[]"
                cur.execute("SELECT competencia FROM tb_detalhe_ficha "
                            "WHERE ficha=?", (cd,))
                linha = cur.fetchone()
                if linha and (linha[0] or "") == comp:
                    resumo["inalteradas"] += 1
                    continue
                # Dono da matrícula (contrato já carregado pela folha).
                cur.execute("SELECT user_nome FROM tb_contratos "
                            "WHERE matricula=?", (mat,))
                dono = cur.fetchone()
                login = str((dono[0] if dono else "") or "").strip()
                if linha:
                    cur.execute(
                        "UPDATE tb_detalhe_ficha SET matricula=?, user_nome=?, "
                        "cpf_parcial=?, nascimento=?, salario_base=?, "
                        "proventos=?, descontos=?, liquido=?, n_itens=?, "
                        "itens_json=?, competencia=?, "
                        "atualizado_em=CURRENT_TIMESTAMP WHERE ficha=?",
                        (mat, login, cpf, nasc,
                         str((ficha or {}).get("salario_base") or ""),
                         str((ficha or {}).get("proventos") or ""),
                         str((ficha or {}).get("descontos") or ""),
                         str((ficha or {}).get("liquido") or ""),
                         int((ficha or {}).get("n_itens") or 0), itens,
                         comp, cd))
                else:
                    cur.execute(
                        "INSERT INTO tb_detalhe_ficha (ficha, matricula, "
                        "user_nome, cpf_parcial, nascimento, salario_base, "
                        "proventos, descontos, liquido, n_itens, itens_json, "
                        "competencia) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(ficha) DO UPDATE SET matricula=excluded.matricula, "
                        "user_nome=excluded.user_nome, cpf_parcial=excluded.cpf_parcial, "
                        "nascimento=excluded.nascimento, salario_base=excluded.salario_base, "
                        "proventos=excluded.proventos, descontos=excluded.descontos, "
                        "liquido=excluded.liquido, n_itens=excluded.n_itens, "
                        "itens_json=excluded.itens_json, competencia=excluded.competencia, "
                        "atualizado_em=CURRENT_TIMESTAMP",
                        (cd, mat, login, cpf, nasc,
                         str((ficha or {}).get("salario_base") or ""),
                         str((ficha or {}).get("proventos") or ""),
                         str((ficha or {}).get("descontos") or ""),
                         str((ficha or {}).get("liquido") or ""),
                         int((ficha or {}).get("n_itens") or 0), itens,
                         comp))
                if login and _cpf_valido(cpf):
                    try:
                        cur.execute("UPDATE tb_usuarios SET cpf_parcial=?, "
                                    "data_nascimento=? WHERE user_nome=? "
                                    "AND (cpf_parcial IS NULL "
                                    "OR cpf_parcial='' OR cpf_parcial=?)",
                                    (cpf, nasc, login, cpf))
                    except Exception:
                        pass
                    tocados.add(login)
                resumo["gravadas"] += 1
            except Exception as e:
                resumo["erros"].append(f"{(ficha or {}).get('ficha', '?')}: {e}")
                continue
        _commit_com_retry(conn, contexto="carregar_detalhe:fichas")

        # ---- Regra de pessoa: mesmo CPF = um login; CPFs distintos = dois.
        try:
            cur.execute("SELECT user_nome, cpf_parcial FROM tb_usuarios "
                        "WHERE cpf_parcial IS NOT NULL AND cpf_parcial<>''")
            por_cpf = {}
            for login, cpf in (cur.fetchall() or []):
                try:
                    login = str(login or "").strip()
                    cpf = str(cpf or "").strip()
                    if login and _cpf_valido(cpf):
                        por_cpf.setdefault(cpf, set()).add(login)
                except Exception:
                    continue
            for cpf, logins in sorted(por_cpf.items()):
                try:
                    uteis = sorted(l for l in logins
                                   if not _login_intocavel(l))
                    if len(uteis) < 2:
                        continue
                    novo = uteis[0]
                    for velho in uteis[1:]:
                        try:
                            if _fundir_login(cur, velho, novo, ator):
                                resumo["fundidos"] += 1
                                _audit(ator, "detalhe_fundir_pessoa", novo,
                                       f"mesmo CPF parcial: {velho} -> {novo}")
                        except Exception:
                            continue
                    _commit_com_retry(conn,
                                      contexto=f"carregar_detalhe:fundir:{novo}")
                except Exception:
                    continue
        except Exception as e:
            _log().exception(f"carregar_detalhe: fusão por CPF | {e}")

        # ---- Nomes iguais, CPFs diferentes: separar.
        try:
            cur.execute("SELECT user_nome, user_nome_completo FROM tb_usuarios")
            por_nome = {}
            for login, nome in (cur.fetchall() or []):
                try:
                    login = str(login or "").strip()
                    if not login or _login_intocavel(login):
                        continue
                    chave = _nome_normalizado_bd(nome or login)
                    por_nome.setdefault(chave, set()).add(login)
                except Exception:
                    continue
            for _nome, logins in sorted(por_nome.items()):
                try:
                    if len(logins) < 2:
                        continue
                    cpfs = {l: _cpf_do_login(cur, l) for l in logins}
                    if not any(_cpf_valido(c) for c in cpfs.values()):
                        continue
                    # Grupos por CPF conhecido; sem CPF acompanha o principal.
                    grupos = {}
                    for login in sorted(logins):
                        cpf = cpfs.get(login) or ""
                        grupos.setdefault(cpf if _cpf_valido(cpf) else "?",
                                          []).append(login)
                    conhecidos = sorted(c for c in grupos if c != "?")
                    if len(conhecidos) < 2:
                        continue
                    # Só conta: a separação de verdade acontece no passo
                    # seguinte (contratos com CPF distinto do login). Contar
                    # aqui somaria de novo o que já foi separado em carga
                    # anterior — e "rodar duas vezes não muda nada" inclui
                    # o resumo.
                    resumo["homonimos"] += 1
                    for cpf in conhecidos[1:]:
                        for login in grupos[cpf]:
                            _audit(ator, "detalhe_homonimo", login,
                                   f"CPF parcial distinto no mesmo nome "
                                   f"({cpf})")
                except Exception:
                    continue
        except Exception as e:
            _log().exception(f"carregar_detalhe: leitura de homônimos | {e}")

        # ---- Contratos com CPF distinto do login: login próprio.
        try:
            cur.execute("SELECT user_nome FROM tb_usuarios")
            todos = [str(r[0] or "").strip() for r in (cur.fetchall() or [])]
            for login in sorted(todos):
                try:
                    if not login or _login_intocavel(login):
                        continue
                    pares = _cpfs_dos_contratos(cur, login)
                    com_cpf = [(m, c) for m, c in pares if _cpf_valido(c)]
                    if len({c for _, c in com_cpf}) < 2:
                        continue
                    base = sorted({c for _, c in com_cpf})[0]
                    for mat, cpf in com_cpf:
                        if cpf == base:
                            continue
                        # Novo login = a matrícula (padrão do sistema).
                        cur.execute("SELECT COUNT(*) FROM tb_usuarios "
                                    "WHERE user_nome=?", (mat,))
                        if not (cur.fetchone()[0] or 0):
                            cur.execute(
                                "SELECT user_nome_completo FROM tb_usuarios "
                                "WHERE user_nome=?", (login,))
                            dito = cur.fetchone()
                            nome = str((dito[0] if dito else "")
                                       or login or "").strip()
                            ok_c, _msg = criar_usuario(
                                ator, mat, "123456", perfil="comum",
                                nome_completo=nome, exigir_telefone=True)
                            if not ok_c:
                                resumo["erros"].append(
                                    f"{mat}: não separou ({_msg})")
                                continue
                        cur.execute("UPDATE tb_contratos SET user_nome=?, "
                                    "mesmo_nome_de='' WHERE matricula=?",
                                    (mat, mat))
                        cur.execute("UPDATE tb_detalhe_ficha SET user_nome=? "
                                    "WHERE matricula=?", (mat, mat))
                        cur.execute("UPDATE tb_usuarios SET cpf_parcial=? "
                                    "WHERE user_nome=?", (cpf, mat))
                        _recomputar_principal(cur, login)
                        _recomputar_principal(cur, mat)
                        _reindexar(cur, login)
                        _reindexar(cur, mat)
                        _commit_com_retry(
                            conn, contexto=f"carregar_detalhe:split:{mat}")
                        resumo["separados"] += 1
                        _audit(ator, "detalhe_separar_pessoa", mat,
                               f"CPF parcial {cpf} distinto do login {login}")
                    _commit_com_retry(
                        conn, contexto=f"carregar_detalhe:cpf:{login}")
                except Exception as e:
                    resumo["erros"].append(f"{login}: {e}")
                    continue
        except Exception as e:
            _log().exception(f"carregar_detalhe: separação por CPF | {e}")

        # ---- Contagem final para o resumo (espelho do que ficou).
        try:
            cur.execute("SELECT user_nome, cpf_parcial FROM tb_usuarios "
                        "WHERE cpf_parcial IS NOT NULL AND cpf_parcial<>''")
            vistos = {}
            for login, cpf in (cur.fetchall() or []):
                try:
                    vistos.setdefault(str(cpf).strip(), set()).add(
                        str(login).strip())
                except Exception:
                    continue
            resumo["mesma_pessoa"] = sum(
                1 for s in vistos.values() if len(s) == 1)
            resumo["homonimos"] = sum(
                1 for c, s in _grupos_nome_cpf(cur).items()
                if len(s) > 1)
        except Exception:
            pass
        _commit_com_retry(conn, contexto="carregar_detalhe:fim")
        return resumo
    except Exception as e:
        _rollback_seguro(conn, contexto="carregar_detalhe")
        try:
            _log().exception(f"carregar_detalhe_ficha: falha | {e}")
        except Exception:
            pass
        resumo["erros"].append(str(e))
        return resumo
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def _nome_normalizado_bd(texto):
    """Normaliza nome para agrupar (sem acento, caixa alta, sem duplicar)."""
    try:
        import unicodedata as _ud
        base = _ud.normalize("NFKD", str(texto or "")).encode(
            "ascii", "ignore").decode()
        return " ".join(base.upper().split())
    except Exception:
        return str(texto or "").upper().strip()


def _grupos_nome_cpf(cur):
    """Mapa nome normalizado → CPFs distintos (para o resumo)."""
    try:
        cur.execute("SELECT user_nome, user_nome_completo, cpf_parcial "
                    "FROM tb_usuarios")
        grupos = {}
        for login, nome, cpf in (cur.fetchall() or []):
            try:
                chave = _nome_normalizado_bd(nome or login)
                cpf = str(cpf or "").strip()
                if chave and _cpf_valido(cpf):
                    grupos.setdefault(chave, set()).add(cpf)
            except Exception:
                continue
        return grupos
    except Exception:
        return {}


# ================= DIÁRIAS (11/10/2026) =================

def _resolver_usuario_por_cpf(cur, cpf_parcial):
    """O `user_nome` dono do CPF parcial, ou "" quando ninguém tem."""
    try:
        cpf = str(cpf_parcial or "").strip()
        if not cpf:
            return ""
        cur.execute("SELECT user_nome FROM tb_usuarios WHERE cpf_parcial=? "
                    "LIMIT 1", (cpf,))
        linha = cur.fetchone()
        return str((linha[0] if linha else "") or "")
    except Exception:
        return ""


def gravar_diarias(linhas):
    """Grava o consolidado anual de diárias (idempotente por ano+fornecedor).

    EN: Upserts yearly per-person allowance rows. PT-BR: insere ou atualiza
    uma linha por favorecido por ano; recarregar o mesmo ano não duplica.
    O vínculo `user_nome` é resolvido pelo CPF parcial na hora da gravação.
    Devolve `{"gravadas": N}`. Nunca levanta (AGENTS §3.2).
    """
    saida = {"gravadas": 0}
    try:
        linhas = list(linhas or [])
        if not linhas:
            return saida
        conn = get_connection()
        cur = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for linha in linhas:
            try:
                ano = str((linha or {}).get("ano") or "").strip()
                cd = str((linha or {}).get("cd_fornecedor") or "").strip()
                if not ano or not cd:
                    continue
                cpf = str((linha or {}).get("cpf_parcial") or "").strip()
                dono = _resolver_usuario_por_cpf(cur, cpf)
                cur.execute(
                    "INSERT INTO tb_diarias (ano, cd_fornecedor, nome_portal, "
                    "cpf_parcial, user_nome, vl_empenhado, vl_liquidado, "
                    "vl_pago, coletado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT DO NOTHING",
                    (ano, cd, str((linha or {}).get("nome_portal") or "")[:200],
                     cpf, dono,
                     float((linha or {}).get("vl_empenhado") or 0),
                     float((linha or {}).get("vl_liquidado") or 0),
                     float((linha or {}).get("vl_pago") or 0), agora))
                if (cur.rowcount or 0):
                    saida["gravadas"] += 1
                else:
                    cur.execute(
                        "UPDATE tb_diarias SET nome_portal=?, cpf_parcial=?, "
                        "user_nome=?, vl_empenhado=?, vl_liquidado=?, "
                        "vl_pago=?, coletado_em=? "
                        "WHERE ano=? AND cd_fornecedor=?",
                        (str((linha or {}).get("nome_portal") or "")[:200],
                         cpf, dono,
                         float((linha or {}).get("vl_empenhado") or 0),
                         float((linha or {}).get("vl_liquidado") or 0),
                         float((linha or {}).get("vl_pago") or 0), agora,
                         ano, cd))
                    saida["gravadas"] += 1
            except Exception as e:
                try:
                    _log().warning(f"gravar_diarias: linha ignorada ({e})")
                except Exception:
                    pass
                continue
        _commit_com_retry(conn, contexto="gravar_diarias")
        try:
            conn.close()
        except Exception:
            pass
    except Exception as e:
        try:
            _log().exception(f"gravar_diarias: {e}")
        except Exception:
            pass
    return saida


def listar_diarias_usuario(user_nome):
    """As diárias de UMA pessoa, ano a ano (para o perfil).

    Casa por `user_nome` OU pelo CPF parcial do dono (o vínculo pode ter
    entrado no cadastro depois da coleta). Ordenado por ano. Fail-soft: [].
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT cpf_parcial FROM tb_usuarios WHERE user_nome=?",
                    ((user_nome or "").strip(),))
        linha = cur.fetchone()
        cpf = str((linha[0] if linha else "") or "").strip()
        if cpf:
            cur.execute("SELECT ano, nome_portal, cpf_parcial, vl_empenhado, "
                        "vl_liquidado, vl_pago, coletado_em FROM tb_diarias "
                        "WHERE user_nome=? OR cpf_parcial=? ORDER BY ano",
                        ((user_nome or "").strip(), cpf))
        else:
            cur.execute("SELECT ano, nome_portal, cpf_parcial, vl_empenhado, "
                        "vl_liquidado, vl_pago, coletado_em FROM tb_diarias "
                        "WHERE user_nome=? ORDER BY ano",
                        ((user_nome or "").strip(),))
        saida = [{"ano": r[0], "nome_portal": r[1], "cpf_parcial": r[2],
                  "vl_empenhado": float(r[3] or 0),
                  "vl_liquidado": float(r[4] or 0),
                  "vl_pago": float(r[5] or 0),
                  "coletado_em": r[6] or ""} for r in (cur.fetchall() or [])]
        try:
            conn.close()
        except Exception:
            pass
        return saida
    except Exception as e:
        try:
            _log().exception(f"listar_diarias_usuario({user_nome}): {e}")
        except Exception:
            pass
        return []


def resumo_diarias_anos():
    """Totais de diárias por ano: pago, pessoas, coleta mais recente.

    É o que o painel do admin mostra ("gastos 2025 e 2026"). Agregado puro:
    soma e contagem, sem nome de ninguém. Fail-soft: `{"anos": []}`.
    """
    saida = {"anos": []}
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT ano, COUNT(*), COALESCE(SUM(vl_pago), 0), "
                    "COALESCE(SUM(vl_empenhado), 0), "
                    "COALESCE(SUM(vl_liquidado), 0), MAX(coletado_em) "
                    "FROM tb_diarias GROUP BY ano ORDER BY ano")
        for r in (cur.fetchall() or []):
            try:
                saida["anos"].append({
                    "ano": str(r[0] or ""), "pessoas": int(r[1] or 0),
                    "vl_pago": round(float(r[2] or 0), 2),
                    "vl_empenhado": round(float(r[3] or 0), 2),
                    "vl_liquidado": round(float(r[4] or 0), 2),
                    "coletado_em": str(r[5] or "")})
            except Exception:
                continue
        try:
            conn.close()
        except Exception:
            pass
    except Exception as e:
        try:
            _log().exception(f"resumo_diarias_anos: {e}")
        except Exception:
            pass
    return saida


def ultima_coleta_diarias_em():
    """Quando foi a última carga de diárias (`coletado_em` máximo, ou "")."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT MAX(coletado_em) FROM tb_diarias")
        linha = cur.fetchone()
        try:
            conn.close()
        except Exception:
            pass
        return str((linha[0] if linha else "") or "")
    except Exception:
        return ""


def ultima_diaria_coletada():
    """A última linha de diária gravada (nome, ano, valores, quando).

    É o "último dado coletado" que o painel mostra — quem foi, de que ano e
    quanto. Fail-soft: {} quando nada foi coletado.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT ano, nome_portal, cpf_parcial, vl_pago, "
                    "vl_empenhado, vl_liquidado, coletado_em FROM tb_diarias "
                    "ORDER BY coletado_em DESC, id DESC LIMIT 1")
        linha = cur.fetchone()
        try:
            conn.close()
        except Exception:
            pass
        if not linha:
            return {}
        return {"ano": str(linha[0] or ""), "nome_portal": str(linha[1] or ""),
                "cpf_parcial": str(linha[2] or ""),
                "vl_pago": float(linha[3] or 0),
                "vl_empenhado": float(linha[4] or 0),
                "vl_liquidado": float(linha[5] or 0),
                "coletado_em": str(linha[6] or "")}
    except Exception as e:
        try:
            _log().exception(f"ultima_diaria_coletada: {e}")
        except Exception:
            pass
        return {}


def resumo_diarias_publico():
    """Agregados anuais das diárias para o dado aberto (costura nº 5).

    EN: Yearly allowance aggregates for open data. PT-BR: por ano — total
    pago, maior, menor, média, mediana, moda, nº de favorecidos — mais a
    lista nominal (nome + valor pago) que o portal publica.

    A lista é nominal DE PROPÓSITO, e difere da folha: o portal publica cada
    favorecido com nome e valor abertamente, e o dado aberto aqui espelha a
    fonte — sem CPF (não pedido e desnecessário para a leitura). O que NÃO
    sai: CPF parcial, `user_nome`, `cd_fornecedor`.
    Fail-soft: `{"disponivel": False, ...}` quando nada foi coletado.
    """
    vazio = {"disponivel": False, "motivo": "", "anos": []}
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT ano FROM tb_diarias ORDER BY ano")
        anos = [str(r[0] or "") for r in (cur.fetchall() or []) if r[0]]
        if not anos:
            try:
                conn.close()
            except Exception:
                pass
            return {**vazio, "motivo": "diárias ainda não coletadas"}
        saida_anos = []
        for ano in anos:
            try:
                cur.execute("SELECT nome_portal, vl_pago, vl_empenhado, "
                            "vl_liquidado FROM tb_diarias WHERE ano=? "
                            "ORDER BY vl_pago DESC", (ano,))
                linhas = cur.fetchall() or []
                pagos = sorted(float(r[1] or 0) for r in linhas)
                pagos = [v for v in pagos if v > 0]
                total = round(sum(pagos), 2)
                n = len(pagos)
                media = round(total / n, 2) if n else 0.0
                mediana = 0.0
                if pagos:
                    meio = len(pagos) // 2
                    if len(pagos) % 2:
                        mediana = pagos[meio]
                    else:
                        mediana = round((pagos[meio - 1] + pagos[meio]) / 2, 2)
                moda_valor, moda_vezes = 0.0, 0
                if pagos:
                    from collections import Counter as _Contador
                    mais = _Contador(pagos).most_common(1)
                    if mais:
                        moda_valor = mais[0][0]
                        moda_vezes = int(mais[0][1])
                saida_anos.append({
                    "ano": ano, "pessoas": n, "total_pago": total,
                    "maior": pagos[-1] if pagos else 0.0,
                    "menor": pagos[0] if pagos else 0.0,
                    "media": media, "mediana": mediana,
                    "moda": moda_valor, "moda_vezes": moda_vezes,
                    "lista": [{"nome": str(r[0] or ""),
                               "vl_pago": round(float(r[1] or 0), 2),
                               "vl_empenhado": round(float(r[2] or 0), 2),
                               "vl_liquidado": round(float(r[3] or 0), 2)}
                              for r in linhas],
                })
            except Exception as e:
                try:
                    _log().warning(f"resumo_diarias_publico({ano}): {e}")
                except Exception:
                    pass
                continue
        try:
            conn.close()
        except Exception:
            pass
        if not saida_anos:
            return {**vazio, "motivo": "falha ao agregar as diárias"}
        return {"disponivel": True, "motivo": "", "anos": saida_anos,
                "coletado_em": ultima_coleta_diarias_em()}
    except Exception as e:
        try:
            _log().exception(f"resumo_diarias_publico: {e}")
        except Exception:
            pass
        return {**vazio, "motivo": "falha ao ler as diárias"}


# Grupos de vínculo para a leitura contratado x concursado (12/10/2026):
# Efetivo passou em concurso; Determinado/Indeterminado são contratos
# temporários; o resto (estágio, comissão, pensão...) não entra nos dois
# e aparece como "outros" para a conta fechar.
GRUPO_VINCULO_CONCURSADO = ("efetivo",)
GRUPO_VINCULO_CONTRATADO = ("contrato determinado", "contrato indetermindo")


def grupo_do_vinculo(vinculo):
    """'concursado', 'contratado' ou 'outros' — nunca levanta."""
    try:
        texto = _sem_acentos(str(vinculo or "")).lower().strip()
        if texto in GRUPO_VINCULO_CONCURSADO:
            return "concursado"
        if texto in GRUPO_VINCULO_CONTRATADO:
            return "contratado"
        return "outros"
    except Exception:
        return "outros"


def listar_cargos_com_proventos(competencia=""):
    """Cargos com 2+ pessoas com provento capturado (para o seletor).

    EN: Roles with 2+ captured payslips. PT-BR: só cargo com par compara —
    cargo de uma pessoa só não tem "maior que os pares". Fail-soft: [].
    """
    try:
        from collections import Counter as _Contador
        conn = get_connection()
        cur = conn.cursor()
        if not (competencia or "").strip():
            cur.execute("SELECT MAX(competencia) FROM tb_detalhe_ficha")
            linha = cur.fetchone()
            competencia = str((linha[0] if linha else "") or "")
        cur.execute("SELECT DISTINCT user_nome FROM tb_detalhe_ficha "
                    "WHERE competencia=?", (competencia,))
        pessoas = {str(r[0] or "") for r in (cur.fetchall() or []) if r[0]}
        contagem = _Contador()
        for pessoa in pessoas:
            try:
                contratos = listar_contratos(pessoa) or []
            except Exception:
                continue
            if not contratos:
                continue
            principal = next((c for c in contratos if c.get("principal")),
                             contratos[0])
            cargo = str(principal.get("cargo") or "").strip()
            if cargo:
                contagem[cargo] += 1
        try:
            conn.close()
        except Exception:
            pass
        return sorted([c for c, n in contagem.items() if n >= 2])
    except Exception as e:
        try:
            _log().exception(f"listar_cargos_com_proventos: {e}")
        except Exception:
            pass
        return []


def comparar_proventos_por_cargo(cargo, competencia=""):
    """Quem ganha mais que os pares no MESMO cargo (controle interno).

    EN: Same-role pay comparison. PT-BR: pares ordenados por proventos
    (maior primeiro), mediana do cargo e a marca de quem está ACIMA dela —
    com o grupo de cada um (concursado/contratado/outros) e as contagens:
    quantos acima, quantos deles concursados, quantos contratados.

    "Maior" é acima da MEDIANA dos pares (não do máximo): o máximo sozinho
    não diz se os demais estão juntos ou espalhados, e a mediana parte o
    cargo no meio — quem está acima dela ganha mais que (pelo menos) metade
    dos pares. Proventos vêm da ficha capturada; cargo/vínculo, do contrato
    principal. Fail-soft: `{"disponivel": False, ...}`.
    """
    vazio = {"disponivel": False, "motivo": "", "cargo": cargo or "",
             "competencia": "", "pares": []}
    try:
        cargo = str(cargo or "").strip()
        if not cargo:
            return {**vazio, "motivo": "informe o cargo"}
        conn = get_connection()
        cur = conn.cursor()
        if not (competencia or "").strip():
            cur.execute("SELECT MAX(competencia) FROM tb_detalhe_ficha")
            linha = cur.fetchone()
            competencia = str((linha[0] if linha else "") or "")
        competencia = (competencia or "").strip()
        cur.execute("SELECT user_nome, proventos FROM tb_detalhe_ficha "
                    "WHERE competencia=?", (competencia,))
        fichas = {str(r[0] or ""): _valor_numerico(r[1])
                  for r in (cur.fetchall() or []) if r[0]}
        try:
            conn.close()
        except Exception:
            pass
        if not fichas:
            return {**vazio, "motivo": "sem contracheque capturado"}
        pares = []
        try:
            conn3 = get_connection()
            cur3 = conn3.cursor()
            cur3.execute("SELECT user_nome, user_nome_completo FROM tb_usuarios")
            nomes = {str(r[0] or ""): (str(r[1] or "").strip() or str(r[0] or ""))
                     for r in (cur3.fetchall() or [])}
            try:
                conn3.close()
            except Exception:
                pass
        except Exception:
            nomes = {}
        for pessoa, proventos in fichas.items():
            try:
                contratos = listar_contratos(pessoa) or []
            except Exception:
                continue
            if not contratos:
                continue
            principal = next((c for c in contratos if c.get("principal")),
                             contratos[0])
            if str(principal.get("cargo") or "").strip() != cargo:
                continue
            nome = nomes.get(pessoa, pessoa)
            pares.append({"user_nome": pessoa, "nome": nome,
                          "proventos": round(float(proventos or 0), 2),
                          "vinculo": str(principal.get("vinculo") or ""),
                          "grupo": grupo_do_vinculo(
                              principal.get("vinculo"))})
        if len(pares) < 2:
            return {**vazio, "motivo": "cargo com menos de 2 pares",
                    "competencia": competencia}
        pares.sort(key=lambda p: -p["proventos"])
        valores = sorted(p["proventos"] for p in pares)
        meio = len(valores) // 2
        if len(valores) % 2:
            mediana = valores[meio]
        else:
            mediana = round((valores[meio - 1] + valores[meio]) / 2, 2)
        for par in pares:
            par["acima_da_mediana"] = bool(par["proventos"] > mediana)
        acima = [p for p in pares if p["acima_da_mediana"]]
        return {"disponivel": True, "motivo": "", "cargo": cargo,
                "competencia": competencia, "total": len(pares),
                "mediana": mediana,
                "minimo": valores[0], "maximo": valores[-1],
                "acima": len(acima),
                "acima_concursados": sum(1 for p in acima
                                         if p["grupo"] == "concursado"),
                "acima_contratados": sum(1 for p in acima
                                         if p["grupo"] == "contratado"),
                "pares": pares}
    except Exception as e:
        try:
            _log().exception(f"comparar_proventos_por_cargo({cargo}): {e}")
        except Exception:
            pass
        return {**vazio, "motivo": "falha ao comparar"}


def comparar_todos_os_cargos(competencia=""):
    """Todos os cargos comparáveis de uma vez, agrupados (visão completa).

    EN: All comparable roles in one pass. PT-BR: a mesma conta de
    `comparar_proventos_por_cargo`, mas em 3 consultas (não 58×N): uma
    passada monta pares, medianas e acima-da-mediana de cada cargo com 2+
    pares, ordenados por proventos. Existe porque a lista completa pedida
    não cabe em 58 idas ao banco. Fail-soft: `{"disponivel": False, ...}`.
    """
    vazio = {"disponivel": False, "motivo": "", "competencia": "",
             "cargos": []}
    try:
        conn = get_connection()
        cur = conn.cursor()
        if not (competencia or "").strip():
            cur.execute("SELECT MAX(competencia) FROM tb_detalhe_ficha")
            linha = cur.fetchone()
            competencia = str((linha[0] if linha else "") or "")
        competencia = (competencia or "").strip()
        if not competencia:
            try:
                conn.close()
            except Exception:
                pass
            return {**vazio, "motivo": "sem contracheque capturado"}
        cur.execute("SELECT user_nome, proventos FROM tb_detalhe_ficha "
                    "WHERE competencia=?", (competencia,))
        fichas = [(str(r[0] or ""), _valor_numerico(r[1]))
                  for r in (cur.fetchall() or []) if r[0]]
        cur.execute("SELECT user_nome, cargo, vinculo, "
                    "COALESCE(principal, 0) FROM tb_contratos")
        contratos = {}
        for user_nome, cargo, vinculo, principal in (cur.fetchall() or []):
            try:
                chave = str(user_nome or "")
                if not chave:
                    continue
                atual = contratos.get(chave)
                if atual is None or (int(principal or 0) and
                                     not atual[2]):
                    contratos[chave] = (str(cargo or "").strip(),
                                        str(vinculo or ""), bool(principal))
            except Exception:
                continue
        cur.execute("SELECT user_nome, user_nome_completo FROM tb_usuarios")
        nomes = {str(r[0] or ""): (str(r[1] or "").strip() or str(r[0] or ""))
                 for r in (cur.fetchall() or [])}
        try:
            conn.close()
        except Exception:
            pass
        from collections import defaultdict as _dd
        grupos = _dd(list)
        for pessoa, proventos in fichas:
            try:
                cargo, vinculo, _ = contratos.get(pessoa, ("", "", False))
                if not cargo:
                    continue
                grupos[cargo].append({
                    "nome": nomes.get(pessoa, pessoa),
                    "proventos": round(float(proventos or 0), 2),
                    "vinculo": vinculo,
                    "grupo": grupo_do_vinculo(vinculo),
                })
            except Exception:
                continue
        saida_cargos = []
        for cargo in sorted(grupos):
            try:
                pares = sorted(grupos[cargo], key=lambda p: -p["proventos"])
                if len(pares) < 2:
                    continue
                valores = sorted(p["proventos"] for p in pares)
                meio = len(valores) // 2
                if len(valores) % 2:
                    mediana = valores[meio]
                else:
                    mediana = round((valores[meio - 1] + valores[meio]) / 2, 2)
                for par in pares:
                    par["acima_da_mediana"] = bool(par["proventos"] > mediana)
                acima = [p for p in pares if p["acima_da_mediana"]]
                # Faixa de ±R$ 1.000 da mediana (12/10/2026, pedido do
                # responsável): o interessante não é "acima/abaixo" seco, e
                # sim quem está 1.000 para lá ou para cá — o extremo.
                faixa = [p for p in pares
                         if abs(float(p["proventos"] or 0) - mediana) > 1000]
                # "Acima +1000" e "abaixo −1000" (12/10/2026): os dois
                # extremos, cada um com o split concursado/contratado.
                extremo_alto = [p for p in faixa
                                if float(p["proventos"] or 0) > mediana]
                extremo_baixo = [p for p in faixa
                                 if float(p["proventos"] or 0) < mediana]
                saida_cargos.append({
                    "cargo": cargo, "competencia": competencia,
                    "total": len(pares), "mediana": mediana,
                    "media": round(sum(valores) / len(valores), 2),
                    "minimo": valores[0], "maximo": valores[-1],
                    "acima": len(acima),
                    "acima_concursados": sum(
                        1 for p in acima if p["grupo"] == "concursado"),
                    "acima_contratados": sum(
                        1 for p in acima if p["grupo"] == "contratado"),
                    "alto_concursados": sum(
                        1 for p in extremo_alto
                        if p["grupo"] == "concursado"),
                    "alto_contratados": sum(
                        1 for p in extremo_alto
                        if p["grupo"] == "contratado"),
                    "baixo_concursados": sum(
                        1 for p in extremo_baixo
                        if p["grupo"] == "concursado"),
                    "baixo_contratados": sum(
                        1 for p in extremo_baixo
                        if p["grupo"] == "contratado"),
                    "pares": pares,
                })
            except Exception:
                continue
        if not saida_cargos:
            return {**vazio, "motivo": "sem cargos com pares"}
        return {"disponivel": True, "motivo": "", "competencia": competencia,
                "cargos": saida_cargos,
                "total_cargos": len(saida_cargos),
                "total_pessoas": sum(c["total"] for c in saida_cargos)}
    except Exception as e:
        try:
            _log().exception(f"comparar_todos_os_cargos: {e}")
        except Exception:
            pass
        return {**vazio, "motivo": "falha ao comparar"}


# ================= COMPATIBILIDADE =================

PERFIS_VALIDOS = PERFIS_GLOBAIS
DB_PATH = DB_CAD_PATH


def validar_acesso_modulo_compat(user_nome, modulo_chave):
    """Backward-compatible alias of `validar_acesso_modulo`."""
    return validar_acesso_modulo(user_nome, modulo_chave)


init_db()
