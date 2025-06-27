"""apps/api/routes/oauth

Routes for external integration authentication - google, github, discord, etc.
"""

from typing import Unpack

from flask import Blueprint, Flask

from apps.common.errors import api_errors
from common.validation.flask import FlaskResponse, unpack_request, validate

bp = Blueprint('auth', __name__, url_prefix='/oauth')


def init_app(app: Flask | Blueprint) -> None:
    """Initialise auth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


## Integration authentication routes

@bp.post('/google/callback')
@unpack_request
@validate(
    request=GoogleCallback.__annotations__,
    response={"message": str},
    on_error=api_errors.raise_api_error
)
def google_callback(*_, **data: Unpack[GoogleCallback]) -> FlaskResponse:
    """Handle a Google OAuth callback request."""
    return {"message": "Not implemented"}, 501


# TODO: github
# TODO: discord
