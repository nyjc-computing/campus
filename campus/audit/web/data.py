"""campus.audit.web.data

Data endpoints for the Audit Web UI.

The browser cannot call the authenticated /audit/v1 API directly (it has
no API key), so these routes serve the same data in-process from the
resources layer. They are gated by the trace-view capability
(campus.audit.web.auth): unauthenticated callers get 401, and an
authenticated session without the capability gets 403 (#928).
"""

__all__ = ["create_blueprint"]

import flask

import campus.flask_campus as flask_campus
from campus.common.errors import api_errors

from ..resources import traces as traces_resource
from . import clientnames

# Query values that mean "yes" for a boolean-ish param.
_TRUTHY = frozenset({"1", "true", "on", "yes"})


def _include_events() -> bool:
    """Whether the caller asked for audit-event traces (#941).

    Off by default: the viewer's list is for debugging real request
    flows, and the event trail is noise there. The toggle in the filter
    bar sets ?events=1.
    """
    value = (flask.request.args.get("events") or "").strip().lower()
    return value in _TRUTHY


def create_blueprint() -> flask.Blueprint:
    """Create a Flask blueprint for UI data endpoints.

    Returns:
        A Flask blueprint serving JSON data for the UI's JavaScript
    """
    bp = flask.Blueprint(
        'audit_data',
        __name__,
        url_prefix='/audit/api',
    )

    @bp.route('/traces')
    def list_traces() -> flask_campus.JsonResponse:
        """List traces for the UI trace table.

        Query params (all optional):
            path: filter by endpoint path
            status: filter by HTTP status code
            journey_id: filter by login-journey tag (#803)
            since: ISO 8601 timestamp
            until: ISO 8601 timestamp
            limit: page size, clamped to [1, MAX_PAGE_SIZE] (default
                DEFAULT_PAGE_SIZE)
            cursor: opaque token from a previous page's cursor.next
            events: include audit-event traces (#941). Off by default:
                the viewer lists request traces, and the event trail
                (audit.apikeys.*, audit.ui.auth.*, …) is noise for
                someone debugging a real flow. The versioned API keeps
                returning the events — the trail is queryable by
                design.

        Returns:
            JSON: {"traces": [...], "cursor": {"next": ..., "has_more": ...}}
        """
        status = flask.request.args.get("status")
        status_int: int | None
        if status is None or status == "":
            status_int = None
        else:
            try:
                status_int = int(status)
            except (TypeError, ValueError) as e:
                raise api_errors.InvalidRequestError(
                    f"status must be an integer, got {status!r}"
                ) from e
        page = traces_resource.search(
            path=flask.request.args.get("path") or None,
            status=status_int,
            journey_id=flask.request.args.get("journey_id") or None,
            since=flask.request.args.get("since") or None,
            until=flask.request.args.get("until") or None,
            limit=traces_resource.parse_page_size(
                flask.request.args.get("limit")
            ),
            cursor=flask.request.args.get("cursor"),
            include_events=_include_events(),
        )
        return {
            "traces": clientnames.enrich_summaries(
                [s.to_resource() for s in page.summaries]
            ),
            "cursor": {"next": page.next_cursor, "has_more": page.has_more},
        }, 200

    @bp.route('/journeys/<journey_id>')
    def get_journey(journey_id: str) -> flask_campus.JsonResponse:
        """List the member traces of one login journey (#803).

        Serves the journey page: every trace whose spans carry the
        journey tag, oldest first, so the flow reads top to bottom.
        """
        summaries = traces_resource.journey(journey_id)
        return {
            "journey_id": journey_id,
            "trace_count": len(summaries),
            "traces": clientnames.enrich_summaries(
                [s.to_resource() for s in summaries]
            ),
        }, 200

    @bp.route('/traces/<trace_id>')
    def get_trace(trace_id: str) -> flask_campus.JsonResponse:
        """Get a single trace tree for the UI detail page.

        Mirrors the versioned API's response shape:
        {"trace_id": ..., "root_span": <tree with nested children>}.
        """
        tree = traces_resource[trace_id].get_tree()
        if tree is None or tree.root is None:
            return {"error": f"Trace {trace_id} not found"}, 404
        return {
            "trace_id": trace_id,
            "root_span": clientnames.enrich_tree(tree.to_resource()),
        }, 200

    @bp.route('/traces/<trace_id>/spans/<span_id>')
    def get_span(trace_id: str, span_id: str) -> flask_campus.JsonResponse:
        """Get a single span (with headers/bodies) for the UI drawer."""
        span = traces_resource[trace_id]["spans"][span_id].get()
        if span is None:
            return {"error": f"Span {span_id} not found in trace {trace_id}"}, 404
        return span.to_resource(), 200

    return bp
