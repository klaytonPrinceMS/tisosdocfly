# -*- coding: utf-8 -*-
"""Prova a detecção de linhas de plantio (Hough em Python puro).

Baseado no vídeo do GeoIA Aplicada: máscara de vegetação, envelope, morfologia,
Sobel, Hough, ângulo/espaçamento e GeoJSON. Não prova acurácia em campo.
"""
import json
import os
import struct
import sys
import unittest
import zlib

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
os.environ.setdefault("SKYROVER_DIR_BANCO", "/tmp/opencode/bd_linhas")
os.environ.setdefault("SKYROVER_DIR_MIDIA", "/tmp/opencode/linhas_plantio/midia")

from mod_skyrover import linhas_plantio as lp

TMP = "/tmp/opencode/linhas_plantio"


def _png(largura, altura, pixel_fn, caminho):
    raw = bytearray()
    for y in range(altura):
        raw.append(0)
        for x in range(largura):
            raw.extend(pixel_fn(x, y))

    def chunk(tipo, corpo):
        return (struct.pack(">I", len(corpo)) + tipo + corpo
                + struct.pack(">I", zlib.crc32(tipo + corpo) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    dados = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
             + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
             + chunk(b"IEND", b""))
    with open(caminho, "wb") as f:
        f.write(dados)


def _listras(x, y):
    # Faixas verdes verticais (8 px) sobre solo marrom.
    return (40, 170, 55) if (x // 8) % 2 else (95, 70, 35)


def _listras_horizontais(x, y):
    return (40, 170, 55) if (y // 8) % 2 else (95, 70, 35)


class TestLinhasPlantio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(TMP, exist_ok=True)
        cls.vertical = os.path.join(TMP, "vertical.png")
        cls.horizontal = os.path.join(TMP, "horizontal.png")
        _png(128, 128, _listras, cls.vertical)
        _png(128, 128, _listras_horizontais, cls.horizontal)

    def test_detecta_linhas_verticais(self):
        r = lp.detectar_linhas_plantio(self.vertical, max_lado=128)
        self.assertTrue(r)
        self.assertGreaterEqual(r["total_linhas"], 4)
        self.assertGreater(r["vegetacao_ratio"], 0.2)
        self.assertGreater(r["espacamento_px"], 0)
        self.assertLessEqual(r["angulo_dominante"], 180)

    def test_detecta_linhas_horizontais(self):
        r = lp.detectar_linhas_plantio(self.horizontal, max_lado=128)
        self.assertTrue(r)
        self.assertGreaterEqual(r["total_linhas"], 4)
        # Linhas horizontais ficam perto de 90° no Hough.
        self.assertTrue(60 <= r["angulo_dominante"] <= 120
                        or r["angulo_dominante"] <= 20
                        or r["angulo_dominante"] >= 160)

    def test_integracao_com_voo(self):
        from mod_skyrover.bd_criador import inicializar_bancos
        from mod_skyrover import voos
        inicializar_bancos()
        c = voos.criar_cliente("Cliente Linhas", ator="teste")
        p = voos.criar_propriedade(c, "Talhão Linhas", ator="teste")
        v = voos.criar_voo(c, p, data_voo="2026-11-02", ator="teste")
        with open(self.vertical, "rb") as f:
            voos.salvar_arquivo_midia(
                v, "vertical.png", f.read(), mime="image/png", ator="teste")
        resultados = voos.detectar_linhas_plantio(
            v, ator="teste", max_imagens=1, max_lado=128)
        self.assertTrue(resultados)
        self.assertGreater(
            resultados[0]["resultado"]["total_linhas"], 0)

    def test_exporta_geojson_e_anotado(self):
        r = lp.detectar_linhas_plantio(self.vertical, max_lado=128)
        geojson = os.path.join(TMP, "linhas.geojson")
        anotado = os.path.join(TMP, "anotado.png")
        self.assertTrue(lp.exportar_geojson(r, geojson))
        self.assertTrue(lp.anotar_imagem(self.vertical, r, anotado))
        with open(geojson, encoding="utf-8") as f:
            dados = json.load(f)
        self.assertEqual(dados["type"], "FeatureCollection")
        self.assertGreaterEqual(len(dados["features"]), 1)
        self.assertTrue(os.path.isfile(anotado))


if __name__ == "__main__":
    unittest.main(verbosity=2)
