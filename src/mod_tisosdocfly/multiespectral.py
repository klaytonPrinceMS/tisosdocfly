"""Processamento multiespectral em Python (bandas, índices, estatísticas, GeoTIFF).

Baseado em SOARES et al. (2022), Embrapa Semiárido — "Desenvolvimento de
scripts em Python para processamento de imagens aéreas obtidas com drones":
análise por banda, NDVI/SAVI e outros índices, histogramas, estatísticas
(média, mínima, máxima, mediana, variância, desvio-padrão), exportação
GeoTIFF e recorte por área de interesse (AOI).

O que este módulo NÃO faz: alinhamento, nuvem de pontos, DSM/DTM e
ortomosaico — essas etapas são de fotogrametria (ODM/Metashape) e entram como
produto de entrada. Aqui tratamos o ortomosaico/bandas já alinhados.

Limite de memória: as bandas são amostradas para no máximo `MAX_LADO`
(1024 px no maior lado) por padrão. Para laudo de precisão em resolução
nativa, use rasterio/GDAL (o módulo aceita os mesmos arquivos).
"""
import argparse
import json
import math
import os
import re
import struct
from pathlib import Path

from mod_tisosdocfly import avaliacao_imagens

MAX_LADO = 1024
EPS = 1e-9

# Aliases de nome de banda (sufixo do arquivo ou chave explícita).
BANDAS = {
    "R": ("r", "red", "vermelho", "b4"),
    "G": ("g", "green", "verde", "b3"),
    "B": ("b", "blue", "azul", "b2"),
    "NIR": ("nir", "infravermelho", "b5", "n"),
    "RE": ("re", "rededge", "red_edge", "borda_vermelho", "b6"),
    "T": ("t", "thermal", "termal", "termica", "b7"),
}

INDICES = ("NDVI", "SAVI", "OSAVI", "NDRE", "GNDVI", "NDWI", "EVI")
_SAVI_L = 0.5
_EVI_G = 2.5
_EVI_C1 = 6.0
_EVI_C2 = 7.5
_EVI_L = 1.0


def _log():
    try:
        from mod_tisosdocfly import observabilidade
        return observabilidade.get_logger("tisosdocfly")
    except Exception:
        import logging
        return logging.getLogger("multiespectral")


def _erro(msg):
    try:
        _log().exception(msg)
    except Exception:
        pass


# =============================================================================
# Leitura de bandas
# =============================================================================

def carregar_banda(caminho, max_lado=MAX_LADO):
    """Carrega uma banda como lista de floats em [0,1].

    PNG/BMP/PPM 8 bits: decode puro do `avaliacao_imagens`. TIFF/16 bits/JPEG:
    Pillow apenas para ler os pixels; a conta é nossa. Devolve
    `(largura, altura, valores)` ou None.
    """
    try:
        if not caminho:
            return None
        ext = os.path.splitext(str(caminho))[1].lower()
        if ext in (".png", ".bmp", ".ppm"):
            carregado = avaliacao_imagens.carregar_pixels(
                caminho, max_lado=max_lado)
            if carregado:
                largura, altura, pixels, _passo, _fonte = carregado
                return largura, altura, [p[0] / 255.0 for p in pixels]
        # TIFF/JPEG/16 bits: Pillow só decodifica.
        from PIL import Image
        with Image.open(caminho) as img:
            img.thumbnail((max_lado, max_lado))
            modo = img.mode
            if modo not in ("L", "I", "I;16", "I;16B", "F"):
                img = img.convert("L")
            largura, altura = img.size
            dados = list(img.getdata())
            if modo in ("I", "I;16", "I;16B"):
                maximo = max(dados) if dados else 1
                escala = float(maximo or 1)
            elif modo == "F":
                maximo = max(dados) if dados else 1.0
                escala = float(maximo or 1.0)
            else:
                escala = 255.0
            return largura, altura, [float(v) / escala for v in dados]
    except Exception as exc:
        _erro(f"carregar_banda('{caminho}'): {exc}")
        return None


def _normalizar_chave(chave):
    bruto = re.sub(r"[^a-z0-9_]+", "", str(chave or "").lower())
    for canonica, aliases in BANDAS.items():
        if bruto == canonica.lower() or bruto in aliases:
            return canonica
    return None


def identificar_banda(nome):
    """Descobre a banda pelo nome do arquivo (`voo_R.tif`, `voo_NIR.tif`)."""
    try:
        base = os.path.splitext(os.path.basename(str(nome)))[0]
        partes = re.split(r"[_\-. ]+", base)
        for parte in reversed(partes):
            chave = _normalizar_chave(parte)
            if chave:
                return chave
        return None
    except Exception:
        return None


def agrupar_bandas(diretorio):
    """Agrupa arquivos por base removendo o sufixo de banda.

    `voo1_R.png`, `voo1_NIR.png` → `{"voo1": {"R": path, "NIR": path}}`.
    """
    grupos = {}
    try:
        for arquivo in sorted(Path(diretorio).iterdir()):
            if not arquivo.is_file():
                continue
            banda = identificar_banda(arquivo.name)
            if not banda:
                continue
            base = os.path.splitext(arquivo.name)[0]
            base = re.sub(
                r"[_\-. ]+(r|red|vermelho|g|green|verde|b|blue|azul|nir|"
                r"infravermelho|n|re|rededge|red_edge|borda_vermelho|t|"
                r"thermal|termal|termica|b[2-7])+$",
                "", base, flags=re.IGNORECASE) or base
            grupos.setdefault(base, {})[banda] = str(arquivo)
    except Exception as exc:
        _erro(f"agrupar_bandas('{diretorio}'): {exc}")
    return grupos


def carregar_bandas(arquivos):
    """Carrega um dict {banda: caminho} e alinha na menor dimensão."""
    try:
        carregadas = {}
        for chave, caminho in (arquivos or {}).items():
            banda = _normalizar_chave(chave) or chave
            dados = carregar_banda(caminho)
            if dados:
                carregadas[banda] = dados
        if not carregadas:
            return {}
        largura = min(d[0] for d in carregadas.values())
        altura = min(d[1] for d in carregadas.values())
        saida = {}
        for banda, (l, a, valores) in carregadas.items():
            if l == largura and a == altura:
                saida[banda] = valores
            else:
                # Reamostra por vizinho mais próximo para a grade comum.
                novo = []
                for y in range(altura):
                    sy = min(a - 1, int(y * a / altura))
                    for x in range(largura):
                        sx = min(l - 1, int(x * l / largura))
                        novo.append(valores[sy * l + sx])
                saida[banda] = novo
        return {"largura": largura, "altura": altura, "bandas": saida}
    except Exception as exc:
        _erro(f"carregar_bandas: {exc}")
        return {}


# =============================================================================
# Índices e estatísticas
# =============================================================================

def _indice(nome, b, i):
    r = b.get("R", [0.0] * len(b.get("NIR", [])))
    g = b.get("G", r)
    bl = b.get("B", r)
    nir = b.get("NIR", r)
    re = b.get("RE", r)
    try:
        if nome == "NDVI":
            return (nir[i] - r[i]) / (nir[i] + r[i] + EPS)
        if nome == "SAVI":
            return ((nir[i] - r[i]) / (nir[i] + r[i] + _SAVI_L + EPS)
                    * (1.0 + _SAVI_L))
        if nome == "OSAVI":
            return (nir[i] - r[i]) / (nir[i] + r[i] + 0.16 + EPS)
        if nome == "NDRE":
            return (nir[i] - re[i]) / (nir[i] + re[i] + EPS)
        if nome == "GNDVI":
            return (nir[i] - g[i]) / (nir[i] + g[i] + EPS)
        if nome == "NDWI":
            return (g[i] - nir[i]) / (g[i] + nir[i] + EPS)
        if nome == "EVI":
            den = nir[i] + _EVI_C1 * r[i] - _EVI_C2 * bl[i] + _EVI_L
            return _EVI_G * (nir[i] - r[i]) / (den + EPS)
    except Exception:
        return 0.0
    return 0.0


def calcular_indices(dados, nomes=INDICES):
    """Calcula um dict {índice: [valores]} sobre as bandas carregadas."""
    try:
        bandas = (dados or {}).get("bandas") or {}
        n = len(next(iter(bandas.values()))) if bandas else 0
        if not n:
            return {}
        return {nome: [_indice(nome, bandas, i) for i in range(n)]
                for nome in nomes}
    except Exception as exc:
        _erro(f"calcular_indices: {exc}")
        return {}


def estatisticas(valores):
    """Média, mínima, máxima, mediana, variância, desvio e histograma."""
    try:
        vals = [float(v) for v in (valores or []) if math.isfinite(float(v))]
        if not vals:
            return {}
        vals_ord = sorted(vals)
        n = len(vals)
        media = sum(vals) / n
        var = sum((v - media) ** 2 for v in vals) / n
        mediana = (vals_ord[n // 2] if n % 2 else
                   (vals_ord[n // 2 - 1] + vals_ord[n // 2]) / 2.0)
        hist = [0] * 16
        for v in vals:
            idx = min(15, max(0, int((v + 1.0) / 2.0 * 16)))
            hist[idx] += 1
        return {
            "n": n,
            "media": media,
            "minima": vals_ord[0],
            "maxima": vals_ord[-1],
            "mediana": mediana,
            "variancia": var,
            "desvio_padrao": math.sqrt(var),
            "p10": vals_ord[int(0.10 * (n - 1))],
            "p90": vals_ord[int(0.90 * (n - 1))],
            "histograma": hist,
        }
    except Exception as exc:
        _erro(f"estatisticas: {exc}")
        return {}


# =============================================================================
# AOI (GeoJSON; shapefile opcional)
# =============================================================================

def _ponto_em_anel(x, y, anel):
    dentro = False
    j = len(anel) - 1
    for i in range(len(anel)):
        xi, yi = anel[i]
        xj, yj = anel[j]
        if ((yi > y) != (yj > y)) and \
                (x < (xj - xi) * (y - yi) / (yj - yi + EPS) + xi):
            dentro = not dentro
        j = i
    return dentro


def ler_aoi(caminho):
    """Lê um AOI GeoJSON (.geojson/.json) ou shapefile (se `pyshp` existir).

    Devolve uma lista de polígonos, cada um uma lista de anéis [(x,y), ...].
    """
    try:
        ext = os.path.splitext(str(caminho))[1].lower()
        if ext in (".geojson", ".json"):
            dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
            feicoes = (dados.get("features")
                       if dados.get("type") == "FeatureCollection"
                       else [dados])
            poligonos = []
            for feicao in feicoes:
                geom = feicao.get("geometry", feicao)
                if geom.get("type") == "Polygon":
                    poligonos.append(geom.get("coordinates") or [])
                elif geom.get("type") == "MultiPolygon":
                    poligonos.extend(geom.get("coordinates") or [])
            return poligonos
        if ext == ".shp":
            import shapefile  # pyshp opcional
            leitor = shapefile.Reader(str(caminho))
            poligonos = []
            for forma in leitor.shapes():
                pontos = forma.points
                partes = list(forma.parts) + [len(pontos)]
                aneis = [pontos[partes[i]:partes[i + 1]]
                         for i in range(len(partes) - 1)]
                if aneis:
                    poligonos.append(aneis)
            return poligonos
    except Exception as exc:
        _erro(f"ler_aoi('{caminho}'): {exc}")
    return []


def mascara_aoi(largura, altura, poligonos, geotransform=None):
    """Máscara booleana por pixel; geotransform=(x0, y0, dx, dy)."""
    try:
        if not poligonos:
            return None
        x0, y0, dx, dy = geotransform or (0.0, 0.0, 1.0, 1.0)
        mascara = bytearray(largura * altura)
        for y in range(altura):
            my = y0 + (y + 0.5) * dy
            for x in range(largura):
                mx = x0 + (x + 0.5) * dx
                dentro = False
                for poligono in poligonos:
                    if not poligono:
                        continue
                    if _ponto_em_anel(mx, my, poligono[0]):
                        # furos
                        dentro = not any(
                            _ponto_em_anel(mx, my, furo)
                            for furo in poligono[1:])
                        if dentro:
                            break
                if dentro:
                    mascara[y * largura + x] = 1
        return mascara
    except Exception as exc:
        _erro(f"mascara_aoi: {exc}")
        return None


def _filtrar(valores, mascara):
    if not mascara:
        return valores
    return [v for v, m in zip(valores, mascara) if m]


# =============================================================================
# GeoTIFF
# =============================================================================

def exportar_geotiff(valores, largura, altura, caminho,
                     geotransform=None):
    """Exporta um índice como GeoTIFF float32 (Pillow + tags GeoTIFF).

    `geotransform=(x0, y0, dx, dy)` opcional. Sem geotransform, gera TIFF
    comum (a imagem não fica georreferenciada).
    """
    try:
        from PIL import Image
        destino = str(caminho)
        if not destino.lower().endswith((".tif", ".tiff")):
            destino += ".tif"
        os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
        img = Image.new("F", (int(largura), int(altura)))
        img.putdata([float(v) for v in valores])
        info = {}
        if geotransform:
            x0, y0, dx, dy = [float(v) for v in geotransform]
            # Tags GeoTIFF mínimas: PixelScale, Tiepoint e GeoKeyDirectory.
            info["tiffinfo"] = {
                33550: (dx, abs(dy), 0.0),
                33922: (0.0, 0.0, 0.0, x0, y0, 0.0),
                34735: (1, 1, 0, 3, 1024, 0, 1, 2, 1025, 0, 1, 1,
                        2048, 0, 1, 1),
            }
        img.save(destino, format="TIFF", **info)
        return destino
    except Exception as exc:
        _erro(f"exportar_geotiff('{caminho}'): {exc}")
        return None


# =============================================================================
# Processamento
# =============================================================================

def processar_bandas(arquivos, aoi=None, geotransform=None,
                     nomes=INDICES):
    """Processa bandas e devolve estatísticas por banda e por índice."""
    try:
        dados = carregar_bandas(arquivos)
        if not dados:
            return {}
        largura, altura = dados["largura"], dados["altura"]
        bandas = dados["bandas"]
        mascara = None
        if aoi:
            poligonos = ler_aoi(aoi) if isinstance(aoi, (str, Path)) else aoi
            mascara = mascara_aoi(largura, altura, poligonos, geotransform)
        stats_bandas = {
            nome: estatisticas(_filtrar(vals, mascara))
            for nome, vals in bandas.items()
        }
        indices = calcular_indices(dados, nomes)
        stats_indices = {
            nome: estatisticas(_filtrar(vals, mascara))
            for nome, vals in indices.items()
        }
        return {
            "largura": largura,
            "altura": altura,
            "bandas": list(bandas),
            "estatisticas_bandas": stats_bandas,
            "indices": list(indices),
            "estatisticas_indices": stats_indices,
            "valores_indices": indices,
            "mascara": mascara,
            "fonte": "python-puro",
        }
    except Exception as exc:
        _erro(f"processar_bandas: {exc}")
        return {}


def processar_diretorio(diretorio, saida=None, aoi=None,
                        geotransform=None, nomes=INDICES):
    """Processa todos os grupos de bandas de um diretório.

    Grava, por grupo: `<base>_indices.json`, `<base>_NDVI.tif`,
    `<base>_SAVI.tif`. Devolve um resumo por grupo.
    """
    resumo = {}
    try:
        grupos = agrupar_bandas(diretorio)
        saida = saida or os.path.join(str(diretorio), "indices")
        os.makedirs(saida, exist_ok=True)
        for base, arquivos in grupos.items():
            if not ({"R", "NIR"} <= set(arquivos)):
                resumo[base] = {"erro": "faltam bandas R/NIR",
                                "bandas": sorted(arquivos)}
                continue
            resultado = processar_bandas(
                arquivos, aoi=aoi, geotransform=geotransform, nomes=nomes)
            if not resultado:
                resumo[base] = {"erro": "processamento falhou"}
                continue
            json_path = os.path.join(saida, f"{base}_indices.json")
            exportavel = {
                "largura": resultado["largura"],
                "altura": resultado["altura"],
                "bandas": resultado["bandas"],
                "estatisticas_bandas": resultado["estatisticas_bandas"],
                "indices": resultado["indices"],
                "estatisticas_indices": resultado["estatisticas_indices"],
            }
            try:
                Path(json_path).write_text(
                    json.dumps(exportavel, ensure_ascii=False, indent=2),
                    encoding="utf-8")
            except Exception as exc:
                _erro(f"processar_diretorio: JSON {base}: {exc}")
            tiffs = {}
            for nome in ("NDVI", "SAVI", "NDRE", "GNDVI", "NDWI"):
                valores = (resultado.get("valores_indices") or {}).get(nome)
                if not valores:
                    continue
                caminho = os.path.join(saida, f"{base}_{nome}.tif")
                tif = exportar_geotiff(
                    valores, resultado["largura"], resultado["altura"],
                    caminho, geotransform=geotransform)
                if tif:
                    tiffs[nome] = tif
            resumo[base] = {
                "json": json_path,
                "tiffs": tiffs,
                "bandas": resultado["bandas"],
                "indices": resultado["indices"],
                "estatisticas_indices": resultado["estatisticas_indices"],
            }
        return resumo
    except Exception as exc:
        _erro(f"processar_diretorio('{diretorio}'): {exc}")
        return resumo


# =============================================================================
# CLI
# =============================================================================

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Processa bandas multiespectrais e gera índices/GeoTIFF.")
    parser.add_argument("--r", "--red", dest="r", help="banda vermelha")
    parser.add_argument("--g", "--green", dest="g", help="banda verde")
    parser.add_argument("--b", "--blue", dest="b", help="banda azul")
    parser.add_argument("--nir", dest="nir", help="banda infravermelho próximo")
    parser.add_argument("--re", "--red-edge", dest="re",
                        help="banda red edge")
    parser.add_argument("--aoi", help="GeoJSON ou shapefile de recorte")
    parser.add_argument("--out", default="indices",
                        help="diretório de saída")
    parser.add_argument("--dir", help="processa um diretório inteiro")
    parser.add_argument("--geotransform", nargs=4, type=float,
                        metavar=("X0", "Y0", "DX", "DY"))
    args = parser.parse_args(argv)
    if args.dir:
        resumo = processar_diretorio(
            args.dir, saida=args.out, aoi=args.aoi,
            geotransform=args.geotransform)
        print(json.dumps(resumo, ensure_ascii=False, indent=2))
        return 0 if resumo else 1
    arquivos = {k: v for k, v in (
        ("R", args.r), ("G", args.g), ("B", args.b),
        ("NIR", args.nir), ("RE", args.re)) if v}
    if not arquivos:
        parser.print_help()
        return 2
    resultado = processar_bandas(
        arquivos, aoi=args.aoi, geotransform=args.geotransform)
    if not resultado:
        print("Nenhum resultado.")
        return 1
    os.makedirs(args.out, exist_ok=True)
    json_path = os.path.join(args.out, "indices.json")
    Path(json_path).write_text(
        json.dumps({
            "largura": resultado["largura"],
            "altura": resultado["altura"],
            "estatisticas_bandas": resultado["estatisticas_bandas"],
            "estatisticas_indices": resultado["estatisticas_indices"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {json_path}")
    for nome in ("NDVI", "SAVI", "NDRE", "GNDVI", "NDWI"):
        valores = (resultado.get("valores_indices") or {}).get(nome)
        if valores:
            caminho = exportar_geotiff(
                valores, resultado["largura"], resultado["altura"],
                os.path.join(args.out, f"{nome}.tif"),
                geotransform=args.geotransform)
            if caminho:
                print(f"{nome}: {caminho}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
