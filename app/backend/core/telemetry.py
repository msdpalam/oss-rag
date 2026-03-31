"""
OpenTelemetry setup — call configure_telemetry() once at app startup.

If OTEL_EXPORTER_OTLP_ENDPOINT is set, traces are exported to that endpoint
via gRPC (e.g. a local Jaeger all-in-one or an OTel Collector).
If the variable is unset the SDK is still initialised but uses a NoOp exporter,
so all tracer.start_as_current_span() calls are zero-cost no-ops in production
until an endpoint is configured.
"""

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_SERVICE_NAME = "oss-rag"
_tracer: trace.Tracer | None = None


def configure_telemetry() -> None:
    global _tracer

    resource = Resource.create({"service.name": _SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(_SERVICE_NAME)


def get_tracer() -> trace.Tracer:
    if _tracer is None:
        # Fallback: return a no-op tracer if configure_telemetry() was never called
        return trace.get_tracer(_SERVICE_NAME)
    return _tracer
