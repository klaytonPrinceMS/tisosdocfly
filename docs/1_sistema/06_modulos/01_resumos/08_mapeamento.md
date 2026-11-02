# Mapeamento

Pacote: `src/mod_mapeamento/` — chave de banco `mapeamento` — rota
`/mapeamento`.

## Estado

MVP textual: análise de voo, catálogo de produtos geoespaciais e laudo
resumido. Geração de ortomosaico, COG e validação de hash entram na próxima
etapa.

## Banco

`db_mod_mapeamento.db`:

| Tabela | Conteúdo |
|---|---|
| `tb_mapeamento_analise` | voo, área, GSD, tipo, status, resumo |
| `tb_mapeamento_produto` | nome, formato, caminho, SHA-256, confiança |

## Fluxo

1. Cadastre cliente, propriedade e voo em `/voos`.
2. Em `/mapeamento`, clique em **Nova análise** e selecione o voo.
3. Informe área, GSD e tipo (ortomosaico, topografia, volumetria ou outro).
4. Registre produtos (GeoTIFF, COG, GeoJSON, PDF ou outro) com caminho,
   SHA-256 e confiança.
5. **Concluir** grava o resumo do laudo de mapeamento.

## Regras

- Cada análise referencia um `voo_id` do núcleo via API pública
  (`mod_skyrover.voos`); o módulo não faz cross-query.
- O produto guarda apenas metadados e o caminho; o arquivo continua fora do
  banco.
- O SHA-256 é a referência de integridade para entrega e conferência.

## Próximas capacidades

- Geração de ortomosaico a partir das capturas do voo.
- Conversão para COG e publicação em catálogo.
- Volumetria, curvas de nível e cálculo de área.
- Geração de PDF e pacote de entrega.
