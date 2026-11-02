# Defesa Civil

Pacote: `src/mod_defesa_civil/` — chave de banco `defesa_civil` — rota
`/defesa-civil`.

## Estado

MVP funcional (Onda 5B): análise de voo, ocorrências, status e laudo textual.
A inferência por IA e o PDF entram nas próximas etapas.

## Banco

`db_mod_defesa_civil.db`:

| Tabela | Conteúdo |
|---|---|
| `tb_defesa_civil_analise` | voo, local, tipo, status, resumo |
| `tb_defesa_civil_ocorrencia` | classe, severidade, área, confiança, revisão humana, evidência |

## Fluxo

1. Cadastre cliente, propriedade e voo em `/voos`.
2. Em `/defesa-civil`, clique em **Nova análise** e selecione o voo.
3. Informe o local e o tipo (enchente, deslizamento, vendaval, incêndio,
   estrutural, outro).
4. Registre ocorrências (dano estrutural, via bloqueada, risco geológico,
   telhado, outro) com severidade e área afetada.
5. Marque a revisão humana e clique em **Concluir** para gerar o resumo do
   laudo.

## Regras

- Cada análise referencia um `voo_id` do núcleo via API pública
  (`mod_skyrover.voos`); o módulo não faz cross-query.
- Ocorrência é **triagem**; `revisao_humana` registra a conferência.
- Nenhum dado de cliente/propriedade é copiado para o banco do módulo além
  dos IDs de referência.

## Próximas capacidades

- Detecção de áreas alagadas, deslizamentos e telhados comprometidos por IA.
- Comparativo antes/depois do desastre e mapa de criticidade.
- Integração com alertas oficiais e geração de PDF.
