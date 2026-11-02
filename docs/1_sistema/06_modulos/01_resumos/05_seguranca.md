# Segurança Pública

Pacote: `src/mod_seguranca/` — chave de banco `seguranca` — rota `/seguranca`.

## Estado

MVP funcional (Onda 4 iniciada): triagem de voo, ocorrências, nível de risco e
revisão humana. Detecção por IA e integração com bases oficiais entram nas
próximas etapas.

## Banco

`db_mod_seguranca.db`:

| Tabela | Conteúdo |
|---|---|
| `tb_seguranca_analise` | voo, tipo, nível de risco, status, resumo |
| `tb_seguranca_ocorrencia` | classe, quantidade, confiança, revisão humana, evidência |

## Fluxo

1. Cadastre o voo em `/voos`.
2. Em `/seguranca`, clique em **Nova triagem**.
3. Informe tipo (aglomeração, pessoas, veículos, placas, objetos de risco,
   múltipla) e nível de risco.
4. Registre ocorrências (pessoa, aglomeração, veículo, placa, arma, criança
   em risco).
5. Marque **Revisar** em cada ocorrência e depois **Concluir**.

## Limite obrigatório

- Toda ocorrência é **triagem**, nunca veredito.
- Revisão humana é obrigatória antes de uso operacional.
- Reconhecimento de pessoas e consulta a listas exigem base legal, convênio
  oficial, finalidade específica, retenção limitada e auditoria.
- O sistema não decide culpa automaticamente e não expõe listas de terceiros.

## Próximas capacidades

- Detecção de aglomeração, pessoas, veículos e placas (OCR).
- Detecção de armas de fogo/brancas e crianças em risco.
- Confronto com bases oficiais de veículos e pessoas, com convênio.
- Relatório com evidência, confiança e trilha de revisão.
