"""Production secrets — session secret storage (file or Credential Manager).

Segredos de produção — onde mora o segredo que assina a sessão.

O `TISOSDOCFLY_STORAGE_SECRET` assina o cookie `session`: com o placeholder
(valor público, igual em toda instalação), qualquer um com acesso ao
servidor forja sessão. Em produção ele precisa ser forte e único — e
**nunca** ir para log, doc ou commit (AGENTS.md §8.2.1).

Este módulo resolve ONDE o boot lê o segredo, nesta precedência
(`obter_segredo_sessao`):

1. `TISOSDOCFLY_STORAGE_SECRET` (variável de ambiente — manda em tudo);
2. `TISOSDOCFLY_STORAGE_SECRET_FILE` (caminho de arquivo só do usuário);
3. `TISOSDOCFLY_STORAGE_SECRET_CREDMAN=1` (Gerenciador de Credenciais do
   Windows, alvo `tisosdocfly/STORAGE_SECRET` — criptografado por DPAPI);
4. placeholder (com AVISO — nunca silencioso).

Uso (CLI, sem exibir o valor em tela, log ou histórico de shell — a
leitura é por `getpass`):

    poetry run python src/mod_tisosdocfly/segredos.py guardar --arquivo
    poetry run python src/mod_tisosdocfly/segredos.py guardar --gerenciador
    poetry run python src/mod_tisosdocfly/segredos.py conferir
    poetry run python src/mod_tisosdocfly/segredos.py apagar --gerenciador

Ver `docs/1_sistema/11_seguranca/06_segredos_producao.md`.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

ALVO_CREDMAN = "tisosdocfly/STORAGE_SECRET"


def _log():
    """Logger do módulo (loguru) — cai no sink core em falha."""
    try:
        from mod_tisosdocfly import observabilidade
        return observabilidade.get_logger("tisosdocfly")
    except Exception:
        import logging as _lg
        return _lg.getLogger("segredos")


def _so_windows():
    """True no Windows (único SO com Gerenciador de Credenciais/DPAPI)."""
    try:
        import platform as _plat
        return _plat.system() == "Windows"
    except Exception:
        return os.name == "nt"


def _dir_estado():
    """Pasta privada do usuário para o arquivo de segredo."""
    try:
        if _so_windows():
            base = (os.environ.get("APPDATA") or
                    os.path.join(os.path.expanduser("~"), "AppData", "Roaming"))
        else:
            base = (os.environ.get("XDG_CONFIG_HOME") or
                    os.path.join(os.path.expanduser("~"), ".config"))
        pasta = os.path.join(base, "tisosdocfly")
        os.makedirs(pasta, exist_ok=True)
        return pasta
    except Exception:
        try:
            _log().exception("_dir_estado falhou")
        except Exception:
            pass
        return ""


def caminho_padrao_arquivo():
    """Caminho padrão do arquivo de segredo (pasta privada do usuário)."""
    try:
        pasta = _dir_estado()
        return os.path.join(pasta, ".storage_secret") if pasta else ""
    except Exception:
        return ""


def _endurecer_arquivo(caminho):
    """Restringe o arquivo ao dono (best-effort; True quando aplicou)."""
    try:
        if _so_windows():
            import shutil as _qual
            import subprocess as _proc
            if not _qual.which("icacls"):
                return False
            _r = _proc.run(["icacls", caminho, "/inheritance:r", "/grant:r",
                            f"{os.environ.get('USERNAME', '%USERNAME%')}:F"],
                           capture_output=True, text=True, timeout=30)
            return _r.returncode == 0
        os.chmod(caminho, 0o600)
        return True
    except Exception:
        try:
            _log().warning(f"não foi possível restringir {caminho} ao dono")
        except Exception:
            pass
        return False


def guardar_em_arquivo(valor, caminho=None):
    """Grava o segredo em arquivo só do dono. Devolve (True, caminho)."""
    try:
        valor = (valor or "").strip()
        if not valor:
            return False, "segredo vazio — nada gravado"
        destino = (caminho or "").strip() or caminho_padrao_arquivo()
        if not destino:
            return False, "sem caminho para o arquivo de segredo"
        pasta = os.path.dirname(destino)
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        with open(destino, "w", encoding="utf-8") as fh:
            fh.write(valor + "\n")
        _endurecer_arquivo(destino)
        return True, destino
    except Exception as e:
        try:
            _log().exception(f"guardar_em_arquivo falhou: {e}")
        except Exception:
            pass
        return False, str(e)


def ler_de_arquivo(caminho=None):
    """Lê o segredo do arquivo ("" quando ausente/ilegível)."""
    try:
        origem = (caminho or "").strip() or caminho_padrao_arquivo()
        if not origem or not os.path.isfile(origem):
            return ""
        with open(origem, encoding="utf-8") as fh:
            return (fh.read() or "").strip()
    except Exception:
        try:
            _log().warning("ler_de_arquivo: arquivo ilegível")
        except Exception:
            pass
        return ""


def _advapi32():
    """Handle do advapi32 (só Windows) ou None."""
    try:
        if not _so_windows():
            return None
        import ctypes as _ct
        return _ct.windll.advapi32
    except Exception:
        return None


def _classe_cred():
    """Estrutura CREDENTIAL da API Win32 (para CredWrite/CredRead)."""
    try:
        import ctypes as _ct
        from ctypes import wintypes as _wt

        class _Cred(_ct.Structure):
            _fields_ = [("Flags", _wt.DWORD), ("Type", _wt.DWORD),
                        ("TargetName", _wt.LPWSTR), ("Comment", _wt.LPWSTR),
                        ("LastWritten", _wt.FILETIME),
                        ("CredentialBlobSize", _wt.DWORD),
                        ("CredentialBlob", _ct.c_void_p),
                        ("Persist", _wt.DWORD), ("AttributeCount", _wt.DWORD),
                        ("Attributes", _ct.c_void_p),
                        ("TargetAlias", _wt.LPWSTR), ("UserName", _wt.LPWSTR)]

        return _Cred
    except Exception:
        return None


def guardar_no_gerenciador(valor, alvo=ALVO_CREDMAN):
    """Grava no Gerenciador de Credenciais (DPAPI). Só Windows."""
    try:
        valor = (valor or "").strip()
        if not valor:
            return False, "segredo vazio — nada gravado"
        _adv = _advapi32()
        _Cred = _classe_cred()
        if _adv is None or _Cred is None:
            return False, "Gerenciador de Credenciais só existe no Windows"
        import ctypes as _ct
        from ctypes import wintypes as _wt
        _blob = _ct.create_string_buffer(valor.encode("utf-16-le"))
        _cred = _Cred()
        _cred.Flags = 0
        _cred.Type = 1  # CRED_TYPE_GENERIC
        _cred.TargetName = alvo
        _cred.Comment = "T! SOS DocFly Modular — segredo de sessão"
        _cred.CredentialBlobSize = len(_blob) - 1
        _cred.CredentialBlob = _ct.cast(_blob, _ct.c_void_p)
        _cred.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE
        _adv.CredWriteW.argtypes = [_ct.POINTER(_Cred), _wt.DWORD]
        _adv.CredWriteW.restype = _wt.BOOL
        if not _adv.CredWriteW(_ct.byref(_cred), 0):
            return False, "CredWriteW recusou a gravação"
        return True, alvo
    except Exception as e:
        try:
            _log().exception(f"guardar_no_gerenciador falhou: {e}")
        except Exception:
            pass
        return False, str(e)


def ler_do_gerenciador(alvo=ALVO_CREDMAN):
    """Lê do Gerenciador de Credenciais ("" quando ausente). Só Windows."""
    try:
        _adv = _advapi32()
        _Cred = _classe_cred()
        if _adv is None or _Cred is None:
            return ""
        import ctypes as _ct
        from ctypes import wintypes as _wt
        _adv.CredReadW.argtypes = [_wt.LPCWSTR, _wt.DWORD, _wt.DWORD,
                                   _ct.POINTER(_ct.POINTER(_Cred))]
        _adv.CredReadW.restype = _wt.BOOL
        _adv.CredFree.argtypes = [_ct.c_void_p]
        _ponteiro = _ct.POINTER(_Cred)()
        if not _adv.CredReadW(alvo, 1, 0, _ct.byref(_ponteiro)):
            return ""
        try:
            _cred = _ponteiro.contents
            _tamanho = int(_cred.CredentialBlobSize or 0)
            _endereco = int(_cred.CredentialBlob or 0)
            if not _tamanho or not _endereco:
                return ""
            return _ct.string_at(_endereco, _tamanho).decode(
                "utf-16-le").strip()
        finally:
            _adv.CredFree(_ponteiro)
    except Exception:
        try:
            _log().warning("ler_do_gerenciador: credencial ausente/ilegível")
        except Exception:
            pass
        return ""


def apagar_do_gerenciador(alvo=ALVO_CREDMAN):
    """Apaga a credencial do Gerenciador. Só Windows."""
    try:
        _adv = _advapi32()
        if _adv is None:
            return False, "Gerenciador de Credenciais só existe no Windows"
        from ctypes import wintypes as _wt
        _adv.CredDeleteW.argtypes = [_wt.LPCWSTR, _wt.DWORD, _wt.DWORD]
        _adv.CredDeleteW.restype = _wt.BOOL
        if not _adv.CredDeleteW(alvo, 1, 0):
            return False, "credencial inexistente ou sem permissão"
        return True, alvo
    except Exception as e:
        try:
            _log().exception(f"apagar_do_gerenciador falhou: {e}")
        except Exception:
            pass
        return False, str(e)


def obter_segredo_sessao():
    """(valor|None, origem). Precedência: env > arquivo > gerenciador.

    Nunca levanta: sem segredo em nenhum lugar devolve (None,
    "placeholder") e o boot avisa (nunca silencioso).
    """
    try:
        _v = (os.environ.get("TISOSDOCFLY_STORAGE_SECRET") or "").strip()
        if _v:
            return _v, "env:TISOSDOCFLY_STORAGE_SECRET"
        _cam = (os.environ.get("TISOSDOCFLY_STORAGE_SECRET_FILE") or "").strip()
        if _cam:
            _v = ler_de_arquivo(_cam)
            if _v:
                return _v, f"arquivo:{_cam}"
            return None, f"arquivo:{_cam} (ilegível)"
        if ((os.environ.get("TISOSDOCFLY_STORAGE_SECRET_CREDMAN") or "")
                .strip() == "1"):
            _v = ler_do_gerenciador()
            if _v:
                return _v, f"credman:{ALVO_CREDMAN}"
            return None, "credman (vazio/ausente)"
        return None, "placeholder"
    except Exception:
        try:
            _log().exception("obter_segredo_sessao falhou")
        except Exception:
            pass
        return None, "placeholder"


def _gerar_segredo():
    """Segredo forte (43+ chars URL-safe)."""
    try:
        import secrets as _st
        return _st.token_urlsafe(48)
    except Exception:
        return ""


def _cli():
    """CLI: guardar/conferir/apagar — nunca exibe o valor do segredo."""
    try:
        import argparse as _ap
        import getpass as _gp
        _p = _ap.ArgumentParser(prog="segredos.py",
                                description="Segredo de sessão em produção")
        _sub = _p.add_subparsers(dest="cmd", required=True)
        _g = _sub.add_parser("guardar", help="pede o segredo e guarda")
        _g.add_argument("--arquivo", nargs="?", const="",
                        help="grava em arquivo (padrão: pasta do usuário)")
        _g.add_argument("--gerenciador", action="store_true",
                        help="grava no Gerenciador de Credenciais (Windows)")
        _g.add_argument("--gerar", action="store_true",
                        help="gera um valor forte em vez de pedir")
        _sub.add_parser("conferir", help="diz de onde o boot leria (sem exibir)")
        _a = _sub.add_parser("apagar", help="apaga do Gerenciador")
        _a.add_argument("--alvo", default=ALVO_CREDMAN)
        _args = _p.parse_args()
        if _args.cmd == "guardar":
            if _args.gerar:
                _valor = _gerar_segredo()
            else:
                _valor = _gp.getpass("Segredo de sessão (não aparece): ").strip()
            if not _valor:
                print("segredo vazio — nada gravado")
                return 1
            if _args.gerenciador:
                _ok, _msg = guardar_no_gerenciador(_valor)
            else:
                _ok, _msg = guardar_em_arquivo(
                    _valor, _args.arquivo or None)
            print(("guardado em " if _ok else "FALHA: ") + str(_msg))
            return 0 if _ok else 1
        if _args.cmd == "conferir":
            _v, _origem = obter_segredo_sessao()
            print(f"origem: {_origem} | presente: {'sim' if _v else 'não'}")
            return 0
        if _args.cmd == "apagar":
            _ok, _msg = apagar_do_gerenciador(_args.alvo)
            print(("apagado " if _ok else "FALHA: ") + str(_msg))
            return 0 if _ok else 1
        return 1
    except Exception as e:
        print(f"segredos: falha ({e})")
        return 1


if __name__ == "__main__":
    sys.exit(_cli())
