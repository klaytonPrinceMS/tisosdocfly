# Obras

Pacote: `src/mod_obras/` — chave de banco `obras` — rota `/obras`.

## Estado

MVP textual: análise de avanço, ocorrências, revisão humana e laudo resumido.
Medição automática, curva S e PDF entram na próxima etapa.

## Banco

`db_mod_obras.db`:

| Tabela | Conteúdo |
|---|---|
| `tb_obras_analise` | voo, obra, etapa, progresso, status, resumo |
| `tb_obras_ocorrencia` | classe, severidade, área, confiança, revisão humana, evidência |

## Fluxo

1. Cadastre cliente, propriedade e voo em `/voos`.
2. Em `/obras`, clique em **Nova análise** e selecione o voo.
3. Informe obra, etapa (fundação, estrutura, alvenaria, acabamento, entrega
   ou outra), progresso percentual e resumo.
4. Registre ocorrências (avanço, atraso, falha, material ou outro) com
   severidade, área afetada, confiança e evidência.
5. **Concluir** grava o resumo do laudo de obra.

## Regras

- Cada análise referencia um `voo_id` do núcleo via API pública
  (`mod_skyrover.voos`); o módulo não faz cross-query.
- Ocorrência é **triagem**; `revisao_humana` registra a conferência.
- Progresso é declarado pela equipe na etapa atual do MVP; não é medição
  automática.

## Próximas capacidades

- Comparativo entre voos para medir avanço real.
- Detecção de atraso, falha e material acumulado.
- Curva S, marcos contratuais e alertas.
- Geração de PDF e relatório fotográfico.
