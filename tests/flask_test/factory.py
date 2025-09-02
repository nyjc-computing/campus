"""tests.flask_test.factory

Factory functions for creating Campus test client with Flask apps.
"""

from typing import Mapping, cast

from campus.client.core import Campus
from campus.common.http.interface import JsonClient
from .client import FlaskTestClient


def create_test_client_from_manager(manager) -> Campus:
    """Create a Campus client from a ServiceManager.

    This is the preferred way to create test clients as it ensures proper
    service setup and resource management.

    Args:
        manager: ServiceManager instance with vault_app and apps_app set up

    Returns:
        Campus: Client instance configured with Flask test clients

    Example:
        from tests.flask_test import create_test_client_from_manager
        from tests.fixtures import services

        with services.init() as manager:
            client = create_test_client_from_manager(manager)
            result = client.vault["test"]["key"].get()
    """
    if not manager.vault_app or not manager.apps_app:
        raise ValueError(
            "ServiceManager must be set up with vault_app and apps_app")

    # Create override mapping with Flask test clients, cast to satisfy typing
    override: Mapping[str, JsonClient] = {
        "campus.vault": cast(JsonClient, FlaskTestClient(
            manager.vault_app,
            base_url="http://localhost:8080/api/v1/"
        )),
        "campus.apps": cast(JsonClient, FlaskTestClient(
            manager.apps_app,
            base_url="http://localhost:8081/api/v1/"
        )),
    }

    return Campus(override=override)


def create_test_client() -> Campus:
    """Factory function to create a Campus client using Flask test clients.

    This creates a Campus client that uses FlaskTestClient instances instead
    of making actual HTTP requests. Perfect for integration testing.

    Note: This function sets up services automatically but doesn't provide
    a way to clean them up. For better resource management, use:

    Example:
        from tests.flask_test import create_test_client_from_manager
        from tests.fixtures import services

        with services.init() as manager:
            client = create_test_client_from_manager(manager)
            # Services are automatically cleaned up

    Returns:
        Campus: Client instance configured with Flask test clients
    """
    from tests.fixtures import services

    # This creates a service manager but doesn't clean it up
    # Use create_test_client_from_manager() with services.init() for better control
    manager = services.create_service_manager()
    manager.setup()

    return create_test_client_from_manager(manager)
