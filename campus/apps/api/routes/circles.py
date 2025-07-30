"""campus.apps.api.routes.circles

API routes for the circles resource.
"""

from flask import Blueprint, Flask

import campus.common.validation.flask as flask_validation
from campus.apps.campusauth import authenticate_client
from campus.common.errors import api_errors
from campus.models import circle

bp = Blueprint('circles', __name__, url_prefix='/circles')
bp.before_request(authenticate_client)

# Database Models
circles = circle.Circle()
# users = user.User()


def init_app(app: Flask | Blueprint) -> None:
    """Initialise circle routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.post('/')
def new_circle(*_: str) -> flask_validation.JsonResponse:
    """Create a new circle."""
    payload = flask_validation.validate_request_and_extract_json(
        circle.CircleNew.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    resource = circles.new(**payload)
    flask_validation.validate_json_response(
        circle.CircleResource.__annotations__,
        resource,
        on_error=api_errors.raise_api_error,
    )
    return dict(resource), 201

@bp.delete('/<string:circle_id>')
def delete_circle(circle_id: str) -> flask_validation.JsonResponse:
    """Delete a circle."""
    circles.delete(circle_id)
    return {}, 200

@bp.get('/<string:circle_id>')
def get_circle_details(circle_id: str) -> flask_validation.JsonResponse:
    """Get details of a circle."""
    resource = circles.get(circle_id)
    flask_validation.validate_json_response(
        circle.CircleResource.__annotations__,
        resource,
        on_error=api_errors.raise_api_error,
    )
    return dict(resource), 200

@bp.patch('/<string:circle_id>')
def edit_circle(circle_id: str) -> flask_validation.JsonResponse:
    """Edit name or description of a circle."""
    params = flask_validation.validate_request_and_extract_json(
        circle.CircleUpdate.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    circles.update(circle_id, **params)
    return {}, 200

@bp.post('/<string:circle_id>/move')
def move_circle(circle_id: str) -> flask_validation.JsonResponse:
    """Move a circle to a new parent."""
    return {"message": "Not implemented"}, 501

@bp.get('/<string:circle_id>/members')
def get_circle_members(circle_id: str) -> flask_validation.JsonResponse:
    """Get member IDs of a circle and their access values."""
    resource = circles.members.list(circle_id)
    # TODO: validate response
    return resource, 200

@bp.post('/<string:circle_id>/members/add')
def add_circle_member(circle_id: str) -> flask_validation.JsonResponse:
    """Add a member to a circle."""
    params = flask_validation.validate_request_and_extract_json(
        circle.CircleMemberAdd.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    circles.members.add(circle_id, **params)
    return {}, 200

@bp.delete('/<string:circle_id>/members/remove')
def remove_circle_member(circle_id: str) -> flask_validation.JsonResponse:
    """Remove a member from a circle."""
    params = flask_validation.validate_request_and_extract_json(
        circle.CircleMemberRemove.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    circles.members.remove(circle_id, **params)
    # TODO: validate response
    return {}, 200

# TODO: Redesign for clearer access update: circles can have multiple parentage paths
@bp.patch('/<string:circle_id>/members/<string:member_circle_id>')
def patch_circle_member(circle_id: str) -> flask_validation.JsonResponse:
    """Update a member's access in a circle."""
    params = flask_validation.validate_request_and_extract_json(
        circle.CircleMemberSet.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    circles.members.set(circle_id, **params)
    # TODO: validate response
    return {}, 200

@bp.get('/<string:circle_id>/users')
def get_circle_users(circle_id: str) -> flask_validation.JsonResponse:
    # TODO: validate request
    """Get users in a circle."""
    return {"message": "Not implemented"}, 501
