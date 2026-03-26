import os
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from shared.database.session import engine
from typing import Any

logger = logging.getLogger("Tracing")

def init_tracing(service_name: str) -> None:
    """
    Initializes OpenTelemetry tracing with OTLP exporter to Jaeger/Collector.
    """
    try:
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        
        # Jaeger OTLP gRPC endpoint
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        
        logger.info(f"Tracing initialized for {service_name} -> {otlp_endpoint}")
    except Exception as e:
        logger.error(f"Failed to initialize tracing: {e}")

def instrument_app(app: Any) -> None:
    """
    Instruments FastAPI and SQLAlchemy for automatic span generation.
    """
    try:
        from typing import Any
        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument(engine=engine)
        logger.info("App instrumentation complete (FastAPI + SQLAlchemy)")
    except Exception as e:
        logger.error(f"Instrumentation failed: {e}")

def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
