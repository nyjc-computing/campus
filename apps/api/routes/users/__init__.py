"""apps.api.routes.users

API routes for the users resource.
"""

from typing import Unpack

from flask import Blueprint, Flask

from apps.campusauth.model import authenticate_client
from apps.common.errors import api_errors
from apps.common.models import user
from common.schema import Message, Response
import common.validation.flask as flask_validation

bp = Blueprint('users', __name__, url_prefix='/users')
bp.before_request(authenticate_client)


users = user.User()


def init_app(app: Flask | Blueprint) -> None:
    """Initialise users routes with the given Flask app/blueprint."""
    user.init_db()
    app.register_blueprint(bp)
    app.add_url_rule('/me', 'get_authenticated_user', get_authenticated_user)


# This view function is not registered with the blueprint
# It will be registered with the app in the init_app function
def get_authenticated_user():
    """Get the authenticated user's summary."""
    # TODO: Get user id from auth token
    return {"message": "not implemented"}, 501


@bp.post('/')
def new_user() -> flask_validation.JsonResponse:
    """Create a new user."""
    payload = flask_validation.validate_request_and_extract_json(
        user.UserNew.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    resp = users.new(**payload)
    if resp.status == "ok":
        flask_validation.validate_json_response(
            resp.data,
            user.UserResource.__annotations__,
            on_error=api_errors.raise_api_error,
        )
        return resp.data, 201
    else:
        return {"error": resp.message}, 400


@bp.delete('/<string:user_id>')
def delete_user(user_id: str) -> flask_validation.JsonResponse:  # *_ appease linter
    """Delete a user."""
    resp = users.delete(user_id)
    if resp.status == "ok":
        return {"message": "User deleted"}, 200
    else:
        return {"error": resp.message}, 400


@bp.get('/<string:user_id>')
def get_user(user_id: str) -> flask_validation.JsonResponse:  # *_ appease linter
    """Get a single user's summary."""
    summary = {}
    record, _ = get_user_profile(user_id)
    summary['profile'] = record
    flask_validation.validate_json_response(
        summary,
        user.UserResource.__annotations__,
        on_error=api_errors.raise_api_error
    )
    # future calls for other user info go here
    return summary, 200


@bp.patch('/<string:user_id>')
def patch_user_profile(user_id: str) -> flask_validation.JsonResponse:
    """Update a single user's profile."""
    payload = flask_validation.validate_request_and_extract_json(
        user.UserUpdate.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    resp = users.update(user_id, **payload)
    flask_validation.validate_json_response(
        resp.data,
        user.UserResource.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    return resp.data, 200


@bp.get('/<string:user_id>/profile')
def get_user_profile(user_id: str) -> flask_validation.JsonResponse:
    """Get a single user's profile."""
    resp = users.get(user_id)
    match resp:
        case Response(status="ok", message=msg, data=None):
            raise api_errors.ConflictError(
                message="User not found"
            )
        case Response(status="ok", message=Message.FOUND, data=record):
            flask_validation.validate_json_response(
                record,
                user.UserResource.__annotations__,
                on_error=api_errors.raise_api_error,
            )
            return record, 200
    raise ValueError(f"Unexpected response: {resp}")
