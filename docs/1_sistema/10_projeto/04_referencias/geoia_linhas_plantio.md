# GeoIA — detecção de linhas de plantio com Hough

Referência aplicada ao módulo agro.

## Fonte

- **Vídeo:** Usando Visão Computacional para detectar linhas de plantio em
  imagens de Drone!!!!
- **Canal:** GeoIA Aplicada (João Otávio / DeepGeo)
- **URL:** <https://www.youtube.com/watch?v=JOmQg-4aDzk>
- **Duração:** ~16 min
- **Tema:** visão computacional tradicional (sem deep learning) aplicada a
  imagens de drone.

## Método ensinado

1. **Abrir a imagem** (no vídeo, com `rasterio`) e converter para 8 bits.
2. **Selecionar a banda** que melhor separa vegetação de solo — não
   necessariamente a banda vermelha; depende da composição da câmera.
3. **Limiarizar** a banda escolhida (exemplo: 90) para gerar máscara binária
   vegetação/não vegetação.
4. **Convex hull** da área vegetada: polígono envolvente que define a AOI.
5. **Orientação do polígono** (~36° no exemplo): a imagem está na diagonal.
6. **Rotacionar** imagem/máscara para alinhar as fileiras, aplicar
   **morfologia** (abertura/dilatação/erosão) para remover ruído e manter
   linhas retas.
7. **Esqueletizar** (skeleton) para reduzir cada faixa a uma linha.
8. **Sobel** para remover resíduos verticais e **rotacionar de volta**.
9. **Hough Line Transform** (`HoughLinesP` no vídeo) para detectar as linhas.
10. **Converter para coordenadas georreferenciadas**, recortar pelo convex
    hull e salvar **shapefile**.
11. Usar as linhas para analisar **falhas de plantio**, espaçamento e outras
    métricas.

Limitações citadas no próprio vídeo: Hough funciona para **linhas retas**;
cultivos com linhas curvas exigem outro método. O pré-processamento é a parte
que mais importa — nenhum algoritmo corrige imagem ruim.

## O que foi aplicado no T! SOS DocFly

`src/mod_tisosdocfly/linhas_plantio.py` implementa em **Python puro**
(sem OpenCV/numpy):

| Etapa | Implementação |
|---|---|
| Máscara de vegetação | ExG + limiar de Otsu (fallback por luminância) |
| Envelope | convex hull (monotonic chain) |
| Orientação | PCA dos pixels da máscara |
| Limpeza | abertura + fechamento 3×3 |
| Bordas | Sobel 3×3 na máscara |
| Linhas | Hough com acumulador plano, passo de 2° |
| Filtro | grupo angular dominante + deduplicação por (theta, rho) |
| Métricas | total de linhas, ângulo, espaçamento, comprimento médio |
| Saída | JSON, GeoJSON LineString e PNG anotado (Pillow só para desenhar) |

### Uso

```bash
poetry run task linhas -- imagem.png --out saida/
# ou
poetry run python -m mod_tisosdocfly.linhas_plantio imagem.png --out saida/
```

A saída inclui `*_linhas.json`, `*_linhas.geojson` e `*_anotado.png`.

Na interface, a análise agro do tipo **lavoura/pastagem** tem o botão
**Linhas de plantio**, que roda em uma imagem do voo e mostra o resumo.

### Limites

- Processa no máximo 256 px no maior lado por padrão (Hough em Python puro).
- Linhas curvas não são suportadas.
- O resultado é triagem: valide espaçamento/falhas em campo.
- GeoJSON usa coordenadas de pixel; para coordenadas geográficas, informe o
  geotransform no CLI (`--geotransform X0 Y0 DX DY`).

## Relação com o restante do pipeline

- `avaliacao_imagens.py` mede cor/índices/bordas.
- `linhas_plantio.py` mede a **geometria** das fileiras.
- `multiespectral.py` mede bandas e índices (NDVI/SAVI...).
- `ia.py` e `relatorio.py` transformam tudo em laudo com revisão humana.
