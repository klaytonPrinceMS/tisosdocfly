"""Patches NiceGUI timers to tolerate page teardown (no "parent slot deleted").

O NiceGUI dispara timers em background tasks; quando a página é navegada ou
fechada, o slot do elemento é removido e um tick pendente lança
`RuntimeError: The parent slot of Timer(...) has been deleted` (ruído no log
do carrossel do Blog e dos timers `once` de reload). Este patch torna esse
cenário silencioso e PARA o timer cujo slot desapareceu (evita ruído e
vazamento de timers).

EN: Silences NiceGUI timers whose parent slot was deleted and stops them,
preventing the noisy "The parent slot of Timer has been deleted" runtime error
after navigating away from a page.
"""
from contextlib import nullcontext

import nicegui.ui as _ui_modulo
from nicegui import ui as _ui
from nicegui.elements.timer import Timer as _Timer

_orig_get_context = _Timer._get_context
_orig_should_stop = _Timer._should_stop
_orig_notify = _ui_modulo.notify


def _notify_com_tempo_do_sistema(*args, **kwargs):
    """`ui.notify` passa a respeitar o tempo configurado de avisos.

    POR QUE ISTO EXISTE (04/10/2026, pedido do responsável): o sistema tem
    **232 chamadas** a `ui.notify` espalhadas por 8 arquivos (104 só no
    Empenhos, 52 na Solicitação, 34 no Blog), e todas elas iam DIRETO ao
    NiceGUI com o tempo padrão da biblioteca — 5 segundos, fixo, ignorando
    `notificacao_timeout`. Só o `tema_modulo.notificar` respeitava a
    configuração, e Changing só ele não mudava nada que a pessoa vê na
    prática: mudar a configuração não surtia efeito justamente porque quase
    nenhum aviso passa por lá.

    Este patch é o lugar CERTO por dois motivos: ele é o ponto único onde o
    NiceGUI é ajustado e roda antes de qualquer tela (ver `main.py`), e ele
    pega as 232 de uma vez — reescrever 232 chamadas seria 232 chances de
    errar, e a próxima chamada nova voltaria a escapar.

    `timeout` explícito continua VALENDO: quem passa `timeout=0` (fixar na
    tela) ou outro valor continua com o que pediu. O patch só preenche o que
    não foi informado, que é o caso dos 232.

    O tempo é lido do `tb_config` na hora de cada aviso (o valor é o mesmo
    para a sessão inteira, mas a leitura é barata e evita estado em cache
    que divergiria do banco depois de uma mudança pela tela de
    configurações).
    """
    if "timeout" not in kwargs:
        try:
            from mod_tisosdocfly.tema_modulo import notificacao_timeout
            # MILISSEGUNDOS, E O MAIS IMPORTANTE DESTA LINHA.
            #
            # `ui.notify` NÃO usa a classe `Notification` do NiceGUI: ele
            # manda o `options` cru pro front, que chama
            # `Quasar.Notify.create(msg)`. E o Quasar espera `timeout` em
            # MILISSEGUNDOS. Mandar segundos aqui é mandar 20 para um campo
            # que quer 20.000 — o aviso nascia e sumia em 20 MILISSEGUNDOS,
            # que na tela é "não apareceu".
            #
            # Foi exatamente o que aconteceu na primeira tentativa: o patch
            # estava correto, o `timeout` saía 20 do `tb_config`, e o toast
            # vivia menos de 1 segundo. A culpa não era a configuração, era a
            # UNIDADE. O `Notification` do NiceGUI faz `(timeout or 0) * 1000`
            # porque recebe segundos; o `ui.notify` não faz essa conversão
            # porque delega direto ao Quasar.
            kwargs["timeout"] = notificacao_timeout() * 1000
        except Exception:
            # Falha ao ler a config não pode impedir o aviso de aparecer: o
            # que acontece sem este `except` é o aviso SOME, que é o oposto
            # do que se quer ao tratar de tempo de exibição.
            pass
    return _orig_notify(*args, **kwargs)


def _get_context(self):
    """Returns nullcontext instead of raising when the parent slot is gone."""
    try:
        return self.parent_slot or nullcontext()
    except RuntimeError:
        return nullcontext()


def _should_stop(self):
    """Stops the timer when its parent slot was deleted (page navegada/fechada).

    Um timer global (sem slot) segue normal; um timer cujo slot morreu (weakref
    expirada) para de rodar."""
    try:
        if getattr(self, "_parent_slot", None) is not None:
            _ = self.parent_slot
    except RuntimeError:
        return True
    return _orig_should_stop(self)


def aplicar():
    """Aplica os patches no NiceGUI (idempotente).

    Os DOIS grupos (timers e avisos) têm guarda PRÓPRIA. A primeira versão
    devolvia cedo quando o Timer já estava patcheado — e, como o patch é
    chamado mais de uma vez no boot, a segunda chamada pulava o aviso, que é
    exatamente o que ele devia fazer. Guarda por grupo, não uma só."""
    if not getattr(_Timer, "_patch_aplicado", False):
        _Timer._get_context = _get_context
        _Timer._should_stop = _should_stop
        _Timer._patch_aplicado = True
    # O aviso é patcheado por um marcador PRÓPRIO: o `_patch_aplicado` do
    # Timer não pode governar o `ui.notify` — são dois objetos distintos.
    #
    # E o patch precisa ser aplicado em DOIS lugares, que é a parte que
    # quase passou: `ui.notify` é uma FUNÇÃO reexportada. Trocar só o
    # atributo `ui.notify` não alcança quem já fez `from nicegui import ui` e
    # chama `ui.notify(...)` — que é o caso das 232 chamadas. E o `from
    # nicegui.ui import notify` direto nem enxerga o atributo `ui`.
    #
    # A verificação de "já patcheado" precisa que os DOIS lados apontem para a
    # NOSSA função, não que o atributo tenha um marcador: um pode estar
    # patcheado e o outro não, e aí o patch reaplicado Embrulha a si mesmo
    # (aí o tempo sai dobrado) ou não pega nada.
    if getattr(_ui_modulo.notify, "_patch_avisos_aplicado", False):
        return
    _ui_modulo.notify = _notify_com_tempo_do_sistema
    _ui.notify = _notify_com_tempo_do_sistema
    _ui_modulo.notify._patch_avisos_aplicado = True
    _aplicar_traducao_pt_br()


def _aplicar_traducao_pt_br():
    """Injeta o PT-BR nas traduções do NiceGUI (banner de desconexão).

    EN: Injects PT-BR into NiceGUI's translation table (disconnect banner).

    PT-BR: O NiceGUI 3.15 traz `translations` sem `pt`/`pt-BR`, e o `main.py`
    sobe com `language="pt-BR"` — sem esta tabela, o banner de "conexão
    perdida" caía no fallback em inglês. A tabela mora no processo (é lida
    por `client.py` a cada página), então injetar no boot vale para todas
    as páginas sem tocar nos arquivos da biblioteca. Falha aqui nunca
    derruba o boot: sem PT-BR, o banner volta ao inglês.
    """
    try:
        from nicegui.translations import translations as _traducoes
        _pt_br = {
            "connection_lost": "Conexão perdida.",
            "trying_to_reconnect": "Tentando reconectar… não feche a página.",
            "message_too_long": "Mensagem muito longa",
            "message_too_long_body": "A mensagem excede o limite do WebSocket.",
        }
        for _chave in ("pt-BR", "pt"):
            try:
                _traducoes[_chave] = dict(_pt_br)
            except Exception:
                pass
    except Exception:
        pass
