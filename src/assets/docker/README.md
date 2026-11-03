# Docker - T! SOS DocFly Modular

## Visão Geral

Esta pasta contém a configuração Docker para a stack de observabilidade da T! SOS DocFly Modular, utilizando **Grafana OTel LGTM** (Grafana + Loki + Tempo + Mimir + OpenTelemetry Collector).

## Objetivo

Fornecer uma stack completa de observabilidade para monitoramento de:

- **Logs** (via Loki) - Registros de eventos e erros do sistema
- **Traces** (via Tempo) - Rastreamento de requisições e latência
- **Métricas** (via Mimir) - Indicadores de performance e uso de recursos
- **Telemetria** (via OTel Collector) - Recoleção padronizada via OpenTelemetry

---

## Instalação

### Pré-requisitos

1. **Docker Desktop** (Windows/Mac) ou **Docker Engine** (Linux)
   - [Docker Desktop para Windows](https://docs.docker.com/desktop/install/windows-install/)
   - [Docker Desktop para Mac](https://docs.docker.com/desktop/install/mac-install/)
   - [Docker Engine para Linux](https://docs.docker.com/engine/install/)

2. **Docker Compose** (já incluído no Docker Desktop v2+)

### Verificar Instalação

```bash
# Verificar Docker
docker --version

# Verificar Docker Compose
docker compose version

# Verificar se Docker está rodando
docker info
```

### Instalar Dependências Python (Opcional)

Para integração completa com a T! SOS DocFly:

```bash
# Ativar ambiente virtual
source .venv/bin/activate  # Linux/Mac
# ou
.venv\Scripts\activate     # Windows

# Instalar dependências OTel
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc
```

---

## Uso

### Opção 1: Auto-inicialização (Recomendado)

Ao rodar o `main.py`, a stack OTel é iniciada **automaticamente** se o Docker estiver disponível:

```bash
# Simplesmente rode a aplicação
.venv/bin/python main.py

# A stack OTel será iniciada automaticamente
# Logs aparecerão no terminal:
# [otel] Docker detected, starting OTel LGTM stack...
# [otel] OTel stack started successfully
# [otel] OpenTelemetry initialized (endpoint=localhost:4317)
```

**O que acontece:**
1. O `main.py` verifica se o Docker está disponível
2. Se disponível, inicia a stack OTel (Grafana, Loki, Tempo, Mimir, OTel Collector)
3. Configura o OpenTelemetry SDK para enviar dados
4. Ao encerrar o `main.py`, a stack OTel é finalizada automaticamente

### Opção 2: Script de Inicialização

Use o script `start.sh` para gerenciar a stack manualmente:

```bash
# Navegar até a pasta docker
cd assets/docker

# Iniciar stack
./start.sh

# Ver status
./start.sh status

# Ver logs
./start.sh logs

# Parar stack
./start.sh stop

# Testar integração
./start.sh test
```

### Opção 3: Docker Compose Direto

```bash
# Navegar até a pasta docker
cd assets/docker

# Iniciar todos os serviços
docker compose up -d

# Ver status
docker compose ps

# Ver logs
docker compose logs -f

# Parar serviços
docker compose down
```

## Credenciais e Autenticação

### Padrão de Credenciais (master/master)

Todos os serviços usam as mesmas credenciais do usuário **master** da T! SOS DocFly:

| Serviço | Usuário | Senha | Acesso |
|---------|---------|-------|--------|
| **Grafana** | master | master | http://localhost:3000 |
| Loki | (interno) | (interno) | Via Grafana |
| Tempo | (interno) | (interno) | Via Grafana |
| Mimir | (interno) | (interno) | Via Grafana |
| OTel Collector | (interno) | (interno) | Via rede Docker |

### Como Funciona a Autenticação

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EXTERNO (Internet)                          │
│                                                                     │
│   Seu Navegador → http://localhost:3000 (Grafana)                  │
│                   Login: master / master                            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         INTERNO (Docker)                            │
│                                                                     │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐         │
│   │   Grafana   │────→│    Loki     │     │    Tempo    │         │
│   │  (auth OK)  │     │ (sem auth)  │     │ (sem auth)  │         │
│   └─────────────┘     └─────────────┘     └─────────────┘         │
│                                                                     │
│   ┌─────────────┐     ┌─────────────┐                             │
│   │    Mimir    │     │ OTel Collect│                             │
│   │ (sem auth)  │     │ (sem auth)  │                             │
│   └─────────────┘     └─────────────┘                             │
│                                                                     │
│   NOTA: Serviços internos NÃO requerem autenticação               │
│         pois só são acessíveis pela rede Docker.                   │
└─────────────────────────────────────────────────────────────────────┘
```

**Por que não usar autenticação nos serviços internos?**

1. **Segurança**: Os serviços só são acessíveis dentro da rede Docker
2. **Simplicidade**: Evita configuração complexa de autenticação
3. **Performance**: Sem overhead de verificação de credenciais
4. **Padrão**: É a prática recomendada para stacks Docker

### Configuração Automática

Quando você inicia o `main.py`:
1. A stack OTel é iniciada automaticamente
2. O Grafana é configurado com as credenciais master/master
3. As credenciais são sincronizadas com o banco de dados da T! SOS DocFly

### Configuração Manual

Se precisar reconfigurar as credenciais do Grafana:

```bash
# Navegar até a pasta docker
cd assets/docker

# Executar script de configuração
./setup-grafana-credentials.sh
```

### Verificação de Credenciais

Para verificar se todas as credenciais estão configuradas corretamente:

```bash
# Navegar até a pasta docker
cd assets/docker

# Executar script de verificação
./verify-credentials.sh
```

Este script verifica:
- Se o Docker está disponível
- Se todos os serviços estão rodando
- Se as credenciais master/master funcionam no Grafana

### Provisioning

O Grafana usa provisioning para configurar usuários automaticamente:

```yaml
# config/grafana-provisioning/users/users.yml
apiVersion: 1
users:
  - login: master
    name: Master Admin
    email: admin@tisosdocfly.local
    password: master
    orgRole: Admin
```

> **Nota**: O provisioning de usuários via arquivo não é 100% confiável no Grafana 13+. O usuário admin `master`/`master` é criado de forma confiável via variáveis de ambiente (`GF_SECURITY_ADMIN_USER`/`GF_SECURITY_ADMIN_PASSWORD`) no `compose.yml`. Para reconfigurar a senha manualmente, use: `docker exec tisosdocfly-grafana grafana cli admin reset-admin-password master`.

### Dashboards Automatizados

A pasta `assets/docker/config/grafana-dashboards/` contém os dashboards **providos automaticamente** no Grafana:

| Dashboard | Fonte de dados | UID |
|-----------|---------------|-----|
| **T! SOS DocFly - Visão Geral** | Mimir (métricas) | `tisosdocfly-visao-geral` |
| **T! SOS DocFly - Traces** | Tempo | `tisosdocfly-traces` |
| **T! SOS DocFly - Logs** | Loki | `tisosdocfly-logs` |

- O provider é configurado em `config/grafana-provisioning/dashboards/dashboards.yml` (atualiza a cada 30s)
- Os dashboards são montados via volume em `/var/lib/grafana/dashboards`
- Para adicionar um dashboard: basta criar um `.json` em `assets/docker/config/grafana-dashboards/`

#### Provisionar via API (alternativa)

Se preferir provisionar via API (útil fora do Docker):

```bash
# Navegar até a pasta docker
cd assets/docker

# Provisionar os dashboards
python3 grafana_provision.py

# Ver listagem (sem alterar)
python3 grafana_provision.py --dry-run
```

**Nota**: Se o provisioning por arquivo estiver ativo, os dashboards são gerenciados por ele (o script via API retornará "Cannot save provisioned dashboard").

---

## Portas e Serviços

### Portas Mapeadas (Host → Container)

| Serviço | Porta no Host | Protocolo | Descrição |
|---------|---------------|-----------|-----------|
| **Grafana** | 3000 | HTTP | Dashboard de visualização |
| **OTel Collector** | 4317 | gRPC | Recepção OTLP (host→Docker) |
| **OTel Collector** | 4318 | HTTP | Recepção OTLP (host→Docker) |
| **Loki** | 3100 | HTTP | API de logs |
| **Tempo** | 3200 | HTTP | API de traces |
| **Mimir** | 9009 | HTTP | API de métricas |

### Acessar os Serviços

| Serviço | URL | Credenciais |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | master / master |
| Loki | http://localhost:3100 | - |
| Tempo | http://localhost:3200 | - |
| Mimir | http://localhost:9009 | - |
| OTel Collector | http://localhost:8888 | - |

**Nota:** As credenciais do Grafana (master/master) são iguais ao usuário administrador da T! SOS DocFly.

---

## Como Funciona

### Fluxo de Dados

```
┌─────────────────────────────────────────────────────────────────────┐
│                         T! SOS DocFly Modular                            │
│                          (Python/NiceGUI)                           │
│                         RODA NO HOST                                │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ localhost:4317 (gRPC)
                                │ localhost:4318 (HTTP)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    OpenTelemetry Collector                          │
│                    RODA NO DOCKER                                   │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                │
│  │   Logs      │  │   Traces    │  │  Métricas   │                │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                │
└─────────┼────────────────┼────────────────┼────────────────────────┘
          │                │                │
          │ Nomes de serviço Docker (rede interna)
          ▼                ▼                ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│      Loki       │ │      Tempo      │ │      Mimir      │
│   http://loki   │ │   http://tempo  │ │   http://mimir  │
│   :3100         │ │   :4317         │ │   :9009         │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │     Grafana     │
                    │ http://grafana  │
                    │   :3000         │
                    └─────────────────┘
```

### Detecção Automática

O sistema detecta automaticamente:

1. **Docker disponível?** → Inicia stack OTel
2. **Docker não disponível?** → Sistema funciona sem telemetria (sem erros)
3. **Stack já rodando?** → Não reinicia (evita duplicação)

```python
# mod_tisosdocfly/docker_detector.py
def auto_iniciar_otel():
    if not docker_disponivel():
        return False  # Sem Docker, sem OTel (sem erro)
    
    if otel_stack_rodando():
        return True  # Já está rodando
    
    # Inicia a stack
    sucesso, msg = iniciar_otel_stack()
    return sucesso
```

---

## Integração com a T! SOS DocFly

### Envio de Logs

```python
from mod_tisosdocfly.otel_integracao import get_tracer, criar_span

# Criar um trace
with criar_span("minha_operacao", {"tipo": "consulta"}) as span:
    # Lógica da operação...
    span.set_attribute("resultado", "sucesso")
```

### Envio de Métricas

```python
from mod_tisosdocfly.otel_integracao import criar_contador

# Criar um contador
requisicoes = criar_contador("tisosdocfly_requests_total", "Total de requisições")
requisicoes.add(1, {"rota": "/blog", "metodo": "GET"})
```

### Verificar Status

```python
from mod_tisosdocfly.docker_detector import print_otel_info

# Imprimir informações do OTel
print_otel_info()
```

---

## Troubleshooting

### Docker Não Disponível

**Sintoma:** Mensagem `[otel] Docker not available, skipping OTel stack`

**Solução:**
```bash
# Verificar se Docker está instalado
docker --version

# Verificar se Docker está rodando
docker info

# Iniciar Docker Desktop (Windows/Mac)
# Ou iniciar Docker Engine (Linux)
sudo systemctl start docker
```

### Portas em Uso

**Sintoma:** Erro `port is already allocated`

**Solução:**
```bash
# Verificar processos usando a porta
netstat -tulpn | grep :3000

# Matar processo na porta (substitua <PID>)
kill <PID>

# Ou usar porta diferente no compose.yml
```

### Containers Não Iniciam

**Sintoma:** `docker compose ps` mostra containers com erro

**Solução:**
```bash
# Ver logs de erro
docker compose logs grafana
docker compose logs loki
docker compose logs otel-collector

# Reiniciar containers
docker compose down
docker compose up -d
```

### Espaço em Disco

**Sintoma:** Erros de espaço em disco

**Solução:**
```bash
# Limpar containers parados
docker container prune

# Limpar images não utilizadas
docker image prune

# Limpar volumes não utilizados (atenção: perde dados)
docker volume prune

# Limpar tudo
docker system prune -a
```

### Logs Não Aparecem no Grafana

**Sintoma:** Grafana aberto mas sem dados

**Solução:**
1. Verifique se a T! SOS DocFly está rodando: `python main.py`
2. Verifique se o OTel Collector está recebendo dados: `curl http://localhost:8888/metrics`
3. Verifique se o Loki está funcionando: `curl http://localhost:3100/ready`
4. Verifique as fontes de dados no Grafana (Configuração → Fontes de dados)

---

## Segurança

### Credenciais Padrão

- **Grafana:** master / master (mesmo usuário da T! SOS DocFly)
- **Serviços internos:** Sem autenticação (acesso restrito à rede Docker)

### Recomendações para Produção

1. **Alterar credenciais do Grafana:**
   ```bash
   # Usar variáveis de ambiente
   export GF_SECURITY_ADMIN_USER=seu_usuario
   export GF_SECURITY_ADMIN_PASSWORD=sua_senha_segura
   ```

2. **Habilitar TLS:**
   ```yaml
   # No compose.yml, adicionar:
   environment:
     - GF_SERVER_PROTOCOL=https
     - GF_SERVER_CERT_FILE=/etc/ssl/certs/grafana.crt
     - GF_SERVER_CERT_KEY=/etc/ssl/private/grafana.key
   ```

3. **Restringir acesso:**
   - Portas internas (3100, 3200, 9009) não devem ser expostas
   - Para acesso remoto, usar VPN ou SSH tunnel
   - Configurar firewall para limitar acesso

4. **Variáveis de ambiente:**
   ```bash
   # Criar arquivo .env
   GF_SECURITY_ADMIN_USER=master
   GF_SECURITY_ADMIN_PASSWORD=master
   GF_USERS_ALLOW_SIGN_UP=false
   ```

### Segurança da Rede Docker

- Os serviços internos (Loki, Tempo, Mimir) só são acessíveis pela rede Docker
- O Grafana é o ponto de entrada único com autenticação
- Não exponha portas internas diretamente

---

## Estrutura de Arquivos

```
assets/docker/
├── compose.yml                          # Definição dos serviços
├── README.md                            # Este arquivo
├── start.sh                             # Script de inicialização rápida
└── config/
    ├── otel-collector-config.yml        # Configuração do OTel Collector
    ├── loki-config.yml                  # Configuração do Loki
    ├── tempo-config.yml                 # Configuração do Tempo
    ├── mimir-config.yml                 # Configuração do Mimir
    ├── grafana-dashboards/              # Dashboards customizados
    └── grafana-provisioning/
        ├── datasources/
        │   └── datasources.yml          # Fontes de dados automáticas
        └── dashboards/
            └── dashboards.yml           # Configuração de dashboards
```

---

## PostgreSQL opcional (backend duplo)

Além da stack de observabilidade (LGTM), o projeto suporta **PostgreSQL opcional** como backend de dados (SQLite é o padrão):

```bash
# Subir o container Postgres (banco `tisosdocfly`, usuário/senha `tisosdocfly`)
cd assets/docker/postgres && docker compose up -d
```

Depois, em `/configuracoes` → card **"Banco de dados — SQLite ou PostgreSQL"**, selecione **PostgreSQL**, confira o DSN e **REINICIE o servidor**. Todos os módulos passam a usar o banco `tisosdocfly` com **um SCHEMA por módulo** (`tisosdocfly`, `blog`, `usuarios`, `auditoria`, `editar_pdf`, `empenhos`, `solicita_impressao`) — isolamento equivalente ao modelo "um SQLite por módulo".

> ⚠️ Apenas desenvolvimento/staging — não exponha a porta 5432 em produção. Credenciais configuráveis via env `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`.

## Referências

- [Grafana OTel LGTM](https://grafana.com/docs/otel-lgtm/latest/)
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
- [Loki](https://grafana.com/docs/loki/latest/)
- [Tempo](https://grafana.com/docs/tempo/latest/)
- [Mimir](https://grafana.com/docs/mimir/latest/)
- [Docker Compose](https://docs.docker.com/compose/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)