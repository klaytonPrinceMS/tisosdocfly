# Processamento multiespectral

Implementação inspirada em Soares et al. (Embrapa Semiárido, 2022): bandas
multiespectrais, índices, estatísticas, histograma, GeoTIFF e AOI.

## Nomenclatura

Nomeie as bandas com sufixo `_R`, `_G`, `_B`, `_NIR`, `_RE`, `_T`
(maiúsculo ou minúsculo):

```
talhao1_R.png   talhao1_G.png   talhao1_B.png
talhao1_NIR.png talhao1_RE.png  talhao1_T.png
```

## Pela interface

1. Envie as bandas em `/voos` (diálogo do voo → upload).
2. Clique em **Processar multiespectral**.
3. O resultado aparece em `midia/<voo_id>/indices/`:
   - `<base>_indices.json`;
   - `<base>_NDVI.tif`, `_SAVI.tif`, `_NDRE.tif`, `_GNDVI.tif`, `_NDWI.tif`.

## Pela CLI

```bash
poetry run task multiespectral -- \
  --r talhao1_R.tif --nir talhao1_NIR.tif \
  --g talhao1_G.tif --re talhao1_RE.tif \
  --out saida/

# diretório inteiro (agrupa por nome)
poetry run task multiespectral -- --dir midia/1 --out midia/1/indices

# com AOI GeoJSON
poetry run task multiespectral -- --dir midia/1 --aoi talhao.geojson
```

## Índices

| Índice | Fórmula (bandas normalizadas) | Uso |
|---|---|---|
| NDVI | `(NIR - R) / (NIR + R)` | vigor/vegetação |
| SAVI | `1,5 * (NIR - R) / (NIR + R + 0,5)` | vegetação com solo exposto |
| OSAVI | `(NIR - R) / (NIR + R + 0,16)` | variante do SAVI |
| NDRE | `(NIR - RE) / (NIR + RE)` | clorofila/estresse |
| GNDVI | `(NIR - G) / (NIR + G)` | clorofila |
| NDWI | `(G - NIR) / (G + NIR)` | água/umidade |
| EVI | `2,5 * (NIR - R) / (NIR + 6R - 7,5B + 1)` | vegetação densa |

## Estatísticas

`media`, `minima`, `maxima`, `mediana`, `variancia`, `desvio_padrao`, `p10`,
`p90` e `histograma` de 16 faixas. O JSON mantém as estatísticas por banda e
por índice.

## GeoTIFF

`exportar_geotiff` grava float32 e, quando informado, aplica `PixelScale`,
`Tiepoint` e `GeoKeyDirectory`. Sem geotransform, o TIFF é uma imagem de
índice não georreferenciada.

## AOI

- **GeoJSON** (`.geojson`/`.json`): suportado sem dependência extra.
- **Shapefile** (`.shp`): suportado se `pyshp` estiver instalado.

A máscara usa o geotransform `(x0, y0, dx, dy)`; sem ele, as coordenadas do
AOI são tratadas como pixels.

## Limitações

- Não faz fotogrametria (alinhamento, DTM, ortomosaico).
- Índices de cor não substituem reflectância calibrada.
- Processa no máximo 1024 px no maior lado (amostragem). Para resolução
  nativa, use rasterio/GDAL.
- Não é laudo agronômico sem validação de campo.

## Referência

[Embrapa — scripts Python para imagens aéreas](../10_projeto/04_referencias/embrapa_scripts_python.md)
