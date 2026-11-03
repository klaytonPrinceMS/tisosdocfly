# Gestão de Usuários

Pacote: `src/mod_gest_cad_usuario/` — chave de banco `usuarios`.

## Responsabilidade

Cadastro de contas, perfis globais, papéis por módulo e sessões.

| Arquivo | Papel |
|---|---|
| `bd_manipulador.py` | Único acesso ao banco do módulo; CRUD, seed, papéis |
| `telas.py` | Tela `/users`: lista, busca, criação, edição, sessões |
| `telas_administracao.py` | Painel `/admin/usuarios` |
| `bd_criador.py` | Legado — o schema real vem do `init_db` do `bd_manipulador` |

## Banco

`db_mod_gest_cad_usuario.db`:

- `tb_usuarios` — conta, perfil global, ativo, soft delete, tipo de conta e
  vínculo com cliente;
- `tb_acesso_usuario` — papel por módulo (`comum`/`administrador`);
- `tb_modulo_perfil` — metadados de perfil.

## Tipo de conta e vínculo com cliente

Desde 02/11/2026 a conta tem um eixo próprio, independente do perfil global e
do papel por módulo:

| Campo | Valores | Significado |
|---|---|---|
| `user_tipo` | `interno` (padrão) | Equipe que opera a plataforma T! SOS DocFly |
| `user_tipo` | `cliente` | Contratante do laudo de voo (qualquer drone) |
| `cliente_id` | inteiro ou vazio | Referência lógica ao cliente do núcleo |

`cliente_id` é **referência lógica**, não FK entre bancos: este módulo nunca
consulta o banco do núcleo (cada módulo tem o próprio banco: nunca há
cross-query). O vínculo é informado pelo
administrador na tela e validado apenas como inteiro positivo.

### Garantias da conta cliente

- Nasce **sempre** com perfil global `comum`, mesmo que o chamador tente
  informar um perfil administrativo.
- Nasce **sem acesso ao módulo `usuarios`** e sem acesso padrão a nenhum
  outro módulo. A liberação dos módulos contratados é decisão explícita do
  administrador.
- Ao converter uma conta existente para `cliente`, o backend rebaixa o perfil
  para `comum` e remove a linha de acesso ao módulo `usuarios` na mesma
  transação.

As colunas são criadas por migração idempotente check-then-add em
`_init_db_seguro`, portável entre SQLite e PostgreSQL. Rodar `init_db` duas
vezes não altera schema nem dados.

## Perfis e papéis

São dois eixos independentes:

| Eixo | Valores | Onde |
|---|---|---|
| Perfil global | `comum`, `administrador_modulo`, `administrador_geral` | `tb_usuarios.user_perfil` |
| Papel no módulo | `comum`, `administrador` | `tb_acesso_usuario.papel` |

`administrador_modulo` **não** dá escrita em módulo nenhum: escrita exige a
linha em `tb_acesso_usuario`.

## Seed

O `init_db` é idempotente e cria:

| Usuário | Senha | Perfil | Tipo | Troca forçada |
|---|---|---|---|---|
| `master` | `master` | `administrador_geral` | `interno` | Sim (senha + credenciais) |
| `qacomum` | `123456` | `comum` | `interno` | Não |
| `qamaster` | `123456` | `administrador_geral` | `interno` | Não |

As contas de fábrica nunca são removidas automaticamente. Quem decide é o
administrador.

## Folha de pagamento (opcional)

A folha deixou de ser distribuída com o produto de laudos. O código histórico
(`dados/`, `fonte_folha.json`, coleta e carga) continua no módulo, mas a tela
de usuários não depende dele: a aba **Folha** só aparece quando existe algum
contrato, movimento ou histórico salarial no banco. Sem esses dados, `/users`
e `/admin/usuarios` continuam utilizáveis.

