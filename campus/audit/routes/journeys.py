"""campus.audit.routes.journeys

Journey query endpoints for the audit service (#803).

A journey groups the traces of one user-initiated episode (a login, a
form post and its XHRs) via a shared journey_id tag on their spans.
This endpoint serves the member traces of one journey, oldest first,
so the flow reads top to bottom.

It mirrors the shape the audit web UI's data endpoint has always
served (campus.audit.web.data get_journey), exposed on the versioned
API so consumers reach it with an API key like any other audit query.
"""

import flask

import campus.flask_campus as flask_campus

from .. import decorators
from ..helpers import audit_events
from ..resources import traces as traces_resource

# Create blueprint for journey routes
bp = flask.Blueprint('audit_journeys', __name__, url_prefix='/journeys')


@bp.get("/<journey_id>")
@audit_events.audit_event("audit.traces.journey")
@decorators.require_scopes("traces:read")
def get_journey(journey_id: str) -> flask_campus.JsonResponse:
    """List the member traces of one journey, oldest first.

    Args:
        journey_id: The journey tag carried on the member spans

    Returns:
        {"journey_id": ..., "trace_count": N, "traces": [...]} — the
        same envelope the web UI's journey view renders. An unknown or
        empty journey is a 200 with trace_count 0, not a 404: the id
        is a tag, not a stored resource.
    """
    summaries = traces_resource.journey(journey_id)
    return {
        "journey_id": journey_id,
        "trace_count": len(summaries),
        "traces": [s.to_resource() for s in summaries],
    }, 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('audit_journeys', __name__, url_prefix='/journeys')
    new_bp.add_url_rule(
        "/<journey_id>/", "get_journey", get_journey, methods=["GET"]
    )
    return new_bp
