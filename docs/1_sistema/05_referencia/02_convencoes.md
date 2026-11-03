# Convenções de código

| Elemento | Padrão | Exemplo |
|---|---|---|
| Idioma / semântica | Português BR | `calcular_total` |
| Classes | `PascalCase` | `GerenciadorUsuario` |
| Classes internas | `_PascalCase` | `_GerenciadorInterno` |
| Funções / métodos | `snake_case` | `obter_usuario_por_id()` |
| Constantes | `MAIUSCULAS_SNAKE` | `TENTATIVAS_MAXIMAS` |
| Pacote de módulo | `mod_<nome>` minúsculo | `mod_gest_cad_usuario` |
| Tabelas | `tb_<nome>` | `tb_usuario` |
| Colunas | `snake_case` | `nome_usuario` |

## Tratamento de erros

- Toda função trata exceção com `try/except Exception` (nunca `except:` cru).
- O `except` registra a causa (`logger.exception` ou `traceback`) e, quando há
  UI, notifica o usuário.
- Nunca engula um `NameError` com `except Exception: pass` novo. O gate de
  `pyflakes` existe para isso.
- Restaure botões, spinners e travas no `finally`.

## Docstrings

Padrão bilíngue: resumo em inglês no topo e explicação em Português BR abaixo.

```python
def obter_usuario(nome: str):
    """Fetch a user by login.

    Busca um usuário pelo login; devolve None quando não existe.
    """
```

## Dados reais

Nunca use nome, matrícula, CPF, e-mail ou telefone de pessoa real em exemplo,
teste ou docstring. Use `MT-1234` e nomes fictícios.
