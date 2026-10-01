"""campus.audit.web.data

Data endpoints for the Audit Web UI.

The browser cannot call the authenticated /audit/v1 API directly (it has
no API key), so these routes serve the same data in-process from the
resources layer. They are intentionally unauthenticated for now; the
browser OAuth flow in docs/web-ui-requirements.md §5 must gate them
before production use (see issue #429).
"""

__all__ = ["create_blueprint"]

import flask

import campus.flask_campus as flask_campus

from ..resources import traces as traces_resource


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
            since: ISO 8601 timestamp
            until: ISO 8601 timestamp
            limit: max results (default 50)

        Returns:
            JSON: {"traces": [...], "cursor": {"next": ..., "has_more": ...}}
        """
        limit = flask.request.args.get("limit", "50")
        status = flask.request.args.get("status")
        limit_int = int(limit) if isinstance(limit, str) else limit
        status_int = int(status) if status else None
        summaries = traces_resource.search(
            path=flask.request.args.get("path") or None,
            status=status_int,
            since=flask.request.args.get("since") or None,
            until=flask.request.args.get("until") or None,
            limit=limit_int,
        )
        return {
            "traces": [s.to_resource() for s in summaries],
            "cursor": {"next": None, "has_more": False}
        }, 200

    return bp
