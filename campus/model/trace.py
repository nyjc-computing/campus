"""campus.model.trace

Trace span model for Campus audit API.

This model represents a single span in a distributed trace,
capturing request-response data for observability.
"""

from dataclasses import dataclass, field

from campus.common import schema

from .base import InternalModel


@dataclass(eq=False, kw_only=True)
class TraceSpan(InternalModel):
    """A single span in a distributed trace.

    Captures HTTP request-response data for observability and debugging.
    Uses OpenTelemetry-compatible trace/span ID formats.

    Note: span_id serves as the unique identifier (no separate 'id' field),
    following OpenTelemetry conventions rather than Campus schema conventions.

    Attributes:
        trace_id: 32-char hex string grouping related spans
        span_id: 16-char hex string identifying this span (unique identifier)
        parent_span_id: 16-char hex string of parent span, null for roots
        method: HTTP method (GET, POST, etc.)
        path: Request path (e.g. /api/v1/students)
        query_params: Query string parameters as dict
        request_headers: Request headers (Authorization stripped)
        request_body: Request body JSON (if applicable)
        status_code: HTTP response status code
        response_headers: Response headers
        response_body: Response body JSON (truncated to 64KB)
        started_at: Span start timestamp
        duration_ms: Span duration in milliseconds
        api_key_id: API key used for the request
        client_id: OAuth client identifier (null until auth succeeds)
        user_id: User identifier (null until auth succeeds)
        client_ip: Client IP address
        user_agent: User-Agent header value
        error_message: Error details for failed requests
        tags: Arbitrary key-value metadata
    """

    # Trace identification (OpenTelemetry-compatible)
    trace_id: str  # 32-char hex
    span_id: str  # 16-char hex (primary key)
    parent_span_id: str | None = None

    # Request data
    method: str  # HTTP method
    path: str  # Request path
    query_params: dict[str, object] = field(default_factory=dict)
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: dict[str, object] | None = None

    # Response data
    status_code: int | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: dict[str, object] | None = None

    # Timing
    started_at: schema.DateTime = field(default_factory=schema.DateTime.utcnow)
    duration_ms: float  # milliseconds

    # Identity (nullable - populated after auth)
    api_key_id: str | None = None
    client_id: str | None = None
    user_id: str | None = None

    # Client info
    client_ip: str  # INET type
    user_agent: str | None = None

    # Error info
    error_message: str | None = None

    # Metadata
    tags: dict[str, object] = field(default_factory=dict)
