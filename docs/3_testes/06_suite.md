# Suíte de testes

## Como rodar

```bash
poetry run task teste
```

O runner é `tests/test_suite.py`: ele executa cada script `test*.py` e
`teste*.py` de `tests/` em subprocesso e falha se algum sair com código
diferente de zero.

## O que o runner injeta

| Variável | Valor |
|---|---|
| `SKYROVER_DIR_BANCO` | `tests/_bd_teste` |
| `SKYROVER_QA_SEM_TROCA` | `1` |
| `PYTHONPATH` | `src` + raiz |

## Teste novo

```bash
poetry run task teste:novo > tests/teste_novo.py
```

O template já traz `src` no `sys.path`, banco isolado e `unittest.main`.

## E2E

Os testes `pw_*.py` são pytest-style, exigem navegador e o servidor no ar.
Ficam fora do runner standalone de propósito: rodá-los como script executa
zero testes e devolve falso verde.

```bash
poetry run task start
poetry run pytest -m e2e -v
```
