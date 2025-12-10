"""campus.auth.routes.users

Flask routes for Campus user management.

These routes handle creating, listing, retrieving, and deleting Campus
users.

Authentication is handled in a global routes.before_request hook.
"""

import flask

from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import get_yapper
from ..resources import user as user_resource

# Create blueprint for user management routes
bp = flask.Blueprint('users', __name__, url_prefix='/users')


@bp.get("/")
@flask_campus.unpack_request
def get_all() -> flask_campus.JsonResponse:
    """Get all users.

    GET /users
    Returns: List[User]
    """
    users = user_resource.list()
    return {"users": [user.to_resource() for user in users]}, 200


@bp.post("/")
@flask_campus.unpack_request
def new(email: schema.Email, name: str) -> flask_campus.JsonResponse:
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
def activate(user_id: schema.UserID) -> flask_campus.JsonResponse:
    """Activate a user

    POST /users/{user_id}/activate
    Returns: User
    """
    user_resource[user_id].activate()
    activated_user = user_resource[user_id].get()
    get_yapper().emit('campus.users.activate', {"user_id": str(user_id)})
    return activated_user.to_resource(), 200


@bp.delete("/<user_id>")
@flask_campus.unpack_request
def delete_user(user_id: schema.UserID) -> flask_campus.JsonResponse:
    """Delete a user

    DELETE /users/{user_id}
    Returns: {}
    """
    user_resource[user_id].delete()
    get_yapper().emit('campus.users.delete', {"user_id": str(user_id)})
    return {}, 200


@bp.get("/<user_id>")
@flask_campus.unpack_request
def get(user_id: schema.UserID) -> flask_campus.JsonResponse:
    """Get details of a specific user

    GET /users/{user_id}
    Returns: User
    """
    import logging
    logging.info(
        f"[DEBUG] get user route: user_id={user_id!r} type={type(user_id)}"
    )
    if user_id is None:
        raise api_errors.InvalidRequestError("user_id is None - check URL path")
    if not user_id:
        raise api_errors.InvalidRequestError(f"user_id is empty: {user_id!r}")
    user = user_resource[user_id].get()
    return user.to_resource(), 200


@bp.patch("/<user_id>")
@flask_campus.unpack_request
def update() -> flask_campus.JsonResponse:
    """Update a user

    PATCH /users/{user_id}
    Body: {}  (unsupported for now)
    Returns: User
    """
    return {}, 501
