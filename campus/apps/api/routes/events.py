"""campus.apps.api.routes.events

API routes for the events resource (abstract endpoints only).
"""

from typing import Callable

from flask import Blueprint, Flask
from flask import request as flask_request # For datetime wrapper

import campus.common.validation.flask as flask_validation
from campus.apps.campusauth import authenticate_client
from campus.common.errors import api_errors
from campus.models import event  # Event model to be implemented
from campus.common.utils import utc_time
import campus.yapper as campus_yapper

bp = Blueprint('events', __name__, url_prefix='/events')
bp.before_request(authenticate_client)

yapper = campus_yapper.create()
events = event.Event()

def init_app(app: Flask | Blueprint) -> None:
    """Initialise event routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)

@bp.post('/')
def new_event(*_: str) -> flask_validation.JsonResponse:
    """Create a new event."""

    payload = flask_validation.validate_request_and_extract_json(
        event.EventNew.__annotations__,
        on_error=api_errors.raise_api_error,
    )

    record = events.new(event.EventNew.from_dict(payload))

    flask_validation.validate_json_response(
        event.EventRecord.__annotations__,
        record.to_dict(),
        on_error=api_errors.raise_api_error,
    )

    yapper.emit('campus.events.new')
    return record.to_dict(), 200


@bp.get('/<string:event_id>')
def get_event_details(event_id: str) -> flask_validation.JsonResponse:
    """Get details of an event occurrence."""

    # Parse payload even though empty expected.
    # To allow for future additions.
    payload = flask_validation.validate_request_and_extract_json(
        event.EventGet.__annotations__,
        on_error=api_errors.raise_api_error,
    )

    record = events.get(event_id, event.EventGet.from_dict(payload))

    flask_validation.validate_json_response(
        event.EventRecord.__annotations__,
        record.to_dict(),
        on_error=api_errors.raise_api_error,
    )

    # No event emitted.
    return record.to_dict(), 200


@bp.patch('/<string:event_id>')
def update_event(event_id: str) -> flask_validation.JsonResponse:
    """Edit an event occurrence."""

    payload = flask_validation.validate_request_and_extract_json(
        event.EventUpdate.__annotations__,
        on_error=api_errors.raise_api_error,
    )

    record = events.update(event_id, event.EventUpdate.from_dict(payload))

    flask_validation.validate_json_response(
        event.EventRecord.__annotations__,
        record.to_dict(),
        on_error=api_errors.raise_api_error,
    )

    yapper.emit('campus.events.update')
    return record.to_dict(), 200


@bp.delete('/<string:event_id>')
def delete_event(event_id: str) -> flask_validation.JsonResponse:
    """Delete an event occurrence."""
    # Parse payload even though empty expected.
    # To allow for future additions.
    payload = flask_validation.validate_request_and_extract_json(
        event.EventDelete.__annotations__,
        on_error=api_errors.raise_api_error,
    )

    events.delete(event_id, event.EventDelete.from_dict(payload))

    yapper.emit('campus.events.delete')
    return {}, 200