from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

try:
    from opentelemetry import propagate, trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import Link, SpanKind, get_current_span
    from opentelemetry.trace.propagation import set_span_in_context

    _OTEL_AVAILABLE = True
except Exception:  # noqa: BLE001
    propagate = None
    trace = None
    Link = None
    SpanKind = None
    get_current_span = None
    set_span_in_context = None
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    _OTEL_AVAILABLE = False

try:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    _OTLP_HTTP_EXPORTER_AVAILABLE = True
except Exception:  # noqa: BLE001
    OTLPSpanExporter = None
    _OTLP_HTTP_EXPORTER_AVAILABLE = False


@dataclass(slots=True)
class _NoopSpan:
    attributes: dict[str, Any]

    def add_event(self, name: str, attributes: Mapping[str, Any] | None = None) -> None:
        _ = name
        _ = attributes

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def end(self) -> None:
        return


class ActorTracing:
    def __init__(
        self,
        *,
        service_name: str,
        tracer_provider: Any | None = None,
        resource_attributes: Mapping[str, Any] | None = None,
    ) -> None:
        self.service_name = service_name
        self._owned_provider = tracer_provider is None
        self._enabled = False
        self._provider = tracer_provider
        self._tracer = None
        if tracer_provider is None:
            tracer_provider = self._build_provider(service_name=service_name, resource_attributes=resource_attributes)
            self._provider = tracer_provider
        if _OTEL_AVAILABLE and tracer_provider is not None:
            self._tracer = tracer_provider.get_tracer("openagentic_sdk.actor")
            self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, Any] | None = None,
        parent_context: Any | None = None,
        kind: Any | None = None,
        links: Sequence[Any] | None = None,
    ) -> Any:
        if not self._enabled or self._tracer is None:
            return _NoopSpan(dict(_clean_attributes(attributes)))
        return self._tracer.start_span(
            name,
            context=parent_context,
            kind=kind or SpanKind.INTERNAL,
            attributes=dict(_clean_attributes(attributes)),
            links=list(links or ()),
        )

    def use_span(self, span: Any):
        if not self._enabled or trace is None or isinstance(span, _NoopSpan):
            return contextlib.nullcontext()
        return trace.use_span(span, end_on_exit=False)

    def end_span(self, span: Any) -> None:
        if span is None:
            return
        span.end()

    def add_event(self, span: Any, name: str, *, attributes: Mapping[str, Any] | None = None) -> None:
        if span is None:
            return
        span.add_event(name, attributes=dict(_clean_attributes(attributes)))

    def set_attributes(self, span: Any, attributes: Mapping[str, Any] | None = None) -> None:
        if span is None:
            return
        for key, value in _clean_attributes(attributes):
            span.set_attribute(key, value)

    def inject_current_context(self) -> dict[str, str]:
        if not self._enabled or propagate is None:
            return {}
        carrier: dict[str, str] = {}
        propagate.inject(carrier)
        return carrier

    def extract_context(self, carrier: Mapping[str, str] | None) -> Any | None:
        if not self._enabled or propagate is None or not carrier:
            return None
        return propagate.extract(carrier=dict(carrier))

    def link_from_carrier(self, carrier: Mapping[str, str] | None) -> Any | None:
        if not self._enabled or Link is None or get_current_span is None or not carrier:
            return None
        context = self.extract_context(carrier)
        if context is None:
            return None
        span = get_current_span(context)
        if span is None:
            return None
        get_span_context = getattr(span, "get_span_context", None)
        if not callable(get_span_context):
            return None
        span_context = get_span_context()
        if span_context is None or not getattr(span_context, "is_valid", False):
            return None
        return Link(span_context)

    def context_with_span(self, span: Any) -> Any | None:
        if not self._enabled or set_span_in_context is None or span is None or isinstance(span, _NoopSpan):
            return None
        return set_span_in_context(span)

    def shutdown(self) -> None:
        if self._owned_provider and self._provider is not None and hasattr(self._provider, "shutdown"):
            self._provider.shutdown()

    def _build_provider(
        self,
        *,
        service_name: str,
        resource_attributes: Mapping[str, Any] | None = None,
    ) -> Any | None:
        if not _OTEL_AVAILABLE:
            return None
        if not _OTLP_HTTP_EXPORTER_AVAILABLE:
            return None
        if os.environ.get("OA_DISABLE_ACTOR_TRACING", "").strip().lower() in {"1", "true", "yes"}:
            return None
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if not endpoint:
            return None
        resource_payload = {"service.name": os.environ.get("OTEL_SERVICE_NAME", service_name)}
        if resource_attributes:
            for key, value in resource_attributes.items():
                if value is not None:
                    resource_payload[str(key)] = value
        provider = TracerProvider(resource=Resource.create(resource_payload))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        return provider


def ensure_actor_tracing(options: Any, *, default_service_name: str = "openagentic-sdk") -> ActorTracing:
    runtime_state = getattr(options, "runtime_state", None)
    tracing = getattr(runtime_state, "actor_tracing", None)
    if isinstance(tracing, ActorTracing):
        return tracing
    tracing = ActorTracing(service_name=os.environ.get("OTEL_SERVICE_NAME", default_service_name))
    if runtime_state is not None:
        runtime_state.actor_tracing = tracing
    return tracing


def actor_execution_attributes(
    *,
    execution_id: str | None,
    actor_id: str | None,
    agent_name: str | None,
    dispatch_mode: str | None,
    transport_kind: str | None,
    session_id: str | None = None,
    parent_session_id: str | None = None,
    child_session_id: str | None = None,
    target_node: str | None = None,
) -> dict[str, Any]:
    return {
        "oa.execution.id": execution_id,
        "oa.actor.id": actor_id,
        "oa.agent.name": agent_name,
        "oa.dispatch.mode": dispatch_mode,
        "oa.transport.kind": transport_kind,
        "oa.session_id": session_id,
        "oa.parent_session_id": parent_session_id,
        "oa.child_session_id": child_session_id,
        "oa.target_node": target_node,
    }


def envelope_trace_attributes(envelope: Any) -> dict[str, Any]:
    return {
        "oa.execution.id": getattr(envelope, "execution_id", None),
        "oa.message.id": getattr(envelope, "message_id", None),
        "oa.mailbox": getattr(envelope, "mailbox", None),
        "oa.seq": getattr(envelope, "seq", None),
        "oa.actor.id": getattr(envelope, "sender_actor_id", None),
    }


def down_trace_attributes(down: Any) -> dict[str, Any]:
    return {
        "oa.execution.id": getattr(down, "execution_id", None),
        "oa.actor.id": getattr(down, "actor_id", None),
        "oa.reason.kind": getattr(down, "reason_kind", None),
        "oa.reason.detail": getattr(down, "reason_detail", None),
        "oa.dispatch.mode": getattr(down, "dispatch_mode", None),
        "oa.child_session_id": getattr(down, "child_session_id", None),
        "oa.target_node": getattr(down, "target_node", None),
    }


def supervisor_trace_attributes(*, action: str, policy: str, retry_count: int) -> dict[str, Any]:
    return {
        "oa.supervisor.action": action,
        "oa.supervisor.policy": policy,
        "oa.supervisor.retry_count": retry_count,
    }


def _clean_attributes(attributes: Mapping[str, Any] | None) -> list[tuple[str, Any]]:
    if not attributes:
        return []
    cleaned: list[tuple[str, Any]] = []
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (str, bool, int, float)):
            cleaned.append((str(key), value))
            continue
        cleaned.append((str(key), str(value)))
    return cleaned
