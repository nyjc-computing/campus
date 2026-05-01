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
import campus.model as model


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
    if not env.get_flag("AUDIT_EVENTS_ENABLED", False):
        return

    # Lazy-import resources to enable test monkey-patching
    from campus.audit.resources import traces as traces_resource

    # Get data from Flask context if not provided
    api_key_id = api_key_id or flask.g.get('api_key_id')
    client_ip = client_ip or flask.request.remote_addr

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
        traces_resource.ingest([audit_span])
    except Exception:
        # Fail silently - don't break operations if audit logging fails
        pass


def audit_event(
        event_type: str,
        data_func: typing.Callable[..., dict[str, typing.Any]] | None = None,
) -> flask_campus.ViewFunctionDecorator:
    """Decorator to emit audit events for route functions.

    Enables audit logging for specific routes with automatic data capture.
    Can be applied to any route function to enable/disable audit tracking.

    Args:
        event_type: Event type (e.g., "campus.apikeys.new")
        data_func: Optional function to extract event data from route response.
                  Takes response_dict and returns event data dict.
                  If None, only basic metadata is captured.

    Example:
        @bp.post("/")
        @audit_event("campus.apikeys.new")
        def create_api_key(**kwargs):
            # ... route logic ...
            return {"id": key_id, "name": name}, 201

        # With custom data extraction:
        @audit_event("campus.apikeys.new", lambda resp: {"api_key_id": resp["id"]})
        def create_api_key(**kwargs):
            # ... route logic ...
            return {"id": key_id, "name": name}, 201

    Returns:
        Decorator function
    """
    def decorator(
            func: flask_campus.JsonViewFunction
    ) -> flask_campus.JsonViewFunction:
        # If audit disabled, return original function unchanged
        if not env.get_flag("AUDIT_EVENTS_ENABLED", False):
            return func

        # Only apply the decorator if audit is enabled
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> flask_campus.JsonResponse:
            # Call the original route function
            result = func(*args, **kwargs)

            # Extract response data
            response_dict, status_code = result

            # TODO: Validate status_code before building event data
            # (e.g., only emit audit events for 2XX responses)

            # Build event data
            event_data = {}
            if data_func is not None:
                try:
                    event_data = data_func(response_dict)
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
    return decorator
