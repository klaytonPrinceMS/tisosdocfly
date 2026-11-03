# -*- coding: utf-8 -*-
"""Prova o fluxo multiespectral baseado na Embrapa (Soares et al., 2022).

O que este teste garante: bandas R/G/B/NIR/RE são lidas, NDVI/SAVI/NDRE/
GNDVI/NDWI são calculados, estatísticas e histograma saem, o processamento
por diretório grava JSON/GeoTIFF e o AOI GeoJSON recorta a análise. Não
garante ortomosaico/DTM (fotogrametria externa).
"""
import json
import os
import struct
import sys
import unittest
import zlib

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
os.environ.setdefault("TISOSDOCFLY_DIR_BANCO", "/tmp/opencode/bd_multi")

from mod_tisosdocfly import multiespectral as ms

TMP = "/tmp/opencode/multiespectral"


def _png(valor, caminho, largura=32, altura=32):
    """PNG grayscale 8 bits com um valor constante (stdlib, sem Pillow)."""
    raw = bytearray()
    for _ in range(altura):
        raw.append(0)
        raw.extend(bytes([valor]) * largura)

    def chunk(tipo, corpo):
        return (struct.pack(">I", len(corpo)) + tipo + corpo
                + struct.pack(">I", zlib.crc32(tipo + corpo) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", largura, altura, 8, 0, 0, 0, 0)
    dados = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
             + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
             + chunk(b"IEND", b""))
    with open(caminho, "wb") as f:
        f.write(dados)


class TestMultiespectral(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(TMP, exist_ok=True)
        cls.bandas = {
            "R": os.path.join(TMP, "talhao_R.png"),
            "G": os.path.join(TMP, "talhao_G.png"),
            "B": os.path.join(TMP, "talhao_B.png"),
            "NIR": os.path.join(TMP, "talhao_NIR.png"),
            "RE": os.path.join(TMP, "talhao_RE.png"),
        }
        for banda, valor in (("R", 51), ("G", 128), ("B", 26),
                             ("NIR", 204), ("RE", 77)):
            _png(valor, cls.bandas[banda])
        cls.aoi = os.path.join(TMP, "aoi.geojson")
        with open(cls.aoi, "w", encoding="utf-8") as f:
            json.dump({
                "type": "Polygon",
                "coordinates": [[[0, 0], [16, 0], [16, 32],
                                 [0, 32], [0, 0]]],
            }, f)

    def test_carrega_bandas(self):
        dados = ms.carregar_bandas(self.bandas)
        self.assertEqual(dados["largura"], 32)
        self.assertEqual(dados["altura"], 32)
        self.assertEqual(set(dados["bandas"]), {"R", "G", "B", "NIR", "RE"})
        self.assertAlmostEqual(dados["bandas"]["NIR"][0], 204 / 255, places=2)

    def test_indices(self):
        dados = ms.carregar_bandas(self.bandas)
        idx = ms.calcular_indices(dados)
        self.assertAlmostEqual(idx["NDVI"][0], (0.8 - 0.2) / 1.0, places=2)
        self.assertAlmostEqual(idx["NDRE"][0], (0.8 - 0.3) / 1.1, places=2)
        self.assertGreater(idx["SAVI"][0], 0)
        self.assertLess(idx["NDWI"][0], 0)

    def test_estatisticas(self):
        e = ms.estatisticas([0.1, 0.2, 0.3, 0.4])
        self.assertAlmostEqual(e["media"], 0.25)
        self.assertAlmostEqual(e["mediana"], 0.25)
        self.assertEqual(e["minima"], 0.1)
        self.assertEqual(e["maxima"], 0.4)
        self.assertGreater(e["desvio_padrao"], 0)
        self.assertEqual(len(e["histograma"]), 16)

    def test_aoi_recorta(self):
        res = ms.processar_bandas(self.bandas, aoi=self.aoi)
        self.assertTrue(res)
        self.assertEqual(res["largura"], 32)
        # Metade da imagem (x < 16) deve sobrar no recorte.
        self.assertEqual(res["estatisticas_indices"]["NDVI"]["n"], 16 * 32)

    def test_processa_diretorio_e_geotiff(self):
        saida = os.path.join(TMP, "saida")
        resumo = ms.processar_diretorio(TMP, saida=saida)
        self.assertIn("talhao", resumo)
        item = resumo["talhao"]
        self.assertTrue(os.path.isfile(item["json"]))
        self.assertIn("NDVI", item["tiffs"])
        self.assertTrue(os.path.isfile(item["tiffs"]["NDVI"]))
        with open(item["json"], encoding="utf-8") as f:
            dados = json.load(f)
        self.assertIn("NDVI", dados["estatisticas_indices"])
        self.assertIn("histograma", dados["estatisticas_indices"]["NDVI"])

    def test_geotiff_com_geotransform(self):
        from PIL import Image
        valores = [0.5] * (8 * 8)
        caminho = os.path.join(TMP, "geo.tif")
        saida = ms.exportar_geotiff(
            valores, 8, 8, caminho,
            geotransform=(500000.0, 8000000.0, 0.1, -0.1))
        self.assertTrue(saida and os.path.isfile(saida))
        with Image.open(saida) as img:
            self.assertEqual(img.size, (8, 8))
            self.assertEqual(img.mode, "F")


if __name__ == "__main__":
    unittest.main(verbosity=2)
