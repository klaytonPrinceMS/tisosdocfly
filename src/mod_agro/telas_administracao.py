"""Painel administrativo do módulo Agropecuário (/admin/agro)."""
from nicegui import ui

from mod_skyrover import observabilidade
from mod_skyrover.tema_modulo import notificar

from mod_agro import bd_manipulador as bd


def _log():
    return observabilidade.get_logger("agro")


def mostrar_administracao(ator: str):
    """Renderiza o painel administrativo do módulo."""
    try:
        bd.init_db()
        r = bd.resumo()
        with ui.column().classes("w-full").style("gap: 1rem"):
            with ui.row().classes("w-full items-center"):
                ui.icon("agriculture").classes("text-4xl")
                with ui.column().style("gap: 0"):
                    ui.label("Administração — Agropecuário").classes(
                        "text-h5")
                    ui.label(
                        "Banco próprio db_mod_agro.db. Análises e ocorrências "
                        "ficam isoladas do núcleo e dos demais módulos."
                    ).classes("text-caption text-grey-7")
            with ui.row().classes("w-full").style("gap: 1rem"):
                for rotulo, valor in (
                        ("Análises", r["total"]),
                        ("Concluídas", r["concluido"]),
                        ("Ocorrências", r["ocorrencias"])):
                    with ui.card().style("min-width: 180px"):
                        ui.label(str(valor)).classes("text-h5")
                        ui.label(rotulo).classes("text-caption text-grey-7")
            with ui.card().classes("w-full"):
                ui.label("Próximas configurações").classes("text-subtitle1")
                ui.label(
                    "Limiares por cultura, catálogo de índices, modelos de "
                    "visão computacional e geração de PDF entram na Onda 2."
                ).classes("text-body2 text-grey-7")
    except Exception as e:
        try:
            _log().exception(f"mostrar_administracao: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao carregar a administração do Agro.", tipo="error")
