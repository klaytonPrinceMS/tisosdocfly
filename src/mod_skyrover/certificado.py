"""TLS autossuficiente com CA própria — sem aquisição externa.

EN: Self-contained TLS with a private CA — no external acquisition.

Modelo (24/10/2026, pedido do responsável): a **CA raiz local "T! SOS
Sistemas"** emite o certificado do servidor. Instala-se a CA **uma vez**
nas máquinas (`tls/ca_cert.pem`); todo certificado de servidor emitido
depois já nasce confiável, sem reinstalar nada.

- Folha do servidor: CN `SKYROVER DTI`, O = a prefeitura (env
  `SKYROVER_TLS_ORG` > `orgao_nome` do painel), OU `DTI - Divisão de
  Tecnologia da Informação`, SAN com `localhost`, hostname, `skyrover`,
  `skyrover-dti`, `127.0.0.1` e os IPs da rede local.
- CA raiz: CN `Administrador do sistema` (env `SKYROVER_TLS_CA_CN`), O
  `T! SOS Sistemas` (env `SKYROVER_TLS_CA_ORG`), validade 10 anos, só
  assina (não serve tráfego).

Tudo com a biblioteca `cryptography` (já dependência do projeto).
Nenhum openssl na máquina, nenhuma AC externa, nenhuma compra.

Uso:
    poetry run python src/mod_skyrover/certificado.py
    # grava src/mod_skyrover/tls/ca_cert.pem + ca_key.pem (a CA) e
    # cert.pem + key.pem (a folha) — tudo fora do git.

O `main.py` liga o TLS sozinho quando folha+chave existem
(`SKYROVER_TLS_CERT`/`SKYROVER_TLS_KEY` mudam o caminho), e junto liga
o `Secure` no cookie e o HSTS — que são os condicionais já prontos.

Ressalva honesta que continua valendo: CA própria NÃO prova identidade
para a internet — para acesso externo, aí sim Let's Encrypt. Dentro da
rede do órgão, a cadeia fecha: quem confia na CA fala com este servidor.
"""

import datetime
import os
import socket
import sys

try:
    BASE_MOD = os.path.dirname(os.path.abspath(__file__))
except NameError:
    BASE_MOD = os.path.dirname(os.path.abspath(sys.argv[0]))

PASTA_TLS = os.path.join(BASE_MOD, "tls")
CERT_PADRAO = os.path.join(PASTA_TLS, "cert.pem")
CHAVE_PADRAO = os.path.join(PASTA_TLS, "key.pem")
CA_CERT_PADRAO = os.path.join(PASTA_TLS, "ca_cert.pem")
CA_CHAVE_PADRAO = os.path.join(PASTA_TLS, "ca_key.pem")

CN_CA = os.environ.get("SKYROVER_TLS_CA_CN", "Administrador do sistema")
ORG_CA = os.environ.get("SKYROVER_TLS_CA_ORG", "T! SOS Sistemas")
CN_SERVIDOR_PADRAO = "SKYROVER DTI"
OU_PADRAO = "DTI - Divisão de Tecnologia da Informação"
DIAS_FOLHA = 825  # teto que os navegadores aceitam
DIAS_CA = 3650  # 10 anos: a raiz dura, a folha renova


def certificado_pronto(cert_path=None, chave_path=None) -> bool:
    """True se folha+chave do TLS existem e têm conteúdo."""
    try:
        cert_path = cert_path or os.environ.get("SKYROVER_TLS_CERT",
                                                CERT_PADRAO)
        chave_path = chave_path or os.environ.get("SKYROVER_TLS_KEY",
                                                  CHAVE_PADRAO)
        return (os.path.isfile(cert_path)
                and os.path.getsize(cert_path) > 0
                and os.path.isfile(chave_path)
                and os.path.getsize(chave_path) > 0)
    except Exception:
        return False


def nome_organizacao() -> str:
    """O (organização): a prefeitura, sem dado pessoal.

    Ordem: env `SKYROVER_TLS_ORG` > `orgao_nome` do painel (o nome
    oficial, o mesmo das telas — quem troca lá, troca aqui no próximo
    `gerar`) > "SKYROVER". Nome de pessoa NÃO entra em certificado de
    servidor: o cert identifica o SERVIÇO (CN) e a instituição (O);
    pessoa aparece no login e na auditoria.
    """
    try:
        de_env = (os.environ.get("SKYROVER_TLS_ORG") or "").strip()
        if de_env:
            return de_env
    except Exception:
        pass
    try:
        import sys as _sys
        _src = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if _src not in _sys.path:
            _sys.path.insert(0, _src)
        from mod_skyrover.bd_conexao import get_config as _cfg
        for _chave in ("orgao_nome", "prefeitura"):
            nome = (_cfg(_chave, "") or "").strip()
            if nome and nome != "Nome da instituição":
                return nome
    except Exception:
        pass
    return "SKYROVER"


def _nomes_san(cn_servidor: str):
    """SAN da folha: localhost, nomes curtos, hostname e IPs locais."""
    try:
        from cryptography import x509
    except Exception:
        return []
    try:
        import ipaddress as _ipmod
        # Nomes locais extras (24/10/2026): `SKYROVER_TLS_SAN_EXTRA`
        # com nomes separados por vírgula (ex.: "skyrover.gov"). É o que
        # faz a URL curta do DNS interno não dar erro de NOME no TLS —
        # sem estar no SAN, o navegador reclama mesmo com a CA instalada.
        # Reemitir a folha não pede reinstalar a CA (ela não muda).
        _extras = [e.strip() for e in
                   (os.environ.get("SKYROVER_TLS_SAN_EXTRA") or "")
                   .replace(";", ",").split(",")]
        _extras = [e for e in _extras if e]
        nomes = [x509.DNSName("localhost"),
                 x509.DNSName(cn_servidor),
                 x509.DNSName("skyrover"),
                 x509.DNSName("skyrover-dti")]
        nomes += [x509.DNSName(e) for e in _extras]
        nomes.append(x509.IPAddress(_ipmod.ip_address("127.0.0.1")))
        try:
            nomes.append(x509.DNSName(socket.gethostname()))
        except Exception:
            pass
        _vistos = set()
        try:
            _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            _s.connect(("8.8.8.8", 80))
            _vistos.add(_s.getsockname()[0])
            _s.close()
        except Exception:
            pass
        try:
            for _ip in socket.gethostbyname_ex(socket.gethostname())[2]:
                _vistos.add(_ip)
        except Exception:
            pass
        for _ip in sorted(_vistos):
            try:
                _obj = _ipmod.ip_address(_ip)
                if not (_obj.is_loopback or _obj.is_link_local):
                    nomes.append(x509.IPAddress(_obj))
            except Exception:
                pass
        return nomes
    except Exception:
        return []


def _chave_rsa():
    from cryptography.hazmat.primitives.asymmetric import rsa
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _gravar_chave(chave, caminho):
    from cryptography.hazmat.primitives import serialization
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with open(caminho, "wb") as fh:
        fh.write(chave.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()))
    try:
        os.chmod(caminho, 0o600)
    except Exception:
        pass


def _gravar_cert(cert, caminho):
    from cryptography.hazmat.primitives import serialization
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with open(caminho, "wb") as fh:
        fh.write(cert.public_bytes(serialization.Encoding.PEM))


def garantir_ca():
    """Cria a CA "T! SOS Sistemas" se ainda não existe; reutiliza se existe.

    Reutilizar de propósito: reemitir a folha sem trocar a CA mantém
    todas as máquinas confiando, sem reinstalar nada. Devolve
    (chave_ca, cert_ca).
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID
    ca_cert = os.environ.get("SKYROVER_TLS_CA_CERT", CA_CERT_PADRAO)
    ca_chave = os.environ.get("SKYROVER_TLS_CA_KEY", CA_CHAVE_PADRAO)
    if (os.path.isfile(ca_cert) and os.path.getsize(ca_cert) > 0
            and os.path.isfile(ca_chave) and os.path.getsize(ca_chave) > 0):
        from cryptography.hazmat.primitives import serialization
        with open(ca_chave, "rb") as fh:
            chave_ca = serialization.load_pem_private_key(
                fh.read(), password=None)
        with open(ca_cert, "rb") as fh:
            cert_ca = x509.load_pem_x509_certificate(fh.read())
        return chave_ca, cert_ca
    chave_ca = _chave_rsa()
    nome_ca = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, CN_CA),
         x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORG_CA)])
    agora = datetime.datetime.now(datetime.timezone.utc)
    cert_ca = (x509.CertificateBuilder()
               .subject_name(nome_ca).issuer_name(nome_ca)
               .public_key(chave_ca.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(agora)
               .not_valid_after(agora + datetime.timedelta(days=DIAS_CA))
               .add_extension(x509.BasicConstraints(ca=True,
                                                   path_length=0),
                              critical=True)
               .add_extension(x509.KeyUsage(
                   digital_signature=True, content_commitment=False,
                   key_encipherment=False, data_encipherment=False,
                   key_agreement=False, key_cert_sign=True,
                   crl_sign=True, encipher_only=False,
                   decipher_only=False), critical=True)
               .sign(chave_ca, hashes.SHA256()))
    _gravar_chave(chave_ca, ca_chave)
    _gravar_cert(cert_ca, ca_cert)
    return chave_ca, cert_ca


def gerar_servidor(cert_path=None, chave_path=None, cn=None, dias=None):
    """Emite a folha do servidor assinada pela CA. Devolve (ok, msg)."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    except Exception as e:
        return False, f"biblioteca cryptography indisponível: {e}"
    try:
        cn = (cn or os.environ.get("SKYROVER_TLS_CN")
              or CN_SERVIDOR_PADRAO).strip()
        ou = (os.environ.get("SKYROVER_TLS_OU") or OU_PADRAO).strip()
        dias = int(dias or DIAS_FOLHA)
        cert_path = cert_path or os.environ.get("SKYROVER_TLS_CERT",
                                                CERT_PADRAO)
        chave_path = chave_path or os.environ.get("SKYROVER_TLS_KEY",
                                                  CHAVE_PADRAO)
        chave_ca, cert_ca = garantir_ca()
        san = _nomes_san(cn)
        if not san:
            return False, "não foi possível montar o SAN"
        chave = _chave_rsa()
        assunto = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, cn),
             x509.NameAttribute(NameOID.ORGANIZATION_NAME,
                                nome_organizacao()),
             x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, ou)])
        agora = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder()
                .subject_name(assunto).issuer_name(cert_ca.subject)
                .public_key(chave.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(agora)
                .not_valid_after(agora + datetime.timedelta(days=dias))
                .add_extension(x509.SubjectAlternativeName(san),
                               critical=False)
                .add_extension(x509.BasicConstraints(ca=False,
                                                    path_length=None),
                               critical=True)
                .add_extension(x509.KeyUsage(
                    digital_signature=True, content_commitment=False,
                    key_encipherment=True, data_encipherment=False,
                    key_agreement=False, key_cert_sign=False,
                    crl_sign=False, encipher_only=False,
                    decipher_only=False), critical=True)
                .add_extension(x509.ExtendedKeyUsage(
                    [ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .sign(chave_ca, hashes.SHA256()))
        _gravar_chave(chave, chave_path)
        _gravar_cert(cert, cert_path)
        return True, (f"folha '{cn}' emitida por '{CN_CA}' em "
                      f"{cert_path} + {chave_path} "
                      f"(instalar: {os.environ.get('SKYROVER_TLS_CA_CERT', CA_CERT_PADRAO)})")
    except Exception as e:
        return False, f"falha ao gerar: {e}"


def gerar_autossinado(*a, **kw):
    """Compat: agora emite pela CA (antes era autossinado puro)."""
    return gerar_servidor(*a, **kw)


def gerar():
    """Garante a CA e emite (ou renova) a folha. Ponto único da CLI."""
    return gerar_servidor()


if __name__ == "__main__":
    ok, msg = gerar()
    print(msg)
    sys.exit(0 if ok else 1)
