"""tests.fixtures.services

Service management for local Campus service instances.
Provides a clean interface to start and stop all Campus services for testing.
"""

from contextlib import contextmanager
from typing import Optional

from . import setup, vault, apps, storage, yapper


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

        # Step 1: Initialize vault service and create Flask app
        vault.init()      # Creates test client credentials
        import campus.vault
        self.vault_app = campus.vault.create_app()

        # Step 2: Initialize storage (doesn't depend on other services)
        storage.init()    # Sets up database connections

        # Step 3: Initialize yapper service
        # This must happen after vault is initialized because yapper
        # needs vault credentials to access secret database URIs
        yapper.init()     # Requires vault credentials

        # Step 4: Initialize apps service last
        # Apps imports yapper routes, so yapper must be fully initialized first
        apps.init()       # Requires vault credentials

        # Step 5: Create apps Flask application
        # Import here to avoid circular imports and ensure all dependencies are ready
        try:
            import campus.apps
            from campus.common import devops
            self.apps_app = devops.deploy.create_app(campus.apps)
        except Exception as e:
            # If we can't create the apps service due to dependencies,
            # create a minimal Flask app instead
            from flask import Flask
            self.apps_app = Flask('test_apps_minimal')
            self.apps_app.config['TESTING'] = True

            @self.apps_app.route('/')
            def health():
                return {'status': 'healthy', 'service': 'test-apps-minimal'}

            print(
                f"Warning: Could not create full apps service, using minimal app: {e}")

        self._setup_done = True
        return self

    def close(self):
        """Clean up service instances.

        This method cleans up resources and resets the manager state.
        Can be called multiple times safely.
        """
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
