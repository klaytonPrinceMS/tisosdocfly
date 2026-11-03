"""Basic RGB metrics, vegetation indices, GSD and thumbnails for drone imagery.

Leitura e análise determinística de imagens de voo de qualquer drone: RGB, brilho,
contraste, saturação, proporções de cor, densidade de borda, índices de
vegetação RGB, cálculo de GSD (ground sample distance) e miniatura.

Nada aqui depende de modelo treinado: são medidas de pixel, reprodutíveis e
auditáveis, usadas pelo baseline do módulo `ia`. As dependências obrigatórias
são `numpy` e `Pillow`; `rasterio` é OPCIONAL e só habilita `ler_geotiff`.
"""
import math
import os

import numpy as np
from PIL import Image

_MODULO_LOG = "tisosdocfly"
_EPS = 1e-6

# Limiares do baseline. Ficam nomeados para a documentação e para o teste
# conseguir explicar por que uma ocorrência disparou.
LIMIAR_VERDE_EXG = 0.10      # ExG acima disto = pixel de vegetação
LIMIAR_BORDA = 0.08          # gradiente (0..1) acima disto = borda
LIMIAR_ESCURO = 0.20         # luminância abaixo disto = pixel escuro
LIMIAR_CINZA_SAT = 0.12      # saturação abaixo disto = pixel cinza
LADO_MAXIMO_ANALISE = 1024   # amostragem máxima por lado (desempenho)


def _log():
    """Logger loguru do núcleo; nunca falha por causa da observabilidade."""
    try:
        from mod_tisosdocfly import observabilidade
        return observabilidade.get_logger(_MODULO_LOG)
    except Exception:
        from loguru import logger
        return logger


def _erro(contexto, exc):
    """Registra a causa sem derrubar o chamador."""
    try:
        _log().exception(f"geoprocessamento.{contexto}: {exc}")
    except Exception:
        pass


def carregar_rgb(caminho):
    """Loads an image as an HxWx3 float32 array normalized to [0, 1].

    Converte qualquer formato suportado pelo Pillow para RGB e devolve
    `numpy.ndarray` com shape `(altura, largura, 3)` e valores em `[0, 1]`.
    Retorna `None` quando o caminho não existe, não é imagem ou a leitura
    falha. A normalização em `[0, 1]` é o que mantém as fórmulas de índice
    independentes do tipo do arquivo (8/16 bits).
    """
    try:
        if not caminho or not os.path.isfile(str(caminho)):
            return None
        with Image.open(caminho) as imagem:
            rgb = imagem.convert("RGB")
            arr = np.asarray(rgb, dtype=np.float32) / 255.0
        if arr.ndim != 3 or arr.shape[2] != 3 or arr.size == 0:
            return None
        return arr
    except Exception as exc:
        _erro(f"carregar_rgb('{caminho}')", exc)
        return None


def _amostrar(arr, lado_maximo=LADO_MAXIMO_ANALISE):
    """Subamostra por passo inteiro para limitar custo em fotos grandes.

    O passo preserva a proporção e evita `resize` (que inventaria pixels).
    Para uma imagem de 4000 px, o passo 4 analisa 1000 px por lado.
    """
    try:
        altura, largura = arr.shape[:2]
        maior = max(altura, largura)
        passo = max(1, int(math.ceil(maior / float(lado_maximo))))
        return arr[::passo, ::passo]
    except Exception:
        return arr


def _densidade_borda(luminancia):
    """Fraction of pixels with a Sobel-like gradient above `LIMIAR_BORDA`.

    Gradiente central (diferença para os vizinhos de cada lado) em X e Y;
    a magnitude é comparada ao limiar. É a medida usada como indício de
    trinca (vistoria) e de textura/heterogeneidade (agro, obras).
    """
    try:
        if luminancia.shape[0] < 3 or luminancia.shape[1] < 3:
            return 0.0
        gx = np.zeros_like(luminancia)
        gy = np.zeros_like(luminancia)
        gx[:, 1:-1] = luminancia[:, 2:] - luminancia[:, :-2]
        gy[1:-1, :] = luminancia[2:, :] - luminancia[:-2, :]
        magnitude = np.hypot(gx, gy)
        return float(np.mean(magnitude > LIMIAR_BORDA))
    except Exception as exc:
        _erro("_densidade_borda", exc)
        return 0.0


def _metricas_de_array(arr):
    """Computes the RGB metric dictionary from a normalized HxWx3 array."""
    r = arr[..., 0]
    g = arr[..., 1]
    b = arr[..., 2]
    soma = r + g + b + _EPS
    r_c = r / soma
    g_c = g / soma
    b_c = b / soma

    luminancia = 0.299 * r + 0.587 * g + 0.114 * b
    maior = arr.max(axis=2)
    menor = arr.min(axis=2)
    saturacao = (maior - menor) / (maior + _EPS)

    exg = 2.0 * g_c - r_c - b_c
    # Marrom = solo/terra exposta, não incandescente: R dominante e abaixo do
    # brilho de fogo, G entre R e B, saturação mínima. O teto de R separa
    # terra de chama/lava (que passam de 0,78 em R).
    marrom = ((r > g) & (g > b) & (saturacao > 0.15)
              & (r > 0.20) & (r < 0.78) & (exg < 0.12))
    # Laranja de queimada: R alto de verdade e muito acima de G (razão > 1,7),
    # não o laranja terroso de solo exposto (razão ~1,2).
    laranja = ((r > 0.70) & (g > 0.15) & (g < 0.55) & (b < 0.30)
               & (r > g * 1.7) & (exg < 0.05))
    cinza = saturacao < LIMIAR_CINZA_SAT
    escuro = luminancia < LIMIAR_ESCURO

    return {
        "media_rgb": [float(r.mean()), float(g.mean()), float(b.mean())],
        "brilho": float(luminancia.mean()),
        "contraste": float(luminancia.std()),
        "saturacao_media": float(saturacao.mean()),
        "verde_ratio": float(np.mean(exg > LIMIAR_VERDE_EXG)),
        "marrom_ratio": float(np.mean(marrom)),
        "cinza_ratio": float(np.mean(cinza)),
        "escuro_ratio": float(np.mean(escuro)),
        "laranja_ratio": float(np.mean(laranja)),
        "densidade_borda": _densidade_borda(luminancia),
    }


def metricas_rgb(caminho):
    """Returns brightness, contrast, saturation, color ratios and edge density.

    Dicionário com `media_rgb` (lista R,G,B em `[0,1]`), `brilho` (luminância
    média Rec.601), `contraste` (desvio-padrão da luminância),
    `saturacao_media` (S do HSV), `verde_ratio`, `marrom_ratio`,
    `cinza_ratio`, `escuro_ratio`, `laranja_ratio` e `densidade_borda`.
    Devolve `{}` em falha de leitura.
    """
    try:
        arr = carregar_rgb(caminho)
        if arr is None:
            return {}
        return _metricas_de_array(_amostrar(arr))
    except Exception as exc:
        _erro(f"metricas_rgb('{caminho}')", exc)
        return {}


def _indices_de_array(arr):
    """Computes RGB vegetation index means plus the base metrics."""
    r = arr[..., 0]
    g = arr[..., 1]
    b = arr[..., 2]
    soma = r + g + b + _EPS
    r_c = r / soma
    g_c = g / soma
    b_c = b / soma

    # Fórmulas RGB (índices de excesso/razão), todas sobre coordenadas
    # cromáticas r=R/(R+G+B), g=G/(...), b=B/(...):
    #   ExG  = 2g - r - b                    (Woebbecke et al., 1995)
    #   VARI = (g - r) / (g + r - b)         (Gitelson et al., 2002)
    #   GLI  = (2g - r - b) / (2g + r + b)   (Louhaichi et al., 2001)
    #   TGI  = (g - r) / (g + b - r)         (Hunt et al., 2011)
    exg = 2.0 * g_c - r_c - b_c
    vari = np.clip((g_c - r_c) / (g_c + r_c - b_c + _EPS), -2.0, 2.0)
    gli = (2.0 * g_c - r_c - b_c) / (2.0 * g_c + r_c + b_c + _EPS)
    tgi = np.clip((g_c - r_c) / (g_c + b_c - r_c + _EPS), -2.0, 2.0)

    dados = _metricas_de_array(arr)
    dados.update({
        "ExG": float(exg.mean()),
        "VARI": float(vari.mean()),
        "GLI": float(gli.mean()),
        "TGI": float(tgi.mean()),
        "vegetacao_ratio": float(np.mean(exg > LIMIAR_VERDE_EXG)),
    })
    return dados


def indices_vegetacao(caminho):
    """Returns ExG, VARI, GLI and TGI means plus the base RGB metrics.

    As quatro fórmulas estão documentadas em `_indices_de_array`. Valores
    altos de ExG/GLI indicam vegetação fotossinteticamente ativa; VARI é uma
    razão (mais sensível a solo exposto) e TGI separa verde de solo/sombra.
    Devolve `{}` em falha de leitura.

    Limitação: são índices de COR, não de reflectância. Sem calibração de
    câmera/sol, servem para comparação relativa dentro do mesmo voo — nunca
    como laudo absoluto de biomassa.
    """
    try:
        arr = carregar_rgb(caminho)
        if arr is None:
            return {}
        return _indices_de_array(_amostrar(arr))
    except Exception as exc:
        _erro(f"indices_vegetacao('{caminho}')", exc)
        return {}


def gsd_cm(altitude_m, sensor_largura_mm, focal_mm, largura_px):
    """Computes ground sample distance in centimeters per pixel.

    Fórmula (triângulos semelhantes, tudo em unidades coerentes):

        GSD_m  = (altitude_m * sensor_largura_mm) / (focal_mm * largura_px)
        GSD_cm = GSD_m * 100

    `altitude_m` é a altura do drone acima do alvo (m); `sensor_largura_mm`
    é a largura física do sensor (mm); `focal_mm` é a distância focal (mm);
    `largura_px` é a largura da foto em pixels. Levanta `ValueError` para
    entrada ausente/não numérica ou não positiva — é conta pura, e devolver
    `None` esconderia erro de cadastro do voo.
    """
    try:
        altitude = float(altitude_m)
        sensor = float(sensor_largura_mm)
        focal = float(focal_mm)
        largura = float(largura_px)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "gsd_cm exige números: altitude_m, sensor_largura_mm, focal_mm "
            "e largura_px") from exc
    if not all(math.isfinite(v) for v in (altitude, sensor, focal, largura)):
        raise ValueError("gsd_cm não aceita NaN/infinito")
    if min(altitude, sensor, focal, largura) <= 0:
        raise ValueError("gsd_cm exige todos os valores positivos")
    gsd_m = (altitude * sensor) / (focal * largura)
    return gsd_m * 100.0


def gerar_thumbnail(origem, destino, tamanho=512):
    """Writes a max-`tamanho`px JPEG/PNG thumbnail keeping the aspect ratio.

    Cria a pasta de destino e converte para RGB (compatível com PNG/JPEG).
    O formato é decidido pela extensão do destino (padrão JPEG). Devolve
    `True` só quando o arquivo final existe e tem conteúdo.
    """
    try:
        if not origem or not os.path.isfile(str(origem)):
            return False
        lado = max(16, int(tamanho))
        pasta = os.path.dirname(os.path.abspath(str(destino)))
        os.makedirs(pasta, exist_ok=True)
        with Image.open(origem) as imagem:
            miniatura = imagem.convert("RGB")
            miniatura.thumbnail((lado, lado), Image.Resampling.LANCZOS)
            miniatura.save(destino)
        return os.path.isfile(destino) and os.path.getsize(destino) > 0
    except Exception as exc:
        _erro(f"gerar_thumbnail('{origem}')", exc)
        return False


def _exif_basico(imagem):
    """Extracts only non-identifying camera EXIF fields.

    Lê marca/modelo, data/hora, exposição, abertura, ISO, distância focal e
    presença de GPS — nunca as coordenadas em si. Nome/telefone/CPF não
    existem em EXIF de câmera; GPS fica só como booleano para preservar a
    privacidade do dado bruto.
    """
    try:
        from PIL.ExifTags import TAGS
        bruto = imagem.getexif()
        if not bruto:
            return {}
        interessantes = {
            "Make", "Model", "DateTime", "DateTimeOriginal",
            "ExposureTime", "FNumber", "ISOSpeedRatings",
            "FocalLength", "ExifImageWidth", "ExifImageHeight",
        }
        dados = {}
        for tag_id, valor in bruto.items():
            nome = TAGS.get(tag_id, str(tag_id))
            if nome in interessantes:
                if isinstance(valor, bytes):
                    valor = valor.decode("utf-8", "ignore")
                dados[nome] = str(valor)[:120]
        dados["gps_presente"] = bool(bruto.get_ifd(0x8825))
        return dados
    except Exception as exc:
        _erro("_exif_basico", exc)
        return {}


def estatisticas_imagem(caminho):
    """Returns width, height, mode and basic EXIF metadata via Pillow.

    Dicionário com `largura`, `altura`, `modo` e `exif_basico` (dict). Não
    depende de `piexif`; `exif_basico` fica vazio quando a imagem não tem
    EXIF ou o parser falha. Retorna `{}` quando o arquivo não abre.
    """
    try:
        if not caminho or not os.path.isfile(str(caminho)):
            return {}
        with Image.open(caminho) as imagem:
            largura, altura = imagem.size
            return {
                "largura": int(largura),
                "altura": int(altura),
                "modo": str(imagem.mode),
                "exif_basico": _exif_basico(imagem),
            }
    except Exception as exc:
        _erro(f"estatisticas_imagem('{caminho}')", exc)
        return {}


def ler_geotiff(caminho):
    """Reads a GeoTIFF bounds/CRS/profile when `rasterio` is installed.

    `rasterio` é dependência OPCIONAL: sem ele a função devolve `None` e o
    restante do pipeline continua funcionando só com RGB. Com ele, devolve
    `{"bounds": [minx, miny, maxx, maxy], "crs": str|None, "perfil": dict}`.
    """
    try:
        try:
            import rasterio  # noqa: WPS433 (import opcional deliberado)
        except Exception:
            return None
        if not caminho or not os.path.isfile(str(caminho)):
            return None
        with rasterio.open(caminho) as ds:
            bounds = ds.bounds
            crs = str(ds.crs) if ds.crs else None
            perfil = {
                "width": int(ds.width),
                "height": int(ds.height),
                "count": int(ds.count),
                "dtype": str(ds.dtypes[0]) if ds.dtypes else None,
                "nodata": ds.nodata,
            }
            return {
                "bounds": [float(bounds.left), float(bounds.bottom),
                           float(bounds.right), float(bounds.top)],
                "crs": crs,
                "perfil": perfil,
            }
    except Exception as exc:
        _erro(f"ler_geotiff('{caminho}')", exc)
        return None


def area_imagem_m2(largura_px, altura_px, gsd_cm_px):
    """Returns the ground area covered by an image in square meters.

    `area = largura_px * altura_px * (gsd_cm / 100) ** 2`. Devolve `0.0`
    quando GSD ou dimensões são inválidos — área desconhecida nunca vira
    número inventado.
    """
    try:
        largura = float(largura_px)
        altura = float(altura_px)
        gsd = float(gsd_cm_px)
        if min(largura, altura, gsd) <= 0:
            return 0.0
        return largura * altura * (gsd / 100.0) ** 2
    except (TypeError, ValueError):
        return 0.0
