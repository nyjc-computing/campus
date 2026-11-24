"""campus.auth.routes.directory

Read-only user directory for the campus.api users facade (#1226).

campus.auth's management surface is walled by design (#854/#865): user
creation/import, session and login inspection, and vault management are
admin-only, and clients are never designated admins there — even with a
grant row. The facade's forward call is precisely a client principal,
so it cannot use /users. This module exposes the narrow read-only slice
the facade needs, gated the same way the operator itself is gated: an
operator-configured client allowlist (AUTH_DIRECTORY_CLIENT_IDS,
comma-separated client ids, read at request time).

User principals are denied here on purpose: end users consume the
directory through campus.api's circles authorization (the /users
facade), never through auth internals — a user principal on this
surface is a design error, not a missing permission.

Both routes are read-only by construction; this module defines no
write route.
"""

import flask

import campus.flask_campus as flask_campus
from campus.common import env, schema
from campus.common.errors import api_errors

from .. import authz
from ..resources import user as user_resource

DIRECTORY_CLIENT_IDS_ENVVAR = "AUTH_DIRECTORY_CLIENT_IDS"

bp = flask.Blueprint('directory', __name__, url_prefix='/directory')


def _directory_client_ids() -> set[str]:
    """The allowlisted client ids, parsed per request (mirrors the
    operator env var's read-at-request-time convention)."""
    raw = env.get(DIRECTORY_CLIENT_IDS_ENVVAR) or ""
    return {c.strip() for c in raw.split(",") if c.strip()}


def require_directory_reader() -> None:
    """Allow the operator or an allowlisted client; deny user principals.

    Fail-closed: an unauthenticated caller, an unlisted client, and a
    user principal are all denied with distinct messages.
    """
    if authz.is_operator():
        return
    client = getattr(flask.g, "current_client", None)
    client_id = (
        str(client.get("id") or "")
        if isinstance(client, dict)
        else str(getattr(client, "id", "") or "")
    )
    if client_id and client_id in _directory_client_ids():
        return
    if client_id:
        raise api_errors.ForbiddenError(
            f"Client '{client_id}' is not allowlisted for directory "
            f"reads ({DIRECTORY_CLIENT_IDS_ENVVAR})"
        )
    raise api_errors.ForbiddenError(
        "User principals may not read the directory on campus.auth: "
        "use the campus.api users facade"
    )


@bp.get("/users/")
@flask_campus.unpack_request
def list_users() -> flask_campus.JsonResponse:
    """List all users (read-only directory dump).

    GET /directory/users
    Authorization: the operator, or a client in AUTH_DIRECTORY_CLIENT_IDS.

    No query parameters by design: filtering, scoping, and pagination
    are campus.api's job — it rewrites the query per the caller's
    circles scope before serving (#1226).

    Returns: {"users": [User, ...]}
    """
    require_directory_reader()
    users = user_resource.list()
    return {"users": [user.to_resource() for user in users]}, 200


@bp.get("/users/<user_id>/")
@flask_campus.unpack_request
def get_user(user_id: schema.UserID) -> flask_campus.JsonResponse:
    """Get one user (read-only directory record).

    GET /directory/users/{user_id}
    Authorization: the operator, or a client in AUTH_DIRECTORY_CLIENT_IDS.

    Returns: User
    """
    require_directory_reader()
    user = user_resource[user_id].get()
    return user.to_resource(), 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('directory', __name__, url_prefix='/directory')
    new_bp.add_url_rule("/users/", "list_users", list_users, methods=["GET"])
    new_bp.add_url_rule(
        "/users/<user_id>/", "get_user", get_user, methods=["GET"]
    )
    return new_bp
