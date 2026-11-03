# Visão de produto — T! SOS DocFly

## O que é

O **T! SOS DocFly** é uma plataforma de laudos de voo **multidrone**: aceita
fotos e vídeos capturados por qualquer drone. O cliente entra com usuário e
senha, **envia fotos e vídeos do voo** e, dentro dos módulos contratados,
**gera laudos técnicos** a partir dos arquivos capturados.

O laudo é o produto vendido. O drone é o instrumento — de qualquer marca ou
modelo; o software transforma a captura bruta em evidência organizada,
mensurável e auditável.

## Jornada do usuário

```
Login
  └─ Cliente / propriedade / talhão
       └─ Voo (data, piloto, drone, plano de voo, GSD)
            └─ Upload de fotos e vídeos
                 └─ Processamento (mosaico, índices, modelos)
                      └─ Laudo (PDF + mapa + evidências)
                           └─ Histórico e comparativo entre voos
```

Cada etapa precisa de rastreabilidade: quem enviou, quando, com qual
equipamento, qual modelo/versão analisou e qual foi o resultado. Sem isso o
laudo não é defensável.

## Módulos de negócio

### Implementados

| Módulo | Papel | Estado |
|---|---|---|
| `mod_tisosdocfly` | Núcleo: contas, sessões, tema, configurações, documentação, voos e mídia | Funcional |
| `mod_gest_cad_usuario` | Cadastro de usuários, perfis e papéis | Funcional |
| `mod_agro` | Lavoura, pastagem e rebanho (contagem declarada/revisada) | MVP |
| `mod_vistoria_predial` | Vistoria, patologias e laudo textual | MVP |
| `mod_seguranca` | Triagem de segurança com revisão humana | MVP |
| `mod_ambiental` | Desmatamento, APP, queimada e recuperação | MVP |
| `mod_obras` | Avanço físico, ocorrências e medição | MVP |
| `mod_mapeamento` | Ortomosaico, topografia e produtos geoespaciais | MVP |
| `mod_defesa_civil` | Dano pós-desastre e risco geológico | MVP |
| `mod_inspecao_industrial` | Estruturas, torres, linhas e equipamentos | MVP |
| `mod_eventos` | Público, fluxo, ocupação e multidão | MVP |
| `mod_perimetro` | Perímetro físico/lógico, câmeras, cercas, iluminação e Wi-Fi/RF | MVP |

> **MVP** significa: banco próprio, CRUD, telas, ocorrências e laudo textual.
> A inferência por IA/visão computacional e o PDF entram nas ondas seguintes.

Novos módulos seguem o padrão do projeto: pacote próprio, banco próprio, sem
cross-query, registrados em `MODULOS_BD` e `MODULOS_SISTEMA`.

## Módulo agropecuário

Capacidades esperadas:

- **Estresse metabólico precoce** por reflectância foliar e índices
  (NDVI, NDRE, GNDVI, NDWI, SAVI).
- **Ferrugem asiática da soja**, **oídio** e **nematoides** — detecção por
  padrão espectral e modelos convolucionais.
- Monitoramento sanitário em **tomate, milho, café, banana e frutíferas**.
- **Falhas de plantio**, **contagem automática de plantas**, **cálculo de
  estande** e **mapa de falhas** logo após a emergência.
- **Matocompetição**: reboleiras de plantas daninhas.
- **Topografia de solo** e apoio a curvas de nível.
- Comparativo entre safras e entre talhões.

Saídas típicas: mapa de índice, mapa de classes, contagem por talhão,
percentual de falha, ranking de risco e laudo em PDF com metodologia e data.

## Módulo de vistoria predial

- Fachadas, telhados, calhas, reservatórios e estruturas.
- Detecção de trincas, manchas, infiltração, vegetação invasora e
  patologias aparentes.
- Comparação temporal entre vistorias.
- Laudo com foto, localização, classificação de severidade e recomendação.

## Módulo de segurança pública

- **Aglomeração de pessoas**: densidade e pontos de alta concentração.
- **Pessoas e placas**: detecção e leitura (OCR) para apoio operacional.
- **Veículos**: classificação e consulta a bases públicas de veículos
  furtados/roubados.
- **Objetos de risco**: armas de fogo e armas brancas.
- **Crianças em potencial risco**: alerta com revisão humana obrigatória.
- **Listas de procurados**: confronto com bases oficiais, quando houver base
  legal e convênio.

> **Limite jurídico e ético (obrigatório).** Reconhecimento facial, base de
> “ladrões/pedófilos” e qualquer lista de pessoas exigem base legal,
> convênio oficial, finalidade específica, retenção limitada e revisão humana.
> O sistema **não** toma decisão automatizada de culpa, não expõe lista de
> terceiros e não substitui autoridade policial. O que a plataforma entrega é
> **triagem e evidência**, com trilha de auditoria e acesso restrito.

## Pipeline de IA e visão computacional

```
1. Ingestão         upload, hash, EXIF, geotag, vínculo com o voo
2. Pré-processo     correção de lente, alinhamento, recorte, tiling
3. Geoprocessamento ortomosaico, DSM, índices espectrais, GSD
4. Inferência       modelos por módulo (CNN, detecção, segmentação)
5. Pós-processo     NMS, limiar, agrupamento, contagem, área
6. Laudo            mapa, tabela, gráfico, evidência, PDF
7. Auditoria        modelo, versão, parâmetros, insumo, resultado
```

Requisitos técnicos que decorrem disso:

- **Versionamento de modelo** e de dataset. Laudo antigo precisa ser
  reproduzível com o modelo que o gerou.
- **Fila de inferência** separada do processo web (GPU/worker), com status e
  retry.
- **Armazenamento de mídia** fora do banco, com hash e política de retenção.
- **Processamento geoespacial** (GDAL/rasterio/OpenCV) como serviço.
- **Explicabilidade mínima**: o laudo mostra a evidência que sustenta cada
  apontamento.

## Requisitos não funcionais

| Requisito | Diretriz |
|---|---|
| Privacidade | LGPD: finalidade, minimização, retenção, exclusão e acesso auditado |
| Rastreabilidade | quem, quando, qual voo, qual arquivo, qual modelo, qual versão |
| Reprodutibilidade | laudo guarda parâmetros e versão do modelo |
| Segurança | papéis por módulo, sessão revogável, criptografia em trânsito |
| Disponibilidade | processamento pesado fora do event-loop web |
| Escala | mídia em object storage; banco só com metadados |
| Offline/edge | possibilidade de inferência embarcada ou em servidor local |
| Auditabilidade | trilha imutável de acesso a mídia e a laudo |

## O que NÃO é

- Não é um sistema de decisão automática de culpa.
- Não é um repositório livre de imagens de pessoas.
- Não substitui laudo de responsável técnico habilitado.
- Não garante diagnóstico fitossanitário sem validação de campo.
