# -*- coding: utf-8 -*-
"""Prova o parser/sanitizador de varredura Wi-Fi/RF do T! SOS DocFly.

O que este teste garante: CSV, JSON, nmcli e iw são lidos; a banda/canal e a
segurança são normalizados; o risco é classificatório e documentado; o BSSID
NUNCA aparece cru (só SHA-256); a CLI gera JSON sanitizado. Não acessa rede,
não exige root e não usa banco.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
os.environ.setdefault("TISOSDOCFLY_DIR_BANCO", "/tmp/opencode/bd_perimetro")
os.environ.setdefault("TISOSDOCFLY_DIR_MIDIA", "/tmp/opencode/midia_perimetro")
os.environ.setdefault("TISOSDOCFLY_RF_VIVO", "0")

from mod_tisosdocfly import rf_scan


CSV_EXEMPLO = (
    "ssid;bssid;banda;canal;rssi;seguranca;latitude;longitude\n"
    "Rede-A;AA:BB:CC:DD:EE:01;2.4GHz;6;-48;WPA2;-23.5;-46.6\n"
    "Rede-B;AA:BB:CC:DD:EE:02;5GHz;36;-65;--;;\n"
)

JSON_EXEMPLO = json.dumps({
    "redes": [
        {"ssid": "Rede-C", "bssid": "AA:BB:CC:DD:EE:03", "canal": 11,
         "rssi": -55, "security": "WEP"},
        {"ssid": "Rede-D", "bssid": "AA:BB:CC:DD:EE:04", "freq": 5180,
         "rssi": -61, "seguranca": "WPA3"},
    ]
})

NMCLI_EXEMPLO = (
    "Rede-Nmcli:AA\\:BB\\:CC\\:DD\\:EE\\:05:79:WPA2\n"
    "Rede-Nmcli2;AA:BB:CC:DD:EE:06;42;WPA3\n"
)

IW_EXEMPLO = """BSS aa:bb:cc:dd:ee:07 (on wlan0)
        freq: 2437
        signal: -52.00 dBm
        SSID: Rede-Iw
        RSN:     * Version: 1
                 * Authentication suites: PSK
BSS aa:bb:cc:dd:ee:08 (on wlan0)
        freq: 5180
        DS Parameter set: channel 36
        signal: -71.50 dBm
        SSID: Rede-Iw5
        RSN:     * Version: 1
                 * Authentication suites: SAE
"""


class TestParsers(unittest.TestCase):
    def test_parse_csv(self):
        registros = rf_scan.parse_csv(CSV_EXEMPLO)
        self.assertEqual(len(registros), 2)
        self.assertEqual(registros[0]["ssid"], "Rede-A")
        self.assertEqual(registros[0]["bssid"], "AA:BB:CC:DD:EE:01")
        self.assertEqual(registros[0]["canal"], 6)
        self.assertAlmostEqual(registros[0]["rssi"], -48.0)
        self.assertAlmostEqual(registros[0]["latitude"], -23.5)
        self.assertAlmostEqual(registros[0]["longitude"], -46.6)
        self.assertEqual(registros[1]["seguranca"], "--")

    def test_parse_csv_virgula_e_apelidos(self):
        texto = ("rede,mac,channel,signal,auth\n"
                 "Rede-V,aa-bb-cc-dd-ee-09,1,-44,WPA2\n")
        registros = rf_scan.parse_csv(texto)
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["ssid"], "Rede-V")
        self.assertEqual(registros[0]["banda"], "2.4GHz")
        self.assertEqual(registros[0]["canal"], 1)

    def test_parse_json_lista_e_objeto(self):
        registros = rf_scan.parse_json(JSON_EXEMPLO)
        self.assertEqual(len(registros), 2)
        self.assertEqual(registros[0]["ssid"], "Rede-C")
        self.assertEqual(registros[0]["banda"], "2.4GHz")
        self.assertEqual(registros[1]["banda"], "5GHz")
        self.assertEqual(registros[1]["canal"], 36)
        lista = rf_scan.parse_json(json.dumps([registros[0]]))
        self.assertEqual(len(lista), 1)
        self.assertEqual(rf_scan.parse_json("não é json"), [])

    def test_parse_nmcli(self):
        registros = rf_scan.parse_nmcli(NMCLI_EXEMPLO)
        self.assertEqual(len(registros), 2)
        self.assertEqual(registros[0]["ssid"], "Rede-Nmcli")
        self.assertEqual(registros[0]["bssid"], "AA:BB:CC:DD:EE:05")
        self.assertAlmostEqual(registros[0]["rssi"], -60.5)
        self.assertEqual(registros[0]["seguranca"], "WPA2")
        self.assertEqual(registros[1]["bssid"], "AA:BB:CC:DD:EE:06")
        self.assertAlmostEqual(registros[1]["rssi"], -79.0)
        self.assertEqual(registros[1]["seguranca"], "WPA3")

    def test_parse_iw(self):
        registros = rf_scan.parse_iw(IW_EXEMPLO)
        self.assertEqual(len(registros), 2)
        self.assertEqual(registros[0]["ssid"], "Rede-Iw")
        self.assertEqual(registros[0]["banda"], "2.4GHz")
        self.assertEqual(registros[0]["canal"], 6)
        self.assertAlmostEqual(registros[0]["rssi"], -52.0)
        self.assertEqual(registros[0]["seguranca"], "wpa2")
        self.assertEqual(registros[1]["banda"], "5GHz")
        self.assertEqual(registros[1]["canal"], 36)
        self.assertEqual(registros[1]["seguranca"], "wpa3")

    def test_parse_vazio_nao_quebra(self):
        self.assertEqual(rf_scan.parse_csv(""), [])
        self.assertEqual(rf_scan.parse_json(""), [])
        self.assertEqual(rf_scan.parse_nmcli(""), [])
        self.assertEqual(rf_scan.parse_iw(""), [])


class TestHashESanitizacao(unittest.TestCase):
    def test_hash_bssid_canonico(self):
        esperado = hashlib.sha256(
            b"aa:bb:cc:dd:ee:0f").hexdigest()
        self.assertEqual(rf_scan.hash_bssid("AA:BB:CC:DD:EE:0F"), esperado)
        self.assertEqual(rf_scan.hash_bssid("aa-bb-cc-dd-ee-0f"), esperado)
        self.assertEqual(rf_scan.hash_bssid(""), "")

    def test_normalizar_nao_expoe_bssid(self):
        bruto = {
            "ssid": "Rede-Hash", "bssid": "AA:BB:CC:DD:EE:10",
            "canal": 6, "rssi": -45, "seguranca": "aberta",
            "latitude": -23.1, "longitude": -46.2,
        }
        registro = rf_scan.normalizar_registro(bruto)
        self.assertNotIn("bssid", registro)
        self.assertEqual(len(registro["bssid_hash"]), 64)
        self.assertEqual(
            registro["bssid_hash"],
            hashlib.sha256(b"aa:bb:cc:dd:ee:10").hexdigest())
        self.assertEqual(registro["seguranca"], "aberta")
        self.assertEqual(registro["banda"], "2.4GHz")
        self.assertEqual(registro["risco"], "alto")
        self.assertNotIn("AA:BB:CC:DD:EE:10",
                         json.dumps(registro, ensure_ascii=False))

    def test_normalizar_invalido(self):
        self.assertEqual(rf_scan.normalizar_registro(None), {})
        self.assertEqual(rf_scan.normalizar_registro("x"), {})


class TestRisco(unittest.TestCase):
    def test_matriz_de_risco(self):
        self.assertEqual(rf_scan.classificar_risco("aberta", -50), "alto")
        self.assertEqual(rf_scan.classificar_risco("aberta", -80), "medio")
        self.assertEqual(rf_scan.classificar_risco("wep", -55), "alto")
        self.assertEqual(rf_scan.classificar_risco("wep", -85), "medio")
        self.assertEqual(rf_scan.classificar_risco("wpa2", -40), "baixo")
        self.assertEqual(rf_scan.classificar_risco("wpa3", -40), "baixo")
        self.assertEqual(
            rf_scan.classificar_risco("desconhecida", -45), "medio")
        self.assertEqual(
            rf_scan.classificar_risco("desconhecida", -90), "baixo")

    def test_fora_perimetro_eleva_so_com_sinal_forte(self):
        self.assertEqual(
            rf_scan.classificar_risco("aberta", -45, True), "critico")
        self.assertEqual(
            rf_scan.classificar_risco("wpa2", -45, True), "medio")
        self.assertEqual(
            rf_scan.classificar_risco("aberta", -90, True), "medio")

    def test_seguranca_normalizada(self):
        self.assertEqual(rf_scan.normalizar_seguranca("--"), "aberta")
        self.assertEqual(rf_scan.normalizar_seguranca(""), "aberta")
        self.assertEqual(rf_scan.normalizar_seguranca("WPA2 WPA3"), "wpa3")
        self.assertEqual(rf_scan.normalizar_seguranca("WPA1 WPA2"), "wpa2")
        self.assertEqual(rf_scan.normalizar_seguranca("WEP"), "wep")
        self.assertEqual(rf_scan.normalizar_seguranca("WPA"), "desconhecida")


class TestResumoECLI(unittest.TestCase):
    def test_resumo_registros(self):
        registros = [rf_scan.normalizar_registro(r)
                     for r in rf_scan.parse_csv(CSV_EXEMPLO)]
        resumo = rf_scan.resumo_registros(registros)
        self.assertEqual(resumo["total"], 2)
        self.assertEqual(resumo["abertas"], 1)
        self.assertEqual(resumo["por_risco"]["alto"], 1)

    def test_varredura_ao_vivo_desligada(self):
        os.environ["TISOSDOCFLY_RF_VIVO"] = "0"
        self.assertEqual(rf_scan.escanear_ao_vivo(), [])

    def test_cli_gera_json_sanitizado(self):
        os.makedirs("/tmp/opencode", exist_ok=True)
        pasta = tempfile.mkdtemp(prefix="rf_scan_", dir="/tmp/opencode")
        try:
            entrada = os.path.join(pasta, "entrada.csv")
            saida = os.path.join(pasta, "saida.json")
            with open(entrada, "w", encoding="utf-8") as arquivo:
                arquivo.write(CSV_EXEMPLO)
            codigo = rf_scan.main(
                ["--csv", entrada, "--out", saida])
            self.assertEqual(codigo, 0)
            self.assertTrue(os.path.isfile(saida))
            with open(saida, "r", encoding="utf-8") as arquivo:
                relatorio = json.load(arquivo)
            self.assertEqual(relatorio["total"], 2)
            self.assertEqual(relatorio["resumo"]["abertas"], 1)
            texto = json.dumps(relatorio, ensure_ascii=False)
            self.assertNotIn("AA:BB:CC:DD:EE:01", texto)
            self.assertNotIn("AA:BB:CC:DD:EE:02", texto)
            for registro in relatorio["registros"]:
                self.assertIn("bssid_hash", registro)
                self.assertNotIn("bssid", registro)
        finally:
            shutil.rmtree(pasta, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
