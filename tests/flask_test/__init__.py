"""tests.flask_test

Flask test client adapters for Campus testing.

This module provides adapter classes that wrap Flask's test client to implement
the Campus JsonClient and JsonResponse protocols. This enables using Flask test
clients with the Campus client interface for testing without actual HTTP calls.

Key Components:
- FlaskTestResponse: Adapts werkzeug.test.TestResponse to JsonResponse protocol
- FlaskTestClient: Adapts Flask test client to JsonClient protocol  
- create_test_client: Factory function for creating Campus client with Flask apps
"""

from .client import FlaskTestClient
from .response import FlaskTestResponse
from .factory import create_test_client, create_test_client_from_manager
from .configure import configure_for_testing


__all__ = [
    "FlaskTestClient",
    "FlaskTestResponse",
    "create_test_client",
    "create_test_client_from_manager",
    "configure_for_testing"
]
