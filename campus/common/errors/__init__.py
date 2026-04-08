"""campus.common.errors

API error handling for Campus.
"""

from .base import JsonDict
from . import api_errors, auth_errors, token_errors, validation
from .validation import ValidationError, FieldError
from .api_errors import (
    ConflictError,
    ForbiddenError,
    InternalError,
    InvalidRequestError,
    NotFoundError,
    UnauthorizedError,
)
from . import handlers

__all__ = [
    "init_app",
    "JsonDict",
    "api_errors",
    "auth_errors",
    "token_errors",
    "validation",
    "ValidationError",
    "FieldError",
    "ConflictError",
    "ForbiddenError",
    "InternalError",
    "InvalidRequestError",
    "NotFoundError",
    "UnauthorizedError",
]

# Re-export init_app for backward compatibility
init_app = handlers.init_app
