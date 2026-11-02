# Eventos

Pacote: `src/mod_eventos/` — chave de banco `eventos` — rota `/eventos`.

## Estado

MVP funcional (Onda 5B): análise de voo, ocorrências, público estimado,
status e laudo textual. A inferência por IA e o PDF entram nas próximas
etapas.

## Banco

`db_mod_eventos.db`:

| Tabela | Conteúdo |
|---|---|
| `tb_eventos_analise` | voo, evento, tipo, público estimado, status, resumo |
| `tb_eventos_ocorrencia` | classe, severidade, quantidade, confiança, revisão humana, evidência |

## Fluxo

1. Cadastre cliente, propriedade e voo em `/voos`.
2. Em `/eventos`, clique em **Nova análise** e selecione o voo.
3. Informe o evento, o tipo (público, fluxo, ocupação, multidão, outro) e o
   público estimado.
4. Registre ocorrências (aglomeração, fluxo, saída de emergência, obstrução,
   outro) com severidade e quantidade.
5. Marque a revisão humana e clique em **Concluir** para gerar o resumo do
   laudo.

## Regras

- Cada análise referencia um `voo_id` do núcleo via API pública
  (`mod_skyrover.voos`); o módulo não faz cross-query.
- Ocorrência é **triagem**; `revisao_humana` registra a conferência.
- Nenhum dado de cliente/propriedade é copiado para o banco do módulo além
  dos IDs de referência.

## Próximas capacidades

- Contagem de público e detecção de aglomeração por IA.
- Mapa de fluxo e capacidade por área do evento.
- Comparativo entre edições e geração de PDF.
