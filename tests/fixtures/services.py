"""tests.fixtures.services

Service management for local Campus service instances.
Provides a clean interface to start and stop all Campus services for testing.
"""

from contextlib import contextmanager
from typing import Optional, cast

from . import setup, auth, api, storage, yapper
from campus.common import devops, env

# pylint: disable=import-outside-toplevel


class ServiceManager:
    """Manages local Campus service instances for testing.

    This class coordinates the setup of all required services:
    - Database setup (PostgreSQL, MongoDB)
    - Service initialization (auth, api, yapper, storage)
    - Flask app creation for test clients

    Usage:
        manager = ServiceManager()
        manager.setup()
        # Use manager.auth_app and manager.apps_app
        manager.close()

    Or use as context manager:
        with services.init() as manager:
            # Use manager.auth_app and manager.apps_app
    """

    # Class-level shared instance for reuse across test suites
    _shared_instance = None
    _shared_setup_done = False

    def __init__(self, shared=True):
        """Initialize ServiceManager.

        Args:
            shared: If True, reuse shared instance across test suites.
                   If False, create independent instance.
        """
        self.auth_app: Optional[object] = None
        self.apps_app: Optional[object] = None
        self._setup_done = False
        self._shared = shared

        if shared and ServiceManager._shared_instance is not None:
            # Reuse existing shared instance
            self.auth_app = ServiceManager._shared_instance.auth_app
            self.apps_app = ServiceManager._shared_instance.apps_app
            self._setup_done = ServiceManager._shared_setup_done

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
        # Ensure we're running in the testing environment for safety.
        # If devops.ENV is not TESTING, override it for the duration of tests.
        # This fixture is only used by the test suite and must run in testing mode.
        if devops.ENV != devops.TESTING:
            devops.ENV = devops.TESTING
            env.ENV = devops.TESTING

        if self._setup_done:
            return self

        # If using shared mode and shared instance exists, reuse it
        if self._shared and ServiceManager._shared_setup_done and ServiceManager._shared_instance:
            self.auth_app = ServiceManager._shared_instance.auth_app
            self.apps_app = ServiceManager._shared_instance.apps_app
            self._setup_done = True
            return self

        # Set up test environment
        setup.set_test_env_vars()
        # Ensure storage uses test backends (in-memory/sqlite) so we don't
        # attempt to connect to external Postgres/MongoDB during tests.
        # This uses the helper in campus.storage.testing which sets
        # env.STORAGE_MODE = "1".
        try:
            import campus.storage.testing as storage_testing
            storage_testing.configure_test_storage()
        except Exception:
            # If for some reason the testing helper can't be imported,
            # continue; downstream storage.init() may still handle test mode.
            pass
        setup.set_postgres_env_vars()
        setup.set_mongodb_env_vars()

        # Initialize services in dependency order: auth → yapper → api
        # This order is crucial because:
        # 1. Auth must be initialized first to create client credentials
        # 2. Yapper needs auth credentials to access secrets
        # 3. API imports yapper routes, so yapper must be ready first

        # Step 1: Initialize auth service and create Flask app using devops.deploy
        # The auth fixture creates test client credentials and sets up auth resources
        auth.init()      # Creates test client credentials
        import campus.auth
        from tests import flask_test

        self.auth_app = devops.deploy.create_app(campus.auth)
        flask_test.configure_for_testing(self.auth_app)

        # Step 2: Initialize storage (doesn't depend on other services)
        storage.init()    # Sets up database connections

        # Step 3: Initialize yapper service
        # This must happen after auth is initialized because yapper
        # needs auth credentials to access secret database URIs
        yapper.init()     # Requires auth credentials

        # Step 4: Initialize API service last
        # API imports yapper routes, so yapper must be fully initialized first
        api.init()       # Requires auth credentials

        # Step 5: Create apps Flask application using devops.deploy
        # Import here to avoid circular imports and ensure all dependencies are ready
        # campus.api is the current API module (campus.apps was deprecated)
        import campus.api
        self.apps_app = devops.deploy.create_app(campus.api)
        flask_test.configure_for_testing(self.apps_app)

        self._setup_done = True

        # Store as shared instance if using shared mode
        if self._shared:
            ServiceManager._shared_instance = self
            ServiceManager._shared_setup_done = True

        return self

    def close(self):
        """Clean up service instances.

        This method cleans up resources and resets the manager state.
        Can be called multiple times safely.

        Note: For shared instances, the test client is only deleted
        when cleanup_shared() is called to prevent interfering with
        other test suites that might still be using the client.
        """
        # Only clean up test client if this is not a shared instance
        if not self._shared:
            self._cleanup_vault_client()

        # Clean up Flask apps
        if self.auth_app is not None:
            # Flask apps don't need explicit cleanup, but we can clear references
            self.auth_app = None

        if self.apps_app is not None:
            self.apps_app = None

        # For non-shared instances, clear client credentials from environment
        if not self._shared:
            if env.CLIENT_ID is not None:
                delattr(env, "CLIENT_ID")
            if env.CLIENT_SECRET is not None:
                delattr(env, "CLIENT_SECRET")

        self._setup_done = False

    def _cleanup_vault_client(self):
        """Properly clean up the test client from auth service.

        This method attempts to delete the test client using the auth resources,
        which ensures proper cleanup of both client records and associated
        access permissions.
        """
        client_id = env.CLIENT_ID
        if not client_id:
            return  # No client to clean up

        try:
            # Delete the client through the auth resources
            from campus.auth.resources import client as auth_client
            auth_client[client_id].delete()
        except Exception:
            # If deletion fails (e.g., vault service already shut down,
            # client already deleted, database connection issues),
            # we continue with environment cleanup silently.
            # This is acceptable for test cleanup scenarios.
            pass
            pass

    @classmethod
    def cleanup_shared(cls):
        """Clean up shared service instances and reset storage.

        This should be called at the end of test runs to ensure clean state.
        """
        if cls._shared_instance:
            # For shared instances, we do the test client cleanup here
            cls._shared_instance._cleanup_vault_client()
            cls._shared_instance.close()
            cls._shared_instance = None
            cls._shared_setup_done = False

        # Clear client credentials from environment
        if env.CLIENT_ID is not None:
            delattr(env, "CLIENT_ID")
        if env.CLIENT_SECRET is not None:
            delattr(env, "CLIENT_SECRET")

        # Reset test storage
        from campus.storage.testing import reset_test_storage
        reset_test_storage()

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
            # manager.auth_app and manager.apps_app are ready
            auth_client = FlaskTestClient(manager.auth_app)
            apps_client = FlaskTestClient(manager.apps_app)

    Yields:
        ServiceManager: Configured service manager with running applications
    """
    manager = ServiceManager()
    try:
        yield manager.setup()
    finally:
        manager.close()


def create_service_manager(shared=True):
    """Factory function to create a new ServiceManager.

    Args:
        shared: If True, reuse shared instance across test suites.
               If False, create independent instance.

    Returns:
        ServiceManager: New or shared service manager
    """
    return ServiceManager(shared=shared)
