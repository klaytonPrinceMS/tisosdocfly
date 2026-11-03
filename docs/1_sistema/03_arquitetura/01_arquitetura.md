# Arquitetura modular

## Camadas

```
main.py                 # entry point: rotas centrais e boot
src/mod_tisosdocfly/       # núcleo
src/mod_gest_cad_usuario/  # módulo de negócio
src/assets/             # CSS, favicon e imagens embarcados
tests/                  # runner + testes standalone + E2E
docs/                   # MkDocs (tema readthedocs)
```

## Regra de isolamento

- Cada módulo tem o **próprio banco**. Nada de cross-query.
- A comunicação entre módulos passa pela API pública do núcleo.
- `bd_manipulador.py` é o único ponto de acesso ao banco do módulo.
- O núcleo não importa módulo de negócio em nível de topo; usa hooks e imports
  lazy para evitar ciclo.

## Estrutura obrigatória de um módulo

```
src/mod_<nome>/
├── __init__.py
├── bd_manipulador.py
├── telas.py
└── telas_administracao.py
```

`mod_tisosdocfly` acrescenta `bd_conexao.py`, `banco_conexao.py`,
`repositorio.py`, `models/`, `autenticacao.py`, `tema_modulo.py`,
`tela_configuracoes.py` e `documentacao.py`.

## Bancos

| Chave | Arquivo SQLite | Módulo |
|---|---|---|
| `tisosdocfly` | `db_mod_tisosdocfly.db` | Núcleo (voos, mídia, laudo base) |
| `usuarios` | `db_mod_gest_cad_usuario.db` | Gestão de usuários |
| `agro` | `db_mod_agro.db` | Agropecuário |
| `vistoria_predial` | `db_mod_vistoria_predial.db` | Vistoria predial |
| `seguranca` | `db_mod_seguranca.db` | Segurança pública |
| `ambiental` | `db_mod_ambiental.db` | Ambiental |
| `obras` | `db_mod_obras.db` | Obras |
| `mapeamento` | `db_mod_mapeamento.db` | Mapeamento |
| `defesa_civil` | `db_mod_defesa_civil.db` | Defesa civil |
| `inspecao_industrial` | `db_mod_inspecao_industrial.db` | Inspeção industrial |
| `eventos` | `db_mod_eventos.db` | Eventos |

Com `banco_tipo=postgres`, cada chave vira um database PostgreSQL com o mesmo
nome, sem `.db`. Toda DDL nova precisa funcionar nos dois backends — o proxy
em `banco_conexao.py` traduz o SQL.

## Registro de um módulo novo

1. Criar o pacote em `src/mod_<nome>/`.
2. Adicionar a chave em `MODULOS_BD` (`repositorio.py`).
3. Adicionar a tupla em `MODULOS_SISTEMA` (`autenticacao.py`) com nome, ícone e
   rota.
4. Chamar o `init_db` do módulo em `mod_tisosdocfly/bd_criador.py`.
5. Criar a rota em `main.py` passando por `pagina_restrita`.
