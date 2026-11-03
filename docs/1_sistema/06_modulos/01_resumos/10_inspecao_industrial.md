# Inspeção Industrial

Pacote: `src/mod_inspecao_industrial/` — chave de banco
`inspecao_industrial` — rota `/inspecao-industrial`.

## Estado

MVP funcional (Onda 5B): análise de voo, ocorrências, status e laudo textual.
A inferência por IA e o PDF entram nas próximas etapas.

## Banco

`db_mod_inspecao_industrial.db`:

| Tabela | Conteúdo |
|---|---|
| `tb_inspecao_analise` | voo, ativo, tipo, status, resumo |
| `tb_inspecao_ocorrencia` | classe, severidade, área, confiança, revisão humana, evidência |

## Fluxo

1. Cadastre cliente, propriedade e voo em `/voos`.
2. Em `/inspecao-industrial`, clique em **Nova análise** e selecione o voo.
3. Informe o ativo/TAG e o tipo (estrutura, torre, linha, tanque,
   equipamento, outro).
4. Registre ocorrências (corrosão, trinca, vazamento, deformação, vegetação,
   outro) com severidade e área afetada.
5. Marque a revisão humana e clique em **Concluir** para gerar o resumo do
   laudo.

## Regras

- Cada análise referencia um `voo_id` do núcleo via API pública
  (`mod_tisosdocfly.voos`); o módulo não faz cross-query.
- Ocorrência é **triagem**; `revisao_humana` registra a conferência.
- Nenhum dado de cliente/propriedade é copiado para o banco do módulo além
  dos IDs de referência.

## Próximas capacidades

- Detecção de corrosão, trincas e vazamentos por IA.
- Indicação de criticidade por tipo de ativo e priorização de manutenção.
- Comparativo entre inspeções e geração de PDF.
