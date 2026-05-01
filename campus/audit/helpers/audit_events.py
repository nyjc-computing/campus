"""Audit event emission helpers for campus.audit.

Provides helper function and decorator for emitting audit events to the
traces table with easy enabling/disabling per route.
"""

import functools
import typing

import flask

import campus.flask_campus as flask_campus
from campus.common import env
from campus.common import schema
from campus.common.utils import uid
from campus.common.errors import api_errors

# Feature flag: can be set via environment variable
# Default: enabled for all routes unless explicitly disabled
AUDIT_EVENTS_ENABLED = env.get("AUDIT_EVENTS_ENABLED", "true").lower() == "true"


def emit_audit_event(
    event_type: str,
    data: dict,
    api_key_id: str | None = None,
    client_ip: str | None = None,
    method: str = "AUDIT",
) -> None:
    """Emit an audit event directly to the traces table.

    This function writes audit events as TraceSpan records with special
    fields to distinguish them from regular HTTP request traces.

    Args:
        event_type: Event type (e.g., "campus.apikeys.new")
        data: Event metadata (will be stored in tags field)
        api_key_id: API key identifier (optional, pulled from flask.g if not provided)
        client_ip: Client IP (optional, pulled from request if not provided)
        method: HTTP method for the span (default: "AUDIT" to distinguish from HTTP requests)
    """
    # Early exit if disabled
    if not AUDIT_EVENTS_ENABLED:
        return

    from campus.audit.resources.traces import traces_storage
    import campus.model as model

    # Get data from Flask context if not provided
    if api_key_id is None:
        api_key_id = flask.g.get('api_key_id')
    if client_ip is None:
        client_ip = flask.request.remote_addr

    # Create audit span record
    audit_span = model.TraceSpan(
        trace_id=uid.generate_trace_id(),
        span_id=uid.generate_span_id(),
        parent_span_id=None,
        method=method,
        path=event_type,
        query_params={},
        request_headers={},
        request_body=None,
        status_code=None,
        response_headers={},
        response_body=None,
        started_at=schema.DateTime.utcnow(),
        duration_ms=0.0,
        api_key_id=api_key_id,
        client_id=None,
        user_id=None,
        client_ip=client_ip or "unknown",
        user_agent=None,
        error_message=None,
        tags=data  # Event metadata goes here
    )

    # Ingest the audit event
    try:
        traces_storage.insert_one(audit_span.to_storage())
    except Exception:
        # Fail silently - don't break operations if audit logging fails
        pass


def audit_event(
    event_type: str,
    data_func: typing.Callable[[typing.Any, dict[str, typing.Any]], dict] | None = None,
) -> typing.Callable:
    """Decorator to emit audit events for route functions.

    Enables audit logging for specific routes with automatic data capture.
    Can be applied to any route function to enable/disable audit tracking.

    Args:
        event_type: Event type (e.g., "campus.apikeys.new")
        data_func: Optional function to extract event data from route result
                  Takes (result, response_dict) and returns event data dict.
                  If None, only basic metadata is captured.

    Example:
        @bp.post("/")
        @audit_event("campus.apikeys.new")
        def create_api_key(**kwargs):
            # ... route logic ...
            return {"id": key_id, "name": name}, 201

        # With custom data extraction:
        @audit_event("campus.apikeys.new", lambda r, d: {"api_key_id": r["id"]})
        def create_api_key(**kwargs):
            # ... route logic ...
            return {"id": key_id, "name": name}, 201

    Returns:
        Decorator function
    """
    def decorator(func: typing.Callable) -> typing.Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> flask_campus.JsonResponse:
            # Call the original route function
            result = func(*args, **kwargs)

            # Extract response data if result is a tuple (response, status_code)
            response_dict = {}
            if isinstance(result, tuple) and len(result) >= 1:
                response_dict = result[0] if isinstance(result[0], dict) else {}
            elif isinstance(result, dict):
                response_dict = result

            # Build event data
            event_data = {}
            if data_func is not None:
                try:
                    event_data = data_func(result, response_dict)
                except Exception:
                    # If data_func fails, log with basic data only
                    pass

            # Add request metadata
            event_data.update({
                "endpoint": flask.request.endpoint,
                "method": flask.request.method,
                "path": flask.request.path,
            })

            # Emit the audit event
            emit_audit_event(
                event_type=event_type,
                data=event_data
            )

            return result

        return wrapper

    # Only apply the decorator if audit is enabled
    if AUDIT_EVENTS_ENABLED:
        return decorator
    else:
        # If audit disabled, return original function unchanged
        return data_func


def disable_audit_for_route(f: typing.Callable) -> typing.Callable:
    """Decorator to explicitly disable audit logging for a specific route.

    Use this to opt-out specific routes from audit logging even when
    AUDIT_EVENTS_ENABLED is true.

    Example:
        @bp.get("/health")
        @disable_audit_for_route
        def health_check():
            return {"status": "ok"}
    """
    # Mark function as audit-disabled
    f._audit_disabled = True  # type: ignore[attr-defined]
    return f
