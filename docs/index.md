# Skyrover

Plataforma de **laudos de voo do drone Skyrover X1**. O cliente entra com
usuário e senha, envia fotos e vídeos do voo e gera laudos nos módulos
contratados — agropecuário, vistoria predial, segurança pública e os demais
módulos da visão de produto.

Projeto Python modularizado com **Poetry**, **Python 3.13**, **NiceGUI** e um
banco de dados independente por módulo. Módulos atuais:

| Módulo | Papel | Rota |
|---|---|---|
| `mod_skyrover` | Núcleo: banco central, autenticação, tema, layout, configurações, documentação, voos/mídia/laudo | `/`, `/voos`, `/configuracoes` |
| `mod_gest_cad_usuario` | Usuários, perfis, papéis por módulo e sessões | `/users` |
| `mod_agro` | Agropecuário | `/agro` |
| `mod_vistoria_predial` | Vistoria Predial | `/vistoria-predial` |
| `mod_seguranca` | Segurança Pública | `/seguranca` |
| `mod_ambiental` | Ambiental | `/ambiental` |
| `mod_obras` | Obras | `/obras` |
| `mod_mapeamento` | Mapeamento | `/mapeamento` |
| `mod_defesa_civil` | Defesa Civil | `/defesa-civil` |
| `mod_inspecao_industrial` | Inspeção Industrial | `/inspecao-industrial` |
| `mod_eventos` | Eventos | `/eventos` |

## Por onde começar

- [Visão de produto — Skyrover X1](1_sistema/10_projeto/01_visao_produto/index.md)
- [Arquitetura futura — voos, mídia e laudos](1_sistema/10_projeto/02_arquitetura_futura/index.md)
- [Roadmap de módulos](1_sistema/10_projeto/03_roadmap/index.md)
- [Início rápido](1_sistema/02_fundamentos/02_inicio_rapido.md)
- [Arquitetura modular](1_sistema/03_arquitetura/01_arquitetura.md)
- [Contas de fábrica](1_sistema/11_seguranca/01_contas_de_fabrica.md)
- [Suíte de testes](3_testes/06_suite.md)

## Regra de ouro

Todo artefato de um módulo vive dentro de `src/mod_<nome>/`. O código que o
Python importa está em `src/`; bancos, logs, `site/` e `graphify-out/` ficam na
raiz e nunca são versionados.
