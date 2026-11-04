# Entrega inicial — commit e push

Registro da primeira publicação do repositório Skyrover.

## Identificação

| Campo | Valor |
|---|---|
| Data do commit | 02/11/2026 16:33 |
| Documentado em | 04/11/2026 |
| Commit | `d4c84f940d7b1e506a1fb9a85b1bde27d714bd4e` |
| Hash curto | `d4c84f9` |
| Mensagem | `261102 1633 Implementa plataforma Skyrover X1 com modulos, IA e laudos` |
| Branch | `main` |
| Remoto | `origin` — https://github.com/klaytonPrinceMS/skyrover.git |
| Push | `main -> origin/main` (novo branch, tracking configurado) |
| Arquivos | 261 |
| Linhas adicionadas | 83.133 |

## O que entrou

- Núcleo modular `mod_skyrover` (config, autenticação, tema, layout,
  documentação, auditoria, voos, mídia e laudo PDF).
- `mod_gest_cad_usuario` com seed `master`, `qacomum` e `qamaster`.
- Nove módulos de negócio: agro, vistoria predial, segurança, ambiental,
  obras, mapeamento, defesa civil, inspeção industrial, eventos.
- `mod_perimetro` com auditoria física, achados e varredura Wi-Fi/RF
  (BSSID em SHA-256).
- Pipeline de imagem em Python puro (`avaliacao_imagens.py`,
  `linhas_plantio.py`, `multiespectral.py`, `ia.py`,
  `geoprocessamento.py`, `relatorio.py`).
- Painel de riscos `/riscos`.
- Documentação MkDocs (tema readthedocs) com visão de produto, roadmap,
  manuais, referências Embrapa/GeoIA/RWTV e conformidade regulatória.
- Subagentes `kbp-*`, skill e plugin graphify.
- Suíte standalone + testes de integração e E2E Playwright.

## Validação no momento da entrega

| Gate | Resultado |
|---|---|
| `poetry run task lint` | 0 `undefined name` |
| `tests/test_suite.py` | 17/17 scripts OK |
| `tests/check_integridade.py` | 81/81 checagens |
| `poetry run task docs` | `mkdocs build --strict` OK |
| UI | login, home, módulos, `/riscos`, `/perimetro`, `/admin/perimetro` validados |
| Console do navegador | sem erros |

## O que ficou fora do git

Por regra do projeto, o commit não inclui:

- `db_mod_*.db`, `*.db-wal`, `*.db-shm`;
- `logs/`, `backup/`, `site/`, `graphify-out/`;
- `.venv/`, `.nicegui/`, `node_modules/`, `poetry.toml`;
- mídia de voo (`src/mod_skyrover/midia/`) e laudos gerados
  (`src/mod_skyrover/laudos/`);
- `tests/_bd_teste/` e massa de teste.

## Como conferir

```bash
git show --stat --oneline d4c84f9
git log --oneline -1
git rev-parse HEAD origin/main
git status --short
```

## Como reproduzir o ambiente

```bash
poetry env use 3.13
poetry install
poetry run task start
```

Credenciais de demonstração: `qamaster` / `123456`. O `master` nativo força
troca de senha e credenciais no primeiro acesso.

## Observação

O commit inicial é a linha de base. Alterações posteriores devem ser
commitadas separadamente, com a mensagem no formato `AAMMDD HHMM` e o mesmo
cuidado de stage descrito no `AGENTS.md` §5.
