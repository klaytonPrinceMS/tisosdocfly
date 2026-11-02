#!/bin/bash
# Instala a CA raiz local "T! SOS Sistemas / Klayton Prince" no Linux.
# EN: Installs the local root CA on Linux (system trust store).
#
# Como usar: copie este .sh JUNTO com a pasta tls/ (ca_cert.pem) para a
# maquina e rode:  sudo bash instalar_ca_linux.sh
# Efeito: o aviso "site nao seguro" some em Chrome apos reabrir o
# navegador. Firefox usa cofre proprio (ver docs/seguranca/certificado_tls.md).
set -e
cd "$(dirname "$0")"

CA="tls/ca_cert.pem"
if [ ! -f "$CA" ]; then
    echo "[ERRO] Nao achei $CA. Copie a pasta tls/ para junto deste .sh."
    exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
    echo "[ERRO] Rode com sudo: sudo bash instalar_ca_linux.sh"
    exit 1
fi

if command -v update-ca-certificates >/dev/null 2>&1; then
    # Debian/Ubuntu
    cp "$CA" /usr/local/share/ca-certificates/skyrover-ca.crt
    update-ca-certificates
elif command -v update-ca-trust >/dev/null 2>&1; then
    # RHEL/Fedora
    cp "$CA" /etc/pki/ca-trust/source/anchors/skyrover-ca.crt
    update-ca-trust extract
else
    echo "[ERRO] Nem update-ca-certificates nem update-ca-trust encontrados."
    exit 1
fi

echo "[OK] CA instalada. Feche e reabra o navegador."
