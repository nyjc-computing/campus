"""Audit event emission helpers for campus.audit.

Provides helper function and decorator for emitting audit events to the
traces table with easy enabling/disabling per route.
"""

import functools
import time
import typing

import flask

from campus.common import env
from campus.common import schema
from campus.common.utils import uid
import campus.model as model

# Standardize JsonObject representation in campus.audit
JsonObject = dict[str, typing.Any]


class FlaskRequestContext(typing.TypedDict):
    """A dict containing Flask request context used by campus.audit."""
    method: str
    path: str
    urlparams: JsonObject
    client_ip: str | None
    user_agent: str | None
    headers: JsonObject
    body: JsonObject


class FlaskResponseContext(typing.TypedDict):
    """A dict containing Flask response context inferred from viewfunc return."""
    status_code: int
    headers: JsonObject
    body: JsonObject


def _calculate_duration_ns(
        start_ns: int,
        units: typing.Literal["s", "ms", "us", "ns"] = "ns"
) -> float:
    """Calculate time elapsed in the specified units."""
    duration_ns = (time.perf_counter_ns() - start_ns)
    match units:
        case "s":
            return duration_ns / 1_000_000_000
        case "ms":
            return duration_ns / 1_000_000
        case "us":
            return duration_ns / 1_000
        case "ns":
            return duration_ns


def _extract_request_context(request: flask.Request) -> FlaskRequestContext:
    """Extract Flask request context into a dict.

    Returns:
        FlaskRequestContext containing client IP, user agent, headers,
        URL parameters, and request body parsed as JSON.

    Note:
        Request body extraction is graceful - returns empty dict if JSON
        parsing fails (e.g., for GET requests with no body).
    """
    context: FlaskRequestContext = {
        "method": request.method,
        "path": request.path,
        "urlparams": dict(request.args),
        "client_ip": request.remote_addr,
        "user_agent": request.user_agent.string,
        "headers": dict(request.headers),
        # JSON object is expected for body
        "body": request.get_json(force=False, silent=True) or {},
    }
    return context


def _extract_response_context(response: flask.Response) -> FlaskResponseContext:
    """Extract Flask response context from viewfunc return value.

    Args:
        result: Tuple of (response_dict, status_code) returned by view function

    Returns:
        FlaskResponseContext containing status code and response body
    """
    context: FlaskResponseContext = {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": response.get_json(force=False, silent=True) or {},
    }
    return context


def emit_from_flask(
        request: flask.Request | None,
        response: flask.Response,
        *,
        event_type: str,
        data: JsonObject,
        api_key_id: str | None,
        started_at: schema.DateTime,
        duration_ms: float,
) -> None:
    """Emit audit event from Flask request/response objects.

    Extracts request and response context from Flask objects and emits
    an audit event with full context. Only emits for 2XX and 3XX responses.

    Args:
        request: Flask request object (uses flask.request if None)
        response: Flask response object
        event_type: Event type (e.g., "audit.apikeys.new")
        data: Event metadata stored in tags field
        api_key_id: API key identifier (falls back to flask.g.api_key_id)
        started_at: When the operation started
        duration_ms: Operation duration in milliseconds
    """
    request_context = _extract_request_context(request or flask.request)
    response_context = _extract_response_context(response)

    # Only emit audit events for 2XX and 3XX responses
    if 200 <= response_context["status_code"] < 400:
        # Include event_type in metadata for easy querying
        event_metadata = {**data, "event_type": event_type}
        emit_audit_event(
            data=event_metadata,
            api_key_id=api_key_id or flask.g.api_key_id,
            parent_span_id=flask.g.get('span_id'),
            started_at=started_at,
            duration_ms=duration_ms,
            request_context=request_context,
            response_context=response_context,
        )


def emit_audit_event(
        *,
        data: JsonObject,
        api_key_id: str | None,
        parent_span_id: str | None = None,
        started_at: schema.DateTime,
        duration_ms: float,
        request_context: FlaskRequestContext,
        response_context: FlaskResponseContext,
) -> None:
    """Emit an audit event as a TraceSpan record.

    Creates and ingests a TraceSpan with audit event data. Event type
    should be included in the data dict for easy querying.

    Args:
        data: Event metadata stored in tags field (should include event_type)
        api_key_id: API key identifier
        parent_span_id: Parent span ID for linking to HTTP request span
        started_at: When the operation started
        duration_ms: Operation duration in milliseconds
        request_context: Flask request context (method, path, headers, body, etc.)
        response_context: Flask response context (status_code, headers, body)
    """
    # Early exit if disabled
    if not env.get_flag("AUDIT_EVENTS_ENABLED", False):
        return

    # Create audit span record
    audit_span = model.TraceSpan(
        trace_id=uid.generate_trace_id(),
        span_id=uid.generate_span_id(),
        parent_span_id=parent_span_id,
        method=request_context["method"],
        path=request_context["path"],
        query_params=request_context["urlparams"],
        request_headers=request_context["headers"],
        request_body=request_context["body"],
        status_code=response_context["status_code"],
        response_headers=response_context["headers"] or {},
        response_body=response_context["body"],
        started_at=started_at,
        duration_ms=duration_ms,
        api_key_id=api_key_id,  # main source ID in campus.audit
        client_id=None,  # not used in campus.audit
        user_id=None,  # not used in campus.audit
        client_ip=request_context["client_ip"] or "unknown",
        user_agent=request_context["user_agent"],
        error_message=None,
        tags=data  # Event metadata goes here
    )

    # Lazy-import resources to enable test monkey-patching
    from campus.audit.resources import traces as traces_resource
    # Ingest the audit event
    try:
        traces_resource.ingest([audit_span])
    except Exception:
        # Fail silently - don't break operations if audit logging fails
        pass


def audit_event(
        event_type: str,
) -> typing.Callable[[typing.Any], typing.Any]:
    """Decorator to emit audit events for route functions.

    Automatically captures request/response context including:
    - Request method, path, headers, body
    - Response status code, headers, body
    - Duration, API key ID, parent span ID
    - Client IP and user agent

    Only emits events for 2XX and 3XX responses. Error responses are
    captured from error handler output via flask.after_this_request.

    Args:
        event_type: Event type (e.g., "audit.apikeys.new")

    Example:
        @bp.post("/")
        @audit_event("audit.apikeys.new")
        def create_api_key(**kwargs):
            # ... route logic ...
            return {"id": key_id, "name": name}, 201

    Returns:
        Decorator function that preserves the wrapped function's signature
    """
    def decorator(
            func: typing.Any
    ) -> typing.Any:
        # If audit disabled, return original function unchanged
        if not env.get_flag("AUDIT_EVENTS_ENABLED", False):
            return func

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> flask.Response:
            # Capture request timing
            event_emitted = False
            started_at = schema.DateTime.utcnow()
            request_start_ns = time.perf_counter_ns()

            def emit_after_response(response: flask.Response) -> flask.Response:
                """Emit audit event after response is fully processed.

                This is called by Flask after the view function and any
                error handlers have completed, giving us access to the
                final response that will be sent to the client.

                Captures both successful responses and error responses.
                """
                nonlocal event_emitted
                if event_emitted:
                    return response

                duration_ms = _calculate_duration_ns(request_start_ns, units="ms")
                status_code = response.status_code

                # Only emit audit events for 2XX and 3XX responses
                if 200 <= status_code < 400:
                    event_data = {
                        "endpoint": flask.request.endpoint,
                        "method": flask.request.method,
                        "path": flask.request.path,
                        "status_code": status_code,
                    }

                    emit_from_flask(
                        flask.request,
                        response,
                        event_type=event_type,
                        data=event_data,
                        api_key_id=flask.g.api_key_id,
                        started_at=started_at,
                        duration_ms=duration_ms,
                    )

                event_emitted = True
                return response

            # Register callback to run after request completes
            # This captures final response from view func OR error handlers
            flask.after_this_request(emit_after_response)

            # Call the original route function and convert to Response
            result = func(*args, **kwargs)
            response_dict, status_code = result
            return flask.make_response(response_dict, status_code)

        return wrapper
    return decorator
