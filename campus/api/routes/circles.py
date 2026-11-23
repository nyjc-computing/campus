"""campus.api.routes.circles

API routes for the circles resource.
"""

from typing import Any

import campus_python
import flask

import campus.flask_campus as flask_campus
import campus.model
import campus.yapper
from campus.common import schema
from campus.common.errors import api_errors

from .. import authz, resources
from ..resources.circle import circle_storage

bp = flask.Blueprint('circles', __name__, url_prefix='/circles')

# Lazily initialized yapper and auth_root - set in init_app() after test fixtures are ready
# This prevents connection to external services during module import in tests
# Type: ignore because we initialize these in init_app() before first use
yapper: campus.yapper.YapperInterface = None  # type: ignore
auth_root: Any = None  # type: ignore


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise circle routes with the given Flask app/blueprint."""
    global yapper, auth_root
    # Initialize yapper after test fixtures have set up the vault
    yapper = campus.yapper.create()
    # Initialize auth_root after test fixtures have set up the auth service
    auth_root = campus_python.Campus().auth.root  # type: ignore
    app.register_blueprint(bp)


@bp.get('/')
@flask_campus.unpack_request
def list_circles(tag: str | None = None) -> flask_campus.JsonResponse:
    """List all circles

    List all circles matching filter requirements
    """
    result = resources.circle.list(**{"tag": tag} if tag else {})
    return {"data": [circle.to_resource() for circle in result]}, 200


@bp.post('/')
@flask_campus.unpack_request
def new_circle(
        name: str,
        tag: str,
        description: str = "",
        parents: dict[str, int] | None = None,
) -> flask_campus.JsonResponse:
    """Create a new circle

    Create a new circle

    .

    Method:
        POST /circles

    Path Parameters:
        None

    Query Parameters:
        None

    Request Body (application/json):
        name: str (required)
            The name of the new circle.
            Must not already be used by another circle.
        description: str (optional)
            An optional description of the circle.
        tag: CircleTag (required)
            The tag that categorizes the circle.
        parents: dict[CircleID, AccessValue] (optional)
            A mapping of parent circle IDs to integer access values.
            Omit to create a circle with no parents.
            The root circle (tag "root") must not have parents.

    Responses:
        201 Created: dict
            JSON object representing the newly created circle.
            Example:
                {
                    "id": "circle_ab12cd34",
                    "name": "Design Team",
                    "description": "Handles UI/UX",
                    "tag": "project",
                    "parents": {
                        "circle_1a2b3c4d": 15
                    }
                }

        400 Bad Request: None
            Returned if the request body is invalid or missing required fields.

        409 Conflict: None
            - Returned if another circle already uses the requested name
              (best-effort, exact-match check).
            - Returned if tag is "root" and parents were provided.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `circles.admin` circle (only user tokens are eligible).

        422 Unprocessable Entity: None
            Returned if validation fails (e.g., a required field is missing).
    """
    authz.require_resource_admin("circles", "create circles")
    circle = resources.circle.new(
        name=name,
        description=description,
        tag=tag,
        **{"parents": parents} if parents else {},
    )
    resource = circle.to_resource()
    yapper.emit('campus.circles.new')
    return resource, 201


@bp.delete('/<string:circle_id>/')
def delete_circle(circle_id: str) -> flask_campus.JsonResponse:
    """Delete a circle

    Delete a circle by its unique ID

    by its unique ID.

    Method:
        DELETE /circles/{circle_id}

    Path Parameters:
        circle_id: str (required)
            The unique identifier of the circle to delete.

    Query Parameters:
        None

    Request Body:
        None

    Responses:
        200 OK: dict
            Empty JSON object indicating successful deletion.
            Example:
                {}

        409 Conflict: None
            Returned if the circle does not exist.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `circles.admin` circle (only user tokens are eligible).

        500 Internal Server Error: None
            Returned if an unexpected storage error occurs.

    Notes:
        - This action is **destructive** and cannot be undone.
        - Requires membership in the `circles.admin` circle.
        - Emits the event: `campus.circles.delete`
    """
    authz.require_resource_admin("circles", "delete circles")
    resources.circle[schema.CampusID(circle_id)].delete()
    yapper.emit('campus.circles.delete', {"circle_id": circle_id})
    return {}, 200


@bp.get('/<string:circle_id>/')
def get_circle_details(circle_id: str) -> flask_campus.JsonResponse:
    """Get circle details

    Retrieve detailed information about a specific circle

    Retrieve detailed information about a specific circle.

    Method:
        GET /circles/{circle_id}

    Path Parameters:
        circle_id: str (required)
            The unique identifier of the circle to retrieve.

    Query Parameters:
        None

    Request Body:
        None

    Responses:
        200 OK: dict
            JSON object representing the circle details.
            Example:
                {
                    "id": "circle_ab12cd34",
                    "name": "Design Team",
                    "description": "Handles UI/UX",
                    "tag": "project",
                    "parents": {
                        "circle_1a2b3c4d": 15
                    },
                    "sources": {}
                }

        409 Conflict: None
            Returned if the circle does not exist.

        500 Internal Server Error: None
            Returned if a storage-level error occurs while retrieving the circle.

    Notes:
        - If the circle is not found, a `ConflictError` is raised with message `"Circle not found"`.
        - Response is validated against `CircleResource`.
        - Currently, `sources` is always an empty object (may change in future with enrichment).
    """
    circle = resources.circle[schema.CampusID(circle_id)].get()
    resource = circle.to_resource()
    return resource, 200


@bp.patch('/<string:circle_id>/')
@flask_campus.unpack_request
def edit_circle(
        *,
        circle_id: str,
        name: str,
        description: str | None = None
) -> flask_campus.JsonResponse:
    """Update circle name/description

    Update the name and/or description of an existing circle

    Update the name, and optionally the description, of an existing circle.

    Method:
        PATCH /circles/{circle_id}

    Path Parameters:
        circle_id: str (required)
            The unique identifier of the circle to update.

    Query Parameters:
        None

    Request Body (application/json):
        name: str (required)
            The new name for the circle.
            Must not already be used by another circle.
        description: str (optional)
            The new description for the circle.
            Unchanged if omitted.

    Responses:
        200 OK: dict
            Empty object indicating that the update was successful.
            Example:
                {}

        409 Conflict: None
            - Returned if the circle does not exist.
            - Returned if another circle already uses the requested name
              (best-effort, exact-match check).

        403 Forbidden: None
            Returned if the caller is not a member of the
            `circles.admin` circle (only user tokens are eligible).

        422 Unprocessable Entity: None
            Returned if validation fails (e.g., name is missing).

        500 Internal Server Error: None
            Returned if a storage-level error occurs during the update.

    Notes:
        - `name` is required; `description` is unchanged when omitted.
        - If no changes are detected, the request is treated as a no-op (200 OK, no error).
        - Requires membership in the `circles.admin` circle.
        - Emits the event: `campus.circles.update`.
    """
    authz.require_resource_admin("circles", "edit circles")
    updates = {"name": name}
    if description is not None:
        updates["description"] = description
    resources.circle[schema.CampusID(circle_id)].update(**updates)
    yapper.emit('campus.circles.update', {"circle_id": circle_id})
    return {}, 200


@bp.post('/<string:circle_id>/move')
def move_circle(circle_id: str) -> flask_campus.JsonResponse:
    """Move a circle to a new parent."""
    authz.require_resource_admin("circles", "move circles")
    return {"message": "Not implemented"}, 501


@bp.get('/<string:circle_id>/members/')
def get_circle_members(circle_id: str) -> flask_campus.JsonResponse:
    """List circle members

    Retrieve the member IDs of a circle along with their access values

    Retrieve the member IDs of a circle along with their access values.

    Method:
        GET /circles/{circle_id}/members

    Path Parameters:
        circle_id: str (required)
            The unique identifier of the circle whose members are to be listed.

    Query Parameters:
        None

    Request Body:
        None

    Responses:
        200 OK: dict
            A mapping of member IDs to their access values within the circle.
            Example:
                {
                    "user:alice": "admin",
                    "user:bob": "read"
                }

        409 Conflict: None
            Returned if the circle does not exist.

        500 Internal Server Error: None
            Returned if a storage-level error occurs while retrieving members.

    Notes:
        - The result includes only direct members of the circle.
        - If the circle has no members, an empty object is returned.
        - Emits no events and does not currently validate the response structure.
    """
    resource = resources.circle.members.list(schema.CampusID(circle_id))
    # TODO: validate response
    return resource, 200


@bp.get('/<string:circle_id>/members/<member_id>/')
def get_circle_member(
        circle_id: str,
        member_id: str
) -> flask_campus.JsonResponse:
    """Probe circle membership

    Probe a single membership: the member's access value, or 404 when
    unreachable. Resolves transitively through member group circles by
    default — the same question campus.api's enforcement gate answers.

    Probe a single membership in a circle. An unreachable member is an
    expected negative answer (404), not an error: clients use this
    endpoint for cheap, fail-closed role checks (e.g. "is this user in
    the timetable.admin role circle") instead of fetching the full
    members dict. A direct-only answer is available explicitly via
    ?resolve=direct.

    Method:
        GET /circles/{circle_id}/members/{member_id}

    Path Parameters:
        circle_id: str (required)
            The unique identifier of the circle to probe.
        member_id: str (required)
            The member identifier to look up, as stored: a circle UID
            or the email name of a user circle.

    Query Parameters:
        resolve: str (optional)
            Membership resolution mode. Omit (or "transitive") to
            resolve through member group circles — the default, with
            the same semantics as the enforcement gate (#1202/#1207):
            cycle-safe, stale keys fail closed per key. "direct"
            probes the circle's direct members dict only. Any other
            value is a validation error.

    Request Body:
        None

    Responses:
        200 OK: dict
            The member's access value within the circle. The default
            (transitive) probe adds resolution detail; ?resolve=direct
            returns the member_id and access_value fields only.
            Example (default / ?resolve=transitive, reached via a
            group):
                {
                    "member_id": "teacher@campus.test",
                    "access_value": 15,
                    "direct": false,
                    "via": ["students"]
                }
            Example (?resolve=direct):
                {
                    "member_id": "teacher@campus.test",
                    "access_value": 15
                }

        404 Not Found: None
            Returned if the circle has no such member under the
            requested resolution mode (the probe's expected negative
            answer). Under the default transitive mode the message
            points at ?resolve=direct, the common cause being callers
            that expected the pre-#1207 direct-only default.

        409 Conflict: None
            Returned if the circle does not exist.

        422 Unprocessable Entity: None
            Returned if resolve has a value other than "direct" or
            "transitive".

        500 Internal Server Error: None
            Returned if a storage-level error occurs while probing.

    Notes:
        - Reads stay open (no role membership required), consistent
          with GET /circles/{circle_id}/members/: the probe leaks
          nothing the members listing does not.
        - Resolution answers through the shared membership resolver
          (resources.circle.resolve_member, #1202) — the same
          implementation the enforcement gate uses, so gate and probe
          decisions agree by construction. access_value is the maximum
          across resolving paths; "direct" flags a direct edge and
          "via" lists the containment chain of circle names from the
          probed circle to the member (empty when direct).
        - The default flipped from direct-only to transitive
          (#1207), completing the #1202 switchover ahead of its
          Sunset date; the Deprecation/Sunset headers are retired.
          Direct-only callers must pass the explicit ?resolve=direct.
        - Emits no events.
    """
    resolve = flask.request.args.get("resolve")
    if resolve is not None and resolve not in ("direct", "transitive"):
        raise api_errors.ValidationError(
            f"Invalid resolve value: {resolve!r} "
            '(expected "direct" or "transitive")',
            field="resolve",
        )
    resolution = resources.circle.members.resolve(
        schema.CampusID(circle_id),
        schema.CampusID(member_id),
        transitive=resolve != "direct",
    )
    if resolution is None:
        if resolve == "direct":
            # The caller asked for direct-only; the answer needs no
            # switchover hint.
            raise api_errors.NotFoundError(
                "Member not found in circle",
                id=member_id
            )
        # The default walks the whole graph; callers that expected the
        # pre-#1207 direct-only default are the common cause — point
        # them at the explicit spelling.
        raise api_errors.NotFoundError(
            "Member not found in circle: not a direct member and not "
            "reachable through any member group. Pass ?resolve=direct "
            "for a direct-only probe.",
            id=member_id
        )
    result = {
        "member_id": member_id,
        "access_value": resolution["access_value"],
    }
    if resolve != "direct":
        result["direct"] = resolution["direct"]
        result["via"] = resolution["via"]
    return result, 200


@bp.post('/<string:circle_id>/members/add')
@flask_campus.unpack_request
def add_circle_member(
        *,
        circle_id: str,
        member_id: str,
        access_value: int,
) -> flask_campus.JsonResponse:
    """Add circle member

    Add a member to a circle with a specified access level

    Add a member to a circle with a specified access level.

    Method:
        POST /circles/{circle_id}/members/add

    Path Parameters:
        circle_id: str (required)
            The unique identifier of the circle to which the member will be added.

    Query Parameters:
        None

    Request Body (application/json):
        member_id: str (required)
            The member being added — circles contain only circles, so
            this is either a circle ID or the email name of the user's
            circle (each user has a circle named after their email
            account). The addressed circle must exist.
        access_value: AccessValue (required)
            The level of access the member will have in the parent circle.

    Responses:
        200 OK: dict
            Empty object indicating the member was successfully added.
            Example:
                {}

        409 Conflict: None
            - Returned if the target circle does not exist.
            - Returned if the member ID does not address an existing
              circle (including a missing user circle for an
              email-shaped ID).
            - Returned if no changes were applied (e.g., member already exists with same access).

        403 Forbidden: None
            Returned if the caller is not a member of the
            `circles.admin` circle (only user tokens are eligible).

        500 Internal Server Error: None
            Returned if a storage-level error occurs during the operation.

    Notes:
        - Emits the event: `campus.circles.members.add`.
        - Requires membership in the `circles.admin` circle: membership
          editing is privilege escalation once circles gate access.
        - Members are stored as a single `members` dict on the circle
          record, written by read-modify-write: member identifiers may
          be email names, whose dots a nested-field update path would
          misparse.
    """
    authz.require_resource_admin("circles", "edit circle membership")
    resources.circle.members.add(
        schema.CampusID(circle_id),
        member_id=schema.CampusID(member_id),
        access_value=access_value
    )
    yapper.emit('campus.circles.members.add', {"circle_id": circle_id})
    return {}, 200


@bp.delete('/<string:circle_id>/members/remove')
@flask_campus.unpack_request
def remove_circle_member(
        *,
        circle_id: str,
        member_id: str,
) -> flask_campus.JsonResponse:
    """Remove circle member

    Remove a member from a circle

    Remove a member from a circle.

    Method:
        DELETE /circles/{circle_id}/members/remove

    Path Parameters:
        circle_id: str (required)
            The ID of the circle from which the member will be removed.

    Request Body (application/json):
        member_id: str (required)
            The member identifier to remove, as added: a circle ID or
            the email name of a user circle.

    Responses:
        200 OK: dict
            Empty object indicating the member was successfully removed.
            Example:
                {}

        409 Conflict: None
            - Returned if the target circle does not exist.
            - Returned if the specified member is not part of the circle.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `circles.admin` circle (only user tokens are eligible).

        500 Internal Server Error: None
            Returned if a storage-level error occurs while removing the member.

    Notes:
        - Emits the event: `campus.circles.members.remove`.
        - Requires membership in the `circles.admin` circle.
        - Removal rewrites the circle's `members` dict without the
          member (read-modify-write; see POST /members/add).
        - Only direct members can be removed this way.
        - The response is not currently validated.
    """
    authz.require_resource_admin("circles", "edit circle membership")
    resources.circle.members.remove(
        schema.CampusID(circle_id),
        member_id=schema.CampusID(member_id)
    )
    yapper.emit('campus.circles.members.remove', {"circle_id": circle_id, "member_id": member_id})
    return {}, 200

# TODO: Redesign for clearer access update: circles can have multiple parentage paths


@bp.patch('/<string:circle_id>/members/')
@flask_campus.unpack_request
def patch_circle_member(
        *,
        circle_id: str,
        member_id: str,
        access_value: int
) -> flask_campus.JsonResponse:
    """Update member access level

    Update the access level of a member within a circle

    Update the access level of a member within a circle.

    Method:
        PATCH /circles/{circle_id}/members/{member_circle_id}

    Path Parameters:
        circle_id: str (required)
            The ID of the circle where the member's access is being updated.
        member_circle_id: str (required)
            The ID of the member circle whose access is being modified.

    Query Parameters:
        None

    Request Body (application/json):
        member_id: str (required)
            Must match the path parameter `member_circle_id`.
        access_value: AccessValue (required)
            The new access level to assign to the member.

    Responses:
        200 OK: dict
            Empty object indicating the access level was successfully updated.
            Example:
                {}

        409 Conflict: None
            - Returned if the member circle does not exist.
            - Returned if no changes were applied.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `circles.admin` circle (only user tokens are eligible).

        500 Internal Server Error: None
            Returned if a storage-level error occurs.

    Notes:
        - This operation will create or update the member's access.
        - Requires membership in the `circles.admin` circle.
        - Emits the event: `campus.circles.members.set`.
        - No validation is currently performed to compare existing access.
    """
    authz.require_resource_admin("circles", "edit circle membership")
    resources.circle.members.set(
        schema.CampusID(circle_id),
        member_id=schema.CampusID(member_id),
        access_value=access_value
    )
    yapper.emit('campus.circles.members.set', {"circle_id": circle_id, "member_id": member_id})
    return {}, 200


@bp.get('/<string:circle_id>/users')
def get_circle_users(circle_id: str) -> flask_campus.JsonResponse:
    """List the user circles reachable through a circle's membership graph.

    Walk the circle's members transitively and enumerate every
    contained user circle (by email name) — the audit question
    "who is venues:admin", answered without clients hand-walking
    members dicts. Group circles are traversed; user circles are
    collected; stale member keys (circle deleted after being added)
    are skipped fail-closed without blocking the remaining walk.

    Method:
        GET /api/v1/circles/{circle_id}/users

    Path Parameters:
        circle_id: str (required)
            The circle whose membership graph to enumerate.

    Query Parameters:
        None

    Request Body:
        None

    Responses:
        200 OK: dict
            {"circle_id": str, "users": [email names, sorted]}

        401 Unauthorized: None
            Returned if the request carries no valid authentication.

        409 Conflict: None
            Returned if the circle does not exist (consistent with
            the members listing).

    Notes:
        - Reads stay open (no membership required), consistent with
          the members listing: this enumerates exactly what a client
          could compute by walking the members listings, so it leaks
          nothing new.
        - Emits no events.
    """
    from campus.storage import errors as storage_errors

    try:
        start = circle_storage.get_by_id(schema.CampusID(circle_id))
        if start is None:
            raise api_errors.ConflictError(
                "Circle not found",
                id=circle_id
            )
    except storage_errors.NotFoundError:
        raise api_errors.ConflictError(
            "Circle not found",
            id=circle_id
        ) from None
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e

    users: set[str] = []
    visited: set[str] = set()
    pending = [start]
    while pending:
        record = pending.pop()
        key = str(record.get(schema.CAMPUS_KEY))
        if key in visited:
            continue
        visited.add(key)
        if record.get("tag") == "user":
            users.append(str(record.get("name") or key))
            continue  # user circles are leaves
        for member_key in (record.get("members") or {}):
            member_key = str(member_key)
            if member_key in visited:
                continue
            if "@" not in member_key:
                try:
                    member_record = circle_storage.get_by_id(
                        schema.CampusID(member_key)
                    )
                except storage_errors.NotFoundError:
                    continue
                except campus.storage.errors.StorageError as e:
                    raise api_errors.InternalError.from_exception(e) from e
                if member_record:
                    pending.append(member_record)
            else:
                # Email-shaped keys name user circles directly; verify
                # the circle exists rather than trusting the key.
                try:
                    member_record = circle_storage.get_matching(
                        {"name": member_key}
                    )
                except campus.storage.errors.StorageError as e:
                    raise api_errors.InternalError.from_exception(e) from e
                if member_record:
                    pending.append(member_record[0])
    return {
        "circle_id": circle_id,
        "users": sorted(users),
    }, 200
