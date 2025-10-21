"""tests.flask_test.factory

Factory functions for creating Campus test client with Flask apps.
"""

from typing import Mapping, cast

from campus.client.core import Campus
from campus.common.http.interface import JsonClient
from campus.common import env
from .client import FlaskTestClient


def create_test_client_from_manager(manager) -> Campus:
    """Create a Campus client from a ServiceManager.

    This is the preferred way to create test clients as it ensures proper
    service setup and resource management. Automatically sets STORAGE_MODE
    for test storage backends.

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

    # Ensure test storage mode is enabled
    env.STORAGE_MODE = "1"

    # Create override mapping with Flask test clients, cast to satisfy typing
    import campus.config
    from campus.common import devops
    override: Mapping[str, JsonClient] = {
        "campus.vault": cast(JsonClient, FlaskTestClient(
            manager.vault_app,
            base_url=campus.config.BASE_URLS["campus.vault"][devops.TESTING]
        )),
        "campus.apps": cast(JsonClient, FlaskTestClient(
            manager.apps_app,
            base_url=campus.config.BASE_URLS["campus.apps"][devops.TESTING]
        )),
    }
    return Campus(override=override)


def create_test_client() -> Campus:
    """Factory function to create a Campus client using Flask test clients.

    This creates a Campus client that uses FlaskTestClient instances instead
    of making actual HTTP requests. Perfect for integration testing.
    Automatically sets STORAGE_MODE for test storage backends.

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
    # Ensure test storage mode is enabled
    env.STORAGE_MODE = "1"

    from tests.fixtures import services

    # This creates a service manager but doesn't clean it up
    # Use create_test_client_from_manager() with services.init() for better control
    manager = services.create_service_manager()
    manager.setup()

    return create_test_client_from_manager(manager)


def create_test_app(module):
    """Create a single Flask app for testing with proper test configuration.

    This function handles all the proper setup for testing a single service:
    - Sets test environment variables 
    - Enables test storage mode
    - Creates and configures Flask app

    Args:
        module: Campus service module (e.g., campus.vault, campus.apps)

    Returns:
        Flask app configured for testing

    Example:
        import campus.vault
        from tests.flask_test import create_test_app

        app = create_test_app(campus.vault)
        # App is ready for FlaskTestClient testing
    """
    from tests.fixtures import setup
    from campus.common.devops.deploy import create_app
    from .configure import configure_for_testing

    # Set proper environment variables
    setup.set_test_env_vars()
    env.STORAGE_MODE = "1"

    # Create and configure app
    app = create_app(module)
    configure_for_testing(app)

    return app
