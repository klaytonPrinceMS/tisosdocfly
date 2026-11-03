"""Module backup management dialog — reusable header component.

Diálogo de gestão de backup DO MÓDULO — componente reutilizado no header.

Cada módulo gerencia o próprio banco: intervalo em horas, execução imediata
e histórico das cópias retidas. Acesso: administrador geral OU administrador
daquele módulo (validado por quem abre o diálogo).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from nicegui import ui

from mod_tisosdocfly.bd_conexao import get_config, set_config
from mod_tisosdocfly.tema_modulo import botao as _botao_tema
from mod_tisosdocfly.tema_modulo import notificar
from mod_tisosdocfly.ui_comum import dialogo_formulario
from mod_tisosdocfly.rotinas import (
    MAPA_BACKUPS, intervalo_backup, reagendar_backup,
    backup_modulo, listar_backups,
)
from mod_tisosdocfly.bd_manipulador import audit_log


def pode_gerenciar(usuario, chave_modulo):
    """Admin geral gerencia qualquer módulo; admin do módulo, só o seu."""
    from mod_tisosdocfly import autenticacao
    if autenticacao.perfil_global_de(usuario) == "administrador_geral":
        return True
    return autenticacao.eh_admin_do_modulo(usuario, chave_modulo)


def abrir_dialogo(usuario, chave_modulo):
    """Opens the module backup dialog.

    Abre o diálogo de backup do módulo informado.
    """
    if chave_modulo not in MAPA_BACKUPS:
        return
    if not pode_gerenciar(usuario, chave_modulo):
        notificar("Sem permissão para gerir backups deste módulo", tipo="negative")
        return
    _arquivo, nome_amigavel = MAPA_BACKUPS[chave_modulo]

    with dialogo_formulario(f"Backup » {nome_amigavel}",
                            descricao=f"Banco gerenciado: {_arquivo}"
                            ) as (dlg, card, miolo, grade):
        with miolo:
            with ui.row().classes("w-full items-end flex-wrap").style("gap: 0.5rem"):
                horas = ui.number(
                    "Intervalo automático (horas)",
                    value=intervalo_backup(chave_modulo), min=1, max=720, precision=0,
                ).props("outlined dense").classes("w-52")
                ultima = listar_backups(chave_modulo)[None:1]
                if ultima:
                    _, quando = ultima[0]
                    ui.badge(f"Última cópia: {quando}",
                             color="blue-2").props("outline dense text-color=blue-9")

                def salvar_intervalo():
                    set_config(f"backup_horas:{chave_modulo}",
                               int(horas.value) or 12)
                    reagendar_backup(chave_modulo, int(horas.value) or 12)
                    audit_log(usuario, "tisosdocfly", "config_alterada",
                              f"backup_horas:{chave_modulo}={int(horas.value) or 12}h")
                    notificar(f"Intervalo salvo: {int(horas.value) or 12}h (aplicado sem reiniciar)",
                              tipo="positive")

                _botao_tema("Salvar intervalo", on_click=salvar_intervalo)

                def rodar_agora():
                    gerado = backup_modulo(chave_modulo)
                    if gerado:
                        audit_log(usuario, "tisosdocfly", "backup_manual",
                                  f"módulo={chave_modulo} arquivo={gerado}")
                        notificar(f"Cópia gerada: {gerado}", tipo="positive")
                        grade_backups.refresh()
                    else:
                        notificar("Falha ao gerar a cópia", tipo="negative")

                _botao_tema("Fazer backup agora", icone="backup", on_click=rodar_agora)

            ui.separator()
            ui.label("Cópias retidas (retenção: 10 por banco)") \
                .classes("text-subtitle2 font-bold text-grey-8")

            @ui.refreshable
            def grade_backups():
                linhas = listar_backups(chave_modulo)
                if not linhas:
                    ui.label("Nenhuma cópia retida até o momento.") \
                        .classes("text-caption text-grey-6")
                    return
                with ui.grid(columns="1fr auto auto").classes(
                        "w-full bg-grey-1 rounded px-3 py-1.5 text-caption font-bold text-grey-8"):
                    for c in ("Arquivo", "Tamanho", "Data/hora"):
                        ui.label(c)
                for arq, kb, quando in linhas:
                    with ui.grid(columns="1fr auto auto").classes("w-full text-caption"):
                        ui.label(arq)
                        ui.label(f"{kb} KB")
                        ui.label(quando)

            grade_backups()
            with ui.row().classes("w-full justify-end mt-2"):
                _botao_tema("Fechar", variante="texto", on_click=dlg.close)

    dlg.open()
