"""campus.audit.middleware.tracing

Tracing middleware implementation for capturing HTTP request-response spans.
"""

import concurrent.futures
import copy
import json
import logging
import time
import typing

import flask

from campus.audit.client import AuditClient
from campus.common import schema
from campus.common.utils import uid

logger = logging.getLogger(__name__)

# Thread pool for async ingestion (avoid blocking requests)
_ingestion_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="audit_ingest"
)

# Client singleton (lazy initialized)
_audit_client: AuditClient | None = None


def _get_audit_client() -> AuditClient:
    """Get or create the audit client singleton.

    Returns:
        AuditClient instance for sending spans to audit service.
    """
    global _audit_client
    if _audit_client is None:
        _audit_client = AuditClient()
    return _audit_client


def start_span() -> None:
    """Start a root span for the incoming request.

    - Generates or reuses trace_id from X-Request-ID header
    - Generates span_id for this request
    - Stores timing data in flask.g

    Stores in flask.g:
        - trace_id: 32-char hex trace identifier
        - span_id: 16-char hex span identifier
        - trace_start: timestamp for duration calculation
    """
    # Get or generate trace_id from X-Request-ID header
    trace_id = flask.request.headers.get("X-Request-ID") or uid.generate_trace_id()

    # Generate span_id for this request
    span_id = uid.generate_span_id()

    # Store in flask.g for use in after_request
    flask.g.trace_id = trace_id
    flask.g.span_id = span_id
    flask.g.trace_start = time.perf_counter()


def end_span(response: flask.Response) -> flask.Response:
    """Complete the span and ingest to audit service.

    - Builds TraceSpan from flask.request, flask.g, and response
    - Ingests asynchronously to avoid blocking
    - Echoes trace_id in response headers

    Args:
        response: The Flask response object

    Returns:
        Response with X-Request-ID header added
    """
    # Get trace data from flask.g (set by start_span)
    trace_id = getattr(flask.g, "trace_id", None)
    span_id = getattr(flask.g, "span_id", None)
    trace_start = getattr(flask.g, "trace_start", None)

    if not all([trace_id, span_id, trace_start]):
        # Tracing wasn't started properly, skip ingestion
        return response

    # Calculate duration
    duration_ms = (time.perf_counter() - trace_start) * 1000

    # Build span from context
    span = build_span_from_context(trace_id, span_id, response, duration_ms)

    # Ingest asynchronously (don't block the response)
    _ingest_span_async(span)

    # Echo trace_id in response header
    response.headers["X-Request-ID"] = trace_id

    return response


def build_span_from_context(
    trace_id: str,
    span_id: str,
    response: flask.Response,
    duration_ms: float,
) -> dict:
    """Build a span dict from request/response context.

    Args:
        trace_id: The trace identifier
        span_id: The span identifier
        response: The Flask response object
        duration_ms: Request duration in milliseconds

    Returns:
        Dictionary representation of the span for ingestion.
    """
    request = flask.request

    # Extract headers (strip Authorization)
    headers = dict(request.headers)
    headers.pop("Authorization", None)
    headers.pop("authorization", None)  # Case-insensitive

    # Get request body (only for supported content types)
    request_body = _extract_request_body(request)

    # Get response body (truncated to 64KB)
    response_body = _extract_response_body(response)

    # Build span dict matching TraceSpan schema
    span = {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": None,  # Root spans have no parent
        "timestamp": time.time_ns() // 1_000_000,  # milliseconds since epoch
        "duration_ms": round(duration_ms, 3),
        "name": f"{request.method} {request.path}",
        "kind": "SERVER",  # This middleware handles server-side requests
        "status_code": response.status_code,
        "http_method": request.method,
        "url": request.url,
        "path": request.path,
        "query_params": dict(request.args),
        "request_headers": headers,
        "request_body": request_body,
        "response_headers": dict(response.headers),
        "response_body": response_body,
        # Optional: populated by auth middleware if available
        "client_id": getattr(flask.g, "client_id", None),
        "user_id": getattr(flask.g, "user_id", None),
    }

    return span


def _extract_request_body(request: flask.Request) -> dict | str | None:
    """Extract request body safely.

    Only extracts for supported content types (JSON, form data).
    Returns None for unsupported types (files, binary, etc).

    Args:
        request: The Flask request object.

    Returns:
        Request body as dict, str, or None.
    """
    # Don't extract body for file uploads or unsupported content types
    if request.files:
        return None
    if request.content_length and request.content_length > 1_000_000:  # 1MB
        return None

    content_type = request.content_type or ""

    if "application/json" in content_type:
        try:
            return request.json
        except Exception:
            return None
    elif "application/x-www-form-urlencoded" in content_type:
        return dict(request.form)
    elif "text/" in content_type:
        try:
            return request.data.decode("utf-8")
        except Exception:
            return None

    return None


def _extract_response_body(response: flask.Response) -> dict | str | None:
    """Extract response body with 64KB truncation.

    Args:
        response: The Flask response object.

    Returns:
        Response body truncated to 64KB, or None if not applicable.
    """
    # Don't try to extract from streaming responses
    if response.is_streamed:
        return None

    # Don't extract if no response data
    if not response.response:
        return None

    try:
        # Get response data
        if isinstance(response.response, list):
            data = b"".join(response.response)
        elif isinstance(response.response, str):
            data = response.response.encode("utf-8")
        else:
            data = response.response

        # Decode if possible
        if isinstance(data, bytes):
            try:
                data = data.decode("utf-8")
            except UnicodeDecodeError:
                return "<binary data>"

        # Truncate to 64KB
        max_size = 64 * 1024
        if len(data) > max_size:
            data = data[:max_size]

        # Try to parse as JSON for structured logging
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return data

        return data
    except Exception:
        return None


def _ingest_span_async(span: dict) -> None:
    """Ingest span asynchronously using thread pool.

    Args:
        span: Span data to ingest.
    """
    def _do_ingest():
        try:
            client = _get_audit_client()
            client.traces.new(span)
        except Exception as e:
            # Don't let tracing errors break the application
            logger.warning(f"Failed to ingest trace span: {e}")

    _ingestion_executor.submit(_do_ingest)


def ingest_span(span: dict) -> None:
    """Send span to audit service via HTTP.

    This is a synchronous wrapper for backward compatibility.
    The actual ingestion happens asynchronously to avoid blocking.

    Args:
        span: Span data dictionary to ingest
    """
    _ingest_span_async(span)
