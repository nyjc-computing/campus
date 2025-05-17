"""apps/api/routes/users

API routes for the users resource.
"""

from typing import Unpack

from flask import Blueprint, request

from apps.api.models import user
from apps.common.errors import api_errors
from common.auth import authenticate_client
from common.schema import Message, Response
from common.validation.flask import FlaskResponse, validate_and_unpack

bp = Blueprint('users', __name__, url_prefix='/users')
bp.before_request(authenticate_client)


users = user.User()


def init_app(app) -> None:
    """Initialise users routes with the given Flask app/blueprint."""
    """Initialise users routes with the given Flask app/blueprint."""
    user.init_db()
    app.register_blueprint(bp)
    app.add_url_rule('/me', 'get_authenticated_user', get_authenticated_user)
    return app


# This view function is not registered with the blueprint
# It will be registered with the app in the init_app function
def get_authenticated_user():
    """Get the authenticated user's summary."""
    # TODO: Get user id from auth token
    return {"message": "not implemented"}, 501


@bp.post('/')
@validate_and_unpack(
    request=user.UserNew.__annotations__,
    response=user.UserResource.__annotations__
)
def new_user(*_, **data: Unpack[user.UserNew]) -> FlaskResponse:
    """Create a new user."""
    resp = users.new(**data)
    if resp.status == "ok":
        return resp.data, 201
    else:
        return {"error": resp.message}, 400


@bp.delete('/<string:user_id>')
@validate_and_unpack(response={"message": str})
def delete_user(user_id: str, *_, **__) -> FlaskResponse:  # *_ appease linter
    """Delete a user."""
    resp = users.delete(user_id)
    if resp.status == "ok":
        return {"message": "User deleted"}, 200
    else:
        return {"error": resp.message}, 400

@bp.get('/<string:user_id>')
@validate_and_unpack(response=user.UserResource.__annotations__)
def get_user(user_id: str, *_, **__) -> FlaskResponse:  # *_ appease linter
    """Get a single user's summary."""
    summary = {}
    record, _ = get_user_profile(user_id)
    summary['profile'] = record
    # future calls for other user info go here
    return summary, 200

@bp.patch('/<string:user_id>')
@validate_and_unpack(
    request=user.UserUpdate.__annotations__,
    response=user.UserResource.__annotations__
)
def patch_user_profile(user_id: str, *_, **data: Unpack[user.UserUpdate]) -> FlaskResponse:  # *_ appease linter
    """Update a single user's profile."""
    resp = users.update(user_id, **data)
    return resp.data, 200

@bp.get('/<string:user_id>/profile')
@validate_and_unpack(
    response=user.UserResource.__annotations__
)
# TODO: require client auth or token auth
def get_user_profile(user_id: str, *_, **__) -> FlaskResponse:  # *_ appease linter
    """Get a single user's profile."""
    resp = users.get(user_id)
    match resp:
        case Response(status="ok", message=msg, data=None):
            raise api_errors.ConflictError(
                message="User not found"
            )
        case Response(status="ok", message=Message.FOUND, data=record):
            return record, 200
        case Response(status="ok", message=Message.FOUND, data=record):
            return record, 200
    raise ValueError(f"Unexpected response: {resp}")
