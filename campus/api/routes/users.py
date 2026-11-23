"""campus.api.routes.users

API routes for user membership queries: the inverted membership
check. There is no users resource family — this blueprint only
answers "what does this user hold?" by walking the circles graph, so
it lives alongside the circles routes' semantics but under its own
/users prefix (the ops-facing spelling of the question, per #1196's
prod run).
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


def _absolute_path(circle_record: dict, circles_by_id: dict) -> str:
    """Derive a circle's absolute path from its containment chain.

    The path is the chain of labels from the first ancestor below the
    root down to the circle itself, dotted. The root circle never
    appears (its dots would break the grammar). A missing parent
    (stale edge) truncates the chain at what is reachable — paths are
    derived, best-effort addressing, never authorization input.
    """
    labels: list[str] = []
    current = circle_record
    seen = set()
    while True:
        key = str(current.get(schema.CAMPUS_KEY))
        if key in seen:
            break  # cycle: stop, address what we have
        seen.add(key)
        labels.append(str(current.get("name") or key))
        parents = current.get("parents") or {}
        parent_ids = [p for p in parents if p in circles_by_id]
        if not parent_ids:
            break
        parent = circles_by_id[parent_ids[0]]
        if parent.get("tag") == "root":
            break
        current = parent
    labels.reverse()
    return ".".join(labels)


@bp.get('/<string:user_id>/roles')
def get_user_roles(user_id: str) -> flask_campus.JsonResponse:
    """List a user's circle memberships as absolute paths

    List every circle the given user holds — directly or through
    member circles — as absolute paths with their access values: the
    inverted membership check. The membership probe answers "is this
    user in this circle", this endpoint answers "which circles is
    this user in" without clients diffing members dicts (the stopgap
    the #1196 prod ops run had to hand-roll).

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
            The user's memberships, sorted by absolute path. Paths
            are derived from containment (root excluded; a
            multi-parent circle appears once per parent chain).
            Example:
                {
                    "user_id": "teacher@campus.test",
                    "memberships": [
                        {
                            "circle_id": "uid-circle-ab12cd34",
                            "path": "timetable",
                            "access_value": 126,
                            "direct": false,
                            "via": ["committees", "committees.timetabling"]
                        }
                    ]
                }

        401 Unauthorized: None
            Returned if the request carries no valid authentication.

        500 Internal Server Error: None
            Returned if a storage-level error occurs while resolving.

    Notes:
        - Reads stay open (no membership required), consistent with
          the circles reads: the listing leaks nothing the members
          listings do not.
        - Resolution always goes through the shared membership
          resolver (resources.circle.resolve_member) — the same
          semantics as the enforcement gate and the probe.
          access_value is the maximum across resolving paths;
          "direct" flags an edge on the circle itself; "via" lists
          the containment chain of circle names from the circle to
          the member (empty when direct).
        - User circles are excluded from the listing: membership in
          someone's personal circle is not an authority.
        - Emits no events.
    """
    circles = resources.circle.list()
    circles_by_id = {str(c.id): c.to_storage() for c in circles}
    memberships = []
    for circle in circles:
        if circle.tag == "user":
            continue
        resolution = resolve_member(
            circle.id,
            schema.CampusID(user_id),
        )
        if resolution is None:
            continue
        record = circles_by_id.get(str(circle.id), {})
        memberships.append({
            "circle_id": str(circle.id),
            "path": _absolute_path(record, circles_by_id),
            "access_value": resolution["access_value"],
            "direct": resolution["direct"],
            "via": resolution["via"],
        })
    memberships.sort(key=lambda m: m["path"])
    return {"user_id": user_id, "memberships": memberships}, 200
