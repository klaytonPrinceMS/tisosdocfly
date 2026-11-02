# Vistoria Predial

Pacote: `src/mod_vistoria_predial/` — chave de banco `vistoria_predial` — rota
`/vistoria-predial`.

## Estado

MVP funcional (Onda 3 iniciada): vistoria, patologias, severidade e laudo
textual. Comparativo temporal e PDF entram nas próximas etapas.

## Banco

`db_mod_vistoria_predial.db`:

| Tabela | Conteúdo |
|---|---|
| `tb_vistoria` | voo, imóvel, tipo, status, resumo |
| `tb_vistoria_patologia` | tipo, severidade, área, descrição, revisão humana |

## Fluxo

1. Cadastre o voo em `/voos`.
2. Em `/vistoria-predial`, clique em **Nova vistoria**.
3. Informe imóvel e tipo (`fachada`, `telhado`, `estrutural`, `completa`).
4. Registre patologias: trinca, infiltração, mancha, vegetação, corrosão,
   desplacamento.
5. **Concluir** gera o resumo do laudo.

## Regras

- Cada vistoria referencia um voo do núcleo; sem cross-query.
- Patologia é **triagem visual**; a severidade e a revisão humana são
  registradas separadamente.
- O módulo não substitui laudo de responsável técnico habilitado.

## Próximas capacidades

- Detecção automática de trinca, infiltração e vegetação invasora.
- Comparativo entre vistorias do mesmo imóvel.
- Mapa de calor de severidade e PDF com evidências.
