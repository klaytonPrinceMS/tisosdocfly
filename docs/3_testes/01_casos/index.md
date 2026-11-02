# Casos de teste

| Caso | O que garante | Arquivo |
|---|---|---|
| CT-01 | Boot cria os dois bancos e as três contas de fábrica | `tests/teste_boot.py` |
| CT-02 | `master` autentica e exige troca; QA não exige | `tests/teste_fluxo_autenticacao.py` |
| CT-03 | CRUD de usuário: criar, buscar, bloquear, excluir | `tests/teste_usuarios_crud.py` |
| CT-04 | Isolamento modular e layout `src/` | `tests/check_integridade.py` |
| CT-05 | Login e dashboard no navegador | `tests/pw_skyrover_login_dashboard.py` |
| CT-06 | Módulos ambiental, obras e mapeamento | `tests/teste_modulos_onda5a.py` |
| CT-07 | Módulos defesa civil, inspeção e eventos | `tests/teste_modulos_onda5b.py` |
| CT-08 | Pipeline de imagem e PDF | `tests/teste_pipeline_ia.py` |
| CT-09 | Paridade do login/troca de senha | `tests/teste_paridade_login.py` |
| CT-10 | Avaliação de imagem em Python puro | `tests/teste_avaliacao_pura.py` |
| CT-11 | Multiespectral: NDVI/SAVI, AOI, GeoTIFF | `tests/teste_multiespectral.py` |
| CT-12 | Linhas de plantio: Hough, GeoJSON, integração com voo | `tests/teste_linhas_plantio.py` |
| CT-13 | Perímetro: auditoria, achados, RF e schema | `tests/teste_perimetro.py` |
| CT-14 | Varredura RF: parsers, hash e risco | `tests/teste_rf_scan.py` |
| CT-15 | Painel de riscos agregado | `tests/teste_painel_riscos.py` |

## Pirâmide

Muitos unitários, menos integração, poucos E2E. E2E exige o servidor no ar e
navegador Playwright.
