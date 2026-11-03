#!/bin/bash
# =============================================================================
# Verify Credentials - T! SOS DocFly Modular
# =============================================================================
# Script para verificar se todas as credenciais estão configuradas corretamente.
#
# Uso:
#   ./verify-credentials.sh
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}  Verificar Credenciais - T! SOS DocFly          ${NC}"
    echo -e "${BLUE}  Padrão: master/master                      ${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
}

check_docker() {
    echo -e "${YELLOW}1. Verificando Docker...${NC}"
    
    if ! command -v docker &> /dev/null; then
        echo -e "   ${RED}✗ Docker não encontrado${NC}"
        return 1
    fi
    
    if ! docker info &> /dev/null; then
        echo -e "   ${RED}✗ Docker não está rodando${NC}"
        return 1
    fi
    
    echo -e "   ${GREEN}✓ Docker disponível${NC}"
    return 0
}

check_grafana() {
    echo -e "${YELLOW}2. Verificando Grafana...${NC}"
    
    # Check if container exists
    if ! docker inspect tisosdocfly-grafana &> /dev/null; then
        echo -e "   ${RED}✗ Container do Grafana não encontrado${NC}"
        return 1
    fi
    
    # Check if running
    STATUS=$(docker inspect --format '{{.State.Running}}' tisosdocfly-grafana 2>/dev/null)
    if [ "$STATUS" != "true" ]; then
        echo -e "   ${RED}✗ Grafana não está rodando${NC}"
        return 1
    fi
    
    echo -e "   ${GREEN}✓ Grafana rodando${NC}"
    
    # Check credentials using basic auth (método confiável no Grafana 13+)
    echo -e "${YELLOW}3. Verificando credenciais do Grafana...${NC}"
    
    RESPONSE=$(curl -s -o /tmp/grafana_check.json -w "%{http_code}" \
        -u master:master http://localhost:3000/api/user)
    
    if [ "$RESPONSE" = "200" ]; then
        LOGIN=$(grep -o '"login":"[^"]*"' /tmp/grafana_check.json | head -1 | cut -d'"' -f4)
        echo -e "   ${GREEN}✓ Credenciais master/master funcionando (usuário: $LOGIN)${NC}"
        return 0
    else
        echo -e "   ${RED}✗ Credenciais master/master não funcionam (HTTP $RESPONSE)${NC}"
        return 1
    fi
}

check_loki() {
    echo -e "${YELLOW}4. Verificando Loki...${NC}"
    
    if ! docker inspect tisosdocfly-loki &> /dev/null; then
        echo -e "   ${RED}✗ Container do Loki não encontrado${NC}"
        return 1
    fi
    
    STATUS=$(docker inspect --format '{{.State.Running}}' tisosdocfly-loki 2>/dev/null)
    if [ "$STATUS" != "true" ]; then
        echo -e "   ${RED}✗ Loki não está rodando${NC}"
        return 1
    fi
    
    echo -e "   ${GREEN}✓ Loki rodando${NC}"
    return 0
}

check_tempo() {
    echo -e "${YELLOW}5. Verificando Tempo...${NC}"
    
    if ! docker inspect tisosdocfly-tempo &> /dev/null; then
        echo -e "   ${RED}✗ Container do Tempo não encontrado${NC}"
        return 1
    fi
    
    STATUS=$(docker inspect --format '{{.State.Running}}' tisosdocfly-tempo 2>/dev/null)
    if [ "$STATUS" != "true" ]; then
        echo -e "   ${RED}✗ Tempo não está rodando${NC}"
        return 1
    fi
    
    echo -e "   ${GREEN}✓ Tempo rodando${NC}"
    return 0
}

check_mimir() {
    echo -e "${YELLOW}6. Verificando Mimir...${NC}"
    
    if ! docker inspect tisosdocfly-mimir &> /dev/null; then
        echo -e "   ${RED}✗ Container do Mimir não encontrado${NC}"
        return 1
    fi
    
    STATUS=$(docker inspect --format '{{.State.Running}}' tisosdocfly-mimir 2>/dev/null)
    if [ "$STATUS" != "true" ]; then
        echo -e "   ${RED}✗ Mimir não está rodando${NC}"
        return 1
    fi
    
    echo -e "   ${GREEN}✓ Mimir rodando${NC}"
    return 0
}

check_otel_collector() {
    echo -e "${YELLOW}7. Verificando OTel Collector...${NC}"
    
    if ! docker inspect tisosdocfly-otel-collector &> /dev/null; then
        echo -e "   ${RED}✗ Container do OTel Collector não encontrado${NC}"
        return 1
    fi
    
    STATUS=$(docker inspect --format '{{.State.Running}}' tisosdocfly-otel-collector 2>/dev/null)
    if [ "$STATUS" != "true" ]; then
        echo -e "   ${RED}✗ OTel Collector não está rodando${NC}"
        return 1
    fi
    
    echo -e "   ${GREEN}✓ OTel Collector rodando${NC}"
    return 0
}

show_summary() {
    echo ""
    echo -e "${BLUE}============================================${NC}"
    echo -e "${GREEN}  Resumo da Verificação                     ${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
    echo -e "  Serviços rodando:     ${GREEN}$SERVICES_RUNNING/5${NC}"
    echo -e "  Credenciais Grafana:  ${GREEN}master/master${NC}"
    echo ""
    echo -e "  URLs de Acesso:"
    echo -e "    • Grafana:      ${BLUE}http://localhost:3000${NC}"
    echo -e "    • Loki:         ${BLUE}http://localhost:3100${NC}"
    echo -e "    • Tempo:        ${BLUE}http://localhost:3200${NC}"
    echo -e "    • Mimir:        ${BLUE}http://localhost:9009${NC}"
    echo -e "    • OTel Collect: ${BLUE}http://localhost:8888${NC}"
    echo ""
    echo -e "${BLUE}============================================${NC}"
}

main() {
    print_header
    
    SERVICES_RUNNING=0
    
    check_docker && SERVICES_RUNNING=$((SERVICES_RUNNING + 1))
    check_grafana && SERVICES_RUNNING=$((SERVICES_RUNNING + 1))
    check_loki && SERVICES_RUNNING=$((SERVICES_RUNNING + 1))
    check_tempo && SERVICES_RUNNING=$((SERVICES_RUNNING + 1))
    check_mimir && SERVICES_RUNNING=$((SERVICES_RUNNING + 1))
    check_otel_collector && SERVICES_RUNNING=$((SERVICES_RUNNING + 1))
    
    show_summary
}

main "$@"