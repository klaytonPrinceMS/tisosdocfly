"""Avaliação de imagens em Python puro (stdlib), sem modelo e sem rede.

Pure-Python image evaluation. Decodifica PNG/BMP/PPM com `zlib` e `struct` da
stdlib e calcula métricas de cor, índices de vegetação, bordas, entropia e
blobs. JPEG é decodificado pelo Pillow quando disponível — a AVALIAÇÃO
continua 100% em Python; o Pillow só entrega os pixels.

Por que existe: o baseline anterior dependia de numpy/Pillow para toda a
conta. Aqui a conta é explícita, auditável e determinística, sem peso de
modelo treinado e sem chamada externa. É o que roda por padrão em
`ia.analisar_imagem`; um modelo homologado pode substituir via registro.

Limites (honestos):
- índices são de COR (RGB), não de reflectância calibrada;
- não há detector de pessoas/armas; segurança exige modelo homologado;
- imagens gigantes são amostradas (máx. ~192 px no maior lado) para manter a
  conta barata; os valores são proporcionais, não contagem absoluta.
"""
import math
import struct
import zlib
from pathlib import Path

MAX_LADO_AMOSTRA = 192
# Acima deste tamanho o decode puro de PNG/BMP fica caro (medido: 2000x1500
# em ~5 s). O Pillow é usado SÓ para decodificar; as métricas continuam em
# Python puro. Sem Pillow, o decode puro ainda funciona (mais lento).
LIMITE_BYTES_PURO = 8_000_000
LIMITE_PIXELS_PURO = 2_000_000
_EPS = 1e-9
LIMIAR_BORDA = 0.20


# =============================================================================
# Decodificação
# =============================================================================

def _amostrar_lista(pixels, largura, altura, max_lado=MAX_LADO_AMOSTRA):
    """Amostra uma matriz de pixels (lista de tuplas) por passo inteiro."""
    try:
        passo = max(1, math.ceil(max(largura, altura) / max_lado))
        sw = len(range(0, largura, passo))
        sh = len(range(0, altura, passo))
        amostra = []
        for y in range(0, altura, passo):
            base = y * largura
            for x in range(0, largura, passo):
                amostra.append(pixels[base + x])
        return sw, sh, amostra, passo
    except Exception:
        return 0, 0, [], 1


def _ler_ppm(dados, max_lado=MAX_LADO_AMOSTRA):
    """Lê PPM P6 (binário) ou P3 (ASCII) e devolve (w,h,pixels,passo)."""
    # Tokeniza o cabeçalho (comentários começam com #).
    pos = 0
    tokens = []
    n = len(dados)
    while len(tokens) < 4 and pos < n:
        while pos < n and dados[pos:pos + 1].isspace():
            pos += 1
        if pos < n and dados[pos:pos + 1] == b"#":
            while pos < n and dados[pos:pos + 1] not in (b"\n", b"\r"):
                pos += 1
            continue
        ini = pos
        while pos < n and not dados[pos:pos + 1].isspace():
            pos += 1
        if pos > ini:
            tokens.append(dados[ini:pos])
    if len(tokens) < 4 or tokens[0] not in (b"P6", b"P3"):
        raise ValueError("PPM inválido")
    largura = int(tokens[1])
    altura = int(tokens[2])
    maxval = int(tokens[3])
    if maxval <= 0:
        raise ValueError("PPM maxval inválido")
    escala = 255.0 / maxval
    passo = max(1, math.ceil(max(largura, altura) / max_lado))
    amostra = []
    if tokens[0] == b"P6":
        # Um separador após o maxval.
        while pos < n and dados[pos:pos + 1].isspace():
            pos += 1
        canais = 3
        for y in range(0, altura, passo):
            base = pos + y * largura * canais
            for x in range(0, largura, passo):
                i = base + x * canais
                r = int(dados[i] * escala)
                g = int(dados[i + 1] * escala)
                b = int(dados[i + 2] * escala)
                amostra.append((r, g, b))
    else:
        valores = []
        while pos < n and len(valores) < largura * altura * 3:
            while pos < n and dados[pos:pos + 1].isspace():
                pos += 1
            ini = pos
            while pos < n and not dados[pos:pos + 1].isspace():
                pos += 1
            if pos > ini:
                valores.append(int(dados[ini:pos]))
        for y in range(0, altura, passo):
            base = y * largura
            for x in range(0, largura, passo):
                i = (base + x) * 3
                amostra.append((int(valores[i] * escala),
                                int(valores[i + 1] * escala),
                                int(valores[i + 2] * escala)))
    sw = len(range(0, largura, passo))
    sh = len(range(0, altura, passo))
    return sw, sh, amostra, passo


def _ler_bmp(dados, max_lado=MAX_LADO_AMOSTRA):
    """Lê BMP 24/32 bits sem compressão."""
    if dados[:2] != b"BM":
        raise ValueError("BMP inválido")
    deslocamento = struct.unpack_from("<I", dados, 10)[0]
    tamanho_dib = struct.unpack_from("<I", dados, 14)[0]
    if tamanho_dib < 40:
        raise ValueError("BMP DIB não suportado")
    largura, altura = struct.unpack_from("<ii", dados, 18)
    bpp = struct.unpack_from("<H", dados, 28)[0]
    compressao = struct.unpack_from("<I", dados, 30)[0]
    if compressao != 0 or bpp not in (24, 32):
        raise ValueError("BMP comprimido/não 24-32 bits")
    topo_para_baixo = altura < 0
    altura = abs(altura)
    canais = bpp // 8
    passo_linha = ((largura * canais + 3) // 4) * 4
    passo = max(1, math.ceil(max(largura, altura) / max_lado))
    amostra = []
    for y in range(0, altura, passo):
        linha = y if topo_para_baixo else altura - 1 - y
        base = deslocamento + linha * passo_linha
        for x in range(0, largura, passo):
            i = base + x * canais
            b, g, r = dados[i], dados[i + 1], dados[i + 2]
            amostra.append((r, g, b))
    sw = len(range(0, largura, passo))
    sh = len(range(0, altura, passo))
    return sw, sh, amostra, passo


def _desfiltrar_png(linha, anterior, filtro, bpp):
    """Aplica o filtro PNG (0-4) e devolve a linha desfiltrada."""
    tam = len(linha)
    saida = bytearray(tam)
    if filtro == 0:
        return bytearray(linha)
    if filtro == 1:  # Sub
        for i in range(tam):
            esq = saida[i - bpp] if i >= bpp else 0
            saida[i] = (linha[i] + esq) & 0xFF
        return saida
    if filtro == 2:  # Up
        for i in range(tam):
            saida[i] = (linha[i] + anterior[i]) & 0xFF
        return saida
    if filtro == 3:  # Average
        for i in range(tam):
            esq = saida[i - bpp] if i >= bpp else 0
            cima = anterior[i]
            saida[i] = (linha[i] + ((esq + cima) // 2)) & 0xFF
        return saida
    if filtro == 4:  # Paeth
        for i in range(tam):
            a = saida[i - bpp] if i >= bpp else 0
            b = anterior[i]
            c = anterior[i - bpp] if i >= bpp else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            saida[i] = (linha[i] + pred) & 0xFF
        return saida
    raise ValueError("Filtro PNG inválido")


def _ler_png(dados, max_lado=MAX_LADO_AMOSTRA):
    """Lê PNG 8 bits (RGB/RGBA/cinza/cinza+alfa/paleta), sem interlace."""
    if dados[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("PNG inválido")
    pos = 8
    idat = bytearray()
    paleta = None
    largura = altura = bits = cor = interlace = 0
    n = len(dados)
    while pos + 8 <= n:
        comprimento = struct.unpack_from(">I", dados, pos)[0]
        tipo = dados[pos + 4:pos + 8]
        corpo = dados[pos + 8:pos + 8 + comprimento]
        pos += 12 + comprimento
        if tipo == b"IHDR":
            largura, altura, bits, cor, _comp, _filt, interlace = \
                struct.unpack(">IIBBBBB", corpo[:13])
        elif tipo == b"PLTE":
            paleta = [tuple(corpo[i:i + 3])
                      for i in range(0, len(corpo), 3)]
        elif tipo == b"IDAT":
            idat += corpo
        elif tipo == b"IEND":
            break
    if interlace:
        raise ValueError("PNG entrelaçado não suportado")
    if bits not in (8, 16):
        raise ValueError("PNG bit depth não suportado")
    canais = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(cor)
    if canais is None:
        raise ValueError("PNG color type não suportado")
    if cor == 3 and not paleta:
        raise ValueError("PNG paleta sem PLTE")
    bytes_por_pixel = canais * (bits // 8)
    tam_linha = largura * bytes_por_pixel
    cru = zlib.decompress(bytes(idat))
    passo = max(1, math.ceil(max(largura, altura) / max_lado))
    sw = len(range(0, largura, passo))
    sh = len(range(0, altura, passo))
    amostra = []
    anterior = bytearray(tam_linha)
    p = 0
    for y in range(altura):
        if p >= len(cru):
            break
        filtro = cru[p]
        p += 1
        linha = _desfiltrar_png(cru[p:p + tam_linha], anterior, filtro,
                                bytes_por_pixel)
        p += tam_linha
        if y % passo == 0:
            for x in range(0, largura, passo):
                i = x * bytes_por_pixel
                if cor == 2:
                    r, g, b = linha[i], linha[i + 1], linha[i + 2]
                elif cor == 6:
                    r, g, b = linha[i], linha[i + 1], linha[i + 2]
                elif cor == 0:
                    r = g = b = linha[i]
                elif cor == 4:
                    r = g = b = linha[i]
                else:  # paleta
                    idx = linha[i]
                    r, g, b = paleta[idx] if idx < len(paleta) else (0, 0, 0)
                amostra.append((r, g, b))
        anterior = linha
    return sw, sh, amostra, passo


def _ler_pillow(caminho, max_lado=MAX_LADO_AMOSTRA):
    """Fallback para JPEG/WebP: o Pillow só DECODIFICA; a conta é nossa."""
    from PIL import Image
    with Image.open(caminho) as img:
        img = img.convert("RGB")
        img.thumbnail((max_lado, max_lado))
        largura, altura = img.size
        pixels = list(img.getdata())
    return largura, altura, pixels, max(1, math.ceil(
        max(largura, altura) / max_lado))


def _pixels_da_imagem(dados):
    """Lê largura*altura do cabeçalho (PNG/BMP/PPM) sem decodificar."""
    try:
        if dados[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack_from(">II", dados, 16)
            return w * h
        if dados[:2] == b"BM":
            w, h = struct.unpack_from("<ii", dados, 18)
            return abs(w) * abs(h)
        if dados[:2] in (b"P6", b"P3"):
            partes = dados[:128].split()
            if len(partes) >= 3:
                return int(partes[1]) * int(partes[2])
    except Exception:
        pass
    return 0


def carregar_pixels(caminho, max_lado=MAX_LADO_AMOSTRA):
    """Carrega pixels amostrados de PNG/BMP/PPM/JPEG.

    Devolve `(largura, altura, [(r,g,b), ...], passo, fonte)`. PNG/BMP/PPM
    pequenos são decodificados em Python puro; arquivos grandes e
    JPEG/WebP usam Pillow apenas como decoder. `None` em falha.
    """
    try:
        if not caminho:
            return None
        dados = Path(caminho).read_bytes()
        puro = dados[:8] == b"\x89PNG\r\n\x1a\n" or dados[:2] == b"BM" \
            or dados[:2] in (b"P6", b"P3")
        # Arquivo grande: tenta o decoder do Pillow primeiro para não gastar
        # segundos no unfilter puro; a avaliação continua em Python.
        grande = (len(dados) > LIMITE_BYTES_PURO
                  or _pixels_da_imagem(dados) > LIMITE_PIXELS_PURO)
        if puro and grande:
            try:
                w, h, px, passo = _ler_pillow(caminho, max_lado)
                return w, h, px, passo, "pillow-decode"
            except Exception:
                pass
        if dados[:8] == b"\x89PNG\r\n\x1a\n":
            w, h, px, passo = _ler_png(dados, max_lado)
            return w, h, px, passo, "python-puro"
        if dados[:2] == b"BM":
            w, h, px, passo = _ler_bmp(dados, max_lado)
            return w, h, px, passo, "python-puro"
        if dados[:2] in (b"P6", b"P3"):
            w, h, px, passo = _ler_ppm(dados, max_lado)
            return w, h, px, passo, "python-puro"
        w, h, px, passo = _ler_pillow(caminho, max_lado)
        return w, h, px, passo, "pillow-decode"
    except Exception:
        try:
            w, h, px, passo = _ler_pillow(caminho, max_lado)
            return w, h, px, passo, "pillow-decode"
        except Exception:
            return None


# =============================================================================
# Métricas
# =============================================================================

def _lum(pixel):
    return 0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]


def _blobs(mask, largura, altura, minimo=4):
    """Conta componentes conexos 4-vizinhos de uma máscara booleana."""
    try:
        visitado = bytearray(largura * altura)
        total = 0
        maior = 0
        for inicio in range(largura * altura):
            if not mask[inicio] or visitado[inicio]:
                continue
            pilha = [inicio]
            visitado[inicio] = 1
            tamanho = 0
            while pilha:
                i = pilha.pop()
                tamanho += 1
                x, y = i % largura, i // largura
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < largura and 0 <= ny < altura:
                        j = ny * largura + nx
                        if mask[j] and not visitado[j]:
                            visitado[j] = 1
                            pilha.append(j)
            if tamanho >= minimo:
                total += 1
                maior = max(maior, tamanho)
        return total, (maior / max(1, largura * altura))
    except Exception:
        return 0, 0.0


def _metricas(largura, altura, pixels):
    """Calcula métricas de cor, índices, bordas, entropia e blobs."""
    n = len(pixels)
    if not n or not largura or not altura:
        return {}
    soma_r = soma_g = soma_b = 0.0
    soma_lum = soma_lum2 = 0.0
    soma_sat = 0.0
    verde = marrom = cinza = escuro = laranja = 0
    exg_s = vari_s = gli_s = tgi_s = 0.0
    veg = 0
    lum_pixels = []
    masks = {"verde": bytearray(n), "escuro": bytearray(n)}
    for i, (r, g, b) in enumerate(pixels):
        rn, gn, bn = r / 255.0, g / 255.0, b / 255.0
        soma_r += rn
        soma_g += gn
        soma_b += bn
        lum = _lum((rn, gn, bn))
        lum_pixels.append(lum)
        soma_lum += lum
        soma_lum2 += lum * lum
        mx, mn = max(rn, gn, bn), min(rn, gn, bn)
        soma_sat += (mx - mn) / mx if mx > _EPS else 0.0
        if gn > rn * 1.10 and gn > bn * 1.10:
            verde += 1
            masks["verde"][i] = 1
        if rn > gn * 1.10 and gn > bn * 1.05 and rn < 0.80:
            marrom += 1
        if (mx - mn) < 0.08:
            cinza += 1
        if lum < 0.20:
            escuro += 1
            masks["escuro"][i] = 1
        if rn > 1.70 * gn and gn > bn:
            laranja += 1
        soma = rn + gn + bn + _EPS
        rc, gc, bc = rn / soma, gn / soma, bn / soma
        exg = 2.0 * gc - rc - bc
        exg_s += exg
        vari_s += max(-2.0, min(2.0, (gc - rc) / (gc + rc - bc + _EPS)))
        gli_s += (2.0 * gc - rc - bc) / (2.0 * gc + rc + bc + _EPS)
        tgi_s += max(-2.0, min(2.0, (gc - rc) / (gc + bc - rc + _EPS)))
        if exg > 0.10:
            veg += 1
    media_r = soma_r / n
    media_g = soma_g / n
    media_b = soma_b / n
    brilho = soma_lum / n
    variancia = max(0.0, soma_lum2 / n - brilho * brilho)
    contraste = math.sqrt(variancia)

    # Entropia de luminância em 16 faixas.
    hist = [0] * 16
    for lum in lum_pixels:
        hist[min(15, max(0, int(lum * 16)))] += 1
    entropia = 0.0
    for q in hist:
        if q:
            p = q / n
            entropia -= p * math.log2(p)

    # Densidade de borda (Sobel 3x3) sobre a grade amostrada.
    soma_grad = 0.0
    total_grad = 0
    for y in range(1, altura - 1):
        base = y * largura
        for x in range(1, largura - 1):
            i = base + x
            gx = (-lum_pixels[i - largura - 1]
                  - 2 * lum_pixels[i - 1]
                  - lum_pixels[i + largura - 1]
                  + lum_pixels[i - largura + 1]
                  + 2 * lum_pixels[i + 1]
                  + lum_pixels[i + largura + 1])
            gy = (-lum_pixels[i - largura - 1]
                  - 2 * lum_pixels[i - largura]
                  - lum_pixels[i - largura + 1]
                  + lum_pixels[i + largura - 1]
                  + 2 * lum_pixels[i + largura]
                  + lum_pixels[i + largura + 1])
            soma_grad += math.hypot(gx, gy)
            total_grad += 1
    densidade = (soma_grad / total_grad) if total_grad else 0.0

    blobs_verde, maior_verde = _blobs(masks["verde"], largura, altura)
    blobs_escuro, maior_escuro = _blobs(masks["escuro"], largura, altura)

    return {
        "largura_amostrada": largura,
        "altura_amostrada": altura,
        "pixels_amostrados": n,
        "media_rgb": [media_r, media_g, media_b],
        "brilho": brilho,
        "contraste": contraste,
        "saturacao_media": soma_sat / n,
        "verde_ratio": verde / n,
        "marrom_ratio": marrom / n,
        "cinza_ratio": cinza / n,
        "escuro_ratio": escuro / n,
        "laranja_ratio": laranja / n,
        "densidade_borda": densidade,
        "entropia": entropia,
        "ExG": exg_s / n,
        "VARI": vari_s / n,
        "GLI": gli_s / n,
        "TGI": tgi_s / n,
        "vegetacao_ratio": veg / n,
        "blobs_verde": blobs_verde,
        "blobs_escuro": blobs_escuro,
        "maior_blob_verde_ratio": maior_verde,
        "maior_blob_escuro_ratio": maior_escuro,
        "metodo": "python-puro",
    }


def avaliar_imagem(caminho, max_lado=MAX_LADO_AMOSTRA):
    """Avalia uma imagem e devolve o dicionário de métricas (ou {})."""
    try:
        carregado = carregar_pixels(caminho, max_lado=max_lado)
        if not carregado:
            return {}
        largura, altura, pixels, passo, fonte = carregado
        metricas = _metricas(largura, altura, pixels)
        if not metricas:
            return {}
        metricas["passo_amostragem"] = passo
        metricas["fonte"] = fonte
        return metricas
    except Exception:
        return {}
