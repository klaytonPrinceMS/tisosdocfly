"""Painel administrativo do módulo Segurança Pública (/admin/seguranca)."""
from nicegui import ui

from mod_tisosdocfly import observabilidade
from mod_tisosdocfly.tema_modulo import notificar

from mod_seguranca import bd_manipulador as bd


def _log():
    return observabilidade.get_logger("seguranca")


def mostrar_administracao(ator: str):
    try:
        bd.init_db()
        r = bd.resumo()
        with ui.column().classes("w-full").style("gap: 1rem"):
            with ui.row().classes("w-full items-center"):
                ui.icon("shield").classes("text-4xl")
                with ui.column().style("gap: 0"):
                    ui.label("Administração — Segurança Pública").classes(
                        "text-h5")
                    ui.label(
                        "Banco próprio db_mod_seguranca.db. Triagens isoladas; "
                        "revisão humana e auditoria são obrigatórias."
                    ).classes("text-caption text-grey-7")
            with ui.row().classes("w-full").style("gap: 1rem"):
                for rotulo, valor in (
                        ("Análises", r["total"]),
                        ("Ocorrências", r["ocorrencias"]),
                        ("Revisão pendente", r["pendentes_revisao"])):
                    with ui.card().style("min-width: 180px"):
                        ui.label(str(valor)).classes("text-h5")
                        ui.label(rotulo).classes("text-caption text-grey-7")
            with ui.card().classes("w-full").style(
                    "background: #FFF3E0; border-left: 4px solid #EF6C00"):
                ui.label("Limite jurídico").classes(
                    "text-subtitle1 text-orange-10")
                ui.label(
                    "Reconhecimento de pessoas e consulta a listas exigem "
                    "base legal, convênio oficial, retenção limitada e "
                    "revisão humana. O sistema entrega triagem e evidência, "
                    "nunca decisão automática de culpa."
                ).classes("text-body2 text-orange-9")
            with ui.card().classes("w-full"):
                ui.label("Próximas configurações").classes("text-subtitle1")
                ui.label(
                    "Classes de detecção, limiares de confiança, retenção de "
                    "evidências e integração com bases oficiais entram na "
                    "Onda 4."
                ).classes("text-body2 text-grey-7")
    except Exception as e:
        try:
            _log().exception(f"mostrar_administracao: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao carregar a administração de Segurança.",
                  tipo="error")
