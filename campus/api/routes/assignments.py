"""campus.api.routes.assignments

API routes for the assignments resource.
"""

from dataclasses import asdict

import flask

import campus.model
import campus.yapper
from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import resources

bp = flask.Blueprint('assignments', __name__, url_prefix='/assignments')

# Lazily initialized yapper - set in init_app() after test fixtures are ready
# This prevents connection to external services during module import in tests
yapper: campus.yapper.YapperInterface | None = None


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise assignment routes with the given Flask app/blueprint."""
    global yapper
    # Initialize yapper after test fixtures have set up the vault
    yapper = campus.yapper.create()
    app.register_blueprint(bp)


@bp.get('/')
@flask_campus.unpack_request
def list_assignments(created_by: str | None = None) -> flask_campus.JsonResponse:
    """Summary:
        List all assignments matching filter requirements.

    Method:
        GET /assignments

    Query Parameters:
        created_by: str (optional)
            Filter by teacher who created the assignment

    Responses:
        200 OK: dict
            {"data": [assignment resources]}
    """
    filters = {}
    if created_by:
        filters['created_by'] = created_by

    result = resources.assignment.list(**filters)
    return {"data": [assignment.to_resource() for assignment in result]}, 200


@bp.post('/')
@flask_campus.unpack_request
def create_assignment(
    title: str,
    description: str = "",
    questions: list[dict] | None = None,
    classroom_links: list[dict] | None = None,
) -> flask_campus.JsonResponse:
    """Summary:
        Create a new assignment.

    Method:
        POST /assignments

    Request Body:
        title: str (required)
        description: str (optional)
        questions: list[dict] (optional)
        classroom_links: list[dict] (optional)

    Responses:
        201 Created: dict
            Assignment resource
    """
    # Get created_by from authenticated user
    current_user = flask.g.get('current_user')
    if not current_user or not current_user.get('id'):
        raise api_errors.UnauthorizedError(
            "User must be authenticated to create assignments"
        )
    created_by = current_user.get('id')

    assignment = resources.assignment.new(
        title=title,
        description=description,
        questions=questions or [],
        created_by=created_by,
        classroom_links=classroom_links or []
    )
    resource = assignment.to_resource()
    yapper.emit('campus.assignments.create', {'assignment_id': assignment.id})
    return resource, 201


@bp.get('/<string:assignment_id>')
def get_assignment(assignment_id: str) -> flask_campus.JsonResponse:
    """Summary:
        Get a single assignment by ID.

    Method:
        GET /assignments/{assignment_id}

    Responses:
        200 OK: dict
            Assignment resource
    """
    assignment = resources.assignment[schema.CampusID(assignment_id)].get()
    return assignment.to_resource(), 200


@bp.patch('/<string:assignment_id>')
@flask_campus.unpack_request
def update_assignment(
    *,
    assignment_id: str,
    title: str | None = None,
    description: str | None = None,
    questions: list[dict] | None = None,
    classroom_links: list[dict] | None = None,
) -> flask_campus.JsonResponse:
    """Summary:
        Update an assignment.

    Method:
        PATCH /assignments/{assignment_id}

    Request Body:
        title, description, questions, or classroom_links (all optional)

    Responses:
        200 OK: dict
            Empty object on success
    """
    updates = {}
    if title is not None:
        updates["title"] = title
    if description is not None:
        updates["description"] = description
    if questions is not None:
        # Convert dict questions to Question models
        updates["questions"] = [
            campus.model.Question(**q) for q in questions
        ]
    if classroom_links is not None:
        # Convert dict links to ClassroomLink models
        updates["classroom_links"] = [
            campus.model.ClassroomLink(**l) for l in classroom_links
        ]

    if not updates:
        raise api_errors.InvalidRequestError("Empty request body")

    resources.assignment[schema.CampusID(assignment_id)].update(**updates)
    yapper.emit('campus.assignments.update', {"assignment_id": assignment_id})
    return {}, 200


@bp.delete('/<string:assignment_id>')
def delete_assignment(assignment_id: str) -> flask_campus.JsonResponse:
    """Summary:
        Delete an assignment.

    Method:
        DELETE /assignments/{assignment_id}

    Responses:
        200 OK: dict
        Empty object on success
    """
    resources.assignment[schema.CampusID(assignment_id)].delete()
    yapper.emit('campus.assignments.delete', {"assignment_id": assignment_id})
    return {}, 200


@bp.post('/<string:assignment_id>/links')
@flask_campus.unpack_request
def add_classroom_link(
    *,
    assignment_id: str,
    course_id: str,
    coursework_id: str,
    attachment_id: str | None = None,
) -> flask_campus.JsonResponse:
    """Summary:
        Add a Google Classroom link to an assignment.

    Method:
        POST /assignments/{assignment_id}/links

    Request Body:
        course_id: str (required)
        coursework_id: str (required)
        attachment_id: str (optional)

    Responses:
        200 OK: dict
        Empty object on success
    """
    assignment = resources.assignment[schema.CampusID(assignment_id)].get()
    new_link = campus.model.ClassroomLink(
        course_id=course_id,
        coursework_id=coursework_id,
        attachment_id=attachment_id
    )
    assignment.classroom_links.append(new_link)

    # Convert to dict for storage
    links_dict = [asdict(l) for l in assignment.classroom_links]
    resources.assignment[schema.CampusID(assignment_id)].update(
        classroom_links=links_dict
    )
    yapper.emit('campus.assignments.link', {"assignment_id": assignment_id})
    return {}, 200
