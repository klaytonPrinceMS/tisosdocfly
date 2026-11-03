# Relatórios

## 02/11/2026 — boot inicial

- `inicializar_bancos()` cria `db_mod_tisosdocfly.db` e
  `db_mod_gest_cad_usuario.db`.
- Seed confirmado: `master`, `qacomum`, `qamaster`.
- `master/master` autentica como `administrador_geral` e recebe a pendência de
  troca de credenciais.
- `qacomum/123456` autentica como `comum`, sem troca forçada.
- `modulos_registrados()` devolve apenas `usuarios`.

## 02/11/2026 — implementação total

- `poetry run task lint`: 0 `undefined name`.
- `tests/test_suite.py`: **11/11 scripts OK**.
- `tests/check_integridade.py`: **75/75 checagens**.
- `tests/teste_pipeline_ia.py`: 21 testes (índices, GSD, baseline, PDF).
- `poetry run task docs`: build `--strict` OK.
- Fluxo real validado: voo + imagem → análise IA → laudo PDF → link de
  download no diálogo do voo.

## 02/11/2026 — multiespectral e linhas de plantio

- `poetry run task lint`: 0 `undefined name`.
- `tests/test_suite.py`: **14/14 scripts OK**.
- `tests/check_integridade.py`: **75/75 checagens**.
- `tests/teste_multiespectral.py`: 6 testes (NDVI/SAVI, AOI, GeoTIFF).
- `tests/teste_linhas_plantio.py`: 4 testes (Hough, GeoJSON, integração).
- `tests/teste_avaliacao_pura.py`: 9 testes (Python puro, rebanho).
- `mkdocs build --strict`: OK.
- CLI multiespectral gerou `talhao_indices.json` + 5 GeoTIFFs.
- UI: botão **Linhas de plantio** abre o resumo Hough no cartão do agro.

## 02/11/2026 — serviços híbridos

- `poetry run task lint`: 0 `undefined name`.
- `tests/test_suite.py`: **17/17 scripts OK**.
- `tests/check_integridade.py`: **81/81 checagens**.
- `tests/teste_perimetro.py`: 8 testes (auditoria, achados, RF, schema).
- `tests/teste_rf_scan.py`: 15 testes (CSV/JSON/nmcli/iw, hash, risco).
- `tests/teste_painel_riscos.py`: 2 testes (agregação sem cross-query).
- `mkdocs build --strict`: OK.
- UI validada: `/perimetro`, `/admin/perimetro`, `/riscos`, card na home,
  botão de PDF na inspeção industrial; console sem erros.
- CLI RF: 2 redes, 1 aberta, JSON sanitizado sem BSSID cru.

## Próximos relatórios

Cada execução da suíte deve ser registrada aqui com data, comando e resultado,
sem apagar o histórico anterior.
