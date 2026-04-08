"""campus.common.errors.handlers

Error handler functions for Flask error handling.
"""

import sys
import traceback
import logging
import werkzeug.exceptions
import flask

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
) -> werkzeug.Response | tuple[JsonDict, int]:
    """Handle OAuth authorization request errors.

    This function handles OAuth errors and returns appropriate responses:
    - For API requests (JSON Accept header or /auth/v1/* paths): JSON error
    - For OAuth browser flows: HTTP redirect (RFC 6749)

    In development mode, raises BadRequest for ambiguous requests.
    """
    module = get_caller()
    # Only log tracebacks for 5xx errors; 4xx are client errors and don't need tracebacks
    if 500 <= err.status_code < 600:
        logger.exception("OAuthError in %s: %s", module, err)
    else:
        logger.info("OAuthError in %s: %s", module, err)

    # Determine if this is an API request (expects JSON) or OAuth browser flow (expects redirect)
    accept_header = flask.request.headers.get("Accept", "")
    is_json_accept = "application/json" in accept_header
    is_api_path = flask.request.path.startswith("/auth/v1/")
    has_redirect_uri = err.redirect_uri is not None

    # API request detection: JSON Accept header or API path prefix
    is_api_request = is_json_accept or is_api_path

    # OAuth browser flow detection: has redirect_uri and not an API request
    is_oauth_flow = has_redirect_uri and not is_api_request

    if is_api_request:
        # API request - return JSON error response
        # Use envelope format for API consistency
        err_dict = err.to_dict(envelope_format=True)
        from campus.common import devops
        # Remove details in production for security reasons
        if devops.ENV == devops.PRODUCTION:
            err_dict["error"].pop("details", None)
        # Return appropriate status code from the error
        return err_dict, err.status_code

    elif is_oauth_flow:
        # OAuth browser flow - return redirect (RFC 6749)
        err_dict = err.to_dict()
        # OAuth errors follow RFC 6749, not the API error spec
        # No production cleanup needed for OAuth redirect errors
        return flask.redirect(
            url.add_query(
                err.redirect_uri or flask.request.base_url,
                **err_dict
            )
        )

    else:
        # Ambiguous request - in development, raise an error to help debugging
        from campus.common import devops
        if devops.ENV == devops.PRODUCTION:
            # In production, default to JSON for safety
            err_dict = err.to_dict(envelope_format=True)
            return err_dict, err.status_code
        else:
            # In development, raise to help identify the issue
            raise flask.abort(
                400,
                description=(
                    f"Ambiguous authorization error: "
                    f"Accept={accept_header!r}, path={flask.request.path!r}, "
                    f"has_redirect_uri={has_redirect_uri}. "
                    f"Please set Accept: application/json for API requests "
                    f"or provide redirect_uri for OAuth flows."
                )
            )

def handle_api_error(err: api_errors.APIError) -> tuple[JsonDict, int]:
    """Handle API errors.

    This function is used to handle API errors and return
    standardised JSON responses following the API Error Handling Specification.

    Reference: campus/api/docs/api-error-spec.md
    """
    module = get_caller()
    # Only log tracebacks for 5xx errors; 4xx are client errors and don't need tracebacks
    if 500 <= err.status_code < 600:
        logger.exception("APIError in %s: %s", module, err)
    else:
        logger.info("APIError in %s: %s", module, err)
    err_dict = err.to_dict()
    from campus.common import devops
    # Remove traceback and sensitive details in production for security reasons
    if devops.ENV == devops.PRODUCTION:
        err_dict["error"].pop("details", None)
    return err_dict, err.status_code


def handle_token_error(
        err: token_errors.TokenError
) -> tuple[JsonDict, int]:
    """Handle OAuth token request errors.

    This function is used to handle Token errors and return
    standardised JSON responses following RFC 6749 Section 5.2
    with Campus error envelope for API consistency.

    Reference: campus/auth/docs/auth-error-spec.md
    """
    module = get_caller()
    # Only log tracebacks for 5xx errors; 4xx are client errors and don't need tracebacks
    if 500 <= err.status_code < 600:
        logger.exception("TokenError in %s: %s", module, err)
    else:
        logger.info("TokenError in %s: %s", module, err)
    err_dict = err.to_dict(envelope_format=True)
    from campus.common import devops
    # Remove details in production for security reasons
    if devops.ENV == devops.PRODUCTION:
        err_dict["error"].pop("details", None)
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
