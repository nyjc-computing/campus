"""campus.apps.api.routes.circles

API routes for the circles resource.
"""

from typing import Any

import campus_python
import flask

import campus.model
import campus.yapper
from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import resources

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
    auth_root = campus_python.Campus(timeout=60).auth.root  # type: ignore
    app.register_blueprint(bp)


@bp.get('/')
@flask_campus.unpack_request
def list_circles(tag: str | None = None) -> flask_campus.JsonResponse:
    """List all circles matching filter requirements."""
    result = resources.circle.list(**{"tag": tag} if tag else {})
    return {"data": [circle.to_resource() for circle in result]}, 200


@bp.post('/')
@flask_campus.unpack_request
def new_circle(
        name: str,
        description: str,
        tag: str,
        parents: dict[str, int] | None = None,
) -> flask_campus.JsonResponse:
    """Summary:
        Create a new circle.

    Method:
        POST /circles

    Path Parameters:
        None

    Query Parameters:
        None

    Request Body (application/json):
        name: str (required)
            The name of the new circle.
        description: str (optional)
            An optional description of the circle.
        tag: CircleTag (required)
            The tag that categorizes the circle.
        parents: dict[CirclePath, AccessValue] (optional)
            A mapping of parent circle paths to access values.
            At least one parent is required (defaults to "admin" if omitted).
            The full path is of the form: `{parent path} / {circle_id}`.

    Responses:
        201 Created: dict
            JSON object representing the newly created circle.
            Example:
                {
                    "id": "design-team",
                    "name": "Design Team",
                    "description": "Handles UI/UX",
                    "tag": "project",
                    "parents": {
                        "/root/admin": "admin"
                    }
                }

        400 Bad Request: None
            Returned if the request body is invalid or missing required fields.

        422 Unprocessable Entity: None
            Returned if validation fails (e.g., tag or parent format is incorrect).
    """
    circle = resources.circle.new(
        name=name,
        description=description,
        tag=tag,
        **{"parents": parents} if parents else {},
    )
    resource = circle.to_resource()
    yapper.emit('campus.circles.new')
    return resource, 201


@bp.delete('/<string:circle_id>')
def delete_circle(circle_id: str) -> flask_campus.JsonResponse:
    """Summary:
        Delete a circle by its unique ID.

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

        500 Internal Server Error: None
            Returned if an unexpected storage error occurs.

    Notes:
        - This action is **destructive** and cannot be undone.
        - Only admins or owners should perform this operation.
        - Emits the event: `campus.circles.delete`
    """
    resources.circle[schema.CampusID(circle_id)].delete()
    yapper.emit('campus.circles.delete', {"circle_id": circle_id})
    return {}, 200


@bp.get('/<string:circle_id>')
def get_circle_details(circle_id: str) -> flask_campus.JsonResponse:
    """Summary:
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
                    "id": "design-team",
                    "name": "Design Team",
                    "description": "Handles UI/UX",
                    "tag": "project",
                    "parents": {
                        "/root/admin": "admin"
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


@bp.patch('/<string:circle_id>')
@flask_campus.unpack_request
def edit_circle(
        *,
        circle_id: str,
        name: str,
        description: str
) -> flask_campus.JsonResponse:
    """Summary:
        Update the name and/or description of an existing circle.

    Method:
        PATCH /circles/{circle_id}

    Path Parameters:
        circle_id: str (required)
            The unique identifier of the circle to update.

    Query Parameters:
        None

    Request Body (application/json):
        name: str (optional)
            The new name for the circle.
        description: str (optional)
            The new description for the circle.

    Responses:
        200 OK: dict
            Empty object indicating that the update was successful.
            Example:
                {}

        409 Conflict: None
            Returned if the circle does not exist.

        500 Internal Server Error: None
            Returned if a storage-level error occurs during the update.

    Notes:
        - At least one of `name` or `description` must be present in the request.
        - If no changes are detected, the request is treated as a no-op (200 OK, no error).
        - Emits the event: `campus.circles.update`.
    """
    updates = {}
    if name:
        updates["name"] = name
    if description:
        updates["description"] = description
    if not updates:
        raise api_errors.InvalidRequestError("Empty request body")
    resources.circle[schema.CampusID(circle_id)].update(**updates)
    yapper.emit('campus.circles.update', {"circle_id": circle_id})
    return {}, 200


@bp.post('/<string:circle_id>/move')
def move_circle(circle_id: str) -> flask_campus.JsonResponse:
    """Move a circle to a new parent."""
    return {"message": "Not implemented"}, 501


@bp.get('/<string:circle_id>/members')
def get_circle_members(circle_id: str) -> flask_campus.JsonResponse:
    """Summary:
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


@bp.post('/<string:circle_id>/members/add')
@flask_campus.unpack_request
def add_circle_member(
        *,
        circle_id: str,
        member_id: str,
        access_value: int,
) -> flask_campus.JsonResponse:
    """Summary:
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
            The ID of the circle being added as a member.
        access_value: AccessValue (required)
            The level of access the member will have in the parent circle.

    Responses:
        200 OK: dict
            Empty object indicating the member was successfully added.
            Example:
                {}

        409 Conflict: None
            - Returned if the member circle does not exist.
            - Returned if no changes were applied (e.g., member already exists with same access).

        500 Internal Server Error: None
            Returned if a storage-level error occurs during the operation.

    Notes:
        - Emits the event: `campus.circles.members.add`.
        - This operation directly updates a nested field (`members.{member_id}`) in storage.
        - Only circle IDs can be added as members — not users or arbitrary entities.
    """
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
    """Summary:
        Remove a member from a circle.

    Method:
        DELETE /circles/{circle_id}/members/remove

    Path Parameters:
        circle_id: str (required)
            The ID of the circle from which the member will be removed.

    Request Body (application/json):
        member_id: str (required)
            The ID of the member circle to remove.

    Responses:
        200 OK: dict
            Empty object indicating the member was successfully removed.
            Example:
                {}

        409 Conflict: None
            - Returned if the target circle does not exist.
            - Returned if the specified member is not part of the circle.
            - Returned if no changes were applied during the removal.

        500 Internal Server Error: None
            Returned if a storage-level error occurs while removing the member.

    Notes:
        - Emits the event: `campus.circles.members.remove`.
        - Removal uses a MongoDB `$unset` on the path `members.{member_id}`.
        - Only direct member circles can be removed this way.
        - The response is not currently validated.
    """
    resources.circle.members.remove(
        schema.CampusID(circle_id),
        member_id=schema.CampusID(member_id)
    )
    yapper.emit('campus.circles.members.remove', {"circle_id": circle_id, "member_id": member_id})
    return {}, 200

# TODO: Redesign for clearer access update: circles can have multiple parentage paths


@bp.patch('/<string:circle_id>/members')
@flask_campus.unpack_request
def patch_circle_member(
        *,
        circle_id: str,
        member_id: str,
        access_value: int
) -> flask_campus.JsonResponse:
    """Summary:
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

        500 Internal Server Error: None
            Returned if a storage-level error occurs.

    Notes:
        - This operation will create or update the member's access.
        - Emits the event: `campus.circles.members.set`.
        - No validation is currently performed to compare existing access.
    """
    resources.circle.members.set(
        schema.CampusID(circle_id),
        member_id=schema.CampusID(member_id),
        access_value=access_value
    )
    yapper.emit('campus.circles.members.set', {"circle_id": circle_id, "member_id": member_id})
    return {}, 200


@bp.get('/<string:circle_id>/users')
def get_circle_users(circle_id: str) -> flask_campus.JsonResponse:
    # TODO: validate request
    """Get users in a circle."""
    return {"message": "Not implemented"}, 501
