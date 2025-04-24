"""apps.palmtree.errors

API error handling for Palmtree.
"""

from werkzeug.exceptions import HTTPException, InternalServerError

from .base import APIError, JsonDict
from .api_errors import InvalidRequestError


def handle_api_error(err: APIError) -> tuple[JsonDict, int]:
    """Handle API errors.

    This function is used to handle API errors and return
    standardised JSON responses.
    """
    return err.to_dict(), err.status_code


def handle_werkzeug_error(err: HTTPException) -> tuple[JsonDict, int]:
    """Handle werkzeug errors.

    This function is used to handle werkzeug errors and return
    standardised JSON responses.

    Reference: https://flask.palletsprojects.com/en/stable/errorhandling/
    """
    match err:
        case InternalServerError():
            return InvalidRequestError().to_dict(), 500
        case _:
            raise err


def init_app(app):
    """Initialise the error handling for the app.

    This function is used to register the error handlers for the app.
    """
    app.register_error_handler(HTTPException, handle_werkzeug_error)
    app.register_error_handler(APIError, handle_api_error)

