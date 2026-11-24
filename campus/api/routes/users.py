"""campus.api.routes.users

The /users surface, two layers deep:

- the read-only **directory facade** (#1226): list/search the user
  base for staff (group-read via the staff:viewer baseline), scoped
  for everyone else to the members of circles they can read, with
  every authenticated user able to fetch their own record. The
  records themselves live in campus.auth (separate storage — service
  boundaries hold), so authorized queries are *forwarded* to auth's
  read-only /directory surface under the api's own service client;
  campus.api authorizes and rewrites the query, auth never sees an
  end-user principal.
- the **inverted membership check** (#1196): "which circles does this
  user hold", answered by walking the circles graph through the same
  shared resolver as the enforcement gate.

Both live under /users (the ops-facing spelling of the question).
"""

import flask

import campus.flask_campus as flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import authz, resources
from ..resources.circle import has_permission, resolve_member

bp = flask.Blueprint('users', __name__, url_prefix='/users')

DIRECTORY_PAGE_DEFAULT = 50
DIRECTORY_PAGE_MAX = 200


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


def _fetch_directory() -> list[dict]:
    """Fetch the full user directory from campus.auth.

    Service boundary (#1226): the records live in campus.auth (separate
    storage), so authorized queries are forwarded to auth's read-only
    /directory surface under this service's own client credentials —
    the auth side allowlists that client; end-user principals never
    reach auth here. No query parameters travel: auth dumps the
    directory, campus.api does the scoping, filtering, and pagination
    (the rewrite happens before anything is served).
    """
    import campus_python

    try:
        response = campus_python.Campus().auth.client.get(
            "/auth/v1/directory/users"
        )
    except Exception as err:  # network-level failure
        raise api_errors.InternalError(
            f"users directory forward failed: {type(err).__name__}: {err}"
        ) from err
    if not response.ok:
        raise api_errors.InternalError(
            f"users directory forward failed: auth returned "
            f"{response.status_code}"
        )
    try:
        users = response.json().get("users", [])
    except Exception as err:
        raise api_errors.InternalError(
            f"users directory forward returned malformed JSON: {err}"
        ) from err
    return users


def _circle_visible_user_ids(user_id: str) -> set[str]:
    """The directory slice visible to a caller without group-read.

    The callers' visible set is the union of email-shaped members of
    every circle where THEIR OWN membership value carries group-read
    (a guest membership confers nothing, so the primary `student`
    circle never leaks the roster; a club membership at viewer or
    above confers that club's whole roster — "student leader of a
    club" needs no extra role logic). The caller always sees
    themselves. Direct memberships only: transitive member-circle
    expansion is a later refinement. Note the asymmetry with the
    authz resolver: this is a visibility computation, not an
    authority edge — it deliberately ignores family-directed edges
    into the `users` grant circle.
    """
    visible: set[str] = set()
    for circle in resources.circle.list():
        members = circle.members or {}
        value = members.get(schema.CampusID(user_id))
        if value is None or not has_permission(int(value), "group", "read"):
            continue
        visible.update(str(member) for member in members if "@" in str(member))
    visible.add(user_id)
    return visible


def _directory_scope(user_id: str) -> set[str] | None:
    """Classify the caller: None = full list, set = visible slice.

    Full list requires group-read on the users family (the
    staff:viewer baseline carries it; no other baseline does). A
    member of no readable circle still gets their own record, so the
    scoped path never denies outright.
    """
    try:
        authz.require_resource_access("users", "group", "read")
    except api_errors.ForbiddenError:
        return _circle_visible_user_ids(user_id)
    return None


def _paginate(
        records: list[dict], limit: str | None, cursor: str | None
) -> dict:
    """Slice the filtered directory into a page.

    The cursor is the opaque spelling of the next offset; unknown
    cursors are caller errors, not 500s.
    """
    try:
        offset = int(cursor) if cursor else 0
    except (TypeError, ValueError):
        raise api_errors.InvalidRequestError(
            f"Invalid cursor: {cursor!r}"
        ) from None
    try:
        page_size = int(limit) if limit is not None else DIRECTORY_PAGE_DEFAULT
    except (TypeError, ValueError):
        raise api_errors.InvalidRequestError(
            f"Invalid limit: {limit!r}"
        ) from None
    page_size = max(1, min(page_size, DIRECTORY_PAGE_MAX))
    page = records[offset:offset + page_size]
    next_cursor = (
        str(offset + page_size)
        if offset + page_size < len(records)
        else None
    )
    return {"users": page, "next_cursor": next_cursor}


def _match_directory_query(record: dict, q: str | None) -> bool:
    """Substring match over name and id (the id IS the email)."""
    if not q:
        return True
    needle = q.lower()
    return (
        needle in str(record.get("name", "")).lower()
        or needle in str(record.get("id", "")).lower()
    )


@bp.get('/')
@flask_campus.unpack_request
def list_users(q: str | None = None, limit: str | None = None,
               cursor: str | None = None) -> flask_campus.JsonResponse:
    """Search the user directory (read-only facade).

    Method:
        GET /users/

    Authorization (#1226): a user principal with group-read on the
    users family (staff:viewer baseline) gets the full list; any
    other authenticated user gets the members of circles they can
    read (plus themselves); client principals are denied.

    Query Parameters:
        q: str (optional) — case-insensitive substring over name and
            id (the id IS the email).
        limit: int (optional) — page size, default 50, capped at 200.
        cursor: str (optional) — the previous response's next_cursor.

    Responses:
        200 OK: {"users": [directory records], "next_cursor": str | None}
        502: the campus.auth directory forward failed.
    """
    caller = authz.require_user_principal("search the user directory")
    visible = _directory_scope(caller)
    records = _fetch_directory()
    if visible is not None:
        records = [
            record for record in records
            if str(record.get("id")) in visible
        ]
    records = [
        record for record in records if _match_directory_query(record, q)
    ]
    records.sort(key=lambda record: str(record.get("id", "")))
    return _paginate(records, limit, cursor), 200


@bp.get('/<user_id>/')
@flask_campus.unpack_request
def get_user(user_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Fetch one directory record (read-only facade).

    Method:
        GET /users/{user_id}

    Authorization (#1226): a user principal with group-read on the
    users family sees any record; any authenticated user sees their
    own record (self read via the baseline); a scoped caller sees a
    record only when it sits in their circle-visible set. An
    invisible or absent user is indistinguishable (404) — scoped
    callers learn nothing about who exists outside their slice.

    Responses:
        200 OK: directory record
        404: the record is absent or outside the caller's slice
        502: the campus.auth directory forward failed.
    """
    caller = authz.require_user_principal("view a directory record")
    if str(user_id) != caller:
        try:
            authz.require_resource_access("users", "group", "read")
        except api_errors.ForbiddenError:
            if str(user_id) not in _circle_visible_user_ids(caller):
                raise api_errors.NotFoundError(
                    f"User not found: {user_id}"
                ) from None
    else:
        # Own record: self read via the baseline (staff:viewer and
        # student:guest both carry S-r).
        authz.require_resource_access("users", "self", "read")
    import campus_python

    try:
        response = campus_python.Campus().auth.client.get(
            f"/auth/v1/directory/users/{user_id}"
        )
    except Exception as err:  # network-level failure
        raise api_errors.InternalError(
            f"users directory forward failed: {type(err).__name__}: {err}"
        ) from err
    if response.status_code == 404:
        raise api_errors.NotFoundError(f"User not found: {user_id}")
    if not response.ok:
        raise api_errors.InternalError(
            f"users directory forward failed: auth returned "
            f"{response.status_code}"
        )
    return response.json(), 200
