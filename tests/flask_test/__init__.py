"""tests.flask_test

Flask test client adapters for Campus testing.

This module provides adapter classes that wrap Flask's test client to implement
the Campus JsonClient and JsonResponse protocols. This enables using Flask test
clients with the Campus client interface for testing without actual HTTP calls.

Key Components:
- FlaskTestResponse: Adapts werkzeug.test.TestResponse to JsonResponse protocol
- TestCampusRequest: JsonClient implementation with routing to Flask test apps
- TestJsonClient: JsonClient implementation with routing to test apps
- create_test_app: Factory function for creating a single Flask app for testing
- register_test_app: Register Flask app for test mode routing
- patch_campus_python: Monkey-patch campus_python to use TestCampusRequest
"""

__all__ = [
    "FlaskTestResponse",
    "TestCampusRequest",
    "TestJsonClient",
    "clear_test_apps",
    "configure_for_testing",
    "create_test_app",
    "patch_campus_python",
    "register_test_app",
    "unpatch_campus_python",
]

from .campus_request import (
    TestCampusRequest,
    clear_test_apps,
    patch_campus_python,
    register_test_app,
    unpatch_campus_python,
)
from .response import FlaskTestResponse
from .factory import create_test_app
from .configure import configure_for_testing
from .json_client import TestJsonClient

