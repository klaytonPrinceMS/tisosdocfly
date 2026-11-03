# Video Download — User Manual — T! SOS DocFly

> Operational guide for the Video module (`/video`): paste the link, verify it, pick the real video/audio format, download to your PC. Every user sees only their own downloads plus an expiry countdown; the admin curates the system library (`/midia_video/*`) and adjusts the stage lifetime in `/admin/video`.

---

# Manual de Uso — Vídeos — T! SOS DocFly

> Guia operacional do módulo Vídeos (`/video`): cole o link, verifique, escolha o formato e baixe para o seu computador. Cada usuário vê só os próprios arquivos, com contagem de expiração; o administrador do módulo cura a biblioteca do sistema e ajusta o tempo de vida no painel `/admin/video`.

## Contexto

O módulo baixa vídeos e áudios de sites como YouTube, Facebook, TikTok e Instagram (via yt-dlp) para uso legítimo — **conteúdo livre de direitos autorais**. O **usuário responde pelo que baixa**: todo link fica registrado com quem pediu, quando, de onde (URL de origem), o quê (título e tamanho) e como (formato e plataforma), conforme o aviso exibido na própria tela (`src/mod_video/telas.py:414-428`). Os registros seguem a LGPD e a Lei nº 9.610/1998 e podem ser entregues à Justiça em caso de violação.

O fluxo é o mesmo para todo perfil: **colar → verificar → escolher o formato → processar**. O arquivo concluído **desce automaticamente para o seu computador** e fica no stage do servidor só até o prazo de expiração (10 min padrão) para baixar de novo ou juntar num ZIP — nada some antes da hora (`src/mod_video/telas.py:1393-1416`).

## As telas

### 1. Baixar vídeo ou áudio (`/video`, cartão superior)

- Campo **Link do vídeo ou da playlist** + botão **Verificar link** na mesma linha (`src/mod_video/telas.py:486-496`). O botão **Processar e preparar para download** nasce desativado e **só libera após a verificação** (`src/mod_video/telas.py:530-539`).
- A verificação mostra título, autor e duração, com spinner e mensagens de andamento enquanto consulta o site (`src/mod_video/telas.py:599-638`).
- **Vídeo único:** lista os **formatos que o vídeo tem de verdade** (um item por resolução/extensão, com tamanho aproximado). O padrão selecionado é um formato de áudio (`src/mod_video/telas.py:845-856`).
- **Playlist:** lista os vídeos (até 50) com caixinha de marcação cada; botões **Marcar todos** e **Desmarcar todos** aparecem só neste caso (`src/mod_video/telas.py:731-798`). Cada item marcado vira um pedido próprio, cada um com sua barra de progresso.
- **Sem ffmpeg no servidor:** não há junção nem conversão. A tela avisa direto e oferece só o que desce de verdade (arquivo único ou áudio original) (`src/mod_video/telas.py:776-784`). O aviso de qualidade aparece só para o admin (`src/mod_video/telas.py:554-561`).
- Se o link não puder ser lido, a tela informa ("não foi possível ler o link — confira") em vez de tentar às cegas (`src/mod_video/telas.py:724-729`).

### 2. Downloads em andamento (grade de cartões)

- Cada clique em processar cria **um pedido com barra própria** (porcentagem, MB baixados/total, velocidade e tempo estimado) (`src/mod_video/telas.py:971-1021`).
- Dá para colar outro link em seguida sem esperar o anterior terminar. **Só 2 downloads rodam por vez** (`VAGAS_DOWNLOAD`, `src/mod_video/telas.py:231`); o restante espera em **"Na fila…"**.
- Enquanto baixa, o cartão mostra só o botão **Interromper** (cancela o download e elimina o trabalho, sem deixar resto no servidor) (`src/mod_video/telas.py:1128-1141`, `src/mod_video/telas.py:1172-1230`). Ao concluir ou falhar, a barra sai da grade e o resultado vai para **Meus arquivos**.
- Sair da tela **não para nada**: ao voltar, as barras dos seus downloads vivos são recriadas (só as suas — ninguém vê pedido alheio) (`src/mod_video/telas.py:2077-2094`).

### 3. Meus arquivos (tabela, todo perfil)

- Todo perfil — inclusive o `comum` — tem **Meus arquivos** com **só os próprios** pedidos (`src/mod_video/telas.py:1629-1634`). Colunas: **Arquivo, Tamanho, Situação, Expira em** (com selo colorido: verde → âmbar → vermelho perto de vencer) (`src/mod_video/telas.py:1782-1802`).
- Clique com o botão direito (menu da linha): **Assistir** (abre o player com a capa do vídeo), **Baixar** (desce de novo para o PC), **Publicar no sistema** (só admin) e **Excluir** (`src/mod_video/telas.py:1856-1866`).
- Botões de lote sobre a seleção (o cabeçalho da tabela marca todos): **Excluir selecionados**, **Baixar ZIP** (junta os marcados num ZIP efêmero, apagado do servidor 10 s após descer) e **Baixar** (um download por arquivo) (`src/mod_video/telas.py:1882-1896`, `src/mod_video/bd_manipulador.py:963-1003`).
- O que aparece: pendente (baixando), pronto com arquivo existente, publicado e erro (que precisa de ação). Expirado some da lista; pronto sem arquivo (limpo pela expiração) também (`src/mod_video/telas.py:1903-1931`).
- A contagem **Expira em** é repintada ao vivo; a tabela recarrega sozinha a cada 30 s preservando a seleção (`src/mod_video/telas.py:1023-1081`, `src/mod_video/telas.py:2034-2038`).

### 4. Biblioteca do sistema (só admin, na `/video`)

- Visível **só para o admin do módulo** (o comum não cura acervo) (`src/mod_video/telas.py:2040-2048`). Reúne os vídeos **publicados: sem expiração, para assistir ou salvar** por quem tem acesso ao módulo (`src/mod_video/telas_administracao.py:147-151`).
- O admin recém-baixado recebe um diálogo com player e os botões **Salvar no PC**, publicar e excluir (`src/mod_video/telas.py:2159-2204`).
- Publicar move o arquivo do stage para a biblioteca e zera a expiração; só vídeo **pronto** pode ser publicado (`src/mod_video/bd_manipulador.py:687-736`).

### 5. Administração (`/admin/video` — admin do módulo ou geral)

Três cartões (`src/mod_video/telas_administracao.py:62-210`):

- **Tempo de vida no servidor:** minutos que o baixado fica no stage antes de expirar e ser excluído sozinho (padrão 10, mínimo 1; vale para todo o stage — só o publicado não expira). Botões **Salvar** e **Expirar agora** (roda a limpeza na hora) (`src/mod_video/telas_administracao.py:76-145`, `src/mod_video/bd_manipulador.py:74-84`).
- **Biblioteca do sistema:** lista global dos publicados, cada linha com **Devolver ao stage** e **Excluir** (`src/mod_video/telas_administracao.py:147-182`, `src/mod_video/telas_administracao.py:224-273`).
- **Histórico global:** total de pedidos + últimos 50, com data, quem pediu, plataforma, título e situação (**só metadados, nunca o conteúdo**) (`src/mod_video/telas_administracao.py:184-210`).

## Fluxos principais

- **Baixar um vídeo:** cole o link → **Verificar link** → confira título/autor/duração → escolha o formato → **Processar e preparar para download**. O arquivo desce sozinho para o seu PC ao concluir; se o navegador barrar o automático, use o **Baixar** da linha (`src/mod_video/telas.py:1453-1623`).
- **Baixar uma playlist:** verifique → marque os episódios (ou **Marcar todos**) → escolha o formato → processe. Cada item vira um pedido com barra própria (`src/mod_video/telas.py:1518-1550`).
- **Rever o que baixou:** volte à `/video` e abra **Meus arquivos** — o que ainda está no prazo pode ser assistido, baixado de novo, juntado num ZIP ou excluído (`src/mod_video/telas.py:1898-2033`).
- **Interromper:** durante o download, use **Interromper** no cartão. O pedido é cancelado e removido, sem órfão no servidor (`src/mod_video/telas.py:1172-1230`).
- **Expiração:** passado o prazo (10 min padrão), o arquivo sai do disco sozinho e o registro marca `expirado`. Publicado na biblioteca **nunca expira** (`src/mod_video/bd_manipulador.py:824-960`).
- **Publicar (admin):** no menu da linha (Meus arquivos) ou no diálogo do recém-baixado, escolha **Publicar no sistema**. Para retirar, use **Devolver ao stage** no `/admin/video` (`src/mod_video/bd_manipulador.py:687-784`).
- **Reinício no meio:** pedido `pendente` antigo (2+ min) sem tarefa viva vira `erro` — no boot e ao abrir a tela — em vez de ficar preso para sempre (`src/mod_video/bd_manipulador.py:266-318`, `src/mod_video/telas.py:2096-2119`).

## Permissões

| Papel | O que vê | O que faz |
|:---|:---|:---|
| `comum` com acesso liberado | cartão de baixar + **Meus arquivos** (só os próprios) + andamento dos próprios | verifica link, baixa para o PC, assiste, junta ZIP, exclui os próprios até o prazo |
| Admin do módulo / `administrador_geral` | tudo do `comum` + **Biblioteca** na `/video` + painel `/admin/video` | publica/despublica/exclui qualquer item, ajusta o tempo de vida, expira agora, vê o histórico global |
| Sem acesso ao módulo | nada — a rota é barrada | nada |

A checagem é feita por `_eh_admin(user_nome, perfil_global)` (`src/mod_video/telas.py:85-93`): publicar, despublicar e excluir acervo exigem admin antes de qualquer escrita. O stage é por dono; a biblioteca é global (todos com acesso veem). Contas de teste: `qacomum` (perfil `comum`) e `qamaster` (perfil `administrador_geral`).

## Auditoria e segurança

- Cada pedido registra quem pediu, URL, plataforma, título, formato, estado, tamanho e expiração (`tb_video_historico`, `src/mod_video/bd_manipulador.py:162-178`); publicar, despublicar, excluir e expirar geram trilha na auditoria central (`src/mod_video/bd_manipulador.py:151-159`).
- Autenticação e perfis pelo núcleo (`mod_tisosdocfly`); o módulo não tem gestão própria de usuários nem lê banco de outro módulo.

Veja [Manual do Usuário Comum](../03_usuario_comum/index.md) e [Resumo do Módulo](../../1_sistema/06_modulos/01_resumos/13_video.md).
