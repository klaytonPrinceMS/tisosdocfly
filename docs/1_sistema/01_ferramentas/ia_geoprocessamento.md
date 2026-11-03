# IA, índices e geoprocessamento

Camada do núcleo que transforma as fotos **de qualquer drone** em medidas
reprodutíveis e em um laudo PDF. Ela é dividida em três módulos:

| Arquivo | Papel |
|---|---|
| `src/mod_tisosdocfly/avaliacao_imagens.py` | **avaliação padrão em Python puro**: decode PNG/BMP/PPM, métricas, índices, bordas, entropia e blobs |
| `src/mod_tisosdocfly/geoprocessamento.py` | RGB/índices via numpy, GSD, miniatura, EXIF e GeoTIFF opcional |
| `src/mod_tisosdocfly/ia.py` | registro de modelos; usa a avaliação pura como padrão |
| `src/mod_tisosdocfly/relatorio.py` | geração do laudo PDF em ReportLab |

## Avaliação pura em Python (padrão)

`avaliacao_imagens.avaliar_imagem(caminho)` não usa modelo, rede ou serviço
externo. O decode de **PNG/BMP/PPM** é feito com `zlib` e `struct` da stdlib;
**JPEG/WebP** usam o Pillow apenas para entregar os pixels (a conta continua
em Python). Imagens acima de 2 MP ou 8 MB também usam o Pillow só como
decoder, para não gastar segundos no unfilter puro.

| Recurso | Implementação |
|---|---|
| PNG 8/16 bits, RGB/RGBA/cinza/paleta | filtros 0-4 em Python puro |
| BMP 24/32 bits sem compressão | leitura direta em Python puro |
| PPM P6/P3 | leitura direta em Python puro |
| JPEG/WebP | decode pelo Pillow; métricas em Python puro |
| Amostragem | no máximo ~192 px no maior lado (determinística) |

Métricas entregues (todas em Python puro): `media_rgb`, `brilho`,
`contraste`, `saturacao_media`, `verde_ratio`, `marrom_ratio`, `cinza_ratio`,
`escuro_ratio`, `laranja_ratio`, `densidade_borda` (Sobel), `entropia`,
`ExG`, `VARI`, `GLI`, `TGI`, `vegetacao_ratio`, `blobs_verde`,
`blobs_escuro` e as razões do maior blob. O dicionário inclui
`metodo="python-puro"` e `fonte` (`python-puro` ou `pillow-decode`).

Nada aqui é um modelo treinado disfarçado. O repositório **não** traz pesos,
então a análise padrão é um **baseline por pixel**: mede a cena, aponta
hipóteses com limiar explícito e devolve `revisao_humana_obrigatoria=True`.
Quando existir um modelo homologado (ONNX/Torch), ele entra pela interface
descrita adiante e assume a análise.

## Baseline x modelo homologado

| | Avaliação pura | Modelo homologado |
|---|---|---|
| Origem | fórmulas de cor, borda e blobs | pesos treinados/validados |
| Resultado | hipótese de triagem | detecção com classe aprendida |
| Auditoria | limiar documentado neste arquivo | cartão do modelo, dataset e métricas |
| Revisão humana | obrigatória na maioria dos módulos | obrigatória em segurança pública |
| Dependência extra | **nenhuma** para PNG/BMP/PPM; Pillow só para JPEG | `onnxruntime` ou `torch` |

A avaliação **não simula** saída de rede neural: `modelo` fica
`"avaliacao-pura-v1"`, a confiança é derivada da distância ao limiar e
nenhuma classe é emitida quando o módulo não tem regra defensável.

## Métricas RGB

`carregar_rgb(caminho)` devolve `numpy.ndarray` `(altura, largura, 3)`,
`float32`, normalizado em `[0, 1]`. A normalização mantém as fórmulas
independentes de 8/16 bits e do formato do arquivo.

`metricas_rgb(caminho)` devolve:

| Chave | Definição |
|---|---|
| `media_rgb` | média de R, G e B (lista de 3 floats em `[0,1]`) |
| `brilho` | média da luminância Rec.601 `Y = 0,299R + 0,587G + 0,114B` |
| `contraste` | desvio-padrão de `Y` |
| `saturacao_media` | média de `S = (max-min)/max` (HSV) |
| `verde_ratio` | fração de pixels com `ExG > 0,10` |
| `marrom_ratio` | fração de solo/terra exposta (ver abaixo) |
| `cinza_ratio` | fração com saturação `< 0,12` |
| `escuro_ratio` | fração com `Y < 0,20` |
| `laranja_ratio` | fração compatível com chama (ver abaixo) |
| `densidade_borda` | fração de pixels com gradiente central `> 0,08` |

Definições de cor que evitam falsos positivos conhecidos:

- **marrom**: `R > G > B`, saturação `> 0,15`, `0,20 < R < 0,78` e `ExG < 0,12`.
  O teto de `R` separa terra de fogo/lava; sem ele, solo alaranjado virava
  "queimada".
- **laranja de queimada**: `R > 0,70`, `0,15 < G < 0,55`, `B < 0,30`,
  `R > 1,7·G` e `ExG < 0,05`. A razão `R/G` alta é o que distingue chama de
  solo exposto (razão ~1,2).

`densidade_borda` usa diferença central em X e Y e a magnitude
`sqrt(gx² + gy²)`. É o indício de trinca (vistoria) e de textura
(agro/obras), não um detector de fissura.

Imagens grandes são subamostradas por passo inteiro até 1024 px no maior
lado (`LADO_MAXIMO_ANALISE`) antes do cálculo — sem `resize`, que inventaria
pixels e alteraria a borda.

## Índices de vegetação

`indices_vegetacao(caminho)` usa **coordenadas cromáticas**
`r = R/(R+G+B)`, `g = G/(R+G+B)`, `b = B/(R+G+B)` e devolve a média de cada
índice, além de todas as métricas RGB:

| Índice | Fórmula | Referência |
|---|---|---|
| `ExG` | `2g - r - b` | Woebbecke et al. (1995) |
| `VARI` | `(g - r) / (g + r - b)` | Gitelson et al. (2002) |
| `GLI` | `(2g - r - b) / (2g + r + b)` | Louhaichi et al. (2001) |
| `TGI` | `(g - r) / (g + b - r)` | Hunt et al. (2011) |

Também sai `vegetacao_ratio` (fração com `ExG > 0,10`). `VARI` e `TGI` são
razões e podem explodir perto de zero; o código limita cada pixel a
`[-2, 2]` antes da média. São índices de **cor**, não de reflectância: sem
calibração de câmera/sol, só valem para comparação relativa dentro do mesmo
voo.

## GSD (ground sample distance)

```text
GSD_m  = (altitude_m × sensor_largura_mm) / (focal_mm × largura_px)
GSD_cm = GSD_m × 100
```

Exemplo: 100 m de altitude, sensor de 6,3 mm, focal de 4,5 mm e foto de
4000 px → `100 × 6,3 / (4,5 × 4000) = 0,035 m` → **3,5 cm/px**.

`gsd_cm` valida os quatro valores (numéricos, finitos e positivos) e levanta
`ValueError` fora disso — é conta pura, e devolver `None` esconderia erro de
cadastro do voo. `area_imagem_m2(largura_px, altura_px, gsd_cm_px)` usa o
mesmo GSD para estimar a área coberta pelo quadro.

`estatisticas_imagem` lê largura, altura, modo e EXIF básico via Pillow (sem
`piexif`): marca/modelo, data, exposição, abertura, ISO, focal e **apenas a
presença** de GPS (`gps_presente`), nunca as coordenadas.

`ler_geotiff` só existe de fato quando `rasterio` está instalado; sem ele
devolve `None`. `rasterio` **não** é dependência obrigatória.

## Baseline por módulo

Os limiares abaixo estão no código e são a fonte de verdade. Confiança é
`soma limitada a 0,92` conforme a distância do limiar; severidade vira
`baixa` (< 0,50), `media` (< 0,70) ou `alta`.

| Módulo | Classe | Regra |
|---|---|---|
| `agro` | `estresse_metabolico` | `ExG < 0,05` e `brilho > 0,22` |
| `agro` | `falha_plantio` | `ExG < 0,08` e `marrom_ratio > 0,35` |
| `agro` | `matocompeticao` | `verde_ratio > 0,55` e `densidade_borda > 0,18` |
| `vistoria_predial` | `trinca` | `densidade_borda > 0,22` |
| `vistoria_predial` | `infiltracao` | `escuro_ratio > 0,30` |
| `vistoria_predial` | `vegetacao` | `verde_ratio > 0,20` |
| `ambiental` | `desmatamento` | `marrom_ratio > 0,35` e `verde_ratio < 0,25` |
| `ambiental` | `queimada` | `laranja_ratio > 0,12` ou (`brilho > 0,65` e `laranja_ratio > 0,08`) |
| `obras` | `avanco` | `densidade_borda > 0,25` (confiança ≤ 0,45) |
| `obras` | `falha` | `contraste < 0,05` e `brilho < 0,35` (confiança ≤ 0,45) |
| `mapeamento` | — | nenhuma ocorrência; métricas + GSD |
| `seguranca` | — | nenhuma ocorrência; revisão obrigatória |
| `defesa_civil`, `inspecao_industrial`, `eventos` | — | conservador: métricas, zero classes, revisão obrigatória |

`area_m2` só é preenchida quando o contexto traz `gsd_cm` (ou
`altitude_m` + `sensor_largura_mm` + `focal_mm`). Sem GSD, a área fica `0.0`:
área desconhecida não vira número inventado.

### Contrato de retorno

```python
{
    "modelo": "avaliacao-pura-v1",
    "versao": "1.0",
    "confianca": 0.62,
    "resumo": "texto para o laudo",
    "metricas": {"ExG": 0.12, "brilho": 0.40, ...},
    "ocorrencias": [{
        "classe": "falha_plantio",
        "severidade": "media",
        "confianca": 0.62,
        "area_m2": 123.45,
        "evidencia": "marrom_ratio 0.81 (> 0,35)...",
    }],
    "revisao_humana_obrigatoria": True,
}
```

Qualquer modelo registrado passa por `_normalizar_resultado`: campo ausente é
preenchido, confiança fica em `[0, 1]`, área negativa vira `0`, severidade
desconhecida vira `indeterminada` e ocorrência sem classe é descartada.

## Por que segurança pública não usa baseline para pessoas/armas

Por limite obrigatório do produto: reconhecimento de pessoas e consulta a
listas exigem base legal, convênio oficial, retenção limitada, revisão humana
e auditoria. Cor e borda não identificam pessoa, veículo, placa ou arma — e
afirmar isso a partir de RGB seria decisão automática de culpa, exatamente o
que o produto não faz.

Sem modelo homologado, `analisar_imagem(..., "seguranca")` devolve
`ocorrencias=[]`, `confianca=0`, `revisao_humana_obrigatoria=True` e um resumo
que explica a ausência de detector homologado. O sistema entrega **triagem e
evidência**, nunca conclusão. Se um modelo for registrado com o nome
`seguranca`, ele passa a ser usado — mas o resultado continua sujeito ao
mesmo contrato e à revisão humana.

## Como plugar um modelo real

### Função Python (ONNX, Torch ou regra própria)

```python
from mod_tisosdocfly import ia

def modelo_agro(caminho, contexto):
    # contexto["_metricas"] e contexto["_estatisticas"] já vêm calculados;
    # contexto traz o que o chamador enviou (voo, gsd_cm, altitude_m, ...).
    return {
        "confianca": 0.81,
        "resumo": "CNN agro v2026.10: 3 manchas de estresse.",
        "ocorrencias": [{
            "classe": "estresse_metabolico",
            "severidade": "media",
            "confianca": 0.81,
            "area_m2": 42.0,
            "evidencia": "score 0.81 na janela 3 da ortofoto",
        }],
        "revisao_humana_obrigatoria": True,
    }

ia.registrar_modelo("agro", "cnn-2026.10", modelo_agro)
```

O nome do modelo é o **nome do módulo** (`agro`, `vistoria_predial`,
`ambiental`, ...). Registrar de novo substitui a versão anterior; use
`modelos_disponiveis()` para listar e `remover_modelo(nome)` para reverter ao
baseline (rollback).

### ONNX por variável de ambiente

```bash
export TISOSDOCFLY_MODELO_ONNX_AGRO=/dados/modelos/agro.onnx
# fallback para todos os módulos:
export TISOSDOCFLY_MODELO_ONNX=/dados/modelos/generico.onnx
```

`ia.modelo_onnx(caminho)` carrega a sessão com `onnxruntime` (opcional). Sem a
biblioteca ou sem o arquivo, devolve `None` e o baseline continua — nada
quebra. A inferência usa RGB, `float32`, NCHW e `[0,1]`, com entrada
`224×224` por padrão. O resultado expõe `indice_saida` e `probabilidade`
brutos: o **mapa de classes** precisa ser validado e traduzido pelo módulo que
registra o modelo; o núcleo não inventa rótulo semântico. A sessão ONNX só é
tentada uma vez por módulo (cache de falha), para não repetir IO.

## Laudo PDF

```python
from mod_tisosdocfly import relatorio

caminho = relatorio.gerar_pdf_laudo(
    "/tmp/laudo.pdf", "Laudo do voo #1", metadados, resumo,
    ocorrencias, imagens=[foto], metricas=metricas)

caminho = relatorio.gerar_pdf_modulo(
    "agro", "Laudo agro", metadados, resumo, ocorrencias, imagens=[foto])
```

- `gerar_pdf_laudo` grava no destino pedido; `gerar_pdf_modulo` grava em
  `src/mod_tisosdocfly/laudos/<chave>/<slug>.pdf`.
- `TISOSDOCFLY_DIR_LAUDOS` redireciona a raiz (a suíte usa isso para `/tmp`).
- Todo texto é escapado: `<b>` vindo do banco não vira marcação e
  `<script>` não executa.
- Laudo existente **nunca** é sobrescrito: o nome recebe
  `_AAAAMMDD_HHMMSS` (e sufixo numérico se necessário).
- Falha devolve `None`, registra a causa no loguru e remove o PDF parcial.
- A pasta `laudos/` é artefato de execução e deve ficar fora do git.

## Limitações conhecidas

- Índice RGB não substitui reflectância multiespectral nem NDVI calibrado.
- Borda alta pode ser telhado, cerca ou sombra — não é diagnóstico de trinca.
- `marrom_ratio`/`laranja_ratio` são sensíveis à exposição da câmera; compare
  imagens do mesmo voo e mesma hora.
- Sem GSD, não há área em m².
- `rasterio` e `onnxruntime` são opcionais e ausentes no ambiente padrão.
- O baseline é determinístico, mas **não** é laudo: toda saída pede revisão
  humana, e segurança pública nunca conclui culpa.

## Verificação

```bash
PYTHONPATH="$PWD/src:$PWD" poetry run python tests/teste_pipeline_ia.py
poetry run task lint
```

O teste gera imagens sintéticas (vegetação, seca, alto contraste e escura),
prova métricas/índices/GSD, os baselines de agro, vistoria, ambiental e
segurança, o registro de modelo plugável e um PDF real com mais de 1000
bytes.
