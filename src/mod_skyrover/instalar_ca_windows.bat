@echo off
REM Instala a CA raiz local "T! SOS Sistemas / Klayton Prince" no Windows.
REM EN: Installs the local root CA on Windows (Trusted Root).
REM
REM Como usar: copie este .bat JUNTO com a pasta tls\ (ca_cert.pem) para a
REM maquina, clique com o botao direito > "Executar como administrador".
REM Sem admin o certutil nega (proposital: raiz confiavel e area de sistema).
REM Efeito: o aviso "site nao seguro" some em Chrome/Edge apos reabrir o
REM navegador. Firefox usa cofre proprio (ver docs/seguranca/certificado_tls.md).

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Execute como administrador: botao direito ^> Executar como administrador.
    pause
    exit /b 1
)

set "CA=%~dp0tls\ca_cert.pem"
if not exist "%CA%" (
    echo [ERRO] Nao achei "%CA%". Copie a pasta tls\ para junto deste .bat.
    pause
    exit /b 1
)

certutil -addstore Root "%CA%"
if %errorlevel% neq 0 (
    echo [ERRO] certutil falhou (%errorlevel%).
    pause
    exit /b 1
)

echo [OK] CA instalada. Feche e reabra o navegador.
pause
