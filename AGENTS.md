# AGENTS.md — Diretrizes de Desenvolvimento Assistido por Agente

> Fonte de verdade para qualquer agente (OpenCode, Codex, Cursor, Claude Code)
> atuando no **T! SOS DocFly**. Siga à risca.

## 1. Visão geral e regra de ouro

O T! SOS DocFly é uma aplicação web Python modular, criada do zero, com **Poetry
2.x**, **Python 3.13**, **NiceGUI** e **um banco independente por módulo**.

**REGRA DE OURO:** todo artefato de um módulo vive dentro de
`src/mod_<nome>/`. Nada de arquivo de módulo solto na raiz. A raiz guarda
apenas o que o AGENTS.md §2.2 permite.

**Shell:** use sempre **bash** no Linux/macOS. Não use `cmd`/PowerShell para
editar arquivos.

## 2. Arquitetura

### 2.1 Módulos iniciais

| Módulo | Papel | Rota | Banco |
|---|---|---|---|
| `mod_tisosdocfly` | Núcleo: voos, mídia, laudo base | `/`, `/voos`, `/configuracoes`, `/admin/{chave}` | `db_mod_tisosdocfly.db` |
| `mod_gest_cad_usuario` | Usuários | `/users` | `db_mod_gest_cad_usuario.db` |
| `mod_agro` | Agropecuário (MVP) | `/agro` | `db_mod_agro.db` |
| `mod_vistoria_predial` | Vistoria Predial (MVP) | `/vistoria-predial` | `db_mod_vistoria_predial.db` |
| `mod_seguranca` | Segurança Pública (MVP) | `/seguranca` | `db_mod_seguranca.db` |
| `mod_ambiental` | Ambiental (MVP) | `/ambiental` | `db_mod_ambiental.db` |
| `mod_obras` | Obras (MVP) | `/obras` | `db_mod_obras.db` |
| `mod_mapeamento` | Mapeamento (MVP) | `/mapeamento` | `db_mod_mapeamento.db` |
| `mod_defesa_civil` | Defesa Civil (MVP) | `/defesa-civil` | `db_mod_defesa_civil.db` |
| `mod_inspecao_industrial` | Inspeção Industrial (MVP) | `/inspecao-industrial` | `db_mod_inspecao_industrial.db` |
| `mod_eventos` | Eventos (MVP) | `/eventos` | `db_mod_eventos.db` |
| `mod_perimetro` | Perímetro e segurança física/lógica (MVP) | `/perimetro` | `db_mod_perimetro.db` |

Os nove módulos de negócio estão em **MVP textual**: tabelas, CRUD, telas,
ocorrências e laudo resumido. IA/visão computacional, geoprocessamento e PDF
são a camada seguinte. Não crie um décimo módulo sem pedido explícito.

Os módulos nascem **ligados** (`MODULOS_ATIVOS_POR_PADRAO`), mas o
administrador pode desligá-los. Só `usuarios` é indispensável.

### 2.1.1 Produto — T! SOS DocFly

O T! SOS DocFly é a plataforma de **laudos de voo de qualquer drone
(multidrone)**. O cliente
autentica, envia fotos/vídeos do voo e gera laudos nos módulos contratados.

Fluxo: `login → cliente/propriedade → voo → upload → processamento → laudo →
histórico/comparativo`.

Módulos implementados em MVP (ver `docs/1_sistema/10_projeto/`):

| Módulo | Chave | MVP | Próximo |
|---|---|---|---|
| Agropecuário | `agro` | lavoura/pastagem/rebanho, ocorrências, laudo textual | detector de gado, índices, CNN, PDF |
| Vistoria predial | `vistoria_predial` | vistoria, patologias, laudo textual | comparativo, CNN, PDF |
| Segurança pública | `seguranca` | triagem, ocorrências, revisão humana | aglomeração/veículos/placas, bases oficiais |
| Ambiental | `ambiental` | análise, ocorrências, laudo textual | IA, PDF |
| Obras | `obras` | análise, ocorrências, avanço | IA, PDF |
| Mapeamento | `mapeamento` | análise, produtos (GeoTIFF/COG/GeoJSON) | ortomosaico/GDAL |
| Defesa civil | `defesa_civil` | análise, ocorrências, laudo textual | IA, PDF |
| Inspeção industrial | `inspecao_industrial` | análise, ocorrências, laudo textual | IA, PDF |
| Eventos | `eventos` | análise, ocorrências, público | IA, PDF |
| Perímetro e segurança | `perimetro` | auditoria física, Wi-Fi/RF, achados | varredura autorizada, IA, PDF |

**Limite obrigatório em segurança pública:** reconhecimento de pessoas e
consulta a listas exigem base legal, convênio oficial, retenção limitada,
revisão humana e auditoria. O sistema entrega **triagem e evidência**, nunca
decisão automática de culpa.

### 2.2 Estrutura padrão de um módulo

```
src/mod_<nome>/
├── __init__.py              # encapsulamento e bootstrap
├── bd_manipulador.py        # ÚNICO ponto de acesso ao banco do módulo
├── telas.py                 # telas de negócio: mostrar_tela(nome, perfil)
└── telas_administracao.py   # painel standalone: mostrar_administracao(ator)
```

O núcleo (`mod_tisosdocfly`) acrescenta `bd_conexao.py`, `banco_conexao.py`,
`repositorio.py`, `models/`, `autenticacao.py`, `tema_modulo.py`,
`tela_configuracoes.py`, `documentacao.py` e `observabilidade.py`.

### 2.3 Layout da raiz

| Onde | O que é |
|---|---|
| `src/mod_*/` | código importado pelo Python |
| `src/assets/` | CSS, favicon e imagens embarcados |
| `main.py` | entry point (raiz) |
| `docs/` | documentação MkDocs |
| `tests/` | suíte standalone + E2E |
| raiz (runtime) | `db_mod_*.db`, `logs/`, `backup/`, `site/`, `graphify-out/`, `.venv/` |

As duas constantes:

```python
BASE_DIR    = dirname(dirname(abspath(__file__)))  # src/
DIR_PROJETO = dirname(BASE_DIR)                    # raiz
```

`BASE_DIR` serve para `src/mod_x` e `src/assets`; `DIR_PROJETO` serve para
bancos, logs, `site/` e o `cwd` do `mkdocs build`.

### 2.4 Banco por módulo

- Cada módulo tem o **próprio banco**. Nunca faça cross-query.
- A chave de banco vive em `MODULOS_BD` (`mod_tisosdocfly/repositorio.py`).
- `SQLite` (`db_mod_<chave>.db`) e `PostgreSQL` (database `db_mod_<chave>`) são
  espelhos. Toda DDL nova deve funcionar nos dois.
- `CrudBase` é o caminho para escrita transacional; `sqlite3` cru só em
  migração do núcleo, via `banco_conexao`.

## 3. Convenções

| Elemento | Padrão | Exemplo |
|---|---|---|
| Idioma | Português BR | `calcular_total` |
| Classes | `PascalCase` | `GerenciadorUsuario` |
| Classes internas | `_PascalCase` | `_GerenciadorInterno` |
| Funções | `snake_case` | `obter_usuario_por_id()` |
| Constantes | `MAIUSCULAS_SNAKE` | `TENTATIVAS_MAXIMAS` |
| Pacote | `mod_<nome>` | `mod_gest_cad_usuario` |
| Tabela | `tb_<nome>` | `tb_usuarios` |
| Coluna | `snake_case` | `nome_usuario` |

### 3.1 Tratamento de erros

- Toda função trata exceção com `try/except Exception` (nunca `except:` cru).
- O `except` registra a causa (`logger.exception` ou `traceback`) e, com UI,
  notifica o usuário.
- Nunca engula `NameError` com `except Exception: pass` novo — o gate de
  `pyflakes` existe para isso.
- Restaure botões, spinners e travas no `finally`.

### 3.2 Docstrings

Resumo em inglês no topo, explicação em Português BR abaixo.

### 3.3 Dados de pessoa

Nunca use nome, matrícula, CPF, e-mail ou telefone real em exemplo, teste,
docstring ou documentação. Use `MT-1234` e nomes fictícios.

## 4. Autenticação e seed

### 4.1 Contas de fábrica

Seed idempotente em `mod_gest_cad_usuario/bd_manipulador.py` (`init_db`):

| Usuário | Senha | Perfil | Comportamento |
|---|---|---|---|
| `master` | `master` | `administrador_geral` | Primeiro login **força** troca de senha e credenciais |
| `qacomum` | `123456` | `comum` | QA; **sem** troca forçada |
| `qamaster` | `123456` | `administrador_geral` | QA; **sem** troca forçada |

- As contas de fábrica **nunca** são removidas automaticamente. Quem decide é
  o administrador.
- Com `TISOSDOCFLY_QA_SEM_TROCA=1`, o seed sobe sem troca para QA (usado na suíte).
- Senha de desenvolvimento pode ficar no **código**; **nunca** na documentação.

### 4.2 Dois eixos de permissão

| Eixo | Valores | Onde |
|---|---|---|
| Perfil global | `comum`, `administrador_modulo`, `administrador_geral` | `tb_usuarios.user_perfil` |
| Papel no módulo | `comum`, `administrador` | `tb_acesso_usuario.papel` |

`administrador_modulo` **não** dá escrita em módulo nenhum. Escrita exige a
linha em `tb_acesso_usuario`.

### 4.3 Guard obrigatório

Toda rota protegida passa por `mod_tisosdocfly.telas.pagina_restrita`. Ele valida
sessão, revogação, timeout, troca obrigatória, permissão e se o módulo está
ligado. Nunca renderize tela de módulo sem ele.

## 5. Git

Comandos git são liberados quando solicitados via terminal pelo usuário.
`commit` e `push` somente com pedido expresso.

Formato: `AAMMDD HHMM breve resumo no imperativo`

Exemplo: `261102 1530 Adiciona modulo de gestao de usuarios`

- Nunca `--force`, `--no-verify` nem pular hooks.
- Nunca commitar `.env`, segredos, `db_mod_*.db`, `*.db-wal/shm`, `backup/`,
  `logs/`, `site/`, `graphify-out/`, `.venv/`, `node_modules/`, `poetry.toml`.
- `poetry.lock` **é versionado**.

## 6. Dependências e execução (Poetry)

Fonte única: `pyproject.toml`. Não crie `requirements*.txt`.

| Grupo | O que vai |
|---|---|
| `[tool.poetry.dependencies]` | runtime (NiceGUI, FastAPI, SQLAlchemy, bcrypt, etc.) |
| `[tool.poetry.group.dev.dependencies]` | pytest, pyflakes, bandit, semgrep, pip-audit, safety, faker, mkdocs, taskipy |
| `[tool.poetry.group.graph.dependencies]` | opcional — `graphifyy`, só com `--with graph` |

```bash
poetry env use 3.13
poetry install
poetry install --with graph
poetry run task --list
poetry run task start
```

### Tasks

| Task | O que faz |
|---|---|
| `task start` | sobe o T! SOS DocFly |
| `task teste` | suíte completa (runner standalone) |
| `task lint` | gate de `pyflakes`: `undefined name` bloqueia |
| `task verificar` | lint + testes |
| `task teste:e2e` | Playwright (exige servidor no ar) |
| `task docs` | `mkdocs build --strict` |
| `task bandit` / `semgrep` / `audit` | segurança |
| `task grafo:extract` / `update` / `relatorio` / `saude` | graphify |

## 7. Subagentes autorizados

Arquivos em `.opencode/agent/`. Todos usam frontmatter `description` +
`mode: subagent` e são carregados no boot do OpenCode — **reinicie o OpenCode**
depois de criar/editar.

| Subagente | Quando acionar | O que entrega |
|---|---|---|
| `kbp-commit` | commit/push padronizados | estuda diff, stage seguro, mensagem `AAMMDD HHMM` |
| `kbp-devSecOps` | segurança, dependências, segredos | bandit, semgrep, pip-audit, safety, gitleaks, k6 |
| `kbp-doc` | documentação | audita `docs/`, MkDocs readthedocs, docstring bilíngue, `graphify update` |
| `kbp-doc_teste` | massa de teste | gera 15 registros fictícios via Faker (padrão) |
| `kbp-qa` | testes e qualidade | pytest/pytest-playwright, pirâmide, `pyflakes` bloqueante |
| `kbp-web-design` | UI | responsivo, mobile-first, a11y, sem JS solto |

### Como acionar

No OpenCode, mencione o agente na mensagem:

```
@kbp-qa escreva os testes do CRUD de usuários
@kbp-doc atualize docs/3_testes/06_suite.md e rode o graphify update
@kbp-commit faça o commit das alterações de hoje
```

Ou peça explicitamente ao agente principal para delegar via ferramenta
`task`/`subagent`.

### Regras comuns aos subagentes

- Responsabilidade única; não misture dois papéis no mesmo retorno.
- Nomes de arquivo/pasta seguros: só `a-z`, `0-9`, `_`, `-` e o `.` da
  extensão. Sem espaço, acento, `<>:"/\|?*`, `'";&|$` ou `--`.
- Git liberado quando pedido; em dúvida, consulte `kbp-commit`.
- Nunca segredo, banco ou dado real no stage.

## 8. Skills

### 8.1 graphify

Arquivo: `.opencode/skills/graphify/SKILL.md` (+ `references/`). O plugin
`.opencode/plugins/graphify.js` injeta o lembrete na sessão, mas **não**
atualiza o grafo sozinho.

```bash
poetry install --with graph
poetry run graphify extract . --code-only
poetry run graphify update .
poetry run graphify query "Como o login chega ao cadastro de usuários?"
poetry run graphify path "autenticacao" "bd_manipulador"
poetry run graphify explain "pagina_restrita"
```

Regras:

- `graphify-out/` nunca é versionado.
- Toda tarefa de documentação termina com `update` executado de verdade, com
  mtime do `graph.json` conferido antes/depois.
- Fases paralelas não rodam `update`; só a consolidação final.

## 8.2 Pipeline de IA, geoprocessamento e PDF

| Arquivo | Papel |
|---|---|
| `src/mod_tisosdocfly/avaliacao_imagens.py` | avaliação padrão em Python puro (decode PNG/BMP/PPM, métricas, índices, bordas, blobs) |
| `src/mod_tisosdocfly/ia.py` | registro de modelo (`registrar_modelo`, ONNX opcional) e uso da avaliação pura |
| `src/mod_tisosdocfly/geoprocessamento.py` | métricas RGB, ExG/VARI/GLI/TGI, GSD, thumbnail, GeoTIFF opcional |
| `src/mod_tisosdocfly/multiespectral.py` | bandas R/G/B/NIR/RE/T, NDVI/SAVI/OSAVI/NDRE/GNDVI/NDWI/EVI, estatísticas, histograma, GeoTIFF e AOI |
| `src/mod_tisosdocfly/linhas_plantio.py` | Hough em Python puro: máscara de vegetação, convex hull, morfologia, Sobel, linhas, GeoJSON |
| `src/mod_tisosdocfly/relatorio.py` | PDF com metadados, ocorrências, métricas e imagens |
| `src/mod_tisosdocfly/ui_analise.py` | botão "Analisar IA" reutilizado pelos módulos |

Regras:

- **Nunca simular modelo treinado.** Sem modelo registrado, o resultado é
  `avaliacao-pura-v1` (Python puro) e diz isso.
- PNG/BMP/PPM são decodificados pela stdlib; JPEG/WebP usam Pillow só como
  decoder. A conta é sempre Python puro.
- **Segurança pública não infere pessoas/armas** no baseline; devolve
  `revisao_humana_obrigatoria=True` e exige detector homologado/base legal.
- Toda análise é gravada em `tb_analises_ia` (núcleo), com modelo, versão,
  ocorrências e métricas.
- Laudo PDF nunca sobrescreve: usa timestamp/sufixo.
- Mídia em `src/mod_tisosdocfly/midia/` e laudos em `src/mod_tisosdocfly/laudos/`
  são ignorados pelo git.
- Para plugar modelo: `ia.registrar_modelo("agro", "cnn-x", funcao)` ou
  `TISOSDOCFLY_MODELO_ONNX_AGRO=/caminho/modelo.onnx`.
- Multiespectral: bandas nomeadas `*_R`, `*_G`, `*_B`, `*_NIR`, `*_RE`,
  `*_T`; processe com `voos.processar_multiespectral` ou
  `python -m mod_tisosdocfly.multiespectral`. O módulo não faz fotogrametria
  (ODM/Metashape antes).
- Linhas de plantio: `voos.detectar_linhas_plantio` ou
  `python -m mod_tisosdocfly.linhas_plantio`. Hough em Python puro, 256 px,
  linhas retas; não prometa precisão em linhas curvas.

## 9. Padrão de testes

- Runner: `tests/test_suite.py`, que executa cada script standalone em
  subprocesso e falha se algum sair != 0.
- Banco isolado: `TISOSDOCFLY_DIR_BANCO=tests/_bd_teste` e
  `TISOSDOCFLY_QA_SEM_TROCA=1` injetados pelo runner.
- Todo teste é standalone (`unittest`, `if __name__ == "__main__": ...`).
- E2E em `tests/pw_*.py` com `pytest-playwright`, marcador `e2e`, fora do
  runner standalone.
- Gate estático: `pyflakes` sem `undefined name`.
- Asserts de valor, não de ausência de erro.

```bash
poetry run task verificar
poetry run python tests/check_integridade.py
poetry run task teste:e2e
```

## 10. Padrão de documentação

- MkDocs com tema **readthedocs**, em português (`mkdocs.yml`).
- `docs/` organizado em três baldes: `1_sistema/`, `2_manuais/`, `3_testes/`;
  prefixos numéricos na ordem do menu; `index.md` nunca numerado.
- Sem datas em nome de arquivo/pasta/menu; a data vai dentro da seção.
- `mkdocstrings` lê docstrings de `src/`.
- Build bloqueante: `poetry run task docs` (`--strict`).
- `/documentacao` é montado no boot (desligue com `TISOSDOCFLY_DOCS_ATIVO=0`).

## 11. graphify — estado

O grafo é construído sob demanda. Para criar do zero:

```bash
poetry run task grafo:extract
poetry run task grafo:relatorio
```

O `.graphifyignore` exclui runtime, dependências e artefatos. Se o grafo não
existir, o plugin não injeta o lembrete — é o comportamento esperado.
