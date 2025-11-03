"""campus.vault.routes.users

Flask routes for Campus user management.

These routes handle creating, listing, retrieving, and deleting Campus
users.

Authentication is handled in a global routes.before_request hook.
"""

import flask

from campus.common import flask as campus_flask, schema
import campus.yapper

from ..resources import user as user_resource

# Create blueprint for user management routes
bp = flask.Blueprint('users', __name__, url_prefix='/users')

# Lazy-loaded yapper instance to avoid circular dependencies
_yapper_instance = None


def get_yapper():
    """Get yapper instance, creating it lazily to avoid circular
    dependencies."""
    global _yapper_instance
    if _yapper_instance is None:
        _yapper_instance = campus.yapper.create()
    return _yapper_instance


@bp.get("/")
@campus_flask.unpack_request
def get_all() -> campus_flask.JsonResponse:
    """Get all users.

    GET /users
    Returns: List[User]
    """
    users = user_resource.list()
    return {"users": [user.to_resource() for user in users]}, 200

@bp.post("/")
@campus_flask.unpack_request
def new(email: schema.Email, name: str) -> campus_flask.JsonResponse:
    """Create a new Campus user.

    POST /users
    Body: {
        "email": "user@example.com",
        "name": "User Name"
    }

    Returns: User
    """
    # Note that no client_secret is generated here
    # Apps are expected to generate the secret separately
    user = user_resource.new(email=email, name=name)
    get_yapper().emit('campus.users.create')
    return user.to_resource(), 201

@bp.post("/<user_id>/activate")
def activate(user_id: schema.UserID) -> campus_flask.JsonResponse:
    """Activate a user

    POST /users/{user_id}/activate
    Returns: User
    """
    user_resource[user_id].activate()
    activated_user = user_resource[user_id].get()
    get_yapper().emit('campus.users.activate', {"user_id": str(user_id)})
    return activated_user.to_resource(), 200

@bp.delete("/<user_id>")
@campus_flask.unpack_request
def delete_user(user_id: schema.UserID) -> campus_flask.JsonResponse:
    """Delete a user

    DELETE /users/{user_id}
    Returns: {}
    """
    user_resource[user_id].delete()
    get_yapper().emit('campus.users.delete', {"user_id": str(user_id)})
    return {}, 200

@bp.get("/<user_id>")
@campus_flask.unpack_request
def get(user_id: schema.UserID) -> campus_flask.JsonResponse:
    """Get details of a specific user

    GET /users/{user_id}
    Returns: User
    """
    user = user_resource[user_id].get()
    return user.to_resource(), 200

@bp.patch("/<user_id>")
@campus_flask.unpack_request
def update() -> campus_flask.JsonResponse:
    """Update a user

    PATCH /users/{user_id}
    Body: {}  (unsupported for now)
    Returns: User
    """
    return {}, 501
