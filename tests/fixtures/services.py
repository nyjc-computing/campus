"""tests.fixtures.services

Service manager for initializing and coordinating Campus service instances.

Orchestrates setup and lifecycle of services for integration testing.
"""

from contextlib import contextmanager
from typing import Optional, cast

from . import setup, auth, api, storage, yapper
from campus.common import devops, env

# Lazy import of audit (imports campus_python which needs vault setup)
# pylint: disable=import-outside-toplevel


class ServiceManager:
    """Manages Campus service instances for integration testing.

    Coordinates initialization of campus.auth, campus.api, campus.audit,
    and related services with proper test fixtures and environment configuration.

    Attributes:
        auth_app: Flask application for campus.auth service
        apps_app: Flask application for campus.api service
        audit_app: Flask application for campus.audit service
        _setup_done: Initialization completion flag
        _shared: Whether instance uses shared resources across tests
    """

    _shared_instance = None
    _shared_setup_done = False

    def __init__(self, shared=False):
        """Initialize ServiceManager.

        Args:
            shared: Whether to reuse shared instance across test suites.
                    Defaults to False to create fresh Flask apps per test class
                    for better test isolation.
        """
        self.auth_app: Optional[object] = None
        self.apps_app: Optional[object] = None
        self.audit_app: Optional[object] = None
        self._setup_done = False
        self._shared = shared

        if shared and ServiceManager._shared_instance is not None:
            # Reuse existing shared instance
            self.auth_app = ServiceManager._shared_instance.auth_app
            self.apps_app = ServiceManager._shared_instance.apps_app
            self.audit_app = ServiceManager._shared_instance.audit_app
            self._setup_done = ServiceManager._shared_setup_done

    def setup(self):
        """Initialize all Campus services for integration testing.

        Performs environment setup, database configuration, and service
        initialization in proper dependency order: auth → storage → yapper → api.

        Note:
            With shared=False (the default), creates fresh Flask apps with
            fresh blueprints for each test class. This ensures full test
            isolation at the cost of slightly slower test execution.

        Returns:
            ServiceManager: Self for method chaining
        """
        # Reset test storage at start of setup for clean state
        # This ensures test classes don't pollute each other's storage
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

        # Ensure we're running in testing mode
        # env.ENV is mutable and can be set for testing purposes
        if env.get("ENV") != devops.TESTING:
            env.set('ENV', devops.TESTING)

        # Always re-init auth and yapper services if already setup,
        # in case storage was reset. These are idempotent.
        if self._setup_done:
            auth.init()
            yapper.init()
            return self

        # If using shared mode and shared instance exists, reuse it
        if self._shared and ServiceManager._shared_setup_done and ServiceManager._shared_instance:
            self.auth_app = ServiceManager._shared_instance.auth_app
            self.apps_app = ServiceManager._shared_instance.apps_app
            self._setup_done = True
            # Re-init auth and yapper in case storage was reset
            auth.init()
            yapper.init()
            return self

        # Set up test environment
        setup.set_test_env_vars()
        # Ensure storage uses test backends (in-memory/sqlite) so we don't
        # attempt to connect to external Postgres/MongoDB during tests.
        # This uses the helper in campus.storage.testing which sets
        # env.STORAGE_MODE = "1".
        try:
            import campus.storage.testing
            campus.storage.testing.configure_test_storage()
        except Exception:
            # If for some reason the testing helper can't be imported,
            # continue; downstream storage.init() may still handle test mode.
            pass
        setup.set_postgres_env_vars()
        setup.set_mongodb_env_vars()

        # Set HOSTNAME for test mode - campus_python uses this to build base_url
        # When DEPLOY="campus.auth", it uses base_url = f"https://{env.HOSTNAME}"
        # We use a fake hostname that we'll map to Flask test apps
        env.set('HOSTNAME', "campus.test")

        # Patch campus_python to use TestCampusRequest (Flask test client)
        # This must be done before any campus_python.Campus instances are created
        from tests import flask_test
        flask_test.patch_campus_python()

        # Patch DefaultClient to use TestJsonClient (Flask test client)
        # This allows AuditClient to use Flask test clients for testing
        # Note: This is a safety net - the factory pattern below is the primary mechanism
        flask_test.patch_default_client()

        # Initialize auth service infrastructure
        # Creates storage tables, test client credentials, vault secrets
        # This is safe to call multiple times as it's idempotent
        auth.init()
        import campus.auth

        self.auth_app = devops.deploy.create_app(campus.auth)
        flask_test.configure_for_testing(self.auth_app)

        # Register auth app with its base URL and path prefix for test routing
        # campus_python will use base_url = f"https://{env.HOSTNAME}" = "https://campus.test"
        # Auth routes are at /auth/v1/*
        flask_test.register_test_app("https://campus.test", self.auth_app, path_prefix="/auth")

        # Set up HTTP client factory for AuditClient dependency injection
        # This must happen AFTER auth.init() so CLIENT_ID/CLIENT_SECRET are set
        from campus.audit.client import set_http_client_factory

        def _test_http_client_factory(base_url: str) -> flask_test.TestJsonClient:
            """Factory function that creates TestJsonClient for testing."""
            # Load credentials from environment at call time (not at factory setup time)
            # This ensures each test class gets the current credentials, not stale ones
            # This is needed because auth.init() creates a new client for each test class
            client_id = env.CLIENT_ID
            client_secret = env.CLIENT_SECRET
            return flask_test.TestJsonClient(
                base_url=base_url,
                _credentials=(client_id, client_secret)
            )

        set_http_client_factory(_test_http_client_factory)

        # Initialize storage connections
        storage.init()

        # Initialize yapper service (requires auth credentials)
        yapper.init()

        # Initialize API service (requires auth credentials, imports yapper)
        api.init()

        # Create Flask app for campus.api service
        import campus.api
        self.apps_app = devops.deploy.create_app(campus.api)
        flask_test.configure_for_testing(self.apps_app)

        # Register api app with path prefix for test routing
        # API routes are at /api/v1/*
        flask_test.register_test_app("https://campus.test", self.apps_app, path_prefix="/api")

        # Initialize audit service
        import campus.audit
        # Note: audit doesn't have a separate init() function like auth/api
        # Storage initialization happens in init_app() and in tests

        # Create Flask app for campus.audit service
        self.audit_app = devops.deploy.create_app(campus.audit)
        flask_test.configure_for_testing(self.audit_app)

        # Register audit app with path prefix for test routing
        # Audit routes are at /audit/v1/*
        flask_test.register_test_app("https://campus.test", self.audit_app, path_prefix="/audit")

        self._setup_done = True

        # Store as shared instance if using shared mode
        if self._shared:
            ServiceManager._shared_instance = self
            ServiceManager._shared_setup_done = True

        return self

    def reset_test_data(self):
        """Reset test storage for per-test isolation.

        This method clears all test storage (SQLite in-memory DB, memory collections)
        and re-initializes services. Use this in tearDown() for per-test isolation.

        WARNING: This clears auth credentials, so tests using bearer tokens will need
        to re-create their tokens after calling this method.

        For tests that use authentication, consider using unique identifiers per test
        (e.g., filtering by created_by) instead of full reset, or re-create the token
        in setUp() after calling this in tearDown().
        """
        import campus.storage.testing

        # Reset storage (clears SQLite in-memory DB and memory collections)
        campus.storage.testing.reset_test_storage()

        # Re-initialize auth and yapper services
        # These are idempotent and will recreate necessary tables/collections
        auth.init()
        yapper.init()

    def close(self):
        """Clean up service instances and resources.

        Always cleans up auth client and credentials. With shared=False,
        also cleans up Flask apps for full isolation.
        """
        # Always clean up auth client regardless of shared mode
        self._cleanup_auth_client()

        # Always clear credentials from environment
        if env.contains("CLIENT_ID"):
            env.delete("CLIENT_ID")
        if env.contains("CLIENT_SECRET"):
            env.delete("CLIENT_SECRET")

        # Clean up audit client factory
        from campus.audit.client import set_http_client_factory
        set_http_client_factory(None)  # Reset to None

        # Clean up audit client factory
        from campus.audit.client import set_http_client_factory
        set_http_client_factory(None)  # Reset to None

        # For non-shared instances, clean up apps for full isolation
        # This is now the default behavior
        if not self._shared:
            if self.auth_app is not None:
                self.auth_app = None
            if self.apps_app is not None:
                self.apps_app = None
            if self.audit_app is not None:
                self.audit_app = None

        self._setup_done = False

    def _cleanup_auth_client(self):
        """Clean up the test client from auth service.

        Deletes the test client to ensure proper cleanup of client records
        and associated access permissions.
        """
        client_id = env.CLIENT_ID
        if not client_id:
            return

        try:
            from campus.auth import resources as auth_resources
            auth_resources.client[client_id].delete()
        except Exception:
            pass

    @classmethod
    def cleanup_shared(cls):
        """Clean up shared service instances and reset storage.

        Should be called at the end of test runs to ensure clean state.
        """
        # Unpatch campus_python, DefaultClient, and clear test apps
        from tests import flask_test
        flask_test.unpatch_campus_python()
        flask_test.unpatch_default_client()
        flask_test.clear_test_apps()

        if cls._shared_instance:
            cls._shared_instance._cleanup_auth_client()
            cls._shared_instance.close()
            cls._shared_instance = None
            cls._shared_setup_done = False

        if env.contains("CLIENT_ID"):
            env.delete("CLIENT_ID")
        if env.contains("CLIENT_SECRET"):
            env.delete("CLIENT_SECRET")

        # Reset test storage
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def __enter__(self):
        """Context manager entry."""
        return self.setup()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


@contextmanager
def init():
    """Context manager for Campus service initialization and cleanup.

    Provides convenient setup and teardown of services for integration testing.
    Ensures proper cleanup even if exceptions occur.

    Usage:
        with services.init() as manager:
            auth_client = manager.auth_app.test_client()
            api_client = manager.apps_app.test_client()

    Yields:
        ServiceManager: Configured service manager with Flask applications
    """
    manager = ServiceManager()
    try:
        yield manager.setup()
    finally:
        manager.close()


def create_service_manager(shared=False):
    """Factory function to create a new ServiceManager.

    Args:
        shared: If True, reuse shared instance across test suites (faster).
               If False (default), create independent instance with fresh
               Flask apps for each test class (better isolation).

    Returns:
        ServiceManager: New or shared service manager
    """
    return ServiceManager(shared=shared)
