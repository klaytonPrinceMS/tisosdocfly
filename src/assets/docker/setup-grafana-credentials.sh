#!/bin/bash
# =============================================================================
# Setup Grafana Credentials - Skyrover Modular
# =============================================================================
# Script para configurar as credenciais do Grafana igual ao usuário master
# da Skyrover (master/master).
#
# Uso:
#   ./setup-grafana-credentials.sh
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}  Configurar Credenciais Grafana            ${NC}"
    echo -e "${BLUE}  (master/master como Skyrover)              ${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
}

check_docker() {
    echo -e "${YELLOW}Verificando Docker...${NC}"
    
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}✗ Docker não encontrado.${NC}"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        echo -e "${RED}✗ Docker não está rodando.${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ Docker disponível${NC}"
    echo ""
}

check_grafana() {
    echo -e "${YELLOW}Verificando Grafana...${NC}"
    
    # Check if Grafana container is running
    if ! docker inspect skyrover-grafana &> /dev/null; then
        echo -e "${RED}✗ Container do Grafana não encontrado.${NC}"
        echo "  Inicie a stack primeiro: cd assets/docker && ./start.sh"
        exit 1
    fi
    
    # Check if Grafana is running
    STATUS=$(docker inspect --format '{{.State.Running}}' skyrover-grafana 2>/dev/null)
    if [ "$STATUS" != "true" ]; then
        echo -e "${RED}✗ Grafana não está rodando.${NC}"
        echo "  Inicie a stack primeiro: cd assets/docker && ./start.sh"
        exit 1
    fi
    
    echo -e "${GREEN}✓ Grafana rodando${NC}"
    echo ""
}

update_grafana_password() {
    echo -e "${YELLOW}Atualizando senha do Grafana via CLI...${NC}"
    
    # Reset admin password using Grafana CLI (método confiável no Grafana 13+)
    RESULT=$(docker exec skyrover-grafana grafana cli admin reset-admin-password master 2>&1)
    
    if echo "$RESULT" | grep -qi "changed successfully"; then
        echo -e "${GREEN}✓ Senha do admin atualizada para 'master'${NC}"
    else
        echo -e "${YELLOW}⚠ Não foi possível atualizar senha: $RESULT${NC}"
    fi
    
    echo ""
}

restart_grafana() {
    echo -e "${YELLOW}Reiniciando Grafana para aplicar configurações...${NC}"
    
    docker restart skyrover-grafana
    
    # Wait for Grafana to be ready
    echo "Aguardando Grafana inicializar..."
    for i in {1..30}; do
        if curl -s http://localhost:3000/api/health | grep -q "ok"; then
            echo -e "${GREEN}✓ Grafana reiniciado e pronto${NC}"
            break
        fi
        sleep 1
    done
    
    echo ""
}

show_credentials() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${GREEN}  Credenciais do Grafana Configuradas!       ${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
    echo -e "  URL:      ${BLUE}http://localhost:3000${NC}"
    echo -e "  Usuário:  ${GREEN}master${NC}"
    echo -e "  Senha:    ${GREEN}master${NC}"
    echo ""
    echo -e "  (Mesmas credenciais do usuário master da Skyrover)"
    echo ""
    echo -e "${BLUE}============================================${NC}"
}

main() {
    print_header
    check_docker
    check_grafana
    update_grafana_password
    restart_grafana
    show_credentials
}

main "$@"