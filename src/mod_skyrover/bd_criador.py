"""Aggregated database bootstrap.

Bootstrap agregado dos bancos do Skyrover.

Idempotente: cria tabelas e os usuários de fábrica apenas quando não existem.
NUNCA apaga dados. Reutilizável no boot (`main.py`) e por CLI.

ORDEM OBRIGATÓRIA: o banco CENTRAL (`db_mod_skyrover.db`) precisa existir
antes de importar `mod_gest_cad_usuario.bd_manipulador`, porque aquele módulo
executa `init_db()` no nível do módulo e grava em `tb_config` central.
"""
from mod_skyrover.repositorio import garantir_bancos


def inicializar_bancos():
    """Cria os bancos e os schemas dos dois módulos iniciais, na ordem certa."""
    # 0) Garante os arquivos/databases dos módulos (SQLite ou PostgreSQL).
    garantir_bancos()

    from mod_skyrover import observabilidade as _obs_boot
    _log_boot = _obs_boot.get_logger("skyrover")

    # 1) Banco central primeiro: tb_config, tb_sessoes, tb_modulos, tb_auditoria.
    from mod_skyrover.bd_conexao import init_db as init_central
    from mod_skyrover.bd_manipulador import garantir_rastreabilidade

    init_central()
    garantir_rastreabilidade()

    # 1.1) Onda 1 do produto: clientes, propriedades, voos, capturas,
    #      arquivos de mídia e laudos no MESMO banco central. DDL idempotente
    #      (CREATE TABLE/INDEX IF NOT EXISTS), portável para PostgreSQL.
    try:
        from mod_skyrover.voos import garantir_schema_voos
        garantir_schema_voos()
    except Exception as _e_voos:
        try:
            _log_boot.exception(
                f"schema de voos falhou (fail-soft): {_e_voos}")
        except Exception:
            pass

    # 2) Cadastro de usuários: db_mod_gest_cad_usuario.db + seed
    #    master/master, qacomum/123456 e qamaster/123456.
    try:
        from mod_gest_cad_usuario.bd_manipulador import init_db as init_users
        init_users()
    except Exception as _e_users:
        try:
            _log_boot.exception(
                f"init_db de gestão de usuários falhou: {_e_users}")
        except Exception:
            pass
        raise

    # 3) Módulos de negócio iniciais. Cada um tem banco e schema próprios;
    #    falha em um módulo não derruba o boot dos demais (fail-soft com log).
    from importlib import import_module
    for _pacote in (
            "mod_agro", "mod_vistoria_predial", "mod_seguranca",
            "mod_ambiental", "mod_obras", "mod_mapeamento",
            "mod_defesa_civil", "mod_inspecao_industrial", "mod_eventos",
            "mod_perimetro"):
        try:
            _mod = import_module(f"{_pacote}.bd_manipulador")
            if not _mod.init_db():
                _log_boot.warning(
                    f"init_db de {_pacote} devolveu False (schema não criado)")
        except Exception as _e_mod:
            try:
                _log_boot.exception(
                    f"init_db de {_pacote} falhou: {_e_mod}")
            except Exception:
                pass


if __name__ == "__main__":
    inicializar_bancos()
