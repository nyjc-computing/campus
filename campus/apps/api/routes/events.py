"""campus.apps.api.routes.events

API routes for the events resource (abstract endpoints only).
"""

from typing import Callable, Any

from flask import Blueprint, Flask, 
from flask import request as flask_request # For datetime wrapper

import campus_yapper

import campus.common.validation.flask as flask_validation
from campus.apps.campusauth import authenticate_client
from campus.common.errors import api_errors
from campus.models import event  # Event model to be implemented
from campus.common.utils import utc_time

bp = Blueprint('events', __name__, url_prefix='/events')
bp.before_request(authenticate_client)

yapper = campus_yapper.create()
events = event.Event()

def init_app(app: Flask | Blueprint) -> None:
    """Initialise event routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)

# NOTE: AS THE MODEL ONLY DEALS IN DATETIMES, ALL STR <-> DATETIME CONVERSION IS HANDLED HERE!
# TODO: Is this an antipattern?

DATETIME_PARAMS = ["event_time"]
DATETIME_RETURNS = ["event_time", "created_at"]
# Datetime returns can be inferred from type.
def datetime_wrapper(func: Callable) -> Callable:
    """Wraps a flask route to transform input datetimes to python datetimes
    and output datetimes to rfc3339 strings."""
    def datetime_wrapped(*args, **kwargs):
        """Wrapped function produced by datetime_wrapper."""
        raw_payload = flask_request.get_raw_json(on_error=api_errors.raise_api_error)

        # Request body str -> datetime
        for param in DATETIME_PARAMS:
            if param in raw_payload:
                raw_payload[param] = utc_time.from_rfc3339(raw_payload[param])
        
        data, status_code = func(*args, **kwargs)

        # Reply datetime -> str
        for param in DATETIME_RETURNS:
            if param in data:
                data[param] = utc_time.to_rfc3339(data[param])

        return data, status_code
    return datetime_wrapped

@bp.post('/')
@datetime_wrapper
def new_event(*_: str) -> flask_validation.JsonResponse:
    """Create a new event."""

    payload = flask_validation.validate_request_and_extract_json(
        event.EventNew.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    resource = events.new(**payload)
    flask_validation.validate_json_response(
        event.EventResource.__annotations__,
        resource,
        on_error=api_errors.raise_api_error,
    )

    yapper.emit('campus.events.new')
    return dict(resource), 201


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
