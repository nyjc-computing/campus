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

    def _do_initialize(self):
        """Core initialization logic for all services.

        This method contains the actual initialization logic without storage reset.
        It's called by both setup() (which resets storage first) and initialize()
        (which doesn't reset storage).

        Returns:
            ServiceManager: Self for method chaining
        """
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
            # Configure file-based test database for debugging
            campus.storage.testing.configure_test_db()
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

        # Enable audit tracing middleware in tests (default: enabled)
        # This can be disabled per-test by setting env.set('AUDIT_TRACING_ENABLED', '0')
        env.set('AUDIT_TRACING_ENABLED', '1')

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

    def setup(self):
        """Initialize all Campus services for integration testing.

        DEPRECATED: Use initialize() instead.

        This method is deprecated and will be removed in a future version.
        Please use the new initialize() method which provides a cleaner lifecycle.
        See: #518 - Test lifecycle documentation

        **Lifecycle Phase**: Class Setup (once per test class)
        **Ownership**: Primary owner of service initialization
        **Cleanup**: Handled by cleanup() method

        Performs environment setup, database configuration, and service
        initialization in proper dependency order: auth → storage → yapper → api.

        Phase Details:
        - Configures test environment variables (ENV, STORAGE_MODE, HOSTNAME)
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

        See: #518 - Test lifecycle documentation
        """
        # Call the core initialization logic
        return self._do_initialize()


    def _do_cleanup(self):
        """Core cleanup logic for all services.

        This method contains the actual cleanup logic. It's called by both
        close() (deprecated) and cleanup() (new API).

        Cleans up:
        - Background threads (tracing middleware executor)
        - Auth client (test client record)
        - Environment credentials (CLIENT_ID, CLIENT_SECRET)
        - Audit client configuration
        - Flask apps (if not shared mode)
        """
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
        if env.contains("ACCESS_TOKEN"):
            env.delete("ACCESS_TOKEN")

        # Clean up audit client configuration
        from campus.audit.client import AuditClient
        AuditClient.json_client_class = None  # Reset to None

        # Clear audit client singleton
        from campus.audit.middleware import tracing
        tracing._audit_client = None

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
        **Ownership**: Delegates to tracing module's ExecutorManager
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
        - Idempotent by design (ExecutorManager tracks state explicitly)

        Implementation Notes:
        - Uses ExecutorManager.shutdown() which is inherently idempotent
        - No exception handling needed for normal flow
        - Tests can call recreate_executor() to create fresh executors

        See: #520 - Discussion of executor idempotency patterns
        """
        from campus.audit.middleware import tracing
        # ExecutorManager.shutdown() is idempotent by design
        # No exception handling needed - it handles state tracking internally
        tracing._ingestion_executor_manager.shutdown(wait=True)

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
        - Background threads (via cleanup())

        Should be called at the end of test runs to ensure clean state.
        Used in test fixtures and finalizers to clean up after all tests complete.

        Cleanup Order:
        1. Unpatch campus_python and clear test app routing
        2. Clean up auth client from shared instance
        3. Cleanup shared instance (shuts down threads, clears credentials)
        4. Clear environment credentials (redundant but safe)

        Usage:
            Typically called in test finalizers or atexit handlers rather than
            in individual test classes, which use cleanup() instead.
        """
        # Unpatch campus_python and clear test apps
        from tests import flask_test
        flask_test.unpatch_campus_python()
        flask_test.clear_test_apps()

        if cls._shared_instance:
            cls._shared_instance._cleanup_auth_client()
            cls._shared_instance.cleanup()
            cls._shared_instance = None
            cls._shared_setup_done = False

        if env.contains("CLIENT_ID"):
            env.delete("CLIENT_ID")
        if env.contains("CLIENT_SECRET"):
            env.delete("CLIENT_SECRET")
        if env.contains("ACCESS_TOKEN"):
            env.delete("ACCESS_TOKEN")

    # === NEW LIFECYCLE API (Issue #518) ===
    # These methods provide a cleaner, more predictable lifecycle for integration tests.
    # They coexist with the old API (setup/reset_test_data/close) during migration.

    def initialize(self):
        """One-time initialization of all services.

        **Lifecycle Phase**: Class Setup (once per test class)
        **New API**: Use this instead of setup() for new test code
        **Ownership**: Primary owner of service initialization

        This is the new recommended method for service initialization.

        Key Difference from setup():
        - Does NOT reset test storage (no schema destruction)
        - Storage reset only happens once in setup() for backwards compatibility
        - clear_test_data() handles per-test data cleanup without schema destruction
        - Faster than setup() because it preserves table structure

        This method initializes services without destroying the database schema,
        which is the core performance improvement of the new lifecycle API.

        Returns:
            ServiceManager: Self for method chaining

        See: #518 - Proposal: Saner Integration Test Lifecycle
        """
        self._do_initialize()
        # Ensure audit API key exists after initialization
        # This must be called after _do_initialize() so the audit app is ready
        self._ensure_audit_api_key()
        return self

    def _ensure_audit_api_key(self) -> None:
        """Ensure audit API key exists for tracing middleware span ingestion.

        Creates a fresh audit API key if one doesn't exist (e.g., after
        clear_test_data() deletes all rows). This should be called after any
        operation that clears the database.

        The audit service requires Bearer token authentication (audit API keys)
        instead of Basic auth (CLIENT_ID/CLIENT_SECRET) used by auth/api services.
        """
        from campus.audit.resources.apikeys import APIKeysResource

        # Initialize audit API keys storage (creates table if needed)
        # This is idempotent and safe to call multiple times
        APIKeysResource.init_storage()

        # Create an audit API key for span ingestion
        apikey_resource = APIKeysResource()
        api_key_model, plaintext_key = apikey_resource.new(
            name="test-tracing-key",
            owner_id=str(env.CLIENT_ID),  # Use test client ID as owner
            scopes="traces:ingest,traces:read,traces:search"
        )

        # Set ACCESS_TOKEN so TestJsonClient uses Bearer authentication
        # TestJsonClient._auth_headers() checks ACCESS_TOKEN first before falling
        # back to CLIENT_ID/CLIENT_SECRET Basic auth
        env.set('ACCESS_TOKEN', plaintext_key)

        # Reset audit client singleton to pick up the new ACCESS_TOKEN
        # Note: We don't reset json_client_class as that would break TestJsonClient injection
        from campus.audit.middleware import tracing
        tracing._audit_client = None  # Clear singleton so it recreates with new token

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
        - Recreates audit API key after clearing (since clear_all_data() deletes it)

        Migration Path:
        - Old: reset_test_data() - manual Resource.init_storage()
        - New: clear_test_data() - no manual reinit needed

        See: #518 - Proposal: Saner Integration Test Lifecycle
        """
        """
        import campus.storage.testing

        # Clear data without destroying schema (faster than reset_test_storage)
        campus.storage.testing.clear_all_data()

        # Re-initialize auth and yapper services
        # These are idempotent and will recreate necessary data
        auth.init()
        yapper.init()

        # Recreate audit API key after clearing data
        # Since clear_all_data() deletes all rows, the API key created during
        # _do_initialize() is gone and needs to be recreated for each test
        self._ensure_audit_api_key()

        **Lifecycle Phase**: Test Setup (once per test)
        **New API**: Use this instead of reset_test_data() for new test code
        **Ownership**: Primary owner of per-test data cleanup

        This is the new recommended method for per-test data cleanup.
        Unlike reset_test_data(), this method:
        - Uses clear_all_data() which preserves schema structure
        - Is faster (no table/collection recreation)
        - Doesn't require manual Resource.init_storage() calls

        Migration Path:
        - Old: reset_test_data() - manual Resource.init_storage()
        - New: clear_test_data() - no manual reinit needed

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

        Cleans up:
        - Background threads (tracing middleware executor)
        - Auth client (test client record)
        - Environment credentials (CLIENT_ID, CLIENT_SECRET)
        - Audit client configuration
        - Flask apps (if not shared mode)

        This method contains the core cleanup logic.

        See: #518 - Proposal: Saner Integration Test Lifecycle
        """
        self._do_cleanup()


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
