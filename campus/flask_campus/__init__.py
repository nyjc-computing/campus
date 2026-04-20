"""flask_campus

This package provides utilities and types for building a Flask
application for the Campus API. It includes tools for request parsing,
validation, and response formatting, as well as an OAuth login manager
for handling authentication with the Campus API.
"""

__all__ = [
    "HtmlResponse",
    "JsonResponse",
    "OAuthLoginManager",
    "get_user_agent",
    "get_request_headers",
    "get_request_payload",
    "unpack_into",
    "unpack_request",
    "validate_request_and_extract_json",
    "validate_request_and_extract_urlparams",
    "validate_json_response",
]

from .login_manager import OAuthLoginManager
from .types import (
    HtmlResponse,
    JsonResponse,
)
from .utils import (
    get_request_headers,
    get_request_payload,
    get_user_agent,
    unpack_into,
    unpack_request,
    validate_json_response,
    validate_request_and_extract_json,
    validate_request_and_extract_urlparams,
)
