"""campus.common.errors

API error handling for Campus.
"""

import logging
import sys
import traceback

logger = logging.getLogger(__name__)

from flask import Flask
import werkzeug.exceptions

from .base import JsonDict
from . import api_errors


def get_caller() -> str:
    """Return the filename of the module where the exception was raised."""
    tb = sys.exc_info()[2]
    if tb:
        frames = traceback.extract_tb(tb)
        if frames:
            return frames[-1].filename
    return "unknown"


def handle_api_error(err: api_errors.APIError) -> tuple[JsonDict, int]:
    """Handle API errors.

    This function is used to handle API errors and return
    standardised JSON responses.
    """
    module = get_caller()
    logger.exception("APIError in %s: %s", module, err)
    err_dict = err.to_dict()
    from campus.common import devops
    # Remove traceback in production for security reasons
    if devops.ENV == devops.PRODUCTION:
        del err_dict["traceback"]
    return err_dict, err.status_code


def handle_werkzeug_error(
        err: werkzeug.exceptions.HTTPException
) -> tuple[JsonDict, int]:
    """Handle werkzeug errors.

    This function is used to handle werkzeug errors and return
    standardised JSON responses.

    Reference: https://flask.palletsprojects.com/en/stable/errorhandling/
    """
    module = get_caller()
    match err:
        case werkzeug.exceptions.NotFound():
            return {}, 404  # ignore 404 errors; too numerous
        case werkzeug.exceptions.InternalServerError():
            logger.exception("InternalServerError in %s: %s", module, err)
            return api_errors.InternalError().to_dict(), 500
        case _:
            raise err


def init_app(app: Flask) -> None:
    """Initialise the error handling for the app.

    This function is used to register the error handlers for the app.
    """
    app.register_error_handler(
        werkzeug.exceptions.HTTPException, handle_werkzeug_error
    )
    app.register_error_handler(api_errors.APIError, handle_api_error)
