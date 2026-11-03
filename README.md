# T! SOS DocFly

Plataforma de **laudos de voo de qualquer drone (multidrone)**. O cliente
autentica, envia fotos e vídeos do voo e gera laudos nos módulos contratados:
agropecuário, vistoria predial, segurança pública, ambiental, obras,
mapeamento, defesa civil, inspeção industrial, eventos e perímetro.

Fluxo do produto: `login → cliente/propriedade → voo → upload → processamento
→ laudo → histórico/comparativo`.

Projeto Python modular com **Poetry 2.x**, **Python 3.13**, **NiceGUI** e **um
banco independente por módulo** (SQLite por padrão, PostgreSQL opcional). Cada
módulo tem tabelas, CRUD, telas, ocorrências e laudo textual próprios; nenhum
módulo consulta o banco de outro.

## Requisitos

- Python 3.13
- Poetry 2.x
- Git

## Instalação

```bash
git clone https://github.com/klaytonPrinceMS/tisosdocfly.git
cd tisosdocfly
poetry env use 3.13
poetry install
poetry run task start
```

Acesse <http://127.0.0.1:8080/login>. No primeiro boot os bancos são criados
na raiz e as contas de fábrica são semeadas.

### Primeiro acesso (passo a passo)

1. Suba o sistema: `poetry run task start` (pare com `Ctrl+C`).
2. Abra <http://127.0.0.1:8080/login>.
3. Entre com `master` / `master` — o primeiro acesso **força** a troca de
   senha e das credenciais (ver Contas de fábrica).
4. A Home mostra os módulos liberados para a conta; `/voos` concentra
   cliente → propriedade → voo → upload → laudo.
5. O administrador liga/desliga módulos em `/configuracoes` e gerencia cada
   módulo em `/admin/{chave}` (ex.: `/admin/agro`).

### Verificação rápida

```bash
poetry run task lint      # pyflakes: "undefined name" bloqueia
poetry run task teste     # suíte completa (~1-2 min)
poetry run task verificar # lint + testes
```

## Poetry (ambiente e dependências)

O `pyproject.toml` é a fonte única de dependências (não existe
`requirements*.txt`).

```bash
poetry env use 3.13          # cria/usa o venv com Python 3.13
poetry env list              # venvs conhecidos do projeto
poetry install               # instala runtime + dev/teste/docs
poetry install --with graph  # inclui o grupo opcional do graphify
poetry run <comando>         # roda dentro do venv (ex.: poetry run task start)
poetry check                 # valida o pyproject
```

`poetry run task <nome>` executa as tasks de `[tool.taskipy.tasks]` (ver
Comandos abaixo). As dependências de execução ficam em
`[tool.poetry.dependencies]`; testes, lint, segurança e docs no grupo `dev`;
o graphify no grupo opcional `graph`.

## Contas de fábrica

| Conta | Senha | Perfil | Primeiro acesso |
|---|---|---|---|
| `master` | `master` | administrador_geral | força troca de senha e credenciais |
| `qacomum` | `123456` | comum | sem troca forçada |
| `qamaster` | `123456` | administrador_geral | sem troca forçada |

As contas de fábrica nunca são removidas automaticamente. Senha de
desenvolvimento fica no código, nunca na documentação.

## Módulos e rotas

| Módulo | Rota | Banco | O que faz |
|---|---|---|---|
| Núcleo | `/`, `/voos`, `/configuracoes`, `/admin/{chave}` | `db_mod_tisosdocfly.db` | voos, mídia, laudo base, autenticação, tema, auditoria |
| Usuários | `/users` | `db_mod_gest_cad_usuario.db` | cadastro, perfis, papéis por módulo, sessões revogáveis |
| Agropecuário | `/agro` | `db_mod_agro.db` | lavoura/pastagem/rebanho, ocorrências, laudo textual |
| Vistoria Predial | `/vistoria-predial` | `db_mod_vistoria_predial.db` | vistoria, patologias, laudo textual |
| Segurança Pública | `/seguranca` | `db_mod_seguranca.db` | triagem com revisão humana obrigatória |
| Ambiental | `/ambiental` | `db_mod_ambiental.db` | desmatamento, APP, queimada, recuperação |
| Obras | `/obras` | `db_mod_obras.db` | avanço físico, ocorrências, medição |
| Mapeamento | `/mapeamento` | `db_mod_mapeamento.db` | ortomosaico, topografia, produtos geoespaciais |
| Defesa Civil | `/defesa-civil` | `db_mod_defesa_civil.db` | dano pós-desastre, risco geológico |
| Inspeção Industrial | `/inspecao-industrial` | `db_mod_inspecao_industrial.db` | estruturas, torres, linhas, equipamentos |
| Eventos | `/eventos` | `db_mod_eventos.db` | público, fluxo, ocupação, multidão |
| Perímetro e Segurança | `/perimetro` | `db_mod_perimetro.db` | perímetro físico, pontos cegos, iluminação, Wi-Fi/RF (BSSID em hash) |

Há ainda o **Painel de Riscos** (`/riscos`), que agrega defesa civil,
ambiental, obras, segurança e inspeção industrial num resumo municipal ou
corporativo.

## Pipeline de imagem, IA e PDF

O núcleo traz o pipeline transversal, sem depender de modelo treinado:

- **Avaliação em Python puro** (decode PNG/BMP/PPM com stdlib, índices de
  vegetação, bordas, entropia, blobs e proporções). Sem modelo registrado, o
  resultado é `avaliacao-pura-v1` e diz isso.
- Interface para plugar modelo ONNX (`ia.registrar_modelo`) ou via variável
  `TISOSDOCFLY_MODELO_ONNX_<MODULO>`.
- GSD, thumbnails e **laudo PDF** (ReportLab; nunca sobrescreve: usa
  timestamp/sufixo).
- **Multiespectral**: NDVI/SAVI/OSAVI/NDRE/GNDVI/NDWI/EVI, histogramas,
  estatísticas e GeoTIFF a partir de bandas nomeadas `*_R`, `*_G`, `*_B`,
  `*_NIR`, `*_RE`, `*_T`.
- **Linhas de plantio**: Hough em Python puro, GeoJSON de saída.

A tela `/voos` executa **Analisar mídias (IA)** e **Gerar laudo PDF**; cada
módulo tem o atalho **Analisar IA**.

> **Limite obrigatório em segurança pública:** reconhecimento de pessoas e
> consulta a listas exigem base legal, convênio oficial, retenção limitada,
> revisão humana e auditoria. O sistema entrega **triagem e evidência**, nunca
> decisão automática de culpa.

## Estrutura

```
main.py                      # entry point
src/mod_tisosdocfly/         # núcleo (banco central, auth, tema, voos, IA, PDF)
src/mod_gest_cad_usuario/    # gestão de usuários
src/mod_agro/ ...            # demais módulos de negócio
src/assets/                  # CSS, favicon, imagens, docker
tests/                       # suíte standalone + Playwright
docs/                        # documentação MkDocs (tema readthedocs)
main.py, docs/, tests/       # raiz: código e ferramenta
.opencode/                   # agentes, skills e plugins (automação)
db_mod_*.db, logs/, backup/  # raiz (runtime): nunca versionados
```

Cada módulo segue o mesmo esqueleto: `__init__.py`, `bd_manipulador.py`
(único acesso ao banco do módulo), `telas.py` e `telas_administracao.py`.

## Comandos

```bash
poetry run task --list
poetry run task start        # sobe o T! SOS DocFly
poetry run task teste        # suíte completa
poetry run task lint         # pyflakes (undefined name é bloqueante)
poetry run task verificar    # lint + testes
poetry run task teste:e2e    # Playwright (exige o servidor no ar)
poetry run task docs         # mkdocs build --strict
poetry run task bandit       # segurança do código
poetry run task multiespectral -- --r R.tif --nir NIR.tif --out saida
poetry run task linhas       # linhas de plantio
```

## Automação (`.opencode/`)

O repositório traz a pasta `.opencode/`, que concentra a automação de IA do
projeto:

- `.opencode/agent/` — subagentes (`kbp-commit`, `kbp-devSecOps`, `kbp-doc`,
  `kbp-doc_teste`, `kbp-qa` e `kbp-web-design`);
- `.opencode/skills/` — habilidades (ex.: `graphify`);
- `.opencode/plugins/` — plugins.

Toda alteração envolvendo skills, padrão de subagentes, MCP e demais itens
correlatos deve ser implementada dentro de `.opencode/`, seguindo a
organização já existente nessas pastas.

### Graphify (grafo do código)

O graphify gera um grafo de conhecimento do código para responder perguntas
de arquitetura (de onde vem, para onde vai e o que faz cada símbolo). É
opcional e vive fora do versionamento (`graphify-out/`):

```bash
poetry install --with graph   # instala o grupo opcional
poetry run task grafo:extract # cria o grafo (só código)
poetry run task grafo:update  # atualiza após mudanças no código
poetry run task grafo:relatorio # relatório por clusters
poetry run task grafo:saude   # diagnóstico do grafo
poetry run graphify query "Como o login chega ao cadastro de usuários?"
poetry run graphify path "autenticacao" "bd_manipulador"
poetry run graphify explain "pagina_restrita"
```

Detalhes em `docs/1_sistema/01_ferramentas/graphify.md`.

## Variáveis de ambiente

| Variável | Efeito |
|---|---|
| `TISOSDOCFLY_PORTA` / `TISOSDOCFLY_HOST` | porta/host do site (padrão `127.0.0.1:8080`) |
| `TISOSDOCFLY_DOCS_ATIVO=0` | desliga a documentação em `/documentacao` |
| `TISOSDOCFLY_STORAGE_SECRET` | segredo das sessões (troque em produção) |
| `TISOSDOCFLY_DIR_BANCO` | move os `db_mod_*.db` para outro diretório (usado pela suíte) |
| `TISOSDOCFLY_QA_SEM_TROCA=1` | seed de QA sem troca forçada (usado pela suíte) |
| `TISOSDOCFLY_FORCE_SQLITE=1` | força SQLite mesmo com Postgres configurado |
| `TISOSDOCFLY_MODELO_ONNX_<MODULO>` | caminho do modelo ONNX do módulo (ex.: `TISOSDOCFLY_MODELO_ONNX_AGRO`) |

## Banco de dados

- SQLite é o padrão (zero configuração). PostgreSQL é opcional, em container
  (`src/assets/docker/postgres/docker-compose.yml`); selecione em
  `/configuracoes` e reinicie.
- Toda DDL nova precisa funcionar nos dois backends.

## Backup

## Backup

Os bancos são arquivos `db_mod_*.db` na raiz. Pare o servidor, copie os
arquivos e guarde fora do repositório. `db_mod_*.db`, `logs/`, `backup/`,
`site/` e `.venv/` nunca são versionados.

## Documentação detalhada

A documentação completa vive em `docs/` (MkDocs, tema readthedocs) e é
servida em `/documentacao` no boot:

- `docs/1_sistema/` — ferramentas, fundamentos, arquitetura, interface,
  referência, módulos, visão de produto, segurança e registro de mudanças.
- `docs/2_manuais/` — instalação, administrador, usuário comum e manual de
  cada módulo.
- `docs/3_testes/` — casos, plano, relatórios e suíte.

Gere localmente com `poetry run task docs`.
