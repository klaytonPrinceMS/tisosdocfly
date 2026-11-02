# CSS frameworks embarcados

> Local CSS frameworks served under `/css/frameworks/*` (no CDN). Standard visual is **PIC (Quasar nativo suave)** — no external framework.
>
> Frameworks CSS servidos localmente em `/css/frameworks/*` (sem CDN). Padrão visual **PIC (Quasar nativo suave)** — sem framework externo.

**Padrão PIC definido:** `tb_config empenhos_modelo_visual=pic` (`mod_renomear_empenho/visual.py:MODELO_PADRAO`). O drawer `mod_intranet/telas.py` exibe apenas **Empenhos padrão** — comentário `Padrão PIC definido — exemplos de CSS removidos do menu` (`telas.py:289`). Os 17 CSS permanecem em disco para comparação direta via URL (rota responde `200`), sem poluir o menu.

| Framework | Arquivo | Versão | Origem | Licença | Rota dedicada (200) | No menu? |
|---|---|---|---|---|---|---|
| **PIC (padrão)** | — | — | Quasar nativo suave (sem arquivo) | — | `/renomear-empenho` e `/renomear-empenho-pic` | **Sim — Empenhos padrão** |
| Bootstrap | `bootstrap@5.3.8.min.css` | 5.3.8 | https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css | MIT | `/renomear-empenho-bootstrap` | Não — removido do drawer, mantido em disco |
| Bulma | `bulma@1.0.2.min.css` | 1.0.2 | https://cdn.jsdelivr.net/npm/bulma@1.0.2/css/bulma.min.css | MIT | — | Não |
| DaisyUI | `daisyui@5.6.8.min.css` | 5.6.8 | https://cdnjs.cloudflare.com/ajax/libs/daisyui/5.6.8/daisyui.css | MIT | — | Não |
| DaisyUI themes | `daisyui@5.6.8.themes.min.css` | 5.6.8 | https://cdnjs.cloudflare.com/ajax/libs/daisyui/5.6.8/themes.min.css | MIT | — | — (auxiliar) |
| Pico CSS | `pico@2.min.css` | 2.x | https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css | MIT | — | Não |
| Picnic CSS | `picnic@7.1.0.min.css` | 7.1.0 | https://cdn.jsdelivr.net/npm/picnic@7.1.0/picnic.min.css | MIT | — | Não |
| Spectre | `spectre@0.5.9.min.css` | 0.5.9 | https://cdn.jsdelivr.net/npm/spectre.css@0.5.9/dist/spectre.min.css | MIT | `/renomear-empenho-spectre` | Não — rota direta |
| Chota | `chota@0.8.0.min.css` | 0.8.0 | https://cdn.jsdelivr.net/npm/chota@0.8.0/dist/chota.min.css | MIT | `/renomear-empenho-chota` | Não — rota direta |
| Milligram | `milligram@1.4.1.min.css` | 1.4.1 | https://cdn.jsdelivr.net/npm/milligram@1.4.1/dist/milligram.min.css | MIT | `/renomear-empenho-milligram` | Não — rota direta |
| Skeleton | `skeleton@2.0.4.min.css` | 2.0.4 | https://cdn.jsdelivr.net/npm/skeleton-css@2.0.4/css/skeleton.css | MIT | `/renomear-empenho-skeleton` | Não — rota direta |
| Water.css | `water@2.1.1.min.css` | 2.1.1 | https://cdn.jsdelivr.net/npm/water.css@2.1.1/out/water.min.css | MIT | `/renomear-empenho-water` | Não — rota direta |
| MVP.css | `mvp@1.14.min.css` | 1.14 | https://unpkg.com/mvp.css@1.14/mvp.css | MIT | `/renomear-empenho-mvp` | Não — rota direta |
| Tachyons | `tachyons@4.12.0.min.css` | 4.12.0 | https://cdn.jsdelivr.net/npm/tachyons@4.12.0/css/tachyons.min.css | MIT | `/renomear-empenho-tachyons` | Não — rota direta |
| UIkit | `uikit@3.21.5.min.css` | 3.21.5 | https://cdn.jsdelivr.net/npm/uikit@3.21.5/dist/css/uikit.min.css | MIT | `/renomear-empenho-uikit` | Não — rota direta |
| Foundation | `foundation@6.8.1.min.css` | 6.8.1 | https://cdn.jsdelivr.net/npm/foundation-sites@6.8.1/dist/css/foundation.min.css | MIT | `/renomear-empenho-foundation` | Não — rota direta |
| Semantic UI | `semantic@2.5.0.min.css` | 2.5.0 | https://cdn.jsdelivr.net/npm/semantic-ui@2.5.0/dist/semantic.min.css | MIT | `/renomear-empenho-semantic` | Não — rota direta |
| Materialize | `materialize@1.0.0.min.css` | 1.0.0 | https://cdn.jsdelivr.net/npm/materialize-css@1.0.0/dist/css/materialize.min.css | MIT | `/renomear-empenho-materialize` | Não — rota direta |
| Primer | `primer@21.0.9.min.css` | 21.0.0 | https://unpkg.com/@primer/css@21.0.9/dist/primer.css | MIT | `/renomear-empenho-primer` | Não — rota direta |

Total em disco: **17 frameworks** (17 arquivos principais + `daisyui themes` auxiliar = 18 arquivos em `assets/css/frameworks/`). `main.py:572-637` registra as rotas `/renomear-empenho-{nome}` via `_page_empenho_forcado(modelo)` + `visual.FORCAR_MODELO` — todas respondem `200` quando autenticado, para comparação lado a lado sem alterar o padrão.

## Como usar

Todo framework é servido localmente pelo módulo `mod_intranet/tema_css.py` (`FRAMEWORKS_CSS`, `montar_rotas_static`, `injetar_framework`). A injeção é **por página** (evita conflito de resets com o Quasar/Tailwind do NiceGUI). O padrão **PIC** não injeta framework — é o visual suave nativo:

```python
from mod_intranet import tema_css
from mod_renomear_empenho import visual

# Padrão PIC (sem CSS externo)
visual.injetar_pic_suave()
# Ou um framework específico (tela dedicada, fora do menu)
tema_css.injetar_framework("spectre")  # adiciona <link> ao <head> da página atual
# Para comparar, use a rota dedicada com FORCAR_MODELO
# /renomear-empenho-spectre -> visual.FORCAR_MODELO="spectre"
```

Lista de frameworks: `tema_css.FRAMEWORKS_CSS` (nome → descrição + aviso). No módulo Renomear Empenhos o modelo padrão é `visual.MODELO_PADRAO="pic"` e `visual.VALIDOS=("pic",)+FRAMEWORKS` (12 novos); `tb_config empenhos_modelo_visual` permanece `pic`. As telas dedicadas usam `visual.FORCAR_MODELO` + `tema_css.injetar_framework()` por página (sem CDN, sem reset global fora do escopo).

## Drawer — padrão PIC

`mod_intranet/telas.py:_montar_layout` monta o drawer lateral (`ui.left_drawer`). Após a lista de módulos do usuário, havia o bloco `Empenhos — PIC + por CSS` com 12+ itens. Agora:

```python
# Padrão PIC definido — exemplos de CSS removidos do menu (mantidos em disco/docs para comparação direta via URL se necessário).
```

O menu exibe apenas **Empenhos padrão** (`/renomear-empenho`, chave `empenhos`). As rotas dedicadas `/renomear-empenho-{spectre,chota,milligram,skeleton,water,mvp,tachyons,uikit,foundation,semantic,materialize,primer}` continuam registradas em `main.py` e servem para comparação direta via URL (sem poluir o drawer).

## Avaliação de compatibilidade

- **Bootstrap**: grid `.row`/`.col-*` + `.btn`, `.card`, `.badge`, `.table`. Reset global pesado — por página.
- **Bulma**: flexbox `.button`, `.columns`; pode colidir com Quasar — mantido em disco, fora do menu atual.
- **DaisyUI**: `.btn/.card/.badge` sobre Tailwind v4 (NiceGUI usa v3 parcial) — mantido em disco.
- **Pico**: reset sem classes (estiliza tags) — mantido em disco.
- **Picnic**: leve, manutenção reduzida — mantido em disco.
- **Spectre/Chota/Milligram/Skeleton**: leves (≈9–46KB), grid simples — baixo conflito, bons para comparar com PIC.
- **Water.css/MVP.css**: classless (estilizam `body/h1/button` direto) — impacto global mesmo leve.
- **Tachyons**: utilitários atômicos — muitas classes, baixo conflito.
- **UIkit/Foundation/Semantic/Materialize/Primer**: mais pesados (134–843KB), resets moderados a pesados — por página dedicada.

**Padrão mantido:** `PIC` suave (sem framework) é o padrão em `tb_config empenhos_modelo_visual=pic`; os demais ficam em rotas dedicadas para avaliação sem alterar o padrão.

## Atualização

Baixar nova versão com `curl` e ajustar o nome do arquivo em `FRAMEWORKS_CSS` (`mod_intranet/tema_css.py`).
