"""campus.apps.api.routes.users

API routes for the users resource.
"""

from flask import Blueprint, Flask

import campus_yapper

import campus.common.validation.flask as flask_validation
from campus.apps.campusauth import authenticate_client
from campus.common.errors import api_errors
from campus.models import user

bp = Blueprint('users', __name__, url_prefix='/users')
bp.before_request(authenticate_client)

users = user.User()
yapper = campus_yapper.create()


def init_app(app: Flask | Blueprint) -> None:
    """Summary:
        Initialize and register all user-related routes with the given Flask app or blueprint.

    Method:
        None

    Parameters:
        app: Flask | Blueprint (required)
            The Flask application/blueprint to which the user routes should be registered in.

    Path Parameters:
        None

    Query Parameters:
        None

    Request Body:
        None

    Responses:
        None
    """
    app.register_blueprint(bp)
    app.add_url_rule('/me', 'get_authenticated_user', get_authenticated_user)


# This view function is not registered with the blueprint
# It will be registered with the app in the init_app function
def get_authenticated_user():
    """Summary:
        Retrieve the currently authenticated user's summary.

    Method:
        GET /me

    Path Parameters:
        None

    Query Parameters:
        None

    Request Body:
        None

    Responses:
        501 Not Implemented: dict
            Returned because this function is not yet implemented:
            {
                "message": "not implemented"
            }
    """
    # TODO: Get user id from auth token
    return {"message": "not implemented"}, 501


@bp.get('/')
def list_users() -> flask_validation.JsonResponse:
    """List all users (not yet implemented)."""
    return {"message": "List users not implemented"}, 501


@bp.post('/')
def new_user() -> flask_validation.JsonResponse:
    """Summary:
        Create a new user in the system.

    Method:
        POST

    Parameters:
        None

    Query Parameters:
        None

    Request Body (application/json):
        "email": str,  # required, must be unique
        "name": str    # required

    Responses:
        201 Created:
            Returns a `UserResource` object representing the newly created user:
            {
                "id": str,
                "email": str,
                "name": str,
                "created_at": str,
                "activated_at": str | null  # may not be activated yet
            }

        400 Bad Request:
            Invalid request body or missing required fields:
            {
                "error": str
            }

        409 Conflict:
            User with the same email already exists:
            {
                "error": str
            }

        500 Internal Server Error:
            Unexpected errors during creation:
            {
                "error": str
            }
    """
    payload = flask_validation.validate_request_and_extract_json(
        user.UserNew.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    resource = users.new(**payload)
    flask_validation.validate_json_response(
        user.UserResourceDict.__annotations__,
        resource,
        on_error=api_errors.raise_api_error,
    )
    yapper.emit('campus.users.new')
    return dict(resource), 201


@bp.delete('/<string:user_id>')
def delete_user(user_id: str) -> flask_validation.JsonResponse:
    """Summary:
        Delete a user by their unique ID.

    Method:
        DELETE /<user_id>

    Path Parameters:
        user_id: str (required)
            The unique identifier of the user to delete.

    Query Parameters:
        None

    Request Body:
        None

    Responses:
        200 OK: dict
            Empty JSON object indicating successful deletion:
            {}

        404 Not Found: dict
            Returned if no user exists with the given ID:
            {
                "error": str
            }

        500 Internal Server Error: dict
            Unexpected server error during deletion:
            {
                "error": str
            }
    """
    users.delete(user_id)
    yapper.emit('campus.users.delete')
    return {}, 200


@bp.get('/<string:user_id>')
def get_user(user_id: str) -> flask_validation.JsonResponse:
    """Summary:
        Retrieve a single user's summary by their unique ID.

    Method:
        GET /<user_id>

    Path Parameters:
        user_id: str (required)
            The unique identifier of the user.

    Query Parameters:
        None

    Request Body:
        None

    Responses:
        200 OK: dict
            JSON object containing the user's profile summary.
            Example:
                {
                    "profile": {
                        "id": str,
                        "email": str,
                        "name": str,
                        "created_at": str,
                        "activated_at": str | None
                    }
                }

        404 Not Found: dict
            Returned if no user exists with the given ID:
            {
                "error": str
            }

        500 Internal Server Error: dict
            Unexpected server error while retrieving the user:
            {
                "error": str
            }
    """
    summary = {}
    record, _ = get_user_profile(user_id)
    summary['profile'] = record
    flask_validation.validate_json_response(
        summary,
        user.UserResourceDict.__annotations__,
        on_error = api_errors.raise_api_error
    )
    # future calls for other user info go here
    return summary, 200


@ bp.patch('/<string:user_id>')
def patch_user_profile(user_id: str) -> flask_validation.JsonResponse:
    """Summary:
        Update a single user's profile by their unique ID.

    Method:
        PATCH /<user_id>

    Path Parameters:
        user_id: str (required)
            The unique identifier of the user to update.

    Query Parameters:
        None

    Request Body:
        JSON object matching the UserUpdate schema:
            {
                # Currently empty, can include optional fields to update in the future
            }

    Responses:
        200 OK: dict
            Empty JSON object indicating the update was successful:
            {}

        400 Bad Request: dict
            Returned if the request body is invalid or contains unsupported fields:
            {
                "error": str
            }

        404 Not Found: dict
            Returned if no user exists with the given ID:
            {
                "error": str
            }

        500 Internal Server Error: dict
            Unexpected server error during the update:
            {
                "error": str
            }
    """
    payload = flask_validation.validate_request_and_extract_json(
        user.UserUpdate.__annotations__,
        on_error = api_errors.raise_api_error,
    )
    users.update(user_id, **payload)
    yapper.emit('campus.users.update')
    return {}, 200


@ bp.get('/<string:user_id>/profile')
def get_user_profile(user_id: str) -> flask_validation.JsonResponse:
    """Summary:
        Retrieve a single user's full profile by their unique ID.

    Method:
        GET /<user_id>/profile

    Path Parameters:
        user_id: str (required)
            The unique identifier of the user.

    Query Parameters:
        None

    Request Body:
        None

    Responses:
        200 OK: dict
            JSON object containing the user's full profile.
            Example:
                {
                    "id": str,
                    "email": str,
                    "name": str,
                    "created_at": str,
                    "activated_at": str | None
                }

        404 Not Found: dict
            Returned if no user exists with the given ID:
            {
                "error": str
            }

        500 Internal Server Error: dict
            Unexpected server error while retrieving the user:
            {
                "error": str
            }
    """
    resource= users.get(user_id)
    flask_validation.validate_json_response(
        user.UserResourceDict.__annotations__,
        resource,
        on_error = api_errors.raise_api_error,
    )
    return dict(resource), 200
