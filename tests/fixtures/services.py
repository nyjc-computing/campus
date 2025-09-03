"""tests.fixtures.services

Service management for local Campus service instances.
Provides a clean interface to start and stop all Campus services for testing.
"""

from contextlib import contextmanager
from typing import Optional, cast

from . import setup, vault, apps, storage, yapper

# pylint: disable=import-outside-toplevel


class ServiceManager:
    """Manages local Campus service instances for testing.

    This class coordinates the setup of all required services:
    - Database setup (PostgreSQL, MongoDB)
    - Service initialization (vault, apps, yapper, storage)
    - Flask app creation for test clients

    Usage:
        manager = ServiceManager()
        manager.setup()
        # Use manager.vault_app and manager.apps_app
        manager.close()

    Or use as context manager:
        with services.init() as manager:
            # Use manager.vault_app and manager.apps_app
    """

    def __init__(self):
        self.vault_app: Optional[object] = None
        self.apps_app: Optional[object] = None
        self._setup_done = False

    def setup(self):
        """Set up all Campus services for testing.

        This method:
        1. Sets up test environment variables
        2. Configures database connections (PostgreSQL, MongoDB)
        3. Initializes all Campus services (vault, apps, yapper, storage)
        4. Creates Flask applications ready for testing

        Returns:
            ServiceManager: Self for method chaining
        """
        if self._setup_done:
            return self

        # Set up test environment
        setup.set_test_env_vars()
        setup.set_postgres_env_vars()
        setup.set_mongodb_env_vars()

        # Initialize services in dependency order: vault → yapper → apps
        # This order is crucial because:
        # 1. Vault must be initialized first to create client credentials
        # 2. Yapper needs vault credentials to access secrets
        # 3. Apps imports yapper routes, so yapper must be ready first

        # Step 1: Initialize vault service and create Flask app using devops.deploy
        vault.init()      # Creates test client credentials
        import campus.vault
        from campus.common import devops
        from tests import flask_test

        self.vault_app = devops.deploy.create_app(campus.vault)
        flask_test.configure_for_testing(self.vault_app)

        # Step 1.5: Set up vault factory for testing to use Flask test client
        # This must happen after vault app is created but before yapper/apps import
        from flask import Flask
        import campus.client.vault
        from campus.common.http.interface import JsonClient
        import campus.config

        def test_vault_factory() -> campus.client.vault.VaultResource:
            vault_base_url = campus.config.BASE_URLS["campus.vault"][devops.TESTING]
            if self.vault_app is None:
                raise RuntimeError("vault_app not initialized")
            test_client = cast(JsonClient, flask_test.client.FlaskTestClient(
                cast(Flask, self.vault_app), base_url=vault_base_url)
            )
            return campus.client.vault.VaultResource(test_client, raw=False)

        # Set the vault factory - this will be used by both yapper and apps modules
        campus.client.vault.set_vault_factory(test_vault_factory)

        # Step 2: Initialize storage (doesn't depend on other services)
        storage.init()    # Sets up database connections

        # Step 3: Initialize yapper service
        # This must happen after vault is initialized because yapper
        # needs vault credentials to access secret database URIs
        yapper.init()     # Requires vault credentials

        # Step 4: Initialize apps service last
        # Apps imports yapper routes, so yapper must be fully initialized first
        apps.init()       # Requires vault credentials

        # Step 5: Create apps Flask application using devops.deploy
        # Import here to avoid circular imports and ensure all dependencies are ready
        import campus.apps
        self.apps_app = devops.deploy.create_app(campus.apps)
        flask_test.configure_for_testing(self.apps_app)

        self._setup_done = True
        return self

    def close(self):
        """Clean up service instances.

        This method cleans up resources and resets the manager state.
        Can be called multiple times safely.
        """
        # Reset vault factory to default
        import campus.client.vault
        campus.client.vault.set_vault_factory(None)

        # Clean up Flask apps
        if self.vault_app is not None:
            # Flask apps don't need explicit cleanup, but we can clear references
            self.vault_app = None

        if self.apps_app is not None:
            self.apps_app = None

        self._setup_done = False

    def __enter__(self):
        """Context manager entry."""
        return self.setup()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


@contextmanager
def init():
    """Context manager for Campus service setup.

    This is the main entrypoint for setting up local Campus services.
    It ensures proper cleanup even if exceptions occur.

    Usage:
        with services.init() as manager:
            # manager.vault_app and manager.apps_app are ready
            vault_client = FlaskTestClient(manager.vault_app)
            apps_client = FlaskTestClient(manager.apps_app)

    Yields:
        ServiceManager: Configured service manager with running applications
    """
    manager = ServiceManager()
    try:
        yield manager.setup()
    finally:
        manager.close()


def create_service_manager():
    """Factory function to create a new ServiceManager.

    Returns:
        ServiceManager: New uninitialized service manager
    """
    return ServiceManager()
