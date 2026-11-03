# Graphify

O T! SOS DocFly usa o mesmo padrão da intranet: um grafo de conhecimento persistente
em `graphify-out/`, com nós de deus, comunidades e consultas.

## Instalação

O `graphifyy` fica no grupo **opcional** `graph` — não entra no `poetry install`
padrão porque é pesado:

```bash
poetry install --with graph
```

## Construção e atualização

```bash
# Construção por AST, sem chave de API (o caminho mais barato e comum)
poetry run graphify extract . --code-only

# Atualização incremental (só arquivos novos/alterados)
poetry run graphify update .

# Relatório de comunidades, sem gerar HTML
poetry run graphify cluster-only . --no-viz --no-label

# Diagnóstico de integridade
poetry run graphify diagnose
```

Equivalentes pelas tasks:

```bash
poetry run task grafo:extract
poetry run task grafo:update
poetry run task grafo:relatorio
poetry run task grafo:saude
```

Com `GEMINI_API_KEY` ou `GOOGLE_API_KEY` no ambiente, remova `--code-only` para
incluir a extração semântica de documentos e imagens.

## Consulta ao grafo

A skill `.opencode/skills/graphify/` e o plugin `.opencode/plugins/graphify.js`
fazem parte do projeto. Para perguntas de arquitetura, é possível consultar o
grafo em vez de varrer arquivos:

```bash
poetry run graphify query "Como o login chega ao cadastro de usuários?"
poetry run graphify path "autenticacao" "bd_manipulador"
poetry run graphify explain "pagina_restrita"
```

## Regra de ouro

O grafo é artefato de desenvolvimento. `graphify-out/` **nunca** é versionado
(está no `.gitignore` e no `.graphifyignore`).
