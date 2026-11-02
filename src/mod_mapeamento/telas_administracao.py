"""Painel administrativo do módulo Mapeamento (/admin/mapeamento)."""
from nicegui import ui

from mod_skyrover import observabilidade
from mod_skyrover.tema_modulo import notificar

from mod_mapeamento import bd_manipulador as bd


def _log():
    return observabilidade.get_logger("mapeamento")


def mostrar_administracao(ator: str):
    """Renderiza o painel administrativo do módulo."""
    try:
        bd.init_db()
        r = bd.resumo()
        with ui.column().classes("w-full").style("gap: 1rem"):
            with ui.row().classes("w-full items-center"):
                ui.icon("map").classes("text-4xl")
                with ui.column().style("gap: 0"):
                    ui.label("Administração — Mapeamento").classes("text-h5")
                    ui.label(
                        "Banco próprio db_mod_mapeamento.db. Análises e "
                        "produtos ficam isolados do núcleo e dos demais "
                        "módulos."
                    ).classes("text-caption text-grey-7")
            with ui.row().classes("w-full").style("gap: 1rem"):
                for rotulo, valor in (
                        ("Análises", r["total"]),
                        ("Concluídas", r["concluido"]),
                        ("Produtos", r["produtos"])):
                    with ui.card().style("min-width: 180px"):
                        ui.label(str(valor)).classes("text-h5")
                        ui.label(rotulo).classes("text-caption text-grey-7")
            with ui.card().classes("w-full"):
                ui.label("Próximas configurações").classes("text-subtitle1")
                ui.label(
                    "Geração de ortomosaico, conversão para COG, validação "
                    "de hash, catálogo de formatos e publicação de produtos "
                    "entram na próxima etapa."
                ).classes("text-body2 text-grey-7")
    except Exception as e:
        try:
            _log().exception(f"mostrar_administracao: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao carregar a administração do Mapeamento.",
                  tipo="error")
