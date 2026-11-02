"""Phone helpers: DDI select + BR formatting (single standard).
EN: Canonical phone storage, BR display mask and a DDI+number field with country tooltip.
PT-BR: Armazenamento canônico, máscara BR de exibição e campo DDI+número com
tooltip do país. Todo telefone do sistema usa este módulo (cadastro de
usuário, meu perfil, troca de credenciais do master e lista telefônica).
"""
import re

try:
    _REGEX_BR = re.compile(
        r"^(?:\+?55\s?)?(?:\(?[1-9]{2}\)?\s?)?"
        r"(?:((?:9\d|[2-9])\d{3})[\s-]?(\d{4}))$"
    )
except Exception:
    _REGEX_BR = None

DDI_PADRAO = "+55"

# DDI -> país (E.164). Lista completa para o combobox; o rótulo exibido é
# "+DDI — País", de modo que o hover sobre a opção já mostra o país.
DDI_PAISES = {
    "+93": "Afeganistão", "+355": "Albânia", "+213": "Argélia",
    "+1684": "Samoa Americana", "+376": "Andorra", "+244": "Angola",
    "+1264": "Anguilla", "+672": "Antártida", "+1268": "Antígua e Barbuda",
    "+54": "Argentina", "+374": "Armênia", "+297": "Aruba",
    "+61": "Austrália", "+43": "Áustria", "+994": "Azerbaijão",
    "+1242": "Bahamas", "+973": "Bahrein", "+880": "Bangladesh",
    "+1246": "Barbados", "+375": "Bielorrússia", "+32": "Bélgica",
    "+501": "Belize", "+229": "Benim", "+1441": "Bermudas",
    "+975": "Butão", "+591": "Bolívia", "+387": "Bósnia e Herzegovina",
    "+267": "Botsuana", "+55": "Brasil", "+673": "Brunei",
    "+359": "Bulgária", "+226": "Burkina Faso", "+257": "Burundi",
    "+855": "Camboja", "+237": "Camarões", "+1": "EUA/Canadá/Caribe",
    "+238": "Cabo Verde", "+1345": "Ilhas Cayman",
    "+236": "República Centro-Africana", "+235": "Chade", "+56": "Chile",
    "+86": "China", "+57": "Colômbia", "+269": "Comores",
    "+242": "Congo", "+243": "Congo (RDC)", "+682": "Ilhas Cook",
    "+506": "Costa Rica", "+225": "Costa do Marfim", "+385": "Croácia",
    "+53": "Cuba", "+357": "Chipre", "+420": "Tchéquia",
    "+45": "Dinamarca", "+253": "Djibuti", "+1767": "Dominica",
    "+1809": "Rep. Dominicana", "+1829": "Rep. Dominicana",
    "+1849": "Rep. Dominicana", "+593": "Equador", "+20": "Egito",
    "+503": "El Salvador", "+240": "Guiné Equatorial", "+291": "Eritreia",
    "+372": "Estônia", "+251": "Etiópia", "+500": "Ilhas Malvinas",
    "+298": "Ilhas Faroe", "+679": "Fiji", "+358": "Finlândia",
    "+33": "França", "+594": "Guiana Francesa", "+241": "Gabão",
    "+220": "Gâmbia", "+995": "Geórgia", "+49": "Alemanha",
    "+233": "Gana", "+350": "Gibraltar", "+30": "Grécia",
    "+299": "Groenlândia", "+1473": "Granada", "+590": "Guadalupe",
    "+1671": "Guam", "+502": "Guatemala", "+224": "Guiné",
    "+245": "Guiné-Bissau", "+592": "Guiana", "+509": "Haiti",
    "+504": "Honduras", "+852": "Hong Kong", "+36": "Hungria",
    "+354": "Islândia", "+91": "Índia", "+62": "Indonésia",
    "+98": "Irã", "+964": "Iraque", "+353": "Irlanda",
    "+972": "Israel", "+39": "Itália", "+1876": "Jamaica",
    "+81": "Japão", "+962": "Jordânia", "+7": "Rússia/Cazaquistão",
    "+254": "Quênia", "+686": "Kiribati", "+850": "Coreia do Norte",
    "+82": "Coreia do Sul", "+965": "Kuwait", "+996": "Quirguistão",
    "+856": "Laos", "+371": "Letônia", "+961": "Líbano",
    "+266": "Lesoto", "+231": "Libéria", "+218": "Líbia",
    "+423": "Liechtenstein", "+370": "Lituânia", "+352": "Luxemburgo",
    "+853": "Macau", "+389": "Macedônia do Norte", "+261": "Madagascar",
    "+265": "Malawi", "+60": "Malásia", "+960": "Maldivas",
    "+223": "Mali", "+356": "Malta", "+692": "Ilhas Marshall",
    "+596": "Martinica", "+222": "Mauritânia", "+230": "Maurício",
    "+52": "México", "+691": "Micronésia", "+373": "Moldávia",
    "+377": "Mônaco", "+976": "Mongólia", "+382": "Montenegro",
    "+1664": "Montserrat", "+212": "Marrocos", "+258": "Moçambique",
    "+95": "Mianmar", "+264": "Namíbia", "+674": "Nauru",
    "+977": "Nepal", "+31": "Holanda", "+687": "Nova Caledônia",
    "+64": "Nova Zelândia", "+505": "Nicarágua", "+227": "Níger",
    "+234": "Nigéria", "+683": "Niue", "+672": "Ilha Norfolk",
    "+1670": "Ilhas Marianas", "+47": "Noruega", "+968": "Omã",
    "+92": "Paquistão", "+680": "Palau", "+970": "Palestina",
    "+507": "Panamá", "+675": "Papua-Nova Guiné", "+595": "Paraguai",
    "+51": "Peru", "+63": "Filipinas", "+48": "Polônia",
    "+351": "Portugal", "+1787": "Porto Rico", "+1939": "Porto Rico",
    "+974": "Catar", "+262": "Reunião", "+40": "Romênia",
    "+250": "Ruanda", "+590": "São Bartolomeu", "+290": "Santa Helena",
    "+1869": "São Cristóvão e Nevis", "+1758": "Santa Lúcia",
    "+590": "São Martinho", "+508": "São Pedro e Miquelon",
    "+1784": "São Vicente e Granadinas", "+685": "Samoa",
    "+378": "San Marino", "+239": "São Tomé e Príncipe",
    "+966": "Arábia Saudita", "+221": "Senegal", "+381": "Sérvia",
    "+248": "Seicheles", "+232": "Serra Leoa", "+65": "Singapura",
    "+421": "Eslováquia", "+386": "Eslovênia", "+677": "Ilhas Salomão",
    "+252": "Somália", "+27": "África do Sul", "+34": "Espanha",
    "+94": "Sri Lanka", "+249": "Sudão", "+597": "Suriname",
    "+268": "Essuatíni", "+46": "Suécia", "+41": "Suíça",
    "+963": "Síria", "+886": "Taiwan", "+992": "Tajiquistão",
    "+255": "Tanzânia", "+66": "Tailândia", "+670": "Timor-Leste",
    "+228": "Togo", "+690": "Tokelau", "+676": "Tonga",
    "+1868": "Trinidad e Tobago", "+216": "Tunísia", "+90": "Turquia",
    "+993": "Turcomenistão", "+1649": "Turks e Caicos", "+688": "Tuvalu",
    "+256": "Uganda", "+380": "Ucrânia", "+971": "Emirados Árabes",
    "+44": "Reino Unido", "+598": "Uruguai", "+998": "Uzbequistão",
    "+678": "Vanuatu", "+58": "Venezuela", "+84": "Vietnã",
    "+1284": "Ilhas Virgens (GB)", "+1340": "Ilhas Virgens (EUA)",
    "+681": "Wallis e Futuna", "+967": "Iêmen", "+260": "Zâmbia",
    "+263": "Zimbábue",
}


def listar_ddis():
    """EN: Sorted DDI list with default (+55) first. PT-BR: Lista de DDIs com +55 primeiro."""
    try:
        todos = sorted(DDI_PAISES.keys(), key=lambda d: (d != DDI_PADRAO, d))
        return todos
    except Exception:
        return [DDI_PADRAO]


def nome_pais(ddi):
    """EN: Country name for a DDI. PT-BR: Nome do país do DDI."""
    try:
        return DDI_PAISES.get((ddi or "").strip(), "")
    except Exception:
        return ""


# Largura de caixa MINIMA do campo DDI (medido por SCREENSHOT em 05/10/2026 —
# ver o bloco de `criar_campo_telefone`).
#
# POR QUE ISTO EXISTE E NÃO SÓ UM NÚMERO NO CHAMADOR: um campo mais estreito
# que o texto que ele mostra é um campo CORTADO, e o corte é invisível para a
# métrica — o QSelect usa `text-overflow: clip` e o navegador NÃO reporta
# transbordo nesse caso. Medido: a 112px o `scrollWidth` dizia "não corta" e a
# imagem da tela mostrava "+55 - Bra:". Sem este piso, quem passar um
# `largura_ddi` curto solta o campo cortado e só descobre na tela.
#
# POR QUE 140px E NÃO O "~140px" QUE ESTAVA NO COMENTÁRIO ANTES: 140px é o
# menor valor em que "+55 - Brasil" aparece INTEIRO, medido por screenshot.
# O `label` ("DDI") e o valor dividem a mesma faixa, então um deles cortando
# já é defeito.
LARGURA_MINIMA_DDI = 140

# Alternativa medida e REJEITADA em 05/10/2026: encurtar o rótulo para `+55`.
# Ela caberia a partir de 88px de caixa e daria 223px ao número, em vez de
# 171px — mas o nome do país sairia do campo (só restaria no `tooltip`) e,
# pior, SAIRIA DA LISTA: as opções virariam "+55", "+49", "+1", e escolher um
# DDI passaria a exigir saber o número de chamada do país. Esse é justamente o
# serviço que a lista existe para prestar. Com o cartão no padrão de 680px e o
# padding lateral em 12px, a coluna do `master` sai com 319px (medido) e o
# rótulo inteiro cabe — não há troca a fazer.


def _px_de_classe(classe: str):
    """EN: px inside a Tailwind `w-[Npx]` class. PT-BR: os px de `w-[Npx]`."""
    import re as _re
    try:
        achado = _re.search(r"w-\[(\d+)px\]", str(classe or ""))
        return int(achado.group(1)) if achado else None
    except Exception:
        return None


def _garantir_piso_ddi(sel, largura_chamada: str) -> None:
    """Garante que a caixa do DDI tem a largura MÍNIMA do rótulo que ela mostra.

    EN: Enforces the DDI box minimum width for its label.

    PT-BR: Um campo mais estreito que o texto que ele mostra é um campo
    cortado — e o corte é INVISÍVEL para a métrica, porque o QSelect usa
    `text-overflow: clip` (medido em 05/10/2026: a 112px o `scrollWidth` dizia
    "não corta" e a tela mostrava "+55 - Bra:"). Por isso o piso vale por
    cima do que o chamador pediu.

    O `largura_ddi` é uma CLASSE (`w-[140px]`), então o piso é escrito no
    `style` — e o `style` vence a classe, porque o Quasar escreve o dele
    depois. A classe continua lá, para o texto continuar legível no devtools.

    Fail-soft: se não der para ler a classe, o campo fica como o chamador
    pediu. Perde-se o piso, nunca o campo.
    """
    try:
        pedido = _px_de_classe(largura_chamada)
        if pedido is None or pedido >= LARGURA_MINIMA_DDI:
            return
        sel.style(f"width: {LARGURA_MINIMA_DDI}px; "
                  f"flex: 0 0 {LARGURA_MINIMA_DDI}px; "
                  f"max-width: {LARGURA_MINIMA_DDI}px")
    except Exception as e:
        try:
            from mod_skyrover import observabilidade
            observabilidade.get_logger("skyrover").warning(
                f"telefone: piso do DDI não aplicado ({e})")
        except Exception:
            pass


def opcoes_ddi():
    """EN: Select options '+DDI — Country'. PT-BR: Opções '+DDI — País' (hover mostra o país)."""
    try:
        opcoes = {}
        for ddi in listar_ddis():
            opcoes[ddi] = f"{ddi} - {DDI_PAISES.get(ddi, '')}".strip()
        return opcoes
    except Exception:
        return {DDI_PADRAO: f"{DDI_PADRAO} - Brasil"}


def apenas_digitos(texto):
    """EN: Only digits. PT-BR: Só dígitos."""
    try:
        import re as _re
        return _re.sub(r"\D", "", texto or "")
    except Exception:
        return ""


def obter_ddi(telefone):
    """EN: Detects stored DDI or default +55. PT-BR: Detecta o DDI gravado ou usa +55."""
    try:
        txt = (telefone or "").strip()
        if not txt:
            return DDI_PADRAO
        if txt.startswith("+"):
            dig = apenas_digitos(txt)
            for ddi in sorted(DDI_PAISES.keys(), key=len, reverse=True):
                if dig.startswith(ddi.replace("+", "")):
                    return ddi
            return DDI_PADRAO
        dig = apenas_digitos(txt)
        if len(dig) > 11:
            for ddi in sorted(DDI_PAISES.keys(), key=len, reverse=True):
                if ddi in ("+1", "+7"):
                    continue
                if dig.startswith(ddi.replace("+", "")):
                    return ddi
        return DDI_PADRAO
    except Exception:
        return DDI_PADRAO


def obter_numero_nacional(telefone):
    """EN: National number without DDI. PT-BR: Número nacional sem o DDI."""
    try:
        txt = (telefone or "").strip()
        if not txt:
            return ""
        ddi = obter_ddi(txt)
        dig = apenas_digitos(txt)
        prefixo = ddi.replace("+", "")
        if dig.startswith(prefixo) and len(dig) > len(prefixo):
            resto = dig[len(prefixo):]
            # evita comer DDD nacional quando DDI=default e número já é nacional
            if ddi == DDI_PADRAO and len(dig) in (10, 11):
                return dig
            return resto
        return dig
    except Exception:
        return apenas_digitos(telefone)


def normalizar_telefone(ddi, numero):
    """EN: Canonical '+DDIdigits'. PT-BR: Canônico '+DDIdígitos' (+55 automático)."""
    try:
        ddi = (ddi or "").strip() or DDI_PADRAO
        if not ddi.startswith("+"):
            ddi = "+" + ddi
        dig = apenas_digitos(numero)
        if not dig:
            return ""
        prefixo = ddi.replace("+", "")
        if dig.startswith(prefixo) and len(dig) > 11:
            return "+" + dig
        return ddi + dig
    except Exception:
        return ""


def validar_br(telefone):
    """EN: BR validation with project regex. PT-BR: Validação BR com o regex do projeto."""
    try:
        txt = (telefone or "").strip()
        if not txt:
            return False
        if _REGEX_BR is None:
            return len(apenas_digitos(txt)) in (10, 11)
        return bool(_REGEX_BR.match(txt))
    except Exception:
        return False


def formatar_br(nacional):
    """EN: '(DD) 9 XXXX-XXXX'. PT-BR: '(DDD) 9 XXXX-XXXX' ou '(DDD) XXXX-XXXX'.

    Padrão pedido pelo responsável (16/10/2026): no celular o nono dígito
    vai ISOLADO — `(35) 9 8818-3288`, e com DDI `+55 (35) 9 8818-3288`.
    No fixo o bloco é único — `(00) 3591-5100`."""
    try:
        dig = apenas_digitos(nacional)
        if len(dig) == 11:
            return f"({dig[:2]}) 9 {dig[3:7]}-{dig[7:]}"
        if len(dig) == 10:
            return f"({dig[:2]}) {dig[2:6]}-{dig[6:]}"
        return (nacional or "").strip()
    except Exception:
        return (nacional or "").strip()


def formatar_para_exibicao(telefone):
    """EN: '+55 (DD) 9 XXXX-XXXX' for BR, '+DDI number' otherwise.
    PT-BR: '+55 (DDD) 9 XXXX-XXXX' para BR, '+DDI número' para o resto."""
    try:
        txt = (telefone or "").strip()
        if not txt:
            return ""
        ddi = obter_ddi(txt)
        nacional = obter_numero_nacional(txt)
        if ddi == DDI_PADRAO and len(apenas_digitos(nacional)) in (10, 11):
            return f"{DDI_PADRAO} {formatar_br(nacional)}"
        if nacional:
            return f"{ddi} {nacional}".strip()
        return txt
    except Exception:
        return (telefone or "").strip()


def _aplicar_mascara_apos_montagem(inp, mascara):
    """Aplica `mask`/`unmask`/`emit-value` no input, já montado na tela.

    Resolve a recusa do `.props()` (ver o comentario em `criar_campo_telefone`).

    `on("mount", js_handler=...)` é o que funciona nesta versão do NiceGUI
    (3.15): o handler roda no navegador no instante em que o elemento entra no
    DOM — que é quando o `q-input` do Quasar já montado e passa a observar
    os atributos. `add_body_html` não serve: ele roda uma vez, no carregamento
    da página, e o diálogo é criado depois disso.

    O JS recebe a máscara por `args` (serializado pelo NiceGUI) em vez de ser
    interpolado no texto: evita o emaranhado de aspas entre `f-string` e
    JavaScript, que só daria erro em runtime, na tela do usuário.

    Falha aqui é fail-soft: o campo continua lendo e gravando número. Perde-se
    a conveniência da máscara, nunca o dado.
    """
    try:
        import json
        inp.on("mount", args=[json.dumps(mascara)], js_handler=(
            "(m) => {{"
            " const el = document.getElementById(this.getAttribute('id'));"
            " if (!el) return;"
            " el.setAttribute('mask', m);"
            " el.setAttribute('unmask', 'true');"
            " el.setAttribute('emit-value', 'true');"
            " }}"))
    except Exception as e:
        try:
            from mod_skyrover import observabilidade
            observabilidade.get_logger("skyrover").warning(
                f"telefone: máscara não aplicada ({e})")
        except Exception:
            pass



def criar_campo_telefone(rotulo="Telefone", valor="", ddi_inicial=None,
                         # Placeholder com `#`: o Quasar usa o texto de exemplo do input como padrão da
# máscara quando há `mask`, e o próprio padrão do `mask` é este. Com os `9`s
# hardcoded o exemplo ficava ambíguo (o 9 é dígito válido ou só exemplo?).
placeholder="(##) #####-####", largura_numero="flex-1",
                         largura_ddi="w-[190px]", empilhado=False,
                         testid_ddi=None, testid_numero=None,
                         classes_linha=None):
    """EN: DDI select + number input with country tooltip; returns dict with getter.
    PT-BR: Linha DDI (combobox com todos os países, hover mostra o país) +
    número; DDI padrão +55 automático; retorna dict com `obter()` canônico.

    O RÓTULO é `+55 - Brasil`, com o nome do país, e a LISTA também. Encurtar
    para `+55` foi medido em 05/10/2026 e REJEITADO: cabe a partir de 88px de
    caixa em vez de 140px, mas o país some do campo (restaria só no `tooltip`)
    e some da LISTA — e escolher um DDI por uma coluna de "+55", "+49", "+1"
    passa a exigir saber o número de chamada do país, que é o serviço que a
    lista existe para prestar. Com o cartão no padrão de 680px (padding lateral
    de 12px) a coluna do `master` sai com 319px, e o rótulo inteiro cabe com
    171px sobrando para o número.

    `largura_ddi` tem um PISO (`LARGURA_MINIMA_DDI`, 140px), aplicado por
    `_garantir_piso_ddi`: um campo mais estreito que o próprio texto é um
    campo cortado, e o corte é invisível para a métrica — o QSelect usa
    `text-overflow: clip` e o navegador não reporta transbordo nesse caso
    (medido: a 112px o `scrollWidth` dizia "não corta" e a tela mostrava
    "+55 - Bra:"). Quem pedir menos que o piso não solta campo cortado.

    `classes_linha` troca as classes da fileira do composto (padrão
    `"w-full gap-2"`): serve para o composto participar como ITEM flex de
    uma fileira externa — ex. `"flex-1 min-w-0 gap-2 flex-nowrap
    items-start"` na linha de adicionar do admin, onde o `w-full` interno
    brigava com os selects vizinhos e espremia o número.
    """
    try:
        from nicegui import ui
    except Exception:
        return None
    try:
        ddi_atual = (ddi_inicial or "").strip() or obter_ddi(valor) or DDI_PADRAO
        nacional_atual = obter_numero_nacional(valor)
        # `classes_linha` (15/10/2026): troca as classes da fileira do
        # composto — serve para ele participar como ITEM flex de uma
        # fileira externa. Sem ele, vale o padrão abaixo.
        _classes_linha = classes_linha or "w-full gap-2"
        _classes_alinho = ""
        if not classes_linha:
            # Empilhado, os filhos precisam ESTICAR na largura —
            # `items-start` é `align-items: flex-start`, que deixaria o
            # campo do número com a largura do seu texto (medido: 186px
            # contra 279px dos outros campos da coluna). Na linha, o alvo
            # é o topo, que é o que `items-start` faz, e é o comportamento
            # antigo.
            _classes_alinho = ("items-stretch" if empilhado
                               else "flex-nowrap items-start")
        with (ui.column() if empilhado else ui.row()).classes(
                _classes_linha).classes(_classes_alinho):
            # `min-w-0` (02/10/2026): o DDI tem largura-ALVO de 190px, mas como
            # item de uma linha `flex-nowrap` vinha com `min-width: auto` e não
            # encolhia abaixo do próprio min-content. Numa célula estreita da
            # grade de campos, isso empurrava o campo do número para fora do
            # diálogo (com barra de rolagem horizontal). Encolher é melhor que
            # estourar — e o alvo de 190px continua valendo no espaço normal.
            #
            # `largura_ddi` (04/10/2026): o 190px é o alvo para uma célula de
            # ~300px, que é o que a grade de diálogo dá. Na tela de credenciais
            # do `master` a célula é uma COLUNA de 319px (medido em 05/10/2026,
            # depois do cartão ir a 680px com padding lateral de 12px), e 190px
            # deixavam 121px para o número. Quem chama passa a largura certa
            # para o espaço que tem; o padrão não muda para mais ninguém. E
            # `_garantir_piso_ddi` impede que a largura passe de 140px para
            # baixo, que é onde o "+55 - Brasil" começa a ser cortado.
            #
            # `empilhado=True` põe o DDI e o número em LINHAS separadas, cada
            # um com a largura inteira do contêiner. Resolve a coluna estreita
            # de quem não tem 319px: lado a lado, o DDI com o nome do país à
            # mostra precisa de 140px de caixa e o número precisa de ~112px
            # para o placeholder — 260px, mais que uma coluna de 240px.
            # Empilhando, cada um tem a largura inteira e os DOIS cabem inteiros.
            #
            # A LISTA sempre com o país (`opcoes_ddi()`), e o rótulo do campo
            # também. Ver o `LARGURA_MINIMA_DDI` acima: encurtar para `+55`
            # foi medido e REJEITADO — a lista viraria uma coluna de números
            # sem nome.
            sel = ui.select(opcoes_ddi(), label="DDI", value=ddi_atual,
                            with_input=True).props("outlined dense").classes(
                f"{largura_ddi} min-w-0")
            _garantir_piso_ddi(sel, largura_ddi)
            if testid_ddi:
                try:
                    sel.props(f"data-testid={testid_ddi}")
                except Exception:
                    pass
            # Máscara BR (02/10/2026): o padrão pedido pelo responsável foi
            # `(xx) 9-9999-9999` — celular com nono dígito. O `#` é o
            # placeholder da máscara do Quasar (aparece só no texto de
            # exemplo) e `unmask` devolve só dígitos, que é o que
            # `normalizar_telefone` quer — quem grava não precisa limpar
            # pontuação. `emit-value` mantém o `value` do input sincronizado
            # com o texto visível; sem ele a máscara aparece mas o valor segue
            # cru, e o `obter()` devolveria lixo.
            # 11 `#` = DDD + 9 dígitos (máximo nacional). A forma anterior
            # (`#(##) #####-####`, 12 `#`) nunca enchia com 11 dígitos, e o
            # número digitado não virava linha gravada (16/10/2026).
            mascara = "(##) #####-####"
            inp = ui.input(rotulo, value=nacional_atual,
                           placeholder=placeholder).props(
                "outlined dense").classes(
                f"{largura_numero} min-w-0")
            # Máscara do Quasar (02/10/2026). O `#` é o placeholder do padrão.
            #
            # POR QUE ISTO NÃO VAI EM `.props()`: medido no browser, escrever
            # `mask=(##) #####-####` em `.props()` não emitia o atributo —
            # enquanto `unmask` e `emit-value`, na MESMA chamada, emitiam. A
            # diferença é o valor com `#`, que o parser de props do NiceGUI
            # trata como início de seletor de id. E `setattr` direto também
            # não sobrevive: o NiceGUI reescreve as props do input ao montar e
            # ao atualizar o componente.
            #
            # O caminho que resta é o `ui.add_body_html` doNiceGUI 3.15, que
            # injeta JS após a montagem, quando o elemento já existe e o
            # NiceGUI não reescreve mais nada naquele passo. Falhou aqui, o
            # campo continua lendo e gravando número — perde-se a Convenience
            # da máscara, nunca o dado.
            _aplicar_mascara_apos_montagem(inp, mascara)

            def _atualizar_tooltip(e=None):
                try:
                    ddi_sel = (sel.value or "").strip() or DDI_PADRAO
                    pais = nome_pais(ddi_sel) or ""
                    sel.tooltip(f"{ddi_sel} - {pais}".strip(" -"))
                except Exception:
                    pass

            try:
                sel.tooltip(f"{ddi_atual} - {nome_pais(ddi_atual)}".strip(" -"))
                sel.on_value_change(_atualizar_tooltip)
            except Exception:
                pass
            if testid_numero:
                try:
                    inp.props(f"data-testid={testid_numero}")
                except Exception:
                    pass

        def _obter():
            try:
                return normalizar_telefone(sel.value, inp.value)
            except Exception:
                return ""

        def _definir(novo_valor):
            try:
                sel.value = obter_ddi(novo_valor)
                inp.value = obter_numero_nacional(novo_valor)
                _atualizar_tooltip()
            except Exception:
                pass

        return {"ddi": sel, "numero": inp, "obter": _obter, "definir": _definir}
    except Exception:
        return None
