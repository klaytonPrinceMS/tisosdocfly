# Ambiental

Pacote: `src/mod_ambiental/` — chave de banco `ambiental` — rota `/ambiental`.

## Estado

MVP textual: análise de voo, ocorrências, revisão humana e laudo resumido.
Visão computacional, índices de vegetação e PDF entram na próxima etapa.

## Banco

`db_mod_ambiental.db`:

| Tabela | Conteúdo |
|---|---|
| `tb_ambiental_analise` | voo, área, tipo, status, resumo, autor e data |
| `tb_ambiental_ocorrencia` | classe, severidade, área, confiança, revisão humana, evidência |

## Fluxo

1. Cadastre cliente, propriedade e voo em `/voos`.
2. Em `/ambiental`, clique em **Nova análise** e selecione o voo.
3. Informe área, tipo (desmatamento, APP, queimada, recuperação ou outro) e
   resumo.
4. Registre ocorrências (desmatamento, queimada, APP, erosão ou outro) com
   severidade, área afetada, confiança e evidência.
5. **Concluir** grava o resumo do laudo ambiental.

## Regras

- Cada análise referencia um `voo_id` do núcleo via API pública
  (`mod_tisosdocfly.voos`); o módulo não faz cross-query.
- Ocorrência é **triagem**; `revisao_humana` registra a conferência.
- Nenhum dado de cliente/propriedade é copiado para o banco do módulo além
  dos IDs de referência.

## Próximas capacidades

- Detecção de desmatamento e APP por comparativo entre voos.
- Mapa de cicatriz de queimada e classificação de severidade.
- Recuperação de área degradada com série temporal.
- Geração de PDF e relatório geoespacial.
