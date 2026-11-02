#!/bin/bash
# =============================================================================
# Quick Start Script - OTel LGTM Stack
# =============================================================================
# Script para iniciar rapidamente a stack de observabilidade.
#
# Uso:
#   ./start.sh          # Iniciar stack
#   ./start.sh stop     # Parar stack
#   ./start.sh status   # Ver status
#   ./start.sh logs     # Ver logs
#   ./start.sh test     # Testar integração
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
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

# =============================================================================
# Functions
# =============================================================================

print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}  OTel LGTM Stack - Skyrover Modular       ${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
}

check_docker() {
    echo -e "${YELLOW}Verificando Docker...${NC}"
    
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}✗ Docker não encontrado. Instale o Docker primeiro.${NC}"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        echo -e "${RED}✗ Docker não está rodando. Inicie o Docker Desktop.${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ Docker disponível${NC}"
    
    # Check Docker Compose
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        echo -e "${RED}✗ Docker Compose não encontrado.${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ Docker Compose disponível${NC}"
    echo ""
}

start_stack() {
    echo -e "${YELLOW}Iniciando stack OTel LGTM...${NC}"
    
    cd "$SCRIPT_DIR"
    
    # Start services
    $COMPOSE_CMD up -d
    
    echo ""
    echo -e "${GREEN}✓ Stack iniciada com sucesso!${NC}"
    echo ""
    echo -e "Serviços disponíveis:"
    echo -e "  • Grafana:      ${BLUE}http://localhost:3000${NC}"
    echo -e "  • OTel Collector: ${BLUE}localhost:4317${NC} (gRPC)"
    echo -e "  • Loki:         ${BLUE}http://localhost:3100${NC}"
    echo -e "  • Tempo:        ${BLUE}http://localhost:3200${NC}"
    echo -e "  • Mimir:        ${BLUE}http://localhost:9009${NC}"
    echo ""
    echo -e "Credenciais Grafana: ${GREEN}master / master${NC}"
    echo ""
}

stop_stack() {
    echo -e "${YELLOW}Parando stack OTel LGTM...${NC}"
    
    cd "$SCRIPT_DIR"
    $COMPOSE_CMD down
    
    echo ""
    echo -e "${GREEN}✓ Stack parada${NC}"
    echo ""
}

show_status() {
    echo -e "${YELLOW}Status da stack OTel LGTM...${NC}"
    echo ""
    
    cd "$SCRIPT_DIR"
    $COMPOSE_CMD ps
    echo ""
}

show_logs() {
    echo -e "${YELLOW}Logs da stack OTel LGTM (Ctrl+C para sair)...${NC}"
    echo ""
    
    cd "$SCRIPT_DIR"
    $COMPOSE_CMD logs -f
}

test_integration() {
    echo -e "${YELLOW}Testando integração OTel...${NC}"
    echo ""
    
    cd "$PROJECT_DIR"
    python tests/test_otel.py
}

show_help() {
    echo "Uso: $0 [comando]"
    echo ""
    echo "Comandos:"
    echo "  (nenhum)   Iniciar a stack OTel LGTM"
    echo "  stop       Parar a stack"
    echo "  status     Ver status dos serviços"
    echo "  logs       Ver logs em tempo real"
    echo "  test       Testar integração com a Skyrover"
    echo "  help       Mostrar esta ajuda"
    echo ""
    echo "Exemplos:"
    echo "  $0              # Inicia a stack"
    echo "  $0 stop         # Para a stack"
    echo "  $0 status       # Mostra status"
    echo "  $0 logs         # Mostra logs"
    echo "  $0 test         # Testa integração"
    echo ""
}

# =============================================================================
# Main
# =============================================================================

print_header

case "${1:-start}" in
    start)
        check_docker
        start_stack
        ;;
    stop)
        check_docker
        stop_stack
        ;;
    status)
        check_docker
        show_status
        ;;
    logs)
        check_docker
        show_logs
        ;;
    test)
        check_docker
        test_integration
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Comando inválido: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac