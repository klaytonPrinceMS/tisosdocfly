# Manual — T! SOS DocFly (núcleo)

## Configurações

`/configuracoes` reúne:

- identidade visual (título, ícone, cores, textos do login);
- segurança (timeout de sessão, captcha);
- banco (SQLite/PostgreSQL);
- observabilidade (log, OTel);
- documentação (reconstruir);
- módulos (ligar/desligar, ordem, rota).

## Módulos

Só o módulo `usuarios` nasce ligado. Os demais são cadastrados em
`MODULOS_SISTEMA` e podem ser ligados pelo administrador.

## Documentação

O botão **Reconstruir documentação** roda `mkdocs build` e remonta
`/documentacao`. O build também roda no boot quando `TISOSDOCFLY_DOCS_ATIVO` não
for `0`.

## Auditoria

A trilha fica em `tb_auditoria` do banco central e registra ator, módulo, ação,
descrição, IP e navegador. `audit_log` nunca derruba a ação do usuário por
falha de gravação.
