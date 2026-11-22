"""campus.api.routes.users

API routes for user membership queries: the inverted membership
check (#1202). There is no users resource family — this blueprint
only answers "which roles does this user hold?" by walking the
circles graph, so it lives alongside the circles routes' semantics
but under its own /users prefix (the ops-facing spelling of the
question, per #1196's prod run).
"""

import flask

import campus.flask_campus as flask_campus
from campus.common import schema

from .. import resources
from ..resources.circle import resolve_member

bp = flask.Blueprint('users', __name__, url_prefix='/users')


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise user routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.get('/<string:user_id>/roles')
def get_user_roles(user_id: str) -> flask_campus.JsonResponse:
    """List a user's role circle memberships

    List the role circles a user holds, resolved transitively

    List the role circles the given user holds, resolving transitively
    through member group circles — the inverted membership check: the
    probe answers "is this user in this circle", this endpoint answers
    "which circles is this user in" without clients diffing members
    dicts (the stopgap the #1196 prod ops run had to hand-roll).

    Method:
        GET /users/{user_id}/roles

    Path Parameters:
        user_id: str (required)
            The user's ID (their email account, naming their user
            circle). A user with no resolvable memberships returns an
            empty list, not an error.

    Query Parameters:
        None

    Request Body:
        None

    Responses:
        200 OK: dict
            The user's role memberships, sorted by role circle name.
            Example:
                {
                    "user_id": "teacher@campus.test",
                    "roles": [
                        {
                            "circle_id": "circle_ab12cd34",
                            "name": "timetable.admin",
                            "access_value": 15,
                            "direct": false,
                            "via": ["staff"]
                        }
                    ]
                }

        401 Unauthorized: None
            Returned if the request carries no valid authentication.

        500 Internal Server Error: None
            Returned if a storage-level error occurs while resolving.

    Notes:
        - Reads stay open (no role membership required), consistent
          with the circles reads: the roles listing leaks nothing the
          members listings do not.
        - Resolution always goes through the shared membership
          resolver (resources.circle.resolve_member, #1202) — the
          same semantics as the enforcement gate and the transitive
          probe. access_value is the maximum across resolving paths;
          "direct" flags a direct edge; "via" lists the containment
          chain of circle names from the role circle to the member
          (empty when direct).
        - Only role circles (tag "role", e.g. the seeded
          "<resource>.admin" circles) are enumerated.
        - Emits no events.
    """
    roles = []
    for circle in resources.circle.list(tag="role"):
        resolution = resolve_member(
            circle.id,
            schema.CampusID(user_id),
        )
        if resolution is None:
            continue
        roles.append({
            "circle_id": str(circle.id),
            "name": circle.name,
            "access_value": resolution["access_value"],
            "direct": resolution["direct"],
            "via": resolution["via"],
        })
    roles.sort(key=lambda role: role["name"])
    return {"user_id": user_id, "roles": roles}, 200
