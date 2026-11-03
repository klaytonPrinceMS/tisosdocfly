"""Central database connection and configuration layer. Internally delegates
to `Repositorio` (SQLAlchemy ORM) while keeping raw sqlite3 `get_connection`
for backward compatibility.

Conexão e configurações centrais do T! SOS DocFly (banco central db_mod_tisosdocfly.db).

Camada mais baixa: sem imports circulares — só os outros módulos dependem daqui.
Usa `Repositorio` (SQLAlchemy ORM) internamente para `get_config`/`set_config`;
mantém `get_connection` (sqlite3 raw) para compatibilidade com código
legado que ainda não foi migrado. Notificações pós-gravação (ex.: limpar
caches `lru_cache` de outros módulos) usam `registrar_hook_config` —
nunca import direto (nem lazy) de outro módulo aqui dentro.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import sqlite3
from functools import lru_cache

_HOOKS_CONFIG = []  # lista de (fn, chaves_ou_None)


def registrar_hook_config(fn, apenas_chaves=None):
    """Registra fn() para rodar após cada gravação de config bem-sucedida.

    Usado por módulos com caches derivados de `tb_config` (ex.: tema,
    template de empenhos): em vez de `bd_conexao` importar o módulo
    (ciclo núcleo→módulo), o módulo se registra aqui no próprio import.
    `apenas_chaves` restringe o disparo (ex.: "empenhos_template_nome").
    Hooks nunca derrubam o `set_config` (cada um roda em try/except).
    """
    if isinstance(apenas_chaves, str):
        chaves = {apenas_chaves}
    elif apenas_chaves:
        chaves = set(apenas_chaves)
    else:
        chaves = None
    def _mesmo(a, b):
        return (getattr(a, "__func__", a) is getattr(b, "__func__", b)
                and getattr(a, "__self__", None) is getattr(b, "__self__", None))
    if callable(fn) and all(not _mesmo(f, fn) for f, _ in _HOOKS_CONFIG):
        _HOOKS_CONFIG.append((fn, chaves))

# `BASE_DIR` é `src/` — a pasta que CONTÉM os `mod_*` (é dela que sai o
# `sys.path` e que guarda `assets/`). `DIR_PROJETO` é a raiz do repositório, um
# nível ACIMA: é onde vivem os bancos `db_mod_*.db`, `logs/`, `backup/`, `docs/`,
# `site/` e o `.venv`. Desde 02/10/2026 o código vive em `src/` (AGENTS.md §2.2)
# e os bancos continuam na raiz, como manda a regra de nunca commitar `*.db`
# junto com o código-fonte.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Mesma regra do `repositorio.py` (03/10/2026): `TISOSDOCFLY_DIR_BANCO` move os
# `db_mod_*.db` para outro diretorio, no processo inteiro. Sem isto os dois
# modulos discordariam sobre onde esta o banco e o override nao resolveria.
DIR_PROJETO = os.path.dirname(BASE_DIR)
_DIR_BANCO_OVERRIDE = os.environ.get("TISOSDOCFLY_DIR_BANCO", "").strip()
if _DIR_BANCO_OVERRIDE:
    os.makedirs(_DIR_BANCO_OVERRIDE, exist_ok=True)
    DIR_PROJETO = _DIR_BANCO_OVERRIDE
DB_PATH = os.path.join(DIR_PROJETO, "db_mod_tisosdocfly.db")

PADRAO_CONFIG = {
    "titulo_sistema": "T! SOS DOCFLY",
    "icone_sistema": "hub",
    "cor_principal": "#000000",
    "cor_fundo": "#EEEEEE",
    "texto_login_titulo": "T! SOS DOCFLY Básica",
    "texto_login_subtitulo": "Acesso restrito a usuários autorizados",
    "texto_login_hint": "Novos usuários? Procure o DTI para realizar o seu cadastro.",
    "texto_home_saudacao": "Olá",
    "texto_home_subtitulo": "Sua plataforma corporativa é tudo em um só lugar.",
    # Segurança local (24/10/2026, pós-pentest): timeout de inatividade em
    # minutos (0 = desligado) e falhas recentes do IP que passam a exigir
    # o captcha local. Tudo sem serviço externo.
    "sessao_timeout_min": "30",
    "captcha_apos_falhas": "3",
    "texto_rodape": "uso interno",
    # Observabilidade — loguru (aba Observabilidade)
    "log_ativo": "1",
    "log_nivel": "INFO",
    "log_rotacao": "1 month",
    "log_retencao": "4 months",
    "log_console": "auto",
    "log_otel_envio": "1",
    "log_otel_nivel": "DEBUG",
    # Observabilidade — telemetria OTel / stack remota
    "otel_ativo": "1",
    "otel_endpoint": "localhost:4317",
    "otel_auto_start_stack": "1",
    # Observabilidade — Grafana
    "grafana_url": "http://localhost:3000",
    # Documentação MkDocs — DESLIGADA por padrão desde 02/10/2026 (decisão do
    # responsável). Antes valia "1" e a documentação subia em todo boot: um
    # `mkdocs build` completo (até 120 s) mais um servidor HTTP na LAN, para um
    # servidor que ninguém tinha pedido. Quem liga usa `--ativ-docs` na linha de
    # comando ou o interruptor em Configurações, que grava `docs_ativo=1`.
    "docs_ativo": "0",
    # SGBD — SQLite (padrão universal) ou PostgreSQL opcional em container
    # (docker/postgres/docker-compose.yml; engine via banco_conexao.py)
    "banco_tipo": "sqlite",
    "postgres_url": "postgresql+psycopg2://tisosdocfly:tisosdocfly@localhost:5432/tisosdocfly",
    # Usuário de operações normais (criado no banco PostgreSQL)
    "banco_usuario": "tisosdocfly",
    "banco_senha": "tisosdocfly",
    # Usuário de operações administrativas (criação de banco, migrations)
    "banco_admin_usuario": "master",
    "banco_admin_senha": "master",
    # Aparência do módulo T! SOS DocFly (botões do sistema — mesmo contrato
    # de 6 chaves dos demais módulos, prefixo "tisosdocfly")
    "tisosdocfly_cor_botao": "#000000",
    "tisosdocfly_cor_texto_botao": "#FFFFFF",
    "tisosdocfly_cor_fundo": "",
    "tisosdocfly_cor_titulo": "#212121",
    "tisosdocfly_btn_tamanho": "medium",
    "tisosdocfly_texto_header": "",
    # Aparência dos cards do módulo T! SOS DocFly (fundo + texto base)
    "tisosdocfly_cor_fundo_card": "#FFFFFF",
    "tisosdocfly_cor_texto_card": "",
    # Avisos do sistema (toasts): tempo de exibição em segundos (10-30, padrão
    # 20). O piso de 10s é do responsável (04/10/2026) e vale no código —
    # `tema_modulo.notificacao_timeout` corta em `max(10, v)`, então nem
    # reconfigurando o painel dá para voltar a 1s.
    "notificacao_timeout": "20",
    # Card "Configurações gerais": intervalo do backup em horas e retenção de
    # sessão em dias. Viviam SÓ como literais espalhados (INSERT de banco novo
    # + `padrao=` da tela + dicionário do "Restaurar padrão"), então o card não
    # tinha fonte única de verdade e um padrão divergente quebrava a tela
    # quando a chave faltava no tb_config. Aqui ficam canônicos.
    "backup_interval_hours": "12",
    "sessao_retencao": "50",
    # Contador de acessos ao sistema (incrementado a cada login bem-sucedido)
    "contador_acessos_total": "0",
    "contador_acessos_inicio": "",
    # Hora Certa (07/10/2026): sincronização NTP.br e tolerância de divergência.
    # `hora_ntp_ativa=1` consulta a/b/c.ntp.br no boot e no "Sincronizar agora";
    # `hora_tolerancia_seg` é a divergência máxima aceita antes de tentar o
    # ajuste do SO e de acusar "hora errada" em tela.
    "hora_ntp_ativa": "1",
    "hora_tolerancia_seg": "5",
    # Validação de senha (`mod_tisosdocfly/validador_senha.py`).
    #
    # A sondagem de internet é o que garante o requisito de rede local: com
    # `senha_sondar_internet=0` a camada de vazamento nem tenta abrir socket,
    # e com `senha_consultar_vazamento=0` ela some de vez. As duas são 1 por
    # padrão porque a sondagem é barata e tem cache de 15 min — mas quem instala
    # em rede fechada tem o botão para desligar sem mexer em código.
    "senha_consultar_vazamento": "1",
    "senha_sondar_internet": "1",
    # 6 é o piso que já valia no código; subir barra o existente sem querer.
    "senha_tamanho_minimo": "6",
    # Tentativas de login (30/09/2026): 3 é o PISO, configurável pelo admin até
    # 20. Acima do piso, o login errado NÃO bloqueia a conta — aumenta a
    # espera (1s, 2,5s, 5s… até o teto), que encarece o ataque de dicionário
    # sem fechar o acesso de quem só esqueceu a senha.
    "login_tentativas_maximas": "3",
    "login_atraso_maximo_seg": "30",
}


def get_connection():
    """Legacy raw DBAPI connection (WAL + synchronous=NORMAL).

    Prefer `Repositorio` from `repositorio.py` for new code.
    EN: Returns a DBAPI connection (SQLite or PostgreSQL) for legacy callers.
    PT: Devolve conexão DBAPI (SQLite ou PostgreSQL) para código legado.
    """
    from mod_tisosdocfly.banco_conexao import conexao
    conn = conexao("tisosdocfly")
    if conn is None:
        raise RuntimeError("Falha ao abrir conexão do banco central")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    """Bootstrap do banco central: cria tabelas e semeia padrões (idempotente).

    Usa `conexao("tisosdocfly")` (SQLite ou PostgreSQL) — o sistema controla o
    backend. `INSERT OR IGNORE` virou `ON CONFLICT DO NOTHING` (portável).
    """
    from mod_tisosdocfly.banco_conexao import conexao

    conn = conexao("tisosdocfly")
    if conn is None:
        raise RuntimeError("Falha ao abrir conexão do banco central")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tb_config (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tb_sessoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            modulo TEXT,
            login_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            logout_timestamp DATETIME,
            cookie_hash TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tb_modulos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chave TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            icone TEXT,
            rota TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            nativo INTEGER NOT NULL DEFAULT 0,
            ordem INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Verificação de senha (`validador_senha.py`), 30/09/2026.
    #
    # `tb_senha_vazamento_cache` NÃO é o corpus de senhas vazadas, e sim a
    # memória das consultas já feitas: par (prefixo, sufixo) do SHA-1 e a
    # contagem devolvida. Existe para a segunda tentativa com a mesma senha sair
    # instantânea e sem repetir chamada — e para que o caminho que BLOQUEIA a
    # troca (que roda no event-loop e por isso não pode depender de rede)
    # consiga ler o veredito em vez de refazer a consulta.
    #
    # `tb_senha_padrao_organizacao` é configuração do PRÓPRIO órgão: as
    # palavras com as quais o público monta senha (nome da prefeitura, do
    # órgão, um termo do serviço). `tipo='exata'` compara a senha inteira;
    # `tipo='palavra'` reprova se a senha CONTER o padrão.
    #
    # A lista de senhas vazadas em texto plano fica de fora, de propósito: ver
    # `validador_senha.motivos_sem_corpus()`.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tb_senha_vazamento_cache (
            prefixo TEXT NOT NULL,
            sufixo TEXT NOT NULL,
            contagem INTEGER NOT NULL DEFAULT 0,
            data_consulta DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (prefixo, sufixo)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tb_senha_padrao_organizacao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            padrao TEXT NOT NULL UNIQUE,
            descricao TEXT,
            tipo TEXT NOT NULL DEFAULT 'palavra',
            ativo INTEGER NOT NULL DEFAULT 1,
            data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("SELECT COUNT(*) FROM tb_config")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES ('versao_sistema', '1.0.260913')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES ('cotadisco_global_gb', '10')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES ('backup_interval_hours', '12')")
    # =====================================================================
    # MODELO ÚNICO DE VERSIONAMENTO (AGENTS.md §4.2) — o seed canônico.
    #
    # A versão de um módulo mora em UM lugar só: a chave
    # `versao_modulo:<chave>` da `tb_config` CENTRAL (`db_mod_tisosdocfly.db`),
    # onde `<chave>` é a chave de `MODULOS_BD` (`repositorio.py`) — nunca o
    # nome da pasta do módulo. É essa chave que o rodapé lê
    # (`_obter_versao_modulo`, em `mod_tisosdocfly/telas.py`) e é a chave de
    # versionamento da trilha de auditoria (`_chave_canonica`,
    # `mod_auditoria/bd_manipulador.py`).
    #
    # Este tuple é o que faz um banco NOVO nascer certo; as migrações
    # `migracao_versao_pendentes_261003` e `migracao_versao_<chave>_261003_*`,
    # mais abaixo, são quem alcança o banco JÁ EM USO. Os dois são
    # obrigatórios: um sem o outro deixa metade das instalações errada (§4.2).
    #
    # O formato é `X.Y.AAMMDD` e o patch é a DATA DA ALTERAÇÃO DO CÓDIGO
    # daquele módulo — não um contador de revisão. Várias mudanças no mesmo
    # dia têm a mesma versão, e está tudo bem.
    #
    # POR QUE 261003 PARA DOZE CHAVES: 03/10/2026 é a data em que o modelo
    # único foi implantado e em que os módulos abaixo tiveram código alterado
    # (mecanismo de versão próprio removido, chave de auditoria corrigida,
    # `os` com o painel de visão geral corrigido, `dados_abertos` com o
    # `execute` que faltava em `listar_fontes`). `blog`, `filas`, `tecnico`,
    # `lista_telefonica` e `estoque` NÃO tiveram código alterado: ficam na
    # data da SUA última alteração, e o alinhamento abaixo é quem garante que
    # o banco em uso bate com isto.
    for _chave_mod, _ver in (
        # (03/10) modelo único: `auditoria` (canonicalização da chave +
        # migração da trilha LGPD), `editar_pdf` (chave de auditoria
        # `editar_pdf`), `agregador_noticias` (mecanismo de versão próprio
        # removido + `_audit` corrigido), `solicita_impressao` (chave órfã
        # `tb_configuracoes_modulo` removida), `empenhos` (chave de
        # auditoria `empenhos`) e `os` (painel de visão geral: as queries
        # da tela foram para o `bd_manipulador` do módulo — ver
        # `migracao_versao_os_261003_visao_geral`).
        #
        # (04/10) SAEM DO LOTE DE 03/10 e ganham data própria:
        #   `tisosdocfly` — `_ddl_postgres` do núcleo (ver
        #     `migracao_versao_tisosdocfly_261004_ddl_references`);
        #   `usuarios` — pessoa × contrato, histórico e busca no servidor
        #     (ver `migracao_versao_usuarios_261004_pessoa_contrato`), e o
        #     bloco de campos do Portal da Transparência no cadastro, como
        #     texto somente-leitura nas três telas onde o cadastro é lido
        #     (ver `migracao_versao_usuarios_261004_folha_no_cadastro`).
        # Ficar em 261003 diria que o código de 04/10 é o de 03/10, que
        # é justamente o que a §4.2 existe para não deixar acontecer.
        # (05/10) `tisosdocfly` — layout da TELA VERDE (`_login_verde`): padding
        # lateral do formulário em 12px e largura padrão única de 680px nas três
        # telas (login, troca de senha e troca de credenciais do `master`), com
        # o telefone do `master` inteiro na coluna de 319px. Ver
        # `migracao_versao_tisosdocfly_261005_layout_tela_verde`.
        # (06/10) `tisosdocfly` — o VERDE passa a ser o padrão do sistema para quem
        # não fez escolha pessoal, e a política de senha ganha faixa amarela com
        # termo de responsabilidade. Ver
        # `migracao_versao_tisosdocfly_261006_padrao_verde`.
        # (08/10) fail-soft da hora no boot via loguru warning (sem traceback).
        # Ver `migracao_versao_tisosdocfly_261008_hora_failsoft`.
        # (10/10) flags `--depencias` e `--popular` no assistente de ativação:
        # a primeira roda `instalar_externos.py` antes do boot, a segunda sobe
        # o sistema e só então dispara `coleta_kbp.py --atualizar` em 2º plano
        # (`app.on_startup` + thread). Ver
        # `migracao_versao_tisosdocfly_261010_flags_utilitarios`.
        # (13/10) banner de desconexão em PT-BR (`language="pt-BR"` no boot +
        # tabela injetada em `nicegui_patch`) e fase da operação no título
        # da aba nos handlers pesados de empenhos. Ver
        # `migracao_versao_tisosdocfly_261013_banner_ptbr`.
        # (14/10) flag `--liberarFirewall` no assistente de ativação: cria
        # a regra de entrada do Firewall do Windows para a porta do site
        # (só perfis privada/doméstica). Ver
        # `migracao_versao_tisosdocfly_261014_liberar_firewall`.
        # (15/10) job `coleta_dados_abertos` passa pelo distribuidor de
        # coleta única. Ver
        # `migracao_versao_tisosdocfly_261015_coleta_unica`.
        # (16/10) telefone: máscara de entrada com 11 casas e `formatar_br`
        # com o 9 isolado (`+55 (35) 9 8818-3288`). Ver
        # `migracao_versao_tisosdocfly_261016_formato_telefone`.
        # (16/10, continuação) comentário da tupla de telefones no Meu
        # perfil (`whatsapp` no índice 8). Ver
        # `migracao_versao_tisosdocfly_261016_tel_comentario`.
        # (17/10) a aba "Telefones" (faixas) sai de /configuracoes para o
        # admin da Lista Telefônica. Ver
        # `migracao_versao_tisosdocfly_261017_faixas_para_lista`.
        # (17/10, mesmo dia) job `cleanup_video` + fachada da biblioteca de
        # vídeos. Ver `migracao_versao_tisosdocfly_261017_video_limpeza`.
        # (18/10) gateway `dados_usuario_lista_gestao` (nome, cargo, unidade e
        # telefone de UM usuário), para a lista telefônica mostrar quem
        # recebeu a partilha como cartão de contato. Ver
        # `migracao_versao_tisosdocfly_261018_dados_pessoa`.
        # (20/10) 16 botões pela fábrica central `mod_tisosdocfly.ui_comum`:
        # `telas.py` ("edit"/"delete" do Meu perfil por `botao_icone`;
        # "Cancelar"/"Informar o telefone do setor"/"Voltar e informar o
        # número" por `botao` variante texto) e `tela_configuracoes.py`
        # (10 chamadas ao intermediário `_botao_padrao` — removido —
        # por `botao`/`botao_icone` diretos). Ver
        # `migracao_versao_tisosdocfly_261020_botao`.
        # (29/10) o botão do menu superior passa a mostrar SEMPRE o login
        # (matrícula), com o nome de tratamento só no tooltip. Ver
        # `migracao_versao_tisosdocfly_261029_header_login`.
        # (29/10, mesmo dia) segredo de sessão por arquivo
        # (`TISOSDOCFLY_STORAGE_SECRET_FILE`) ou Gerenciador de Credenciais
        # (`TISOSDOCFLY_STORAGE_SECRET_CREDMAN=1`) — ver
        # `migracao_versao_tisosdocfly_261029_segredos`.
        # (31/10) `_job_limpeza_video_agenda`, `_acao_agenda` e boot
        # para `video` + `dados_abertos` (cobertura Hora Certa). Ver
        # `migracao_versao_tisosdocfly_261031_agenda_horacerta`.
        # (01/11) fachada do Blog (`obter/definir_blog_carrossel_tempo`).
        # Ver `migracao_versao_tisosdocfly_261101_blog_facade`.
        ("tisosdocfly", "1.0.261101"),
        # (11/10) o sink core passou a receber TUDO que não tem arquivo
        # próprio: 1.581 chamadas de `get_logger` em nove módulos iam só para
        # o console, e o log de encerramento nunca chegava a arquivo. Ver
        # `migracao_versao_tisosdocfly_261011_log_todo_modulo`.
        # (10/10, depois) `enqueue=False` nos sinks do loguru — zera os 56
        # semáforos que o `resource_tracker` reclamava a cada `Ctrl+C` — e o
        # filtro do sink core passou a aceitar `modulo="tisosdocfly"`, que
        # antes não casava com sink nenhum e sumia de todo arquivo. Ver
        # `migracao_versao_tisosdocfly_261010_flags_utilitarios` (mesma versão
        # do dia).
        # (06/10) `usuarios` — TODO servidor que vem do `funcionarios.json`
        # nasce BLOQUEADO e só entra depois de passar pelo DTI. As colunas
        # `liberado_pelo_dti`/`_em`/`_por` guardam a liberação, e existem
        # porque `carga_folha` tem um caminho de volta que reabriria, a cada
        # boot, tudo o que o DTI fechou. Ver
        # `migracao_versao_usuarios_261006_liberacao_dti`.
        # (07/10) foto mensal + registro de cargas: `tb_foto_mensal` (uma
        # linha por pessoa por competência, com unidade/cargo/salário COMO
        # ESTAVAM) e `tb_cargas_folha` (proveniência de cada carga). Ver
        # `migracao_versao_usuarios_261007_foto_mensal`.
        # (09/10) coleta do DETALHE por ficha: `coleta_kbp.py` busca
        # `ServidorDetalhes` (CPF parcial + base/proventos/descontos/
        # líquido + verbas), com ritmo próprio configurável, e corrige o
        # `RAIZ` da coleta da folha (lia a chave errada e `--atualizar`
        # sempre recusava). Ver
        # `migracao_versao_usuarios_261009_coleta_detalhe`.
        # (10/10) a ficha do usuário deixa de ser TOOLTIP de hover e passa a
        # abrir por CLIQUE no nome, em diálogo: grade de duas colunas
        # (usuário/cadastro, perfil/situação, e-mail/telefone), a folha
        # inteira com remuneração/lotação/admissão, e os módulos em duas
        # colunas com selo colorido pelo PAPEL (geral=vermelho/branco,
        # admin=laranja/preto, comum=verde/preto). Ver
        # `migracao_versao_usuarios_261010_ficha_clique`.
        # (15/10) `qacomum`/`qamaster` NUNCA exigem troca de senha (decisão
        # do responsável: contas de teste, senha `123456` definitiva). Ver
        # `migracao_versao_usuarios_261015_qa_sem_troca`.
        # (16/10) linha de inclusão do telefone no admin: ordem [De quem é
        # (particular), Tipo (celular), DDI 12ch, Número 15ch, Disponibilizar,
        # Adicionar], DDD obrigatório no BR com (xx)xxxx-xxxx no fixo e
        # (xx)xxxxx-xxxx no celular, e "Disponibilizar" publicando na agenda
        # com confirmação dupla. Ver
        # `migracao_versao_usuarios_261016_telefone_publicavel`.
        # (16/10, continuação) correção do `_normalizar_telefone_cadastro`
        # (canônico `+55`+11 era mutilado e exibia como Bulgária), lista do
        # admin redesenhada DENTRO da coluna e número sempre completo com
        # DDI. Ver `migracao_versao_usuarios_261016_tel_lista_ddi`.
        # (16/10, continuação 2) lista em colunas com selos (Prefeitura
        # vermelha, Particular verde, Na agenda/Restrito) e marca WhatsApp
        # por telefone (coluna `whatsapp`, checkbox no cadastro e na
        # edição). Ver `migracao_versao_usuarios_261016_tel_selos` e
        # `migracao_versao_usuarios_261016_tel_whatsapp`.
        # (17/10) `video` entra no `ACESSO_PADRAO_NOVO_USUARIO` + liberação
        # única aos já cadastrados (`migracao_acesso_video_261017`). Ver
        # `migracao_versao_usuarios_261017_acesso_video`.
        # (18/10) espelho com TODOS os telefones liberados por usuário
        # (`telefones_publicaveis_todos_em_lote` + `telefones` no
        # `listar_para_lista_telefonica`). Ver
        # `migracao_versao_usuarios_261018_todos_tels`.
        # (20/10) botões do bloco de telefones do admin pela fábrica
        # central `mod_tisosdocfly.ui_comum` (`botao_icone` "edit"/"delete"
        # e `botao` "Cancelar"/"Voltar" variante texto). Ver
        # `migracao_versao_usuarios_261020_botao`.
        # (29/10) saudação passa ao formato "Primeiro.ultimo"
        # ("ana beatriz souza rocha" -> "Ana.rocha"). Ver
        # `migracao_versao_usuarios_261029_saudacao`.
        # (29/10, mesmo dia) a trava de arquivo da carga ignorava o cadastro
        # vazio: banco recriado + `.ultima_carga.json` antigo = pulo eterno.
        # Ver `migracao_versao_usuarios_261029_carga_cadastro_vazio`.
        ("usuarios", "1.0.261029"),
        ("auditoria", "1.0.261021"),
        ("editar_pdf", "1.0.261003"),
        ("empenhos", "1.0.261003"),
        # (08/10) `agregador_noticias` — filtro "Tribunais de Contas" prioriza
        # o TCE-MG (mescla 2:1, ~2/3 do tribunal mineiro). Ver a migração
        # `migracao_versao_agregador_noticias_261008_tcemg`.
        # (20/10) botões ícone pela fábrica central
        # `mod_tisosdocfly.ui_comum.botao_icone` ("delete" em
        # `telas_administracao.py: _rem` e paginação first/prev/next/last em
        # `telas.py`), com `on_click`, `tooltip`, `cor="negative"` e
        # `data-testid` preservados. Ver
        # `migracao_versao_agregador_noticias_261020_botao`.
        ("agregador_noticias", "1.0.261020"),
        ("solicita_impressao", "1.0.261003"),
        # (20/10) botões "Cancelar"/"Fechar" dos 7 diálogos (`telas.py`:
        # novo quadro, nova ordem, detalhe, colunas, renomear coluna,
        # convites, ajustes) pela fábrica central
        # `mod_tisosdocfly.ui_comum.botao` variante texto, com `on_click`
        # (`dlg.close`) e `data-testid` (`os-*-cancelar`/`os-*-fechar`)
        # novos. Ver `migracao_versao_os_261020_botao`.
        ("os", "1.0.261020"),
        # `dados_abertos` entra no lote de 03/10: `listar_fontes()` montava o
        # SQL e chamava `cur.fetchall()` sem `cur.execute(sql)` — a grade de
        # cards nascia vazia em toda instalação. Ver
        # `migracao_versao_dados_abertos_261003_execute`.
        # (10/10) painel mesclado folha+cadastro+contracheque+comissão, e o
        # `ui.link(url, url, target="_blank")` que derrubava a abertura do
        # conjunto. Ver `migracao_versao_dados_abertos_261010_painel_mesclado`.
        # (10/10, depois) botão único: o "Abrir" do card virou "Ver visão
        # geral dos dados" e foi para dentro dele; o painel antigo e os
        # helpers que só ele usava saíram; o `registrar_consulta` mudou de
        # lugar; e o cache dos assets passou a ser o hash do conteúdo. Ver
        # `migracao_versao_dados_abertos_261010_botao_unico`.
        # (13/10) grade com teto de 4 cards por linha + botoes PDF/CSV/JSON
        # com a mesma altura (`items-stretch` + `white-space: nowrap` no
        # rodape do card). Ver `migracao_versao_dados_abertos_261013_grade_4col`.
        # (14/10) contagem "N conjunto(s) de dados" removida da tela.
        # (14/10, depois) card "Coleta PortalFácil" no admin (coletar agora
        # + agenda). Ver `migracao_versao_dados_abertos_261014_coleta_admin`.
        # (15/10) URL única configurável + progresso ao vivo. Ver
        # `migracao_versao_dados_abertos_261015_coleta_url_progresso`.
        # (15/10, depois) coleta única: distribuidor + botões inoperantes
        # durante a coleta. Ver
        # `migracao_versao_dados_abertos_261015_coleta_unica`.
        # (20/10) botões "close"/"delete" da comparação PNTP
        # (`telas.py: _celula_municipio` e `telas_administracao.py:
        # `_linha_comparacao_pntp`) pela fábrica central
        # `mod_tisosdocfly.ui_comum.botao_icone`. Ver
        # `migracao_versao_dados_abertos_261020_botao`.
        ("dados_abertos", "1.0.261021"),
        # (11/10) card sem handler de clique, id único por instância de
        # painel e exportação com os quatro blocos que a tela mostra. Ver
        # `migracao_versao_dados_abertos_261011_card_sem_clique`.
        # (11/10, terceiro) painel do PNTP: a redundância do selo com a faixa de
        # indicadores saiu (o índice e o nível apareciam 3 e 5 vezes), "sem
        # histórico" virou UMA nota do conjunto em vez de 8 células, e a
        # classificação passou a `display: grid` — o `flex: 2fr` anterior era
        # CSS inválido e deixava as colunas do cabeçalho fora de linha com as
        # das linhas. O `_abrir_pntp` virou `async` + `run.io_bound` com
        # spinner. Ver `migracao_versao_dados_abertos_261011_painel_pntp`.
        # (10/10, terceiro) PNTP: card do nível de transparência, comparação por
        # nome, histórico mensal/anual e coleta no boot e no dia 5. E a
        # exportação em PDF/CSV/JSON exigida pelo art. 8º, § 3º, II e III da
        # Lei nº 12.527/2011. Ver `migracao_versao_dados_abertos_261010_pntp`.
        # `filas` entra no lote de 03/10: o upload de mídia gravava o arquivo
        # direto no event-loop (travava a tisosdocfly inteira com vídeo grande) e
        # o painel `/admin/filas` não expunha nenhum `data-testid`. Ver
        # `migracao_versao_filas_261003_upload_io_bound`.
        # (20/10) 53 botoes pela fabrica central `mod_tisosdocfly.ui_comum`:
        # rotulados por `botao` (primario/contorno/perigo), icone-only por
        # `botao_icone` (com `cor`/`tooltip`/`data-testid` preservados), flat de
        # dialogo por `botao` variante texto compacto; 4 condicionais com `if`
        # de variante (Fundo/Tirar fundo, Ativar/Desativar em `telas.py` e
        # `telas_administracao.py`); `rodape_salvar_restaurar` removido do import
        # parado (`telas_administracao.py` nao tem rodape salvar/restaurar).
        # Ver `migracao_versao_filas_261020_botao`.
        # (01/11) horário de funcionamento por fila + limite de re-chamadas
        # (`rechamar`) — ver `migracao_versao_filas_261101_horario_rechamada`.
        ("filas", "1.0.261101"),
        # `lista_telefonica` entra no lote de 03/10 pelo 4º degrau do
        # organograma: o banco já aceita qualquer unidade não-raiz como pai
        # (`_pai_valido`), mas os DOIS formulários e o painel do admin ainda
        # param o pai no degrau anterior. Ver
        # `migracao_versao_lista_telefonica_261003_quarto_degrau`.
        # (06/10) abre no CSV com grade `@container` e arquivo UTF-8 — ver
        # `migracao_versao_lista_telefonica_261006_csv_utf8`.
        # (07/10) a MATRÍCULA some do cartão do diretório: é dado do RH, e o
        # cartão responde "quem é e onde trabalha". Ver
        # `migracao_versao_lista_telefonica_261007_sem_matricula`.
        # (10/10) o comentário que DOCUMENTAVA a remoção da matrícula citava a
        # matrícula — a checagem do §8.3 pegou. Ver
        # `migracao_versao_lista_telefonica_261010_matricula_comentario`.
        # (15/10) o recorte filtrado baixa em PDF denso no molde da lista
        # fixa (botão único "Baixar PDF", Nome | Cargo | Telefone,
        # multipágina) — ver
        # `migracao_versao_lista_telefonica_261015_pdf_resultado`.
        # (17/10) o card "Faixas de telefone da prefeitura" muda de
        # /configuracoes (aba Telefones, removida) para /admin/lista_telefonica.
        # Ver `migracao_versao_lista_telefonica_261017_faixas`.
        # (18/10) coluna `telefones_json` (todos os liberados por contato,
        # com WhatsApp), card com scroll + ligar/zap por número, PDF com
        # todos os números, e escolha de listas no cadastro/edição do
        # contato pessoal. Ver
        # `migracao_versao_lista_telefonica_261018_tels_json`.
        # (20/10) 4 botões pela fábrica central `mod_tisosdocfly.ui_comum`:
        # "Baixar PDF" do recorte e da lista CSV (`telas.py`) por
        # `botao` variante primario (sem `style` manual), e anterior/
        # próxima da paginação por `botao_icone` preservando
        # `data-testid`/`aria-label`/`disable`. Ver
        # `migracao_versao_lista_telefonica_261020_botao`.
        # (29/10) ordem alfabetica dos 3 grupos de telefone nasce no codigo
        # (`leitura_csv.ler` ordena atendimento/externos/geral por `letra`)
        # + `_sem_acento` colapsa espacos internos (espaco duplo punha
        # Secretario antes de Almoxarifado). Ver
        # `migracao_versao_lista_telefonica_261029_ordem_alfabetica`.
        ("lista_telefonica", "1.0.261029"),
        # (04/10) avisos padronizados: as chamadas `ui.notify(...)` viraram
        # `notificar(..., tipo=...)` em Empenhos, Solicitação, Blog,
        # Edit PDF e Auditoria — o aviso passa pelo tema e pelo tempo
        # configurado em vez de ir direto ao NiceGUI com o padrão da
        # biblioteca. Ver a migração `migracao_versao_<chave>_261004`.
        ("auditoria", "1.0.261004"),
        # (29/10) resumos dos manuais semeados como "X — Como usar" no
        # primeiro boot + carrossel com todas as iniciais. Ver
        # `migracao_versao_blog_261029_posts_manuais`.
        # (01/11) `expirar_imagens_orfas` com `minutos=None` lê
        # `blog_imagem_expiracao_min` central (padrão 5). Ver
        # `migracao_versao_blog_261101_imagem_expiracao`.
        ("blog", "1.0.261101"),
        ("editar_pdf", "1.0.261004"),
        # (13/10) `_envia_email` (SMTP 15 s), `_processar` (`rodar_monitor`)
        # e `_processar_todos` (`renomear_manual` por pendente) viraram
        # `async` + `run.io_bound` com trava — antes travavam o event-loop e
        # derrubavam o websocket. Ver
        # `migracao_versao_empenhos_261013_io_bound`.
        ("empenhos", "1.0.261013"),
        ("solicita_impressao", "1.0.261004"),
        # (01-02/10) layout `src/` e entregas anteriores: o caminho do banco
        # mudou de `BASE_DIR` (que agora é `src/`) para `DIR_PROJETO` (a raiz
        # do repositório), e estes módulos já estavam em 261002 no banco.
        # Ver a migração `migracao_versao_<chave>_261002_layout_src`.
        # (20/10) botões "Atualizar" (`telas_administracao.py`) e "Fechar"
        # (`telas.py`, diálogo de prévia) pela fábrica central
        # `mod_tisosdocfly.ui_comum.botao`. Ver
        # `migracao_versao_tecnico_261020_botao`.
        ("tecnico", "1.0.261020"),
        # Última alteração de cada um, sem bump hoje (§4.2 só obriga bump de
        # quem muda). O seed declarava 260928 para `os` e não declarava nada
        # para `dados_abertos`: banco novo nascia atrasado — o defeito que a
        # migração `migracao_versao_pendentes_261003` corrige.
        # (20/10) botões "Retirar" (`telas_administracao.py`) e "Cancelar"
        # (`telas.py`, diálogo de atendimento) pela fábrica central
        # `mod_tisosdocfly.ui_comum.botao`. Ver
        # `migracao_versao_estoque_261020_botao`.
        ("estoque", "1.0.261020"),
        # (07/10) `hora_certa` — módulo NOVO (fonte da verdade da hora NTP.br,
        # relógio digital, IPs e espelho dos agendamentos por módulo). Ver
        # `migracao_versao_hora_certa_261007_nascimento`.
        # (08/10) padronização `CHAVE_MODULO`/`CHAVE` para "hora_certa" + stub
        # `sincronizar_no_boot` fail-soft via loguru. Ver
        # `migracao_versao_hora_certa_261008_chave`.
        # (24/10) grade responsiva dos espelhos (1/2/4 colunas), card de
        # backups compacto em grade interna, alturas equalizadas. Ver
        # `migracao_versao_hora_certa_261024_grade`.
        # (31/10) card Hora do servidor padronizado e fixo (sticky): hora
        # permanente no topo, data + dia da semana + calendario sincronizado
        # no tick, `data-testid=hc-card-hora/hc-dia-semana`. Ver
        # `migracao_versao_hora_certa_261031_relogio`.
        # (01/11) card único do Blog + card principal por módulo. Ver
        # `migracao_versao_hora_certa_261101_blog`.
        ("hora_certa", "1.0.261101"),
        # (12/10) `zap` — módulo NOVO (Fase 1: perfis + logs). Ver
        # `migracao_versao_zap_261012_nascimento`.
        # (17/10, mesmo dia) voz neural e áudio no WhatsApp. Ver
        # `migracao_versao_zap_261017_voz_audio`.
        # (18/10) trava de lançamento (uma operação de navegador por vez),
        # navegador por usuário e guarda de memória. Ver
        # `migracao_versao_zap_261018_trava`.
        # (20/10) botões "Salvar" e "Verificar conexão" pela fábrica
        # central `mod_tisosdocfly.ui_comum.botao`. Ver
        # `migracao_versao_zap_261020_botao`.
        ("zap", "1.0.261020"),
        # (16/10) `video` — módulo NOVO (baixar vídeos: YouTube, Facebook,
        # TikTok e outros via yt-dlp). Ver
        # `migracao_versao_video_261016_nascimento`.
        # (17/10) stage com expiração (10 min, configurável), biblioteca do
        # sistema (publicar, sem expiração, /midia_video), player, entrega
        # automática ao comum e ZIP em grupo. Ver
        # `migracao_versao_video_261017_biblioteca`.
        ("video", "1.0.261017"),
        # (07/10) `solicita_impressao` — `print` de erro virou loguru e os
        # `except Exception: pass` mudos (fallback fitz→pdfplumber e o
        # `init_db()` do import) passaram a registrar no log. Ver a migração
        # `migracao_versao_solicita_impressao_261007_descricao`.
        ("solicita_impressao", "1.0.261007"),
        # (07/10) `editar_pdf` — `print(...)` como relato de erro migrou para
        # loguru e os `except Exception: pass` mudos do `audit_log` passaram a
        # registrar no log. Ver a migração
        # `migracao_versao_editar_pdf_261007_descricao`.
        ("editar_pdf", "1.0.261007"),
    ):
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES (?, ?) "
                    "ON CONFLICT DO NOTHING",
                    (f"versao_modulo:{_chave_mod}", _ver))
    for chave, valor in PADRAO_CONFIG.items():
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES (?, ?) "
                    "ON CONFLICT DO NOTHING", (chave, valor))
    # Semente dos padrões do órgão (30/09/2026). Genéricos de propósito: o
    # administrador edita, desativa ou apaga em `validador_senha` pela tela de
    # administração. O que entra aqui é o que o servidor DAQUI monta senha —
    # o nome da instituição e o termo do serviço —, não dado de terceiros.
    for _pad, _desc in (
        ("prefeitura", "Nome da instituição"),
        ("municipio", "Nome do município"),
        ("cidade", "Como o município é chamado"),
        ("servidor", "Cargo de quem usa o sistema"),
        ("detran", "Órgão"),
        ("tributos", "Área de atendimento"),
        ("camara", "Órgão"),
    ):
        cur.execute("INSERT INTO tb_senha_padrao_organizacao (padrao, descricao, "
                    "tipo, ativo) VALUES (?, ?, 'palavra', 1) "
                    "ON CONFLICT DO NOTHING", (_pad, _desc))
    # Migração ÚNICA (06/09): cores padrão por módulo. O banco existente guardou
    # valores antigos/customizados semeados (tisosdocfly/`cor_principal` = #1565C0,
    # blog/editpdf/empenhos/solicita com cores soltas) que sobrescrevem os
    # padrões do PRÓPRIO módulo. Zeramos as chaves `<prefixo>_cor_botao` para que
    # cada módulo caia no `PADROES_TEMA` (blog #000000, empenhos #000000,
    # editar_pdf #000000, solicita_impressao #000000, demais #000000). Guardado
    # pelo marcador `migracao_cores_padrao` — roda UMA vez para não apagar
    # futuras personalizações do admin.
    cur.execute("SELECT COUNT(*) FROM tb_config WHERE chave='migracao_cores_padrao'")
    migrado = (cur.fetchone()[0] or 0) > 0
    if not migrado:
        cur.execute("UPDATE tb_config SET valor='#000000' "
                    "WHERE chave='cor_principal' AND valor='#1565C0'")
        for _chave in ("tisosdocfly", "usuarios", "auditoria", "blog",
                       "editpdf", "empenhos", "solicita_impressao"):
            cur.execute("UPDATE tb_config SET valor='' WHERE chave=?",
                        (f"{_chave}_cor_botao",))
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('migracao_cores_padrao', '1') ON CONFLICT DO NOTHING")
    # Migração ÚNICA (08/09): padronização geral — TODOS os módulos na cor do
    # tisosdocfly (PRETO #000000, via `PADROES_TEMA`) e versão sistema+módulos em
    # 1.0.260908. Zera as chaves de cor de botão dos módulos (caem no padrão do
    # próprio módulo, agora #000000) e atualiza as versões. Guardado pelo
    # marcador `migracao_padronizacao_260908` — roda UMA vez.
    cur.execute("SELECT COUNT(*) FROM tb_config WHERE chave='migracao_padronizacao_260908'")
    if (cur.fetchone()[0] or 0) == 0:
        for _chave in ("tisosdocfly", "usuarios", "auditoria", "blog",
                       "editpdf", "empenhos", "solicita_impressao"):
            cur.execute("UPDATE tb_config SET valor='' WHERE chave=?",
                        (f"{_chave}_cor_botao",))
        cur.execute("UPDATE tb_config SET valor='1.0.260908' "
                    "WHERE chave='versao_sistema'")
        cur.execute("UPDATE tb_config SET valor='1.0.260908' "
                    "WHERE chave LIKE 'versao_modulo:%'")
    cur.execute("INSERT INTO tb_config (chave, valor) "
                     "VALUES ('migracao_padronizacao_260908', '1') ON CONFLICT DO NOTHING")
    # Migração 260913 — solicita_impressao: seeds iniciais + bump de versão.
    #
    # ESTA LINHA ERA SOLTA (sem marcador) e é a razão de a versão deste módulo
    # não conseguir segurar um bump: rodava a CADA `init_db`, e o
    # `valor != '1.0.260913'` faz dela um REBAIXAMENTO — ela escrevia 13/09
    # por cima de qualquer versão mais nova. Foi assim que o bump de 30/09
    # apareceu como 1.0.260930 numa rodada e como 1.0.260913 na seguinte.
    # A §4.2 é explícita: migração tem de ser idempotente e não pode
    # sobrescrever versão que já evoluiu (ou que o admin tenha mexido).
    # Agora tem marcador próprio e só cria a linha quando ela NÃO existe
    # (`ON CONFLICT DO NOTHING`) — nunca rebaixa, e quem vier depois (o bump
    # de 30/09, mais abaixo) tem a palavra final.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_solicita_impressao_260913'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:solicita_impressao', '1.0.260913') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_solicita_impressao_260913', '1') "
                    "ON CONFLICT DO NOTHING")
    # Migração 13/09/2026 — bump versão do módulo empenhos (padrão PIC + contagem padronizada + CSS docs)
    cur.execute("SELECT COUNT(*) FROM tb_config WHERE chave='migracao_versao_empenhos_260913'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("UPDATE tb_config SET valor='1.0.260913' WHERE chave='versao_modulo:empenhos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES ('migracao_versao_empenhos_260913', '1') ON CONFLICT DO NOTHING")
    # Migração 13/09/2026 — bump versão tisosdocfly/sistema (contagem padronizada + PIC + CSS docs)

    cur.execute("SELECT COUNT(*) FROM tb_config WHERE chave='migracao_versao_tisosdocfly_260913'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("UPDATE tb_config SET valor='1.0.260913' WHERE chave='versao_sistema'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES ('versao_sistema', '1.0.260913') ON CONFLICT DO NOTHING")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES ('versao_modulo:tisosdocfly', '1.0.260913') ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260913' WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES ('migracao_versao_tisosdocfly_260913', '1') ON CONFLICT DO NOTHING")
    # Migração 18/09/2026 — bump versão do módulo usuarios (acesso padrão
    # comum em editar_pdf/empenhos/solicita_impressao, nova ordem dos
    # módulos, blog indesativável, senha provisória 123456 no cadastro)
    cur.execute("SELECT COUNT(*) FROM tb_config WHERE chave='migracao_versao_usuarios_260918'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("UPDATE tb_config SET valor='1.0.260918' WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES ('migracao_versao_usuarios_260918', '1') ON CONFLICT DO NOTHING")
    # Migração 28/09/2026 — VERSÃO DOS MÓDULOS QUE ESTAVAM SEM VERSÃO.
    # Seis chaves de `MODULOS_BD` (repositorio.py) nunca chegaram ao tuple de
    # seed acima, então não tinham `versao_modulo:<chave>` em `tb_config`. Sem a
    # chave, `_obter_versao_modulo` (telas.py) devolve '1.0' e o rodapé mostra
    # `v<versao_sistema> · v1.0` — sem distinguir o código de hoje do de amanhã.
    #   os/estoque      — nasceram no commit 9a7d57d (28/09) sem linha de seed.
    #   agregador_noticias/lista_telefonica/filas/tecnico — débito anterior,
    #                     entraram em MODULOS_BD antes de o tuple existir.
    # `INSERT OR IGNORE` com um `UPDATE` só onde ainda é PLACEHOLDER.
    #
    # POR QUE A LISTA DE PLACEHOLDERS INCLUI '1.0.260908' — a ordem das
    # migrações importa e é fácil errar aqui: num banco NOVO, o seed acima grava
    # 1.0.260928 e a migração `migracao_padronizacao_260908` (mais acima, neste
    # mesmo `init_db`) roda `UPDATE ... WHERE chave LIKE 'versao_modulo:%'`,
    # rebaixando TUDO para 1.0.260908. Sem esta linha no filtro, a correção
    # nunca entraria numa instalação nova: o `INSERT` não faz nada (a chave já
    # existe) e o `UPDATE` não casa com 1.0.260908. O que NÃO entra é uma
    # versão que já evoluiu para outra data — essa é bump futuro, e bump
    # futuro não é da conta desta migração.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_pendentes_260928'")
    if (cur.fetchone()[0] or 0) == 0:
        for _chave_mod in ("agregador_noticias", "lista_telefonica", "filas",
                           "tecnico", "os", "estoque"):
            cur.execute("INSERT INTO tb_config (chave, valor) VALUES (?, '1.0.260928') "
                        "ON CONFLICT DO NOTHING",
                        (f"versao_modulo:{_chave_mod}",))
            cur.execute("UPDATE tb_config SET valor='1.0.260928' "
                        "WHERE chave=? AND (valor IS NULL OR valor='' "
                        "OR valor IN ('1.0', '1.0.260908'))",
                        (f"versao_modulo:{_chave_mod}",))
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('migracao_versao_pendentes_260928', '1') ON CONFLICT DO NOTHING")
    # Bumps de 29/09/2026 — DIÁLOGO DE FORMULÁRIO RESPONSIVO (AGENTS.md §4.2:
    # toda alteração de código obriga a atualizar a versão do módulo).
    #   mod_tisosdocfly        — base `dialogo_formulario` /
    #                         `LARGURA_DIALOGO_FORMULARIO` / `CSS_GRADE_*` em
    #                         `ui_comum`, e os diálogos de Meu Perfil, Troca de
    #                         senha e Seus telefones em `telas.py`
    #   mod_gest_cad_usuario — diálogos Novo usuário, Editar, Duplicar e Sessões
    #   mod_estoque         — 11 diálogos de movimentação/ajuste
    #   mod_lista_telefonica — diálogos Novo contato, Nova unidade e Reordenar
    #   mod_tecnico         — diálogo de listagem de arquivos
    #
    # Bump do `usuarios` em 30/09/2026 — PRIMEIRA CARGA DA FOLHA NO BOOT.
    # `mod_tisosdocfly/bd_criador.py` passou a chamar `carga_automatica()` logo
    # depois do `init_users()`, para que o cadastro de servidores nasça junto
    # com o banco em vez de ficar vazio até o agendador das 03:00. Marcador
    # PRÓPRIO (`carga_folha`), e não um dos de hoje, porque este é um desenho
    # novo — inicializador, não agendador — e a §4.2 exige um bump rastreável
    # por alteração, não por dia.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_260930_carga_folha'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.260930') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260930' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_260930_carga_folha', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `usuarios` em 01/10/2026 — COLETA COM INTERVALO VARIÁVEL.
    # O intervalo fixo de 1,2 s virou espera sorteada na faixa 1 s–5 s, e a
    # `fonte_folha.json` passou a `origem: "csv"`: a folha é coletada UMA vez
    # para `dados/`, e a carga passa a ler o arquivo local — medido 0,02 s para
    # 1.165 servidores, contra ~88 s de coleta pela rede. É a decisão que tira
    # o boot e as 03:00 da dependência do servidor de terceiro.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261001_intervalo_csv'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261001') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261001' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261001_intervalo_csv', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `usuarios` em 01/10/2026 — COLETA QUE NÃO MORRIA MAIS.
    # A coleta da folha parava por volta da página 20 (425 a 525 servidores) e
    # não deixava arquivo nenhum. Duas causas, ambas em `coleta_folha.py`:
    # o retry do `_post` cobria só `URLError`/`TimeoutError`/`ValueError`, e o
    # portal responde ao excesso derrubando a conexão — `RemoteDisconnected`,
    # que é `OSError` —, então a exceção subia e matava o processo; e o
    # parcial era só memória, então a falha levava a folha toda junto. Agora o
    # retry cobre a família de erro de conexão, o backoff é 3/8/20/45 s com
    # pausa de 30 s quando a conexão cai, e o parcial é gravado a cada página.
    # Medido: 1.165 servidores da competência 08/2026, do primeiro ao último.
    # Bump do `usuarios` em 01/10/2026 — COLETOR QUE CONFIA NO PORTAL.
    # `coletar_folha_simples.py` nasce da leitura do portal ao vivo, e corrige
    # o defeito que a versão anterior escondia: ela ignorava `recordsFiltered`
    # (o total que o portal ANUNCA em toda resposta) e tratava "página vazia"
    # como fim da folha. Com o portal limitando, isso gravava 650 de 1165 e
    # imprimia "650 servidores" como se fosse a folha completa. Agora a página
    # vazia só encerra quando `inicio >= total`, folha incompleta não é gravada,
    # e o total é conferido antes de escrever. Medido no portal: 1.165
    # servidores na competência 08/2026, `length` travado em 25, 47 páginas.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261001_coleta_total'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261001') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261001' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261001_coleta_total', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261001_coleta_resiliente'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261001') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261001' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261001_coleta_resiliente', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `auditoria` em 01/10/2026 — CONEXÃO DE GRAVAÇÃO REUTILIZADA.
    # `registrar_auditoria` abria uma conexão nova do banco de auditoria a cada
    # registro (mais dois PRAGMA). Medido: **280 ms -> 2,4 ms** por registro, e
    # a carga da folha — que audita ~3 vezes por servidor — saiu de ~30 min
    # para minutos. A correção é uma conexão privada por thread, e NÃO um cache
    # em `get_auditoria_connection`, porque o contrato dela é "a chamada é dona
    # da conexão e pode fechá-la" (e há quem feche).
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_auditoria_261001_conexao_gravacao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:auditoria', '1.0.261001') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261001' "
                    "WHERE chave='versao_modulo:auditoria'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_auditoria_261001_conexao_gravacao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `tisosdocfly` em 01/10/2026 — a MENSAGEM da primeira carga da folha
    # dizia "~2 min" onde o medido é ~25–35 min. Parece comentário, mas é a
    # linha que alguém lê no console enquanto espera o servidor subir, e um
    # número errado ali faz o administrador achar que o boot travou e matar
    # o processo. A §4.2 não faz exceção para texto, então o bump vem junto.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261001_tempo_carga_folha'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261001') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261001' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261001_tempo_carga_folha', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `tisosdocfly` em 01/10/2026 — VIGIA DO SERVIDOR (arquivo novo).
    # `mod_tisosdocfly/vigia_servidor.py`: observa a porta 8080 e reinicia o
    # servidor se ela ficar muda. Não mata processo nenhum — um laço que
    # também "enferruja" processos transforma uma sondagem ruim em queda.
    # Mesma data do bump de cima, então a versão não muda de número; o
    # marcador é que torna a alteração rastreável.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261001_vigia_servidor'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261001') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261001' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261001_vigia_servidor', '1') "
                    "ON CONFLICT DO NOTHING")

    # POR QUE ESCRETO LITERAL E NÃO UM `for` COM f-string
    #     O marcador `migracao_versao_<chave>_<data>` é o que faz a §4.2
    #     verificável: é nele que o `teste_versionamento_modulo.py` procura para
    #     dizer "este módulo foi alterado e não ganhou bump". Numa f-string o
    #     código-fonte tem `{_chave_mod}` e não `tisosdocfly` — o marcador some da
    #     leitura estática, tanto para o teste quanto para quem lê o diff. Por
    #     isso os cinco blocos são escritos um a um, como já fazia
    #     `migracao_versao_usuarios_260918`. É verbosidade deliberada: um bump
    #     que não dá para ler não é rastreável.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_260929'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:tisosdocfly', '1.0.260929') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260929' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_260929', '1') ON CONFLICT DO NOTHING")

    # Bump do `usuarios` pela CORREÇÃO DE SEGURANÇA de 29/09/2026 (2ª do dia,
    # com marcador próprio — a de cima foi do `dialogo_formulario`).
    # `mod_gest_cad_usuario`: o seed de `master` voltava em todo reinício
    # depois da troca de credenciais; agora ele respeita a marca
    # `forcar_troca_credenciais:master`. O `bd_criador.py` legado, que tinha um
    # SEGUNDO `INSERT` de `master/master` sem essa marca, passou a levantar.
    # Bump do `usuarios` em 30/09/2026, marcador próprio: `bd_manipulador.py`
    # ganhou `tb_login_tentativas` e as funções de contagem do atraso
    # progressivo de login. O módulo do cadastro de usuários é o dono do login,
    # então a tabela mora no banco DELE, e não no central.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_260930_tentativas_login'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.260930') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260930' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_260930_tentativas_login', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_260929_seg'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:usuarios', '1.0.260929') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260929' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_260929_seg', '1') ON CONFLICT DO NOTHING")

    # Bump do `agregador_noticias` pela correção da EXIBIÇÃO de 29/09/2026.
    # A contagem de páginas era feita sobre o total cru (349) enquanto a fatia
    # vinha da amostra de 1 por tema (9 elementos): as páginas 2..30 saíam
    # vazias e caíam no cartão de "nenhuma notícia". Agora a contagem e a fatia
    # saem da MESMA lista, a página 1 continua sendo a amostra por tema e as
    # seguintes mostram o resto. Junto: tamanho de página configurável
    # (múltiplo de 3, mínimo 9, padrão 12) e os dois textos da tela — cabeçalho
    # e aviso de "sem novidade" — tirados do código e agora configuráveis,
    # vazios por padrão.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_agregador_noticias_260929'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:agregador_noticias', '1.0.260929') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260929' "
                    "WHERE chave='versao_modulo:agregador_noticias'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_agregador_noticias_260929', '1') "
                    "ON CONFLICT DO NOTHING")

    # Segundo bump do `agregador_noticias` em 29/09/2026, com marcador
    # próprio: quantas notícias EU VOU LER virou escolha de quem lê.
    #   • saiu do painel admin (que é do administrador) para a barra da tela
    #     de notícias, visível a qualquer perfil, inclusive `comum`;
    #   • gravada em COOKIE do navegador (`noticias_por_pagina`), mesmo
    #     padrão do `estilo_visual` — é leitura de uma pessoa, não dado do
    #     sistema. Lida UMA VEZ no corpo da página, porque o timer redesenha
    #     a grade sem request e releria o padrão do módulo por baixo;
    #   • a amostra por tema virou ORDEM DE PRIORIDADE no topo, não o
    #     conteúdo da página 1 — antes o slider prometia 63 e a tela mostrava
    #     8, porque a primeira página era só a amostra;
    #   • o tooltip do controle ficou "Quantas notícias por página".
    # A coleta automática e o botão "Coletar agora" (só administrador) não
    # mudaram: quem só lê não dispara coleta.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_agregador_noticias_260929_leitura'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:agregador_noticias', '1.0.260929') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260929' "
                    "WHERE chave='versao_modulo:agregador_noticias'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_agregador_noticias_260929_leitura', '1') "
                    "ON CONFLICT DO NOTHING")

    # Terceiro bump do `agregador_noticias`, agora em 30/09/2026, com marcador
    # próprio: o slider de "Por página" finalmente GRAVA.
    #
    # Ele gravava o cookie (a rota funcionava), mas arrastar o trilho não
    # mudava nada, por DUAS falhas encadeadas no mesmo controle:
    #   1. o `change` do Quasar chegava ao handler como
    #      `GenericEventArguments`, que não tem `.value` — o handler estourava
    #      ali, ANTES de gravar (`AttributeError` no log do servidor);
    #   2. trocado por `on_value_change` + atraso de 0,8s (que segura o
    #      arrasto e grava uma vez ao soltar o cursor), a chamada final
    #      passou `force_load=True`, que NÃO EXISTE nesta versão do NiceGUI —
    #      a assinatura é `to(target, new_tab=False)`, e o `TypeError`
    #      impedia a navegação para a rota do cookie.
    # Nenhuma das duas aparecia testando a rota direto pela URL: as duas só
    # nascem na interação real com o trilho.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_agregador_noticias_260930_slider'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:agregador_noticias', '1.0.260930') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260930' "
                    "WHERE chave='versao_modulo:agregador_noticias'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_agregador_noticias_260930_slider', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `tisosdocfly` em 30/09/2026, com marcador próprio. O que mudou foi
    # `telas.py`: a troca de senha obrigatória das CONTAS DE TESTE
    # (`qacomum`/`qamaster`, senha `123456` — AGENTS.md §8.2) nasce
    # PRÉ-PREENCHIDA, para a troca virar um clique em vez de digitação de uma
    # senha que já se publica no §8.2. Mesmo espírito do diálogo de
    # credenciais do `master`, que já nasce preenchido.
    #
    # `tisosdocfly` não tem linha no tuple de seed de cima (linhas 171-188): a
    # chave nasce na migração `migracao_versao_tisosdocfly_260913` e é daqui para
    # frente que a cadeia 260913 -> 260929 -> 260930 a entrega. Banco novo sai
    # certo pela própria cadeia, banco em uso por este marcador.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_260930'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:tisosdocfly', '1.0.260930') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260930' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_260930', '1') ON CONFLICT DO NOTHING")

    # Bump do `tisosdocfly` em 30/09/2026, marcador próprio. Entrou
    # `validador_senha.py`: verificação de força e de vazamento na troca de
    # senha. O requisito que mandou no desenho foi rede local — o sistema não
    # pode travar quando não há internet, tem que ignorar. Daí a separação:
    # o caminho que BLOQUEIA é só o offline (entropia, teclado, sequência,
    # padrões do órgão) e a camada de vazamento é sondada, tem tempo máximo
    # próprio, não faz retry e falha para "indisponível" em vez de travar.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_260930_validador_senha'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.260930') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260930' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_260930_validador_senha', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `tisosdocfly` em 30/09/2026, marcador próprio. Mesmo dia, outra
    # alteração: o diálogo de troca obrigatória ganhou título e boas-vindas no
    # TOPO, e a cor do botão passou a seguir o estilo escolhido pela pessoa.
    # `Dialogo` ganhou `sem_separador` e `dialogo_formulario` ganhou o mesmo
    # parâmetro, para o título nascer no cabeçalho do cartão em vez de depois
    # da coluna rolável; e o seletor de `--q-primary` passou a cobrir o portal
    # do modal (`.q-dialog`), que vive fora do `.q-layout`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_260930_dialogo_topo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.260930') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260930' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_260930_dialogo_topo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `tisosdocfly` em 30/09/2026, marcador próprio. Mesmo dia, terceira
    # alteração. A troca obrigatória PAROU de ser decorativa: o diálogo era um
    # modal sobre a página já montada (`_montar_layout` rodava antes, e
    # `pagina_restrita` devolvia o usuário, então o chamador desenhava a tela
    # inteira), e `persistent` só impedia fechar o modal — não impedia navegar.
    # Quem não quisesse trocar a senha clicava em "voltar" e navegava. Agora o
    # guard fica no servidor: enquanto houver pendência, a página não é montada
    # e a pessoa vai para a tela solta `/troca-obrigatoria`, sem menu. E essa
    # tela ganhou "Sair", que encerra a sessão de verdade para o caso de
    # máquina compartilhada.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_260930_troca_bloqueada'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.260930') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260930' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_260930_troca_bloqueada', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `tisosdocfly` em 30/09/2026, marcador próprio. Mesmo dia, sexta
    # alteração. MEDIDOR DE DIFICULDADE na troca de senha + ACEITE DE RISCO
    # (checkbox e confirmação dupla com o texto da LGPD) + TENTATIVAS DE LOGIN
    # por atraso progressivo, sem bloquear a conta.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_260930_politica_senha'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.260930') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260930' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_260930_politica_senha', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `tisosdocfly` em 30/09/2026, marcador próprio. Mesmo dia, quinta
    # alteração: A COR DE TODOS OS BOTÕES passou a ser a mesma para todos: a
    # pessoa escolhe o estilo e ele vale em toda a tela. A causa era o botão
    # padronizado escrever `background-color` INLINE com a cor do módulo —
    # e estilo inline vence CSS, então nenhuma custom property chegava nele.
    # Agora `preview_estilos.aplicar_no_botao` escreve a cor do estilo escolhido
    # por último, depois do `.style()` da fábrica.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_260930_cor_unica_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.260930') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260930' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_260930_cor_unica_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `usuarios` em 30/09/2026, marcador próprio. O código deste módulo
    # mudou no mesmo dia, pela MESMA alteração que o do `tisosdocfly`: tirou da
    # tela as 13 cores de MARCA chumbadas das chamadas de botão (`teal-8`,
    # `green-8`, `orange-9`, `primary`, `indigo-8`, `red-8`, `amber-8`,
    # `deep-purple-8`) e deixou a cor do estilo escolhido chegar em todo botão.
    # As cores de ESTADO (`negative`, `warning`, `grey-*`) ficaram: o vermelho
    # de "excluir" é vermelho em qualquer estilo.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_260930_cor_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.260930') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260930' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_260930_cor_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `empenhos` em 30/09/2026, marcador próprio. Mesmo motivo, mudou
    # uma chamada só: "Cancelar ZIP" estava com `cor="orange-9"` — laranja de
    # marca, para uma ação que não é estado nem alerta.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_empenhos_260930_cor_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:empenhos', '1.0.260930') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260930' "
                    "WHERE chave='versao_modulo:empenhos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_empenhos_260930_cor_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `solicita_impressao` em 30/09/2026, marcador próprio. Mesmo
    # motivo, 4 chamadas: "Reenviar", "Autorizar" (em duas telas) e
    # "Confirmar impressão", com `cor="primary"`/`cor="green-8"`. Este módulo
    # é a exceção da §4.2 — a versão dele mora na PRÓPRIA
    # `tb_configuracoes_modulo`; a migração de hoje escreve a central, que é a
    # que o rodapé lê, e a exceção segue de pé para quem mexer nele.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_solicita_impressao_260930_cor_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:solicita_impressao', '1.0.260930') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260930' "
                    "WHERE chave='versao_modulo:solicita_impressao'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_solicita_impressao_260930_cor_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `tisosdocfly` em 30/09/2026, marcador próprio. Mesmo dia, quarta
    # alteração. Saiu da tela a referência interna que tinha vazado para o
    # usuário: o rótulo de veredito dizia "Conta de teste do AGENTS.md 8.2",
    # que é jargão de quem escreve o código, lido por servidor no balcão. A
    # isomorphicidade com a camada de bloqueio fica no código e em
    # `docs/modulos/tisosdocfly.md`; na tela, nada. E a situação da consulta
    # (`sem_internet`, `limite_requisicoes`) passou a ser traduzida por
    # `_SITUACAO_PT_BR` em vez de expor o identificador cru.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_260930_texto_pela_tela'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.260930') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260930' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_260930_texto_pela_tela', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_260929'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:usuarios', '1.0.260929') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260929' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_260929', '1') ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_estoque_260929'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:estoque', '1.0.260929') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260929' "
                    "WHERE chave='versao_modulo:estoque'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_estoque_260929', '1') ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_260929'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:lista_telefonica', '1.0.260929') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260929' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_260929', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tecnico_260929'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:tecnico', '1.0.260929') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260929' "
                    "WHERE chave='versao_modulo:tecnico'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tecnico_260929', '1') ON CONFLICT DO NOTHING")
    # A versão do SISTEMA também anda quando o núcleo muda: o aviso de
    # primeiro boot e a própria base de diálogos ficam em `mod_tisosdocfly`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_sistema_260929'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_sistema', '1.0.260929') ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.260929' "
                    "WHERE chave='versao_sistema'")
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('migracao_versao_sistema_260929', '1') ON CONFLICT DO NOTHING")
    # Migração ÚNICA (27/09/2026) — TEMA WHATSAPP como padrão do SISTEMA INTEIRO,
    # escolhido pelo responsável. Antes os 11 módulos usavam preto (#000000).
    # O que ela grava:
    #   cor_principal -> teal da marca (#075E54): é o que `_montar_layout` joga
    #     em `ui.colors(primary=)`, e portanto a cor do cabeçalho e de TODOS os
    #     elementos `bg-primary` de qualquer módulo.
    #   cor_fundo -> bege quente (#EAE6DF), o papel de parede do app.
    #   <prefixo>_cor_botao e <prefixo>_cor_titulo -> VAZIO, de propósito: é o
    #     que faz cada módulo cair no `PADROES_TEMA` (verde teal do botão e
    #     ardósia do título). Zerar em vez de gravar o valor é o que mantém
    #     esta aplicação em UM lugar só — trocar a paleta depois é editar o
    #     `PADROES_TEMA`, sem nova migração.
    #   <prefixo>_cor_fundo_card -> branco (#FFFFFF), o cartão sobre o fundo.
    # Guardada pelo marcador, então roda UMA vez e não apaga personalização
    # posterior do admin. SQL portátil: o proxy `_CursorPostgres` traduz.
    cur.execute("SELECT COUNT(*) FROM tb_config WHERE chave='migracao_tema_whatsapp_260927'")
    if (cur.fetchone()[0] or 0) == 0:
        for _chave, _valor in (("cor_principal", "#075E54"),
                               ("cor_fundo", "#EAE6DF"),
                               # Padrão de estilo do ADMINISTRADOR: o que vale
                               # para quem não fez escolha pessoal no navegador
                               # (cookie `estilo_visual` vazio ou `padrao`).
                               ("estilo_visual_padrao_sistema", "verde")):
            cur.execute("INSERT INTO tb_config (chave, valor) VALUES (?, ?) "
                        "ON CONFLICT DO NOTHING", (_chave, _valor))
            cur.execute("UPDATE tb_config SET valor=? WHERE chave=?",
                        (_valor, _chave))
        for _p in ("tisosdocfly", "blog", "usuarios", "auditoria", "editpdf",
                   "empenhos", "solicita_impressao", "tecnico", "filas",
                   "lista_telefonica", "agregador_noticias"):
            for _campo in ("cor_botao", "cor_titulo", "cor_texto_card",
                           "texto_header", "cor_fundo"):
                cur.execute("INSERT INTO tb_config (chave, valor) VALUES (?, '') "
                            "ON CONFLICT DO NOTHING", (f"{_p}_{_campo}",))
                cur.execute("UPDATE tb_config SET valor='' WHERE chave=?",
                            (f"{_p}_{_campo}",))
            for _campo in ("cor_fundo_card", "cor_texto_botao"):
                cur.execute("INSERT INTO tb_config (chave, valor) VALUES (?, '#FFFFFF') "
                            "ON CONFLICT DO NOTHING", (f"{_p}_{_campo}",))
                cur.execute("UPDATE tb_config SET valor='#FFFFFF' WHERE chave=?",
                            (f"{_p}_{_campo}",))
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('migracao_tema_whatsapp_260927', '1') ON CONFLICT DO NOTHING")
    # Migração ÚNICA (27/09/2026, 2ª rodada) — o menu de estilo visual entrou e
    # com ele a decisão de que o "Padrão" NÃO é uma cor do sistema, e sim a cor
    # que cada ADMINISTRADOR configurou para o seu módulo. Esta migração
    # desfaz o que a de cima fez:
    #   cor_principal/cor_fundo voltam ao preto/cinza de antes;
    #   as chaves por módulo continuam vazias, cair no PADROES_TEMA (preto);
    #   estilo_visual_padrao_sistema é SEMEADA com 'padrao' — a de cima tentou
    #   semear, mas o marcador já estava gravado quando ela rodou, então a
    #   linha nunca existiu e a chave ficava ausente para sempre.
    # O estilo "verde" (WhatsApp) continua existindo, agora como OPÇÃO do menu.
    cur.execute("SELECT COUNT(*) FROM tb_config WHERE chave='migracao_padrao_por_modulo_260927'")
    if (cur.fetchone()[0] or 0) == 0:
        for _chave, _valor in (("cor_principal", "#000000"),
                               ("cor_fundo", "#EEEEEE"),
                               ("estilo_visual_padrao_sistema", "padrao")):
            cur.execute("INSERT INTO tb_config (chave, valor) VALUES (?, ?) "
                        "ON CONFLICT DO NOTHING", (_chave, _valor))
            cur.execute("UPDATE tb_config SET valor=? WHERE chave=?",
                        (_valor, _chave))
        for _p in ("tisosdocfly", "blog", "usuarios", "auditoria", "editpdf",
                   "empenhos", "solicita_impressao", "tecnico", "filas",
                   "lista_telefonica", "agregador_noticias"):
            for _campo in ("cor_botao", "cor_titulo"):
                cur.execute("INSERT INTO tb_config (chave, valor) VALUES (?, '') "
                            "ON CONFLICT DO NOTHING", (f"{_p}_{_campo}",))
                cur.execute("UPDATE tb_config SET valor='' WHERE chave=?",
                            (f"{_p}_{_campo}",))
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('migracao_padrao_por_modulo_260927', '1') ON CONFLICT DO NOTHING")
    # Migração 06/10/2026 — o VERDE vira o padrão do sistema, e a chave que
    # guarda isso sai de morta.
    #
    # A chave `estilo_visual_padrao_sistema` foi criada em 27/09/2026 e
    # sobrescrita com 'padrao' pela migração de cima — e nunca foi lida por
    # NENHUM código. `ler_estilo()` tratava "sem cookie" e "padrao" como a mesma
    # coisa, e essa coisa era a cor do administrador. Consequência: quem abria o
    # sistema pela primeira vez nunca via o verde de entrega, e era salvo se o
    # administrador tivesse configurado aquela cor.
    #
    # Agora são três camadas resolvidas em `preview_estilos.ler_estilo()`:
    # escolha pessoal (cookie) > "Padrão" (cor do admin do módulo) > padrão do
    # sistema (esta chave). O responsável pediu o verde como padrão de todos,
    # mantendo "Padrão" como a cor que cada administrador define no seu módulo.
    #
    # A chave NÃO é sobrescrita à força quando o administrador já a mexeu: quem
    # mudou de propósito continua com o valor escolhido. Só entra o 'verde'
    # quando ela está ausente ou ainda vale 'padrao' — que é o valor herdado
    # da migração de 27/09 e significa "ninguém configurou nada ainda".
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261006_padrao_verde'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES (?, 'verde') "
                    "ON CONFLICT DO NOTHING",
                    ("estilo_visual_padrao_sistema",))
        # Só quando está ausente ou no 'padrao' herdado: um 'azul' que o
        # administrador pôs é decisão dele e fica.
        cur.execute("UPDATE tb_config SET valor='verde' "
                    "WHERE chave='estilo_visual_padrao_sistema' "
                    "AND (valor IS NULL OR TRIM(valor)='' OR valor='padrao')")
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:tisosdocfly', '1.0.261006') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261006' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261006_padrao_verde', '1') "
                    "ON CONFLICT DO NOTHING")
    # Migração 06/10/2026 — TODO servidor da folha nasce bloqueado e só entra
    # depois de passar pelo DTI. Bump do módulo `usuarios`.
    #
    # As COLUNAS são criadas pelo `init_db` do próprio
    # `mod_gest_cad_usuario` (check-then-add em `_init_db_seguro`), porque
    # `tb_usuarios` é o banco DELE e não o central — esta migração cuida só
    # da versão, como manda o §4.2.
    #
    # O dado NÃO é reescrito aqui de propósito: quem fecha as 1.076 contas é
    # a carga da folha, e ela roda no boot com o sistema no ar. Uma migração
    # que fizesse `UPDATE ... SET user_ativo=0` deixaria as contas fechadas
    # mesmo com a folha quebrada, e o DTI ficaria sem a lista do que revisar.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261006_liberacao_dti'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:usuarios', '1.0.261006') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261006' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261006_liberacao_dti', '1') "
                    "ON CONFLICT DO NOTHING")
    # Migração 06/10/2026 — lista telefônica abre no CSV (`leitura_csv`),
    # com a grade em `@container` e o CSV promovido a UTF-8 canônico.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261006_csv_utf8'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:lista_telefonica', '1.0.261006') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261006' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261006_csv_utf8', '1') "
                    "ON CONFLICT DO NOTHING")
    # Seed do contador de acessos (se ainda não existir) + data inicial da contagem
    try:
        cur.execute("SELECT valor FROM tb_config WHERE chave='contador_acessos_inicio'")
        row = cur.fetchone()
        if not row or not (row[0] or "").strip():
            import datetime as _dt
            hoje = _dt.datetime.now().strftime("%Y-%m-%d")
            cur.execute("INSERT INTO tb_config (chave, valor) VALUES ('contador_acessos_inicio', ?) ON CONFLICT DO NOTHING", (hoje,))
            cur.execute("UPDATE tb_config SET valor=? WHERE chave='contador_acessos_inicio' AND (valor IS NULL OR valor='')", (hoje,))
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES ('contador_acessos_total', '0') ON CONFLICT DO NOTHING")
    except Exception:
        pass
    # POR QUE ESTE BLOCO VAI NO FIM, E NÃO COM OS OUTROS BUMPS (01/10/2026)
    #
    # Descobriram-se dois defeitos ao rodar o boot de um banco NOVO:
    #
    # 1. **Um bump no meio da lista é apagado pelo que vem depois.** As
    #    migrações antigas deste arquivo (260929/260930) fazem
    #    `INSERT ... ON CONFLICT DO NOTHING` seguido de `UPDATE` INCONDICIONAL.
    #    Num banco novo, o marcador delas ainda não existe, então elas rodam
    #    depois e sobrescrevem a versão que o bump de hoje gravou. O sintoma é
    #    `versao_modulo:tisosdocfly` valendo 1.0.260930 num banco criado hoje, com
    #    o marcador `..._261001_dados_abertos` gravado como se o bump tivesse
    #    acontecido. Num banco JÁ existente o defeito não aparece (os
    #    marcadores antigos existem e pulam) — que é por que ele passou
    #    despercebido: só a instalação nova via.
    #
    # 2. **O mesmo bug já atingia os bumps de 261001 anteriores**
    #    (`tempo_carga_folha`, `vigia_servidor`), que estão no meio do arquivo.
    #    Eles foram corrigidos de fato pela migração de hoje, que é a última a
    #    falar do `tisosdocfly`.
    #
    # A REGRA que daqui para frente: **bump de versão fica no FIM da sequência
    # de migrações**, imediatamente antes do `commit`. Assim o número de hoje
    # é o último a escrever, tanto no banco novo quanto no banco em uso.
    # Nenhuma migração de versão ANTERIOR pode estar abaixo deste ponto.
    #
    # São cinco módulos tocados, e a §4.2 exige um marcador PRÓPRIO para cada um.
    #
    #   tisosdocfly           — `bd_criador.py` (init do módulo novo + folha lida em
    #                        TODO boot), `autenticacao.py` (MODULOS_SISTEMA),
    #                        `tema_modulo.py` (prefixo e padrão), `repositorio.py`
    #                        (MODULOS_BD) e `integracoes.py` (10ª função da
    #                        fachada: `folha_de_servidores_publica`)
    #   dados_abertos      — módulo NOVO (bd_manipulador/telas/telas_administracao)
    #   usuarios           — `carga_folha.py`: leitor público da folha
    #                        (`folha_arquivo_atual`) e o relatório que agora diz
    #                        o que MUDOU (nomes corrigidos, vínculos, salários,
    #                        inalterados) — sem isso o log do boot respondia
    #                        "criados 0, bloqueados 0" numa folha em que 40
    #                        salários tinham mudado
    #   lista_telefonica   — `tb_unidade.origem`: distingue unidade que veio da
    #                        folha de unidade que o ADMINISTRADOR cadastrou, para
    #                        que a sincronização deixe de desligar a unidade
    #                        manual que o administrador acabou de criar
    #   solicita_impressao — SEM bump: nada foi alterado nele. Ele já consumia a
    #                        hierarquia pela fachada
    #                        (`integracoes.listar_unidades_organograma`) e continua
    #                        consumindo; a garantia de que respeita a lista
    #                        telefônica é a regra, não uma linha nova daqui.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261001_dados_abertos'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261001') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261001' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261001_dados_abertos', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261001_nascimento'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261001') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261001' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261001_nascimento', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261001_folha_todo_boot'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261001') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261001' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261001_folha_todo_boot', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `usuarios` em 01/10/2026 — SENHA PROVISÓRIA SEMPRE ASSIMILADA
    # (o seu teste em uso, 14:26).
    #
    # O que foi encontrado: com as 653 contas criadas, NENHUMA tinha
    # `forcar_troca:<nome>` = '1'. 652 delas seguiam com a senha `123456`.
    # O AGENTS.md §8.2 documenta troca forçada no 1º acesso para `qacomum` e
    # `qamaster` — a documentação estava certa e o código não.
    #
    # A causa foi dupla:
    #   1. `marcar_trocar_senha` só rodava na CRIAÇÃO da conta. Uma conta que
    #      já existia passava pelo caminho de reconciliação — que reconcilia
    #      os ACESSOS e nunca a senha — e entrava sem troca obrigatória. É o
    #      caso de qualquer instalação recriada de backup, restaurada, ou que
    #      perdeu o banco central (que foi o que aconteceu às 14:26: as chaves
    #      `forcar_troca:*` vivem em `db_mod_tisosdocfly.db` e foram com ele).
    #   2. As 650 contas da folha já nascem marcadas (`criar_usuario`), então o
    #      número "0 pendentes" no caso real veio do item 1 e da perda do banco
    #      central, e não da carga.
    #
    # A correção (em `mod_gest_cad_usuario/bd_manipulador.py`) é
    # `_assegurar_troca_de_senha_provisoria`, chamada na reconciliação do
    # seed: confere o **hash** e reassina a troca só enquanto a senha ainda for
    # a provisória. Quem já trocou tem a flag em '0' e não é tocado — por isso
    # a conferência é pelo hash, e não pela ausência da chave.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261001_troca_provisoria'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261001') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261001' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261001_troca_provisoria', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `usuarios` em 01/10/2026 — COLETOR QUE JUNTA AS DUAS PARTES.
    #
    # Os dois coletores que existiam pecam em complementos opostos, e nenhum
    # dos dois serve:
    #   - `coleta_folha.py` pede remuneracao e ficha de contracheque, mas trata
    #     PAGINA VAZIA como fim de folha. O portal limitando a resposta e isso
    #     pareceu "acabou": gravou **650 de 1165** servidores e batizou de folha
    #     completa.
    #   - `coletar_folha_simples.py` acerta o fim da folha, mas pede MENOS
    #     colunas: deixa `vldefault` e `cdContraCheque` de fora. A folha
    #     coletada por ele perde a remuneracao — que e o historico gravado por
    #     `carga_folha.definir_remuneracao` e o numero que o card de Dados
    #     Abertos mostra (mediana e folha bruta).
    #
    # `coletar_folha_completa.py` junta as duas: folha INTEIRA E com
    # remuneracao. E tem saidas que FALHAM em vez de gravar folha truncada
    # (2 = veio menos do que o portal anunciou, 3 = portal nao informou
    # `recordsFiltered`): truncar e chamar aquilo de completo foi o defeito.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261001_coleta_completa'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261001') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261001' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261001_coleta_completa', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261001_origem_unidade'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261001') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261001' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261001_origem_unidade', '1') "
                    "ON CONFLICT DO NOTHING")

    # =====================================================================
    # Migração 02/10/2026 — A ENTREGA SOBE COM TUDO DESLIGADO.
    #
    # Decisão do responsável: na entrega o município recebe o sistema com os
    # módulos desligados, e quem liga é o `master`, um por um. Ficam de pé só os
    # três que o sistema precisa para existir — `usuarios` (quem entra),
    # `auditoria` (a trilha de quem fez o quê) e o núcleo `tisosdocfly`, que nem
    # entra em `tb_modulos`. `blog` deixou de ser indispensável: é conteúdo, e
    # um município que não publica nada continua com um sistema íntegro.
    #
    # POR QUE EXISTE ESTA MIGRAÇÃO, E POR QUE ELA É UMA SÓ VEZ.
    # A semente em `autenticacao._garantir_tb_modulos` só alcança banco NOVO:
    # ela é `INSERT OR IGNORE`, e banco em uso já tem a linha — que é o
    # comportamento desejado para não redecidir por conta própria o que o
    # administrador já ligou (mesmo cuidado das contas de fábrica, §8.2.0).
    # Mas aqui a decisão foi outra, e explícita: o banco ATIVO também entra na
    # regra. Sem isto, a mudança existiria só no código e o servidor em uso
    # continuaria com tudo ligado — o rodapé diria uma coisa e a entrega, outra.
    #
    # O marcador `migracao_modulos_desligados_261002` garante UMA execução. Sem
    # ele este UPDATE rodaria a cada boot e o administrador que ligou o módulo
    # de Empenhos o veria desligar sozinho no dia seguinte — que é o pior
    # defeito que uma migração de estado pode ter.
    #
    # SQL PORTÁTIL (§4.1): o UPDATE não interpola a lista de dispensados; usa
    # `NOT IN` com literais, o mesmo conjunto nos dois backends. As chaves
    # dispensadas são `autenticacao.MODULOS_INDISPENSAVEIS` — a lista é escrita
    # aqui de propósito, e não importada, porque `init_db` roda ANTES de
    # `mod_tisosdocfly.autenticacao` estar pronto para ser importado sem risco de
    # ciclo. A duplicata é o preço da ordem de boot, e é ela que
    # `tests/test_modulos_desligados.py` vigia: se uma lista mudar e a outra
    # não, o teste quebra.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_modulos_desligados_261002'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("UPDATE tb_modulos SET ativo=0 "
                    "WHERE chave NOT IN ('auditoria', 'usuarios', 'hora_certa')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_modulos_desligados_261002', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 02/10/2026 — bump do módulo tisosdocfly (módulos desligados de
    # fábrica + trava de URL em `pagina_restrita` + card laranja só para admin).
    # `ON CONFLICT DO NOTHING` no INSERT para nunca rebaixar uma versão que já
    # evoluiu ou que o administrador ajustou; o UPDATE só age porque o
    # marcador ainda não existe, ou seja, é a primeira vez que este código roda.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261002_modulos_desligados'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261002') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261002' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261002_modulos_desligados', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 02/10/2026 — bump do módulo usuarios (cards de acesso por cargo,
    # DDI obrigatório no telefone, botão Adicionar pela fábrica do tema) e do
    # `tisosdocfly` (grade de campos 40-60 caracteres com 1/2/3 colunas, cartão de
    # diálogo com `flex-wrap: nowrap`, botão Cancelar pela fábrica do tema).
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261002_cards_acesso'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261002') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261002' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261002_cards_acesso', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 02/10/2026 — layout `src/`: bump dos SETE módulos cujo caminho
    # de banco mudou de `BASE_DIR` (que agora é `src/`) para `DIR_PROJETO`
    # (a raiz do repositório). O sintoma era o sistema subir sem banco nenhum
    # e, com `main.py` apontando `sys.path` para a raiz, nem importar.
    #
    # §4.2: "cada módulo alterado ganha a PRÓPRIA migração". Cada chave tem
    # portanto o seu marcador (`migracao_versao_<chave>_261002_layout_src`), o
    # que também torna o bump reentrante: rodar `init_db` duas vezes não
    # sobrescreve uma versão que o administrador ajustou, porque a segunda
    # passagem não entra no `if`. O laço é só para não repetir sete vezes o
    # mesmo bloco — o que continua sendo uma migração por módulo é o
    # MARCADOR, não o `execute`.
    for _chave_bump in ("auditoria", "editar_pdf", "blog", "empenhos",
                        "solicita_impressao", "filas", "tecnico"):
        cur.execute("SELECT COUNT(*) FROM tb_config "
                    "WHERE chave='migracao_versao_%s_261002_layout_src'" % _chave_bump)
        if (cur.fetchone()[0] or 0) == 0:
            cur.execute("INSERT INTO tb_config (chave, valor) VALUES (?, ?) "
                        "ON CONFLICT DO NOTHING",
                        ("versao_modulo:%s" % _chave_bump, "1.0.261002"))
            cur.execute("UPDATE tb_config SET valor='1.0.261002' "
                        "WHERE chave='versao_modulo:%s'" % _chave_bump)
            cur.execute("INSERT INTO tb_config (chave, valor) VALUES (?, '1') "
                        "ON CONFLICT DO NOTHING",
                        ("migracao_versao_%s_261002_layout_src" % _chave_bump,))

    # =====================================================================
    # Migração 02-03/10/2026 — MODELO ÚNICO DE VERSIONAMENTO, ALINHAMENTO.
    #
    # O QUE ESTA MIGRAÇÃO FAZ: garante que, para as 14 chaves de `MODULOS_BD`,
    # o valor no banco em uso seja o MESMO que o tuple de seed do começo deste
    # `init_db`. O seed sozinho alcança banco novo; sozinho, ele deixava o
    # banco em uso defasado em cinco chaves (medido em 02/10/2026):
    # `empenhos` 260930, `auditoria` 261001, `solicita_impressao` 260930,
    # `tecnico` 260929 e `agregador_noticias` 260930 — enquanto o banco dizia
    # 261002 nas quatro primeiras. É a diferença entre a instalação nova e a
    # instalação em uso discordando do mesmo código, que é o defeito que a §4.2
    # existe para impedir.
    #
    # POR QUE "SÓ SE ESTIVER MAIS VELHO" NO UPDATE: o `INSERT ... ON CONFLICT
    # DO NOTHING` já cobre chave ausente. O `UPDATE` com a condição `valor < ?`
    # faz o resto com honestidade — avança um banco atrasado e NÃO rebaixa
    # nada que já tenha evoluído. A comparação de texto é correta porque o
    # formato `1.0.AAMMDD` tem largura fixa, então ordem lexicográfica é ordem
    # cronológica (`1.0.260928` < `1.0.261003`).
    #
    # IDEMPOTÊNCIA em duas camadas: o marcador `migracao_versao_pendentes_
    # 261003` faz a migração rodar UMA vez (mesmo nome de família do lote de
    # 28/09, `migracao_versao_pendentes_260928`); e, mesmo que ela rode outra
    # vez, o `UPDATE` só age em versão mais velha. A segunda passagem de
    # `init_db()` não muda nada.
    #
    # SQL PORTÁTIL (§4.1): `COUNT(*)`, `INSERT ... ON CONFLICT DO NOTHING` e
    # `UPDATE ... WHERE chave = ?` são válidos em SQLite e PostgreSQL. Não há
    # `sqlite3` cru aqui: esta função trabalha pela conexão do `banco_conexao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_pendentes_261003'")
    if (cur.fetchone()[0] or 0) == 0:
        for _chave_al, _ver_al in (
            # Módulos ALTERADOS — bump para a data da alteração (03/10/2026).
            # `os` entrou neste grupo em 03/10/2026: o painel de visão geral da
            # administração parou de ter SQL próprio (cinco queries pediam
            # coluna inexistente e o painel mostrava zero) e passou a ler de
            # `mod_os/bd_manipulador.visao_geral()`.
            ("tisosdocfly", "1.0.261003"),
            ("usuarios", "1.0.261003"),
            ("auditoria", "1.0.261003"),
            ("editar_pdf", "1.0.261003"),
            ("empenhos", "1.0.261003"),
            ("agregador_noticias", "1.0.261003"),
            ("solicita_impressao", "1.0.261003"),
            ("os", "1.0.261003"),
            # `filas` e `lista_telefonica` sobem para 03/10/2026 (upload de
            # mídia no io_bound + testids do admin; 4º grau do organograma
            # documentado). Ficam aqui E na migração própria de cada um: as
            # duas rotas convergem para 1.0.261003 e o `UPDATE` só avança
            # versão mais velha, então rodar as duas é inofensivo.
            ("filas", "1.0.261003"),
            # `lista_telefonica` sobe para 06/10/2026: a tela passou a abrir na
            # lista de telefones lida de `lista_telefonica.csv` (leitura nova,
            # `leitura_csv.py`) e o organograma virou o que aparece com busca.
            ("lista_telefonica", "1.0.261006"),
            # Módulos NÃO alterados: só o alinhamento. Cada um fica na data da
            # SUA última alteração — bump aqui seria dizer que o código mudou
            # hoje, e não mudou (§4.2).
            ("tecnico", "1.0.261002"),
            ("estoque", "1.0.260929"),
            # `dados_abertos` saiu daqui em 03/10/2026: ele foi ALTERADO no dia
            # (`listar_fontes()` sem `cur.execute` deixava o portal vazio em toda
            # instalação) e já tem bump próprio no seed acima e na migração
            # `migracao_versao_dados_abertos_261003_execute`. Ficar aqui com
            # `1.0.261001` era o mesmo defeito que o `lista_telefonica` tinha:
            # a chave declarada duas vezes, com versões que se contradizem.
            #
            # `blog` saiu daqui em 04/10/2026 pelo MESMO motivo: ele foi
            # alterado no dia (os avisos padronizados, com o
            # `migracao_versao_blog_261004` próprio) e, enquanto esta linha
            # dissesse `1.0.261002`, o seed de cima e esta migração se
            # contradiziam sobre a mesma chave.
        ):
            cur.execute("INSERT INTO tb_config (chave, valor) VALUES (?, ?) "
                        "ON CONFLICT DO NOTHING",
                        (f"versao_modulo:{_chave_al}", _ver_al))
            cur.execute("UPDATE tb_config SET valor=? "
                        "WHERE chave=? AND (valor IS NULL OR valor='' "
                        "OR valor='1.0' OR valor < ?)",
                        (_ver_al, f"versao_modulo:{_chave_al}", _ver_al))
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_pendentes_261003', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 02-03/10/2026 — bump individual de cada módulo alterado (§4.2:
    # "múltiplos módulos no mesmo commit: cada módulo alterado ganha a PRÓPRIA
    # migração"). O lote acima alinha; estes sete deixam o rastro do PORQUÊ,
    # e cada marcador próprio garante uma execução só.
    #
    # Os sete blocos abaixo são ESCRITOS UM A UM, e não em laço, por dois
    # motivos que valem mais que a concisão: (a) o marcador de cada módulo é
    # literal, e é o literal que `tests/teste_versionamento_modulo.py` lê para
    # exigir bump de quem foi alterado; (b) a §4.2 quer uma migração POR
    # módulo, e o que separa uma migração da outra é o marcador. A concisão
    # viraria o motivo pelo qual a regra pararia de ser verificável.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261003_modelo_unico'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261003') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261003' "
                    "WHERE chave='versao_modulo:tisosdocfly' AND (valor IS NULL "
                    "OR valor='' OR valor='1.0' OR valor < '1.0.261003')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261003_modelo_unico', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261003_modelo_unico'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261003') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261003' "
                    "WHERE chave='versao_modulo:usuarios' AND (valor IS NULL "
                    "OR valor='' OR valor='1.0' OR valor < '1.0.261003')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261003_modelo_unico', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 03/10/2026 — `usuario_existe` FAIL-SOFT (o login inteiro
    # dependia de uma importação tardia sem rede de proteção).
    # `mod_tisosdocfly/autenticacao.py::usuario_existe` não tinha `try/except`,
    # ao contrário de todos os vizinhos do mesmo arquivo. Ela chama `_gest()`,
    # que faz `from mod_gest_cad_usuario import bd_manipulador` NA HORA DA
    # CHAMADA — e esse módulo roda `init_db()` no topo do arquivo, então um
    # banco travado, um schema pela metade ou um reload de tela fazia a
    # importação falhar ali. Sem o `try`, a exceção subia por `autenticar()`,
    # que é o botão da tela de login: a resposta virava "Erro ao tentar
    # entrar. Tente novamente." para todo mundo, inclusive para quem digitava
    # a senha certa. E `pagina_restrita` (`telas.py:219`) chama a MESMA função
    # sem proteção em CADA request de página protegida.
    #
    # A correção devolve `None` — que é a direção segura: "conta não achada"
    # nega o login, e `perfil_global_de`/`listar_modulos_permitidos` recebem
    # `None` e negam o acesso. Falha de infraestrutura nunca vira permissão.
    #
    # O bump é do `tisosdocfly`, não do `usuarios`: o arquivo alterado é do núcleo,
    # mesmo que o dado que ele protege seja o cadastro. O `usuarios` já está
    # em 261003 pelo lote de cima (mesma data, §4.2 — o patch é o dia).
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261003_usuario_existe_seguro'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261003') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261003' "
                    "WHERE chave='versao_modulo:tisosdocfly' AND (valor IS NULL "
                    "OR valor='' OR valor='1.0' OR valor < '1.0.261003')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261003_usuario_existe_seguro', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_auditoria_261003_modelo_unico'")
    if (cur.fetchone()[0] or 0) == 0:
        # `auditoria`: a trilha deixou de gravar por nome de pasta e passou a
        # gravar pela chave de `MODULOS_BD`; a migração que move as 4.566
        # linhas para as tabelas canônicas vive em
        # `mod_auditoria/bd_manipulador.py` (o banco dela é dela).
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:auditoria', '1.0.261003') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261003' "
                    "WHERE chave='versao_modulo:auditoria' AND (valor IS NULL "
                    "OR valor='' OR valor='1.0' OR valor < '1.0.261003')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_auditoria_261003_modelo_unico', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 21/10/2026 — bump da `auditoria` (§4.2): acoes de Dados Abertos
    # (`consulta_dado_aberto`, `registrar_fonte`, `alternar_fonte`, PNTP)
    # ganham cor e opcao no filtro de acao — a trilha de consulta passa a ser
    # exibida quando solicitada no modulo. Marcador
    # `migracao_versao_auditoria_261021_acoes_dados_abertos`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_auditoria_261021_acoes_dados_abertos'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:auditoria', '1.0.261021') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261021' "
                    "WHERE chave='versao_modulo:auditoria'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_auditoria_261021_acoes_dados_abertos', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_editar_pdf_261003_modelo_unico'")
    if (cur.fetchone()[0] or 0) == 0:
        # `editar_pdf`: saiu o `INSERT OR IGNORE ... '1.0.260908'` que
        # congelava a versão do Editor de PDF em 08/09.
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:editar_pdf', '1.0.261003') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261003' "
                    "WHERE chave='versao_modulo:editar_pdf' AND (valor IS NULL "
                    "OR valor='' OR valor='1.0' OR valor < '1.0.261003')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_editar_pdf_261003_modelo_unico', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_empenhos_261003_modelo_unico'")
    if (cur.fetchone()[0] or 0) == 0:
        # `empenhos`: a trilha de renomeação gravava em
        # `tb_auditoria_renomear_empenho` (nome da pasta) em vez de
        # `tb_auditoria_empenhos`.
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:empenhos', '1.0.261003') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261003' "
                    "WHERE chave='versao_modulo:empenhos' AND (valor IS NULL "
                    "OR valor='' OR valor='1.0' OR valor < '1.0.261003')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_empenhos_261003_modelo_unico', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_agregador_noticias_261003_modelo_unico'")
    if (cur.fetchone()[0] or 0) == 0:
        # `agregador_noticias`: saiu a migração local que sobrescrevia a
        # versão a cada `init_db`, e a chamada de auditoria que passava os
        # argumentos trocados.
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:agregador_noticias', '1.0.261003') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261003' "
                    "WHERE chave='versao_modulo:agregador_noticias' "
                    "AND (valor IS NULL OR valor='' OR valor='1.0' "
                    "OR valor < '1.0.261003')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_agregador_noticias_261003_modelo_unico', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_solicita_impressao_261003_modelo_unico'")
    if (cur.fetchone()[0] or 0) == 0:
        # `solicita_impressao`: removida a chave órfã `versao_modulo` de
        # `tb_configuracoes_modulo` (terceira via de versionamento, que
        # ninguém lia).
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:solicita_impressao', '1.0.261003') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261003' "
                    "WHERE chave='versao_modulo:solicita_impressao' "
                    "AND (valor IS NULL OR valor='' OR valor='1.0' "
                    "OR valor < '1.0.261003')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_solicita_impressao_261003_modelo_unico', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_os_261003_visao_geral'")
    if (cur.fetchone()[0] or 0) == 0:
        # `os`: o painel de visão geral da administração lia o banco com SQL
        # próprio, e cinco das queries pediam coluna que não existe na tabela
        # (`arquivada` em vez de `arquivado`, `situacao` em vez de `status`,
        # `user_nome` em vez de `convidado_user_nome`). Cada uma falhava com
        # `no such column` e um helper da tela devolvia `0` no erro — o painel
        # mostrava ZERO para ordens, atrasos, convites e convidados, sem aviso.
        # As queries foram para `mod_os/bd_manipulador.visao_geral()` (que era
        # código morto), junto do `eh_admin_geral` que se perdia ao comentar e
        # do padrão de numeração que o card gravava e ninguém lia.
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:os', '1.0.261003') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261003' "
                    "WHERE chave='versao_modulo:os' AND (valor IS NULL "
                    "OR valor='' OR valor='1.0' OR valor < '1.0.261003')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_os_261003_visao_geral', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261003_execute'")
    if (cur.fetchone()[0] or 0) == 0:
        # `dados_abertos`: `listar_fontes()` montava o SQL e chamava
        # `cur.fetchall()` num cursor novo SEM `cur.execute(sql)` antes — o
        # cursor nunca consultava e devolvia `[]`. Como a função é fail-soft,
        # o `except` transformava isso em "nenhuma fonte registrada": a grade
        # de cards de `/dados-abertos` nascia VAZIA em toda instalação, mesmo
        # com as fontes no banco. Encontrado por
        # `tests/test_e2e_dados_abertos.py::test_chave_existe_consulta_o_registro_real`.
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261003') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261003' "
                    "WHERE chave='versao_modulo:dados_abertos' "
                    "AND (valor IS NULL OR valor='' OR valor='1.0' "
                    "OR valor < '1.0.261003')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261003_execute', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_filas_261003_upload_io_bound'")
    if (cur.fetchone()[0] or 0) == 0:
        # `filas`: o upload de mídia (áudio/vídeo/foto do carrossel da TV)
        # gravava o arquivo com `open(dest,"wb").write(...)` DIRETO no
        # event-loop, dentro de um `async def` — que é exatamente o lugar onde
        # o defeito se esconde, porque a linha parece instantânea. Um vídeo
        # grande travava o event-loop e, com ele, a tisosdocfly inteira (AGENTS.md
        # §5.1): não só quem enviava, mas quem estava na fila e quem estava na
        # TV. Havia o mesmo defeito em três lugares — upload da fila
        # (`telas.py`), anexo em staging (`telas.py`) e upload global do admin
        # (`telas_administracao.py`) — e os três foram para `run.io_bound`, com
        # botão desabilitado e trava de reentrância. O `/admin/filas` também
        # não expunha NENHUM `data-testid` (o painel do usuário tinha 33), o
        # que tornava o painel do administrador intestável; agora tem 33,
        # parametrizados por `fid`/`eid`/`mid` porque a tela lista as filas em
        # laço e um testid fixo duplicaria N vezes (o strict-mode do Playwright
        # não tolera duplicado).
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:filas', '1.0.261003') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261003' "
                    "WHERE chave='versao_modulo:filas' "
                    "AND (valor IS NULL OR valor='' OR valor='1.0' "
                    "OR valor < '1.0.261003')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_filas_261003_upload_io_bound', '1') "
                    "ON CONFLICT DO NOTHING")

    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261003_quarto_degrau'")
    if (cur.fetchone()[0] or 0) == 0:
        # `lista_telefonica`: o banco JÁ aceita o 4º degrau — `_pai_valido()`
        # diz, no próprio docstring, que a restrição antiga ('subsetor' só
        # pode ficar sob 'setor') foi removida em 27/09/2026 exatamente porque
        # travava a árvore em três degraus, e que "a restrição era do
        # formulário, não do dado". O formulário, porém, nunca foi junto:
        # `telas_administracao.py:refresh_pai` e `telas._opcoes_pai` seguem
        # offering só o degrau anterior como pai, e o painel do admin desenha
        # três níveis. Três lugares concordando em tornar o 4º degrau
        # inalcançável — uma migração pela metade. Esta migração só data o
        # código; a correção dos três lugares é decisão de produto (o tipo
        # `subsetor` continua sendo o rótulo de um 4º degrau, ou o organograma
        # precisa de um 4º rótulo novo), então foi reportada em vez de
        # adivinhada.
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261003') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261003' "
                    "WHERE chave='versao_modulo:lista_telefonica' "
                    "AND (valor IS NULL OR valor='' OR valor='1.0' "
                    "OR valor < '1.0.261003')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261003_quarto_degrau', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `lista_telefonica` em 06/10/2026 — LISTA DE TELEFONES DO CSV.
    #
    # O que mudou é o que a pessoa vê ao ABRIR o módulo. Antes a tela nascia no
    # organograma (secretaria > setor > subsetor, mais de mil servidores do
    # cadastro); agora nasce na lista de telefones lida do `lista_telefonica.csv`
    # que mora dentro do módulo, com recepção e externos no começo, o resto em
    # ordem alfabética e os cartões USO no fim. O organograma continua no
    # módulo e passa a aparecer com busca — nada foi removido, e é por isso que
    # esta migração só data o código (§4.2): o schema de `lista_telefonica`
    # não mudou uma vírgula.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261006_lista_csv'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261006') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261006' "
                    "WHERE chave='versao_modulo:lista_telefonica' "
                    "AND (valor IS NULL OR valor='' OR valor='1.0' "
                    "OR valor < '1.0.261006')")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261006_lista_csv', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `usuarios` em 04/10/2026 — PESSOA × CONTRATO, HISTÓRICO E
    # BUSCA NO SERVIDOR.
    #
    # **A DATA É 04/10, E NÃO 03/10.** A alteração começou em 03/10 (o
    # desenho, o schema, a carga) e é ENTREGUE em 04/10 — e a §4.2 diz
    # que o patch é "a data do dia da alteração", não a de quando o
    # `git status` ficou sujo pela primeira vez. Não é preciosismo de
    # formato: `teste_versionamento_modulo.py` compara o marcador com a
    # data de HOJE e reprova o bump de ontem, porque um marcador de
    # ontem não prova que a mudança de HOJE foi registrada — foi
    # exatamente o que aconteceu com `..._261003_pessoa_contrato`.
    #
    # O que mudou no módulo, e o que a §4.2 do AGENTS.md obriga a
    # registrar:
    #   - três tabelas novas: `tb_contratos` (1 pessoa, N matrículas),
    #     `tb_historico_movimentos` (demissão como movimento) e
    #     `tb_historico_salarial` (evolução por competência);
    #   - a carga da folha passou a gravar TODOS os campos por UM caminho
    #     só (`gravar_dados_folha`), e o primeiro registro virou
    #     `vinculacao` em vez de quatro "mudanças" que não eram mudança;
    #   - a demissão pela folha NÃO desliga mais a conta de quem já
    #     trabalhava no sistema — desligar é decisão do administrador;
    #   - a busca de usuários saiu do navegador para o servidor, com
    #     paginação e total real.
    #
    # Marcador PRÓPRIO (`..._261004_pessoa_contrato`), e não um dos de
    # hoje, porque este é um desenho novo e a §4.2 exige bump
    # rastreável por alteração, não por dia.
    #
    # **ESTE BLOCO VEM POR ÚLTIMO, E ISSO NÃO É ESTÉTICA.** A migração
    # `migracao_versao_usuarios_261003_modelo_unico`, lá acima, faz
    # `UPDATE tb_config SET valor='1.0.261003' WHERE chave='versao_modulo:
    # usuarios'` SEM a guarda `valor <` que os outros têm — ela escreve
    # por cima de qualquer versão. Com este bump antes dela, a versão
    # final do banco ficava `1.0.261003`: o seed dizia 261004, a
    # migração gravava 261004, e a de 03/10 descia de volta. Medido, e o
    # banco novo já saía errado. Migração nova vai depois das antigas.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261004_pessoa_contrato'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261004') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261004' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261004_pessoa_contrato', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — foto mensal + registro de cargas (`tb_foto_mensal`,
    # `tb_cargas_folha`). Vai AQUI (depois da 261004), e não em ordem
    # cronológica lá acima, pelo motivo do comentário acima: bloco antigo com
    # UPDATE incondicional rebaixa o que vier antes dele em instalação nova.
    #
    # **NENHUMA COLUNA MUDA EM TABELA EXISTENTE.** As duas tabelas são NOVAS e
    # nascem no `init_db` do próprio `mod_gest_cad_usuario` (`CREATE TABLE IF
    # NOT EXISTS`) — esta migração cuida só da versão, como manda o §4.2. O
    # dado antigo não é reescrito: a foto da competência corrente entra na
    # próxima carga da folha, que roda no boot com o sistema no ar.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261007_foto_mensal'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:usuarios', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261007_foto_mensal', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — espelho da lista passa a incluir BLOQUEADOS.
    #
    # Vai AQUI (depois da foto_mensal), pelo motivo do comentário acima:
    # bloco antigo com UPDATE incondicional rebaixa o que vier antes dele.
    # Mesma versão do dia (`1.0.261007`, e está tudo bem — a versão data o
    # código, §4.2), marcador próprio para rastrear a alteração.
    #
    # **NENHUM DADO MUDA NESTA MIGRAÇÃO.** O que muda é a leitura
    # (`leitura_lista.listar_para_lista_telefonica` e
    # `buscar_usuarios_para_lista` deixam de exigir `user_ativo=1`): o
    # diretório passa a mostrar o posto público de quem ainda está
    # bloqueado. O bloqueio de ACESSO continua — login, papel e consulta
    # de gestão não foram tocados. Os contatos entram no próximo
    # sincronismo (manual ou automático de 15 min).
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261007_espelho_bloqueados'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:usuarios', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261007_espelho_bloqueados', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — a matrícula sai do cartão do diretório.
    #
    # Vai por último, pelo motivo já dito: bloco antigo com UPDATE
    # incondicional rebaixa o que vier antes dele em instalação nova.
    #
    # **NENHUM DADO MUDA NESTA MIGRAÇÃO.** O que muda é o desenho do cartão
    # em `mod_lista_telefonica/telas.py`: some o rótulo `@<matrícula>`, e o
    # caminho da unidade (secretaria/setor/subsetor) fica sozinho na linha de
    # baixo. O `user_nome` continua gravado em `tb_contato.user_nome` — é por
    # ele que a lista sabe quem é "deixe recado" e reespelha o cadastro. O que
    # deixa de aparecer é o TEXTO, não o vínculo.
    #
    # POR QUE SOME: o cartão responde "quem é e onde trabalha". Nome, cargo,
    # vínculo e situação já dizem o posto; a matrícula é identificador do RH,
    # e quem precisa dela para falar com o DTI tem a busca de usuários.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261007_sem_matricula'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:lista_telefonica', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261007_sem_matricula', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — a sincronização do diretório CONVERGE (era a queda
    # do servidor).
    #
    # Vai por último, pelo motivo de sempre: bloco antigo com UPDATE
    # incondicional rebaixa o que vier antes dele em instalação nova.
    #
    # **NENHUM DADO MUDA NESTA MIGRAÇÃO.** O defeito era de LEITURA: em
    # `mod_lista_telefonica/bd_manipulador.py`, a comparação de convergence
    # fatiava `[7:13]` de uma linha de 12 colunas (o certo era `[6:12]`),
    # produzindo 5 valores contra 6 — nunca iguais. Efeito medido no
    # `logs/up.err`: `atualizados=1094 iguais=0` repetido a cada 0,4 s pelo
    # `_auto_sincronizar` da tela, ou seja, ~1.100 UPDATEs + 1 COMMIT por
    # render da lista telefônica. Em SQLite WAL isso é contenção de escrita,
    # o `_commit_com_retry` dorme no event-loop, o heartbeat do WebSocket
    # estoura e o servidor cai com todo mundo desconectado.
    #
    # A correção é o helper `_posto_do_contato`, e o que a trava é a
    # CONVERGÊNCIA: o segundo sync tem de reler `iguais` e não gravar. O
    # teste `tests/test_lista_telefonica_convergencia.py` existe para isso.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261007_convergencia'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:lista_telefonica', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261007_convergencia', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — a grade de contatos passa a ser GRID fixo (4
    # colunas sempre) e a lista passa a ser PAGINADA, em vez de um corte.
    #
    # Vai por último, pelo motivo de sempre: bloco antigo com UPDATE
    # incondicional rebaixa o que vier antes dele em instalação nova.
    #
    # **NENHUM DADO MUDA NESTA MIGRAÇÃO.** O defeito era de DESENHO: o
    # organograma estava no multicol, que tem `column-fill: balance` por
    # padrão e ignora `column-count`. Com 9 cartões ele distribuía 3×3, e o
    # sintoma era irregular conforme o tamanho da unidade — "Sec Mun de
    # Planejamento Urbano e Meio Ambiente" (9) saía em 3 colunas de 3 e
    # "Gabinete Municipal e Assessoria Governo" (8) em 4. O GRID
    # (`lista-grade-fixa`) rende exatamente as colunas declaradas.
    #
    # E o limite de 240 cartões era um CORTE que escondia servidores que
    # existem — o usuário podia procurar Secretaria de Educação e não achar
    # quem existe. A versão `PAGINA_CONTATOS=20` mostra todos, em páginas, e
    # o teste `tests/test_lista_telefonica_paginacao.py` trava a partição
    # (todo contato aparece uma vez só).
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261007_paginacao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:lista_telefonica', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261007_paginacao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — a unidade do cartão de contato ganha duas linhas,
    # sem o ">" esticando para a direita.
    #
    # Vai por último, pelo motivo de sempre.
    #
    # **NENHUM DADO MUDA NESTA MIGRAÇÃO.** O cartão de contato mostrava o
    # caminho "Secretaria > Setor > Subsetor" numa linha só, e o ">" puxava
    # a largura do cartão para a direita. Agora o cartão mostra a secretaria
    # em uma linha e a subunidade logo abaixo, e o ">" só some da linha
    # principal (o caminho inteiro segue no `tooltip`, para quem precisar).
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261007_cards_unidade'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:lista_telefonica', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261007_cards_unidade', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — os selects de unidade ganham largura mínima de
    # `25ch`, para o nome da unidade não aparecer truncado ("al de Educacao
    # Publica") quando a seleção é uma secretaria longa.
    #
    # **NENHUM DADO MUDA NESTA MIGRAÇÃO.** Só o estilo das três boxes de
    # `mod_lista_telefonica/telas.py` mudou (`sm:min-w-[320px]` +
    # `min-width: 25ch`): antes devolvam o texto da opção em meio caminho, e
    # o usuário tinha de adivinhar qual secretaria tinha clicado.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261007_selects'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:lista_telefonica', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261007_selects', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — os quatro campos de filtro na mesma linha e os
    # SELECTES no tamanho pedido.
    #
    # **NENHUM DADO MUDA NESTA MIGRAÇÃO.** O primeiro ajuste dos selects
    # deixou-os largos demais. Agora: o campo de busca fica fixo em 320px;
    # os três selects (Unidade/Subunidade/Sub-subunidade) ficam com `30ch`
    # (entre 25 e 35 caracteres), alinhário à esquerda, numa linha só quando
    # há espaço, e dobrando linha quando a tela estreita — `flex-wrap`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261007_selects_uma_linha'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:lista_telefonica', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261007_selects_uma_linha', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — o placeholder do campo de busca passa a explicar
    # buscav por vínculo e situação, que a busca já cobre desde 28/09.
    #
    # **NENHUM DADO MUDA NESTA MIGRAÇÃO.** Só o texto do campo em
    # `mod_lista_telefonica/telas.py` mudou. A busca por "férias", "efetivo"
    # ou "comissionado" já devolvia os contatos certos (via
    # `impressao._texto_do_contato`, que lê `vinculo` e `situacao`) — só não
    # dizia isso ao usuário. Conferido: 'ferias'→50, 'efetivo'→544,
    # 'comissionado'→20, 'contrato'→425, 'estagiario'→121.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261007_busca_placeholder'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:lista_telefonica', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261007_busca_placeholder', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — o cartão de contato fica legível: cargo ao lado
    # do nome e o texto secundário com mais contraste.
    #
    # **NENHUM DADO MUDA NESTA MIGRAÇÃO.** Só o desenho do cartão em
    # `mod_lista_telefonica/telas.py` mudou: (1) o cargo sai da linha 2 e vai
    # logo depois do nome ("João Silva - Analista de Administração"),
    # eliminando a duplicidade; (2) o texto das linhas secundárias (secretaria,
    # subunidade, telefone, "sem número informado") subiu de `text-grey-5`/ea6
    # para `text-grey-8`/`text-grey-9`, e o cartão ganhou `border-grey-3` +
    # `shadow-sm` — as linhas de secretaria e departamento estavam quase
    # invisíveis contra o fundo branco.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261007_cards_nome_cargo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('versao_modulo:lista_telefonica', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261007_cards_nome_cargo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Bump do `tisosdocfly` em 04/10/2026 — `_ddl_postgres` do núcleo.
    #
    # O `tisosdocfly` é tocado por um DEFEXTO REAL do núcleo, encontrado
    # rodando no PostgreSQL (§4.1) e não por vaidade. Em
    # `banco_conexao._ddl_postgres`, a regex que remove `REFERENCES` dos
    # DDL usava `\w+(?:\s+\w+)?` para a ação de cada cláusula
    # `ON DELETE`/`ON UPDATE` — e `\w` casa "ON". Com as DUAS cláusulas na
    # mesma linha (`ON DELETE CASCADE ON UPDATE CASCADE`) o grupo comia
    # o " ON" seguinte e sobrava `UPDATE CASCADE` pendurado na coluna.
    # Nenhuma tabela anterior do projeto tinha as duas cláusulas, e é por
    # isso que o defeito passou despercebido: `tb_contratos`,
    # `tb_historico_movimentos` e `tb_historico_salarial` são as
    # primeiras, e o `CREATE TABLE` delas morria no PostgreSQL com
    # `relation "tb_contratos" does not exist`. É exatamente o defeito
    # que a §4.1 existe para pegar, e que nenhuma leitura via SQLite
    # veria.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261004_ddl_references'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261004') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261004' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261004_ddl_references', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 04/10/2026 — AVISOS (TOASTS) EM 20 SEGUNDOS, COM PISO DE 10.
    #
    # Subiu duas vezes no mesmo dia, e a segunda vez porque a primeira NÃO
    # SURTIU EFEITO — o que é a informação útil desta migração.
    #
    # A primeira versão mudou só o `PADRAO_CONFIG` e o `tema_modulo`. Não
    # funcionou porque o sistema tem **232 chamadas** a `ui.notify` (104 só
    # no Empenhos, 52 na Solicitação, 34 no Blog) e todas elas vão DIRETO ao
    # NiceGUI com o tempo padrão da biblioteca, ignorando
    # `notificacao_timeout`. Só `tema_modulo.notificar` respeitava a
    # configuração, e quase nenhum aviso passa por lá.
    #
    # A correção de fundo está em `mod_tisosdocfly/nicegui_patch.py`, que
    # embrulha o `ui.notify` do NiceGUI e aplica o tempo configurado a
    # QUALQUER chamada — inclusive as 232.
    #
    # POR QUE UMA MIGRAÇÃO E NÃO SÓ O DEFAULT: o `PADRAO_CONFIG` acima é
    # Consultado quando a CHAVE NÃO EXISTE no banco. Numa instalação já em uso
    # a chave existe com o valor '5', então mudar o default não mudaria nada
    # nela — e é o caso desta. A migração reescreve o valor gravado.
    #
    # POR QUE SUBIR TAMBÉM O PISO PARA 10 E NÃO SÓ O VALOR: se o piso
    # continuasse em 1, bastava o administrador gravar '1' pelo painel e o
    # problema voltaria inteiro. A garantia precisa estar no código — e está,
    # em `tema_modulo.notificacao_timeout` (`max(10, v)`).
    #
    # O `versao_modulo:tisosdocfly` não é reescrito aqui: a data de hoje já é a
    # dele (`1.0.261004`) e a migração anterior, acima, gravou esse valor.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_toast_20s_261004'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("UPDATE tb_config SET valor='20' "
                    "WHERE chave='notificacao_timeout'")
        cur.execute("INSERT INTO tb_config (chave, valor) "
                    "VALUES ('notificacao_timeout', '20') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_toast_20s_261004', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 04/10/2026 — bump dos 5 módulos cujos avisos foram padronizados.
    #
    # A mudança foi MECÂNICA e em vários módulos ao mesmo tempo: as chamadas
    # `ui.notify(...)` viraram `notificar(..., tipo=...)`, o que faz o aviso
    # passar pelo tema (e pelo tempo configurado) em vez de ir direto ao
    # NiceGUI. Cada módulo alterado ganha a sua migração — §4.2 do AGENTS.md
    # é explícito nisso: "Múltiplos módulos no mesmo commit: cada módulo
    # alterado ganha a PRÓPRIA migração".
    #
    # `tisosdocfly` não entra aqui porque a data de hoje já é a dele
    # (`1.0.261004`), gravada pela migração acima.
    #
    # A `<chave>` é a de `MODULOS_BD` em `mod_tisosdocfly/repositorio.py`, e NÃO
    # o nome da pasta: é `empenhos` para `mod_renomear_empenho` e
    # `editar_pdf` para `mod_edit_pdf`. É aqui que mais se erra.
    for _chave in ("auditoria", "blog", "editar_pdf", "empenhos",
                   "solicita_impressao"):
        _marcador = f"migracao_versao_{_chave}_261004"
        cur.execute("SELECT COUNT(*) FROM tb_config WHERE chave=?",
                    (_marcador,))
        if (cur.fetchone()[0] or 0) == 0:
            cur.execute("INSERT INTO tb_config (chave, valor) "
                        "VALUES (?, '1.0.261004') "
                        "ON CONFLICT DO NOTHING",
                        (f"versao_modulo:{_chave}",))
            cur.execute("UPDATE tb_config SET valor='1.0.261004' "
                        "WHERE chave=?", (f"versao_modulo:{_chave}",))
            cur.execute("INSERT INTO tb_config (chave, valor) "
                        "VALUES (?, '1') ON CONFLICT DO NOTHING",
                        (_marcador,))

    # Migração 04/10/2026 — bump do módulo `usuarios` pelos DADOS DA FOLHA NO
    # CADASTRO (somente leitura).
    #
    # O bloco dos campos do Portal da Transparência passa a aparecer em três
    # telas onde o cadastro é lido: o diálogo "Editar" do administrador, o
    # popup que abre ao passar o mouse no nome da lista e o "Meu Perfil" do
    # próprio servidor. Nenhum deles edita — os 12 campos de
    # `CAMPOS_FONTE_FOLHA` e a matrícula são texto puro, para os dois lados.
    #
    # A data de `usuarios` já era 261004 pelo outro trabalho do dia (pessoa ×
    # contrato). O marcador é DISTINTO de propósito: são duas mudanças
    # diferentes na mesma data, e um marcador só diria que a primeira rodou —
    # que é o que a §4.2 pede quando dois bump caem no mesmo dia.
    #
    # **NENHUMA COLUNA MUDA AQUI.** Esta migração só carimba a versão: o
    # `tb_contratos` já existia com os 12 campos, e o bloco novo lê por ele.
    # Registrado assim porque "a migração não mexe em nada" e "a migração não
    # rodou" produzem exatamente o mesmo banco — e a diferença só aparece
    # quando alguém lê a versão e não sabe o que ela cobriu.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261004_folha_no_cadastro'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261004_folha_no_cadastro', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 05/10/2026 — bump do `tisosdocfly` pelo LAYOUT DA TELA VERDE.
    #
    # A `_login_verde` (`preview_estilos.py`) é a função de layout das TRÊS
    # telas do padrão verde: `/login`, a troca de senha e a troca de
    # credenciais do `master`. O que mudou nela:
    #
    #   - o `padding` lateral da caixa branca do formulário foi de `2rem`
    #     (32px) para 12px (~3mm), por decisão do responsável. O vertical
    #     continua em 40px: respiro vertical separa os campos, e 12px colaria
    #     as caixas umas nas outras;
    #   - `LARGURA_CAIXA_PADRAO` foi de 640px para 680px, e é o MESMO número
    #     nas três telas. Antes o login e a troca usavam 640px e a credencial
    #     do `master` passava `largura_caixa="880px"` — três larguras na mesma
    #     tela, dependendo de quem abria;
    #   - o telefone do `master` deixou de ser o caso que exigia 880px: a coluna
    #     saiu de 279px para 319px (medido), e nela o DDI ("+55 - Brasil",
    #     140px) e o número (171px) cabem INTEIROS lado a lado. Encurtar o
    #     rótulo do DDI para `+55` foi medido e REJEITADO — caberia, mas a
    #     lista de opções viraria "+55", "+49", "+1", sem nome de país;
    #   - a grade dos DOIS botões da tela do `master` saiu de `1fr 1fr` para
    #     `repeat(auto-fit, minmax(min(180px, 100%), 1fr))`: o `1fr` puro
    #     respeita o `min-content` do rótulo mais longo e transbordava 26px em
    #     390px.
    #
    # **NENHUMA COLUNA MUDA AQUI.** Esta migração só carimba a versão: nada
    # disso é esquema nem dado — é CSS e largura de um componente. Registrado
    # assim porque, como a migração de 04/10 do `usuarios` logo acima explica,
    # "a migração não mexe em nada" e "a migração não rodou" produzem o mesmo
    # banco, e a diferença só aparece quando alguém lê a versão e não sabe o
    # que ela cobriu.
    #
    # O SQL é o do padrão da §4.2 — `SELECT COUNT(*)` no marcador e
    # `ON CONFLICT DO NOTHING` nas escritas, que o proxy de PostgreSQL traduz
    # (§4.1). Nenhum `sqlite3` cru.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261005_layout_tela_verde'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261005') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261005' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261005_layout_tela_verde', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — bump do `tisosdocfly` pelo `hora_certa` (AGENTS.md §4.2:
    # toda alteração de código no módulo obriga bump). Núcleo tocado:
    # `repositorio.py` (MODULOS_BD), `autenticacao.py` (MODULOS_SISTEMA),
    # `rotinas.py` (MAPA_BACKUPS), `integracoes.py` (espelho solicita_impressao),
    # `tema_modulo.py` (prefixo + padrão) e `bd_criador.py` (init + sync no boot).
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261007_hora_certa'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261007_hora_certa', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — nascimento do `hora_certa` (AGENTS.md §4.2: módulo
    # novo ganha seed + migração com marcador próprio; a regra do fim do arquivo
    # vale aqui — este é o último escritor de versão do `init_db`).
    #
    # O módulo é a fonte da verdade da hora (NTP.br com fallback para a hora do
    # servidor da aplicação), o relógio digital, os IPs (locais + externo) e o
    # espelho dos agendamentos (um card por módulo, visível só ao admin dele).
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261007_nascimento'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261007_nascimento', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — bump do `solicita_impressao` (AGENTS.md §4.2):
    # relato de erro migrou de `print(...)` para loguru via
    # `observabilidade.get_logger("solicita_impressao")` e os `except
    # Exception: pass` mudos (fallback fitz→pdfplumber em
    # `contar_paginas_pdf` e o `init_db()` do import) passaram a registrar no
    # log. Marcador próprio `migracao_versao_solicita_impressao_261007_descricao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_solicita_impressao_261007_descricao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:solicita_impressao', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:solicita_impressao'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_solicita_impressao_261007_descricao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — bump do `empenhos` (AGENTS.md §4.2): erros em
    # runtime migrados para loguru via
    # `observabilidade.get_logger("renomear_empenho")` — handler
    # `_processar` agora registra `str(e)` e notifica o usuário, `rodar_monitor`
    # registra falha ao gravar erro, `levantar_arquivos` registra falha do
    # `os.walk` em vez de tratar UNC com erro como pasta vazia, e
    # `renomear_manual` ganhou trava externa com log + `(False, msg)`.
    # Marcador próprio `migracao_versao_empenhos_261007_descricao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_empenhos_261007_descricao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:empenhos', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:empenhos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_empenhos_261007_descricao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 13/10/2026 — bump do `empenhos` (AGENTS.md §4.2,
    # anti-disconnect §5.1): três handlers que travavam o event-loop e
    # derrubavam o websocket ("perda de conexão" e retorno sozinho) viraram
    # `async` + `run.io_bound` com trava de reentrância — `_envia_email`
    # (SMTP com timeout de 15 s), `_processar` (`rodar_monitor` com extração
    # de texto por PDF) e `_processar_todos` (um `renomear_manual` por
    # pendente). Marcador próprio
    # `migracao_versao_empenhos_261013_io_bound`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_empenhos_261013_io_bound'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:empenhos', '1.0.261013') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261013' "
                    "WHERE chave='versao_modulo:empenhos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_empenhos_261013_io_bound', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — bump do `editar_pdf` (AGENTS.md §4.2): relato de
    # erro migrou de `print(...)` para loguru via
    # `observabilidade.get_logger("edit_pdf")` e os `except Exception: pass`
    # mudos do `audit_log` (upload_hash, sha256 origem, zip, registrar,
    # deletar, expiração) passaram a registrar no log. Marcador próprio
    # `migracao_versao_editar_pdf_261007_descricao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_editar_pdf_261007_descricao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:editar_pdf', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:editar_pdf'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_editar_pdf_261007_descricao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 07/10/2026 — relato de ERRO em runtime migra de print para loguru
    # no núcleo (AGENTS.md §3.2). Vai NO FIM do bloco, como manda a §4.2.
    #
    # `banco_conexao._ler_config_sqlite` imprimia `[banco] Primeira execução`
    # só no console; agora registra também em loguru (`_log().info`) — boot que
    # fala no console é útil, mas o registro precisa ficar no arquivo.
    # `bd_criador.inicializar_bancos` mantém os prints de boot (`[carga_folha]`
    # e `[hora_certa]`) como feedback de console, e toda FALHA já vai para
    # `observabilidade.get_logger("tisosdocfly")` (`_log_boot.exception/warning`).
    # `instrumentacao_app._observer_requisicoes` convertia exceção de socket.io
    # em 204 sem registro, mascarando disconnect; agora registra em debug
    # (logging + loguru) antes de devolver 204. §4.2: sem coluna nova, só bump.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261007_print_loguru'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261007') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261007' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261007_print_loguru', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 08/10/2026 — bump do `hora_certa` (AGENTS.md §4.2):
    # padronização `CHAVE_MODULO`/`CHAVE` de "os" para "hora_certa" + stub
    # `sincronizar_no_boot` fail-soft via loguru (sem traceback) e alias
    # `init_db`. Marcador próprio `migracao_versao_hora_certa_261008_chave`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261008_chave'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261008') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261008' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261008_chave', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — rebuild do `mod_hora_certa` (§4.2): o quadro de
    # ordens (cópia do `mod_os`, 67 cross-queries) saiu; entraram relógio +
    # calendário na tela (comum vê só hora/data), sincronização NTP.br real
    # (`tb_sincronizacao`, ajuste do SO), espelho de agendamentos (um card por
    # módulo, com reagendamento sem restart) e `reagendar_carga_folha` no núcleo.
    # Marcador `migracao_versao_hora_certa_261011_rebuild`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261011_rebuild'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261011_rebuild', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 — nascimento do `mod_zap` (AGENTS.md §4.2): Fase 1
    # (perfis + logs). Marcador `migracao_versao_zap_261012_nascimento`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_zap_261012_nascimento'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:zap', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:zap'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_zap_261012_nascimento', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 — Fase 2 do `mod_zap` (§4.2): motor wa.me + QR na
    # tela + playwright em runtime. Marcador `migracao_versao_zap_261012_motor`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_zap_261012_motor'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:zap', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:zap'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_zap_261012_motor', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 — `zap` (§4.2): voz neural para áudio de WhatsApp
    # (`servico_voz`, 5 vozes PT + reserva espeak) e `enviar_audio`
    # (anexo automatizado no Web). Marcador
    # `migracao_versao_zap_261017_voz_audio`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_zap_261017_voz_audio'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:zap', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:zap'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_zap_261017_voz_audio', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 16/10/2026 — nascimento do `mod_video` (AGENTS.md §4.2):
    # baixar vídeos (YouTube, Facebook, TikTok e outros via yt-dlp).
    # Marcador `migracao_versao_video_261016_nascimento`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261016_nascimento'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261016') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261016' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261016_nascimento', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 08/10/2026 — bump do `tisosdocfly` (AGENTS.md §4.2): fail-soft da
    # hora no boot (`bd_criador`) migrou de `_log_boot.exception` (com stack)
    # para `_log_boot.warning` via loguru — console mantém o print, o arquivo
    # não polui com traceback. Marcador próprio
    # `migracao_versao_tisosdocfly_261008_hora_failsoft`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261008_hora_failsoft'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261008') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261008' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261008_hora_failsoft', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 08/10/2026 — bump do `agregador_noticias` (AGENTS.md §4.2): o
    # filtro por tema "Tribunais de Contas" passou a intercalar 2 notícias do
    # TCE-MG para 1 das demais fontes (~2/3 do tribunal mineiro, cada grupo
    # da mais recente para a mais antiga; esgotado um grupo, o outro
    # completa). Marcador próprio
    # `migracao_versao_agregador_noticias_261008_tcemg`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_agregador_noticias_261008_tcemg'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:agregador_noticias', '1.0.261008') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261008' "
                    "WHERE chave='versao_modulo:agregador_noticias'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_agregador_noticias_261008_tcemg', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 08/10/2026 — bump do `usuarios` (AGENTS.md §4.2): o popup
    # (tooltip) da lista passa a mostrar folha ANTES dos módulos (módulos
    # sempre por último) e fica mais largo, com rolagem própria. Marcador
    # próprio `migracao_versao_usuarios_261008_tooltip_ordem`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261008_tooltip_ordem'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261008') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261008' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261008_tooltip_ordem', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 09/10/2026 — bump do `usuarios` (AGENTS.md §4.2): coleta do
    # detalhe por ficha (`coleta_kbp.py`: CPF parcial + vencimentos por
    # ficha, ritmo configurável) + correção do `RAIZ` da coleta da folha.
    # Marcador próprio `migracao_versao_usuarios_261009_coleta_detalhe`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261009_coleta_detalhe'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261009') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261009' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261009_coleta_detalhe', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 09/10/2026 (mesma versão) — card da ficha na administração:
    # `tb_config` (`usuarios_portal_url`, intervalos do detalhe), tabela
    # `tb_detalhe_ficha` + CPF no espelho (`tb_usuarios`), loader com regra
    # de CPF (mesmo parcial funde, distintos separam) e botões de coleta e
    # carga. Schema mora no `init_db` do módulo; aqui só o marcador.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261009_detalhe_cpf_ui'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261009') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261009' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261009_detalhe_cpf_ui', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 10/10/2026 — bump do `usuarios` (AGENTS.md §4.2): a ficha do
    # usuário sai do TOOLTIP de hover para o CLIQUE no nome, em diálogo, com
    # grade de duas colunas (usuário/cadastro, perfil/situação,
    # e-mail/telefone), a folha completa (remuneração, lotação e admissão
    # entraram no resumo) e os módulos em duas colunas com selo colorido pelo
    # papel que a pessoa tem em cada um. Marcador próprio
    # `migracao_versao_usuarios_261010_ficha_clique`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261010_ficha_clique'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261010') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261010' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261010_ficha_clique', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — bump de `mod_gest_cad_usuario` (§4.2): bypass de
    # teste `TISOSDOCFLY_QA_SEM_TROCA` (qacomum/qamaster nascem sem troca
    # obrigatória só com a variável; produção intacta). Marcador
    # `migracao_versao_usuarios_261011_qa_sem_troca`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261011_qa_sem_troca'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261011_qa_sem_troca', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 10/10/2026 — bump do `tisosdocfly` (AGENTS.md §4.2): o assistente
    # de ativação ganhou duas flags de utilitário. `--depencias` roda
    # `instalar_externos.py` (browsers do Playwright, gitleaks, k6) ANTES do
    # boot; `--popular` sobe o sistema e só então dispara
    # `coleta_kbp.py --atualizar` em 2º plano, num `app.on_startup` + thread.
    # Marcador próprio `migracao_versao_tisosdocfly_261010_flags_utilitarios`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261010_flags_utilitarios'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261010') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261010' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261010_flags_utilitarios', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 10/10/2026 — bump de versão de `mod_dados_abertos` (painel
    # mesclado folha+cadastro+contracheque+comissão, e correção do `ui.link`
    # que derrubava a abertura do conjunto de dados). Marcador próprio
    # `migracao_versao_dados_abertos_261010_painel_mesclado`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261010_painel_mesclado'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261010') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261010' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261010_painel_mesclado', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 10/10/2026 — terceira do dia em `mod_dados_abertos`: o NÍVEL DE
    # TRANSPARÊNCIA DO PNTP. Card novo na tela (o selo da prefeitura e a
    # comparação com as cidades cadastradas), tabela do estado atual e tabela
    # de histórico mensal, e a coleta no boot e no dia 5. Marcador
    # `migracao_versao_dados_abertos_261010_pntp`.
        # (10/10, quarto) rodapé padronizado dos cards: "Ver dados" a 100%
        # da base nos dois cards e "Ver dados" como rótulo único; os três
        # formatos dividem a base em 3 e centralizam quando quebram. Ver
        # `migracao_versao_dados_abertos_261010_pntp` (mesma versão do dia).
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261010_pntp'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261010') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261010' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261010_pntp', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — o log de TODO módulo vai para arquivo.
    #
    # O filtro do sink core era `not extra.get("modulo")`, o que fazia a
    # mensagem DESAPARECER quando o módulo não tinha sink próprio: ela era
    # rejeitada pelo core e não casava com nenhum sink de módulo. Medido em
    # 11/10/2026: 1.581 chamadas de `get_logger` em nove módulos iam só para o
    # console (`lista_telefonica` com 1.523), e as linhas de encerramento do
    # servidor — "sinal recebido" e "atexit" — nunca chegavam a arquivo.
    #
    # A regra agora é "quem não tem sink dedicado vai para o core". Marcador
    # `migracao_versao_tisosdocfly_261011_log_todo_modulo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261011_log_todo_modulo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261011_log_todo_modulo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — segunda do dia. bump de `mod_dados_abertos`: o card
    # parou de registrar clique (o clique no botão de download abria o painel e
    # "Ver dados" abria dois diálogos), o painel passou a usar id único por
    # instância (o segundo painel nascia vazio) e a exportação ganhou os blocos
    # de cadastro, contracheque e comissão, que a tela mostrava e o arquivo
    # não. Marcador `migracao_versao_dados_abertos_261011_card_sem_clique`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_card_sem_clique'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_card_sem_clique', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — terceira do dia. bump de `mod_dados_abertos`: o
    # painel do PNTP parou de repetir o selo duas vezes, "sem histórico" virou
    # uma nota única do conjunto, e a classificação passou a `display: grid`
    # (o `flex: 2fr` era CSS inválido e alinhava cada linha por si). Marcador
    # `migracao_versao_dados_abertos_261011_painel_pntp`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_painel_pntp'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_painel_pntp', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — quarta do dia. `mod_dados_abertos`: a cidade
    # principal do PNTP virou CONFIG (`pntp_cidade_principal` + `pntp_uf_principal`)
    # e o nome do órgão (`orgao_nome`) — quem baixa o sistema para outra
    # prefeitura troca no painel, sem mexer em código. Só INSERT (chaves novas:
    # instalação existente não tem, então não há o que preservar; e o valor do
    # admin, uma vez gravado, nunca é sobrescrito pelo seed). Versão inalterada
    # (1.0.261011, mesmo dia). Marcador
    # `migracao_versao_dados_abertos_261011_cidade_principal`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_cidade_principal'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('pntp_cidade_principal', 'Monte Santo de Minas') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('pntp_uf_principal', 'mg') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('orgao_nome', 'Prefeitura Municipal de Monte Santo de Minas') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_cidade_principal', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — quinta do dia. `mod_dados_abertos`: textos legais
    # enxutos no card (saiu o título "POR QUE CADA CARD...", os incisos II e III
    # por extenso e o parágrafo do PDF-legível; entra a citação curta do art.
    # 8º, § 3º). Versão inalterada (1.0.261011, mesmo dia). Marcador
    # `migracao_versao_dados_abertos_261011_textos_legais`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_textos_legais'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_textos_legais', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — sexta do dia. `mod_dados_abertos`: parágrafo do
    # DADO ABERTO justificado (`text-align: justify`). Versão inalterada
    # (1.0.261011, mesmo dia). Marcador
    # `migracao_versao_dados_abertos_261011_justify`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_justify'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_justify', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — sétima do dia. `mod_dados_abertos`: todos os textos
    # dos cards justificados (`text-align` herdado no container; linha única não
    # muda). Versão inalterada (1.0.261011, mesmo dia). Marcador
    # `migracao_versao_dados_abertos_261011_justify_todos`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_justify_todos'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_justify_todos', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — oitava do dia. `mod_dados_abertos`: "Cidade
    # principal" + "Comparação" fundidos no card único "Transparência PNTP"
    # (metades "1 — Sua cidade" / "2 — Comparar com", cidade+UF lado a lado,
    # hierarquia de botões) — só invólucro e visual, testids e lógica intactos.
    # Versão inalterada (1.0.261011, mesmo dia). Marcador
    # `migracao_versao_dados_abertos_261011_pntp_unico`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_pntp_unico'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_pntp_unico', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — nona do dia. `mod_dados_abertos`: os dois poderes
    # (Executivo + Legislativo lado a lado em gráfico, linhas "[nome] –
    # Executivo/Legislativo" no ranking, comparação temporária da sessão no
    # diálogo, interruptor da Câmara no admin). Semente de `pntp_avaliar_camara`
    # = 0 (opt-in: sem a decisão do admin, nada muda na tela). Versão
    # inalterada (1.0.261011, mesmo dia). Marcador
    # `migracao_versao_dados_abertos_261011_dois_poderes`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_dois_poderes'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('pntp_avaliar_camara', '0') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_dois_poderes', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — décima do dia. `mod_dados_abertos`: ranking
    # emparelhado (uma linha por cidade, 6 números), botões de ordenação por
    # poder no diálogo e ordem padrão do admin (`pntp_ordem_padrao`, fábrica
    # Executivo). Versão inalterada (1.0.261011, mesmo dia). Marcador
    # `migracao_versao_dados_abertos_261011_ordem_poder`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_ordem_poder'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('pntp_ordem_padrao', 'executivo') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_ordem_poder', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — 11ª do dia. `mod_dados_abertos`: gráfico com TODAS
    # as cidades (par grudado Exec+Legis, espaço entre cidades, cor do tema:
    # escura no Executivo, clareada no Legislativo) dentro da área atualizável.
    # Versão inalterada (1.0.261011, mesmo dia). Marcador
    # `migracao_versao_dados_abertos_261011_grafico_todas`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_grafico_todas'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_grafico_todas', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — 12ª do dia. `mod_dados_abertos`: KeyError ao ordenar
    # por Legislativo (`par[ordem]`), gráfico segue a ordem ativa, cores do
    # MÓDULO, selo com ícone por nível + ALTO RISCO no Básico, linha única
    # campo+Incluir+classificar. Versão inalterada (1.0.261011, mesmo dia).
    # Marcador `migracao_versao_dados_abertos_261011_fixes_pntp`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_fixes_pntp'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_fixes_pntp', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — 13ª do dia. `mod_dados_abertos`: cor do gráfico
    # pela MESMA conta do `aplicar_no_botao` (estilo->primaria_q; "Padrão"->
    # cor_botao do módulo, nunca cor_principal do sistema). Versão inalterada
    # (1.0.261011, mesmo dia). Marcador
    # `migracao_versao_dados_abertos_261011_cor_modulo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_cor_modulo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_cor_modulo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — 14ª do dia. `mod_dados_abertos`: selo na cor
    # efetiva de quem olha (`_cor_efetiva_usuario`, mesma do gráfico/botões;
    # nunca o azul da página do PNTP) com tinta por contraste. Versão
    # inalterada (1.0.261011, mesmo dia). Marcador
    # `migracao_versao_dados_abertos_261011_selo_efetivo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_selo_efetivo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_selo_efetivo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — 15ª do dia. `mod_dados_abertos`: pílulas de nível
    # nas linhas da classificação (fundo + ícone do mapa; selo segue quem
    # olha). Versão inalterada (1.0.261011, mesmo dia). Marcador
    # `migracao_versao_dados_abertos_261011_pilulas`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_pilulas'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_pilulas', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — 16ª do dia. `mod_dados_abertos`: tons claros no
    # mapa de níveis (Básico #FF9800, Inicial #E53935, Não Avaliado #E0E0E0,
    # mais claro que o prata). Versão inalterada (1.0.261011, mesmo dia).
    # Marcador `migracao_versao_dados_abertos_261011_tons_claros`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_tons_claros'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_tons_claros', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — 17ª do dia. `mod_dados_abertos`: bloco comissão
    # reordenado (acima, extras, dobro, total) com rótulos novos, nota sem o
    # "Como ler." + parágrafo de anomalias, export em paridade. Versão
    # inalterada (1.0.261011, mesmo dia). Marcador
    # `migracao_versao_dados_abertos_261011_comissao_ordem`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_comissao_ordem'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_comissao_ordem', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 — card "Receitas" (PortalFácil): tabelas espelho +
    # retrato, fonte semeada, coleta dia 5 por chave, export em paridade e o
    # fix do CSV vazio (`len(linha)` vs `len(linhas)`, valia p/ todo card).
    # Marcador `migracao_versao_dados_abertos_261012_receitas`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261012_receitas'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261012_receitas', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 — ano explícito + aviso de defasagem no card
    # Receitas (`defasado`, selo do exercício, aviso no export). Versão
    # inalterada (1.0.261012, mesmo dia). Marcador
    # `migracao_versao_dados_abertos_261012_defasagem`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261012_defasagem'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261012_defasagem', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 — bump do `tisosdocfly` (§4.2): migrations de receitas,
    # despesas e defasagem no `bd_conexao`. Marcador
    # `migracao_versao_tisosdocfly_261012_api_cards`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261012_api_cards'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261012_api_cards', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 13/10/2026 — bump do `tisosdocfly` (§4.2): banner de desconexão
    # em PT-BR (`language="pt-BR"` no `ui.run` + tabela `pt-BR`/`pt`
    # injetada em `nicegui_patch._aplicar_traducao_pt_br`, porque o NiceGUI
    # 3.15 não traz PT) e fase da operação no título da aba nos handlers
    # pesados de empenhos (pedido do responsável: mostrar a fase do erro).
    # Marcador `migracao_versao_tisosdocfly_261013_banner_ptbr`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261013_banner_ptbr'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261013') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261013' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261013_banner_ptbr', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 14/10/2026 — bump de versão do módulo tisosdocfly (flag
    # `--liberarFirewall`: regra de entrada do Firewall para a porta do
    # site). Marcador `migracao_versao_tisosdocfly_261014_liberar_firewall`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261014_liberar_firewall'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261014') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261014' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261014_liberar_firewall', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 14/10/2026 — bump de versão do módulo tisosdocfly (grupo
    # "Desativados" no hambúrguer: módulos desligados centralizados após o
    # Sair, com hover/focus). Marcador
    # `migracao_versao_tisosdocfly_261014_menu_desativados`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261014_menu_desativados'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261014') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261014' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261014_menu_desativados', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 14/10/2026 — bump de versão do módulo tisosdocfly (job mensal
    # `coleta_dados_abertos` no agendador + `reagendar_coleta_dados_abertos`
    # para a agenda do admin valer sem restart).
    # Marcador `migracao_versao_tisosdocfly_261014_coleta_agendada`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261014_coleta_agendada'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261014') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261014' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261014_coleta_agendada', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 15/10/2026 — bump de versão do módulo tisosdocfly (job
    # `coleta_dados_abertos` pelo distribuidor de coleta única).
    # Marcador `migracao_versao_tisosdocfly_261015_coleta_unica`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261015_coleta_unica'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261015') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261015' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261015_coleta_unica', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 10/10/2026 — bump de versão de `mod_lista_telefonica` (retirada
    # da matrícula real que um comentário reintroduziu ao documentar a remoção).
    # §4.2 obriga bump até em comentário, porque é o que diz ao rodapé qual
    # código o banco espera. Marcador
    # `migracao_versao_lista_telefonica_261010_matricula_comentario`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261010_matricula_comentario'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261010') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261010' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261010_matricula_comentario', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 — `mod_gest_cad_usuario`: diárias por favorecido
    # por ano (`tb_diarias`, ligada pelo CPF parcial), coleta no boot e após
    # o dia 10 (`coleta_diarias.py`, URL fábrica + `usuarios_diarias_url` no
    # painel), totais 2025/2026 no admin e bloco no perfil. Schema mora no
    # `init_db` do módulo; aqui só o marcador. Versão inalterada (1.0.261011,
    # mesmo dia). Marcador `migracao_versao_usuarios_261011_diarias`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261011_diarias'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261011_diarias', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 (mesma versão) — `mod_gest_cad_usuario`: ritmo
    # humano configurável na coleta de diárias (espera 2–6 s sorteada entre
    # páginas, `usuarios_diarias_intervalo_min_s/_max_s`), paginação no
    # tamanho que o portal aceita (25) e andamento visível no painel (barra
    # do ano em curso + último favorecido coletado). Schema intacto; aqui só
    # o marcador. Marcador `migracao_versao_usuarios_261011_diarias_ritmo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261011_diarias_ritmo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261011_diarias_ritmo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 (mesma versão) — `mod_gest_cad_usuario`: costura nº
    # 5 (`resumo_diarias_publico` + `integracoes.diarias_publicas`) — por ano:
    # total, maior, menor, média, mediana, moda, favorecidos + lista nominal
    # (nome + valor, sem CPF) para o card Servidores Públicos. Marcador
    # `migracao_versao_usuarios_261011_diarias_publico`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261011_diarias_publico'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261011_diarias_publico', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 (mesma versão) — `mod_dados_abertos`: fim do card
    # próprio de diárias (decisão do responsável: diária só é paga a
    # servidor, o dado mora no card Servidores Públicos). A fileira legada
    # `despesas_diarias` é apagada no `init_db` do módulo; a visão geral
    # ganha `_secao_diarias` (7 números por ano + lista sob expansão) e o
    # export `servidores_publicos` ganha a seção "Diárias recebidas".
    # Marcador `migracao_versao_dados_abertos_261011_diarias_na_visao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_diarias_na_visao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_diarias_na_visao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 (mesma versão) — `mod_dados_abertos`: diárias em
    # ordem decrescente de ano (2026 primeiro, só na tela), os 6 números em
    # caixas `da-kpi` e a lista nominal em terceira janela (botão
    # "Listar beneficiários"); a costura `resumo_diarias_publico()` segue
    # cronológica (export e perfil). Versão `1.0.261011` mantida.
    # Marcador `migracao_versao_dados_abertos_261011_diarias_layout`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_diarias_layout'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_diarias_layout', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 (mesma versão) — `mod_dados_abertos`: ajustes do
    # responsável na seção de diárias — botão "Listar beneficiários" DENTRO
    # da caixa do Total pago (verde #2E7D32), ano delimitado em cartão com
    # borda própria e saída do texto "Nome + valor pago..." da terceira
    # janela. Marcador
    # `migracao_versao_dados_abertos_261011_diarias_caixas`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_diarias_caixas'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_diarias_caixas', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 (mesma versão) — `mod_dados_abertos`: textos novos
    # do responsável na visão — título "Visão geral dos gastos com pessoal",
    # cabeçalho enxuto na cor do módulo (sem "coletado em", origem como
    # link inline), citação legal curta e fim do parágrafo da FORMA.
    # Marcador `migracao_versao_dados_abertos_261011_textos_visao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_textos_visao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_textos_visao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 (mesma versão) — `mod_dados_abertos`: saída do
    # bloco "Cadastro e liberação de acesso" do painel e do export
    # (decisão do responsável: perfil/situação do sistema é só do
    # administrador). Marcador
    # `migracao_versao_dados_abertos_261011_sem_cadastro`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_sem_cadastro'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_sem_cadastro', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 (mesma versão) — `mod_dados_abertos`: título do
    # contracheque com a contagem ("N Contracheques (competência)") e fim do
    # card redundante de fichas (pedido do responsável; vale na tela e no
    # export). Marcador
    # `migracao_versao_dados_abertos_261011_titulo_contracheque`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_titulo_contracheque'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_titulo_contracheque', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 (mesma versão) — `mod_dados_abertos`: deduplicação
    # pedida pelo responsável — legal vai para o subtítulo do diálogo (sai
    # do painel), card "Servidores" sai (o total mora só no cabeçalho) e a
    # mediana perde o "1.159 com valor". Marcador
    # `migracao_versao_dados_abertos_261011_sem_duplicar`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_sem_duplicar'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_sem_duplicar', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 (mesma versão) — `mod_dados_abertos`: Lotação e
    # Cargos mostram TODOS (do maior para o menor, com scroll) em vez de
    # top 12 (pedido do responsável). Marcador
    # `migracao_versao_dados_abertos_261011_lotacao_cargos_todos`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_lotacao_cargos_todos'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_lotacao_cargos_todos', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 (mesma versão) — `mod_dados_abertos`: fileiras das
    # distribuições da folha — primeira fileira com Situação, Vínculo e
    # Secretaria (3 por linha) e segunda com Lotação e Cargos (2 por linha);
    # telas pequenas empilham 1 por linha. Só LAYOUT dos contêineres.
    # Marcador `migracao_versao_dados_abertos_261011_distribuicao_fileiras`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_distribuicao_fileiras'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_distribuicao_fileiras', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 11/10/2026 (mesma versão) — `mod_dados_abertos`: barras
    # legíveis nos cards Secretaria, Lotação e Cargos — o RÓTULO cresce
    # (`flex: 1`, com `ellipsis` + `title=` de segurança) e a TRILHA encolhe
    # (largura máxima menor); "Secretaria Municipal" vira "Sec. Mun." SÓ no
    # prefixo, com o nome completo no `title=`. Só LAYOUT e rótulo exibido.
    # Marcador `migracao_versao_dados_abertos_261011_barras_legiveis`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261011_barras_legiveis'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261011') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261011' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261011_barras_legiveis', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 — `mod_dados_abertos`: título do contracheque sem
    # a contagem (regra do responsável: quantidade de gente SÓ no
    # cabeçalho). É o ÚLTIMO da cadeia porque a versão do dia (1.0.261012)
    # é de quem escreve por último. Marcador
    # `migracao_versao_dados_abertos_261012_titulo_sem_numero`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261012_titulo_sem_numero'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261012_titulo_sem_numero', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 (mesma versão) — `mod_dados_abertos`: demonstrativo
    # de verbas com TODAS as rubricas (mostra 5 + scroll) em vez de só as 14
    # maiores (pedido do responsável). Marcador
    # `migracao_versao_dados_abertos_261012_verbas_todas`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261012_verbas_todas'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261012_verbas_todas', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 (mesma versão) — `mod_dados_abertos`: seção "Quem
    # recebe por comissão" (dois cards por rubrica + terceira janela
    # nominal) ANTES das diárias na visão (pedido do responsável).
    # Marcador `migracao_versao_dados_abertos_261012_comissao_verbas`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261012_comissao_verbas'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261012_comissao_verbas', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 — `mod_gest_cad_usuario`: `resumo_comissao_por_verba`
    # + costura `comissao_por_verba` (quem recebe por rubrica de comissão,
    # com valor). Schema intacto; aqui só o marcador. Marcador
    # `migracao_versao_usuarios_261012_comissao_por_verba`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261012_comissao_por_verba'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261012_comissao_por_verba', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 (mesma versão) — `mod_gest_cad_usuario`: comparação
    # de proventos por cargo (acima da mediana + concursado/contratado) e a
    # seção na aba da folha. Marcador
    # `migracao_versao_usuarios_261012_proventos_cargo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261012_proventos_cargo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261012_proventos_cargo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 15/10/2026 — `qacomum`/`qamaster` SEM troca forçada, sempre
    # (decisão do responsável: são contas de teste e os scripts usam
    # `123456` direto, sem fluxo de login — o bypass por variável de
    # ambiente de 11/10/2026 virou regra). Zera `forcar_troca:<conta>` no
    # banco EM USO (banco novo já nasce zerado pelo seed) e sobe a versão.
    # Posição proposital: é a ÚLTIMA migração de `usuarios` do arquivo,
    # para nenhum bloco anterior (`261011_diarias*`, que gravam 1.0.261011)
    # rebaixar a versão depois. Marcador
    # `migracao_versao_usuarios_261015_qa_sem_troca`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261015_qa_sem_troca'")
    if (cur.fetchone()[0] or 0) == 0:
        for _qa_conta in ("qacomum", "qamaster"):
            cur.execute("INSERT INTO tb_config (chave, valor) VALUES (?, '0') "
                        "ON CONFLICT DO NOTHING",
                        (f"forcar_troca:{_qa_conta}",))
            cur.execute("UPDATE tb_config SET valor='0' WHERE chave=?",
                        (f"forcar_troca:{_qa_conta}",))
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261015') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261015' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261015_qa_sem_troca', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 (mesma versão) — `mod_dados_abertos`: seção
    # "Proventos por cargo" na visão Servidores Públicos (seletor + pares
    # + concursado/contratado; costura `proventos_por_cargo` sem user_nome).
    # Marcador `migracao_versao_dados_abertos_261012_proventos_cargo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261012_proventos_cargo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261012_proventos_cargo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 (mesma versão) — `mod_dados_abertos`: botão "Ver
    # lista completa por cargo" (59 cargos agrupados em terceira janela).
    # Marcador `migracao_versao_dados_abertos_261012_lista_completa`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261012_lista_completa'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261012_lista_completa', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 (mesma versão) — `mod_dados_abertos`: proventos
    # por cargo 100% agregado (tabela cargo/média/extremos ±1000, sem nomes,
    # sem seletor, sem terceira janela). Marcador
    # `migracao_versao_dados_abertos_261012_proventos_agregado`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261012_proventos_agregado'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261012_proventos_agregado', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 (mesma versão) — `mod_dados_abertos`: barras das
    # distribuições da folha com ESCALA ÚNICA — o denominador passa a ser o
    # máximo global das distribuições (na prática o total da folha), e não
    # mais o máximo de cada card (que desenhava 567 e 1.076 do mesmo
    # tamanho); a trilha tem tamanho único em todos os cards (~4 cm no
    # desktop). Só LAYOUT e denominador das barras. É o ÚLTIMO da cadeia
    # porque a versão do dia (1.0.261012) é de quem escreve por último.
    # Marcador `migracao_versao_dados_abertos_261012_barras_escala_unica`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261012_barras_escala_unica'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261012_barras_escala_unica', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 — card "Despesas" (PortalFácil): tabelas espelho +
    # retrato (`tb_api_despesas`/`tb_api_despesas_mes`), fonte semeada,
    # coleta dia 5 por chave, export em paridade e diálogo em paridade.
    # Marcador `migracao_versao_dados_abertos_261012_despesas`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261012_despesas'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261012_despesas', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 (mesma versão) — card "Pagamentos" (PortalFácil):
    # tabelas espelho + retrato (`tb_api_pagamentos`/`tb_api_pagamentos_mes`),
    # fonte semeada, coleta dia 5 por chave, export em paridade e diálogo em
    # paridade. MEDIDO: o portal ignora `numAno` (2025/2026 devolvem 2019),
    # então a competência é o exercício real do item (filtro local).
    # Marcador `migracao_versao_dados_abertos_261012_pagamentos`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261012_pagamentos'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261012_pagamentos', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 (mesma versão) — card "Extras" (PortalFácil):
    # tabelas espelho + retrato (`tb_api_extras`/`tb_api_extras_mes`),
    # fonte semeada, coleta dia 5 por chave, export em paridade e diálogo em
    # paridade. MEDIDO: `extrasano` devolve 8 anos (vigente 2026),
    # `extrasdatareferencia` "02/09/2026", campos `descConta/descFornecedor/
    # tpExtra(D/C)/vlExtra(vírgula)/dtMovimento/numExercicio/numExtra`.
    # Marcador `migracao_versao_dados_abertos_261012_extras`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261012_extras'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261012_extras', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 12/10/2026 (mesma versão) — card "Contratos" (PortalFácil):
    # tabelas espelho + retrato (`tb_api_contratos`/`tb_api_contratos_mes`),
    # fonte semeada, coleta dia 5 por chave, export em paridade e diálogo em
    # paridade. MEDIDO (2 itens, 3 requests): `contratosdataatualizacao`
    # "09/09/2026 00:01:33", `contratosdatareferencia` "03/09/2026"; filtro
    # por JANELA (`dtInicio=01/01/AAAA&dtFim=31/12/AAAA`), competência local
    # pelo ano de `dtInicio`; campos `numContrato/numProcesso/numCpfCnpj/
    # descForn/descObjeto/vlContrato(ponto)/dtInicio/dtFim(DD/MM/AAAA)/
    # dsLicitacao/aparada/nmModalidade/aditivos[]/itens[]`.
    # Marcador `migracao_versao_dados_abertos_261012_contratos`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261012_contratos'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261012') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261012' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261012_contratos', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 13/10/2026 — grade com teto de 4 cards por linha e botões
    # PDF/CSV/JSON com a mesma altura (pedido do responsável: o JSON nascia
    # mais alto porque o conteúdo quebrava em duas linhas).
    # Marcador `migracao_versao_dados_abertos_261013_grade_4col`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261013_grade_4col'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261013') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261013' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261013_grade_4col', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 14/10/2026 — bump de versão do módulo dados_abertos (contagem
    # "N conjunto(s) de dados" removida da tela).
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261014_sem_contagem'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261014') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261014' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261014_sem_contagem', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 14/10/2026 — cabeçalho com o fundamento legal (pedido do
    # responsável): o subtítulo passa a citar o art. 8º, § 3º da LAI. Só
    # preenche valor vazio ou igual ao antigo padrão — personalização que o
    # administrador tenha gravado em Aparência é preservada.
    # Marcador `migracao_versao_dados_abertos_261014_cabecalho_legal`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261014_cabecalho_legal'")
    if (cur.fetchone()[0] or 0) == 0:
        _novo_subtitulo = (
            "Dados abertos publicados pela prefeitura. - O art. 8º, § 3º "
            "da Lei nº 12.527/2011 (Lei de Acesso à Informação) obriga o "
            "sítio do órgão a atender, entre outros, a dois requisitos: "
            "possibilitar a gravação de relatórios e possibilitar o acesso "
            "automatizado por sistemas externos em formatos abertos.")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261014') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261014' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('dados_abertos_texto_header', ?) "
                    "ON CONFLICT DO NOTHING", (_novo_subtitulo,))
        cur.execute("UPDATE tb_config SET valor=? "
                    "WHERE chave='dados_abertos_texto_header' "
                    "AND (valor IS NULL OR valor='' "
                    "OR valor='Dados abertos publicados pela prefeitura.')",
                    (_novo_subtitulo,))
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261014_cabecalho_legal', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 14/10/2026 — bump de versão do módulo dados_abertos (card
    # "Coleta PortalFácil" no admin: coletar agora por ponto + agenda
    # mensal; dia configurável no miolo).
    # Marcador `migracao_versao_dados_abertos_261014_coleta_admin`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261014_coleta_admin'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261014') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261014' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261014_coleta_admin', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 15/10/2026 — bump de versão do módulo dados_abertos (URL
    # única configurável + progresso ao vivo da coleta no admin).
    # Marcador `migracao_versao_dados_abertos_261015_coleta_url_progresso`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261015_coleta_url_progresso'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261015') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261015' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261015_coleta_url_progresso', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 15/10/2026 — bump de versão do módulo dados_abertos (coleta
    # única: distribuidor `coletar_ponto` + botões inoperantes na coleta).
    # Marcador `migracao_versao_dados_abertos_261015_coleta_unica`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261015_coleta_unica'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261015') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261015' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261015_coleta_unica', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 15/10/2026 — bump de versão do módulo dados_abertos (revisão
    # QA dos coletores + URL geral sem ponto no fim).
    # Marcador `migracao_versao_dados_abertos_261015_coleta_qa_geral`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261015_coleta_qa_geral'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261015') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261015' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261015_coleta_qa_geral', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 15/10/2026 — bump de versão do módulo lista_telefonica (PDF
    # do resultado filtrado no molde da lista fixa: botão único "Baixar
    # PDF" no recorte em vez de Imprimir + Baixar, colunas Nome | Cargo |
    # Telefone, multipágina).
    # Marcador `migracao_versao_lista_telefonica_261015_pdf_resultado`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261015_pdf_resultado'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261015') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261015' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261015_pdf_resultado', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 16/10/2026 — bump de `mod_gest_cad_usuario` (§4.2): linha de
    # inclusão do telefone no admin em [De quem é=particular, Tipo=celular,
    # DDI 12ch, Número 15ch, Disponibilizar, Adicionar]; DDD obrigatório no
    # BR ((xx)xxxx-xxxx fixo, (xx)xxxxx-xxxx celular, exibido via
    # `formatar_para_exibicao`); "Disponibilizar" é o consentimento
    # (`visivel`) com confirmação dupla (agenda + mensagens/notificações +
    # remoção a qualquer momento); `telefone_e_publicavel` passa a publicar
    # particular marcado. Marcador
    # `migracao_versao_usuarios_261016_telefone_publicavel`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261016_telefone_publicavel'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261016') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261016' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261016_telefone_publicavel', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 16/10/2026 (mesma versão) — `mod_gest_cad_usuario`: correção
    # do `_normalizar_telefone_cadastro` (o canônico `+55`+11 dígitos era
    # mutilado para `+31999999999` e a tela lia como Bulgária), lista do
    # admin redesenhada DENTRO da coluna (`with caixa:`, sem isso o número
    # recém-gravado não aparecia) e número sempre completo com DDI
    # (`formatar_para_exibicao`). Versão inalterada (1.0.261016, mesmo dia).
    # Marcador `migracao_versao_usuarios_261016_tel_lista_ddi`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261016_tel_lista_ddi'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261016') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261016' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261016_tel_lista_ddi', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 16/10/2026 (mesma versão) — `mod_gest_cad_usuario`: lista de
    # telefones do admin em colunas (Número | De quem | Agenda | ações) com
    # selos — Prefeitura em vermelho, Particular em verde, "Na agenda" em
    # verde e "Restrito" em cinza. Versão inalterada (1.0.261016, mesmo dia).
    # Marcador `migracao_versao_usuarios_261016_tel_selos`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261016_tel_selos'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261016') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261016' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261016_tel_selos', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 16/10/2026 (mesma versão) — `mod_gest_cad_usuario`: marca
    # WhatsApp por telefone — coluna `whatsapp` em `tb_telefone_usuario`
    # (banco novo já nasce com ela; banco em uso ganha por ALTER), escrita
    # em `adicionar_telefone`/`editar_telefone`/`registrar_contatos` e
    # leitura em `listar_telefones` (índice 8, para outros módulos), coluna
    # na lista do admin e checkbox "É WhatsApp" no cadastro e na edição.
    # Versão inalterada (1.0.261016, mesmo dia). Marcador
    # `migracao_versao_usuarios_261016_tel_whatsapp`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261016_tel_whatsapp'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261016') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261016' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261016_tel_whatsapp', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 16/10/2026 (mesma versão) — `mod_gest_cad_usuario`: cartões
    # de telefone em grade responsiva (3 colunas em tela grande, 2 em
    # ≤1100px, 1 em ≤720px). Versão inalterada (1.0.261016, mesmo dia).
    # Marcador `migracao_versao_usuarios_261016_tel_grade`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261016_tel_grade'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261016') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261016' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261016_tel_grade', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 16/10/2026 (mesma versão) — `mod_gest_cad_usuario`: grade com
    # 4 colunas em tela grande (2 em ≤1100px, 1 em ≤720px), contador ocupando
    # a fileira inteira (`grid-column: 1 / -1`, sem isso ele virava célula e
    # quebrava o 1º cartão) e fundo do cartão na cor do módulo bem clara
    # (`tom_clara` sobre `cor_botao`). Versão inalterada (1.0.261016, mesmo
    # dia). Marcador `migracao_versao_usuarios_261016_tel_grade_4`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261016_tel_grade_4'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261016') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261016' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261016_tel_grade_4', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 16/10/2026 — bump de `tisosdocfly` (§4.2): máscara de entrada do
    # telefone com 11 casas (`(##) #####-####`; a de 12 nunca enchia e o
    # número digitado não era gravado) e `formatar_br` com o 9 isolado no
    # celular (`+55 (35) 9 8818-3288`). Marcador
    # `migracao_versao_tisosdocfly_261016_formato_telefone`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261016_formato_telefone'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261016') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261016' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261016_formato_telefone', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 — bump do `video` (§4.2): stage com expiração
    # (`expira_em`, 10 min configuráveis via `video_expiracao_min`),
    # biblioteca do sistema (publicar/despublicar, sem expiração,
    # `/midia_video`), player (assistir), entrega automática ao comum
    # (desce ao PC e sai do servidor) e ZIP em grupo. Marcador
    # `migracao_versao_video_261017_biblioteca`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_biblioteca'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_biblioteca', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 — bump do `tisosdocfly` (§4.2, mesma versão do dia):
    # job `cleanup_video` (1 min, `rotinas.py`) + fachada da biblioteca
    # (`integracoes.listar_videos_publicados`, base para as filas). Marcador
    # `migracao_versao_tisosdocfly_261017_video_limpeza`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261017_video_limpeza'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261017_video_limpeza', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): o admin exclui o
    # vídeo do stage já baixado (botão na linha do pronto + no diálogo do
    # recém-baixado). Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_admin_excluir`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_admin_excluir'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_admin_excluir', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): comum vê só o
    # card de baixar (stage e biblioteca só para admin) + ffmpeg no
    # `instalar_externos.py` (`--ffmpeg`, por SO) + barra de progresso por
    # pedido (hook do yt-dlp por bytes, fila paralela). Versão inalterada
    # (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_tela_comum`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_tela_comum'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_tela_comum', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): download em curso
    # pode ser cancelado (mata o yt-dlp, elimina o trabalho) e falha ganha
    # botão de excluir. Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_cancelar_download`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_cancelar_download'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_cancelar_download', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): pré-checagem de
    # arquivo único (sem trilhas + sem ffmpeg = aviso direto ao admin
    # geral, sem tentativa cega) + fallback CLI via `python -m yt_dlp`
    # (binário ausente não é mais "baixador indisponível"). Versão
    # inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_formato_unico`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_formato_unico'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_formato_unico', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): verificar antes
    # de baixar (botão só libera após a verificação), formatos reais do
    # vídeo e playlist com escolha de itens. Versão inalterada (1.0.261017,
    # mesmo dia). Marcador `migracao_versao_video_261017_verificar`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_verificar'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_verificar', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): marcar/desmarcar
    # todos na playlist. Versão inalterada (1.0.261017, mesmo dia).
    # Marcador `migracao_versao_video_261017_marcar_todos`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_marcar_todos'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_marcar_todos', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): sair da página
    # no meio da verificação/download não gera mais stack no log
    # (`_foi_desconexao`) + aviso honesto quando só há áudio sem ffmpeg.
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_sem_stack_saida`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_sem_stack_saida'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_sem_stack_saida', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): sem ffmpeg, a
    # playlist só oferece o baixável (arquivo único/áudio); opção de vídeo
    # que não desce nem aparece. Versão inalterada (1.0.261017, mesmo dia).
    # Marcador `migracao_versao_video_261017_so_baixavel`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_so_baixavel'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_so_baixavel', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): verificar em
    # linha própria abaixo do link; formato e baixar nascem inativos e só
    # liberam após verificar, com áudio como padrão. Versão inalterada
    # (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_layout_verificar`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_layout_verificar'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_layout_verificar', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): episódios entre
    # o link e os botões; marcar/desmarcar antes do baixar (só playlist).
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_ordem_botoes`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_ordem_botoes'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_ordem_botoes', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): servidor
    # concluiu = desce para o PC na hora (todo perfil; admin mantém o
    # stage) + botão "Salvar no PC" reserva na barra. Versão inalterada
    # (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_entrega_auto`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_entrega_auto'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_entrega_auto', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): todos os botões
    # no padrão do sistema (`ui_comum.botao`) + barra concluída com Baixar,
    # Excluir arquivo e Salvar no PC. Versão inalterada (1.0.261017, mesmo
    # dia). Marcador `migracao_versao_video_261017_botoes_padrao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_botoes_padrao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_botoes_padrao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): todos os botões
    # idênticos (primario, cor do tema), Interromper sempre visível (só
    # habilitado baixando) e andamento em grade 3/2/1. Versão inalterada
    # (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_uniforme`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_uniforme'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_uniforme', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): andamento em
    # grade fluida (auto-fit: sempre ocupa a linha) + cartão e barra
    # maiores. Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_grade_fluida`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_grade_fluida'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_grade_fluida', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): stage com TTL
    # para todo perfil (admin incluso) + contagem regressiva ao vivo no
    # "Concluído" e no histórico + título em 1 linha com rolagem lateral.
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_ttl_total`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_ttl_total'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_ttl_total', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): download
    # sobrevive à navegação (reatacha barras ao voltar, só as próprias;
    # pendente órfão vira erro). Versão inalterada (1.0.261017, mesmo dia).
    # Marcador `migracao_versao_video_261017_sobrevive_tela`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_sobrevive_tela'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_sobrevive_tela', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): 3 downloads por
    # vez, resto em fila (26 paralelos derrubavam a conexão e tomavam 403).
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_fila_3`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_fila_3'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_fila_3', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): "Meus arquivos"
    # para todo perfil + reconciliação no boot + 2 vagas. Versão inalterada
    # (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_meus_arquivos`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_meus_arquivos'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_meus_arquivos', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): Meus arquivos
    # na mesma grade dos em andamento (cartão + Interromper/Excluir/
    # Baixar). Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_grade_arquivos`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_grade_arquivos'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_grade_arquivos', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): varredura de
    # órfãos no stage (resto de queda/ZIP/.part sem dono sai no TTL).
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_varredura_orfaos`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_varredura_orfaos'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_varredura_orfaos', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): Meus arquivos
    # estilo PDF (checkbox um/todos + Excluir/ZIP/separados). Versão
    # inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_sel_pdf`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_sel_pdf'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_sel_pdf', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): Meus arquivos
    # vira tabela do PDF (checkbox nativo, badge de expiração, menu).
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_tabela_pdf`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_tabela_pdf'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_tabela_pdf', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): sai o Baixar ZIP
    # (não entregava); "Baixar separados" vira "Baixar", centralizado com
    # Excluir. Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_sem_zip`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_sem_zip'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_sem_zip', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): sem ffmpeg, um
    # áudio por formato (M4A/Opus/…) em vez de "original" único; MP3 de
    # verdade segue exigindo ffmpeg. Versão inalterada (1.0.261017, mesmo
    # dia). Marcador `migracao_versao_video_261017_audios`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_audios'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_audios', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): seleção lia o
    # evento como dict e nunca marcava (é lista) + expira legada estimada
    # pelo mtime. Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_sel_lista`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_sel_lista'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_sel_lista', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): comum mantém o
    # arquivo até o TTL (fim do apago em 10 s; ZIP/separados precisam
    # dele). Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_fica_ate_ttl`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_fica_ate_ttl'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_fica_ate_ttl', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): volta o Baixar
    # ZIP com entrega via cliente capturado. Versão inalterada (1.0.261017,
    # mesmo dia). Marcador `migracao_versao_video_261017_zip_cliente`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_zip_cliente'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_zip_cliente', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): 403 tenta 1x
    # após 15 s, erro vira mensagem clara e título gravado no pedido.
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_erro_403`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_erro_403'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_erro_403', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): arquivo nasce
    # como `usuario_datahora_titulo[id]-pid.ext` (dono visível no disco).
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_nome_dono`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_nome_dono'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_nome_dono', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): auditoria com
    # arquivo/formato/plataforma/tamanho + aviso de uso legítimo em
    # negrito. Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_auditoria_uso`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_auditoria_uso'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_auditoria_uso', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): spinner + frases
    # na verificação e TODOS os formatos do vídeo (por id, com tamanho).
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_todos_formatos`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_todos_formatos'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_todos_formatos', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): capa do vídeo
    # (miniatura) gravada no pedido e exibida como `poster` no player;
    # backfill na conclusão e no primeiro Assistir. Versão inalterada
    # (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_miniatura`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_miniatura'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_miniatura', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): modo fala
    # (EASTER EGG — NÃO DOCUMENTAR).
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_fala`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_fala'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_fala', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): voz neural
    # Edge pt-BR no modo fala (EASTER EGG — NÃO DOCUMENTAR).
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_fala_edge`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_fala_edge'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_fala_edge', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2 + §8.7): marca
    # o bloco fala como EASTER EGG (sai de docs/, fica no código).
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_easter_egg`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_easter_egg'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_easter_egg', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `video` (§4.2): "Processar e
    # preparar para download" no servidor; concluído tem Baixar
    # (tisosdocfly→PC) + Excluir; Interromper só durante o download. Versão
    # inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_video_261017_papeis_botoes`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_video_261017_papeis_botoes'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:video', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:video'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_video_261017_papeis_botoes', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 — bump do `usuarios` (§4.2): `video` entra no
    # acesso padrão do usuário novo + liberação única aos já cadastrados
    # (`migracao_acesso_video_261017` no `init_db` da gestão). Marcador
    # `migracao_versao_usuarios_261017_acesso_video`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261017_acesso_video'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261017_acesso_video', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — bump do `usuarios` (§4.2):
    # `buscar_usuarios_para_lista` filtra também pelo telefone da empresa.
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_usuarios_261017_busca_fone`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261017_busca_fone'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261017_busca_fone', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — bump do `usuarios` (§4.2): `zap`
    # entra no acesso padrão do usuário novo + liberação única aos já
    # cadastrados (`migracao_acesso_zap_261017` no `init_db` da gestão).
    # Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_usuarios_261017_acesso_zap`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261017_acesso_zap'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261017_acesso_zap', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 — bump do `tisosdocfly` (§4.2): job `cleanup_video`
    # (1 min, `rotinas.py`) + fachada da biblioteca
    # (`integracoes.listar_videos_publicados`, base para as filas). Marcador
    # `migracao_versao_tisosdocfly_261017_video_limpeza`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261017_video_limpeza'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261017_video_limpeza', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 — `lista_telefonica` (§4.2): o card "Faixas de
    # telefone da prefeitura" muda de /configuracoes (aba Telefones) para
    # /admin/lista_telefonica. O serviço (`telefone_faixas.py`) fica no
    # núcleo (a validação é usada pelo cadastro de usuários). Marcador
    # `migracao_versao_lista_telefonica_261017_faixas`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261017_faixas'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261017_faixas', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 (mesma versão) — `lista_telefonica` (§4.2):
    # listas de contatos por categoria (`tb_lista_contato*`, partilha com
    # colegas). Versão inalterada (1.0.261017, mesmo dia). Marcador
    # `migracao_versao_lista_telefonica_261017_listas`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261017_listas'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261017_listas', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 — `lista_telefonica` (§4.2): agenda privada
    # (`tb_contato_pessoal`, só o dono vê) com Ligar e WhatsApp (texto via
    # motor/wa.me, áudio via voz neural). Marcador
    # `migracao_versao_lista_telefonica_261017_contato_pessoal`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261017_contato_pessoal'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261017_contato_pessoal', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 17/10/2026 — `tisosdocfly` (§4.2): a aba "Telefones" sai de
    # /configuracoes (`tela_configuracoes.py`: tab + painel removidos).
    # Marcador `migracao_versao_tisosdocfly_261017_faixas_para_lista`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261017_faixas_para_lista'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261017') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261017' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261017_faixas_para_lista', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 18/10/2026 — bump de versão do `mod_gest_cad_usuario` (§4.2):
    # espelho com TODOS os telefones liberados por usuário
    # (`telefones_publicaveis_todos_em_lote` + `telefones` no
    # `listar_para_lista_telefonica`). Marcador
    # `migracao_versao_usuarios_261018_todos_tels`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261018_todos_tels'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261018') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261018' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261018_todos_tels', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 18/10/2026 — bump de versão do `mod_lista_telefonica`
    # (§4.2): coluna `telefones_json` (todos os liberados por contato, com
    # WhatsApp), card com scroll + ligar/zap por número, PDF com todos os
    # números, e escolha de listas no cadastro/edição do contato pessoal.
    # Marcador `migracao_versao_lista_telefonica_261018_tels_json`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261018_tels_json'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261018') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261018' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261018_tels_json', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 18/10/2026 — bump de versão do `mod_zap` (§4.2): trava de
    # lançamento (uma operação de navegador por vez), navegador por
    # usuário e guarda de memória. Marcador
    # `migracao_versao_zap_261018_trava`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_zap_261018_trava'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:zap', '1.0.261018') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261018' "
                    "WHERE chave='versao_modulo:zap'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_zap_261018_trava', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 18/10/2026 — bump de versão do `mod_tisosdocfly` (§4.2): novo
    # gateway `dados_usuario_lista_gestao`, que devolve nome, cargo, unidade e
    # telefone de UM usuário para a lista telefônica mostrar quem recebeu a
    # partilha como cartão de contato. Marcador
    # `migracao_versao_tisosdocfly_261018_dados_pessoa`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261018_dados_pessoa'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261018') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261018' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261018_dados_pessoa', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 20/10/2026 — bump do `hora_certa` (§4.2): botões pela
    # fábrica central `mod_tisosdocfly.ui_comum.botao` ("Sincronizar agora" e
    # "Salvar horário" em `telas.py`), com `data-testid`, ícone, handler
    # async, trava de reentrância e spinner preservados. Marcador
    # `migracao_versao_hora_certa_261020_botao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261020_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261020') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261020' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261020_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 20/10/2026 — bump do `zap` (§4.2): botões pela fábrica
    # central `mod_tisosdocfly.ui_comum.botao` ("Salvar" e "Verificar conexão"
    # em `telas.py`), com `data-testid`, ícone, handler async
    # (`run.io_bound`), trava de reentrância e disable/enable preservados.
    # Marcador `migracao_versao_zap_261020_botao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_zap_261020_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:zap', '1.0.261020') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261020' "
                    "WHERE chave='versao_modulo:zap'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_zap_261020_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 20/10/2026 — bump do `tecnico` (§4.2): botões pela
    # fábrica central `mod_tisosdocfly.ui_comum.botao` ("Atualizar" em
    # `telas_administracao.py` e "Fechar" do diálogo de prévia em
    # `telas.py`), com ícone, handler (`render`/`dlg.close`) e classe
    # `mt-2` preservados. Marcador
    # `migracao_versao_tecnico_261020_botao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tecnico_261020_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tecnico', '1.0.261020') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261020' "
                    "WHERE chave='versao_modulo:tecnico'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tecnico_261020_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 20/10/2026 — bump do `estoque` (§4.2): botões pela
    # fábrica central `mod_tisosdocfly.ui_comum.botao` ("Retirar" em
    # `telas_administracao.py` e "Cancelar" do diálogo de atendimento em
    # `telas.py`), com handler (`_retirar_vinculo`/`dlg.close`), `dense` e
    # `data-testid` preservados. Marcador
    # `migracao_versao_estoque_261020_botao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_estoque_261020_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:estoque', '1.0.261020') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261020' "
                    "WHERE chave='versao_modulo:estoque'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_estoque_261020_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 20/10/2026 — bump do `dados_abertos` (§4.2): botões ícone da
    # comparação PNTP pela fábrica central
    # `mod_tisosdocfly.ui_comum.botao_icone` ("close" em
    # `telas.py: _celula_municipio` e "delete" em
    # `telas_administracao.py: _linha_comparacao_pntp`), com closure
    # `on_click`, `data-testid` (`pntp-remover-temp`/`pntp-remover`),
    # `tooltip` e `cor="negative"` preservados. Marcador
    # `migracao_versao_dados_abertos_261020_botao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261020_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261020') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261020' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261020_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 20/10/2026 — bump do `dados_abertos` (§4.2): formulário do
    # registro de fontes passa a expor descricao, icone e ordem (Achado 13 da
    # analise) em vez de criar toda fonte com descricao vazia, icone 'public' e
    # ordem 100. Marcador
    # `migracao_versao_dados_abertos_261020_formulario_fonte`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261020_formulario_fonte'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261020') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261020' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261020_formulario_fonte', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 21/10/2026 — bump do `dados_abertos` (§4.2): remove a constante
    # morta TIPOS_UNIDADE (achados 8/12 da analise) e ajusta o seed para
    # 1.0.261021. Marcador
    # `migracao_versao_dados_abertos_261021_codigo_morto`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261021_codigo_morto'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261021') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261021' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261021_codigo_morto', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 21/10/2026 — bump do `dados_abertos` (§4.2): `data-testid` no
    # card do conjunto de dados (achado 10 da analise) para o E2E abrir o
    # card por seletor estável (`dados-abertos-card-<chave>`). Marcador
    # `migracao_versao_dados_abertos_261021_card_testid`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261021_card_testid'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261021') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261021' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261021_card_testid', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 21/10/2026 — bump do `dados_abertos` (§4.2): o liga/desliga
    # da fonte audita com o administrador logado (achado 2 da analise) em
    # vez do ator fixo "sistema". Marcador
    # `migracao_versao_dados_abertos_261021_ator_auditoria`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261021_ator_auditoria'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261021') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261021' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261021_ator_auditoria', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 21/10/2026 — bump do `dados_abertos` (§4.2): link externo do
    # card PNTP só renderiza com esquema http(s) (achado 7 da analise);
    # outro esquema vira texto puro. Marcador
    # `migracao_versao_dados_abertos_261021_link_seguro`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261021_link_seguro'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261021') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261021' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261021_link_seguro', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 21/10/2026 — bump do `dados_abertos` (§4.2): `montar_painel`
    # recebe os três blocos prontos do chamador async via `run.io_bound`
    # (achado 4 da analise) em vez de ler folha+bancos no event-loop.
    # Marcador `migracao_versao_dados_abertos_261021_io_bound`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_dados_abertos_261021_io_bound'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:dados_abertos', '1.0.261021') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261021' "
                    "WHERE chave='versao_modulo:dados_abertos'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_dados_abertos_261021_io_bound', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 20/10/2026 — bump do `usuarios` (§4.2): botões do bloco de
    # telefones do admin pela fábrica central `mod_tisosdocfly.ui_comum`
    # (`botao_icone` "edit" cor primary e "delete" cor negative em
    # `telas.py: _bloco_telefones_admin`, mais `botao` "Cancelar"/"Voltar"
    # variante texto nos diálogos de edição e publicação), com `on_click`,
    # `tooltip`, `data-testid` e `shrink-0` preservados. Marcador
    # `migracao_versao_usuarios_261020_botao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261020_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261020') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261020' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261020_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 20/10/2026 — bump do `agregador_noticias` (§4.2): botões
    # ícone pela fábrica central `mod_tisosdocfly.ui_comum.botao_icone`
    # ("delete" cor negative em `telas_administracao.py: _rem` e
    # paginação first/prev/next/last em `telas.py`), com `on_click`,
    # `tooltip`, `cor` e `data-testid`
    # (`agregador-fonte-remover`/`agregador-primeira`/`agregador-anterior`/
    # `agregador-proxima`/`agregador-ultima`) preservados. Marcador
    # `migracao_versao_agregador_noticias_261020_botao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_agregador_noticias_261020_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:agregador_noticias', '1.0.261020') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261020' "
                    "WHERE chave='versao_modulo:agregador_noticias'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_agregador_noticias_261020_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 20/10/2026 — bump do `os` (§4.2): botões "Cancelar"/"Fechar"
    # dos 7 diálogos em `telas.py` (novo quadro, nova ordem, detalhe,
    # colunas, renomear coluna, convites, ajustes) pela fábrica central
    # `mod_tisosdocfly.ui_comum.botao` variante texto, com `on_click`
    # (`dlg.close`) e `data-testid`
    # (`os-quadro-cancelar`/`os-ordem-cancelar`/`os-detalhe-fechar`/
    # `os-coluna-fechar`/`os-coluna-renomear-cancelar`/`os-convite-fechar`/
    # `os-ajuste-cancelar`) novos. Marcador
    # `migracao_versao_os_261020_botao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_os_261020_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:os', '1.0.261020') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261020' "
                    "WHERE chave='versao_modulo:os'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_os_261020_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 20/10/2026 — bump da `lista_telefonica` (§4.2): 4 botões
    # em `telas.py` pela fábrica central `mod_tisosdocfly.ui_comum` —
    # "Baixar PDF" do recorte e da lista CSV por `botao` variante
    # primario (sem `style` manual `cor_botao`), e anterior/próxima da
    # paginação por `botao_icone` preservando
    # `data-testid`/`aria-label`/`disable`. Marcador
    # `migracao_versao_lista_telefonica_261020_botao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261020_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261020') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261020' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261020_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migração 20/10/2026 — bump do `tisosdocfly` (§4.2): 16 botões pela
    # fábrica central `mod_tisosdocfly.ui_comum` — `telas.py` ("edit"/"delete"
    # do Meu perfil por `botao_icone` com `cor`/`tooltip`/`data-testid` e
    # try/except com loguru + `notificar`; "Cancelar" dos diálogos de
    # edição/adição e "Informar o telefone do setor"/"Voltar e informar o
    # número" das travas por `botao` variante texto) e
    # `tela_configuracoes.py` (10 chamadas ao intermediário
    # `_botao_padrao` — removido — por `botao`/`botao_icone` diretos com
    # `chave_modulo="tisosdocfly"`, `cor="red-8"` no "link_off" e
    # `data-testid` preservado). Marcador
    # `migracao_versao_tisosdocfly_261020_botao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261020_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261020') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261020' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261020_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 20/10/2026 - bump da `filas` (par.4.2): 53 botoes em
    # `telas.py` (33) e `telas_administracao.py` (20) pela fabrica central
    # `mod_tisosdocfly.ui_comum` - rotulados por `botao`
    # (primario/contorno/perigo), icone-only por `botao_icone` com
    # `cor`/`tooltip`/`data-testid` preservados, flat de dialogo por `botao`
    # variante texto compacto; 4 condicionais (Fundo/Tirar fundo e
    # Ativar/Desativar nos dois arquivos) com `if` de variante, sem
    # ternario no props; `rodape_salvar_restaurar` removido do import parado.
    # Marcador `migracao_versao_filas_261020_botao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_filas_261020_botao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:filas', '1.0.261020') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261020' "
                    "WHERE chave='versao_modulo:filas'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_filas_261020_botao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migra��ǜo 20/10/2026 �?" bump do `tisosdocfly` (��4.2): inclusao de
    # `dados_abertos`, `agregador_noticias`, `zap` e `video` no
    # `MAPA_BACKUPS` (rotinas.py) �?" passam a ter backup automatico e painel
    # de agendamento/execucao no admin do modulo. Marcador
    # `migracao_versao_tisosdocfly_261020_backup_mapa`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261020_backup_mapa'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261020') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261020' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261020_backup_mapa', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 21/10/2026 — bump do `tisosdocfly` (§4.2): `notificar` normaliza
    # apelidos de tipo para os canônicos do Quasar (achado 5 da analise do
    # dados_abertos) — `error`/`erro` vira `negative` e o toast ganha a cor
    # de erro nas 12 chamadas de uma vez. Marcador
    # `migracao_versao_tisosdocfly_261021_notificar_tipo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261021_notificar_tipo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261021') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261021' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261021_notificar_tipo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 24/10/2026 — bump do `tisosdocfly` (§4.2): seguranca 100% local
    # (captcha em imagem, TOTP opt-in por conta, timeout de inatividade,
    # TLS autossinado). Sobe a versao e semeia as chaves novas SEM
    # sobrescrever o que o admin já ajustou (`ON CONFLICT DO NOTHING`).
    # Marcador `migracao_versao_tisosdocfly_261024_seguranca_local`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261024_seguranca_local'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261024') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261024' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('sessao_timeout_min', '30') ON CONFLICT DO NOTHING")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('captcha_apos_falhas', '3') ON CONFLICT DO NOTHING")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261024_seguranca_local', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 24/10/2026 — bump do `hora_certa` (§4.2): grade responsiva
    # (1/2/4 colunas) nos espelhos, card de backups compacto em grade
    # interna, alturas equalizadas e icones por modulo — sem mudar regra
    # de negocio. Marcador `migracao_versao_hora_certa_261024_grade`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261024_grade'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261024') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261024' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261024_grade', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 24/10/2026 — `hora_certa` (§4.2, mesma versao do dia):
    # agenda por data em todo card-espelho (data + hora + repeticao
    # diaria|semanal|mensal|anual, ancora na data inicial), motor em
    # `rotinas.reconfigurar_agenda` + jobs `agenda:<chave>`. A versao ja
    # eh 1.0.261024 (lote da grade, hoje); o marcador registra o lote.
    # Marcador `migracao_versao_hora_certa_261024_agenda`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261024_agenda'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261024') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261024' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261024_agenda', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump da `lista_telefonica` (par.4.2, mesma
    # versao do dia): seletor de contato do topo com largura de 2 botoes
    # (flex 2 1 40ch, minimo 40ch - antes min-width 25ch, estreito para
    # achar o contato). Marcador
    # `migracao_versao_lista_telefonica_261029_csv_campo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261029_csv_campo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261029_csv_campo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump da `lista_telefonica` (par.4.2, mesma
    # versao do dia): botoes Baixar PDF, Editar, Excluir e Incluir no mesmo
    # padrao (variante `primario` da fabrica `ui_comum.botao`: mesmo tamanho
    # size=md, formato solido e cor do tema - Editar/Excluir eram
    # `secundario`). Marcador
    # `migracao_versao_lista_telefonica_261029_csv_botoes`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261029_csv_botoes'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261029_csv_botoes', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump do `blog` (par.4.2): seed de primeiro
    # boot gera "<Manual> — Como usar" com Mermaid para os 20 manuais de
    # `docs/2_manuais` (pula os 3 titulos artesanais ja existentes) e o
    # carrossel padrao passa a incluir todas as postagens iniciais, nao
    # so as 3 basicas. Marcador `migracao_versao_blog_261029_posts_manuais`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_blog_261029_posts_manuais'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:blog', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:blog'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_blog_261029_posts_manuais', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump da `lista_telefonica` (par.4.2, mesma
    # versao do dia): titulo do card passa a "Resumo da Lista Telefonica"
    # e o "Meus contatos" conta o total geral de reservados do sistema
    # (`tb_contato_pessoal` de todos os donos - proprios + partilhados
    # sao as mesmas linhas que as abas exibem). Marcador
    # `migracao_versao_lista_telefonica_261029_card_titulo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261029_card_titulo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261029_card_titulo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump da `lista_telefonica` (par.4.2, mesma
    # versao do dia): card de resumo na Home (so admin do modulo:
    # contatos, unidades, vinculados, sem telefone, pessoais de todos,
    # listas, membros, partilhas via `resumo_modulo()`); a contagem sai do
    # topo do card da lista. Marcador
    # `migracao_versao_lista_telefonica_261029_card_home`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261029_card_home'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261029_card_home', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump da `lista_telefonica` (par.4.2, mesma
    # versao do dia): controles de edicao do CSV (pesquisa, editar,
    # excluir, incluir) sobem para o topo do card, junto ao Baixar PDF -
    # antes ficavam depois da lista. Marcador
    # `migracao_versao_lista_telefonica_261029_csv_topo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261029_csv_topo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261029_csv_topo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump da `lista_telefonica` (par.4.2, mesma
    # versao do dia): a linha externa volta a mostrar o local completo
    # ("Exte. - Quartel da Policia Militar") - sem o prefixo, o encurtador
    # reduzia "Quartel da Policia Militar" (sem " - ") a "Quar.",
    # indistinguivel do outro quartel. Marcador
    # `migracao_versao_lista_telefonica_261029_pdf_externos_rotulo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261029_pdf_externos_rotulo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261029_pdf_externos_rotulo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump da `lista_telefonica` (par.4.2, mesma
    # versao do dia): Externos no fim da tela e do papel (GRUPOS passa a
    # atendimento, geral, externos, uso), linha externa sem o prefixo de
    # grupo ("SAMU", e nao "Exte. - SAMU") e faixa de secao no PDF
    # (Recepcao, Telefones, Externos). Marcador
    # `migracao_versao_lista_telefonica_261029_pdf_externos_fim`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261029_pdf_externos_fim'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261029_pdf_externos_fim', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump da `lista_telefonica` (par.4.2, mesma
    # versao do dia): as linhas do PDF passam a carregar o grupo e a ordem
    # final e (grupo, local, ramal) - 1) Aten. - Recepcao e vertentes,
    # 2) Externos, 3) resto alfabetico, como na tela. Sem o grupo na frente,
    # a ordem alfabetica pura punha "Administracao" antes do "Atendimento".
    # Marcador `migracao_versao_lista_telefonica_261029_pdf_grupo_ordem`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261029_pdf_grupo_ordem'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261029_pdf_grupo_ordem', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump da `lista_telefonica` (par.4.2, mesma
    # versao do dia): a chave do passo 1 do `agrupar_por_telefone` passa a
    # ser (numero, local) - so texto igual E telefone igual juntam, no
    # padrao secretaria/local/cargo. Numero igual com local diferente vira
    # uma linha por local ("Educ. - Secretario" e "Educ. - Chefe de divisao"
    # no 5122, e nao uma linha so com o prefixo comum). Numeros diferentes
    # com o MESMO local e o MESMO atendente continuam numa linha so
    # ("5101 / 5102"). Marcador
    # `migracao_versao_lista_telefonica_261029_pdf_linha_por_local`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261029_pdf_linha_por_local'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261029_pdf_linha_por_local', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump da `lista_telefonica` (par.4.2): a ordem
    # alfabetica dos cartoes do CSV passa a nascer no codigo
    # (`leitura_csv.ler` ordena atendimento/externos/geral por `letra`,
    # desempate por pessoa+ramal; `uso` mantem a ordem do arquivo) e o
    # `_sem_acento` colapsa espacos internos - espaco duplo no CSV
    # (`Saude  - Secretario`) ordenava antes de `Saude - Almoxarifado`
    # porque espaco (32) < `a`. Linha nova no CSV aparece sozinha no lugar
    # alfabetico no proximo boot/refresh (`render_lista_csv` rele o arquivo
    # a cada desenho, sem cache). Marcador
    # Migracao 29/10/2026 - bump da `lista_telefonica` (par.4.2, mesma
    # versao do dia): `agrupar_por_telefone` ordena as linhas do PDF por
    # (local, ramal) - antes valia a primeira aparicao no cartao e dois
    # numeros da mesma base ("Educ." 5117 e "Educ." 5122) caiam separados
    # pelas linhas "Educ. - ..." do meio. Marcador
    # `migracao_versao_lista_telefonica_261029_pdf_ordem`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261029_pdf_ordem'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261029_pdf_ordem', '1') "
                    "ON CONFLICT DO NOTHING")

    # `migracao_versao_lista_telefonica_261029_ordem_alfabetica`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_lista_telefonica_261029_ordem_alfabetica'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:lista_telefonica', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:lista_telefonica'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_lista_telefonica_261029_ordem_alfabetica', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump do `tisosdocfly` (par.4.2): o botão do menu
    # superior mostra SEMPRE o login (matrícula), com o nome de tratamento
    # só no tooltip. Marcador `migracao_versao_tisosdocfly_261029_header_login`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261029_header_login'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261029_header_login', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump do `usuarios` (par.4.2): saudação no
    # formato "Primeiro.ultimo" ("ana beatriz souza rocha" -> "Ana.rocha").
    # Marcador `migracao_versao_usuarios_261029_saudacao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261029_saudacao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261029_saudacao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump do `tisosdocfly` (par.4.2, mesma versao do
    # dia): segredo de sessão passa a aceitar arquivo só do usuário
    # (`TISOSDOCFLY_STORAGE_SECRET_FILE`) e Gerenciador de Credenciais do
    # Windows (`TISOSDOCFLY_STORAGE_SECRET_CREDMAN=1`) — ver
    # `mod_tisosdocfly/segredos.py`. Marcador
    # `migracao_versao_tisosdocfly_261029_segredos`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261029_segredos'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261029_segredos', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 29/10/2026 - bump do `usuarios` (par.4.2, mesma versao do
    # dia): a trava de arquivo da carga (`digital` + competência de
    # `.ultima_carga.json`) é ignorada com o cadastro vazio — banco
    # recriado com marcador antigo pulava a primeira carga para sempre.
    # Marcador `migracao_versao_usuarios_261029_carga_cadastro_vazio`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_usuarios_261029_carga_cadastro_vazio'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:usuarios', '1.0.261029') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261029' "
                    "WHERE chave='versao_modulo:usuarios'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_usuarios_261029_carga_cadastro_vazio', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 31/10/2026 - bump do `hora_certa` (§4.2): card Hora do
    # servidor padronizado e fixo no topo (sticky, `hc-card-hora`), campos
    # hora + data + dia da semana + calendario sincronizado no tick, sem
    # mudar regra de negocio. Marcador
    # `migracao_versao_hora_certa_261031_relogio`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261031_relogio'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261031') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261031' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261031_relogio', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 31/10/2026 - bump do `hora_certa` (§4.2, mesma versao do
    # dia): cobertura total dos agendamentos — cards novos `video`
    # (`video_expiracao_min`) e `dados_abertos` (`coleta_api_dia/hora/
    # minuto`) + `_acao_agenda` e boot em `rotinas` para as 2 chaves.
    # Marcador `migracao_versao_hora_certa_261031_cobertura`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261031_cobertura'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261031') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261031' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261031_cobertura', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 31/10/2026 - bump do `hora_certa` (§4.2, mesma versao do
    # dia): endurecimento dos espelhos — `salvar_espelho` recusa quando o
    # `gravar` do dono devolve False (fim do falso sucesso), teto (max)
    # aplicado em `empenhos/auditoria/solicita_impressao/editar_pdf/
    # video`, e `/admin/hora_certa` passa o perfil real (admin do Hora
    # Certa vê os demais cards somente leitura). Marcador
    # `migracao_versao_hora_certa_261031_seguranca`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261031_seguranca'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261031') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261031' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261031_seguranca', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 31/10/2026 - bump do `tisosdocfly` (§4.2): `rotinas`
    # ganha `_job_limpeza_video_agenda`, `_acao_agenda` e boot para
    # `video` + `dados_abertos` (cobertura dos cards do Hora Certa).
    # Marcador `migracao_versao_tisosdocfly_261031_agenda_horacerta`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261031_agenda_horacerta'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261031') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261031' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261031_agenda_horacerta', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 31/10/2026 - bump do `hora_certa` (§4.2, mesma versao do
    # dia): fim do card agregado de backups — um `backup_<mod>` por
    # módulo com banco próprio, cada um com seu campo `intervalo`
    # (1–168h), dono `hora_certa` + módulo, agenda e ação próprias.
    # Marcador `migracao_versao_hora_certa_261031_backup_por_modulo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261031_backup_por_modulo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261031') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261031' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261031_backup_por_modulo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 31/10/2026 - bump do `tisosdocfly` (§4.2, mesma versao do
    # dia): `_acao_agenda` e boot passam a cobrir `backup_<mod>` (ação
    # `_job_backup_modulo_agenda` por módulo). Marcador
    # `migracao_versao_tisosdocfly_261031_backup_por_modulo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261031_backup_por_modulo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261031') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261031' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261031_backup_por_modulo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 01/11/2026 - bump do `tisosdocfly` (§4.2): fachada do Blog
    # (`obter/definir_blog_carrossel_tempo`) para o espelho do Hora Certa.
    # Marcador `migracao_versao_tisosdocfly_261101_blog_facade`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261101_blog_facade'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261101') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261101' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261101_blog_facade', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 31/10/2026 - bump do `hora_certa` (§4.2, mesma versao do
    # dia): padrão único de agendamento — `ler_agenda` sugere a data de
    # ativação do sistema (`sistema_data_ativacao`, padrão `2016-10-21`)
    # quando nada foi gravado; vazio gravado continua = desligado.
    # Marcador `migracao_versao_hora_certa_261031_agenda_padrao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261031_agenda_padrao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261031') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261031' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261031_agenda_padrao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 31/10/2026 - bump do `hora_certa` (§4.2, mesma versao do
    # dia): padrão único de card — trio [data|hora|repetição] primeiro,
    # marcador (`ui.separator`) e só então os campos do módulo; cada
    # card visível só ao admin do módulo dono (hora_certa sai de
    # `folha`/`auditoria`/`backup_<mod>`). Marcador
    # `migracao_versao_hora_certa_261031_card_padrao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261031_card_padrao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261031') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261031' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261031_card_padrao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 31/10/2026 - bump do `hora_certa` (§4.2, mesma versao do
    # dia): um card por módulo (`_card_modulo` + `grupos_por_modulo`:
    # mini-cards dentro do card do módulo dono). Marcador
    # `migracao_versao_hora_certa_261031_um_card_por_modulo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261031_um_card_por_modulo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261031') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261031' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261031_um_card_por_modulo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 31/10/2026 - bump do `hora_certa` (§4.2, mesma versao do
    # dia): card principal por módulo (`_card_modulo` + `_conteudo_espelho`:
    # a config principal abre o card sem moldura; as demais viram
    # mini-cards dentro). Marcador
    # `migracao_versao_hora_certa_261031_card_principal`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261031_card_principal'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261031') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261031' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261031_card_principal', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 01/11/2026 - bump do `hora_certa` (§4.2): card único do
    # Blog (`blog`: carrossel + expiração de órfãs + `backup_blog` no
    # grupo `blog`). Marcador `migracao_versao_hora_certa_261101_blog`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261101_blog'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261101') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261101' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261101_blog', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 01/11/2026 - bump do `blog` (§4.2): `expirar_imagens_orfas`
    # sem `minutos` lê `blog_imagem_expiracao_min` central (padrão 5,
    # ajustável no card Blog). Marcador
    # `migracao_versao_blog_261101_imagem_expiracao`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_blog_261101_imagem_expiracao'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:blog', '1.0.261101') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261101' "
                    "WHERE chave='versao_modulo:blog'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_blog_261101_imagem_expiracao', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 01/11/2026 - bump do `hora_certa` (§4.2): backup com trio
    # [data=hoje | hora=06:00 | período] (14 opções) + restauração de
    # cópia no mini-card. Marcador
    # `migracao_versao_hora_certa_261101_backup_triplo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_hora_certa_261101_backup_triplo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:hora_certa', '1.0.261101') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261101' "
                    "WHERE chave='versao_modulo:hora_certa'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_hora_certa_261101_backup_triplo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 01/11/2026 - bump do `tisosdocfly` (§4.2): 14 períodos no
    # motor (`horaria`, `Ndias`, `Nsemanas`, `Nmeses`) + `restaurar_backup`
    # (valida, preserva o atual, troca atômica, audita). Marcador
    # `migracao_versao_tisosdocfly_261101_backup_triplo`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_tisosdocfly_261101_backup_triplo'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:tisosdocfly', '1.0.261101') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261101' "
                    "WHERE chave='versao_modulo:tisosdocfly'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_tisosdocfly_261101_backup_triplo', '1') "
                    "ON CONFLICT DO NOTHING")

    # Migracao 01/11/2026 - bump do `filas` (§4.2): horário de
    # funcionamento por fila (`hora_inicio`/`hora_fim`/`ativo_horario`;
    # fora do horário `gerar_senha` recusa) + limite de re-chamadas
    # por senha (`max_rechamadas` em tb_fila, `tentativas` em
    # tb_chamada; 0 = ilimitado) com `rechamar()` e botão Rechamar +
    # impressora térmica ESC/POS por fila (`impressora_*`; socket puro,
    # sem dependência nova) com botão Imprimir e auto-impressão +
    # totem público (`/totem`, `/totem/{id}`) + API interna
    # (`/api/filas/*`, token em `tb_config_filas`) + estações por IP
    # (`tb_estacao`, `tb_estacao_fila`, gate em gerar/rechamar/próximo)
    # + métricas (só contagens). Lote sisfila (01/11, mesma versão):
    # `posicao_global`/`senha_aguardando`, `voltar_etapa`, `liberar_guiche`
    # (`livre_apos_id` em tb_tv_estado) — sem DDL nova além da coluna.
    # Marcador `migracao_versao_filas_261101_horario_rechamada`.
    cur.execute("SELECT COUNT(*) FROM tb_config "
                "WHERE chave='migracao_versao_filas_261101_horario_rechamada'")
    if (cur.fetchone()[0] or 0) == 0:
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('versao_modulo:filas', '1.0.261101') "
                    "ON CONFLICT DO NOTHING")
        cur.execute("UPDATE tb_config SET valor='1.0.261101' "
                    "WHERE chave='versao_modulo:filas'")
        cur.execute("INSERT INTO tb_config (chave, valor) VALUES "
                    "('migracao_versao_filas_261101_horario_rechamada', '1') "
                    "ON CONFLICT DO NOTHING")

    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()


def incrementar_contador_acessos() -> int:
    """Increments the global access counter — login-only, never navigation/refresh.

    EN: Centralized counter for **successful logins only** (not page navigations,
    refreshes or tab switches). Called exclusively in `main.tentar_login`
    after `autenticacao.registrar_login` validates credentials. Persists in
    `tb_config` (`contador_acessos_total` + `contador_acessos_inicio`) via
    `get_config`/`set_config` (which delegate to `Repositorio`/SQLAlchemy and
    then to `banco_conexao.conexao`). `main._orquestrar_resumo_dados` only
    reads (`get_config`). Previously incremented inline in `main`; now this
    function is the single source of truth. Fail-soft — returns `0` on error.
    Returns the new total.

    PT-BR: Incrementa o contador global de acessos — **apenas logins**, nunca
    navegações, refreshes ou trocas de aba. Chamado somente em
    `main.tentar_login` após `autenticacao.registrar_login` validar as
    credenciais. Persiste em `tb_config` (`contador_acessos_total` +
    `contador_acessos_inicio`) via `get_config`/`set_config` (que delegam ao
    `Repositorio`/SQLAlchemy e então a `banco_conexao.conexao`).
    `main._orquestrar_resumo_dados` apenas lê (`get_config`). Antes contava
    inline em `main`; agora esta função é a única fonte da verdade. Fail-soft
    — retorna `0` em erro. Retorna o novo total.
    """
    import datetime as _dt
    try:
        total = get_config("contador_acessos_total", "0") or "0"
        try:
            novo = int(str(total).strip() or 0) + 1
        except Exception:
            novo = 1
        set_config("contador_acessos_total", str(novo))
        inicio = (get_config("contador_acessos_inicio", "") or "").strip()
        if not inicio:
            set_config("contador_acessos_inicio", _dt.datetime.now().strftime("%Y-%m-%d"))
        return novo
    except Exception:
        return 0


def get_config(chave, default=""):
    """Leitura pontual de configuração via Repositorio (SQLAlchemy ORM).

    Camada mais baixa: sem imports circulares. Delega para `Repositorio.obter_config`.
    """
    try:
        from mod_tisosdocfly.repositorio import Repositorio
        with Repositorio() as repo:
            return repo.obter_config(chave, default)
    except Exception:
        pass
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT valor FROM tb_config WHERE chave=?", (chave,))
        row = cur.fetchone()
        return row[0] if row else default
    finally:
        conn.close()


def set_config(chave, valor):
    """Gravação de configuração via Repositorio (SQLAlchemy ORM).

    Delega para `Repositorio.definir_config`.
    """
    try:
        from mod_tisosdocfly.repositorio import Repositorio
        with Repositorio() as repo:
            ok = repo.definir_config(chave, valor)
            if ok:
                try:
                    favicon_versao.cache_clear()
                except Exception:
                    pass
                for _fn, _chaves in list(_HOOKS_CONFIG):
                    if _chaves is not None and chave not in _chaves:
                        continue
                    try:
                        _fn()
                    except Exception:
                        pass
            return ok
    except Exception:
        pass
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tb_config (chave, valor) VALUES (?, ?) "
            "ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor",
            (chave, str(valor)))
        conn.commit()
    finally:
        conn.close()


@lru_cache(maxsize=1)
def favicon_versao():
    """mtime do favicon atual — muda quando o .ico é trocado (cache-busting da aba)."""
    try:
        return int(os.path.getmtime(os.path.join(BASE_DIR, "assets", "favicon_atual.ico")))
    except OSError:
        return 0
