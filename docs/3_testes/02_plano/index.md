# Plano de testes

## Gates bloqueantes

1. `poetry run task lint` — nenhum `undefined name` em `main.py`, `src/` e
   `tests/`.
2. `poetry run task teste` — toda a suíte standalone sai com código 0.
3. `poetry run python tests/check_integridade.py` — isolamento modular e
   layout `src/`.
4. `poetry run task docs` — `mkdocs build --strict` sem erro.

## Isolamento do banco

A suíte exporta `TISOSDOCFLY_DIR_BANCO=tests/_bd_teste` e
`TISOSDOCFLY_QA_SEM_TROCA=1` para todos os subprocessos. Sem isso, um teste
avulso grava no banco de desenvolvimento.

## Ordem de execução

```bash
poetry run task verificar      # lint + suíte
poetry run task teste:e2e      # com o servidor no ar
```

## Playwright

```bash
cd tests && npm install
poetry run task start          # em outro terminal
poetry run pytest -m e2e -v
```
