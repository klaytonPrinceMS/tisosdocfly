"""Dynamic module page-route registration for NiceGUI (custom slugs persist).

Registro dinâmico de rotas de páginas de módulos no servidor NiceGUI. Os
decoradores fixos de `main.py` registram as rotas padrão; este módulo permite
que slugs customizados (gravados em `tb_modulos.rota`) sejam re-registrados
após um restart, sem duplicidade (registrar o mesmo path duas vezes quebraria
o servidor).
"""
from nicegui import ui

from mod_tisosdocfly import autenticacao

# Espelho dos decorators fixos de main.py (chave -> rota padrão). Usado para
# semear `_registradas` (as rotas padrão já foram registradas pelos decorators)
# e como referência das rotas nativas.
DEFAULT_ROTAS = {
    "blog": "/blog",
    "users": "/users",
    "auditoria": "/auditoria",
    "editar_pdf": "/edit-pdf",
    "empenhos": "/renomear-empenho",
    "solicita_impressao": "/solicita-impressao",
}

# chave -> função de página. Preenchido em main.py após cada decorator fixo.
REGISTRO_MODULOS: dict = {}

# Rotas já registradas no servidor (evita duplicidade). As rotas padrão já
# foram registradas pelos decorators fixos de main.py.
_registradas: set = set(DEFAULT_ROTAS.values())


def _normalizar_rota(rota):
    """Normalizes a route: leading '/', lowercase, no spaces/duplicate slashes.

    Normaliza uma rota: garante '/' inicial, lowercase, remove espaços
    (vira hífen) e slashes duplicados."""
    rota = (rota or "").strip().strip("/").lower().replace(" ", "-")
    while "//" in rota:
        rota = rota.replace("//", "/")
    return "/" + rota if rota else ""


def registrar_modulo(chave, rota):
    """Registers a module page route in NiceGUI (idempotent).

    Registra a rota de um módulo no servidor NiceGUI via `ui.page`, se a
    chave tiver função de página em `REGISTRO_MODULOS` e a rota ainda não
    estiver em `_registradas`. Idempotente: registrar o mesmo path duas
    vezes quebraria o servidor, por isso `_registradas` evita duplicidade.
    Se a chave não tiver página, apenas retorna (módulo futuro)."""
    if chave not in REGISTRO_MODULOS:
        return
    rota = _normalizar_rota(rota)
    if not rota or rota in _registradas:
        return
    ui.page(rota)(REGISTRO_MODULOS[chave])
    _registradas.add(rota)


def montar_rotas_ativas():
    """Re-registers persisted custom routes from tb_modulos (idempotent).

    Lê `tb_modulos` (via `autenticacao.modulos_registrados()`) e chama
    `registrar_modulo` para todos os módulos, re-registrando slugs
    customizados persistidos no banco após um restart. As rotas padrão já
    foram registradas pelos decorators fixos de main.py."""
    for chave, _nome, _icone, rota, _ativo in autenticacao.modulos_registrados():
        registrar_modulo(chave, rota)
