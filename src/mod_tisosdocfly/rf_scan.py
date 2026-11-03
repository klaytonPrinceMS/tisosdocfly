"""Wi-Fi/RF scan parsers and sanitizer (pure Python standard library).

Parsers e sanitizador de varredura Wi-Fi/RF em Python puro (só stdlib).

Este módulo lê a saída de ferramentas comuns de varredura e converte tudo para
um dicionário canônico, sem guardar o BSSID cru:

- `parse_csv`  — CSV/TSV com cabeçalho (ssid, bssid, banda, canal, rssi,
  seguranca, latitude, longitude);
- `parse_json` — lista JSON ou objeto com `redes`/`networks`/`registros`;
- `parse_nmcli` — `nmcli -t -f SSID,BSSID,SIGNAL,SECURITY dev wifi list`;
- `parse_iw`   — `iw dev <iface> scan`.

Privacidade: `normalizar_registro` troca o BSSID por SHA-256 e devolve somente
`bssid_hash`. Nenhuma função de exportação (CLI/JSON) reemite o MAC original.

A varredura ao vivo (`escanear_ao_vivo`) é opcional, passiva e fail-soft:
usa `nmcli` (sem root) quando existe e `iw` (normalmente exige root) como
alternativa; sem ferramenta, permissão ou rede, devolve lista vazia. Só deve
ser usada com autorização do responsável pelo ambiente.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

CAMPOS = ("ssid", "bssid", "banda", "canal", "rssi", "seguranca",
          "latitude", "longitude")
SEGURANCAS = ("aberta", "wep", "wpa2", "wpa3", "desconhecida")
RISCOS = ("baixo", "medio", "alto", "critico")
_ORDEM_RISCO = {"baixo": 0, "medio": 1, "alto": 2, "critico": 3}
_RISCO_INVERSO = {v: k for k, v in _ORDEM_RISCO.items()}

# Sinal considerado "forte" para fins de vazamento: -70 dBm é o limite usual
# em que uma rede ainda é utilizável a dezenas de metros do ponto de acesso.
RSSI_FORTE = -70

# Apelidos aceitos nos arquivos de entrada (PT-BR e EN).
_ALIASES = {
    "ssid": ("ssid", "rede", "nome_rede", "network", "essid"),
    "bssid": ("bssid", "mac", "mac_address", "endereco_mac", "bss"),
    "banda": ("banda", "band", "frequency_band"),
    "canal": ("canal", "channel", "ch"),
    "rssi": ("rssi", "sinal", "signal", "potencia", "dbm"),
    "seguranca": ("seguranca", "security", "auth", "autenticacao",
                  "criptografia"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "lng", "long"),
    "freq": ("freq", "frequencia", "frequency"),
}

_MAC_RE = re.compile(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}")
_HEX_PAR = re.compile(r"^[0-9A-Fa-f]{2}$")


def _texto(valor):
    """Converte um valor arbitrário para texto limpo (nunca None)."""
    if valor is None:
        return ""
    return str(valor).strip()


def _float(valor, padrao=0.0):
    """Converte para float aceitando vírgula decimal; devolve o padrão."""
    if valor is None or valor == "":
        return padrao
    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return padrao


def _int(valor, padrao=0):
    """Converte para inteiro; devolve o padrão em qualquer falha."""
    try:
        return int(float(str(valor).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return padrao


def _booleano(valor):
    """Interpreta 1/true/sim/yes/fora como verdadeiro."""
    if isinstance(valor, bool):
        return valor
    return _texto(valor).lower() in ("1", "true", "sim", "yes", "s", "fora")


def _pegar(dicionario, campo, padrao=""):
    """Busca um campo por apelido, ignorando maiúsculas e acentos de caixa."""
    for nome in _ALIASES.get(campo, (campo,)):
        for chave, valor in (dicionario or {}).items():
            if _texto(chave).lower() == nome:
                return valor
    return padrao


def normalizar_seguranca(valor):
    """Normaliza a segurança declarada para o vocabulário do módulo.

    EN: Normalizes security labels to aberta/wep/wpa2/wpa3/desconhecida.

    PT-BR: Indicadores como `--`, vazio e `none` são rede **aberta**. `WPA3`
    ou `SAE` viram `wpa3`; `WPA2` (inclusive `WPA1 WPA2`) vira `wpa2`; `WEP`
    vira `wep`. `WPA` isolado (WPA1) não tem slot próprio e vira
    `desconhecida`, para não superestimar a proteção.
    """
    s = _texto(valor).lower()
    if not s or s in ("--", "none", "open", "aberta", "aberto", "ess", "n/a"):
        return "aberta"
    if "wpa3" in s or "sae" in s:
        return "wpa3"
    if "wep" in s:
        return "wep"
    if "wpa2" in s or "rsn" in s:
        return "wpa2"
    return "desconhecida"


def normalizar_bssid(bssid):
    """Canonicaliza o BSSID em `aa:bb:cc:dd:ee:ff` (vazio se inválido)."""
    bruto = _texto(bssid).lower()
    hexa = re.sub(r"[^0-9a-f]", "", bruto)
    if len(hexa) != 12:
        return ""
    return ":".join(hexa[i:i + 2] for i in range(0, 12, 2))


def hash_bssid(bssid):
    """SHA-256 hex do BSSID canônico (string vazia para BSSID inválido).

    EN: Returns the SHA-256 hex digest of the canonical BSSID.

    O hash é determinístico: permite comparar a mesma rede entre auditorias
    sem guardar o endereço MAC. É pseudonimização local, não anonimização
    irreversível — o espaço de MACs é pequeno e um atacante com candidatos
    pode testá-los. Sirva-se dele para não expor o identificador no banco,
    nos laudos e na UI.
    """
    canonico = normalizar_bssid(bssid)
    if not canonico:
        return ""
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def banda_por_frequencia(freq):
    """Classifica a frequência (MHz) em 2.4GHz, 5GHz, 6GHz ou desconhecida."""
    f = _float(freq, 0.0)
    if 2400 <= f <= 2500:
        return "2.4GHz"
    if 4900 <= f <= 5925:
        return "5GHz"
    if 5925 < f <= 7125:
        return "6GHz"
    return "desconhecida"


def canal_por_frequencia(freq):
    """Deriva o canal aproximado a partir da frequência (0 se desconhecido).

    EN: Approximate channel from frequency in MHz.

    Fórmulas usuais: 2,4 GHz `(f-2407)/5`; 5 GHz `(f-5000)/5`; 6 GHz
    `(f-5950)/5`. São aproximações para triagem, não substituem o canal
    reportado pelo adaptador.
    """
    f = _float(freq, 0.0)
    if 2412 <= f <= 2472:
        return int(round((f - 2407) / 5))
    if f == 2484:
        return 14
    if 5000 <= f <= 5895:
        return int(round((f - 5000) / 5))
    if 5955 <= f <= 7115:
        return int(round((f - 5950) / 5))
    return 0


def banda_por_canal(canal):
    """Classifica o canal quando a frequência não está disponível."""
    c = _int(canal, 0)
    if 1 <= c <= 14:
        return "2.4GHz"
    if 32 <= c <= 177:
        return "5GHz"
    return "desconhecida"


def classificar_risco(seguranca, rssi, fora_perimetro=False):
    """Classifica o risco de exposição de uma rede Wi-Fi (baixo..critico).

    EN: Classifies Wi-Fi exposure risk from security, signal and perimeter.

    PT-BR: Regra documentada e determinística:

    1. **Aberta/WEP** com sinal forte (>= -70 dBm) = `alto`; com sinal fraco =
       `medio`. É o caso de vazamento utilizável.
    2. **Desconhecida** com sinal forte = `medio`; fraco = `baixo`.
    3. **WPA2/WPA3** = `baixo` (a rede está protegida; o achado é de
       visibilidade, não de quebra de cifra).
    4. **Fora do perímetro** eleva um nível (`baixo`→`medio`→`alto`→`critico`)
       somente quando o sinal é forte: rede fraca do vizinho não é vazamento
       do perímetro.

    Nunca afirma comprometimento: é triagem para revisão humana.
    """
    seg = normalizar_seguranca(seguranca)
    forte = _float(rssi, -100.0) >= RSSI_FORTE
    if seg in ("aberta", "wep"):
        risco = "alto" if forte else "medio"
    elif seg == "desconhecida":
        risco = "medio" if forte else "baixo"
    else:
        risco = "baixo"
    if _booleano(fora_perimetro) and forte:
        risco = _RISCO_INVERSO[min(3, _ORDEM_RISCO[risco] + 1)]
    return risco


def _canal_banda(registro):
    """Resolve (banda, canal) a partir de freq/canal/banda informados."""
    freq = _pegar(registro, "freq", "")
    canal = _int(_pegar(registro, "canal", 0), 0)
    banda = _texto(_pegar(registro, "banda", ""))
    if not canal and freq:
        canal = canal_por_frequencia(freq)
    if not banda:
        banda = banda_por_frequencia(freq) if freq else banda_por_canal(canal)
    return banda, canal


def _registro_base(origem):
    """Monta o dict bruto canônico a partir de um dict de entrada."""
    banda, canal = _canal_banda(origem)
    return {
        "ssid": _texto(_pegar(origem, "ssid", "")),
        "bssid": _texto(_pegar(origem, "bssid", "")),
        "banda": banda,
        "canal": canal,
        "rssi": _float(_pegar(origem, "rssi", 0), 0.0),
        "seguranca": _texto(_pegar(origem, "seguranca", "")),
        "latitude": _float(_pegar(origem, "latitude", ""), None),
        "longitude": _float(_pegar(origem, "longitude", ""), None),
    }


def _sniff_delimitador(texto):
    """Detecta `,`, `;` ou tabulação no cabeçalho; cai em vírgula."""
    try:
        return csv.Sniffer().sniff(texto[:2048], delimiters=",;\t").delimiter
    except Exception:
        cabecalho = (texto or "").splitlines()[0] if texto else ""
        for sep in (";", "\t"):
            if sep in cabecalho:
                return sep
        return ","


def parse_csv(texto):
    """Parseia CSV/TSV com cabeçalho e devolve registros brutos (com BSSID).

    EN: Parses headered CSV/TSV into raw records.

    Aceita vírgula, ponto e vírgula ou tabulação e apelidos de coluna (PT-BR
    e EN). O BSSID sai cru aqui — quem for persistir/exportar deve chamar
    `normalizar_registro`, que o substitui pelo hash.
    """
    try:
        conteudo = (texto or "").lstrip("\ufeff")
        if not conteudo.strip():
            return []
        delimitador = _sniff_delimitador(conteudo)
        leitor = csv.DictReader(io.StringIO(conteudo),
                                delimiter=delimitador)
        registros = []
        for linha in leitor:
            if not linha:
                continue
            limpo = {_texto(k).lstrip("\ufeff").lower(): v
                     for k, v in linha.items() if k is not None}
            if not any(_texto(v) for v in limpo.values()):
                continue
            registro = _registro_base(limpo)
            if not registro["ssid"] and not registro["bssid"]:
                continue
            registros.append(registro)
        return registros
    except Exception:
        return []


def parse_json(texto):
    """Parseia lista JSON (ou objeto com lista) e devolve registros brutos."""
    try:
        dados = json.loads((texto or "").strip())
    except (TypeError, ValueError):
        return []
    if isinstance(dados, dict):
        for chave in ("redes", "networks", "registros", "results", "data"):
            if isinstance(dados.get(chave), list):
                dados = dados[chave]
                break
        else:
            dados = [dados]
    if not isinstance(dados, list):
        return []
    registros = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        registro = _registro_base(item)
        if not registro["ssid"] and not registro["bssid"]:
            continue
        registros.append(registro)
    return registros


def _dividir_campos(linha):
    """Divide uma linha do nmcli respeitando `\\:`/`\\;` escapados.

    EN: Splits an nmcli line while honoring escaped separators.
    """
    sep = ";" if ";" in linha else ":"
    partes, atual, escape = [], [], False
    for caractere in linha:
        if escape:
            atual.append(caractere)
            escape = False
        elif caractere == "\\":
            escape = True
        elif caractere == sep:
            partes.append("".join(atual))
            atual = []
        else:
            atual.append(caractere)
    partes.append("".join(atual))
    # nmcli pode imprimir o BSSID sem escape: SSID:AA:BB:CC:DD:EE:FF:80:WPA2
    if sep == ":" and len(partes) > 4:
        for inicio in range(1, len(partes) - 5):
            bloco = partes[inicio:inicio + 6]
            if all(_HEX_PAR.match(p or "") for p in bloco):
                mac = ":".join(bloco)
                resto = partes[:inicio] + [mac] + partes[inicio + 6:]
                partes = resto
                break
    return partes


def parse_nmcli(texto):
    """Parseia `nmcli -t -f SSID,BSSID,SIGNAL,SECURITY dev wifi list`.

    O campo SIGNAL do nmcli é 0–100 (percentual), não dBm. A conversão usada
    é `rssi = signal/2 - 100`: 100→-50 dBm, 50→-75 dBm, 0→-100 dBm. É uma
    aproximação de triagem; quando o adaptador informar dBm diretamente, o
    valor negativo é mantido.
    """
    registros = []
    try:
        for linha in (texto or "").splitlines():
            linha = linha.rstrip("\r")
            if not linha.strip():
                continue
            partes = _dividir_campos(linha)
            if len(partes) < 2:
                continue
            if partes[0].strip().lower() == "ssid":
                continue
            ssid = _texto(partes[0])
            bssid = _texto(partes[1] if len(partes) > 1 else "")
            sinal = _int(partes[2], 0) if len(partes) > 2 else 0
            seguranca = _texto(" ".join(partes[3:])) if len(partes) > 3 else ""
            if not _MAC_RE.fullmatch(bssid):
                encontrado = _MAC_RE.search(linha)
                bssid = encontrado.group(0) if encontrado else bssid
            if 0 <= sinal <= 100:
                rssi = sinal / 2.0 - 100.0
            else:
                rssi = float(sinal)
            registros.append({
                "ssid": ssid,
                "bssid": bssid,
                "banda": "",
                "canal": 0,
                "rssi": rssi,
                "seguranca": seguranca,
                "latitude": None,
                "longitude": None,
            })
        return registros
    except Exception:
        return []


def parse_iw(texto):
    """Parseia a saída de `iw dev <interface> scan` (blocos `BSS`).

    Extrai BSSID, SSID, `signal` (dBm), `freq`/`DS Parameter set` (banda e
    canal) e a segurança pelos blocos `RSN:`/`WPA:`. `RSN` com `SAE`/`WPA3`
    vira `wpa3`; `RSN` sem SAE vira `wpa2`; `WPA:` isolado (WPA1) vira
    `desconhecida` para não superestimar a proteção.
    """
    registros = []
    atual = None

    def _fechar():
        if atual is None:
            return
        if atual["_wpa3"]:
            atual["seguranca"] = "wpa3"
        elif atual["_rsn"]:
            atual["seguranca"] = "wpa2"
        elif atual["_wpa"]:
            atual["seguranca"] = "desconhecida"
        elif atual["_wep"]:
            atual["seguranca"] = "wep"
        else:
            atual["seguranca"] = "aberta"
        for chave in ("_rsn", "_wpa3", "_wpa", "_wep"):
            atual.pop(chave, None)
        if atual["ssid"] or atual["bssid"]:
            registros.append(atual)

    try:
        for linha in (texto or "").splitlines():
            linha = linha.rstrip("\r")
            achado_bss = re.match(r"^\s*BSS\s+([0-9A-Fa-f:]{17})", linha)
            if achado_bss:
                _fechar()
                atual = {"ssid": "", "bssid": achado_bss.group(1),
                         "banda": "", "canal": 0, "rssi": 0,
                         "seguranca": "", "latitude": None,
                         "longitude": None, "_rsn": False, "_wpa3": False,
                         "_wpa": False, "_wep": False, "_freq": 0.0}
                continue
            if atual is None:
                continue
            achado_ssid = re.match(r"^\s*SSID:\s*(.*)$", linha)
            if achado_ssid:
                atual["ssid"] = achado_ssid.group(1).strip()
                continue
            achado_sinal = re.search(
                r"signal:\s*(-?\d+(?:[.,]\d+)?)\s*dBm", linha)
            if achado_sinal:
                atual["rssi"] = _float(achado_sinal.group(1), 0.0)
                continue
            achado_freq = re.search(r"freq:\s*(\d+(?:[.,]\d+)?)", linha)
            if achado_freq:
                atual["_freq"] = _float(achado_freq.group(1), 0.0)
                continue
            achado_canal = re.search(r"DS Parameter set:\s*channel\s*(\d+)",
                                     linha)
            if achado_canal:
                atual["canal"] = _int(achado_canal.group(1), 0)
                continue
            if re.match(r"^\s*RSN:", linha):
                atual["_rsn"] = True
            if re.match(r"^\s*WPA:", linha):
                atual["_wpa"] = True
            if "SAE" in linha or "WPA3" in linha:
                atual["_wpa3"] = True
            if "WEP" in linha:
                atual["_wep"] = True
        _fechar()
        for registro in registros:
            freq = registro.get("_freq") or 0
            if freq:
                registro["banda"] = banda_por_frequencia(freq)
                if not registro["canal"]:
                    registro["canal"] = canal_por_frequencia(freq)
            if not registro["banda"]:
                registro["banda"] = banda_por_canal(registro["canal"])
            registro.pop("_freq", None)
        return registros
    except Exception:
        return []


def montar_evidencia(registro):
    """Monta uma linha de evidência sem qualquer identificador cru."""
    partes = [
        f"SSID={registro.get('ssid') or '—'}",
        f"banda={registro.get('banda') or '—'}",
        f"canal={registro.get('canal') or 0}",
        f"rssi={_float(registro.get('rssi'), 0):.0f} dBm",
        f"seguranca={registro.get('seguranca') or 'desconhecida'}",
        "fora_perimetro=" + ("sim" if registro.get("fora_perimetro") else "não"),
        f"risco={registro.get('risco') or 'baixo'}",
    ]
    return " · ".join(partes)


def normalizar_registro(registro):
    """Converte um registro bruto no dict canônico sanitizado.

    EN: Normalizes one raw record into the canonical sanitized dict.

    PT-BR: Devolve somente as chaves `ssid`, `bssid_hash`, `banda`, `canal`,
    `rssi`, `seguranca`, `fora_perimetro`, `risco`, `latitude`, `longitude` e
    `evidencia`. A chave `bssid` NUNCA existe na saída. Dict inválido devolve
    `{}` (o chamador ignora).
    """
    if not isinstance(registro, dict):
        return {}
    base = _registro_base(registro)
    if not base["ssid"] and not base["bssid"]:
        return {}
    fora = 1 if _booleano(_pegar(registro, "fora_perimetro", 0)) else 0
    seguranca = normalizar_seguranca(base["seguranca"])
    risco = classificar_risco(seguranca, base["rssi"], fora)
    canonico = {
        "ssid": base["ssid"],
        "bssid_hash": hash_bssid(base["bssid"]),
        "banda": base["banda"],
        "canal": base["canal"],
        "rssi": base["rssi"],
        "seguranca": seguranca,
        "fora_perimetro": fora,
        "risco": risco,
        "latitude": base["latitude"],
        "longitude": base["longitude"],
    }
    canonico["evidencia"] = montar_evidencia(canonico)
    return canonico


def resumo_registros(registros):
    """Resume registros sanitizados (ou brutos) para painel/CLI.

    Devolve `total`, `abertas`, `fora_perimetro`, `criticos` e `por_risco`.
    Registros brutos são normalizados antes de contar.
    """
    resumo = {"total": 0, "abertas": 0, "fora_perimetro": 0, "criticos": 0,
              "por_risco": {r: 0 for r in RISCOS}}
    try:
        for item in registros or []:
            registro = item if isinstance(item, dict) and \
                "bssid_hash" in item else normalizar_registro(item)
            if not registro:
                continue
            resumo["total"] += 1
            if registro.get("seguranca") == "aberta":
                resumo["abertas"] += 1
            if registro.get("fora_perimetro"):
                resumo["fora_perimetro"] += 1
            risco = registro.get("risco") or "baixo"
            if risco not in resumo["por_risco"]:
                risco = "baixo"
            resumo["por_risco"][risco] += 1
            if risco == "critico":
                resumo["criticos"] += 1
        return resumo
    except Exception:
        return resumo


def _executar(comando, timeout=8):
    """Executa um comando e devolve stdout (vazio em qualquer falha)."""
    try:
        resultado = subprocess.run(
            comando, capture_output=True, text=True, timeout=timeout)
        return resultado.stdout or ""
    except Exception:
        return ""


def escanear_ao_vivo():
    """Varredura passiva opcional via `nmcli` (sem root) ou `iw` (fail-soft).

    EN: Optional passive live scan; returns [] when unavailable.

    PT-BR: Devolve registros **já normalizados** (sem BSSID cru). Respeita
    `TISOSDOCFLY_RF_VIVO=0` para desligar a varredura (usado em testes e em
    ambientes sem autorização). Qualquer falha — ferramenta ausente, sem
    permissão, sem interface — resulta em lista vazia, nunca exceção.
    """
    if _texto(os.environ.get("TISOSDOCFLY_RF_VIVO", "1")).lower() == "0":
        return []
    brutos = []
    try:
        nmcli = shutil.which("nmcli")
        if nmcli:
            texto = _executar([
                nmcli, "-t", "-f", "SSID,BSSID,SIGNAL,SECURITY",
                "dev", "wifi", "list"])
            brutos = parse_nmcli(texto)
        if not brutos:
            iw = shutil.which("iw")
            if iw:
                texto = _executar([iw, "dev", "scan"], timeout=20)
                brutos = parse_iw(texto)
    except Exception:
        brutos = []
    vistos = set()
    saida = []
    for bruto in brutos:
        registro = normalizar_registro(bruto)
        if not registro:
            continue
        chave = registro.get("bssid_hash") or \
            (registro.get("ssid"), registro.get("canal"))
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(registro)
    return saida


def _ler_arquivo(caminho):
    """Lê um arquivo de texto UTF-8 (BOM tolerado); vazio em falha."""
    try:
        with open(caminho, "r", encoding="utf-8-sig") as arquivo:
            return arquivo.read()
    except Exception:
        return ""


def main(argv=None):
    """CLI: `python -m mod_tisosdocfly.rf_scan --csv entrada --out saida.json`.

    EN: Command-line entrypoint for offline RF scan conversion.

    Gera um JSON sanitizado (sem BSSID cru) com `gerado_em`, `total`,
    `resumo` e `registros`. Sem `--out`, imprime somente o resumo e o JSON
    completo na saída padrão.
    """
    parser = argparse.ArgumentParser(
        description="Converte uma varredura Wi-Fi/RF em JSON sanitizado "
                    "(BSSID apenas como hash SHA-256).")
    parser.add_argument("--csv", dest="arquivo_csv", default="",
                        help="arquivo CSV/TSV de entrada")
    parser.add_argument("--json", dest="arquivo_json", default="",
                        help="arquivo JSON de entrada")
    parser.add_argument("--ao-vivo", action="store_true",
                        help="tenta nmcli/iw no equipamento local")
    parser.add_argument("--out", default="",
                        help="arquivo JSON de saída (opcional)")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    brutos = []
    if args.arquivo_csv:
        texto = _ler_arquivo(args.arquivo_csv)
        if not texto:
            print(f"rf_scan: não foi possível ler {args.arquivo_csv}",
                  file=sys.stderr)
            return 2
        brutos.extend(parse_csv(texto))
    if args.arquivo_json:
        texto = _ler_arquivo(args.arquivo_json)
        if not texto:
            print(f"rf_scan: não foi possível ler {args.arquivo_json}",
                  file=sys.stderr)
            return 2
        brutos.extend(parse_json(texto))
    if args.ao_vivo:
        brutos.extend(escanear_ao_vivo())

    registros = [r for r in (normalizar_registro(b) for b in brutos) if r]
    relatorio = {
        "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(registros),
        "resumo": resumo_registros(registros),
        "registros": registros,
    }
    texto_json = json.dumps(relatorio, ensure_ascii=False, indent=2)
    if args.out:
        try:
            # `--out saida` (diretório) ou `--out saida.json` (arquivo).
            destino = args.out
            if not destino.lower().endswith(".json"):
                os.makedirs(destino, exist_ok=True)
                destino = os.path.join(destino, "rf_sanitizado.json")
            pasta = os.path.dirname(os.path.abspath(destino))
            if pasta:
                os.makedirs(pasta, exist_ok=True)
            with open(destino, "w", encoding="utf-8") as arquivo:
                arquivo.write(texto_json + "\n")
        except Exception as exc:
            print(f"rf_scan: falha ao gravar {args.out}: {exc}",
                  file=sys.stderr)
            return 2
        resumo = relatorio["resumo"]
        print(f"rf_scan: {relatorio['total']} rede(s) · "
              f"{resumo['abertas']} aberta(s) · "
              f"{resumo['fora_perimetro']} fora do perímetro · "
              f"{resumo['criticos']} crítica(s)")
        print(f"rf_scan: saída sanitizada em {destino}")
    else:
        print(texto_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
