"""Política de senha do sistema: medidor, aceite de risco e tentativas de login.

O que este módulo responde, e o que ele **não** faz:

1. **Medidor de dificuldade** — mostra quão forte a senha é, mesmo quando ela
   já vazou. Vazamento e dificuldade são coisas diferentes: `123456` vaza e é
   fraca, mas a dificuldade é o que mede o trabalho de ataque.

2. **Aceite de risco com dupla confirmação** — o servidor que escolhe uma senha
   fraca ainda pode usá-la. O que muda é que ele **assina, sabendo**: um
   checkbox que ele tem de marcar consciously, e a confirmação de que entendeu.

3. **Tentativas de login** — limite configurável (3 por padrão), **sem travar a
   conta**: quem erra espera mais, até 30 segundos. Não é "fraco" por omissão:
   é a decisão de quem usa o sistema, porque bloqueio por tentativas muda um
   servidor que esqueceu a senha em mais um número no DTI — e a prefeitura
   tem gente que entra cinco vezes ao dia.

**Por que o aceite é só aviso, e não bloqueio.** Decisão de 30/09/2026 do
responsável: o aceite **registra e audita**, não impede promoção de perfil.
Isso não é esquecimento de segurança — é a posição de que a **
responsabilidade é do servidor que escolheu a senha fraca**, e ela se prova no
registro e na auditoria, não num trinco que o próprio sistema aplicaria contra
quem ele atendeu. O que o sistema garante é o **dever do controlador**: ter
medidas de segurança (Art. 6º, VI e VII, e Art. 46 da LGPD). O que ele não pode
garantir em nome do servidor é a senha boa dele, e fingir que garante —
impedindo o cargo — seria substituir o consentimento Fiscal pela decisão do
software.

O texto do aceite reproduz, em português claro, o que a lei diz e o que a lei
não diz. Ver `TEXTO_ACEITE_RISCO`.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Tentativas de login (30/09/2026, decisão do responsável).
TENTATIVAS_PADRAO = 3
TENTATIVAS_MINIMO = 3
TENTATIVAS_MAXIMO = 20
ATRASO_INICIAL_SEG = 1.0
ATRASO_MAXIMO_SEG = 30.0
PASSO_ATRASO_SEG = 1.5
JANELA_TENTATIVAS_SEG = 900  # 15 min: após isso a contagem zera

CHAVE_TENTATIVAS = "login_tentativas_maximas"
CHAVE_ATRASO_MAXIMO = "login_atraso_maximo_seg"

# Faixas do medidor. Os limites são de bits TOTAIS (comprimento x entropia),
# e não de "caracteres especiais": uma senha de 20 caracteres sorteados vale
# mais do que uma de 10 com símbolos. Ver `validador_senha._entropia`.
# --- PISO DE FORÇA: abaixo disto a senha não é usável (30/09/2026) ---
# Decisão do responsável: **0,5** da barra é o corte. Abaixo disso a senha
# simplesmente não pode ser usada — sem aceite, sem exceção, sem saída. O
# aceite de risco deixou de ser para senha fraca e passou a ser para senha
# BOA COM RISCO: passa de 0,5, mas aparece em vazamento, ou tem palavra do
# órgão, ou tem ano, ou tem o nome do usuário.
#
# Isso inverte o desenho anterior, e a inversão é o ponto: antes a pessoa podia
# aceitar uma senha de 15 bits. Agora o sistema recusa, e o que ela pode
# aceitar é o risco residual de uma senha decente.
FORCA_MINIMA = 0.5

# Piso de 75 bits para "Muito forte" é ALTÍSSIMO para senha humana: uma senha
# de 20 caracteres bem variados dá ~76. Colocar o patamar em 75 fazia quase toda
# senha boa cair no topo e a barra deixar de distinguir. Os pisos medem o que o
# validador considera aceitável (45 = "aceitável", 60 = "boa"), e o topo fica
# como elogio para o que é sorteado de verdade — não como rótulo de rotina.
FAIXAS = (
    (0, "muito_fraca", "Muito fraca", "negative"),
    (30, "fraca", "Fraca", "negative"),
    (45, "media", "Média", "warning"),
    (60, "forte", "Forte", "positive"),
    (90, "muito_forte", "Muito forte", "positive"),
)

# Cor da BARRA por faixa de força (0 a 1) — decisão do responsável, 30/09/2026.
#
# Mora aqui, e não na tela, pelo mesmo motivo de `FORCA_MINIMA`: o corte da
# cor é o mesmo corte que decide se a senha pode ser usada. Se a barra
# pintasse de verde a 0,45 — enquanto o sistema recusa por estar abaixo de
# 0,5 —, a tela estaria dizendo "vá em frente" na cor de quem aprova.
#
# | faixa         | cor         | leitura                               |
# |:--------------|:------------|:--------------------------------------|
# | abaixo de 0,5 | `negative`  | vermelho — não pode ser usada         |
# | 0,5 até 0,7   | `warning`   | amarelo — dá para usar, mas não é forte|
# | acima de 0,7  | `positive`  | verde — forte                         |
#
# O amarelo é a faixa em que a senha passa do corte e ainda não é forte, que é
# também a faixa em que costuma aparecer o risco residual e o aceite. As três
# cores são as do Quasar (`negative`/`warning`/`positive`), e é por isso que a
# faixa é a mesma das cinco faixas de RÓTULO acima — uma tela com duas
# palettes de cor discordando entre si seria pior que nenhuma.
FORCA_FORTE = 0.7
COR_BARRA_FRACA = "negative"   # < FORCA_MINIMA — não pode ser usada
COR_BARRA_MEDIA = "warning"    # >= FORCA_MINIMA e < FORCA_FORTE
COR_BARRA_FORTE = "positive"   # >= FORCA_FORTE

# Papéis que o aceite NÃO impede (decisão: aviso e registro, sem bloqueio).
PERFIS_ADMIN = ("administrador_geral", "administrador_modulo")


# ---------------------------------------------------------------------------
#  Sorteio de senha sugerida
# ---------------------------------------------------------------------------
# Conjuntos SEM ambiguidade visual. As letras `I l 1 O 0` ficam de fora de
# propósito: senha sugerida é copiada por mão, often ditada por telefone e
# às vezes lida de um papel — um `l` que parece `1` transforma a sugestão em
# senha diferente da que o validador checou, e o erro só aparece no login.
_ALFA_MAIUSCULAS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_ALFA_MINUSCULAS = "abcdefghijkmnopqrstuvwxyz"
_DIGITOS = "23456789"
_ESPECIAIS = "!@#$%&*?-_"

# 16 é o piso do sorteio, e não um número arbitrário: o medidor mede ~3,7% de
# força por caractere em senha variada, e o piso de 50% é atingido em 14
# (medido em 05/10/2026). Com 16 a sugestão entra com folga, e o
# `analisar_offline` é quem confirma.
TAMANHO_SORTEADO = 16


def senha_aleatoria(tamanho: int = TAMANHO_SORTEADO) -> str:
    """Sorteia uma senha forte. `""` se não conseguir.

    EN: Random strong password; empty string on failure.

    PT-BR: Sorteia uma senha com um caractere de CADA classe — minúscula,
    maiúscula, número e especial — e completa até `tamanho` com caracteres
    escolhidos de todos os conjuntos juntos. A primeira volta de cada classe
    é o que garante os quatro tipos que o validador exige; o resto é sorteio
    solto, que é o que dá a variedade que o medidor mede.

    Usa `secrets`, e não `random`, porque senha sugerida por um sistema
    municipal não pode vir de gerador previsível. O valor da sugestão é ser
    forte, e `random` daria uma senha mais fraca com a mesma aparência.

    NÃO garante que a senha passe no validador: um bloco como "abcd" ou
    "1234" pode sair por acaso. Quem chama precisa conferir com
    `analisar_offline` — em `telas.py` isso é `_senha_proposta()`, que
    sorteia de novo até passar. Fail-soft: devolve `""` em vez de levantar.
    """
    try:
        import secrets as _secrets
        tam = max(8, int(tamanho or TAMANHO_SORTEADO))
        # A primeira de cada classe: é o que garante os quatro tipos.
        partes = [
            _secrets.choice(_ALFA_MINUSCULAS),
            _secrets.choice(_ALFA_MAIUSCULAS),
            _secrets.choice(_DIGITOS),
            _secrets.choice(_ESPECIAIS),
        ]
        todo = (_ALFA_MINUSCULAS + _ALFA_MAIUSCULAS + _DIGITOS + _ESPECIAIS)
        while len(partes) < tam:
            partes.append(_secrets.choice(todo))
        _secrets.SystemRandom().shuffle(partes)
        return "".join(partes)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
#  Medidor de dificuldade
# ---------------------------------------------------------------------------
def classificar(bits: float) -> tuple[str, str, str]:
    """`(chave, rótulo, cor)` a partir dos bits totais de entropia.

    A varredura vai do maior piso para o menor e **para na primeira casada**,
    porque `FAIXAS` está em ordem crescente: percorrer de cima para baixo dá
    o patamar mais alto que a senha alcança, que é a única leitura certa.
    Percorrendo de baixo para cima, o laço nunca saía do primeiro item — e tudo
    era "Muito fraca", qualquer que fosse a senha. Era o bug que a prova
    pegou: 70 bits saíam como "muito fraca".
    """
    try:
        v = float(bits or 0)
    except Exception:
        v = 0.0
    for piso, chave, rotulo, cor in reversed(FAIXAS):
        if v >= piso:
            return chave, rotulo, cor
    chave, rotulo, cor = FAIXAS[0][1:]
    return chave, rotulo, cor


def forca(medidor: dict) -> float:
    """A força como fração de 0 a 1 — a mesma escala da barra na tela."""
    try:
        return max(0.0, min(1.0, float((medidor or {}).get("percentual", 0)) / 100.0))
    except Exception:
        return 0.0


def acima_do_piso(medidor: dict) -> bool:
    """A senha passa do piso de 0,5? Abaixo disso ela não é usável."""
    try:
        return forca(medidor) >= FORCA_MINIMA
    except Exception:
        return False


def cor_da_barra(medidor: dict) -> str:
    """A cor da barra de força para este medidor (nome de cor do Quasar).

    Três faixas e nenhum critério novo: o corte é o mesmo `FORCA_MINIMA` que
    decide se a senha pode ser usada, e o topo é `FORCA_FORTE`. Ver o quadro
    nas constantes — o ponto é que a cor e a regra não podem divergir.
    """
    try:
        f = forca(medidor)
        if f < FORCA_MINIMA:
            return COR_BARRA_FRACA
        if f < FORCA_FORTE:
            return COR_BARRA_MEDIA
        return COR_BARRA_FORTE
    except Exception:
        return COR_BARRA_FRACA


def medidor(senha: str) -> dict:
    """O medidor completo: bits, faixa, rótulo, cor e barra.

    Usa o `validador_senha` já pronto — não repete regra de força aqui. O que
    este módulo acrescenta é a **faixa visual** e a leitura que responde "mas
    ela vazou e eu ainda assim…": vazamento é um aviso independente da
    dificuldade, e os dois aparecem juntos na tela.
    """
    try:
        from mod_skyrover.validador_senha import analisar_offline
        r = analisar_offline(senha or "", "")
        bits = float(r.get("bits") or 0.0)
        chave, rotulo, cor = classificar(bits)
        # A barra é a fração do bits contra o topo da escala (100). Não usa
        # `nivel` do validador: o medidor é contínuo, e o usuário precisa ver
        # que está perto de um patamar, não só "média" ou "forte".
        return {
            "bits": round(bits, 1),
            "nivel": chave,
            "rotulo": rotulo,
            "cor": cor,
            "percentual": max(2, min(100, int(bits))),
            "vazou": bool(r.get("vazou")),
            "bloqueios": list(r.get("bloqueios") or []),
        }
    except Exception:
        logger.exception("politica_senha: medidor falhou")
        return {"bits": 0.0, "nivel": "muito_fraca", "rotulo": "Muito fraca",
                "cor": "negative", "percentual": 2, "vazou": False,
                "bloqueios": []}


# ---------------------------------------------------------------------------
#  O ATALHO (18/10/2026, decisão do responsável)
# ---------------------------------------------------------------------------
# A senha que NÃO passa do piso de força deixa de ser "não pode ser usada" e
# vira "pode, se você assinar". O pedido foi literal e está nas três
# condições abaixo, e nada mais:
#
#   1. ter ao menos `senha_tamanho_minimo` caracteres (6, por padrão);
#   2. não ter vazado — nenhuma consulta achou a senha em vazamento;
#   3. usar pelo menos DOIS dos quatro tipos (número, especial, maiúscula,
#      minúscula).
#
# "Mesmo que a cor esteja vermelha" é o ponto: a barra continua vermelha,
# porque a senha continua fraca — o que muda é que ela deixa de ser recusada
# e passa a exigir o aceite de risco, o mesmo que a faixa amarela já exigia.
#
# Mora aqui, e não na tela, pelo mesmo motivo de `FORCA_MINIMA`: o corte que
# decide o que pode ser gravado é um, e a tela, o validador e o serviço leem
# o mesmo. Divergir entre os três era como uma senha entrava em um e era
# recusada em outro.
TIPOS_MINIMOS_ACEITE = 2


def minimo_essencial(senha: str, vazou: bool = False) -> bool:
    """A senha que pode ser usada mesmo com a barra no vermelho.

    EN: The password that can be used even with the bar in the red.

    PT-BR: True quando a senha cumpre o ATALHO do responsável — mínimo de
    caracteres, não vazada e com pelo menos dois tipos de caractere. Quem
    chama daqui decide o que fazer com a resposta: a tela abre o termo de
    risco, e o validador deixa de tratar a força como bloqueio.
    """
    try:
        if vazou:
            return False
        s = senha or ""
        from mod_skyrover.validador_senha import (
            CHAVE_TAMANHO_MINIMO, TAMANHO_MINIMO_PADRAO, tipos_usados)
        try:
            minimo = int(_config(CHAVE_TAMANHO_MINIMO,
                                 str(TAMANHO_MINIMO_PADRAO)))
        except Exception:
            minimo = TAMANHO_MINIMO_PADRAO
        if len(s) < minimo:
            return False
        return tipos_usados(s) >= TIPOS_MINIMOS_ACEITE
    except Exception:
        logger.exception("politica_senha: minimo_essencial falhou")
        return False


def regras_para_tela() -> str:
    """As regras da senha, escritas para quem vai ESCOLHER uma.

    EN: The password rules, written for the person choosing one.

    PT-BR: As regras em UM texto, para a tela de troca de senha.

    Existe por um pedido do responsável (18/10/2026): as regras estavam
    espalhadas em mensagens de erro que aparecem uma de cada vez, e quem está
    escolhendo a senha não tem como saber a regra ANTES de errar. A tela passa
    a mostrar a lista inteira, de uma vez.

    O texto é uma LINHA POR REGRA e começa na primeira regra, sem frase de
    introdução (18/10/2026): é uma lista para conferir item por item.

    O texto é montado a partir das MESMAS constantes que o validador usa —
    o mínimo de caracteres vem da configuração (`senha_tamanho_minimo`), e não
    de uma cópia. Regra escrita duas vezes diverge na primeira edição de uma
    das duas, e aqui a divergência seria uma senha recusada sem explicação.

    Os tipos de caractere espelham `_TIPOS_EXIGIDOS` do validador; os
    caracteres especiais são os mesmos do sorteio (`_ESPECIAIS`), para quem
    não souber onde achá-los.
    """
    try:
        from mod_skyrover.validador_senha import (
            CHAVE_TAMANHO_MINIMO, TAMANHO_MINIMO_PADRAO)
        try:
            minimo = int(_config(CHAVE_TAMANHO_MINIMO,
                                 str(TAMANHO_MINIMO_PADRAO)))
        except Exception:
            minimo = TAMANHO_MINIMO_PADRAO
        especiais = " ".join(_ESPECIAIS)
        piso = int(round(FORCA_MINIMA * 100))
        # SEM título e SEM frase de introduction (18/10/2026): a lista começa
        # na primeira regra. Uma linha por regra, e só.
        return (
            f"• ter no mínimo {minimo} caracteres;\n"
            "• usar os quatro tipos: letra minúscula, letra maiúscula, "
            "número e caractere especial ("
            f"{especiais});\n"
            # A linha "não usar só números, nem repetir a mesma letra ou
            # bloco" SAIU da lista (18/10/2026, pedido do responsável): quem
            # é obrigado a usar os quatro tipos já não pode ter senha de só
            # números nem uma letra repetida — a regra está contida na de
            # cima, e repetir as duas só fazia a lista mais longa.
            #
            # A VERIFICAÇÃO continua no validador (`analisar_offline`), porque
            # quem escreve a regra é quem decide, e reduzir a tela não afrouxa
            # o que o sistema aceita.
            "• não ser sequência de teclado ou de números (1234, qwerty);\n"
            "• não começar nem terminar com espaço;\n"
            "• não colocar o seu nome de usuário dentro dela;\n"
            "• não usar senha que esteja entre as mais usadas do mundo;\n"
            f"• a barra de força passar de {piso}%;\n"
            f"• e, se ela ficar abaixo, ter no mínimo {minimo} caracteres, "
            f"pelo menos {TIPOS_MINIMOS_ACEITE} tipos de caractere e nunca "
            "ter vazado;\n"
            "• senha que já vazou só é liberada com a barra amarela ou "
            "acima;\n"
            "• em qualquer um desses casos o sistema pede um aceite de "
            "risco, e a tela explica o que isso significa."
        )
    except Exception:
        logger.exception("politica_senha: regras_para_tela falhou")
        return ("A senha precisa ter letras minúsculas e maiúsculas, um "
                "número e um caractere especial.")


# ---------------------------------------------------------------------------
#  Tentativas de login: atraso progressivo, sem travar a conta
# ---------------------------------------------------------------------------
def _config(chave: str, padrao) -> str:
    try:
        from mod_skyrover.bd_conexao import get_config
        return str(get_config(chave, str(padrao)) or padrao)
    except Exception:
        return str(padrao)


def tentativas_maximas() -> int:
    """O limite, sempre entre 3 e 20 — 3 é o piso, por decisão do responsável.

    O piso de 3 não é o valor mais empedido de ataque: é o valor em que a
    pessoa comum erra duas vezes e acerta na terceira, e ainda não cai na
   partisan do "segurança" só no papel.
    """
    try:
        v = int(float(_config(CHAVE_TENTATIVAS, TENTATIVAS_PADRAO)))
    except Exception:
        return TENTATIVAS_PADRAO
    return max(TENTATIVAS_MINIMO, min(TENTATIVAS_MAXIMO, v))


def atraso_maximo_seg() -> float:
    try:
        return max(1.0, min(ATRASO_MAXIMO_SEG,
                            float(_config(CHAVE_ATRASO_MAXIMO,
                                          ATRASO_MAXIMO_SEG))))
    except Exception:
        return ATRASO_MAXIMO_SEG


def calcular_atraso(falhas: int) -> float:
    """Quanto esperar, em segundos, por `falhas` tentativas erradas.

    Linear por rampa, com teto: 0 falhas → 0 s; 1 → 1 s; 2 → 2,5 s; 3 → 4 s;
    e a partir daí sobe até o teto configurado. Sem teto, uma senha muito
    usada seria respondida em minutos — e o atacante não ganha com isso, só
    desacelera de menos.

    O efeito real do limite não é o tempo: é o **custo**. O login responde
    sempre "Usuário ou senha inválidos", sem dizer qual dos dois falhou, e a
    espera cresce a cada erro. Um ataque de dicionário fica caro sem nunca
    fechar a conta de quem só esqueceu a senha.
    """
    try:
        n = max(0, int(falhas))
        if n == 0:
            return 0.0
        bruto = ATRASO_INICIAL_SEG + PASSO_ATRASO_SEG * (n - 1) ** 1.5
        return round(min(bruto, atraso_maximo_seg()), 1)
    except Exception:
        return 0.0


def texto_atraso(seg: float) -> str:
    """O aviso que o login mostra quando vai demorar."""
    try:
        s = float(seg or 0)
    except Exception:
        return ""
    if s < 1:
        return ""
    if s < 60:
        return (f"Muitas tentativas incorretas. Aguarde {int(round(s))} "
                "segundo(s) antes de tentar de novo.")
    m = int(s // 60)
    return (f"Muitas tentativas incorretas. Aguarde {m} minuto(s) antes de "
            "tentar de novo.")


# ---------------------------------------------------------------------------
#  Estado das tentativas (tb_login_tentativas, no banco do módulo usuários)
# ---------------------------------------------------------------------------
def registrar_falha(user_nome: str) -> int:
    """Soma uma falha e devolve o total na janela. Devolve 0 se falhar.

    Falha aqui **não** pode derrubar o login: o registro serve para atrasar e
    auditar, e perder a contagem só faz o atacante ganhar tempo — nunca faz o
    servidor legítimo ser barrado.
    """
    try:
        from mod_skyrover import autenticacao
        gest = autenticacao._gest()
        if gest is None:
            return 0
        return int(gest.registrar_tentativa_login(user_nome) or 0)
    except Exception:
        logger.exception("politica_senha: não foi possível registrar a falha "
                         "de login; seguindo sem contagem")
        return 0


def zerar_tentativas(user_nome: str) -> bool:
    """Login certo zera a contagem da janela."""
    try:
        from mod_skyrover import autenticacao
        gest = autenticacao._gest()
        if gest is None:
            return False
        return bool(gest.zerar_tentativas_login(user_nome))
    except Exception:
        logger.exception("politica_senha: não foi possível zerar as "
                         "tentativas de login")
        return False


def tentativas_de(user_nome: str) -> int:
    """Quantas falhas há na janela agora."""
    try:
        from mod_skyrover import autenticacao
        gest = autenticacao._gest()
        if gest is None:
            return 0
        return int(gest.tentativas_login(user_nome) or 0)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
#  O texto do aceite — LGPD
# ---------------------------------------------------------------------------
# Escrito para o SERVIDOR ler, não para o jurídico. A lei aparece pelo que ela
# de fato estabelece, e — tão importante quanto isso — pelo que ela NÃO
# estabelece. Um texto de aceite que só cita artigo para assustar é propaganda,
# não informação, e a prefeitura não pode fazer isso com servidor público.
TEXTO_ACEITE_RISCO_EN = """\
By checking the box, you take responsibility for this access and for its use.

You are aware that:

1. The chosen password appears in known public breaches and can be guessed by
   attack. With it, whoever obtains it can read, change and delete what is
   under your profile — including other people's data.

2. The municipality is the DATA CONTROLLER of the personal data handled here
   and adopts security measures to protect it. This follows Brazilian Law
   13.709/2018 (LGPD), in particular Art. 6º, VI and VII (security and
   prevention) and Art. 46, which requires technical and administrative
   measures against unauthorized access.

3. The CO-RESPONSIBILITY is yours. The law does not transfer to the system the
   task of guessing your password: choosing an easy password is your own act,
   and the consequences for your profile are yours.

4. If your account is breached through a weak or leaked password, improper use
   will be attributed to your profile — not to the municipality, which
   advises and offers a password change at any time.

5. You may change this password whenever you want, at any time, without
   justification."""

# O que a PESSOA lê na tela. Só PT-BR: mostrar os dois idiomas empilhados
# duplicava o texto na tela e empurrava o botão para fora de vista — e o texto
# em inglês não ia fazer sentido para servidor de prefeitura nenhuma.
#
# O termo é montado de PARTES (18/10/2026) porque ele tem duas variantes: a
# pessoa cuja senha VAZOU lê cinco itens, e a pessoa que só escolheu uma senha
# fraca — faixa amarela ou atalho da barra vermelha — lê quatro, porque o item
# do vazamento seria mentira para ela (a consulta respondeu "não encontrada",
# logo em cima, em verde). Ver `texto_aceite`.
ACEITE_INTRODUCAO = """\
Ao marcar a caixa, você assume a responsabilidade por este acesso e pelo uso
que for feito com ele.

Você está ciente de que:"""

# (vazamento, controladora, co-responsabilidade, invasão, troca) — a ordem é a
# do documento; quem monta é `texto_aceite`, que numera e tira o que não cabe.
ACEITE_ITENS = (
    """A senha escolhida aparece em vazamentos públicos conhecidos e pode ser \
deduzida por ataque. Com ela, quem a obtiver pode ler, alterar e apagar o \
que está sob o seu perfil — inclusive dados de outros servidores.""",
    """A prefeitura é a CONTROLADORA dos dados pessoais aqui tratados e adota \
medidas de segurança para protegê-los. Isso decorre da Lei nº 13.709/2018 \
(LGPD), em especial do Art. 6º, VI e VII (segurança e prevenção) e do \
Art. 46, que exige medidas técnicas e administrativas contra acessos não \
autorizados.""",
    """A CO-RESPONSABILIDADE é sua. A lei não transfere ao sistema a tarefa de \
adivinhar a sua senha: escolher senha fácil é ato seu, e as consequências \
sobre o seu perfil são suas.""",
    """Se a sua conta for invadida por senha fraca ou vazada, o uso indevido \
será atribuído ao seu perfil — e não à prefeitura, que orienta e oferece \
troca de senha a qualquer momento.""",
    """Você pode trocar esta senha quando quiser, em qualquer momento, sem \
justificar.""",
)

# O índice do item que é sobre VAZAMENTO — o único que sai quando a senha não
# apareceu em vazamento nenhum. Os outros quatro (controladora, co-
# responsabilidade, invasão e troca) continuam, porque continuam valendo.
ACEITE_ITEM_VAZAMENTO = 0


def texto_aceite(vazou: bool = True) -> str:
    """O termo de responsabilidade, numerado para o que ele descreve.

    EN: The liability term, numbered for what it actually describes.

    PT-BR: O termo inteiro, com os itens certos para o caso da pessoa. Quando a
    senha NÃO apareceu em vazamento nenhum, o item do vazamento sai e os outros
    quatro são RENUMERADOS (18/10/2026, pedido do responsável: "se a senha não
    tiver sido exposta, reordenar os números e não mostrar a parte do texto que
    a senha já foi vazada").

    Renumerar não é vaidade: um item que começa em 2 e vai a 5 com o 1 faltando
    parece ter perdido um parágrafo no meio — e esse parágrafo era justamente o
    que a pessoa não tem o que assinar.

    O texto corrido continua existindo em `TEXTO_ACEITE_RISCO` (com o
    vazamento incluído) porque é ele que a documentação e os testes citam, e é a
    variante mais longa.
    """
    try:
        itens = list(ACEITE_ITENS)
        if not vazou:
            itens.pop(ACEITE_ITEM_VAZAMENTO)
        numerados = "\n\n".join(
            f"{i}. {texto}" for i, texto in enumerate(itens, start=1))
        return f"{ACEITE_INTRODUCAO}\n\n{numerados}"
    except Exception:
        logger.exception("politica_senha: texto_aceite falhou")
        return ACEITE_INTRODUCAO


TEXTO_ACEITE_RISCO = texto_aceite(vazou=True)
