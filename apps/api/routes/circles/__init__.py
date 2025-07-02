"""apps.api.routes.circles

API routes for the circles resource.
"""

from typing import Unpack

from flask import Blueprint, Flask

from apps.campusauth.model import authenticate_client
from apps.common.errors import api_errors
from apps.common.models import circle
from common.validation.flask import FlaskResponse, unpack_request_json, validate

bp = Blueprint('circles', __name__, url_prefix='/circles')
bp.before_request(authenticate_client)

# Database Models
circles = circle.Circle()
# users = user.User()


def init_app(app: Flask | Blueprint) -> None:
    """Initialise circle routes with the given Flask app/blueprint."""
    circle.init_db()
    app.register_blueprint(bp)


@bp.post('/')
@unpack_request_json
@validate(
    request=circle.CircleNew.__annotations__,
    response=circle.CircleResource.__annotations__,
    on_error=api_errors.raise_api_error
)
def new_circle(*_: str, **data: Unpack[circle.CircleNew]) -> FlaskResponse:
    """Create a new circle."""
    # TODO: authenticate
    resp = circles.new(**data)  # raises APIError
    return resp.data, 201

@bp.delete('/<string:circle_id>')
@validate(
    response={"message": str},
    on_error=api_errors.raise_api_error
)
def delete_circle(circle_id: str, *_, **__) -> FlaskResponse:
    """Delete a circle."""
    resp = circles.delete(circle_id)  # raises APIError
    return {"message": "Circle deleted"}, 200

@bp.get('/<string:circle_id>')
@validate(
    response=circle.CircleResource.__annotations__,
    on_error=api_errors.raise_api_error
)
def get_circle_details(circle_id: str, *_, **__) -> FlaskResponse:
    """Get details of a circle."""
    # TODO: validate, authenticate
    resp = circles.get(circle_id)  # raises APIError
    return resp.data, 200

@bp.patch('/<string:circle_id>')
@unpack_request_json
@validate(
    request=circle.CircleUpdate.__annotations__,
    response=circle.CircleResource.__annotations__,
    on_error=api_errors.raise_api_error
)
def edit_circle(
        circle_id: str,
        *_,
        **data: Unpack[circle.CircleUpdate]
) -> FlaskResponse:
    """Edit name or description of a circle."""
    # TODO: authenticate
    resp = circles.update(circle_id, **data)  # raises APIError
    return resp.data, 200

@bp.post('/<string:circle_id>/move')
def move_circle(circle_id: str, *_, **__) -> FlaskResponse:
    """Move a circle to a new parent."""
    return {"message": "Not implemented"}, 501

@bp.get('/<string:circle_id>/members')
def get_circle_members(circle_id: str, *_, **__) -> FlaskResponse:
    """Get member IDs of a circle and their access values."""
    resp = circles.members.list(circle_id)  # raises APIError
    return resp.data, 200

@bp.post('/<string:circle_id>/members/add')
@validate(
    request=circle.CircleMemberAdd.__annotations__,
    on_error=api_errors.raise_api_error
)
def add_circle_member(
        circle_id: str,
        *_,
        **data: Unpack[circle.CircleMemberAdd]
) -> FlaskResponse:
    """Add a member to a circle."""
    resp = circles.members.add(circle_id, **data)
    return resp.data, 200

@bp.delete('/<string:circle_id>/members/remove')
@validate(
    request=circle.CircleMemberRemove.__annotations__,
    on_error=api_errors.raise_api_error
)
def remove_circle_member(
        circle_id: str,
        *_,
        **data: Unpack[circle.CircleMemberRemove]
) -> FlaskResponse:
    """Remove a member from a circle."""
    resp = circles.members.remove(circle_id, **data)
    return resp.data, 200

# TODO: Redesign for clearer access update: circles can have multiple parentage paths
@bp.patch('/<string:circle_id>/members/<string:member_circle_id>')
@validate(
    request=circle.CircleMemberSet.__annotations__,
    on_error=api_errors.raise_api_error
)
def patch_circle_member(
        circle_id: str,
        *_,
        **data: Unpack[circle.CircleMemberSet]
) -> FlaskResponse:
    """Update a member's access in a circle."""
    resp = circles.members.set(circle_id, **data)
    return resp.data, 200

@bp.get('/<string:circle_id>/users')
def get_circle_users(circle_id: str, *_, **data) -> FlaskResponse:
    """Get users in a circle."""
    return {"message": "Not implemented"}, 501
