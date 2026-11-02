"""Run the whole standalone test suite from a single pytest entrypoint.

EN — Executes every standalone script in `tests/` as a subprocess and fails if
any exits non-zero.

PT — Executa os scripts standalone de `tests/` em subprocesso e falha se algum
terminar com código de saída diferente de zero.

Uso:
    poetry run pytest
    poetry run python tests/test_suite.py
"""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUITE_DIR = pathlib.Path(__file__).resolve().parent

# Auxiliares e testes que NÃO entram no runner standalone:
# - helpers importados por outros testes;
# - pytest-style (fixtures), que rodam zero testes como script (falso verde);
# - E2E Playwright, que exige servidor e navegador.
EXCLUIR = {
    "test_suite.py",
    "__init__.py",
    "paths_repo.py",
    "qa_login_helper.py",
    # pytest-style / helpers
    "test_fabrica_dados.py",
    # E2E
    "pw_skyrover_login_dashboard.py",
}


def _env_limpo():
    """Ambiente isolado: banco em tests/_bd_teste e QA sem troca forçada."""
    env = dict(os.environ)
    for k in list(env):
        if k.startswith("PYTEST_"):
            del env[k]
    env["SKYROVER_FORCE_SQLITE"] = "1"
    banco_teste = ROOT / "tests" / "_bd_teste"
    banco_teste.mkdir(parents=True, exist_ok=True)
    env["SKYROVER_DIR_BANCO"] = str(banco_teste)
    env["SKYROVER_QA_SEM_TROCA"] = "1"
    sep = os.pathsep
    env["PYTHONPATH"] = sep.join(
        [str(ROOT / "src"), str(ROOT), env.get("PYTHONPATH", "")]
    ).strip(sep)
    return env


def _scripts():
    for p in sorted(SUITE_DIR.glob("*.py")):
        if p.name not in EXCLUIR:
            yield p


def test_suite_standalone():
    """Roda cada script standalone e exige exit 0 em todos."""
    falhas = _rodar_suite(progresso=True)
    assert not falhas, "Falharam:\n\n" + "\n\n".join(falhas)


def _rodar_suite(progresso=False):
    import time as _time
    falhas = []
    total = 0
    for p in _scripts():
        total += 1
        if progresso:
            print(f"[{total}] {p.name} ...", flush=True)
        ini = _time.time()
        try:
            r = subprocess.run(
                [sys.executable, str(p)], capture_output=True, text=True,
                timeout=240, env=_env_limpo(), encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            falhas.append(f"{p.name}: timeout 240s")
            if progresso:
                print("    FALHOU (timeout 240s)", flush=True)
            continue
        dur = _time.time() - ini
        if r.returncode != 0:
            saida = (r.stdout or "")[-1200:] + "\n" + (r.stderr or "")[-1200:]
            falhas.append(f"{p.name}: exit={r.returncode}\n{saida}")
            if progresso:
                print(f"    FALHOU em {dur:.0f}s (exit={r.returncode})",
                      flush=True)
        elif progresso:
            print(f"    OK em {dur:.0f}s", flush=True)
    return falhas


if __name__ == "__main__":
    _falhas = _rodar_suite(progresso=True)
    if _falhas:
        print(f"\nSUITE: {len(_falhas)} script(s) falharam:", flush=True)
        for f in _falhas:
            print(f"\n--- {f}", flush=True)
        sys.exit(1)
