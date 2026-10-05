"""campus.common.errors.handlers

Error handler functions for Flask error handling.
"""

import logging
import pathlib
import sys
import traceback

import flask
import werkzeug.exceptions

from campus.common.utils import url

from . import api_errors, auth_errors, token_errors
from .base import JsonDict

logger = logging.getLogger(__name__)

# Package root for this copy of campus: handlers.py lives at
# <pkg>/campus/common/errors/handlers.py, and handler frames themselves are
# never the origin of an error.
_CAMPUS_PKG_DIR = pathlib.Path(__file__).resolve().parents[2]
_HANDLER_DIR = pathlib.Path(__file__).resolve().parent


def _select_campus_frame(frames) -> str | None:
    """Return the outermost frame inside the campus package, if any.

    Adapter and client libraries raise from their own modules; the campus
    frame that made the failing call is the actionable one in logs (#620).
    """
    for frame in frames:
        path = pathlib.Path(frame.filename).resolve()
        if (
                path.is_relative_to(_CAMPUS_PKG_DIR)
                and not path.is_relative_to(_HANDLER_DIR)
        ):
            return frame.filename
    return None


def get_caller() -> str:
    """Return the filename of the campus module where the error originated.

    Walks the traceback from the outermost frame and names the first campus
    package frame, so unhandled exceptions log the campus code responsible
    rather than the adapter or client library raise site (#620). Falls back
    to the innermost frame when the chain contains no campus frames.
    """
    tb = sys.exc_info()[2]
    if tb:
        frames = traceback.extract_tb(tb)
        if frames:
            return _select_campus_frame(frames) or frames[-1].filename
    return "unknown"


def log_error_by_status(
        err: api_errors.APIError | auth_errors.AuthorizationError | token_errors.TokenError,
        error_label: str | None = None,
) -> None:
    """Log error with appropriate level based on status code.

    Only logs tracebacks for 5xx server errors; 4xx client errors are logged
    at INFO level without tracebacks to reduce log noise.

    Args:
        err: The error object with a status_code attribute
        error_label: Optional label for the error type (e.g., "APIError", "OAuthError").
                     Defaults to the error class name if not provided.
    """
    module = get_caller()
    label = error_label or err.__class__.__name__
    if 500 <= err.status_code < 600:
        logger.exception("%s in %s: %s", label, module, err)
    else:
        logger.info("%s in %s: %s", label, module, err)


def handle_authorization_error(
        err: auth_errors.AuthorizationError
) -> werkzeug.Response | tuple[JsonDict, int]:
    """Handle OAuth authorization request errors.

    This function handles OAuth errors and returns appropriate responses:
    - For API requests (JSON Accept header or /auth/v1/* paths): JSON error
    - For OAuth browser flows: HTTP redirect (RFC 6749)

    In development mode, raises BadRequest for ambiguous requests.
    """
    log_error_by_status(err)

    # Determine if this is an API request (expects JSON) or OAuth browser flow (expects redirect)
    accept_header = flask.request.headers.get("Accept", "")
    is_json_accept = "application/json" in accept_header
    # All Campus services serve JSON under their versioned path prefixes.
    # API clients (e.g. campus_python) do not send an Accept header, so
    # without these prefixes every authorization error on campus.api /
    # campus.audit would hit the ambiguous-request guard below and come
    # back as 400 instead of its real status (#614).
    is_api_path = flask.request.path.startswith((
        "/auth/v1/",
        "/api/v1/",
        "/audit/v1/",
    ))
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
    log_error_by_status(err)
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
    log_error_by_status(err)
    err_dict = err.to_dict(envelope_format=True)
    from campus.common import devops
    # Remove details in production for security reasons
    if devops.ENV == devops.PRODUCTION:
        err_dict["error"].pop("details", None)
    return err_dict, err.status_code


def handle_werkzeug_error(
        err: werkzeug.exceptions.HTTPException
) -> tuple[JsonDict, int] | tuple[JsonDict, int, dict[str, str]]:
    """Handle werkzeug errors.

    This function is used to handle werkzeug errors and return
    standardised JSON responses. Every HTTPException is mapped to its
    own status code and error code so that client errors (405, 400, ...)
    are not masked as 500 INTERNAL_ERROR (#700).

    Reference: https://flask.palletsprojects.com/en/stable/errorhandling/
    """
    module = get_caller()
    match err:
        case werkzeug.exceptions.NotFound():
            return {}, 404  # ignore 404 errors; too numerous
        case werkzeug.exceptions.InternalServerError():
            logger.exception("InternalServerError in %s: %s", module, err)
            return api_errors.InternalError().to_dict(), 500
        case _ if err.code is None:
            # Bare HTTPException carries no status code; treat as a server error
            logger.exception("HTTPException in %s: %s", module, err)
            return api_errors.InternalError().to_dict(), 500
        case _:
            # Every other werkzeug HTTPException carries its own status code
            # (405 MethodNotAllowed, 400 BadRequest, 415 UnsupportedMediaType, ...).
            # Re-raising here fell through to the generic 500 handler, so client
            # errors surfaced as 500 INTERNAL_ERROR (#700).
            status = err.code
            # "Method Not Allowed" -> "METHOD_NOT_ALLOWED"
            error_code = str(err.name).upper().replace(" ", "_").replace("-", "_")
            api_err = api_errors.APIError(
                message=err.description or err.name,
                error_code=error_code,
            )
            api_err.status_code = status
            log_error_by_status(api_err, error_label="HTTPException")
            headers: dict[str, str] = {}
            if (
                    isinstance(err, werkzeug.exceptions.MethodNotAllowed)
                    and err.valid_methods
            ):
                # 405 responses MUST identify the allowed methods (RFC 9110)
                headers["Allow"] = ", ".join(err.valid_methods)
            if headers:
                return api_err.to_dict(), status, headers
            return api_err.to_dict(), status


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
