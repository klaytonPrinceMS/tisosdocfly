"""Bloco de análise de imagem reutilizável pelos módulos de negócio.

Reusable image-analysis block for business modules. Renders a button that runs
the core pipeline for the flight and the module, then shows the stored
analyses. The module's own database is untouched; results live in the core
`tb_analises_ia` and are read through the public `mod_tisosdocfly.voos` API.
"""
from nicegui import ui

from mod_tisosdocfly import observabilidade, voos
from mod_tisosdocfly.tema_modulo import ler_tema, notificar
from mod_tisosdocfly.ui_comum import botao


def _log():
    return observabilidade.get_logger("tisosdocfly")


def bloco_analise(ator: str, voo_id, chave_modulo: str, contexto=None):
    """Renderiza o botão "Analisar IA" e o resultado já armazenado do voo."""
    try:
        estado = {"ocupado": False}

        @ui.refreshable
        def _painel():
            try:
                itens = voos.listar_analises_ia(
                    voo_id=voo_id, modulo=chave_modulo)
            except Exception:
                itens = []
            if not itens:
                return
            for item in itens[:5]:
                try:
                    import json as _json
                    ocorrencias = _json.loads(
                        item.get("ocorrencias_json") or "[]")
                except Exception:
                    ocorrencias = []
                with ui.expansion(
                        f"IA #{item['id']} · {item.get('modelo') or 'baseline'}",
                        icon="auto_awesome").classes("w-full"):
                    ui.label(
                        f"Versão: {item.get('versao') or '-'} · revisão "
                        f"humana: "
                        f"{'sim' if item.get('revisao_humana') else 'não'}"
                    ).classes("text-caption text-grey-7")
                    ui.label(item.get("resumo") or "").classes(
                        "text-body2 whitespace-pre-line")
                    for o in ocorrencias:
                        if not isinstance(o, dict):
                            continue
                        ui.label(
                            f"• {o.get('classe')} · "
                            f"{o.get('severidade')} · confiança "
                            f"{float(o.get('confianca') or 0):.2f}"
                        ).classes("text-caption")

        def _executar():
            if estado["ocupado"]:
                return
            estado["ocupado"] = True
            try:
                resumo = voos.executar_analise_ia(
                    voo_id, chave_modulo, ator=ator, contexto=contexto)
                if resumo["total"] == 0:
                    notificar(
                        "Nenhuma imagem neste voo. Envie fotos em /voos.",
                        tipo="warning")
                elif resumo["analisadas"]:
                    notificar(
                        f"{resumo['analisadas']}/{resumo['total']} imagem(ns), "
                        f"{resumo['ocorrencias']} ocorrência(s).",
                        tipo="positive")
                else:
                    notificar("A análise não produziu resultado.",
                              tipo="warning")
                _painel.refresh()
            except Exception as exc:
                try:
                    _log().exception(f"bloco_analise: {exc}")
                except Exception:
                    pass
                notificar("Erro ao executar a análise de imagem.",
                          tipo="error")
            finally:
                estado["ocupado"] = False

        with ui.row().classes("w-full items-center").style("gap: .5rem"):
            botao("Analisar IA", icone="auto_awesome", variante="texto",
                  chave_modulo=chave_modulo, on_click=_executar) \
                .props(f"data-testid={chave_modulo}-analisar-ia")
            ui.label(
                "Baseline RGB. Segurança exige detector homologado."
            ).classes("text-caption text-grey-6")
        _painel()
    except Exception as exc:
        try:
            ler_tema(chave_modulo)
            _log().exception(f"bloco_analise({chave_modulo}): {exc}")
        except Exception:
            pass
