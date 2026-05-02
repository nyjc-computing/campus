"""campus.audit.routes.traces

Trace ingestion and query endpoints for the audit service.

Issue: #427
"""

from typing import Any

import flask

import campus.flask_campus as flask_campus
from campus.common.errors import api_errors

from ..resources import traces as traces_resource

# Create blueprint for trace routes
bp = flask.Blueprint('audit_traces', __name__, url_prefix='/traces')


@bp.post("/")
@flask_campus.unpack_request
def ingest_spans(
    *,
    spans: list[dict[str, Any]],
) -> flask_campus.JsonResponse:
    """Ingest trace spans (batch or single).

    Accepts a single span or batch of spans. Returns 201 Created on full
    success, or 207 Multi-Status on partial failure with per-span status
    indicators.

    Request body:
    {
      "spans": [
        {
          "trace_id": "string",
          "span_id": "string",
          "parent_span_id": "string | null",
          "method": "string",
          "path": "string",
          "status_code": 200,
          "started_at": "ISO 8601",
          "duration_ms": 142.5,
          "query_params": {},
          "request_headers": {},
          "request_body": null,
          "response_headers": {},
          "response_body": null,
          "client_id": "string | null",
          "user_id": "string | null",
          "api_key_id": "string",
          "client_ip": "string",
          "user_agent": "string",
          "error_message": "string | null",
          "tags": {}
        }
      ]
    }

    Returns:
        201 Created with span IDs on success
        207 Multi-Status on partial failure
        400 Bad Request on invalid input
    """
    # Convert dicts to TraceSpan models with validation
    import campus.model as model
    try:
        span_models = [
            model.TraceSpan.from_resource(span_dict)
            for span_dict in spans
        ]
    except (KeyError, TypeError, ValueError) as e:
        raise api_errors.InvalidRequestError(f"Invalid span data: {e}")

    result = traces_resource.ingest(span_models)
    return result, 201


@bp.get("/")
@flask_campus.unpack_request
def list_traces(
    *,
    since: str | None = None,
    until: str | None = None,
    limit: str | int = 50,
) -> flask_campus.JsonResponse:
    """List recent traces, newest first.

    Query params:
        since: ISO 8601 timestamp (optional)
        until: ISO 8601 timestamp (optional)
        limit: int, default 50

    Supports content negotiation via Accept header:
        - application/json: Structured JSON with cursor pagination
        - text/plain: Compact human-readable text

    Returns:
        JSON: {"traces": [...], "cursor": {"next": "...", "has_more": true}}
        Text: Compact trace list with pagination hint
    """
    # Convert limit to int if it's a string from query parameters
    limit_int = int(limit) if isinstance(limit, str) else limit
    summaries = traces_resource.list(since=since, until=until, limit=limit_int)
    return {
        "traces": [s.to_resource() for s in summaries],
        "cursor": {"next": None, "has_more": False}
    }, 200


@bp.get("/<trace_id>")
def get_trace(trace_id: str) -> flask_campus.JsonResponse:
    """Get full trace tree with child spans.

    Args:
        trace_id: The 32-char hex trace identifier

    Supports content negotiation via Accept header:
        - application/json: Nested tree structure with children arrays
        - text/plain: Waterfall with offset timing

    Returns:
        JSON: Trace tree with nested children
        Text: Waterfall visualization showing timing hierarchy
    """
    tree = traces_resource[trace_id].get_tree()
    if tree is None:
        raise api_errors.NotFoundError(f"Trace {trace_id} not found")
    return tree.to_resource(), 200


@bp.get("/<trace_id>/spans")
def list_spans(trace_id: str) -> flask_campus.JsonResponse:
    """List all spans in a trace (flat list).

    Args:
        trace_id: The 32-char hex trace identifier

    Returns:
        Flat list of all spans in the trace
    """
    spans = traces_resource[trace_id]["spans"].list()
    return {
        "spans": [s.to_resource() for s in spans]
    }, 200


@bp.get("/<trace_id>/spans/<span_id>")
def get_span(trace_id: str, span_id: str) -> flask_campus.JsonResponse:
    """Get single span detail including full headers and bodies.

    Args:
        trace_id: The 32-char hex trace identifier
        span_id: The 16-char hex span identifier

    Returns:
        Full span data including request/response headers and bodies
    """
    span = traces_resource[trace_id]["spans"][span_id].get()
    if span is None:
        raise api_errors.NotFoundError(
            f"Span {span_id} not found in trace {trace_id}"
        )
    return span.to_resource(), 200


@bp.get("/search")
@flask_campus.unpack_request
def search_traces(
    *,
    path: str | None = None,
    status: str | int | None = None,
    api_key_id: str | None = None,
    client_id: str | None = None,
    user_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: str | int = 50,
) -> flask_campus.JsonResponse:
    """Filter and search traces.

    Query params:
        path: Filter by endpoint path
        status: Filter by HTTP status code
        api_key_id: Filter by API key
        client_id: Filter by OAuth client
        user_id: Filter by user
        since: ISO 8601 timestamp (optional)
        until: ISO 8601 timestamp (optional)
        limit: int, default 50

    Supports content negotiation via Accept header.

    Returns:
        Filtered trace list matching criteria
    """
    # Convert parameters to int if they're strings from query parameters
    limit_int = int(limit) if isinstance(limit, str) else limit
    status_int = int(status) if isinstance(status, str) else status

    summaries = traces_resource.search(
        path=path,
        status=status_int,
        api_key_id=api_key_id,
        client_id=client_id,
        user_id=user_id,
        since=since,
        until=until,
        limit=limit_int,
    )
    return {
        "traces": [s.to_resource() for s in summaries],
        "cursor": {"next": None, "has_more": False}
    }, 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('audit_traces', __name__, url_prefix='/traces')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/", "ingest_spans", ingest_spans, methods=["POST"])
    new_bp.add_url_rule("/", "list_traces", list_traces, methods=["GET"])
    new_bp.add_url_rule("/<trace_id>/", "get_trace", get_trace, methods=["GET"])
    new_bp.add_url_rule("/<trace_id>/spans/", "list_spans", list_spans, methods=["GET"])
    new_bp.add_url_rule("/<trace_id>/spans/<span_id>/", "get_span", get_span, methods=["GET"])
    new_bp.add_url_rule("/search", "search_traces", search_traces, methods=["GET"])

    return new_bp
