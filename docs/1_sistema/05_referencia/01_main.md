# main.py

O `main.py` é o único ponto de entrada. Ele:

1. Insere `src/` no `sys.path`.
2. Aplica o patch do NiceGUI e configura a observabilidade.
3. Chama `mod_skyrover.bd_criador.inicializar_bancos()`.
4. Registra as rotas centrais:
   - `/login` — autenticação, captcha e TOTP;
   - `/` — dashboard com os módulos liberados;
   - `/users` — `mod_gest_cad_usuario.telas.mostrar_tela`;
   - `/configuracoes` — `mod_skyrover.tela_configuracoes.mostrar_tela`;
   - `/admin/{chave_modulo}` — painel administrativo do módulo;
   - `/troca-obrigatoria` — troca de senha/credenciais no primeiro acesso.
5. Monta a documentação em `/documentacao` (fail-soft).
6. Sobe o `ui.run` com `storage_secret`, idioma `pt-BR` e encerramento gracioso.

## Regra

Toda rota protegida passa por `mod_skyrover.telas.pagina_restrita`, que:

- valida a sessão no banco (revogação e bloqueio);
- aplica timeout de inatividade;
- impede navegação enquanto houver troca obrigatória pendente;
- valida permissão **e** se o módulo está ligado antes de montar a tela.

Nunca renderize uma tela de módulo sem passar por esse guard.
