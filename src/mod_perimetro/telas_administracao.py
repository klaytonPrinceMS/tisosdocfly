"""Painel administrativo do módulo Perímetro (/admin/perimetro).

EN: Perimeter admin panel — summary, legal notice and database layout.

PT-BR: Resumo, aviso de autorização para varredura RF e informação de que o
BSSID é armazenado apenas como hash SHA-256. O banco do módulo é próprio
(`db_mod_perimetro.db`) e não há cross-query.
"""
from nicegui import ui

from mod_skyrover import observabilidade
from mod_skyrover.tema_modulo import notificar

from mod_perimetro import bd_manipulador as bd


def _log():
    return observabilidade.get_logger("perimetro")


def mostrar_administracao(ator: str):
    """Renderiza o painel administrativo do módulo."""
    try:
        bd.init_db()
        r = bd.resumo()
        with ui.column().classes("w-full").style("gap: 1rem"):
            with ui.row().classes("w-full items-center"):
                ui.icon("fence").classes("text-4xl")
                with ui.column().style("gap: 0"):
                    ui.label("Administração — Perímetro").classes("text-h5")
                    ui.label(
                        f"Banco próprio db_mod_perimetro.db. "
                        f"Sessão administrativa: {ator or '—'}."
                    ).classes("text-caption text-grey-7")

            with ui.row().classes("w-full").style("gap: 1rem"):
                for rotulo, valor in (
                        ("Auditorias", r["total"]),
                        ("Concluídas", r["concluido"]),
                        ("Achados", r["achados"]),
                        ("Wi-Fi abertas", r["rf_abertas"]),
                        ("Fora do perímetro", r["fora_perimetro"])):
                    with ui.card().style("min-width: 170px"):
                        ui.label(str(valor)).classes("text-h5")
                        ui.label(rotulo).classes("text-caption text-grey-7")

            with ui.card().classes("w-full"):
                ui.label("Segurança física").classes("text-subtitle1")
                ui.label(
                    f"Achados por severidade: baixa {r['baixa']}, "
                    f"média {r['media']}, alta {r['alta']}, "
                    f"crítica {r['critica']}. "
                    f"{r['pendentes_revisao']} achado(s) sem revisão humana."
                ).classes("text-body2")

            with ui.card().classes("w-full"):
                ui.label("Varredura RF — autorização e privacidade").classes(
                    "text-subtitle1")
                ui.label(
                    "A varredura de Wi-Fi/RF é passiva e só pode ser feita em "
                    "rede própria ou com autorização escrita do responsável. "
                    "O módulo não quebra cifra, não captura tráfego e não "
                    "acessa conteúdo. O BSSID (MAC do ponto de acesso) nunca "
                    "é gravado: o banco guarda apenas o hash SHA-256, usado "
                    "para reconhecer a mesma rede entre auditorias."
                ).classes("text-body2 text-grey-7")
                ui.label(
                    "O hash é pseudonimização local, não anonimização "
                    "irreversível. Trate o resultado como triagem: a "
                    "classificação de risco orienta a revisão humana."
                ).classes("text-caption text-grey-7")

            with ui.card().classes("w-full"):
                ui.label("Tabelas do módulo").classes("text-subtitle1")
                ui.label(
                    "tb_perimetro_auditoria · tb_perimetro_achado · "
                    "tb_perimetro_rf. Sem cross-query com o núcleo: cliente, "
                    "propriedade e voo entram apenas como IDs de referência "
                    "pela API pública de voos."
                ).classes("text-body2 text-grey-7")

            with ui.card().classes("w-full"):
                ui.label("Próximas configurações").classes("text-subtitle1")
                ui.label(
                    "Limiares de sinal por banda, catálogo de classes de "
                    "achado e geração de PDF entram na próxima onda."
                ).classes("text-body2 text-grey-7")
    except Exception as e:
        try:
            _log().exception(f"mostrar_administracao: falha | {e}")
        except Exception:
            pass
        notificar("Erro ao carregar a administração do Perímetro.",
                  tipo="error")
