# Vídeos

Baixar vídeos e áudios do YouTube, Facebook, TikTok, Instagram e outros
sites (via yt-dlp), assistir no sistema e publicar na biblioteca.

!!! warning "Uso legítimo e auditoria"
 Ferramenta para conteúdo livre de direitos autorais; o **usuário
 responde** pelo que baixa. Todo link fica registrado com quem pediu,
 quando, de onde (URL), o quê (título/tamanho) e como (formato/
 plataforma) — base LGPD: interesse legítimo e obrigação legal
 (art. 7º), guarda para obrigação e exercício de direitos (art. 16) e
 registro das operações (art. 37), mais Lei nº 9.610/1998. Registros
 entregáveis à Justiça em caso de violação.

!!! note "Titulos sem acento de proposito"
 O MkDocs gera `WARNING` ao normalizar acento em ancora de titulo. Todos os
 `##` deste arquivo sao grafados **sem acento**, para que os IDs de ancora
 fiquem limpos. O texto corrido usa a acentuacao normal do portugues
 brasileiro.

## Visao geral

Todo perfil tem **Meus arquivos** (só os próprios) na mesma grade dos em
andamento: cartão por arquivo com **Interromper, Excluir e Baixar** (só
habilitam quando fazem sentido) + Assistir/Publicar para admin. O comum vê **só o card de baixar** além
disso: cola o link, **verifica**, escolhe e o arquivo **desce direto para
o PC** — nada fica no servidor. O botão de baixar **só libera após a
verificação**. Biblioteca e curadoria do acervo são do **admin do módulo**
(ou geral).

Layout em linha única (quebra só em tela estreita): Verificar → Formato →
Marcar todos → Desmarcar todos → **Processar e preparar para download**.
Formato e processar nascem inativos, com áudio como padrão. Todos os botões
idênticos (`ui_comum.botao` primário, cor do tema, `chave_modulo="video"`).
O andamento é grade fluida (quantos cartões couberem, sempre ocupando a
linha toda; cartão com respiro e barra larga). Interromper fica sempre
visível e só habilita baixando.

### Verificar, formatos reais e playlists

Verificar mostra título/autor/duração com spinner e frases de andamento, e
os **formatos que o vídeo tem de verdade, todos** (um item por
resolução/extensão, com tamanho aproximado; MP3 só com ffmpeg). Vídeo em
trilha separada (sem áudio) também é listado, rotulado **"(só vídeo, sem
áudio)"** — antes era omitido e o webm parecia indisponível. Sendo
**playlist**, lista os
vídeos (até 50) com checkbox — baixa um pedido por item marcado, cada um
com sua barra. Sem arquivo único e sem ffmpeg, avisa direto (sem tentativa
cega).

### Stage, expiracao e biblioteca

| Lugar | O que é | Expira? |
|:---|:---|:---|
| `src/mod_video/downloads/` (stage) | Baixado agora, ainda não publicado | **Sim, para todo perfil**: 10 min padrão (`video_expiracao_min`, mín. 1, no `/admin/video`); expirado é excluído sozinho |
| `src/mod_video/biblioteca/` | Publicado pelo admin (`/midia_video/*`) | **Não**. É o acervo do sistema |

A limpeza roda a cada 1 min (`cleanup_video` em `rotinas.py`, como o
`cleanup_pdf`): apaga do disco e marca `expirado`. Publicado nunca entra.

### Formatos e qualidade

`melhor_mp4`, `medio_mp4` (720p) e `audio_mp3`. Sem **ffmpeg** no servidor
não há junção nem conversão: o vídeo verificado lista um áudio por formato
(M4A, Opus…) para escolher o original. MP3 de verdade e vídeo em trilhas
só com ffmpeg. Instala
com `poetry run python instalar_externos.py --ffmpeg` (detecta o SO:
winget no Windows, apt no Linux, brew no macOS).

### Biblioteca e outros modulos

Publicar move o arquivo para a biblioteca e zera a expiração. A fachada
`integracoes.listar_videos_publicados()` devolve `id/titulo/plataforma/
url_midia/tamanho_bytes` para outros módulos (ex.: a TV das filas) **sem**
importar o `mod_video` (isolamento).

### Em grupo e em paralelo

Cada clique em Baixar é um pedido com **barra própria** (% + bytes + MB/s +
ETA, pelo hook do yt-dlp; na CLI de fallback, pelo parse da saída). O
cartão tem tamanho único: título sempre em 1 linha (rolagem lateral se
longo). Dá para colar outro link em seguida sem esperar.

**Meus arquivos estilo PDF**: tabela com checkbox (cabeçalho marca todos),
badge colorido de expiração, menu por linha (Assistir/Baixar/Excluir,
Publicar no admin) e botões centralizados **Excluir selecionados**,
**Baixar ZIP** (tudo num zip efêmero, apagado 10 s após descer) e
**Baixar** (um download por arquivo, os separados). O arquivo fica no stage
até o TTL para todo perfil (nada some antes da hora). **2 por vez**: o resto espera
em "Na fila…" (lote grande derrubava a conexão e tomava 403 do
YouTube). Reinício no meio marca o pendente órfão como erro (reconcilia
no boot e na tela). Sair da tela não para nada:
voltar mostra o que ainda baixa (barra reatachada, só a própria), o que
já baixou e o stage — pendente órfão de sessão anterior vira erro.

Assistir abre o player com a **capa do vídeo** (`poster` = miniatura do
YouTube, gravada no pedido na verificação; se faltar, busca 1x na conclusão
ou no primeiro Assistir e grava — sem request por linha).

Download em curso tem **Interromper download** (mata o processo e elimina
o trabalho, sem órfão no servidor — só existe durante o download);
concluído tem **Baixar** (sistema → PC) e **Excluir arquivo**; falha ganha
**lixeira** na barra e no histórico. Servidor concluiu = **desce para o PC
na hora, todo perfil** (admin mantém o stage) — o clique é gesto e desce
mesmo se o navegador barrar o automático. Sair da página no meio não gera
stack no log (`_foi_desconexao`).

## Estrutura de arquivos

| Arquivo | Linhas | Responsabilidade |
|:---|:---|:---|
| `src/mod_video/__init__.py` | 2 | Encapsulamento do pacote (sem exposição pública própria) |
| `src/mod_video/bd_manipulador.py` | 955 | Único ponto de acesso ao banco `db_mod_video.db`: schema, pedidos, biblioteca, expiração, ZIP, rotas `/midia_video/*` |
| `src/mod_video/servico_download.py` | 917 | Lógica de download via yt-dlp (validação, formatos, progresso, cancelamento); sem acesso a banco nem UI |
| `src/mod_video/telas.py` | 2.161 | Tela de negócio `mostrar_tela(user_nome, perfil_global)` + player + helpers de UI |
| `src/mod_video/telas_administracao.py` | 275 | Painel `/admin/video`: TTL, biblioteca global, histórico global |
| `src/mod_video/downloads/` | — | Stage temporário (gerado em execução, fora do git) |
| `src/mod_video/biblioteca/` | — | Acervo publicado (gerado em execução, fora do git) |

## Referencia por arquivo

### `bd_manipulador.py` — dados e arquivos

Banco e bootstrap:

- `get_connection()` — abre a conexão do módulo (WAL) via `banco_conexao.conexao("video")`.
- `init_db()` — cria o schema (`tb_video_historico` + colunas de migração); idempotente.
- `init_db_video()` — apelido de bootstrap: chama `init_db()` + `reconciliar_pendentes_boot()`; é o que o boot chama.
- `reconciliar_pendentes_boot()` — pendente órfão (processo morto) vira erro no boot.
- `montar_rotas_static()` — serve a biblioteca em `/midia_video/*` (mesmo padrão das filas).
- `url_biblioteca(nome_arquivo)` — URL pública de um arquivo publicado.
- `_auditar(ator, acao, alvo, detalhe="")` — trilha central (fail-soft).
- `_garantir_colunas(conn)` — adiciona colunas novas a tabela pré-existente (portável SQLite ↔ PostgreSQL).

Pedidos:

- `registrar_pedido(user_nome, url, plataforma, formato="melhor_mp4", ...)` — registra o pedido como `pendente`.
- `atualizar_status(pedido_id, status, titulo="", arquivo="", tamanho=0, ...)` — atualiza estado/título/arquivo do pedido.
- `marcar_erro(pedido_id, detalhe="")` — marca o pedido como erro.
- `obter_pedido(pedido_id)` — um pedido como dict (ou `{}`).
- `listar_historico(user_nome="", limite=30)` — pedidos recentes (próprios; todos para admin).
- `contar_historico(user_nome="")` — conta os pedidos.
- `cfg_expiracao_min()` — TTL do stage em minutos (`video_expiracao_min`, mín. 1).
- `expirar_antigos(minutos=None)` — remove arquivos expirados do stage (disco + marca `expirado`).
- `zipar_selecao(user_nome, nomes)` — ZIP efêmero de arquivos do stage em `downloads/`.

Biblioteca (curadoria do admin):

- `listar_biblioteca(limite=100)` — vídeos publicados (sem expiração, visíveis a quem tem acesso).
- `publicar_pedido(pedido_id, ator="")` — move o arquivo pronto para a biblioteca (zera expiração).
- `despublicar_pedido(pedido_id, ator="")` — devolve o publicado ao stage.
- `excluir_pedido(pedido_id, ator="")` — apaga arquivo (stage ou biblioteca) + linha do banco.

Caminhos seguros:

- `caminho_arquivo(nome_arquivo, publicado=False)` — caminho absoluto do stage/biblioteca (anti-traversal).
- `_sob_dir(base_dir, nome)` / `_sanitizar_nome(nome)` / `_nome_unico(base_dir, nome)` — contenção ao diretório e primeiro nome livre.
- `_linhas_para_dicts(linhas)` — linhas do cursor para dicts.
- `_agora()` / `_daqui_a_minutos(minutos)` — data/hora local em texto.
- `_eh_bloqueio_banco(exc)` / `_rollback_seguro(conn, ...)` / `_commit_com_retry(conn, ...)` — contenção transitória com retry curto.

### `servico_download.py` — motor yt-dlp (sem banco, sem UI)

Validação e plataforma:

- `validar_url(url)` — aceita só URL `http/https`.
- `detectar_plataforma(url)` — rótulo da plataforma pelo host.
- `yt_dlp_disponivel()` — verdadeiro se o pacote Python ou o binário CLI existir.
- `tem_ffmpeg()` — verdadeiro se houver ffmpeg no PATH (junção/conversão disponível).
- `aviso_qualidade()` — aviso quando falta ffmpeg (fallback de arquivo único).
- `exige_ffmpeg(info)` — verdadeiro quando a junção é inevitável (sem formato único).

Verificação (bloqueante — chamar via `run.io_bound`):

- `obter_informacoes(url)` — título/autor/duração sem baixar.
- `extrair_verificacao(url)` — o que o link contém (vídeo, playlist, formatos).
- `opcoes_de_formatos(info, com_ffmpeg=None)` — todos os formatos utilizáveis do vídeo (por id, com tamanho).
- `tem_progressivo(info)` — verdadeiro se há formato com áudio+vídeo num arquivo só.
- `_opcoes_saida(formato, pedido_id, user_nome="")` — modelo de saída + seletor de formato.
- `_mensagem_erro(detalhe)` — mensagem amigável para falhas conhecidas (ex.: 403 = limite temporário do YouTube).

Download (bloqueante — chamar via `run.io_bound`):

- `baixar(url, formato, pedido_id, progresso_cb=None, spec=None, ...)` — baixa o vídeo/áudio com hook de progresso.
- `extrair_progresso_linha(linha)` — lê linha de progresso do yt-dlp `--newline`.
- `limpar_parciais(pedido_id)` — remove restos de pedido falhado.
- `_nome_final_esperado(pedido_id)` / `_nome_seguro_usuario(user_nome)` / `_sanitizar_nome(nome)` — nome do arquivo final (com dono) e sanitização.
- `_yt_dlp_cmd()` — binário da CLI ou fallback `python -m yt_dlp`.
- `mime_por_nome(nome)` — MIME pela extensão (para o player); `eh_audio(nome)` — verdadeiro se só áudio.

Cancelamento:

- `solicitar_cancelamento(pedido_id)` — pede parada (hook levanta / CLI é morta); `class DownloadCancelado` — exceção do hook quando o usuário cancela.
- `consumir_cancelamento(pedido_id)` — consome a bandeira (idempotente, só uma vez); `_limpar_cancelamento(pedido_id)` — esquece bandeira e processo.

Privados `_x` agrupados por arquivo: `bd_manipulador.py` — `_log`, `_agora`, `_daqui_a_minutos`, `_eh_bloqueio_banco`, `_rollback_seguro`, `_commit_com_retry`, `_auditar`, `_garantir_colunas`, `_linhas_para_dicts`, `_sanitizar_nome`, `_sob_dir`, `_nome_unico`; `servico_download.py` — `_log`, `_limpar_cancelamento`, `_nome_seguro_usuario`, `_opcoes_saida`, `_nome_final_esperado`, `_sanitizar_nome`, `_mensagem_erro`, `_yt_dlp_cmd`; `telas.py` — `_notificar` (interna), `_foi_desconexao`, `_botao`, `_log`, `_eh_admin`, `_tamanho_legivel`, `_titulo_1_linha`, `_duracao_legivel`, `_resta`, `_cliente_atual`, `_cliente_vivo`, `_download_para_cliente`, `_notificar_cliente`, `_semaforo`, `_ouvir_conclusao`, `_avisar_seguro`, `_chaves_da_selecao`, `_registrar_relogio`, `_pintar_relogios`, `_mostrar_resultado_admin`, `_remover_zip`, `_linha_biblioteca`; `telas_administracao.py` — `_notificar` (interna), `_log`, `_botao`, `_linha_bib_admin`.

### `telas.py` — tela de negocio

- `mostrar_tela(user_nome: str, perfil_global: str = "")` — grade de downloads, Meus arquivos em tabela estilo PDF, biblioteca, player; 2 downloads por vez (`VAGAS_DOWNLOAD`, semáforo), reattach de barra ao voltar, entrega automática ao PC.
- `abrir_player(titulo, caminho_ou_url, nome_arquivo="")` — player de vídeo/áudio no diálogo.

### `telas_administracao.py` — painel do admin

- `mostrar_administracao(usuario_logado: str = "")` — TTL (`video_expiracao_min`), "Expirar agora", biblioteca global e histórico global.

## Banco de dados

| Item | Valor |
|:---|:---|
| Chave do módulo | `video` |
| Arquivo SQLite | `db_mod_video.db` (raiz) |
| DATABASE PostgreSQL | `db_mod_video`, schema `public` |
| Registro em `MODULOS_BD` | `src/mod_tisosdocfly/repositorio.py` (`"video": "db_mod_video.db"`) |
| Dono do schema | `init_db()` em `bd_manipulador.py:213` (DDL `DDL_HISTORICO` + `_garantir_colunas`) |

| Tabela | O que representa |
|:---|:---|
| `tb_video_historico` | Pedidos de download: quem pediu (`user_nome`), URL, plataforma, formato, estado (`pendente`/`pronto`/`erro`/`expirado`/`entregue`), título, arquivo, tamanho, expiração; publicado vai para a biblioteca |

Configuração vive no banco **central** (`tb_config` do `db_mod_tisosdocfly.db`): `video_expiracao_min` (padrão 10, mín. 1).

## Telas e rotas

| Rota | Função | Perfil mínimo | Onde está |
|:---|:---|:---|:---|
| `/video` | `mod_video.telas.mostrar_tela(user_nome, perfil_global="")` | `comum` com acesso liberado | `main.py:1406-1424` |
| `/midia_video/*` | arquivos da biblioteca (estáticos) | público autenticado | `main.py:315-322` via `montar_rotas_static()` |
| `/admin/video` | `mod_video.telas_administracao.mostrar_administracao(usuario_logado="")` | administrador do módulo/geral | `main.py:1503+` (`page_admin_modulo`, ramo `video`) |

Testids (para a QA): `video-url`, `video-formato`, `video-verificar`,
`video-verificando`, `video-verificado`, `video-andamento`, `video-baixar`,
`video-historico`, `video-biblioteca`, `video-publicar`, `video-excluir`,
`video-excluir-sel`, `video-zip-sel`, `video-separados-sel`,
`video-marcar-todos`, `video-desmarcar-todos`,
`video-admin-{biblioteca,expiracao}`, `video-admin-{salvar,expirar}`.

## Papeis e permissoes

| Papel | O que vê | O que faz |
|:---|:---|:---|
| `comum` com acesso liberado | card de baixar + **Meus arquivos** (só os próprios) | verifica link, baixa para o PC, gerencia os próprios arquivos até o TTL |
| `administrador_geral` / admin do módulo | tudo do `comum` + biblioteca + histórico global | publica/despublica/exclui, ajusta TTL, expira agora |
| sem acesso | nada — `pagina_restrita` barra a rota | nada |

Gate da regra: `_eh_admin(user_nome, perfil_global)` em `telas.py:85`; publicar/despublicar/excluir exigem admin antes de qualquer escrita. Biblioteca é global (todos com acesso veem); stage é por dono.

## Versao

`1.0.261017`: stage com TTL de 10 min para todo perfil, biblioteca sem
expiração, player, entrega automática ao PC (arquivo fica até o TTL),
ZIP em grupo e separados, tabela estilo PDF, botões uniformes, grade
fluida. Chave `versao_modulo:video` na `tb_config` central (seed +
migrações `migracao_versao_video_261017_*` em `src/mod_tisosdocfly/bd_conexao.py`).

## Cobertura de testes (17/10/2026)

`tests/teste_video_ciclo.py` (base) + `tests/teste_video_completo.py`
(decisões do dia). Tudo offline, com arquivos fictícios, banco isolado
(`TISOSDOCFLY_DIR_BANCO`), padrão `check()` + `main()` com exit code:

| Garantido (automático) | Onde |
|:---|:---|
| Stage com TTL de 10 min para **todo perfil** (comum e admin expiram); biblioteca **sem expiração**, mesmo com registro antigo | `teste_video_completo.py` |
| Comum recebe o arquivo no PC **e o arquivo fica** até o TTL (para ZIP/separados); admin mantém o stage do mesmo jeito | `teste_video_completo.py` |
| Ciclo pedido → pronto → publicar → despublicar → excluir (disco + banco) | `teste_video_ciclo.py` |
| Expirado: passado remove, publicado sobrevive, arquivo sumido vira `expirado` | `teste_video_ciclo.py` |
| Varredura de órfãos: velho sai, fresco fica, referenciado fica; referência de status terminal (`erro`/`entregue`/`expirado`) é limpa; `.part` velho sai | `teste_video_ciclo.py` + `teste_video_completo.py` |
| Pendente órfão vira `erro` no boot (> 2 min) e na tela; fresco continua `pendente`; `pronto` não é tocado; reconcile é idempotente | `teste_video_completo.py` |
| Remoção manual do admin não tem retry: após excluir, 2ª exclusão devolve `False`, expirar/reconciliar não ressuscitam | `teste_video_completo.py` |
| Isolamento por usuário (só os próprios; biblioteca é global); anti-traversal nos dois lados | `teste_video_ciclo.py` + `teste_video_completo.py` |
| Seleção da tabela é **LISTA** (`_chaves_da_selecao`); ZIP/separados só levam `pronto` com arquivo existente | `teste_video_ciclo.py` + `teste_video_completo.py` |
| Cancelamento: bandeira idempotente (só uma vez), `DownloadCancelado`, parciais `-pid-` limpos | `teste_video_ciclo.py` + `teste_video_completo.py` |
| Fila de 2 (`VAGAS_DOWNLOAD`, semáforo); tarefas vivas com reattach filtrado por dono | `teste_video_completo.py` |
| Papel antes da escrita: geral é admin, comum sem vínculo não é | `teste_video_completo.py` |
| Formatos/opções: TODOS os do vídeo (por id, com tamanho); sem ffmpeg, vídeo sem áudio vem rotulado; sem info = cautela); presets `unico`/`audio_orig` | `teste_video_ciclo.py` + `teste_video_completo.py` |
| Erro amigável (403 = limite temporário do YouTube, com 1 retry após 15 s) e arquivo com o dono no nome (`usuario_datahora_titulo[id]-pid.ext`) | `teste_video_ciclo.py` |
| Capa do vídeo (`miniatura` no pedido, `poster` no player; backfill 1x; nunca sobrescreve) | `teste_video_ciclo.py` |
| Progresso (linha CLI, teto 1.0, hook por bytes) e `cleanup_video` a cada 1 min | `teste_video_ciclo.py` + `teste_video_completo.py` |
| 38 migrações `migracao_versao_video_*` presentes e idempotentes (init 2x); versões `video` em `1.0.261017` e `tisosdocfly` em `1.0.261101` | `teste_video_ciclo.py` + `teste_video_completo.py` |
| Fachada `integracoes.listar_videos_publicados` (chaves, `/midia_video/`, `limite`, stage não vaza) | `teste_video_ciclo.py` + `teste_video_completo.py` |
| Meus arquivos em tabela estilo PDF (checkbox nativo, badge, menu) + botões uniformes primários e grade fluida | manual (E2E visual) |

`pyflakes` com 0 `undefined name` nos testes e no `mod_video/`; import
isolado (`sys.path` → `src/`) de `telas`, `telas_administracao`,
`bd_manipulador` e `servico_download`; `tests/check_integridade.py` verde.

## E2E manual

Exige navegador (fora da suíte offline):

- Verificar link de verdade (YouTube/playlist) e baixar um vídeo real, com e sem ffmpeg no servidor.
- Entrega automática ao PC (diálogo de download do navegador, comum e admin) e botão "Baixar" na barra quando o automático é barrado.
- Barras ao vivo, "Na fila…" com 3+ pedidos, Interromper no meio, reattach ao sair e voltar à tela.
- Publicar → assistir na biblioteca (`/midia_video/`), despublicar, excluir; contagem regressiva ao vivo.
- Seleção na tabela (cabeçalho marca todos), ZIP e separados descendo de verdade; menu por linha.
- `/admin/video`: salvar TTL, "Expirar agora", biblioteca e histórico global.
- Papel real: comum não vê biblioteca/curadoria; admin publica; `qacomum`/`qamaster` (§8.2).
- Se o navegador pedir plug-in H.264 ao assistir: abrir o arquivo no VLC do PC (já vem com o codec) ou no Chrome.
