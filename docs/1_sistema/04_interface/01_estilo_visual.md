# Estilo visual

## Documentação

O site de documentação usa **MkDocs com o tema `readthedocs`**, em português,
com `search` e `mkdocstrings`. A configuração é `mkdocs.yml` na raiz; a saída
vai para `site/` (nunca versionado).

```bash
poetry run task docs        # build --strict
poetry run task docs:servir # servidor local
```

No boot, `main.py` chama `mod_tisosdocfly.documentacao` e monta `/documentacao`
quando `TISOSDOCFLY_DOCS_ATIVO` não for `0`.

## Interface da aplicação

- Layout de 4 partes: cabeçalho, menu lateral, conteúdo e rodapé.
- Tema por módulo lido de `tb_config` (`<chave>_cor_botao`, etc.).
- Componentes NiceGUI com Bootstrap/Tailwind/Quasar; **sem JavaScript solto**.
- `data-testid` em todo elemento que o QA precisa acionar.
- Mobile-first, foco visível e contraste AA.

Os textos e cores do login são configuráveis em `tb_config`; o padrão visual
do login é o mesmo da intranet.
