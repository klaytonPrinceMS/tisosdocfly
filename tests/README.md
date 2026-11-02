# Testes

## Suíte standalone

```bash
poetry run task teste
```

`tests/test_suite.py` executa cada `test*.py`/`teste*.py` da pasta em
subprocesso. Falha se algum sair com código != 0.

## Um teste avulso

```bash
SKYROVER_DIR_BANCO=/tmp/opencode/bd_teste \
PYTHONPATH="$PWD/src:$PWD" \
poetry run python tests/teste_boot.py
```

Sem `SKYROVER_DIR_BANCO` o teste grava no banco de desenvolvimento.

## Integridade modular

```bash
poetry run python tests/check_integridade.py
```

## E2E (Playwright)

```bash
poetry run task start          # em outro terminal
poetry run pytest -m e2e -v
```

`SKYROVER_BASE_URL` permite apontar para outra porta.

## Regras

- Um assert por comportamento; teste que só "não levantou" não prova nada.
- Assert de **valor**, não de ausência de erro.
- Nunca copie dado real de pessoa para fixture ou massa.
- Todo teste trata banco isolado (`tests/_bd_teste`, ignorado pelo git).
