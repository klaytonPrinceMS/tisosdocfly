# -*- coding: utf-8 -*-
"""Prova o pipeline de imagem do núcleo: métricas, índices, GSD, IA e PDF.

O que este teste garante:
  - `geoprocessamento` mede RGB, índices de vegetação, borda, GSD e miniatura;
  - o baseline de `ia` responde por módulo sem inventar classes proibidas;
  - segurança pública devolve zero ocorrências e exige revisão humana;
  - o registro de modelos aceita um modelo plugável e normaliza a saída;
  - `relatorio` gera PDF real (> 1000 bytes) e nunca sobrescreve laudo.

Tudo com imagens sintéticas em /tmp — nenhum modelo treinado é simulado.
"""
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, RAIZ)

from mod_tisosdocfly import geoprocessamento, ia, relatorio  # noqa: E402


def _salvar(caminho, rgb_base, ruido=6, listras=None, semente=0):
    """Writes a 256x256 synthetic image (solid, noisy or striped)."""
    rng = np.random.default_rng(semente)
    if listras is not None:
        arr = np.zeros((256, 256, 3), dtype=np.float32)
        for coluna in range(256):
            valor = 255.0 if (coluna // listras) % 2 == 0 else 0.0
            arr[:, coluna, :] = valor
    else:
        arr = np.empty((256, 256, 3), dtype=np.float32)
        arr[:, :, :] = np.array(rgb_base, dtype=np.float32)
        if ruido:
            arr += rng.normal(0, ruido, arr.shape)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    Image.fromarray(arr, mode="RGB").save(caminho)
    return caminho


class TestPipelineIA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="tisosdocfly_pipeline_")
        os.environ["TISOSDOCFLY_DIR_LAUDOS"] = cls.tmp
        cls.veg = _salvar(os.path.join(cls.tmp, "vegetacao.png"),
                          (45, 155, 55), ruido=8, semente=1)
        cls.seca = _salvar(os.path.join(cls.tmp, "seca.png"),
                           (150, 120, 75), ruido=5, semente=2)
        cls.contraste = _salvar(os.path.join(cls.tmp, "contraste.png"),
                                None, listras=4)
        cls.escura = _salvar(os.path.join(cls.tmp, "escura.png"),
                             (18, 18, 22), ruido=3, semente=3)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ── geoprocessamento ────────────────────────────────────────────────
    def test_carregar_rgb_normalizado(self):
        arr = geoprocessamento.carregar_rgb(self.veg)
        self.assertIsNotNone(arr)
        self.assertEqual(arr.ndim, 3)
        self.assertEqual(arr.shape[2], 3)
        self.assertEqual(arr.dtype, np.float32)
        self.assertGreaterEqual(float(arr.min()), 0.0)
        self.assertLessEqual(float(arr.max()), 1.0)
        self.assertIsNone(geoprocessamento.carregar_rgb(
            os.path.join(self.tmp, "inexistente.png")))

    def test_metricas_rgb_por_cena(self):
        veg = geoprocessamento.metricas_rgb(self.veg)
        seca = geoprocessamento.metricas_rgb(self.seca)
        contraste = geoprocessamento.metricas_rgb(self.contraste)
        escura = geoprocessamento.metricas_rgb(self.escura)

        obrigatorias = {
            "media_rgb", "brilho", "contraste", "saturacao_media",
            "verde_ratio", "marrom_ratio", "cinza_ratio", "densidade_borda",
        }
        self.assertTrue(obrigatorias.issubset(set(veg)))
        self.assertEqual(len(veg["media_rgb"]), 3)

        self.assertGreater(veg["verde_ratio"], 0.90)
        self.assertLess(veg["marrom_ratio"], 0.10)
        self.assertGreater(seca["marrom_ratio"], 0.90)
        self.assertLess(seca["verde_ratio"], 0.10)
        self.assertGreater(contraste["densidade_borda"], 0.30)
        self.assertGreater(contraste["contraste"], 0.30)
        self.assertGreater(contraste["cinza_ratio"], 0.80)
        self.assertLess(escura["brilho"], 0.20)
        self.assertGreater(escura["escuro_ratio"], 0.80)

    def test_indices_vegetacao(self):
        veg = geoprocessamento.indices_vegetacao(self.veg)
        seca = geoprocessamento.indices_vegetacao(self.seca)
        for chave in ("ExG", "VARI", "GLI", "TGI", "media_rgb", "brilho",
                      "contraste", "densidade_borda"):
            self.assertIn(chave, veg)
        self.assertGreater(veg["ExG"], seca["ExG"])
        self.assertGreater(veg["VARI"], seca["VARI"])
        self.assertGreater(veg["GLI"], 0.50)
        self.assertIsInstance(veg["TGI"], float)
        self.assertTrue(np.isfinite(veg["TGI"]))

    def test_gsd_formula_e_validacao(self):
        # 100 m, sensor de 6,3 mm, focal 4,5 mm, 4000 px → 3,5 cm/px
        self.assertAlmostEqual(
            geoprocessamento.gsd_cm(100, 6.3, 4.5, 4000), 3.5, places=6)
        self.assertAlmostEqual(
            geoprocessamento.gsd_cm(50, 6.3, 4.5, 4000), 1.75, places=6)
        with self.assertRaises(ValueError):
            geoprocessamento.gsd_cm(0, 6.3, 4.5, 4000)
        with self.assertRaises(ValueError):
            geoprocessamento.gsd_cm("x", 6.3, 4.5, 4000)

    def test_thumbnail_e_estatisticas(self):
        destino = os.path.join(self.tmp, "mini.png")
        self.assertTrue(geoprocessamento.gerar_thumbnail(
            self.veg, destino, tamanho=64))
        self.assertTrue(os.path.isfile(destino))
        with Image.open(destino) as miniatura:
            self.assertLessEqual(max(miniatura.size), 64)
        stats = geoprocessamento.estatisticas_imagem(self.veg)
        self.assertEqual(stats["largura"], 256)
        self.assertEqual(stats["altura"], 256)
        self.assertEqual(stats["modo"], "RGB")
        self.assertIsInstance(stats["exif_basico"], dict)

    def test_area_imagem(self):
        self.assertAlmostEqual(
            geoprocessamento.area_imagem_m2(100, 100, 2.0), 4.0, places=6)
        self.assertEqual(geoprocessamento.area_imagem_m2(0, 100, 2.0), 0.0)

    def test_ler_geotiff_opcional_nao_quebra(self):
        # Sem rasterio (estado atual) devolve None; com ele, dict ou None.
        resultado = geoprocessamento.ler_geotiff(self.veg)
        self.assertTrue(resultado is None or isinstance(resultado, dict))

    # ── ia: contrato e baselines ────────────────────────────────────────
    def _chaves_contrato(self, resultado):
        self.assertEqual(set(resultado), {
            "modelo", "versao", "confianca", "resumo", "metricas",
            "ocorrencias", "revisao_humana_obrigatoria",
        })
        self.assertIsInstance(resultado["modelo"], str)
        self.assertIsInstance(resultado["versao"], str)
        self.assertGreaterEqual(resultado["confianca"], 0.0)
        self.assertLessEqual(resultado["confianca"], 1.0)
        self.assertIsInstance(resultado["metricas"], dict)
        self.assertIsInstance(resultado["ocorrencias"], list)
        self.assertIsInstance(resultado["revisao_humana_obrigatoria"], bool)
        for ocorrencia in resultado["ocorrencias"]:
            self.assertEqual(set(ocorrencia), {
                "classe", "severidade", "confianca", "area_m2", "evidencia"})
            self.assertGreaterEqual(ocorrencia["confianca"], 0.0)
            self.assertLessEqual(ocorrencia["confianca"], 1.0)
            self.assertGreaterEqual(ocorrencia["area_m2"], 0.0)

    def test_agro_seca_gera_falha_plantio(self):
        resultado = ia.analisar_imagem(self.seca, "agro",
                                       {"gsd_cm": 2.0})
        self._chaves_contrato(resultado)
        classes = {o["classe"] for o in resultado["ocorrencias"]}
        self.assertIn("falha_plantio", classes)
        self.assertTrue(classes.issubset(
            {"estresse_metabolico", "falha_plantio", "matocompeticao"}))
        self.assertTrue(resultado["revisao_humana_obrigatoria"])
        self.assertGreater(resultado["ocorrencias"][0]["area_m2"], 0.0)

    def test_agro_vegetacao_nao_acusa_solo_exposto(self):
        resultado = ia.analisar_imagem(self.veg, "agro")
        self._chaves_contrato(resultado)
        classes = {o["classe"] for o in resultado["ocorrencias"]}
        self.assertNotIn("falha_plantio", classes)
        self.assertGreater(resultado["metricas"]["ExG"], 0.5)

    def test_vistoria_predial_detecta_borda(self):
        resultado = ia.analisar_imagem(self.contraste, "vistoria_predial")
        self._chaves_contrato(resultado)
        classes = {o["classe"] for o in resultado["ocorrencias"]}
        self.assertIn("trinca", classes)
        self.assertGreater(resultado["metricas"]["densidade_borda"], 0.30)

    def test_ambiental_detecta_solo_exposto(self):
        resultado = ia.analisar_imagem(self.seca, "ambiental")
        self._chaves_contrato(resultado)
        classes = {o["classe"] for o in resultado["ocorrencias"]}
        self.assertIn("desmatamento", classes)

    def test_seguranca_sem_modelo_nao_inventa_deteccao(self):
        resultado = ia.analisar_imagem(self.contraste, "seguranca")
        self._chaves_contrato(resultado)
        self.assertEqual(resultado["ocorrencias"], [])
        self.assertTrue(resultado["revisao_humana_obrigatoria"])
        resumo = resultado["resumo"].lower()
        self.assertTrue("detector" in resumo or "homologado" in resumo)
        self.assertIn("base legal", resumo)

    def test_mapeamento_metricas_e_gsd(self):
        resultado = ia.analisar_imagem(self.veg, "mapeamento",
                                       {"gsd_cm": 2.5})
        self._chaves_contrato(resultado)
        self.assertEqual(resultado["ocorrencias"], [])
        self.assertAlmostEqual(resultado["metricas"]["gsd_cm"], 2.5)
        self.assertGreater(resultado["metricas"]["area_m2"], 0.0)
        self.assertFalse(resultado["revisao_humana_obrigatoria"])

    def test_defesa_civil_conservadora(self):
        resultado = ia.analisar_imagem(self.escura, "defesa_civil")
        self._chaves_contrato(resultado)
        self.assertEqual(resultado["ocorrencias"], [])
        self.assertTrue(resultado["revisao_humana_obrigatoria"])

    def test_caminho_invalido_nao_levanta(self):
        resultado = ia.analisar_imagem(
            os.path.join(self.tmp, "nao_existe.jpg"), "agro")
        self._chaves_contrato(resultado)
        self.assertEqual(resultado["ocorrencias"], [])
        self.assertTrue(resultado["revisao_humana_obrigatoria"])

    def test_analisar_lote_preserva_ordem(self):
        resultados = ia.analisar_lote(
            [self.veg, self.seca, os.path.join(self.tmp, "x.jpg")], "agro")
        self.assertEqual(len(resultados), 3)
        for item in resultados:
            self._chaves_contrato(item)
        self.assertGreater(resultados[0]["metricas"]["ExG"],
                           resultados[1]["metricas"]["ExG"])

    def test_registro_de_modelo_plugavel(self):
        def modelo_falso(caminho, contexto):
            return {
                "confianca": 2.0,  # deve ser limitado a 1.0
                "resumo": "modelo de teste",
                "ocorrencias": [
                    {"classe": "teste", "severidade": "altissima",
                     "confianca": 0.8, "area_m2": -4,
                     "evidencia": "saida do modelo falso"},
                ],
                "revisao_humana_obrigatoria": False,
            }

        try:
            self.assertTrue(ia.registrar_modelo(
                "modulo_teste", "0.1", modelo_falso))
            self.assertIsNotNone(ia.obter_modelo("modulo_teste"))
            disponiveis = {m["nome"]: m["versao"]
                           for m in ia.modelos_disponiveis()}
            self.assertEqual(disponiveis.get("modulo_teste"), "0.1")
            resultado = ia.analisar_imagem(self.veg, "modulo_teste")
            self._chaves_contrato(resultado)
            self.assertEqual(resultado["modelo"], "modulo_teste")
            self.assertEqual(resultado["versao"], "0.1")
            self.assertEqual(resultado["confianca"], 1.0)
            self.assertEqual(resultado["ocorrencias"][0]["area_m2"], 0.0)
            self.assertEqual(resultado["ocorrencias"][0]["severidade"],
                             "indeterminada")
        finally:
            ia.remover_modelo("modulo_teste")
        self.assertIsNone(ia.obter_modelo("modulo_teste"))

    def test_modelo_onnx_opcional_nao_quebra(self):
        caminho = os.path.join(self.tmp, "modelo_inexistente.onnx")
        resultado = ia.modelo_onnx(caminho)
        self.assertTrue(resultado is None or callable(resultado))

    # ── relatorio ───────────────────────────────────────────────────────
    def test_gerar_pdf_laudo_com_imagem(self):
        destino = os.path.join(self.tmp, "laudo.pdf")
        ocorrencias = [{
            "classe": "falha_plantio", "severidade": "media",
            "confianca": 0.62, "area_m2": 123.45,
            "evidencia": "marrom_ratio alto <b>nao deve virar negrito</b>",
        }]
        caminho = relatorio.gerar_pdf_laudo(
            destino, "Laudo de teste — voo #1",
            {"Cliente": "Cliente Fictício", "Propriedade": "Fazenda Teste",
             "GSD": "2,0 cm/px"},
            "Resumo <script>alert(1)</script> com acento: vegetação.",
            ocorrencias, imagens=[self.seca],
            metricas={"ExG": 0.12, "brilho": 0.4})
        self.assertIsNotNone(caminho)
        self.assertTrue(os.path.isfile(caminho))
        self.assertGreater(os.path.getsize(caminho), 1000)
        with open(caminho, "rb") as arquivo:
            self.assertEqual(arquivo.read(5), b"%PDF-")

    def test_pdf_nao_sobrescreve(self):
        destino = os.path.join(self.tmp, "repetido.pdf")
        primeiro = relatorio.gerar_pdf_laudo(
            destino, "Laudo repetido", {}, "Resumo.", [])
        segundo = relatorio.gerar_pdf_laudo(
            destino, "Laudo repetido", {}, "Resumo.", [])
        self.assertIsNotNone(primeiro)
        self.assertIsNotNone(segundo)
        self.assertNotEqual(primeiro, segundo)
        self.assertTrue(os.path.isfile(primeiro))
        self.assertTrue(os.path.isfile(segundo))

    def test_gerar_pdf_modulo_cria_pasta(self):
        argumentos = ("agro", "Laudo agro", {"Módulo": "agro"},
                      "Resumo do módulo.", [])
        primeiro = relatorio.gerar_pdf_modulo(*argumentos)
        segundo = relatorio.gerar_pdf_modulo(*argumentos)
        self.assertIsNotNone(primeiro)
        self.assertIsNotNone(segundo)
        self.assertNotEqual(primeiro, segundo)
        self.assertEqual(os.path.dirname(primeiro),
                         os.path.join(self.tmp, "agro"))
        self.assertGreater(os.path.getsize(primeiro), 1000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
