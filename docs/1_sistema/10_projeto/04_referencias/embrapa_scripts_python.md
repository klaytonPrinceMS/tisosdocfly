# Embrapa — scripts Python para imagens aéreas de drones

Referência aplicada ao processamento multiespectral do T! SOS DocFly.

## Fonte

- **Título:** Desenvolvimento de scripts em Python para processamento de
  imagens aéreas obtidas com drones
- **Autores:** Bruno do Nascimento Rodrigues Soares; Magna Soelma Beserra de
  Moura; Josiclêda Domiciano Galvíncio; Rodrigo de Queiroga Miranda
- **Publicação:** Anais da XVI Jornada de Iniciação Científica da Embrapa
  Semiárido — Documentos 308, dezembro/2022, p. 22–23.
- **Unidade:** Embrapa Semiárido (Petrolina/PE)
- **PDF:** <https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1152163/1/Desenvolvimento-de-scripts-em-Python-para-2022.pdf>
- **Código original citado:** `github.com/BrunoNRS/Simple-Remote-Sensing-Index-Script`

## O que o trabalho fez

- Cultivo de videira **‘BRS Vitória’** no Submédio do Vale São Francisco
  (Petrolina/PE).
- Drone **DJI Matrice 200 v2** com câmera multiespectral **Altum (MicaSense)**.
- Bandas: **Vermelho, Verde, Azul, NIR (infravermelho próximo), Red Edge e
  infravermelho termal**.
- Fotogrametria: alinhamento, nuvem de pontos, modelo digital do terreno
  (DTM) e ortomosaico.
- Scripts em Python para:
  - analisar cada banda espectral;
  - calcular índices de vegetação, incluindo **NDVI** e **SAVI**;
  - gerar **histogramas**;
  - exportar **média, máxima, mínima, mediana, variância e desvio-padrão**;
  - exportar camadas em **GeoTIFF**;
  - gerar mapas para visualização;
  - processar **todos os ortomosaicos** em lote;
  - recortar **áreas de interesse (AOI)** por arquivos shape.

## O que foi aplicado no T! SOS DocFly

### `src/mod_tisosdocfly/multiespectral.py`

| Recurso | Implementação |
|---|---|
| Bandas | `R`, `G`, `B`, `NIR`, `RE`, `T` por sufixo de arquivo ou dict explícito |
| Índices | `NDVI`, `SAVI` (L=0,5), `OSAVI`, `NDRE`, `GNDVI`, `NDWI`, `EVI` |
| Estatísticas | média, mínima, máxima, mediana, variância, desvio-padrão, p10, p90 |
| Histograma | 16 faixas em `[-1, 1]` |
| Lote | `processar_diretorio` agrupa `voo_R`, `voo_NIR`, ... |
| GeoTIFF | `exportar_geotiff` float32 com tags de pixel scale/tiepoint |
| AOI | GeoJSON nativo; shapefile se `pyshp` estiver instalado |
| CLI | `python -m mod_tisosdocfly.multiespectral` |

### Nomenclatura dos arquivos

Para o processamento automático por voo, nomeie as bandas com sufixo:

```
talhao1_R.png      talhao1_G.png      talhao1_B.png
talhao1_NIR.png    talhao1_RE.png     talhao1_T.png
```

O agrupador remove o sufixo e junta o grupo `talhao1`. O processamento exige
pelo menos **R** e **NIR** para NDVI.

### Saídas

Em `midia/<voo_id>/indices/`:

- `<base>_indices.json` — estatísticas por banda e por índice;
- `<base>_NDVI.tif`, `<base>_SAVI.tif`, `<base>_NDRE.tif`,
  `<base>_GNDVI.tif`, `<base>_NDWI.tif` — mapas float32.

### Limites

- **Não faz** alinhamento, nuvem de pontos, DTM ou ortomosaico: use ODM,
  Metashape ou similar antes.
- Índices RGB/multiespectrais são **relativos**; sem calibração de
  reflectância (painel/referência) não são laudo absoluto de biomassa.
- O processamento é amostrado (máx. 1024 px no maior lado) para manter a
  conta em Python viável. Em resolução nativa, use rasterio/GDAL.
- `SAVI` reduz o efeito do solo; ainda depende de calibração e da cultura.
- `AOI` por shapefile exige `pyshp`; GeoJSON funciona sem dependência extra.

## Como citar

SOARES, B. do N. R.; MOURA, M. S. B. de; GALVÍNCIO, J. D.; MIRANDA, R. de Q.
**Desenvolvimento de scripts em Python para processamento de imagens aéreas
obtidas com drones.** In: Anais da XVI Jornada de Iniciação Científica da
Embrapa Semiárido. Petrolina: Embrapa Semiárido, 2022. (Documentos 308),
p. 22–23.
