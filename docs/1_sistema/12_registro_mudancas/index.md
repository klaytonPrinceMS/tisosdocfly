# Registro de mudanças

## 04/11/2026 — documentação da entrega inicial

- Registrada a publicação do commit `d4c84f9` em `main`/`origin`.
- Detalhes em [Entrega inicial — commit e push](01_entrega_inicial.md).

## 02/11/2026 — serviços híbridos e painel de riscos

- Catálogo dos três serviços híbridos: perímetro/segurança, inspeção com PDF
  e monitoramento de riscos.
- Página de conformidade ANAC/DECEA/SISANT + LGPD + Wi-Fi/RF.
- Painel `/riscos` agregando defesa civil, ambiental, obras, segurança,
  inspeção industrial e perímetro.
- Laudo PDF por módulo e botão na Inspeção Industrial (telhado, torre, painel
  solar).

## 02/11/2026 — linhas de plantio e vistoria de lavoura

- `linhas_plantio.py`: Hough em Python puro (máscara, hull, morfologia,
  Sobel, segmentos, GeoJSON, PNG anotado).
- Botão **Linhas de plantio** no agro e task `linhas`.
- Agro ganhou `finalidade`, `perda_estimada_pct` e `area_afetada_ha`
  (laudo de perdas/seguro agrícola).
- Culturas maçã/mandioca/uva e classes doença foliar/déficit hídrico/excesso
  de umidade.
- Referências: GeoIA (linhas de plantio) e RWTV/Epagri (vistoria de lavouras).

## 02/11/2026 — multiespectral (Embrapa, 2022)

- Módulo `multiespectral.py`: bandas R/G/B/NIR/RE/T, NDVI/SAVI/OSAVI/NDRE/
  GNDVI/NDWI/EVI, estatísticas, histograma, GeoTIFF e AOI GeoJSON/shapefile.
- CLI `python -m mod_skyrover.multiespectral` e task `multiespectral`.
- Botão **Processar multiespectral** no diálogo do voo.
- Referência: Soares et al. (Embrapa Semiárido, 2022).

## 02/11/2026 — pecuária e avaliação pura em Python

- Módulo agro passa a cobrir **lavoura, pastagem e rebanho**
  (`tipo_analise`, `cabecas_estimadas`, `area_pastagem_ha`).
- Classes de gado: contagem, animal isolado, aglomeração, animal caído,
  pastagem degradada e sombra/água.
- Base de conhecimento: Embrapa (Barbedo, 2024) — drones e IA para gado.
- Avaliação de imagem padrão em **Python puro** (`avaliacao_imagens.py`),
  com decode PNG/BMP/PPM via stdlib e modelo `avaliacao-pura-v1`.
- Rebanho no baseline não inventa contagem: exige detector treinado.

## 02/11/2026 — implementação total dos módulos e pipeline

- Nove módulos de negócio: agro, vistoria predial, segurança, ambiental,
  obras, mapeamento, defesa civil, inspeção industrial e eventos.
- Núcleo com clientes, propriedades, voos, capturas, mídia, análises de IA e
  laudos PDF.
- Pipeline `ia.py` (baseline RGB + registro/ONNX), `geoprocessamento.py`
  (ExG/VARI/GLI/TGI, GSD, thumbnail) e `relatorio.py` (PDF).
- Botão **Analisar IA** em todos os módulos e **Analisar mídias/Gerar laudo
  PDF** em `/voos`.
- Login/troca de senha com o CSS do padrão WhatsApp servido corretamente.
- Suíte com 11 scripts/testes; integridade modular 75/75.

## 02/11/2026 — criação do projeto

- Scaffold Python 3.13 + Poetry, com `pyproject.toml` como fonte única de
  dependências e `taskipy` como runner.
- Porte do núcleo da intranet como `mod_skyrover` (banco central, autenticação,
  tema, layout, configurações, documentação e auditoria central).
- Porte do módulo de gestão de usuários como `mod_gest_cad_usuario`, sem os
  dados reais da folha.
- Dois bancos iniciais: `db_mod_skyrover.db` e `db_mod_gest_cad_usuario.db`.
- Seed preservado: `master`, `qacomum` e `qamaster`.
- Padrão de documentação MkDocs (tema `readthedocs`) e suíte de testes
  standalone portados.
- Subagentes `kbp-*`, skill `graphify` e plugin `graphify.js` disponíveis.
