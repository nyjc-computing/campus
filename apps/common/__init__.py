"""apps.common

This module contains common functions and classes used across multiple
applications.

Modules:

- errors: Contains error definitions and handling for API errors.
- webauth: Contains web authentication models and configurations.
"""

from . import errors, webauth

__all__ = [
    "errors",
    "webauth",
]
