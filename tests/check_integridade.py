"""Structural guard for modular isolation (AST-only, zero imports executed).

Guarda estrutural do isolamento modular, por análise estática (stdlib `ast`):
  A. Nenhum módulo de negócio importa outro; a comunicação passa pelo núcleo.
  B. Sem ciclos de import em nível de topo entre `mod_*` e `main.py`.
  C. Todo `mod_*` tem `bd_manipulador.py` (nunca `db_manipulador.py`).
  D. O layout `src/` está de pé (`src/` existe, `mod_*` dentro, `main.py` na
     raiz) — senão as checagens varrem zero arquivos e aprovam por acidente.

Execute: poetry run python tests/check_integridade.py
"""
import ast
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_SRC = os.path.join(RAIZ, "src")
NUCLEO = "mod_tisosdocfly"

_OK = 0
_TOTAL = 0
_FALHAS = []


def check(cond, msg):
    global _OK, _TOTAL
    _TOTAL += 1
    if cond:
        _OK += 1
        print(f"  OK [{_OK}] {msg}")
    else:
        _FALHAS.append(msg)
        print(f"  FALHOU [{_TOTAL - _OK}] {msg}")


def _modulo_de(path_rel):
    partes = path_rel.replace("\\", "/").split("/")
    if partes[0] == "main.py":
        return "main"
    if partes[0].startswith("mod_"):
        return partes[0]
    return None


def _alvo_top(modulo_importado):
    if not modulo_importado:
        return None
    primeiro = modulo_importado.split(".")[0]
    if primeiro == "main":
        return "main"
    if primeiro.startswith("mod_"):
        return primeiro
    return None


def _imports_de(caminho):
    try:
        with open(caminho, encoding="utf-8") as f:
            arvore = ast.parse(f.read())
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set(), set()
    topo, lazy = set(), set()

    def _visitar(no, dentro_funcao):
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _visitar(filho, True)
            elif isinstance(filho, (ast.Import, ast.ImportFrom)):
                destino = lazy if dentro_funcao else topo
                if isinstance(filho, ast.Import):
                    for a in filho.names:
                        t = _alvo_top(a.name)
                        if t:
                            destino.add(t)
                else:
                    t = _alvo_top(filho.module or "")
                    if t:
                        destino.add(t)
                    for a in filho.names:
                        t2 = _alvo_top(a.name)
                        if t2:
                            destino.add(t2)
            else:
                _visitar(filho, dentro_funcao)

    _visitar(arvore, False)
    return topo, lazy


def _arquivos_py():
    alvos = []
    main_py = os.path.join(RAIZ, "main.py")
    if os.path.isfile(main_py):
        alvos.append(("main", "main.py", main_py))
    if os.path.isdir(DIR_SRC):
        for raiz, _dirs, arqs in os.walk(DIR_SRC):
            for a in arqs:
                if not a.endswith(".py"):
                    continue
                cheio = os.path.join(raiz, a)
                rel = os.path.relpath(cheio, DIR_SRC)
                mod = _modulo_de(rel)
                if mod is None:
                    continue
                alvos.append((mod, rel, cheio))
    return alvos


def main():
    print("=" * 64)
    print("Integridade modular — T! SOS DocFly")
    print("=" * 64)

    # D) Layout
    check(os.path.isdir(DIR_SRC), "D: src/ existe")
    mods = sorted({m for m, _rel, _c in _arquivos_py()
                   if m and m.startswith("mod_")})
    check(bool(mods), f"D: módulos encontrados em src/: {', '.join(mods)}")
    check(os.path.isfile(os.path.join(RAIZ, "main.py")),
          "D: main.py está na raiz")

    # C) bd_manipulador
    for mod in mods:
        pasta = os.path.join(DIR_SRC, mod)
        check(os.path.isfile(os.path.join(pasta, "bd_manipulador.py")),
              f"C: {mod}/bd_manipulador.py existe")
        check(not os.path.isfile(os.path.join(pasta, "db_manipulador.py")),
              f"C: {mod}/db_manipulador.py NÃO existe")

    # A) módulo de negócio não importa outro
    for mod, rel, caminho in _arquivos_py():
        if not mod.startswith("mod_") or mod == NUCLEO:
            continue
        topo, _lazy = _imports_de(caminho)
        externos = sorted(m for m in topo
                          if m.startswith("mod_") and m != mod
                          and m != NUCLEO)
        check(not externos,
              f"A: {rel} não importa outro módulo de negócio"
              + (f" (achou: {externos})" if externos else ""))

    # B) ciclos de import em nível de topo
    grafo = {}
    for mod, _rel, caminho in _arquivos_py():
        topo, _lazy = _imports_de(caminho)
        grafo.setdefault(mod, set()).update(
            m for m in topo if m and m.startswith("mod_") and m != mod)

    def _ciclo(no, visitados, pilha):
        visitados.add(no)
        pilha.add(no)
        for viz in grafo.get(no, ()):  # noqa: B007
            if viz in pilha:
                return [no, viz]
            if viz not in visitados:
                r = _ciclo(viz, visitados, pilha)
                if r:
                    return r
        pilha.discard(no)
        return None

    visitados = set()
    ciclo = None
    for no in grafo:
        if no not in visitados:
            ciclo = _ciclo(no, visitados, set())
            if ciclo:
                break
    check(ciclo is None,
          "B: nenhum ciclo de import top-level entre mod_*"
          + (f" (achou: {ciclo})" if ciclo else ""))

    print("-" * 64)
    print(f"{_OK}/{_TOTAL} checagens OK")
    if _FALHAS:
        print("FALHAS:")
        for f in _FALHAS:
            print(f"  - {f}")
        return 1
    print("Integridade modular: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
