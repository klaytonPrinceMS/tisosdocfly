# Manual — Gestão de Usuários

## Lista

`/users` lista os usuários com busca por nome/login, filtro por situação e
perfil. Cada linha oferece as ações permitidas ao seu papel.

A aba **Folha** é opcional: só aparece quando há dados de folha carregados no
banco. Sem ela, a lista e o cadastro continuam funcionando normalmente.

## Criar

1. Clique em **Novo**.
2. Informe login (`snake_case`, sem acento), senha, tipo de conta, perfil
   global e nome.
3. Libere os módulos na aba de acessos.

Usuário novo nasce sem acesso a módulo — a liberação é decisão explícita do
administrador.

### Tipo de conta

| Tipo | Para quem | Observação |
|---|---|---|
| `interno` | Equipe que opera a plataforma T! SOS DocFly | Pode receber perfil e papéis administrativos |
| `cliente` | Quem contrata laudo de voo (qualquer drone) | Nasce com perfil `comum` e sem acesso ao módulo `usuarios` |

Ao escolher **Cliente**, informe opcionalmente o **ID do cliente**: é uma
referência lógica ao cadastro do núcleo, usada para vincular a conta ao
contratante. O campo aceita apenas número inteiro positivo e não consulta o
banco do núcleo.

Conta cliente começa sem nenhum acesso a módulo. Depois de criada, o
administrador libera os módulos contratados e o papel de cada um.

## Editar

Na edição é possível trocar o tipo de conta e ajustar o ID do cliente. Ao
converter uma conta para **Cliente**, o sistema força o perfil global para
`comum` e remove o acesso ao módulo administrativo de usuários.

## Papéis

- `comum`: lê e opera o módulo conforme a tela.
- `administrador`: escreve, configura e administra o módulo.

O perfil `administrador_modulo` **não** substitui o papel no módulo.

## Sessões

A aba **Sessões** mostra IP, navegador e horário. Encerrar uma sessão derruba o
navegador correspondente no próximo request.

## Contas de fábrica

`qacomum` e `qamaster` são contas de teste. Não são removidas automaticamente;
quem decide é o administrador.
