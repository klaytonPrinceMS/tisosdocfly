"""EN — Resolves repository paths for the test suite (post-`src/` layout).

PT-BR — Resolve caminhos do repositório para a suíte de testes (layout `src/`).

Regra de layout (código em `src/`, dado de execução na raiz):

| Caminho relativo        | Onde está | Por quê |
|-------------------------|-----------|---------|
| `mod_tisosdocfly/telas.py` | `src/`    | código importado |
| `assets/css/x.css`      | `src/`    | vai junto do código |
| `main.py`               | raiz      | entry point |
| `db_mod_tisosdocfly.db`    | raiz      | dado de execução |
| `docs/`, `mkdocs.yml`   | raiz      | ferramenta |
"""
from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
BASE_DIR = RAIZ / "src"
DIR_PROJETO = RAIZ

_RAIZ_EM_SRC = ("mod_", "assets")


def caminho(rel: str) -> Path:
    """Resolve um caminho relativo para a base correta (sem checar existência)."""
    primeiro = str(rel).replace("\\", "/").split("/", 1)[0]
    if primeiro.startswith(_RAIZ_EM_SRC):
        return BASE_DIR / rel
    return DIR_PROJETO / rel


def existe(rel: str) -> bool:
    """Diz se o caminho relativo existe na base correta."""
    try:
        return caminho(rel).is_file()
    except (OSError, ValueError):
        return False


def juntar(*partes: str) -> str:
    """Equivalente a `os.path.join(caminho(primeira_parte), *resto)`."""
    if not partes:
        return str(DIR_PROJETO)
    return os.path.join(str(caminho(partes[0])), *partes[1:])
