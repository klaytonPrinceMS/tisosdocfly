# -*- coding: utf-8 -*-
"""Prova a avaliação de imagens em Python puro (stdlib).

O que este teste garante: PNG/BMP/PPM são decodificados sem numpy/Pillow,
as métricas de cor/índices/bordas respondem a imagens sintéticas conhecidas e
o `ia.analisar_imagem` usa o modelo `avaliacao-pura-v1` por padrão. Não
garante precisão agronômica nem substitui modelo homologado.
"""
import os
import struct
import sys
import unittest
import zlib

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
os.environ.setdefault("TISOSDOCFLY_DIR_BANCO", "/tmp/opencode/bd_puro")

from mod_tisosdocfly import avaliacao_imagens, ia

TMP = "/tmp/opencode/avaliacao_pura"


def _png(largura, altura, pixels, caminho):
    """Escreve um PNG RGB 8 bits com stdlib (sem Pillow)."""
    raw = bytearray()
    for y in range(altura):
        raw.append(0)  # filtro None
        for x in range(largura):
            r, g, b = pixels[y * largura + x]
            raw.extend((r, g, b))

    def chunk(tipo, corpo):
        return (struct.pack(">I", len(corpo)) + tipo + corpo
                + struct.pack(">I", zlib.crc32(tipo + corpo) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    dados = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
             + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
             + chunk(b"IEND", b""))
    with open(caminho, "wb") as f:
        f.write(dados)


def _ppm(largura, altura, pixels, caminho):
    with open(caminho, "wb") as f:
        f.write(f"P6\n{largura} {altura}\n255\n".encode("ascii"))
        for r, g, b in pixels:
            f.write(bytes((r, g, b)))


def _bmp(largura, altura, pixels, caminho):
    linha = ((largura * 3 + 3) // 4) * 4
    dados = bytearray()
    for y in range(altura - 1, -1, -1):
        for x in range(largura):
            r, g, b = pixels[y * largura + x]
            dados.extend((b, g, r))
        dados.extend(b"\x00" * (linha - largura * 3))
    tamanho = 54 + len(dados)
    cabecalho = (b"BM" + struct.pack("<IHHI", tamanho, 0, 0, 54)
                 + struct.pack("<IiiHHIIiiII", 40, largura, altura, 1, 24,
                               0, len(dados), 2835, 2835, 0, 0))
    with open(caminho, "wb") as f:
        f.write(cabecalho + dados)


def _imagem(cor, largura=64, altura=64):
    return [cor] * (largura * altura)


class TestAvaliacaoPura(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(TMP, exist_ok=True)
        cls.verde = os.path.join(TMP, "verde.png")
        cls.marrom = os.path.join(TMP, "marrom.png")
        cls.listras = os.path.join(TMP, "listras.png")
        cls.ppm = os.path.join(TMP, "verde.ppm")
        cls.bmp = os.path.join(TMP, "verde.bmp")
        _png(64, 64, _imagem((40, 180, 60)), cls.verde)
        _png(64, 64, _imagem((120, 80, 40)), cls.marrom)
        listras = []
        for y in range(64):
            for x in range(64):
                listras.append((20, 20, 20) if (x // 8) % 2 else
                               (235, 235, 235))
        _png(64, 64, listras, cls.listras)
        _ppm(32, 32, _imagem((40, 180, 60), 32, 32), cls.ppm)
        _bmp(32, 32, _imagem((40, 180, 60), 32, 32), cls.bmp)

    def test_png_bmp_ppm_sem_numpy_pillow(self):
        for caminho in (self.verde, self.ppm, self.bmp):
            carregado = avaliacao_imagens.carregar_pixels(caminho)
            self.assertIsNotNone(carregado, caminho)
            largura, altura, pixels, _passo, fonte = carregado
            self.assertEqual(fonte, "python-puro", caminho)
            self.assertGreater(largura, 0)
            self.assertGreater(altura, 0)
            self.assertGreater(len(pixels), 0)
            self.assertIsInstance(pixels[0], tuple)

    def test_vegetacao_verde(self):
        m = avaliacao_imagens.avaliar_imagem(self.verde)
        self.assertEqual(m["metodo"], "python-puro")
        self.assertGreater(m["verde_ratio"], 0.90)
        self.assertGreater(m["ExG"], 0.10)
        self.assertGreater(m["vegetacao_ratio"], 0.90)

    def test_solo_marrom(self):
        m = avaliacao_imagens.avaliar_imagem(self.marrom)
        self.assertGreater(m["marrom_ratio"], 0.90)
        self.assertLess(m["ExG"], 0.08)

    def test_bordas_em_listras(self):
        liso = avaliacao_imagens.avaliar_imagem(self.verde)["densidade_borda"]
        listras = avaliacao_imagens.avaliar_imagem(self.listras)[
            "densidade_borda"]
        self.assertGreater(listras, liso * 5)
        self.assertGreater(listras, 0.20)

    def test_ia_usa_avaliacao_pura(self):
        r = ia.analisar_imagem(self.verde, "agro")
        self.assertEqual(r["modelo"], "avaliacao-pura-v1")
        self.assertEqual(r["metricas"]["metodo"], "python-puro")
        self.assertIn(r["metricas"]["fonte"], ("python-puro",))

    def test_ia_detecta_solo_exposto(self):
        r = ia.analisar_imagem(self.marrom, "agro")
        classes = {o["classe"] for o in r["ocorrencias"]}
        self.assertIn("falha_plantio", classes)

    def test_ia_vistoria_detecta_borda(self):
        r = ia.analisar_imagem(self.listras, "vistoria_predial")
        classes = {o["classe"] for o in r["ocorrencias"]}
        self.assertIn("trinca", classes)

    def test_rebanho_nao_inventa_contagem(self):
        r = ia.analisar_imagem(self.verde, "agro",
                               contexto={"tipo_analise": "rebanho"})
        self.assertEqual(r["ocorrencias"], [])
        self.assertTrue(r["revisao_humana_obrigatoria"])
        self.assertIn("conta animais", r["resumo"].lower())

    def test_seguranca_nao_inventa_deteccao(self):
        r = ia.analisar_imagem(self.listras, "seguranca")
        self.assertEqual(r["ocorrencias"], [])
        self.assertTrue(r["revisao_humana_obrigatoria"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
