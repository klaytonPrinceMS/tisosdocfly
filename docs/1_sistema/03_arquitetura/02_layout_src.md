# Layout src/

O código que o Python importa mora em `src/`. A raiz guarda dado de execução e
ferramenta.

| Onde | O que é |
|---|---|
| `src/mod_*/` | Código dos módulos |
| `src/assets/` | CSS, favicon e imagens embarcados |
| raiz | `main.py`, `pyproject.toml`, `poetry.lock`, `mkdocs.yml`, `docs/`, `tests/` |
| raiz (runtime) | `db_mod_*.db`, `logs/`, `backup/`, `site/`, `graphify-out/`, `.venv/` |

## As duas constantes

```python
BASE_DIR    = dirname(dirname(abspath(__file__)))  # src/
DIR_PROJETO = dirname(BASE_DIR)                    # raiz
```

- `BASE_DIR` serve para `src/mod_x` e `src/assets`.
- `DIR_PROJETO` serve para bancos, logs, `site/` e o `cwd` do `mkdocs build`.

Confundir as duas tem dois sintomas: o sistema cria um banco vazio onde
ninguém procura (dados "somem") e um guarda que varre a raiz não encontra
módulo nenhum e aprova. Por isso `tests/check_integridade.py` tem a checagem
explícita do layout.
