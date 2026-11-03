# Manual — Mapeamento

## Antes de começar

Cadastre cliente, propriedade e voo em `/voos`. A análise de mapeamento sempre
parte de um voo registrado no T! SOS DocFly.

## Criar análise

1. Abra `/mapeamento`.
2. Clique em **Nova análise**.
3. Selecione o voo e informe área em hectares, GSD em cm/px, tipo e resumo.
4. Salve. A análise nasce como **Rascunho**.

## Produtos

Cada produto tem nome, formato (GeoTIFF, COG, GeoJSON, PDF ou outro), caminho,
SHA-256 e confiança. O arquivo continua fora do banco; o registro guarda os
metadados e o hash para conferência de integridade.

## Concluir

O botão **Concluir** muda o status para **Concluído** e grava o resumo do
laudo. A geração de ortomosaico e a publicação do catálogo entram na próxima
etapa.

## Boas práticas

- Confira o GSD e a área antes de registrar o produto.
- Guarde o SHA-256 do arquivo entregue; ele é a referência de integridade.
- Não use dado real de pessoa em teste; use massa fictícia.
