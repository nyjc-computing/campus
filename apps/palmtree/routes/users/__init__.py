from flask import Blueprint, request

from apps.palmtree.models import user
from apps.palmtree.errors import api_errors
from common.schema import Message, Response

bp = Blueprint('users', __name__, url_prefix='/users')

users = user.User()


def init_app(app) -> None:
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
    resp = users.update(user_id, update)
    return {"message": "Profile updated"}, 200

@bp.get('/<string:user_id>/profile')
def get_user_profile(user_id: str):
    """Get a single user's profile."""
    resp = users.get(user_id)
    match resp:
        case Response(status="ok", message=msg, data=None):
            raise api_errors.ConflictError(
                message="User not found"
            )
        case Response(status="ok", message=Message.FOUND, data=user):
            return user, 200
    raise ValueError(f"Unexpected response: {resp}")

