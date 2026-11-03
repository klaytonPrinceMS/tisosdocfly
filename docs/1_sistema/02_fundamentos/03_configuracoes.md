# Configurações

As configurações do sistema vivem em `tb_config` no banco **central**
(`db_mod_tisosdocfly.db`), acessadas por `get_config`/`set_config` em
`mod_tisosdocfly/bd_conexao.py`.

## Onde fica cada coisa

| Chave | Uso |
|---|---|
| `titulo_sistema`, `icone_sistema`, `cor_principal`, `cor_fundo` | Identidade visual |
| `texto_login_titulo`, `texto_login_subtitulo`, `texto_login_hint` | Textos do login |
| `sessao_timeout_min` | Tempo de inatividade até derrubar a sessão (0 = desligado) |
| `captcha_apos_falhas` | Falhas por IP antes de exigir captcha |
| `banco_tipo`, `postgres_url` | Backend SQLite/PostgreSQL |
| `versao_modulo:<chave>` | Versão exibida no rodapé do módulo |
| `<chave>_cor_botao`, `<chave>_cor_texto_botao` | Tema do módulo |

## Tela de configurações

A rota `/configuracoes` chama `mod_tisosdocfly.tela_configuracoes.mostrar_tela`
depois do `pagina_restrita`. Apenas administradores devem alterar valores
globais; a própria tela valida o perfil.

## Regra

Nunca há duas fontes para a mesma configuração. O valor mora em `tb_config`,
é lido por `get_config` e o padrão fica em `PADRAO_CONFIG`. Um `if` com valor
fixo em outro arquivo é dívida: os dois vão divergir.
