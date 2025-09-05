"""campus.common.errors

API error handling for Campus.
"""


import logging
import sys
import traceback

from werkzeug.exceptions import HTTPException, InternalServerError

from .base import APIError, JsonDict
from . import api_errors


def get_caller() -> str:
    """Return the filename of the module where the exception was raised."""
    tb = sys.exc_info()[2]
    if tb:
        frames = traceback.extract_tb(tb)
        if frames:
            return frames[-1].filename
    return "unknown"


def handle_api_error(err: APIError) -> tuple[JsonDict, int]:
    """Handle API errors.

    This function is used to handle API errors and return
    standardised JSON responses.
    """
    module = get_caller()
    logging.getLogger("campus.common.errors").exception(
        "APIError in %s: %s", module, err
    )
    err_dict = err.to_dict()
    from campus.common import devops
    # Remove traceback in production for security reasons
    if devops.ENV == devops.PRODUCTION:
        del err_dict["traceback"]
    return err_dict, err.status_code


def handle_werkzeug_error(err: HTTPException) -> tuple[JsonDict, int]:
    """Handle werkzeug errors.

    This function is used to handle werkzeug errors and return
    standardised JSON responses.

    Reference: https://flask.palletsprojects.com/en/stable/errorhandling/
    """
    module = get_caller()
    logging.getLogger("campus.common.errors").exception(
        "Werkzeug HTTPException in %s: %s", module, err
    )
    match err:
        case InternalServerError():
            return api_errors.InternalError().to_dict(), 500
        case _:
            raise err


def init_app(app):
    """Initialise the error handling for the app.

    This function is used to register the error handlers for the app.
    """
    app.register_error_handler(HTTPException, handle_werkzeug_error)
    app.register_error_handler(APIError, handle_api_error)
