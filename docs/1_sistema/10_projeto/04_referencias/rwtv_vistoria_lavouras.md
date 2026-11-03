# RWTV/Epagri — vistoria de lavouras com drone

Referência aplicada ao módulo agro.

## Fonte

- **Vídeo:** Agricultura de precisão: vistoria de lavouras com drone
- **Canal:** Rede Web TV — RWTV
- **URL:** <https://www.youtube.com/watch?v=PWe6VEWMh3U>
- **Tema:** projeto de pesquisa com drones multiespectrais e térmicos para
  vistoria de lavoura e laudo de perdas para seguro agrícola.

## O que o vídeo apresenta

- Projeto aprovado no edital Universal do CNPq, com Epagri, IPAG e cadeias
  produtivas.
- Uso de **imagens multiespectrais e térmicas** para compor um **protocolo de
  vistoria de lavoura**, com foco em **seguro agrícola** e laudo de perdas.
- Culturas citadas: **maçã, mandioca, banana**; também solos.
- Objetivo: apoiar o extensionista, otimizar amostragem e dar embasamento
  técnico-científico ao laudo de perdas.
- Aplicações:
  - mapeamento de falhas e problemas que não se vê a olho nu;
  - saúde das plantas e identificação precoce de doenças;
  - **banana**: padrões de folhas sadias/doentes (ex.: Sigatoka amarela);
  - **maçã**: infecção antes do sintoma visível e identificação varietal por
    reflectância;
  - **irrigação**: câmera térmica para áreas com muita/pouca umidade;
  - drenagem e escoamento para evitar acúmulo de água;
  - contagem de plantas e animais;
  - fertilização, pulverização localizada, queimadas e vigilância da fazenda.
- Pré-processamento em laboratório/escritório com máquina de alta capacidade:
  calibração, **reflectância**, alinhamento de fotos e **ortomosaico**.
- Atributos de solo (areia, silte, argila) por comportamento espectral.

## O que foi aplicado no T! SOS DocFly

### Finalidade e laudo de perdas

`mod_agro` ganhou:

- `finalidade` (`producao`, `seguro_agricola`, `vistoria`, `pesquisa`);
- `perda_estimada_pct`;
- `area_afetada_ha`.

A tela `/agro` mostra a finalidade e a perda no cartão da análise e um card
com a **perda média** das análises.

### Culturas e classes

- Culturas incluídas: `maca`, `mandioca`, `uva` (além de soja, milho, tomate,
  café, banana e frutíferas).
- Classes de ocorrência: `doenca_foliar`, `deficit_hidrico`,
  `excesso_umidade`.

### Pipeline compatível

- `multiespectral.py` calcula NDVI/SAVI/NDRE/GNDVI/NDWI e estatísticas por
  banda — base para doença/umidade/reflectância.
- `linhas_plantio.py` mede falhas e espaçamento de fileiras.
- A banda térmica (`T`) é aceita no agrupamento multiespectral; o laudo PDF
  registra modelo/versão e ocorrências.
- O laudo de perdas usa a perda estimada e a área afetada informadas/revisadas
  pelo técnico.

### O que ainda depende de pesquisa/parceria

- Calibração de reflectância com painel/referência.
- Modelos de doença por cultura (banana/maçã) treinados e validados.
- Mapeamento de areia/silte/argila por espectro.
- Protocolo de seguro agrícola acordado com a seguradora.
- Validação em campo com extensionistas e produtores.

## Limite

O vídeo descreve **pesquisa em andamento**, não um produto validado. O
T! SOS DocFly implementa a infraestrutura (bandas, índices, vistoria, laudo e
revisão humana); a transformação em laudo de perda aceito por seguradora
exige protocolo e validação externos.
