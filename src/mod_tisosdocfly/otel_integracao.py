"""OpenTelemetry integration for T! SOS DocFly Modular.

This module provides integration with OpenTelemetry for sending logs, traces,
and metrics to the OTel LGTM stack.

Modulo de integracao OpenTelemetry para a T! SOS DocFly Modular.
Envia logs, traces e metricas para a stack OTel LGTM.

Author: Administrador do sistema
Date: 2026-09-04
"""
import os
import sys
import platform
from typing import Optional, Any
from contextlib import contextmanager

# =============================================================================
# Conditional Imports
# =============================================================================

try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.trace import StatusCode
    from opentelemetry.semconv.resource import ResourceAttributes
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

from mod_tisosdocfly.docker_detector import docker_disponivel, otel_stack_rodando

# =============================================================================
# Configuration
# =============================================================================

OTEL_ENDPOINT = os.getenv("OTEL_ENDPOINT", "localhost:4317")
SERVICE_NAME_VALUE = os.getenv("OTEL_SERVICE_NAME", "tisosdocfly-modular")
SERVICE_VERSION = os.getenv("OTEL_SERVICE_VERSION", "1.0.260908")

# Chaves de configuração (tb_config) — permitem apontar para stack remota
# sem variável de ambiente (env OTEL_ENDPOINT continua com prioridade).
CFG_OTEL_ATIVO = "otel_ativo"
CFG_OTEL_ENDPOINT = "otel_endpoint"
CFG_OTEL_AUTO_START = "otel_auto_start_stack"

DEFAULT_OTEL_ENDPOINT = "localhost:4317"


def _obter_config(chave, padrao):
    """Reads tb_config with fallback (lowest layer — no circular imports).

    Lê `tb_config` com fallback para `padrao` (nunca quebra o boot)."""
    try:
        from mod_tisosdocfly.bd_conexao import get_config
        return get_config(chave, padrao)
    except Exception:
        return padrao


def obter_endpoint():
    """Resolves the OTLP endpoint (env OTEL_ENDPOINT wins over tb_config).

    Resolve o endpoint OTLP: env tem prioridade, depois `tb_config`
    (`otel_endpoint`), depois o padrão local."""
    try:
        env = (os.getenv("OTEL_ENDPOINT") or "").strip()
        if env:
            return env
        return (_obter_config(CFG_OTEL_ENDPOINT, DEFAULT_OTEL_ENDPOINT)
                or DEFAULT_OTEL_ENDPOINT).strip() or DEFAULT_OTEL_ENDPOINT
    except Exception:
        return DEFAULT_OTEL_ENDPOINT

# =============================================================================
# Global State
# =============================================================================

_tracer_provider: Optional[Any] = None
_meter_provider: Optional[Any] = None
_logger_provider: Optional[Any] = None
_handler_log_otel: Optional[Any] = None
_initialized = False


# =============================================================================
# Initialization
# =============================================================================

def inicializar_otel(auto_stack: bool = True) -> bool:
    """Initialize OpenTelemetry SDK.

    Inicializa o SDK do OpenTelemetry. Com `auto_stack=False` (stack
    remota/dedicada) pula as checagens de Docker e o `compose up` local,
    conectando direto no endpoint. Retorna True se inicializado.
    """
    global _initialized, _tracer_provider, _meter_provider, _logger_provider

    if _initialized:
        return True

    if not OTEL_AVAILABLE:
        print("[otel] OpenTelemetry SDK not installed. Install with:")
        print("  pip install opentelemetry-sdk opentelemetry-exporter-otlp")
        return False

    if auto_stack:
        if not docker_disponivel():
            print("[otel] Docker not available. Skipping OTel initialization.")
            return False

        if not otel_stack_rodando():
            print("[otel] OTel LGTM stack not running. Starting...")
            from mod_tisosdocfly.docker_detector import iniciar_otel_stack
            success, msg = iniciar_otel_stack()
            if not success:
                print(f"[otel] Failed to start OTel stack: {msg}")
                return False

    endpoint = obter_endpoint()
    try:
        # Create resource
        resource = Resource.create({
            SERVICE_NAME: SERVICE_NAME_VALUE,
            ResourceAttributes.SERVICE_VERSION: SERVICE_VERSION,
            ResourceAttributes.SERVICE_NAMESPACE: "tisosdocfly",
            ResourceAttributes.DEPLOYMENT_ENVIRONMENT: "production",
            ResourceAttributes.HOST_NAME: platform.node(),
            ResourceAttributes.OS_TYPE: platform.system().lower(),
        })
        
        # Initialize Tracer Provider
        _tracer_provider = TracerProvider(resource=resource)
        _tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=f"{endpoint}", insecure=True)
            )
        )
        trace.set_tracer_provider(_tracer_provider)
        
        # Initialize Meter Provider
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=f"{endpoint}", insecure=True),
            export_interval_millis=30000
        )
        _meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[reader]
        )
        metrics.set_meter_provider(_meter_provider)
        
        # Initialize Logger Provider
        _logger_provider = LoggerProvider(resource=resource)
        _logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(endpoint=f"{endpoint}", insecure=True)
            )
        )
        
        # Add OTel handler to Python logging
        import logging
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=_logger_provider)
        logging.getLogger().addHandler(handler)
        _handler_log_otel = handler

        _initialized = True
        print(f"[otel] OpenTelemetry initialized (endpoint={endpoint})")
        return True
        
    except Exception as e:
        print(f"[otel] Failed to initialize: {e}")
        return False


def finalizar_otel():
    """Shutdown OpenTelemetry SDK.

    Finaliza o SDK do OpenTelemetry.
    """
    global _tracer_provider, _meter_provider, _logger_provider, _initialized
    
    if not _initialized:
        return
    
    try:
        if _tracer_provider:
            _tracer_provider.shutdown()
        if _meter_provider:
            _meter_provider.shutdown()
        if _logger_provider:
            _logger_provider.shutdown()
        
        _initialized = False
        print("[otel] OpenTelemetry shutdown complete")
    except Exception as e:
        print(f"[otel] Error during shutdown: {e}")


# =============================================================================
# Tracing
# =============================================================================

def get_tracer(name: str = __name__):
    """Get a tracer instance.

    Retorna uma instancia de tracer.
    """
    if not _initialized:
        inicializar_otel()
    return trace.get_tracer(name)


@contextmanager
def criar_span(nome: str, atributos: Optional[dict] = None):
    """Create a span with context manager.

    Cria um span com context manager.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(nome) as span:
        if atributos:
            for key, value in atributos.items():
                span.set_attribute(key, str(value))
        try:
            yield span
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.record_exception(e)
            raise


def registrar_erro(span, erro: Exception, atributos: Optional[dict] = None):
    """Register an error in a span.

    Registra um erro em um span.
    """
    span.set_status(StatusCode.ERROR, str(erro))
    span.record_exception(erro)
    if atributos:
        for key, value in atributos.items():
            span.set_attribute(f"error.{key}", str(value))


# =============================================================================
# Metrics
# =============================================================================

def get_meter(name: str = __name__):
    """Get a meter instance.

    Retorna uma instancia de meter.
    """
    if not _initialized:
        inicializar_otel()
    return metrics.get_meter(name)


def criar_contador(nome: str, descricao: str = "", unidade: str = "1"):
    """Create a counter metric.

    Cria uma metrica counter.
    """
    meter = get_meter()
    return meter.create_counter(
        name=nome,
        description=descricao,
        unit=unidade
    )


def criar_histograma(nome: str, descricao: str = "", unidade: str = "1"):
    """Create a histogram metric.

    Cria uma metrica histogram.
    """
    meter = get_meter()
    return meter.create_histogram(
        name=nome,
        description=descricao,
        unit=unidade
    )


def criar_gauge(nome: str, descricao: str = "", unidade: str = "1"):
    """Create a gauge metric.

    Cria uma metrica gauge.
    """
    meter = get_meter()
    return meter.create_observable_gauge(
        name=nome,
        description=descricao,
        unit=unidade,
        callbacks=[lambda: 0]  # Placeholder
    )


# =============================================================================
# Logging Integration
# =============================================================================

def configurar_log_otel():
    """Configure OTel logging integration.

    Configura a integracao de logging com OTel.
    """
    if not _initialized:
        inicializar_otel()

    import logging

    # Create a logger
    logger = logging.getLogger("tisosdocfly")

    # Add OTel handler if not already present
    if _logger_provider and not any(isinstance(h, LoggingHandler) for h in logger.handlers):
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=_logger_provider)
        logger.addHandler(handler)

    return logger


def obter_handler_log() -> Optional[Any]:
    """Return the OTel LoggingHandler (to register as a loguru sink).

    Retorna o handler OTel para ser usado como sink do loguru.
    """
    return _handler_log_otel


# =============================================================================
# Convenience Functions
# =============================================================================

def obter_info_otel() -> dict:
    """Get OTel status info.

    Retorna informacoes de status do OTel.
    """
    return {
        "initialized": _initialized,
        "available": OTEL_AVAILABLE,
        "docker": docker_disponivel(),
        "stack_running": otel_stack_rodando(),
        "endpoint": obter_endpoint(),
        "service_name": SERVICE_NAME_VALUE
    }


if __name__ == "__main__":
    print("=== OpenTelemetry Info ===")
    info = obter_info_otel()
    for key, value in info.items():
        print(f"{key}: {value}")
    print("=========================")


# ---------------------------------------------------------------------------
# Login observability hook (set by mod_tisosdocfly.instrumentacao_app)
# ---------------------------------------------------------------------------

def registrar_login_observabilidade(usuario: str, sucesso: bool):
    """Placeholder hook para metricas de login via OTel.

    Sobrescrita dinamicamente por instrumentacao_app.instrumentar_aplicacao
    quando o OTel esta ativo. Sem instrumentacao, e um no-op.
    """
    return None