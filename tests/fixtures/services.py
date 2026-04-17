"""tests.fixtures.services

Service manager for initializing and coordinating Campus service instances.

Orchestrates setup and lifecycle of services for integration testing.
"""

from contextlib import contextmanager
from typing import Optional

from flask import Flask

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

    _shared_instance: Optional["ServiceManager"] = None
    _shared_setup_done = False

    def __init__(self, shared=False):
        """Initialize ServiceManager.

        Args:
            shared: Whether to reuse shared instance across test suites.
                    Defaults to False to create fresh Flask apps per test class
                    for better test isolation.
        """
        self.auth_app: Optional[Flask] = None
        self.apps_app: Optional[Flask] = None
        self.audit_app: Optional[Flask] = None
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

        DEPRECATED: Use initialize() instead.

        This method is deprecated and will be removed in a future version.
        Please use the new initialize() method which provides a cleaner lifecycle.
        See: #518 - Test lifecycle documentation

        **Lifecycle Phase**: Class Setup (once per test class)
        **Ownership**: Primary owner of service initialization
        **Cleanup**: Handled by close() method

        Performs environment setup, database configuration, and service
        initialization in proper dependency order: auth → storage → yapper → api.

        Phase Details:
        - Configures test environment variables (ENV, STORAGE_MODE, HOSTNAME)
        - Resets test storage for clean state
        - Patches campus_python for test routing
        - Initializes services in dependency order
        - Creates Flask apps for auth, api, and audit
        - Registers test apps for URL routing

        Note:
            With shared=False (the default), creates fresh Flask apps with
            fresh blueprints for each test class. This ensures full test
            isolation at the cost of slightly slower test execution.

        Returns:
            ServiceManager: Self for method chaining

        Migration Guide:
            Old: manager.setup()
            New: manager.initialize()

        See: #518 - Test lifecycle documentation
        """
        import warnings
        warnings.warn(
            "setup() is deprecated, use initialize() instead. See #518.",
            DeprecationWarning,
            stacklevel=2
        )

        # Reset test storage at start of setup for clean state
        # This ensures test classes don't pollute each other's storage
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

        # Ensure we're running in testing mode
        # env.ENV is mutable and can be set for testing purposes
        if env.get("ENV") != devops.TESTING:
            env.set('ENV', devops.TESTING)

        # Set up test environment BEFORE any service initialization
        # This must happen before auth/yapper/api init since they create campus_python.Campus()
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
        # This MUST happen before any campus_python.Campus instances are created
        # Moved here to ensure patching happens before early returns below
        from tests import flask_test
        flask_test.patch_campus_python()

        # Note: patch_default_client() removed - no longer needed
        # AuditClient.json_client_class is now the primary mechanism

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

        # Configure AuditClient to use TestJsonClient for testing
        # TestJsonClient loads credentials from environment dynamically,
        # just like FlaskTestClient/TestCampusRequest
        from campus.audit.client import AuditClient

        AuditClient.json_client_class = flask_test.TestJsonClient

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

        DEPRECATED: Use clear_test_data() instead.

        This method is deprecated and will be removed in a future version.
        Please use the new clear_test_data() method which preserves schema
        and is faster. See: #518 - Test lifecycle documentation

        This method clears all test storage (SQLite in-memory DB, memory collections)
        and re-initializes services. Use this in tearDown() for per-test isolation.

        WARNING: Brittle Pattern - Manual Resource Reinit Required
        This method destroys table structure, requiring tests to manually call
        Resource.init_storage() after reset. This order-dependent pattern is
        error-prone and will be replaced by ServiceManager.clear_test_data()
        which preserves schema (see #518).

        WARNING: This clears auth credentials, so tests using bearer tokens will need
        to re-create their tokens after calling this method.

        For tests that use authentication, consider using unique identifiers per test
        (e.g., filtering by created_by) instead of full reset, or re-create the token
        in setUp() after calling this in tearDown().

        Migration Path:
            Old: manager.reset_test_data() -> manual Resource.init_storage()
            New: manager.clear_test_data() -> no manual reinit needed

        See: #518 - Test lifecycle documentation
        """
        import warnings
        warnings.warn(
            "reset_test_data() is deprecated, use clear_test_data() instead. See #518.",
            DeprecationWarning,
            stacklevel=2
        )
        import campus.storage.testing

        # Reset storage (clears SQLite in-memory DB and memory collections)
        campus.storage.testing.reset_test_storage()

        # Re-initialize auth and yapper services
        # These are idempotent and will recreate necessary tables/collections
        auth.init()
        yapper.init()

    def close(self):
        """Clean up service instances and resources.

        DEPRECATED: Use cleanup() instead.

        This method is deprecated and will be removed in a future version.
        Please use the new cleanup() method which provides cleaner lifecycle.
        See: #518 - Test lifecycle documentation

        **Lifecycle Phase**: Class Teardown (once per test class)
        **Ownership**: Primary owner of resource cleanup
        **Cleans Up**:
        - Background threads (tracing middleware executor)
        - Auth client (test client record)
        - Environment credentials (CLIENT_ID, CLIENT_SECRET)
        - Audit client configuration
        - Flask apps (if not shared mode)

        Cleanup Order Matters:
        1. Threads are shut down FIRST to avoid race conditions with background tasks
        2. Auth client is cleaned up SECOND while credentials are still available
        3. Credentials are cleared THIRD to prevent use after cleanup
        4. Flask apps are cleaned up LAST (if not shared)

        Always cleans up auth client and credentials. With shared=False,
        also cleans up Flask apps for full isolation.

        Note: Does NOT reset storage - next test class will handle that in initialize()

        Migration Guide:
            Old: manager.close()
            New: manager.cleanup()

        See: #518 - Test lifecycle documentation
        """
        import warnings
        warnings.warn(
            "close() is deprecated, use cleanup() instead. See #518.",
            DeprecationWarning,
            stacklevel=2
        )
        # Shut down tracing middleware's background thread pool FIRST
        # This must happen BEFORE clearing credentials and storage to avoid
        # race conditions where background threads try to access cleared resources
        self.shutdown_threads()

        # Always clean up auth client regardless of shared mode
        self._cleanup_auth_client()

        # Always clear credentials from environment
        if env.contains("CLIENT_ID"):
            env.delete("CLIENT_ID")
        if env.contains("CLIENT_SECRET"):
            env.delete("CLIENT_SECRET")

        # Clean up audit client configuration
        from campus.audit.client import AuditClient
        AuditClient.json_client_class = None  # Reset to None

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

    def shutdown_threads(self):
        """Shutdown background threads idempotently.

        **Lifecycle Phase**: Test Teardown (after each test) OR Class Teardown
        **Ownership**: Delegates to tracing module's shutdown logic
        **Cleans Up**: Tracing middleware background thread pool

        Safely shuts down the tracing middleware's thread pool if it's running.
        This method is idempotent - safe to call multiple times without errors.

        Usage:
        - Optional: Call in tearDown() to wait for async operations before assertions
        - Automatic: Called by close() during class teardown
        - Safe: Multiple calls are no-ops after first shutdown

        Thread Safety:
        - Waits for pending tasks to complete (wait=True)
        - Prevents new tasks from being submitted after shutdown
        - Idempotent via exception handling (RuntimeError from double shutdown)

        Note: This does not set the executor to None, allowing tests to
        recreate it if needed for the next test.

        See: #520 - Discussion of executor idempotency patterns
        """
        try:
            from campus.audit.middleware import tracing
            # Check if executor exists and hasn't been shut down yet
            if hasattr(tracing, '_ingestion_executor') and tracing._ingestion_executor is not None:
                # Try to shutdown - if already shut down, this will raise an exception
                # which we catch, making this idempotent
                tracing._ingestion_executor.shutdown(wait=True)
        except Exception:
            # Executor already shut down or other error - this is fine
            # This makes the method idempotent
            pass

    @classmethod
    def cleanup_shared(cls):
        """Clean up shared service instances and reset storage.

        **Lifecycle Phase**: End of Test Run (global cleanup)
        **Ownership**: Final cleanup for shared service manager instances
        **Cleans Up**:
        - Shared service manager instance
        - campus_python test patches
        - Test app routing configuration
        - Auth client and credentials
        - Background threads (via close())

        Should be called at the end of test runs to ensure clean state.
        Used in test fixtures and finalizers to clean up after all tests complete.

        Note: Does not call reset_test_storage() here to avoid redundant cleanup.
        The close() method already handles cleanup, and any subsequent test runs
        will reset storage in their setup() calls via ServiceManager.setup().

        Cleanup Order:
        1. Unpatch campus_python and clear test app routing
        2. Clean up auth client from shared instance
        3. Close shared instance (shuts down threads, clears credentials)
        4. Clear environment credentials (redundant but safe)

        Usage:
            Typically called in test finalizers or atexit handlers rather than
            in individual test classes, which use close() instead.
        """
        # Unpatch campus_python and clear test apps
        from tests import flask_test
        flask_test.unpatch_campus_python()
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

    # === NEW LIFECYCLE API (Issue #518) ===
    # These methods provide a cleaner, more predictable lifecycle for integration tests.
    # They coexist with the old API (setup/reset_test_data/close) during migration.

    def initialize(self):
        """One-time initialization of all services.

        **Lifecycle Phase**: Class Setup (once per test class)
        **New API**: Use this instead of setup() for new test code
        **Ownership**: Primary owner of service initialization

        This is the new recommended method for service initialization.

        ⚠️ TECHNICAL DEBT: Currently delegates to setup() which calls
        reset_test_storage(). This defeats the performance benefits of the
        new API. Should be refactored to avoid schema destruction.

        TODO: Refactor to separate service initialization from storage reset.
        - Storage should only be reset once at test class setup
 - clear_test_data() should handle per-test data cleanup without schema destruction

        Returns:
            ServiceManager: Self for method chaining

        See: #518 - Proposal: Saner Integration Test Lifecycle
        """
        return self.setup()

    def clear_test_data(self):
        """Clear test data while preserving table/collection structure.

        **Lifecycle Phase**: Test Setup (once per test)
        **New API**: Use this instead of reset_test_data() for new test code
        **Ownership**: Primary owner of per-test data cleanup

        This is the new recommended method for per-test data cleanup.
        Unlike reset_test_data(), this method:
        - Uses clear_all_data() which preserves schema structure
        - Is faster (no table/collection recreation)
        - Doesn't require manual Resource.init_storage() calls

        Migration Path:
        - Old: reset_test_data() → manual Resource.init_storage()
        - New: clear_test_data() → no manual reinit needed

        See: #518 - Proposal: Saner Integration Test Lifecycle
        """
        import campus.storage.testing

        # Clear data without destroying schema (faster than reset_test_storage)
        campus.storage.testing.clear_all_data()

        # Re-initialize auth and yapper services
        # These are idempotent and will recreate necessary data
        auth.init()
        yapper.init()

    def flush_async(self):
        """Wait for async operations to complete.

        **Lifecycle Phase**: Test Teardown (after each test)
        **New API**: Call this in tearDown() to ensure async operations complete
        **Ownership**: Delegates to tracing module's shutdown logic

        This ensures background operations (like tracing middleware ingestion)
        complete before the next test starts. Prevents race conditions where
        async operations from one test affect the next test.

        Usage:
            def tearDown(self):
                super().tearDown()
                self.service_manager.flush_async()

        See: #518 - Proposal: Saner Integration Test Lifecycle
        """
        self.shutdown_threads()

    def cleanup(self):
        """Clean up all resources.

        **Lifecycle Phase**: Class Teardown (once per test class)
        **New API**: Use this instead of close() for new test code
        **Ownership**: Primary owner of resource cleanup

        This is the new recommended method for resource cleanup.

        ⚠️ TECHNICAL DEBT: Currently just a wrapper around close().
        Should have distinct behavior or be consolidated as part of
        the new API refactoring.

        TODO: Evaluate if cleanup() should have different behavior
        than close(), or if they should be consolidated.

        See: #518 - Proposal: Saner Integration Test Lifecycle
        """
        self.close()

    def __enter__(self):
        """Context manager entry.

        DEPRECATED: This context manager is not recommended for new test code.

        Use IntegrationTestCase or IsolatedIntegrationTestCase base classes instead,
        which provide proper lifecycle management for integration tests.

        If you need manual ServiceManager usage, use the new API:
            manager = ServiceManager()
            manager.initialize()
            try:
                # use manager.auth_app, manager.apps_app, etc.
            finally:
                manager.cleanup()
        """
        import warnings
        warnings.warn(
            "ServiceManager context manager is deprecated. "
            "Use IntegrationTestCase or IsolatedIntegrationTestCase base classes instead. "
            "See: #518",
            DeprecationWarning,
            stacklevel=2
        )
        return self.setup()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


@contextmanager
def init():
    """Context manager for Campus service initialization and cleanup.

    DEPRECATED: This context manager is not recommended for new test code.

    Use IntegrationTestCase or IsolatedIntegrationTestCase base classes instead,
    which provide proper lifecycle management for integration tests.

    If you need manual ServiceManager usage, use the new API:
        manager = ServiceManager()
        manager.initialize()
        try:
            # use manager.auth_app, manager.apps_app, etc.
        finally:
            manager.cleanup()

    Deprecated: See #518 - Saner Integration Test Lifecycle
    """
    import warnings
    warnings.warn(
        "services.init() context manager is deprecated. "
        "Use IntegrationTestCase or IsolatedIntegrationTestCase base classes instead. "
        "See: #518",
        DeprecationWarning,
        stacklevel=2
    )

    manager = ServiceManager()
    try:
        yield manager.setup()
    finally:
        manager.close()


def create_service_manager(shared=False) -> ServiceManager:
    """Factory function to create a new ServiceManager.

    Args:
        shared: If True, reuse shared instance across test suites (faster).
               If False (default), create independent instance with fresh
               Flask apps for each test class (better isolation).

    Returns:
        ServiceManager: New or shared service manager
    """
    return ServiceManager(shared=shared)
