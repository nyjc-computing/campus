"""campus.apps.api.routes.users

API routes for the users resource.
"""

from flask import Blueprint, Flask

import campus_yapper

import campus.common.validation.flask as flask_validation
from campus.apps.campusauth import authenticate_client
from campus.common.errors import api_errors
from campus.models import user

bp = Blueprint('users', __name__, url_prefix='/users')
bp.before_request(authenticate_client)

users = user.User()
yapper = campus_yapper.create()


def init_app(app: Flask | Blueprint) -> None:
    """Initialise users routes with the given Flask app/blueprint."""
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
    resource = users.new(**payload)
    flask_validation.validate_json_response(
        user.UserResource.__annotations__,
        resource,
        on_error=api_errors.raise_api_error,
    )
    yapper.emit('campus.users.new')
    return dict(resource), 201


@bp.delete('/<string:user_id>')
def delete_user(user_id: str) -> flask_validation.JsonResponse:
    """Delete a user."""
    users.delete(user_id)
    yapper.emit('campus.users.delete')
    return {}, 200


@bp.get('/<string:user_id>')
def get_user(user_id: str) -> flask_validation.JsonResponse:
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
    users.update(user_id, **payload)
    yapper.emit('campus.users.update')
    return {}, 200


@bp.get('/<string:user_id>/profile')
def get_user_profile(user_id: str) -> flask_validation.JsonResponse:
    """Get a single user's profile."""
    resource = users.get(user_id)
    flask_validation.validate_json_response(
        user.UserResource.__annotations__,
        resource,
        on_error=api_errors.raise_api_error,
    )
    return dict(resource), 200
