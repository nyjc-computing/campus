"""campus.auth.routes.users

Flask routes for Campus user management.

These routes handle creating, listing, retrieving, updating,
activating, and deleting Campus users. User administration is a
deployment-management surface: every route requires the operator
principal (AUTH_OPERATOR_CLIENT_IDS), or — since #887, the epic's
DB-only ruling — a designated admin user (#865/#883) holding a
users:* grant row in the access-grant store whose bearer token
carries the matching management scope (read: list/get; mod:
activate; write: create/update; admin: delete). AUTH_USERS_ADMIN_
USER_IDS is no longer consulted at request time; the rows are
administered via /auth/v1/grants (#886).

Authentication is handled in a global routes.before_request hook.
"""

import flask

from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import authz, get_yapper
from ..resources import user as user_resource

# Create blueprint for user management routes
bp = flask.Blueprint('users', __name__, url_prefix='/users')


@bp.get("/")
@flask_campus.unpack_request
def get_all() -> flask_campus.JsonResponse:
    """Get all users.

    GET /users
    Authorization: operator, or a users:read grant row + scope (#887).

    Returns: List[User]
    """
    authz.require_resource_permission("users", "read")
    users = user_resource.list()
    return {"users": [user.to_resource() for user in users]}, 200


@bp.post("/")
@flask_campus.unpack_request
def new(email: schema.Email, name: str) -> flask_campus.JsonResponse:
    """Create a new Campus user.

    POST /users
    Authorization: operator, or a users:write grant row + scope (#887).

    Body: {
        "email": "user@example.com",
        "name": "User Name"
    }

    Returns: User
    """
    authz.require_resource_permission("users", "write")
    # Note that no client_secret is generated here
    # Apps are expected to generate the secret separately
    user = user_resource.new(email=email, name=name)
    get_yapper().emit('campus.users.create')
    return user.to_resource(), 201


@bp.post("/<user_id>/activate")
def activate(user_id: schema.UserID) -> flask_campus.JsonResponse:
    """Activate a user

    POST /users/{user_id}/activate
    Authorization: operator, or a users:mod grant row + scope (#887).

    Returns: User
    """
    authz.require_resource_permission("users", "mod")
    user_resource[user_id].activate()
    activated_user = user_resource[user_id].get()
    get_yapper().emit('campus.users.activate', {"user_id": str(user_id)})
    return activated_user.to_resource(), 200


@bp.delete("/<user_id>/")
@flask_campus.unpack_request
def delete_user(user_id: schema.UserID) -> flask_campus.JsonResponse:
    """Delete a user

    DELETE /users/{user_id}
    Authorization: operator, or a users:admin grant row + scope (#887).

    Returns: {}
    """
    authz.require_resource_permission("users", "admin")
    user_resource[user_id].delete()
    get_yapper().emit('campus.users.delete', {"user_id": str(user_id)})
    return {}, 200


@bp.get("/<user_id>/")
@flask_campus.unpack_request
def get(user_id: schema.UserID) -> flask_campus.JsonResponse:
    """Get details of a specific user

    GET /users/{user_id}
    Authorization: operator, or a users:read grant row + scope (#887).

    Returns: User
    """
    authz.require_resource_permission("users", "read")
    if user_id is None:
        raise api_errors.InvalidRequestError("user_id is None - check URL path")
    if not user_id:
        raise api_errors.InvalidRequestError(f"user_id is empty: {user_id!r}")
    user = user_resource[user_id].get()
    return user.to_resource(), 200


@bp.patch("/<user_id>/")
@flask_campus.unpack_request
def update(user_id: schema.UserID, name: str | None = None) -> flask_campus.JsonResponse:
    """Update a user's display name.

    PATCH /users/{user_id}
    Authorization: operator, or a users:write grant row + scope (#887).

    Body: {"name": "New Name"} — name only: a user's id IS its email
    (identity), and activation runs through the /activate endpoint, so
    no other field is patchable.

    Returns: User
    """
    authz.require_resource_permission("users", "write")
    updates = {}
    if name is not None:
        updates["name"] = name
    if not updates:
        raise api_errors.InvalidRequestError(
            "No updatable fields provided: only 'name' is patchable"
        )
    user_resource[user_id].update(**updates)
    updated_user = user_resource[user_id].get()
    get_yapper().emit('campus.users.update', {"user_id": str(user_id)})
    return updated_user.to_resource(), 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('users', __name__, url_prefix='/users')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/", "get_all", get_all, methods=["GET"])
    new_bp.add_url_rule("/", "new", new, methods=["POST"])
    new_bp.add_url_rule("/<user_id>/activate", "activate", activate, methods=["POST"])
    new_bp.add_url_rule("/<user_id>/", "delete_user", delete_user, methods=["DELETE"])
    new_bp.add_url_rule("/<user_id>/", "get", get, methods=["GET"])
    new_bp.add_url_rule("/<user_id>/", "update", update, methods=["PATCH"])

    return new_bp
