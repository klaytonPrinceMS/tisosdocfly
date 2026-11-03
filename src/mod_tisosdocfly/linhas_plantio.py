"""Detecção de linhas de plantio em imagens de drone (Python puro).

Baseado no vídeo "Usando Visão Computacional para detectar linhas de plantio
em imagens de Drone" (GeoIA Aplicada) e no método clássico de visão
computacional:

1. separar vegetação de solo por banda/índice e limiar (Otsu);
2. gerar o envelope (convex hull) da área vegetada;
3. limpar a máscara com morfologia (abertura/fechamento);
4. extrair bordas (Sobel) e aplicar a **Transformada de Hough**;
5. converter as linhas em segmentos, estimar ângulo e espaçamento;
6. exportar GeoJSON de linhas e imagem anotada.

Implementação em Python puro (sem OpenCV/numpy). Para imagens grandes, a
avaliação é amostrada; o resultado é de triagem e deve ser validado em campo.

Limites: linhas curvas não são bem representadas por Hough (o próprio vídeo
alerta); culturas em linha reta são o caso de uso.
"""
import argparse
import json
import math
import os
from pathlib import Path

from mod_tisosdocfly import avaliacao_imagens

MAX_LADO = 256
ANGULO_TOLERANCIA = 8.0
DISTANCIA_TOLERANCIA = 12.0
LIMIAR_VOTOS = 14
PASSO_THETA = 2  # 2° basta para linhas de plantio e reduz a conta pela metade
MAX_PONTOS_BORDA = 6000


def _log():
    try:
        from mod_tisosdocfly import observabilidade
        return observabilidade.get_logger("tisosdocfly")
    except Exception:
        import logging
        return logging.getLogger("linhas_plantio")


def _erro(msg):
    try:
        _log().exception(msg)
    except Exception:
        pass


# =============================================================================
# Máscara de vegetação e morfologia
# =============================================================================

def otsu(valores):
    """Limiar de Otsu para uma lista de floats (histograma de 256 faixas)."""
    try:
        vals = [float(v) for v in valores if math.isfinite(float(v))]
        if not vals:
            return 0.0
        minimo, maximo = min(vals), max(vals)
        if maximo - minimo <= 1e-9:
            return minimo
        hist = [0] * 256
        escala = 255.0 / (maximo - minimo)
        for v in vals:
            hist[min(255, max(0, int((v - minimo) * escala)))] += 1
        total = len(vals)
        soma_total = sum(i * hist[i] for i in range(256))
        soma_b = 0.0
        peso_b = 0
        melhor = 0.0
        melhor_var = -1.0
        for i in range(256):
            peso_b += hist[i]
            if peso_b == 0:
                continue
            peso_f = total - peso_b
            if peso_f == 0:
                break
            soma_b += i * hist[i]
            media_b = soma_b / peso_b
            media_f = (soma_total - soma_b) / peso_f
            var = peso_b * peso_f * (media_b - media_f) ** 2
            if var > melhor_var:
                melhor_var = var
                melhor = minimo + (i / escala)
        return melhor
    except Exception as exc:
        _erro(f"otsu: {exc}")
        return 0.0


def _exg(pixel):
    r, g, b = pixel[0] / 255.0, pixel[1] / 255.0, pixel[2] / 255.0
    soma = r + g + b + 1e-9
    return 2.0 * (g / soma) - (r / soma) - (b / soma)


def mascara_vegetacao(pixels):
    """Máscara booleana por ExG com limiar de Otsu (fallback por luminância)."""
    try:
        exg = [_exg(p) for p in pixels]
        limiar = otsu(exg)
        mask = [1 if v > limiar else 0 for v in exg]
        ratio = sum(mask) / max(1, len(mask))
        if ratio < 0.02 or ratio > 0.98:
            lum = [avaliacao_imagens._lum(
                (p[0] / 255, p[1] / 255, p[2] / 255)) for p in pixels]
            limiar = otsu(lum)
            mask = [1 if v > limiar else 0 for v in lum]
        return mask, limiar, exg
    except Exception as exc:
        _erro(f"mascara_vegetacao: {exc}")
        return [], 0.0, []


def _dilatar(mask, largura, altura, raio=1):
    saida = bytearray(largura * altura)
    for y in range(altura):
        for x in range(largura):
            if not mask[y * largura + x]:
                continue
            for dy in range(-raio, raio + 1):
                ny = y + dy
                if ny < 0 or ny >= altura:
                    continue
                base = ny * largura
                for dx in range(-raio, raio + 1):
                    nx = x + dx
                    if 0 <= nx < largura:
                        saida[base + nx] = 1
    return saida


def _erodir(mask, largura, altura, raio=1):
    saida = bytearray(largura * altura)
    for y in range(altura):
        for x in range(largura):
            if not mask[y * largura + x]:
                continue
            manter = True
            for dy in range(-raio, raio + 1):
                ny = y + dy
                if ny < 0 or ny >= altura:
                    manter = False
                    break
                base = ny * largura
                for dx in range(-raio, raio + 1):
                    nx = x + dx
                    if nx < 0 or nx >= largura or not mask[base + nx]:
                        manter = False
                        break
                if not manter:
                    break
            if manter:
                saida[y * largura + x] = 1
    return saida


def limpar_mascara(mask, largura, altura):
    """Abertura + fechamento 3x3: remove ruído e fecha pequenos buracos."""
    m = _erodir(_dilatar(mask, largura, altura, 1), largura, altura, 1)
    m = _dilatar(_erodir(m, largura, altura, 1), largura, altura, 1)
    return m


# =============================================================================
# Envelope e orientação
# =============================================================================

def convex_hull(pontos):
    """Monotonic chain; devolve o envelope convexo em sentido anti-horário."""
    try:
        pts = sorted(set((int(x), int(y)) for x, y in pontos))
        if len(pts) <= 2:
            return pts

        def cross(o, a, b):
            return ((a[0] - o[0]) * (b[1] - o[1])
                    - (a[1] - o[1]) * (b[0] - o[0]))

        lower = []
        for p in pts:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)
        upper = []
        for p in reversed(pts):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)
        return lower[:-1] + upper[:-1]
    except Exception as exc:
        _erro(f"convex_hull: {exc}")
        return []


def _ponto_em_poligono(x, y, poligono):
    dentro = False
    j = len(poligono) - 1
    for i in range(len(poligono)):
        xi, yi = poligono[i]
        xj, yj = poligono[j]
        if ((yi > y) != (yj > y)) and \
                (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
            dentro = not dentro
        j = i
    return dentro


def _pca_angulo(pontos):
    """Ângulo principal (graus) dos pontos da máscara, via covariância."""
    try:
        n = len(pontos)
        if n < 3:
            return 0.0
        mx = sum(p[0] for p in pontos) / n
        my = sum(p[1] for p in pontos) / n
        sxx = sum((p[0] - mx) ** 2 for p in pontos) / n
        syy = sum((p[1] - my) ** 2 for p in pontos) / n
        sxy = sum((p[0] - mx) * (p[1] - my) for p in pontos) / n
        ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
        return math.degrees(ang) % 180.0
    except Exception:
        return 0.0


# =============================================================================
# Bordas e Hough
# =============================================================================

def bordas_sobel(mask, largura, altura):
    """Pontos de borda da máscara (Sobel 3x3 na luminância binária)."""
    pontos = []
    for y in range(1, altura - 1):
        base = y * largura
        for x in range(1, largura - 1):
            i = base + x
            gx = (-mask[i - largura - 1] - 2 * mask[i - 1]
                  - mask[i + largura - 1] + mask[i - largura + 1]
                  + 2 * mask[i + 1] + mask[i + largura + 1])
            gy = (-mask[i - largura - 1] - 2 * mask[i - largura]
                  - mask[i - largura + 1] + mask[i + largura - 1]
                  + 2 * mask[i + largura] + mask[i + largura + 1])
            if abs(gx) + abs(gy) >= 2:
                pontos.append((x, y))
    return pontos


def hough_linhas(pontos, largura, altura, limiar=LIMIAR_VOTOS):
    """Transformada de Hough: devolve segmentos votados (rho, theta, votos)."""
    try:
        if not pontos:
            return []
        diag = int(math.hypot(largura, altura)) + 2
        if len(pontos) > MAX_PONTOS_BORDA:
            pontos = pontos[::max(1, len(pontos) // MAX_PONTOS_BORDA)]
        thetas = list(range(0, 180, PASSO_THETA))
        n_theta = len(thetas)
        cossenos = [math.cos(math.radians(t)) for t in thetas]
        senos = [math.sin(math.radians(t)) for t in thetas]
        # Acumulador plano (rho × theta): lista de ints é bem mais rápida
        # que dict em Python puro.
        n_rho = 2 * diag + 1
        acc = [0] * (n_rho * n_theta)
        for x, y in pontos:
            for idx in range(n_theta):
                rho = int(round(x * cossenos[idx] + y * senos[idx])) + diag
                if 0 <= rho < n_rho:
                    acc[rho * n_theta + idx] += 1
        picos = []
        for rho_i in range(n_rho):
            base = rho_i * n_theta
            for idx in range(n_theta):
                votos = acc[base + idx]
                if votos >= limiar:
                    picos.append((votos, rho_i - diag, thetas[idx]))
        picos.sort(reverse=True)
        aceitos = []
        for votos, rho, theta in picos:
            perto = False
            for r2, t2, _v in aceitos:
                if abs(rho - r2) <= 8 and abs(theta - t2) <= 6:
                    perto = True
                    break
            if not perto:
                aceitos.append((rho, theta, votos))
        linhas = []
        for rho, theta, votos in aceitos:
            rad = math.radians(theta)
            cos_t, sin_t = math.cos(rad), math.sin(rad)
            # Pontos de borda próximos desta reta.
            prox = []
            for x, y in pontos:
                d = abs(x * cos_t + y * sin_t - rho)
                if d <= 2.0:
                    prox.append((x, y))
            if len(prox) < 8:
                continue
            # Projeta no eixo da reta para achar as extremidades.
            dx, dy = -sin_t, cos_t
            proj = [(x * dx + y * dy, x, y) for x, y in prox]
            proj.sort()
            _, x1, y1 = proj[0]
            _, x2, y2 = proj[-1]
            comprimento = math.hypot(x2 - x1, y2 - y1)
            if comprimento < 10:
                continue
            linhas.append({
                "rho": rho, "theta": theta, "votos": votos,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "comprimento": comprimento,
            })
        return linhas
    except Exception as exc:
        _erro(f"hough_linhas: {exc}")
        return []


def _dif_angulo(a, b):
    """Diferença angular mínima em [0,180)."""
    d = abs((a - b) % 180)
    return min(d, 180 - d)


def _filtrar_grupo_dominante(linhas, tolerancia=10.0):
    """Mantém o grupo angular com maior comprimento total.

    O Hough vota também nas bordas superior/inferior da imagem e em diagonais
    espúrias. O grupo dominante é o feixe de linhas de plantio; os demais são
    ruído de borda.
    """
    try:
        if not linhas:
            return []
        melhor, melhor_score = [], -1.0
        for base in linhas:
            grupo = [l for l in linhas
                     if _dif_angulo(l["theta"], base["theta"]) <= tolerancia]
            score = sum(l["comprimento"] for l in grupo)
            if score > melhor_score:
                melhor_score, melhor = score, grupo
        return melhor
    except Exception as exc:
        _erro(f"_filtrar_grupo_dominante: {exc}")
        return linhas


def _deduplicar(linhas, tolerancia=DISTANCIA_TOLERANCIA):
    """Mantém uma reta por (ângulo, rho); linhas vizinhas ficam se o rho difere.

    Comparar somente extremidades deixava passar o mesmo feixe votado em
    ângulos vizinhos (0°, 2°, 4°...), que era a origem de centenas de linhas
    repetidas. O par (theta, rho) é a identidade geométrica da reta.
    """
    saida = []
    for linha in sorted(linhas, key=lambda l: l["comprimento"], reverse=True):
        igual = False
        for outra in saida:
            if (abs(linha["theta"] - outra["theta"]) <= 5
                    and abs(linha["rho"] - outra["rho"]) <= tolerancia):
                igual = True
                break
        if not igual:
            saida.append(linha)
    return saida


def _espacamento(linhas):
    """Mediana da distância entre retas do grupo angular dominante."""
    try:
        if len(linhas) < 2:
            return 0.0
        melhor = []
        for linha in linhas:
            grupo = [l for l in linhas
                     if abs(l["theta"] - linha["theta"]) <= ANGULO_TOLERANCIA]
            if len(grupo) > len(melhor):
                melhor = grupo
        rhos = sorted({l["rho"] for l in melhor})
        difs = [b - a for a, b in zip(rhos, rhos[1:]) if b - a > 1]
        if not difs:
            return 0.0
        difs.sort()
        return float(difs[len(difs) // 2])
    except Exception:
        return 0.0


# =============================================================================
# Análise e saída
# =============================================================================

def detectar_linhas_plantio(caminho, max_lado=MAX_LADO, limiar=LIMIAR_VOTOS):
    """Detecta linhas de plantio e devolve métricas/segmentos.

    Saída: dicionário com `linhas`, `angulo_dominante`, `espacamento_px`,
    `vegetacao_ratio`, `convex_hull`, `limiar`, `largura`, `altura`.
    """
    try:
        carregado = avaliacao_imagens.carregar_pixels(
            caminho, max_lado=max_lado)
        if not carregado:
            return {}
        largura, altura, pixels, passo, fonte = carregado
        mask, limiar_veg, _exg = mascara_vegetacao(pixels)
        if not mask:
            return {}
        mask = limpar_mascara(mask, largura, altura)
        pontos_mask = [(i % largura, i // largura)
                       for i, v in enumerate(mask) if v][::2]
        hull = convex_hull(pontos_mask)
        bordas = bordas_sobel(mask, largura, altura)
        limiar_efetivo = max(int(limiar), int(0.15 * max(largura, altura)))
        linhas = hough_linhas(
            bordas, largura, altura, limiar=limiar_efetivo)
        minimo = max(10.0, 0.30 * max(largura, altura))
        linhas = [l for l in linhas if l["comprimento"] >= minimo]
        # A orientação da máscara (PCA) diz a direção das fileiras; o Hough
        # usa o ângulo da NORMAL, então a linha de plantio está em
        # (orientação - 90°). Filtrar por essa referência elimina o feixe
        # diagonal que cruza várias fileiras e vence por comprimento.
        angulo_mascara = _pca_angulo(pontos_mask)
        alvo = (angulo_mascara - 90.0) % 180.0
        por_orientacao = [l for l in linhas
                          if _dif_angulo(l["theta"], alvo) <= 6.0]
        linhas = (por_orientacao if por_orientacao
                  else _filtrar_grupo_dominante(linhas))
        linhas = _deduplicar(linhas, tolerancia=6.0)
        if hull:
            linhas = [l for l in linhas
                      if _ponto_em_poligono(
                          (l["x1"] + l["x2"]) / 2,
                          (l["y1"] + l["y2"]) / 2, hull)]
        angulos = [l["theta"] % 180 for l in linhas]
        angulo = 0.0
        if angulos:
            angulos.sort()
            angulo = angulos[len(angulos) // 2]
        return {
            "largura": largura,
            "altura": altura,
            "passo_amostragem": passo,
            "fonte": fonte,
            "limiar_vegetacao": limiar_veg,
            "vegetacao_ratio": sum(mask) / max(1, len(mask)),
            "convex_hull": hull,
            "linhas": linhas,
            "total_linhas": len(linhas),
            "angulo_dominante": angulo,
            "angulo_mascara": _pca_angulo(pontos_mask),
            "espacamento_px": _espacamento(linhas),
            "comprimento_medio": (
                sum(l["comprimento"] for l in linhas) / len(linhas)
                if linhas else 0.0),
        }
    except Exception as exc:
        _erro(f"detectar_linhas_plantio('{caminho}'): {exc}")
        return {}


def anotar_imagem(caminho, resultado, saida):
    """Desenha as linhas detectadas sobre a imagem (Pillow, só saída)."""
    try:
        from PIL import Image, ImageDraw
        with Image.open(caminho) as img:
            img = img.convert("RGB")
            img.thumbnail((resultado.get("largura") or 1024,
                           resultado.get("altura") or 1024))
            draw = ImageDraw.Draw(img)
            for linha in resultado.get("linhas") or []:
                draw.line(
                    (linha["x1"], linha["y1"], linha["x2"], linha["y2"]),
                    fill=(255, 0, 0), width=2)
            os.makedirs(os.path.dirname(os.path.abspath(saida)),
                        exist_ok=True)
            img.save(saida)
            return saida
    except Exception as exc:
        _erro(f"anotar_imagem('{saida}'): {exc}")
        return None


def exportar_geojson(resultado, saida, geotransform=None):
    """Exporta as linhas como GeoJSON LineString (coordenadas de pixel/geo)."""
    try:
        x0, y0, dx, dy = geotransform or (0.0, 0.0, 1.0, 1.0)
        feicoes = []
        for linha in resultado.get("linhas") or []:
            coords = [
                [x0 + linha["x1"] * dx, y0 + linha["y1"] * dy],
                [x0 + linha["x2"] * dx, y0 + linha["y2"] * dy],
            ]
            feicoes.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "comprimento": linha["comprimento"],
                    "theta": linha["theta"],
                    "votos": linha["votos"],
                },
            })
        dados = {"type": "FeatureCollection", "features": feicoes}
        os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
        Path(saida).write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        return saida
    except Exception as exc:
        _erro(f"exportar_geojson('{saida}'): {exc}")
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Detecta linhas de plantio em imagem de drone.")
    parser.add_argument("imagem", help="imagem aérea (PNG/BMP/PPM/JPEG)")
    parser.add_argument("--out", default="linhas_plantio",
                        help="diretório de saída")
    parser.add_argument("--max-lado", type=int, default=MAX_LADO)
    parser.add_argument("--geotransform", nargs=4, type=float,
                        metavar=("X0", "Y0", "DX", "DY"))
    args = parser.parse_args(argv)
    resultado = detectar_linhas_plantio(
        args.imagem, max_lado=args.max_lado)
    if not resultado:
        print("Nenhuma linha detectada.")
        return 1
    os.makedirs(args.out, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.imagem))[0]
    json_path = os.path.join(args.out, f"{base}_linhas.json")
    Path(json_path).write_text(
        json.dumps({k: v for k, v in resultado.items()
                    if k != "convex_hull"}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    geojson = exportar_geojson(
        resultado, os.path.join(args.out, f"{base}_linhas.geojson"),
        geotransform=args.geotransform)
    anotado = anotar_imagem(
        args.imagem, resultado, os.path.join(args.out, f"{base}_anotado.png"))
    print(f"linhas: {resultado['total_linhas']} | "
          f"angulo: {resultado['angulo_dominante']:.1f}° | "
          f"espacamento: {resultado['espacamento_px']:.1f}px")
    print(f"JSON: {json_path}")
    if geojson:
        print(f"GeoJSON: {geojson}")
    if anotado:
        print(f"Anotado: {anotado}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
