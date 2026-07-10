"""
Tracing OTLP OPCIONAL por instancia (Fase 3.4).

Se activa SOLO si la env var OTEL_EXPORTER_OTLP_ENDPOINT está seteada. Si no, es un no-op
total (cero costo, cero dependencia en runtime local/tests). Aprovecha
opentelemetry-instrumentation-fastapi, ya presente en requirements.

Uso: setear OTEL_EXPORTER_OTLP_ENDPOINT (ej. "http://otel-collector:4317") en el deploy del
cliente que quiera exportar trazas. El service.name toma el nombre del negocio del perfil (si
está disponible) para distinguir instancias en el backend de trazas.
"""
import os

from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)


def setup_otel(app, service_name: str = "hotel-agent") -> bool:
    """Instrumenta FastAPI con OTLP si hay endpoint configurado. Devuelve True si se activó.

    No-op y seguro si el endpoint no está seteado o si algo falla (nunca rompe el arranque).
    """
    endpoint = (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    if not endpoint:
        return False  # no-op: sin endpoint, no se instrumenta nada
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        logger.info("OTEL tracing habilitado", endpoint=endpoint, service=service_name)
        return True
    except Exception as e:  # noqa: BLE001 — la observabilidad nunca debe tumbar el arranque
        logger.warning("No se pudo activar OTEL (se sigue sin tracing)", error=str(e))
        return False
