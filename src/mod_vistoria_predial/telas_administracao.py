"""Painel administrativo do módulo Vistoria Predial (/admin/vistoria_predial)."""
from nicegui import ui

from mod_skyrover import observabilidade
from mod_skyrover.tema_modulo import notificar

from mod_vistoria_predial import bd_manipulador as bd


def _log():
    return observabilidade.get_logger("vistoria_predial")


def mostrar_administracao(ator: str):
    try:
        bd.init_db()
        r = bd.resumo()
        with ui.column().classes("w-full").style("gap: 1rem"):
            with ui.row().classes("w-full items-center"):
                ui.icon("apartment").classes("text-4xl")
                with ui.column().style("gap: 0"):
                    ui.label("Administração — Vistoria Predial").classes(
                        "text-h5")
                    ui.label(
                        "Banco próprio db_mod_vistoria_predial.db. Vistorias "
                        "e patologias isoladas do núcleo e dos demais módulos."
                    ).classes("text-caption text-grey-7")
            with ui.row().classes("w-full").style("gap: 1rem"):
                for rotulo, valor in (
                        ("Vistorias", r["total"]),
                        ("Concluídas", r["concluido"]),
                        ("Patologias", r["patologias"])):
                    with ui.card().style("min-width: 180px"):
                        ui.label(str(valor)).classes("text-h5")
                        ui.label(rotulo).classes("text-caption text-grey-7")
            with ui.card().classes("w-full"):
                ui.label("Próximas configurações").classes("text-subtitle1")
                ui.label(
                    "Classes de patologia, limiares de severidade, "
                    "comparativo temporal e PDF entram na Onda 3."
                ).classes("text-body2 text-grey-7")
    except Exception as e:
        try:
            _log().exception(f"mostrar_administracao: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao carregar a administração da Vistoria.",
                  tipo="error")
