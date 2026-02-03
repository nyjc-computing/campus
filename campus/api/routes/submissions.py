"""campus.api.routes.submissions

API routes for the submissions resource.
"""

from dataclasses import asdict

import flask

import campus.model
import campus.yapper
from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import resources

bp = flask.Blueprint('submissions', __name__, url_prefix='/submissions')

# Lazily initialized yapper - set in init_app() after test fixtures are ready
# This prevents connection to external services during module import in tests
# Type: ignore because we initialize this in init_app() before first use
yapper: campus.yapper.YapperInterface = None  # type: ignore


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise submission routes with the given Flask app/blueprint."""
    global yapper
    # Initialize yapper after test fixtures have set up the vault
    yapper = campus.yapper.create()
    app.register_blueprint(bp)


@bp.get('/')
@flask_campus.unpack_request
def list_submissions(
    assignment_id: str | None = None,
    student_id: str | None = None,
    course_id: str | None = None,
) -> flask_campus.JsonResponse:
    """Summary:
        List all submissions matching filter requirements.

    Method:
        GET /submissions

    Query Parameters:
        assignment_id: str (optional)
            Filter by assignment
        student_id: str (optional)
            Filter by student
        course_id: str (optional)
            Filter by Google Classroom course

    Responses:
        200 OK: dict
            {"data": [submission resources]}
    """
    filters = {}
    if assignment_id:
        filters['assignment_id'] = assignment_id
    if student_id:
        filters['student_id'] = student_id
    if course_id:
        filters['course_id'] = course_id

    result = resources.submission.list(**filters)
    return {"data": [submission.to_resource() for submission in result]}, 200


@bp.post('/')
@flask_campus.unpack_request
def create_submission(
    assignment_id: str,
    student_id: str,
    course_id: str,
    responses: list[dict] | None = None,
) -> flask_campus.JsonResponse:
    """Summary:
        Create a new submission.

    Method:
        POST /submissions

    Request Body:
        assignment_id: str (required)
        student_id: str (required)
        course_id: str (required)
        responses: list[dict] (optional)

    Responses:
        201 Created: dict
            Submission resource
    """
    submission = resources.submission.new(
        assignment_id=assignment_id,
        student_id=student_id,
        course_id=course_id,
        responses=responses or []
    )
    resource = submission.to_resource()
    yapper.emit('campus.submissions.create', {'submission_id': submission.id})
    return resource, 201


@bp.get('/by-assignment/<string:assignment_id>')
def list_submissions_by_assignment(
    assignment_id: str,
) -> flask_campus.JsonResponse:
    """Summary:
        List submissions for a specific assignment.

    Method:
        GET /submissions/by-assignment/{assignment_id}

    Responses:
        200 OK: dict
            {"data": [submission resources]}
    """
    result = resources.submission.list(assignment_id=assignment_id)
    return {"data": [submission.to_resource() for submission in result]}, 200


@bp.get('/by-student/<string:student_id>')
def list_submissions_by_student(
    student_id: str,
) -> flask_campus.JsonResponse:
    """Summary:
        List submissions from a specific student.

    Method:
        GET /submissions/by-student/{student_id}

    Responses:
        200 OK: dict
            {"data": [submission resources]}
    """
    result = resources.submission.list(student_id=student_id)
    return {"data": [submission.to_resource() for submission in result]}, 200


@bp.get('/<string:submission_id>')
def get_submission(submission_id: str) -> flask_campus.JsonResponse:
    """Summary:
        Get a single submission by ID.

    Method:
        GET /submissions/{submission_id}

    Responses:
        200 OK: dict
            Submission resource
    """
    submission = resources.submission[schema.CampusID(submission_id)].get()
    return submission.to_resource(), 200


@bp.patch('/<string:submission_id>')
@flask_campus.unpack_request
def update_submission(
    *,
    submission_id: str,
    responses: list[dict] | None = None,
    feedback: list[dict] | None = None,
    submitted_at: str | None = None,
) -> flask_campus.JsonResponse:
    """Summary:
        Update a submission.

    Method:
        PATCH /submissions/{submission_id}

    Request Body:
        responses, feedback, or submitted_at (all optional)

    Responses:
        200 OK: dict
            Empty object on success
    """
    updates = {}
    if responses is not None:
        # Convert dict responses to Response models
        updates["responses"] = [
            campus.model.Response(**r) for r in responses
        ]
    if feedback is not None:
        # Convert dict feedback to Feedback models
        updates["feedback"] = [
            campus.model.Feedback(**f) for f in feedback
        ]
    if submitted_at is not None:
        updates["submitted_at"] = schema.DateTime(submitted_at)

    if not updates:
        raise api_errors.InvalidRequestError("Empty request body")

    resources.submission[schema.CampusID(submission_id)].update(**updates)
    yapper.emit('campus.submissions.update', {"submission_id": submission_id})
    return {}, 200


@bp.delete('/<string:submission_id>')
def delete_submission(submission_id: str) -> flask_campus.JsonResponse:
    """Summary:
        Delete a submission.

    Method:
        DELETE /submissions/{submission_id}

    Responses:
        200 OK: dict
            Empty object on success
    """
    resources.submission[schema.CampusID(submission_id)].delete()
    yapper.emit('campus.submissions.delete', {"submission_id": submission_id})
    return {}, 200


@bp.post('/<string:submission_id>/responses')
@flask_campus.unpack_request
def add_response(
    *,
    submission_id: str,
    question_id: str,
    response_text: str,
) -> flask_campus.JsonResponse:
    """Summary:
        Add or update a response to a question in a submission.

    Method:
        POST /submissions/{submission_id}/responses

    Request Body:
        question_id: str (required)
        response_text: str (required)

    Responses:
        200 OK: dict
            Empty object on success
    """
    submission = resources.submission[schema.CampusID(submission_id)].get()

    # Check if response to this question already exists
    existing_index = None
    for i, r in enumerate(submission.responses):
        if r.question_id == question_id:
            existing_index = i
            break

    new_response = campus.model.Response(
        question_id=question_id,
        response_text=response_text
    )

    if existing_index is not None:
        submission.responses[existing_index] = new_response
    else:
        submission.responses.append(new_response)

    # Convert to dict for storage
    responses_dict = [asdict(r) for r in submission.responses]
    resources.submission[schema.CampusID(submission_id)].update(
        responses=responses_dict,
        updated_at=schema.DateTime.utcnow()
    )
    yapper.emit('campus.submissions.response_add',
                {"submission_id": submission_id})
    return {}, 200


@bp.post('/<string:submission_id>/feedback')
@flask_campus.unpack_request
def add_feedback(
    *,
    submission_id: str,
    question_id: str,
    feedback_text: str,
) -> flask_campus.JsonResponse:
    """Summary:
        Add feedback on a response to a question.

    Method:
        POST /submissions/{submission_id}/feedback

    Request Body:
        question_id: str (required)
        feedback_text: str (required)

    Responses:
        200 OK: dict
            Empty object on success
    """
    # Get teacher_id from authenticated user
    current_user = flask.g.get('current_user')
    if not current_user or not getattr(current_user, 'id', None):
        raise api_errors.UnauthorizedError(
            "User must be authenticated to add feedback"
        )
    teacher_id = current_user.id

    submission = resources.submission[schema.CampusID(submission_id)].get()

    # Check if feedback for this question already exists
    existing_index = None
    for i, f in enumerate(submission.feedback):
        if f.question_id == question_id:
            existing_index = i
            break

    new_feedback = campus.model.Feedback(
        question_id=question_id,
        feedback_text=feedback_text,
        teacher_id=schema.UserID(teacher_id)
    )

    if existing_index is not None:
        submission.feedback[existing_index] = new_feedback
    else:
        submission.feedback.append(new_feedback)

    # Convert to dict for storage
    feedback_dict = [asdict(f) for f in submission.feedback]
    resources.submission[schema.CampusID(submission_id)].update(
        feedback=feedback_dict,
        updated_at=schema.DateTime.utcnow()
    )
    yapper.emit('campus.submissions.feedback_add',
                {"submission_id": submission_id})
    return {}, 200


@bp.post('/<string:submission_id>/submit')
@flask_campus.unpack_request
def submit_submission(submission_id: str) -> flask_campus.JsonResponse:
    """Summary:
        Finalize/submit a submission (mark submitted_at timestamp).

    Method:
        POST /submissions/{submission_id}/submit

    Responses:
        200 OK: dict
            Empty object on success
    """
    submission = resources.submission[schema.CampusID(submission_id)].get()

    if submission.submitted_at is not None:
        raise api_errors.InvalidRequestError(
            "Submission has already been submitted"
        )

    resources.submission[schema.CampusID(submission_id)].update(
        submitted_at=schema.DateTime.utcnow()
    )
    yapper.emit('campus.submissions.submit', {"submission_id": submission_id})
    return {}, 200
