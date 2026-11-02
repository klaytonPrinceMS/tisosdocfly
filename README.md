# Skyrover

Plataforma de **laudos de voo do drone Skyrover X1**. O cliente autentica,
envia fotos e vídeos do voo e gera laudos nos módulos de análise —
agropecuário, vistoria predial, segurança pública e os demais previstos no
roadmap.

Projeto Python modular com **Poetry**, **Python 3.13**, **NiceGUI** e um banco
independente por módulo. Começa com dois módulos implementados:

- **`mod_skyrover`** — núcleo: banco central, autenticação, tema, layout,
  configurações, documentação, auditoria e voos/mídia/laudo base.
- **`mod_gest_cad_usuario`** — cadastro de usuários, perfis, papéis por módulo
  e sessões revogáveis.
- **`mod_agro`** — análise agropecuária, ocorrências e laudo textual.
- **`mod_vistoria_predial`** — vistoria, patologias e laudo textual.
- **`mod_seguranca`** — triagem de segurança com revisão humana obrigatória.
- **`mod_ambiental`** — desmatamento, APP, queimada e recuperação.
- **`mod_obras`** — avanço físico, ocorrências e medição.
- **`mod_mapeamento`** — ortomosaico, topografia e produtos geoespaciais.
- **`mod_defesa_civil`** — dano pós-desastre e risco geológico.
- **`mod_inspecao_industrial`** — estruturas, torres, linhas e equipamentos.
- **`mod_eventos`** — público, fluxo, ocupação e multidão.
- **`mod_perimetro`** — perímetro físico, pontos cegos, iluminação e
  vazamento de Wi-Fi/RF (BSSID em hash).

O núcleo já traz o pipeline transversal: **avaliação de imagem em Python
puro** (decode PNG/BMP/PPM com stdlib, índices de vegetação, bordas, entropia,
blobs e proporções), interface para modelo ONNX, GSD, thumbnails e geração de
laudo PDF. A tela `/voos` executa **Analisar mídias (IA)** e **Gerar laudo
PDF**; cada módulo tem o atalho **Analisar IA**. O processamento
multiespectral gera NDVI/SAVI/NDRE/GNDVI/NDWI, histogramas, estatísticas e
GeoTIFF a partir de bandas R/G/B/NIR/RE.

## Requisitos

- Python 3.13
- Poetry 2.x

## Instalação

```bash
poetry env use 3.13
poetry install
poetry run task start
```

Acesse <http://127.0.0.1:8080/login>.

| Conta | Senha | Perfil | Primeiro acesso |
|---|---|---|---|
| `master` | `master` | administrador_geral | força troca de senha e credenciais |
| `qacomum` | `123456` | comum | sem troca forçada |
| `qamaster` | `123456` | administrador_geral | sem troca forçada |

## Estrutura

```
main.py                      # entry point
src/mod_skyrover/            # núcleo
src/mod_gest_cad_usuario/    # gestão de usuários
src/assets/                  # CSS, favicon, imagens
tests/                       # suíte standalone + Playwright
docs/                        # MkDocs (tema readthedocs)
.opencode/                   # subagentes kbp-*, skill e plugin graphify
```

## Comandos

```bash
poetry run task --list
poetry run task teste          # suíte completa
poetry run task lint           # pyflakes (undefined name é bloqueante)
poetry run task verificar      # lint + testes
poetry run task docs           # mkdocs build --strict
poetry run task grafo:update   # atualiza o grafo
```

## Documentação

A documentação é servida em `/documentacao` no boot. Para desligar:
`SKYROVER_DOCS_ATIVO=0`.

## Subagentes e graphify

Os subagentes `kbp-commit`, `kbp-devSecOps`, `kbp-doc`, `kbp-doc_teste`,
`kbp-qa` e `kbp-web-design` estão em `.opencode/agent/`. A skill `graphify`
está em `.opencode/skills/graphify/` e o plugin em `.opencode/plugins/`.
Instale o grupo opcional com `poetry install --with graph`.

O guia completo de uso está em [AGENTS.md](AGENTS.md).
