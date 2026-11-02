# Manual — Agropecuário

## Antes de começar

Cadastre cliente, propriedade e voo em `/voos`. A análise agropecuária sempre
parte de um voo.

## Criar análise

1. Abra `/agro`.
2. Clique em **Nova análise**.
3. Escolha o tipo: **lavoura**, **pastagem** ou **rebanho**.
4. Selecione o voo e informe talhão/piquete, cultura/pastagem, índice e área.
5. Em rebanho, informe as **cabeças** e a **área de pastagem**.
6. Para laudo de perdas/seguro, escolha a finalidade **seguro_agricola** e
   informe a **perda estimada (%)** e a **área afetada (ha)**.
7. Salve. A análise nasce como **Rascunho**.

## Linhas de plantio

Em análises de lavoura/pastagem, o botão **Linhas de plantio** roda o Hough
em uma imagem do voo e mostra total de linhas, ângulo e espaçamento. O
resultado é triagem; linhas curvas não são suportadas.

## Rebanho e pastagem

O capítulo da Embrapa (2024) recomenda separar operação, sensores e validação
do modelo. No Skyrover:

- a contagem de cabeças é **declarada/revisada** — o baseline de cor não
  conta animais;
- ocorrências de gado usam as classes `contagem_gado`, `animal_isolado`,
  `aglomeracao_animal`, `animal_caido`, `pastagem_degradada` e `sombra_agua`;
- contagem automática exige detector treinado e validação em campo.

Consulte [Embrapa — drones e gado](../../1_sistema/10_projeto/04_referencias/embrapa_drones_gado.md).

## Ocorrências

Cada achado é uma ocorrência com classe, severidade, área afetada, confiança e
evidência. Marque **Revisado por humano** quando a equipe conferir.

## Concluir

O botão **Concluir** muda o status para **Concluído** e grava o resumo do
laudo. O PDF e os mapas entram na próxima etapa.

## Boas práticas

- Use um voo por data/talhão para permitir comparativo.
- Não use dado real de pessoa em teste; use massa fictícia.
- Confira o índice espectral antes de interpretar o resultado.
