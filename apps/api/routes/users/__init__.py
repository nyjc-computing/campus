"""apps/api/routes/users

API routes for the users resource.
"""
from flask import Blueprint, request

from apps.api.models import user
from apps.common.errors import api_errors
from common.auth import authenticate_client
from common.schema import Message, Response

bp = Blueprint('users', __name__, url_prefix='/users')
bp.before_request(authenticate_client)


users = user.User()


def init_app(app) -> None:
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
def new_user():
    """Create a new user."""
    if not request.is_json:
        return {"error": "Request must be JSON"}, 400
    data = request.get_json()
    resp = users.new(**data)
    if resp.status == "ok":
        return {"message": "User created"}, 201
    else:
        return {"error": resp.message}, 400

@bp.delete('/<string:user_id>')
def delete_user(user_id: str):
    """Delete a user."""
    resp = users.delete(user_id)
    if resp.status == "ok":
        return {"message": "User deleted"}, 200
    else:
        return {"error": resp.message}, 400

@bp.get('/<string:user_id>')
def get_user(user_id: str):
    """Get a single user's summary."""
    summary = {}
    resp, _ = get_user_profile(user_id)
    summary['profile'] = resp.data
    # future calls for other user info go here
    return summary, 200

@bp.patch('/<string:user_id>')
def patch_user_profile(user_id: str):
    """Update a single user's profile."""
    if not request.is_json:
        return {"error": "Request must be JSON"}, 400
    update = request.get_json()
    resp = users.update(user_id, **update)
    return {"message": "Profile updated"}, 200

@bp.get('/<string:user_id>/profile')
# TODO: require client auth or token auth
def get_user_profile(user_id: str):
    """Get a single user's profile."""
    resp = users.get(user_id)
    match resp:
        case Response(status="ok", message=msg, data=None):
            raise api_errors.ConflictError(
                message="User not found"
            )
        case Response(status="ok", message=Message.FOUND, data=record):
            return record, 200
    raise ValueError(f"Unexpected response: {resp}")
