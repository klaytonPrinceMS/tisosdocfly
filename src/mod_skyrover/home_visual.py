"""Visual switcher for Home dashboard — uma tela por CSS disponível.

Módulo de comutação visual do Resumo do sistema (Home "/"): cada framework
em assets/css/frameworks gera uma tela dedicada /home-{framework}. O `pic`
nativo é o padrão (Quasar puro, sem framework externo). Híbrido não é usado
aqui — o padrão é `pic` suave; todos são injetados por página via
tema_css.injetar_framework — sem CDN, sem reset global fora do escopo.

Uso:
    from mod_skyrover.home_visual import ler_modelo, aplicar_framework, aplicar_modelo, classes_resumo
    aplicar_modelo(ler_modelo())
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CHAVE_CONFIG = "home_modelo_visual"
MODELO_PADRAO = "pic"
# Pic nativo padrão; cada CSS novo tem tela dedicada /home-{nome}
# Mantém compatibilidade com os 12 novos já expostos no menu Empenhos.
FRAMEWORKS = (
    "spectre",
    "chota",
    "milligram",
    "skeleton",
    "water",
    "mvp",
    "tachyons",
    "uikit",
    "foundation",
    "semantic",
    "materialize",
    "primer",
)
# Todos os frameworks fisicamente em disco (inclui os 5 “antigos”)
FRAMEWORKS_TODOS = (
    "bootstrap",
    "bulma",
    "daisyui",
    "pico",
    "picnic",
    "spectre",
    "chota",
    "milligram",
    "skeleton",
    "water",
    "mvp",
    "tachyons",
    "uikit",
    "foundation",
    "semantic",
    "materialize",
    "primer",
)
VALIDOS = ("pic",) + FRAMEWORKS_TODOS

ROTULOS = {
    "pic": "PIC — Quasar nativo suave (padrão)",
    "bootstrap": "Bootstrap 5.3.8",
    "bulma": "Bulma 1.0.2",
    "daisyui": "DaisyUI 5.6.8",
    "pico": "Pico 2",
    "picnic": "Picnic 7.1.0",
    "spectre": "Spectre 0.5.9",
    "chota": "Chota 0.8.0",
    "milligram": "Milligram 1.4.1",
    "skeleton": "Skeleton 2.0.4",
    "water": "Water.css 2.1.1",
    "mvp": "MVP.css 1.14",
    "tachyons": "Tachyons 4.12.0",
    "uikit": "UIkit 3.21.5",
    "foundation": "Foundation 6.8.1",
    "semantic": "Semantic UI 2.5",
    "materialize": "Materialize 1.0",
    "primer": "Primer 21",
}

# Forçar modelo sem tocar tb_config (ex.: /home-pic injeta via FORCAR_MODELO).
FORCAR_MODELO = None  # type: ignore

_ENV_FORCAR = (os.environ.get("HOME_MODELO_VISUAL") or "").strip().lower()
if _ENV_FORCAR in VALIDOS:
    FORCAR_MODELO = _ENV_FORCAR


def _get_config_safe(chave, default, get_config=None):
    if get_config is not None:
        try:
            return get_config(chave, default)
        except Exception:
            return default
    try:
        from mod_skyrover.bd_conexao import get_config as _gc

        return _gc(chave, default)
    except Exception:
        return default


def ler_modelo(get_config=None) -> str:
    """Lê o modelo visual atual (pic|framework), fail-soft para 'pic'."""
    if FORCAR_MODELO in VALIDOS:
        return FORCAR_MODELO
    try:
        raw = _get_config_safe(CHAVE_CONFIG, MODELO_PADRAO, get_config)
        v = (raw or "").strip().lower()
        return v if v in VALIDOS else MODELO_PADRAO
    except Exception:
        return MODELO_PADRAO


def salvar_modelo(valor: str, set_config=None) -> bool:
    """Grava o modelo em tb_config; retorna True se gravou."""
    v = (valor or "").strip().lower()
    if v not in VALIDOS:
        return False
    try:
        if set_config is not None:
            set_config(CHAVE_CONFIG, v)
        else:
            from mod_skyrover.bd_conexao import set_config as _sc

            _sc(CHAVE_CONFIG, v)
        try:
            from mod_skyrover.tema_modulo import _cfg as _cfg_cache, ler_tema

            _cfg_cache.cache_clear()  # type: ignore
            ler_tema.cache_clear()  # type: ignore
        except Exception:
            pass
        return True
    except Exception:
        return False


def aplicar_framework(nome_ou_flag=True) -> bool:
    """Injeta o CSS local do framework (str) ou compat bool (True=bootstrap)."""
    try:
        from mod_skyrover import tema_css

        if isinstance(nome_ou_flag, str):
            nome = nome_ou_flag.strip().lower()
            if not nome or nome == "pic":
                return False
            return bool(tema_css.injetar_framework(nome))
        if not nome_ou_flag:
            return False
        return bool(tema_css.injetar_framework("bootstrap"))
    except Exception:
        return False


def aplicar_modelo(modelo: str) -> bool:
    """Aplica o modelo completo — water é escopado só no card Resumo."""
    m = (modelo or "").strip().lower()
    if m == "pic":
        injetar_pic_suave()
        return True
    if m == "water":
        # Water.css escopado: estiliza APENAS o Resumo, sem reset global
        injetar_water_card()
        return True
    if m in FRAMEWORKS_TODOS:
        ok = aplicar_framework(m)
        try:
            injetar_resumo_overrides(m)
        except Exception:
            pass
        return ok
    injetar_pic_suave()
    return False


def injetar_water_card():
    """Water.css escopado — estiliza APENAS o card Resumo (sem reset global) + sombra lateral direita."""
    try:
        from nicegui import ui

        ui.add_head_html("""
<style>
/* Home — Water escopado (só no Resumo) — altura -25% + ícone ampliado + sombra lateral direita */
.home-resumo-water{border-radius:12px;border:1px solid #dfe8f0;background:#fafcfd;box-shadow:6px 0 16px rgba(0,0,0,.07);border-left-width:4px}
.home-stat-water{border-radius:12px;box-shadow:0 1px 6px rgba(0,0,0,.06);border:1px solid #dfe8f0;background:#ffffff;transition:box-shadow .18s ease, transform .15s ease, border-color .18s}
.home-stat-water:hover{box-shadow:0 8px 22px rgba(0,0,0,.08);transform:translateY(-2px);border-color:#c8d7e6}
.home-stat-water .home-stat-icon{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#e8f1f8}
.home-stat-water .text-primary{color:#0b6a9a !important}
@media (max-width: 640px){
  .home-stat-water{padding:.35rem !important}
}
</style>
""")
    except Exception:
        pass


def injetar_pic_suave():
    """PIC puro — Quasar nativo suave para o Resumo (sombra lateral direita padronizada)."""
    try:
        from nicegui import ui

        ui.add_head_html("""
<style>
/* Home — PIC puro (sem framework externo) — altura -25% + ícone ampliado + sombra lateral direita */
.home-resumo-pic{border-radius:16px;box-shadow:6px 0 16px rgba(0,0,0,.07);border:1px solid #e5e7eb;border-left-width:4px}
.home-stat-pic{border-radius:16px;box-shadow:0 1px 8px rgba(0,0,0,.06);border:1px solid #e5e7eb;background:#fff;transition:box-shadow .18s ease, transform .15s ease}
.home-stat-pic:hover{box-shadow:0 8px 22px rgba(0,0,0,.08);transform:translateY(-2px)}
.home-stat-pic .home-stat-icon{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center}
@media (max-width: 640px){
  .home-stat-pic{padding:.35rem !important}
}
</style>
""")
    except Exception:
        pass


def injetar_resumo_overrides(framework: str):
    """Overrides mínimos quando um framework está ativo para convivência com Quasar."""
    try:
        from nicegui import ui

        # Escopo .home-framework evita vazamento global
        ui.add_head_html(f"""
<style>
/* Home — overrides quando {framework} está ativo */
.home-framework .home-stat{{border-radius:14px}}
</style>
""")
    except Exception:
        pass


# ===== Helpers de classes condicionais =====

def classes_card_resumo(modelo: str) -> str:
    """Classes do card externo 'Resumo do sistema' por modelo (sombra lateral direita padronizada)."""
    m = (modelo or "pic").lower()
    base = "w-full border-l-4 shadow-md"
    if m == "pic":
        return f"{base} home-resumo-pic"
    return f"{base} home-framework home-resumo-{m}"


def classes_stat(modelo: str) -> str:
    """Classes de cada card de métrica por modelo."""
    m = (modelo or "pic").lower()
    if m == "pic":
        return "home-stat-pic flex-1 min-w-[160px] max-w-[260px] bg-white"
    # frameworks: mantém estrutura Quasar mas com escopo do framework
    return f"home-framework home-stat home-stat-{m} flex-1 min-w-[160px] max-w-[260px] bg-white shadow-sm border"


def classes_wrap_resumo(modelo: str) -> str:
    """Classes do wrap que contém os 3 stats."""
    return "w-full justify-center gap-4 flex-wrap"
