# Início rápido

## 1. Instalar

```bash
poetry env use 3.13
poetry install
```

## 2. Subir

```bash
poetry run task start
```

Acesse <http://127.0.0.1:8080/login>.

## 3. Entrar

| Usuário | Senha | Perfil | Primeiro acesso |
|---|---|---|---|
| `master` | `master` | `administrador_geral` | **Força** troca de senha e de credenciais |
| `qacomum` | `123456` | `comum` | Sem troca forçada |
| `qamaster` | `123456` | `administrador_geral` | Sem troca forçada |

As contas de teste existem de propósito para QA e não são removidas
automaticamente.

## 4. Liberar o módulo de usuários

Na entrega, só o módulo `usuarios` é indispensável e nasce ligado. O `master`
administra os demais pela tela de Configurações.

## 5. Rodar a suíte

```bash
poetry run task teste
poetry run task lint
```
