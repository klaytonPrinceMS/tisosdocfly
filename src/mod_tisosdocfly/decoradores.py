"""Central decorators for cross-cutting concerns (permission, audit, fail-soft).

Decoradores centrais para concerns transversais (permissão, auditoria,
falha suave, conexão, validação, cache).

Padrão PT-BR (DDD) com aliases EN: requer_permissao/require_permission,
auditado/audited, falha_suave/fail_soft, com_conexao/with_connection,
valida_regex/validate_regex, invalida_cache/invalidate_cache, ttl_cache.
"""
import sys
import os
import re
import time
import functools
import inspect

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from mod_tisosdocfly import observabilidade


def _log():
    return observabilidade.get_logger("tisosdocfly")


def requer_pode_publicar(arg_usuario="autor", log_msg="sem permissão de publicação bloqueado"):
    """Ensure publish permission before executing (blog).

    Garante permissão de publicação antes de executar; sem permissão
    retorna None (ou (0,0) para lote) e loga warning.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            sig = inspect.signature(func)
            try:
                bound = sig.bind_partial(*args, **kwargs)
                usuario = bound.arguments.get(arg_usuario)
                if usuario is None and args:
                    # fallback: tenta posição 2 (autor é 3º arg em criar_postagem)
                    for a in args:
                        if isinstance(a, str) and a:
                            usuario = a
                            break
                # usa helper do módulo blog sem import circular no topo
                from mod_blog.bd_manipulador import _pode_publicar
                if not _pode_publicar(usuario):
                    _log().warning(f"'{usuario}' {log_msg}")
                    # lote retorna tupla
                    if func.__name__ == "excluir_postagens_em_lote":
                        return 0, 0
                    if func.__name__ == "criar_postagem":
                        return None
                    return False
            except Exception:
                _log().exception(f"requer_pode_publicar: falha ao validar {func.__name__}")
                return None if "criar" in func.__name__ else False
            return func(*args, **kwargs)
        return wrapper
    return decorator


# Alias EN
require_permission = requer_pode_publicar


def requer_permissao(modulo, arg_usuario="usuario_logado", arg_perfil="perfil"):
    """Require admin permission for a module (generic).

    Exige admin geral ou admin do módulo; sem permissão notifica e retorna False.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            sig = inspect.signature(func)
            try:
                bound = sig.bind_partial(*args, **kwargs)
                usuario = bound.arguments.get(arg_usuario) or bound.arguments.get("autor") or bound.arguments.get("ator")
                perfil = bound.arguments.get(arg_perfil)
                from mod_tisosdocfly import autenticacao
                is_admin = (perfil == "administrador_geral") or (autenticacao.eh_admin_do_modulo(usuario, modulo) if usuario else False)
                if not is_admin:
                    _log().warning(f"requer_permissao: '{usuario}' sem admin em '{modulo}' bloqueado em {func.__name__}")
                    return False
            except Exception:
                _log().exception(f"requer_permissao: falha ao validar {func.__name__}")
                return False
            return func(*args, **kwargs)
        return wrapper
    return decorator


def requer_flag(flag, arg_usuario="autor", log_msg="sem flag de permissão bloqueado"):
    """Require a fine-grained permission flag before executing.

    Exige a flag `modulo.acao` (`tem_flag`, com bypass por papel admin
    global/modular); sem a flag retorna False (fail-closed) e loga warning.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            sig = inspect.signature(func)
            try:
                bound = sig.bind_partial(*args, **kwargs)
                usuario = bound.arguments.get(arg_usuario)
                if usuario is None and args:
                    for a in args:
                        if isinstance(a, str) and a:
                            usuario = a
                            break
                modulo = (flag or "").split(".")[0]
                from mod_gest_cad_usuario.bd_manipulador import tem_flag
                if not tem_flag(usuario, modulo, flag):
                    _log().warning(f"'{usuario}' {log_msg} ({flag})")
                    return None if "criar" in func.__name__ else False
            except Exception:
                _log().exception(f"requer_flag: falha ao validar {func.__name__}")
                return None if "criar" in func.__name__ else False
            return func(*args, **kwargs)
        return wrapper
    return decorator


def auditado(modulo, acao, com_hash=False):
    """Audit after successful execution (fail-soft).

    Audita após sucesso via audit_reg/audit_log; falha de auditoria não derruba.
    Se com_hash, calcula hash_sha256 do arquivo de saída quando existir.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            # só audita sucesso
            ok = result
            if isinstance(result, tuple):
                ok = result[0] if result else False
                if isinstance(ok, int):
                    ok = ok > 0
            elif result is None:
                # criar_postagem retorna id ou None
                ok = result is not None
            if not ok:
                return result
            try:
                from mod_tisosdocfly.crud_base import audit_reg
                sig = inspect.signature(func)
                bound = sig.bind_partial(*args, **kwargs)
                autor = bound.arguments.get("autor") or bound.arguments.get("usuario_logado") or bound.arguments.get("ator") or "sistema"
                # descrição com id quando disponível
                desc = f"{acao} por {autor}"
                if isinstance(result, int):
                    desc = f"{acao} #{result} por {autor}"
                elif isinstance(result, tuple) and len(result) >= 2:
                    desc = f"{acao} {result[0]} ok/{result[1]} falha por {autor}"
                audit_reg(autor, modulo, acao, desc)
            except Exception:
                _log().exception(f"auditado: falha ao auditar {modulo}/{acao}")
            return result
        return wrapper
    return decorator


# Alias EN
audited = auditado


def falha_suave(default=None, nivel="warning", msg=None):
    """Fail-soft: try/except + log + return default.

    Falha suave: executa e em exceção loga e retorna default.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as ex:
                m = msg or f"falha_suave: {func.__name__}: {ex}"
                try:
                    if nivel == "exception":
                        _log().exception(m)
                    else:
                        _log().warning(m)
                except Exception:
                    pass
                return default
        return wrapper
    return decorator


# Alias EN
fail_soft = falha_suave


def com_conexao(commit=True):
    """Injects a DB cursor from the module's _conn() (with commit/close).

    Injeta cursor do banco do módulo; commit/rollback/close automáticos.
    A função decorada recebe `cur` como primeiro arg após self se for método,
    ou como kwarg `cur` se não houver.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # resolve _conn do módulo chamador
            mod = inspect.getmodule(func)
            _conn = getattr(mod, "_conn", None)
            if _conn is None:
                # fallback: tenta CrudBase do blog
                return func(*args, **kwargs)
            conn = _conn()
            try:
                cur = conn.cursor()
                # injeta cur
                if "cur" not in kwargs:
                    # tenta como primeiro arg após self
                    result = func(cur, *args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                if commit:
                    conn.commit()
                return result
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        return wrapper
    return decorator


with_connection = com_conexao


def valida_regex(arg="padrao", max_len=200):
    """Validate regex before execution (ReDoS guard).

    Valida regex do arg antes de executar; inválida ou longa retorna (False, msg).
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            sig = inspect.signature(func)
            try:
                bound = sig.bind_partial(*args, **kwargs)
                padrao = bound.arguments.get(arg)
                if padrao is None and args:
                    # tenta segundo arg
                    padrao = args[1] if len(args) > 1 else None
                if padrao is not None:
                    s = str(padrao)
                    if len(s) > max_len:
                        return False, f"Regex deve ter 1-{max_len} caracteres"
                    re.compile(s)
            except re.error as e:
                return False, f"Regex inválida: {e}"
            except Exception:
                pass
            return func(*args, **kwargs)
        return wrapper
    return decorator


validate_regex = valida_regex


def invalida_cache(*funcs):
    """Invalidate lru_cache of given funcs after successful execution."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            for f in funcs:
                try:
                    f.cache_clear()
                except Exception:
                    pass
            return result
        return wrapper
    return decorator


invalidate_cache = invalida_cache


def ttl_cache(ttl=60, maxsize=32):
    """TTL cache (simple, per-process, thread-unsafe, for offset_ntp etc)."""
    def decorator(func):
        cache = {}
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            if key in cache:
                val, exp = cache[key]
                if now < exp:
                    return val
            val = func(*args, **kwargs)
            # evict if over maxsize (FIFO)
            if len(cache) >= maxsize:
                try:
                    cache.pop(next(iter(cache)))
                except Exception:
                    pass
            cache[key] = (val, now + ttl)
            return val
        def cache_clear():
            cache.clear()
        wrapper.cache_clear = cache_clear
        wrapper.cache_info = lambda: f"ttl_cache ttl={ttl} size={len(cache)}/{maxsize}"
        return wrapper
    return decorator


def tela_modulo(chave, titulo="", subtitulo="", icone=None):
    """Decorator for NiceGUI module screens (mostrar_tela).

    Aplica tema (ler_tema + ui.colors) e cabeçalho padrão antes de
    `mostrar_tela(usuario_logado, perfil)`. Mantém contrato AGENTS.md:142.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(usuario_logado: str, perfil: str, *args, **kwargs):
            try:
                from mod_tisosdocfly.tema_modulo import ler_tema
                from nicegui import ui
                tema = ler_tema(chave, cor_botao="#000000", cor_texto_botao="#FFFFFF",
                                cor_titulo="#212121")
                ui.colors(primary=tema["cor_botao"], accent=tema["cor_botao"])
            except Exception:
                _log().exception(f"tela_modulo: falha ao aplicar tema {chave}")
            # cabecalho é responsabilidade da tela (evita duplicar); decorador só garante tema
            return func(usuario_logado, perfil, *args, **kwargs)
        return wrapper
    return decorator


def admin_tela(chave):
    """Decorator for admin panels (mostrar_administracao) — verifica admin."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(usuario_logado: str, *args, **kwargs):
            try:
                from mod_tisosdocfly import autenticacao
                # perfil pode estar em kwargs ou precisa buscar
                perfil = kwargs.get("perfil") or kwargs.get("eh_admin")
                if perfil is None:
                    # tenta obter via autenticacao
                    perfil = autenticacao.perfil_global_de(usuario_logado) if hasattr(autenticacao, "perfil_global_de") else None
                is_admin = (perfil == "administrador_geral") or autenticacao.eh_admin_do_modulo(usuario_logado, chave)
                if not is_admin and perfil is not True:
                    _log().warning(f"admin_tela: '{usuario_logado}' sem admin em '{chave}' bloqueado em {func.__name__}")
                    return None
            except Exception:
                _log().exception(f"admin_tela: falha ao validar {func.__name__}")
                return None
            return func(usuario_logado, *args, **kwargs)
        return wrapper
    return decorator
