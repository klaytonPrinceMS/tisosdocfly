# Instalação

## Requisitos

- Python 3.13 (`poetry python install 3.13` se necessário)
- Poetry 2.x
- Git

## Passos

```bash
git clone https://github.com/klaytonPrinceMS/tisosdocfly.git
cd tisosdocfly
poetry env use 3.13
poetry install
poetry run task start
```

Acesse `http://127.0.0.1:8080`. No primeiro boot, os dois bancos são criados
na raiz e as três contas de fábrica são semeadas.

## Variáveis úteis

```bash
TISOSDOCFLY_PORTA=8090 poetry run task start
TISOSDOCFLY_HOST=0.0.0.0 poetry run task start
TISOSDOCFLY_DOCS_ATIVO=0 poetry run task start
TISOSDOCFLY_STORAGE_SECRET='troque-isto' poetry run task start
```

## Backup

Os bancos são arquivos em `db_mod_*.db`. Pare o servidor, copie os arquivos e
guarde fora do repositório. `db_mod_*.db`, `logs/` e `backup/` nunca são
versionados.
