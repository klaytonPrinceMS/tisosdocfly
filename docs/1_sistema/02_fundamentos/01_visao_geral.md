# Visão geral

O T! SOS DocFly nasce como uma aplicação web modular em Python. A arquitetura repete
o padrão já validado na intranet:

- **Entry point único:** `main.py` na raiz.
- **Um pacote por funcionalidade:** `src/mod_<nome>/`.
- **Um banco por módulo:** `db_mod_<chave>.db` (SQLite) ou um database
  `db_mod_<chave>` (PostgreSQL). Nunca cross-query entre bancos.
- **Núcleo explícito:** `mod_tisosdocfly` concentra configuração, autenticação,
  tema, layout, sessões, auditoria e documentação.
- **Módulos de negócio** conversam com o núcleo apenas pela API pública.

## Módulos iniciais

### `mod_tisosdocfly` (núcleo)

- Banco central `db_mod_tisosdocfly.db`: `tb_config`, `tb_sessoes`,
  `tb_modulos`, `tb_auditoria`.
- Autenticação com `bcrypt`, sessões revogáveis e bloqueio por tentativas.
- Tema por módulo, layout de 4 partes, `pagina_restrita` e troca obrigatória
  de credenciais.
- Configurações (`/configuracoes`) e documentação (`/documentacao`).

### `mod_gest_cad_usuario`

- Banco próprio `db_mod_gest_cad_usuario.db`.
- `tb_usuarios`, `tb_acesso_usuario` (papel por módulo), `tb_modulo_perfil`.
- Seed idempotente das contas de fábrica.
- Telas `telas.py` (uso) e `telas_administracao.py` (painel do módulo).

### Módulos de negócio em MVP

| Módulo | Banco | O que já faz |
|---|---|---|
| `mod_agro` | `db_mod_agro.db` | análise por voo/talhão/cultura/índice, ocorrências e laudo textual |
| `mod_vistoria_predial` | `db_mod_vistoria_predial.db` | vistoria, patologias e laudo textual |
| `mod_seguranca` | `db_mod_seguranca.db` | triagem, ocorrências, revisão humana e limite jurídico |
| `mod_ambiental` | `db_mod_ambiental.db` | desmatamento, APP, queimada e recuperação |
| `mod_obras` | `db_mod_obras.db` | avanço, ocorrências e medição |
| `mod_mapeamento` | `db_mod_mapeamento.db` | ortomosaico, topografia e produtos |
| `mod_defesa_civil` | `db_mod_defesa_civil.db` | dano pós-desastre e risco geológico |
| `mod_inspecao_industrial` | `db_mod_inspecao_industrial.db` | estruturas, torres, linhas e equipamentos |
| `mod_eventos` | `db_mod_eventos.db` | público, fluxo, ocupação e multidão |

## O que ainda não existe

A inferência por IA/visão computacional, o geoprocessamento (ortomosaico,
índices, GSD), o PDF de laudo e os módulos ambiental, obras, mapeamento,
defesa civil, inspeção industrial e eventos. A visão de produto e o roadmap
estão em [Visão de produto](../10_projeto/01_visao_produto/index.md) e
[Roadmap](../10_projeto/03_roadmap/index.md).

Novos módulos devem ser criados como `src/mod_<nome>/` com `__init__.py`,
`bd_manipulador.py`, `telas.py` e `telas_administracao.py`, e registrados em
`MODULOS_BD`, `MODULOS_SISTEMA` e `bd_criador.py`.
