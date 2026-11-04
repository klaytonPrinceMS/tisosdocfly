# Entrega inicial — commit e push

Registro da publicação inicial e da reorganização do repositório.

## 1. Publicação inicial — Skyrover X1

| Campo | Valor |
|---|---|
| Data | 02/11/2026 16:33 |
| Commit | `d4c84f940d7b1e506a1fb9a85b1bde27d714bd4e` |
| Hash curto | `d4c84f9` |
| Mensagem | `261102 1633 Implementa plataforma Skyrover X1 com modulos, IA e laudos` |
| Branch | `main` |
| Arquivos | 261 |
| Linhas adicionadas | 83.133 |
| Push | `main -> origin/main` (primeiro push, tracking configurado) |

Essa publicação continha o núcleo `mod_skyrover`, o cadastro de usuários, os
nove módulos de negócio, o pipeline de imagem/PDF e a documentação MkDocs.
O histórico completo foi preservado na branch local/remota
`skyrover-x1-historico`.

## 2. Reorganização — T! SOS DocFly (multidrone)

Em 03/11/2026 o remoto passou a ter uma história própria, sem ancestral
comum com `d4c84f9`:

| Commit | Data | Conteúdo |
|---|---|---|
| `c7d52df` | 03/11/2026 11:53 | T! SOS DocFly multidrone: commit inicial |
| `d1443a5` | 03/11/2026 14:01 | Adiciona módulo de vídeos com download do YouTube |
| `424ba38` | 03/11/2026 14:09 | Trava `yt-dlp` e `edge-tts` do módulo de vídeos |

A árvore atual é a mesma base modular, agora com:

- `mod_tisosdocfly` como núcleo renomeado;
- `mod_video` para download/biblioteca de vídeos;
- os demais módulos (agro, vistoria, segurança, ambiental, obras,
  mapeamento, defesa civil, inspeção industrial, eventos e perímetro).

O `origin/main` foi atualizado por **force-update** nesse processo. Por isso o
commit `d4c84f9` não é ancestral do `main` atual e um merge direto não é
possível.

## 3. O que este documento registra

- A publicação inicial foi feita e está preservada em
  `skyrover-x1-historico`.
- O `main` atual é a linha autoritativa do **T! SOS DocFly**.
- A documentação desta entrega foi adicionada ao `main` atual por um commit
  normal (fast-forward), **sem force-push**.
- Nenhum banco, log, mídia, laudo, `.venv` ou `poetry.toml` entrou no git.

## 4. Validação na publicação inicial

| Gate | Resultado |
|---|---|
| `poetry run task lint` | 0 `undefined name` |
| `tests/test_suite.py` | 17/17 scripts OK |
| `tests/check_integridade.py` | 81/81 checagens |
| `poetry run task docs` | `mkdocs build --strict` OK |
| UI | login, home, módulos, `/riscos`, `/perimetro`, `/admin/perimetro` |
| Console do navegador | sem erros |

## 5. Como conferir

```bash
# história atual do projeto
git log --oneline --decorate -6

# história original preservada
git log --oneline skyrover-x1-historico -3

# estado do remoto
git rev-parse HEAD origin/main
```

## 6. Como reproduzir o ambiente

```bash
poetry env use 3.13
poetry install
poetry run task start
```

Credenciais de demonstração: `qamaster` / `123456`. O `master` nativo força
troca de senha e credenciais no primeiro acesso.
