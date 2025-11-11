"""campus.common.errors

API error handling for Campus.
"""

import werkzeug.exceptions
import flask
import logging
import sys
import traceback

from campus.common.utils import url

from .base import JsonDict
from . import api_errors, auth_errors, token_errors

logger = logging.getLogger(__name__)


def get_caller() -> str:
    """Return the filename of the module where the exception was raised."""
    tb = sys.exc_info()[2]
    if tb:
        frames = traceback.extract_tb(tb)
        if frames:
            return frames[-1].filename
    return "unknown"


def handle_authorization_error(
        err: auth_errors.AuthorizationError
) -> werkzeug.Response:
    """Handle OAuth authorization request errors.

    This function is used to handle OAuth errors and return
    standardised JSON responses.
    """
    module = get_caller()
    logger.exception("OAuthError in %s: %s", module, err)
    err_dict = err.to_dict()
    from campus.common import devops
    # Remove details and traceback in production for security reasons
    if devops.ENV == devops.PRODUCTION:
        del err_dict["details"]
        del err_dict["traceback"]
    return flask.redirect(
        url.with_params(
            err.redirect_uri or flask.request.base_url,
            **err_dict
        )
    )

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
        err_dict.pop("traceback")
    return err_dict, err.status_code


def handle_token_error(
        err: token_errors.TokenError
) -> tuple[JsonDict, int]:
    """Handle OAuth token request errors.

    This function is used to handle Token errors and return
    standardised JSON responses.
    """
    module = get_caller()
    logger.exception("TokenError in %s: %s", module, err)
    err_dict = err.to_dict()
    from campus.common import devops
    # Remove details and traceback in production for security reasons
    if devops.ENV == devops.PRODUCTION:
        del err_dict["details"]
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


def handle_generic_error(err: Exception) -> tuple[JsonDict, int]:
    """Handle generic exceptions.

    This is the fallback handler for any unhandled exceptions.
    """
    # Generic exception handler
    module = get_caller()
    logger.exception(
        "Unhandled exception in %s: %s", module, err
    )
    internal_err = api_errors.InternalError.from_exception(err)
    return internal_err.to_dict(), internal_err.status_code


def init_app(app: flask.Flask) -> None:
    """Initialise the error handling for the app.

    This function is used to register the error handlers for the app.
    """
    app.register_error_handler(
        auth_errors.AuthorizationError, handle_authorization_error
    )
    app.register_error_handler(
        api_errors.APIError, handle_api_error
    )
    app.register_error_handler(
        token_errors.TokenError, handle_token_error
    )
    app.register_error_handler(
        werkzeug.exceptions.HTTPException, handle_werkzeug_error
    )
    app.register_error_handler(Exception, handle_generic_error)
