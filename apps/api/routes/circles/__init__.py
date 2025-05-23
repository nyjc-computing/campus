"""apps/api/routes/circles

API routes for the circles resource.
"""

from typing import Unpack

from flask import Blueprint, Flask

from apps.api.models import circle, user
from apps.common.errors import api_errors
from common.auth import authenticate_client
from common.validation.flask import FlaskResponse, unpack_request, validate

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
@unpack_request
@validate(
    request=circle.CircleNew.__annotations__,
    response=circle.CircleResource.__annotations__,
    on_error=api_errors.raise_api_error
)
def new_circle(*_: str, **data: Unpack[circle.CircleNew]) -> FlaskResponse:  # *_ appease linter
    """Create a new circle."""
    # TODO: authenticate
    resp = circles.new(**data)  # raises APIError
    return resp.data, 201

@bp.delete('/<string:circle_id>')
@validate(
    response={"message": str},
    on_error=api_errors.raise_api_error
)
def delete_circle(circle_id: str, *_, **__) -> FlaskResponse:  # *_ appease linter
    """Delete a circle."""
    resp = circles.delete(circle_id)  # raises APIError
    return {"message": "Circle deleted"}, 200

@bp.get('/<string:circle_id>')
@validate(
    response=circle.CircleResource.__annotations__,
    on_error=api_errors.raise_api_error
)
def get_circle_details(circle_id: str, *_, **__) -> FlaskResponse:  # *_ appease linter
    """Get details of a circle."""
    # TODO: validate, authenticate
    resp = circles.get(circle_id)  # raises APIError
    return resp.data, 200

@bp.patch('/<string:circle_id>')
@unpack_request
@validate(
    request=circle.CircleUpdate.__annotations__,
    response=circle.CircleResource.__annotations__,
    on_error=api_errors.raise_api_error
)
def edit_circle(circle_id: str, *_, **data: Unpack[circle.CircleUpdate]) -> FlaskResponse:  # *_ appease linter
    """Edit name or description of a circle."""
    # TODO: authenticate
    resp = circles.update(circle_id, **data)  # raises APIError
    return resp.data, 200
