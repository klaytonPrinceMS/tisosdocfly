# Manual do administrador

## Primeiro acesso

1. Entre com `master`/`master`.
2. O sistema abre a troca obrigatória: defina a nova senha e, se quiser,
   renomeie o login.
3. Depois da troca, o `master` nativo não retorna no próximo boot.

## Gestão de usuários

Rota `/users`:

- **Novo usuário:** login, senha, perfil global e nome completo.
- **Editar:** dados cadastrais, e-mail e telefone.
- **Senha:** redefine a senha de outro usuário.
- **Bloquear/Desbloquear:** impede login sem apagar a conta.
- **Excluir:** soft delete; o histórico permanece.
- **Sessões:** encerra uma ou todas as sessões de um usuário.
- **Acessos:** liga o papel `comum`/`administrador` por módulo.

## Painel do módulo

`/admin/usuarios` concentra configurações administrativas do módulo, incluindo
política de senha e backup.

## Segurança

- Sempre valide o perfil no servidor; esconder botão não é controle de acesso.
- Nunca commite `.env`, `db_mod_*.db` ou `poetry.toml`.
- Cadastre dados fictícios em teste.
