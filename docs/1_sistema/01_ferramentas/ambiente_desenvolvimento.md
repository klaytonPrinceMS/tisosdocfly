# Ambiente de desenvolvimento

## Requisitos

- **Python 3.13** (o `pyproject.toml` fixa `>=3.13,<3.14`)
- **Poetry 2.x**
- Git

O interpretador do projeto fica em `.venv/`, porque `poetry.toml` configura
`virtualenvs.in-project = true` (arquivo local, não versionado).

## Instalação

```bash
poetry env use 3.13
poetry install                 # runtime + dev
poetry install --without dev   # só runtime
poetry install --with graph    # adiciona o graphify (grupo opcional)
```

Se o 3.13 ainda não existir na máquina:

```bash
poetry python install 3.13
poetry env use 3.13
```

## Comandos do dia a dia

O runner oficial é o **taskipy** (`poetry run task --list`):

```bash
poetry run task start          # sobe o Skyrover
poetry run task teste          # suíte completa
poetry run task lint           # gate de pyflakes (undefined name)
poetry run task verificar      # lint + testes
poetry run task docs           # mkdocs build --strict
poetry run task grafo:update   # atualiza o grafo
```

## Variáveis de ambiente

| Variável | Efeito |
|---|---|
| `SKYROVER_DIR_BANCO` | Move os `db_mod_*.db` para outro diretório (isola testes) |
| `SKYROVER_PORTA` | Porta do site (padrão 8080) |
| `SKYROVER_HOST` | Bind (padrão `127.0.0.1`) |
| `SKYROVER_DOCS_ATIVO=0` | Não monta `/documentacao` no boot |
| `SKYROVER_STORAGE_SECRET` | Segredo do cookie de sessão em produção |

A suíte de testes já exporta `SKYROVER_DIR_BANCO` para um diretório isolado —
nunca rode um teste avulso sem essa variável.
