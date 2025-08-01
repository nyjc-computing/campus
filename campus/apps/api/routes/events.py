"""campus.apps.api.routes.events

API routes for the events resource (abstract endpoints only).
"""

from flask import Blueprint, Flask

import campus_yapper

import campus.common.validation.flask as flask_validation
from campus.apps.campusauth import authenticate_client
from campus.common.errors import api_errors
# from campus.models import event  # Event model to be implemented

bp = Blueprint('events', __name__, url_prefix='/events')
bp.before_request(authenticate_client)

yapper = campus_yapper.create()


def init_app(app: Flask | Blueprint) -> None:
    """Initialise event routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.post('/')
def new_event(*_: str) -> flask_validation.JsonResponse:
    """Create a new event occurrence."""
    # Abstract: validate and create event
    return {"message": "Not implemented"}, 501


@bp.get('/<string:event_id>')
def get_event_details(event_id: str) -> flask_validation.JsonResponse:
    """Get details of an event occurrence."""
    # Abstract: fetch event details
    return {"message": "Not implemented"}, 501


@bp.patch('/<string:event_id>')
def edit_event(event_id: str) -> flask_validation.JsonResponse:
    """Edit an event occurrence."""
    # Abstract: update event
    return {"message": "Not implemented"}, 501


@bp.delete('/<string:event_id>')
def delete_event(event_id: str) -> flask_validation.JsonResponse:
    """Delete an event occurrence."""
    # Abstract: delete event
    return {"message": "Not implemented"}, 501


@bp.get('/')
def list_events() -> flask_validation.JsonResponse:
    """List event occurrences (with optional filters)."""
    # Abstract: list events
    return {"message": "Not implemented"}, 501
