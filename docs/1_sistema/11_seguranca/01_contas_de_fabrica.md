# Contas de fábrica

O seed de `mod_gest_cad_usuario/bd_manipulador.py` cria três contas conhecidas,
de forma idempotente. Elas existem na entrega e **permanecem**; a decisão de
manter ou apagar é do administrador.

| Conta | Senha | Perfil | Comportamento |
|---|---|---|---|
| `master` | `master` | `administrador_geral` | Primeiro login força troca de senha **e** de credenciais (renomeia o login) |
| `qacomum` | `123456` | `comum` | Conta de QA; sem troca forçada |
| `qamaster` | `123456` | `administrador_geral` | Conta de QA; sem troca forçada |

## O que o sistema garante

- **Não** apaga, desativa ou renomeia `qacomum`/`qamaster` por conta própria.
- **Não** trata a troca de credenciais do `qamaster` como obrigatória; a
  regra de troca vale para o `master` nativo.
- O `master` nativo, depois de renomeado, não volta no próximo boot: o
  marcador `forcar_troca_credenciais:master` impede a recriação.

## O que nunca fazer

- Colocar senha de desenvolvimento em `docs/` ou `README.md`.
  A senha pode estar no **código**; na documentação, não.
- Usar dado de pessoa real em teste ou exemplo. Use `MT-1234`.
