# Agropecuário

Pacote: `src/mod_agro/` — chave de banco `agro` — rota `/agro`.

## Estado

MVP funcional (Onda 2): análise de voo, ocorrências, status e laudo textual.
Cobre **lavoura, pastagem e rebanho**. A inferência por CNN/IA e a contagem
automática de gado dependem de modelo treinado; o baseline não inventa
contagem.

## Banco

`db_mod_agro.db`:

| Tabela | Conteúdo |
|---|---|
| `tb_agro_analise` | voo, talhão/piquete, cultura/pastagem, índice, área, status, resultado, tipo (`lavoura`/`pastagem`/`rebanho`), cabeças, área de pastagem, finalidade, perda estimada, área afetada |
| `tb_agro_ocorrencia` | classe, severidade, área, confiança, revisão humana, evidência |

## Fluxo

1. Cadastre cliente, propriedade e voo em `/voos`.
2. Em `/agro`, clique em **Nova análise** e selecione o voo.
3. Informe talhão, cultura, índice (NDVI/NDRE/GNDVI/NDWI/SAVI) e área.
4. Registre ocorrências (estresse, ferrugem, oídio, nematoides, falha de
   plantio, matocompetição).
5. **Concluir** gera o resumo do laudo agropecuário.

## Regras

- Cada análise referencia um `voo_id` do núcleo via API pública
  (`mod_skyrover.voos`); o módulo não faz cross-query.
- Ocorrência é **triagem**; `revisao_humana` registra a conferência.
- Nenhum dado de cliente/propriedade é copiado para o banco do módulo além
  dos IDs de referência.

## Pecuária (Embrapa, 2024)

O módulo segue as orientações do capítulo **“Drones e Inteligência Artificial
para o monitoramento de gado”** (Barbedo, Embrapa Agricultura Digital, 2024):

- Separação explícita de `lavoura`, `pastagem` e `rebanho`.
- `cabecas_estimadas` é a contagem **declarada/revisada**, não inventada pelo
  baseline.
- Classes de ocorrência: `contagem_gado`, `animal_isolado`,
  `aglomeracao_animal`, `animal_caido`, `pastagem_degradada`, `sombra_agua`.
- O baseline em Python puro mede pasto/cor, mas **não conta animais**; em modo
  rebanho devolve revisão humana obrigatória.
- Contagem automática exige detector (YOLO/Mask R-CNN), dataset anotado,
  validação cruzada e conjunto independente.

Detalhes e citação: [Embrapa — drones e gado](../../10_projeto/04_referencias/embrapa_drones_gado.md).

## Linhas de plantio (Hough)

`linhas_plantio.py` detecta fileiras retas em Python puro: máscara de
vegetação por ExG/Otsu, convex hull, morfologia, Sobel, Hough e filtro pelo
grupo angular dominante. Gera JSON, GeoJSON e PNG anotado. Na tela, o botão
**Linhas de plantio** roda em uma imagem do voo.

```bash
poetry run task linhas -- imagem.png --out saida/
```

Limite: Hough não representa bem linhas curvas. Referência:
[GeoIA — linhas de plantio](../../10_projeto/04_referencias/geoia_linhas_plantio.md).

## Vistoria de lavoura e seguro agrícola

O campo `finalidade` (`producao`, `seguro_agricola`, `vistoria`, `pesquisa`)
e os campos `perda_estimada_pct`/`area_afetada_ha` permitem usar a mesma
análise para laudo de perdas. Culturas incluem maçã, mandioca e uva; classes
incluem doença foliar, déficit hídrico e excesso de umidade.

Referência: [RWTV/Epagri — vistoria de lavouras](../../10_projeto/04_referencias/rwtv_vistoria_lavouras.md).

## Próximas capacidades

- Índices espectrais calculados a partir do ortomosaico.
- Contagem de plantas, estande e mapa de falhas.
- Ferrugem asiática, oídio, nematoides e estresse metabólico por CNN.
- Culturas: soja, milho, tomate, café, banana e frutíferas.
- Detector de gado treinado e contagem automática validada em campo.
- Comparativo entre safras e geração de PDF.
