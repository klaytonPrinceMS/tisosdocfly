# Skyrover (núcleo)

Pacote: `src/mod_skyrover/` — chave de banco `skyrover`.

## Responsabilidade

Fornecer tudo o que um módulo precisa para existir sem duplicar infraestrutura:

| Arquivo | Papel |
|---|---|
| `bd_conexao.py` | `get_config`/`set_config`, schema central, migrações idempotentes |
| `banco_conexao.py` | Backend duplo SQLite/PostgreSQL e tradução de SQL |
| `repositorio.py` | `MODULOS_BD`, engines SQLAlchemy e repositório |
| `crud_base.py` | CRUD transacional por banco |
| `autenticacao.py` | Login, sessões, papéis, tema escuro, TOTP |
| `voos.py` | Onda 1: clientes, propriedades, voos, capturas, mídias e laudos |
| `telas_voos.py` | Telas `/voos`: cadastros, upload de fotos/vídeos e laudo base |
| `tema_modulo.py` | Cores e componentes por módulo |
| `telas.py` | `pagina_restrita`, layout de 4 partes, troca obrigatória |
| `tela_configuracoes.py` | Painel de configurações do sistema |
| `documentacao.py` | Build e montagem do MkDocs em `/documentacao` |
| `observabilidade.py` | Loguru, rotação, exceções |
| `bd_criador.py` | Bootstrap agregado dos bancos |

## Banco central

`db_mod_skyrover.db`:

- `tb_config` — configuração chave/valor;
- `tb_sessoes` — sessões revogáveis com IP/UA;
- `tb_modulos` — cadastro dos módulos e rotas;
- `tb_auditoria` — trilha LGPD escrita por `audit_log`;
- `tb_clientes` — clientes dos laudos (Onda 1);
- `tb_propriedades` — propriedades/áreas vinculadas ao cliente;
- `tb_voos` — voos com data, piloto, drone, GSD e status;
- `tb_capturas` — capturas de cada voo (foto/vídeo);
- `tb_arquivos_midia` — metadados do upload, com SHA-256 e caminho;
- `tb_laudos` — laudo base e caminho do PDF;
- `tb_analises_ia` — resultado do pipeline por imagem/módulo.

As tabelas nascem de forma idempotente em
`voos.garantir_schema_voos()`, chamado por `bd_criador.inicializar_bancos()`.
A mídia fica fora do banco, em `src/mod_skyrover/midia/<voo_id>/` (ignorada
pelo Git e pelo graphify), e o banco guarda apenas os metadados. Os laudos PDF
ficam em `src/mod_skyrover/laudos/<chave>/`.

## Pipeline de imagem e laudo

- `avaliacao_imagens.py` — avaliação padrão em Python puro (PNG/BMP/PPM com
  stdlib; JPEG só decodifica pelo Pillow).
- `ia.py` — usa a avaliação pura ou modelo registrado/ONNX; segurança não
  inventa detecção sem detector homologado.
- `geoprocessamento.py` — índices ExG/VARI/GLI/TGI, métricas, GSD, thumbnail.
- `relatorio.py` — PDF com metadados, ocorrências, métricas e imagens.
- A tela `/voos` executa **Analisar mídias (IA)** e **Gerar laudo PDF**.
- `tb_analises_ia` é lida pelos módulos via `voos.listar_analises_ia`; o bloco
  reutilizável `ui_analise.bloco_analise` aparece em cada módulo.

## Rotas do núcleo

- `/` — dashboard com os módulos liberados e o card fixo "Voos e laudos";
- `/voos` — cliente → propriedade → voo → upload → laudo base;
- `/configuracoes`, `/admin/{chave}` — administração do sistema.

`voos` é funcionalidade do núcleo, não módulo de negócio: **não** entra em
`MODULOS_SISTEMA`, `MODULOS_BD` nem em `tb_modulos`.

## Regras

- Nada de import de módulo de negócio no topo (ciclo). Use hooks ou import lazy.
- Toda migração é idempotente e funciona em SQLite **e** PostgreSQL.
- O núcleo não decide regra de negócio de módulo.
- Escrita em `/voos` exige `administrador_geral` ou papel de administrador no
  módulo `skyrover`; perfil comum é somente leitura.
