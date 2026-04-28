"""campus.storage.testing

This module provides test storage backends and configuration for Campus testing.

This allows the storage system to use lightweight, in-memory backends during testing
instead of requiring full database connections.
"""

import atexit
import os
import tempfile
from typing import Type

from campus.storage.tables.interface import TableInterface
from campus.storage.documents.interface import CollectionInterface


# Track whether we've registered the cleanup handler
_cleanup_registered = False


def _cleanup_test_storage():
    """Cleanup test storage at end of test run.

    This atexit handler ensures test storage is properly cleaned up once
    at the end of the test run, not after each test class.
    """
    try:
        reset_test_storage()

        # Clean up the shared test database file
        temp_path = _get_temp_path()
        if temp_path:
            db_path = os.path.join(temp_path, "campus_test.db")
            if os.path.exists(db_path):
                os.remove(db_path)
    except Exception:
        # Ignore errors during cleanup
        pass


def _get_temp_path() -> str | None:
    """Get the temp directory path for file-based test databases.

    Returns:
        Path to temp directory if it exists and is writable, None otherwise.

    Checks in order:
    1. TMP_PATH environment variable
    2. TMPDIR environment variable (common Unix convention)
    3. /tmp directory (Unix default)
    4. tempfile.gettempdir() (Python cross-platform default)
    """
    # Check environment variables first
    for env_var in ["TMP_PATH", "TMPDIR"]:
        path = os.getenv(env_var)
        if path and os.path.isdir(path) and os.access(path, os.W_OK):
            return path

    # Check common temp directories
    for path in ["/tmp", tempfile.gettempdir()]:
        if path and os.path.isdir(path) and os.access(path, os.W_OK):
            return path

    return None


def get_calling_test_class_name() -> str | None:
    """Detect the calling test class name from call stack.

    Walks up the call stack to find the test class that is calling
    into the storage layer. Used to generate database file names.

    Returns:
        Test class name if called from a test context, None otherwise.
    """
    import inspect

    frame = inspect.currentframe()
    if not frame or not frame.f_back:
        return None

    # Walk up the stack looking for test classes
    calling_frame = frame.f_back
    while calling_frame:
        # Check for 'cls' or 'self' in local variables
        for var_name in ('cls', 'self'):
            obj = calling_frame.f_locals.get(var_name)
            if obj:
                # Get the class name
                class_obj = obj if isinstance(obj, type) else type(obj)
                class_name = class_obj.__name__
                # Check if it looks like a test class
                if 'Test' in class_name:
                    return class_name
        calling_frame = calling_frame.f_back

    return None


def get_test_db_path(test_class_name: str | None = None) -> str:
    """Get the path for a test database file.

    Automatically uses file-based databases when temp storage is available,
    otherwise falls back to in-memory databases.

    Args:
        test_class_name: Optional test class name for unique file naming.
                        If not provided, will auto-detect from call stack.

    Returns:
        Path to test database file (either temp file path or :memory:)
    """
    temp_path = _get_temp_path()

    if not temp_path:
        # No temp storage available, use in-memory database
        return ":memory:"

    # Auto-detect test class name if not provided
    if not test_class_name:
        test_class_name = get_calling_test_class_name()

    # Generate unique filename
    if test_class_name:
        safe_name = test_class_name.replace(".", "_").replace(" ", "_")
        filename = f"campus_test_{safe_name}_{os.getpid()}.db"
    else:
        filename = f"campus_test_{os.getpid()}.db"

    return os.path.join(temp_path, filename)


def configure_test_db():
    """Configure SQLite backend for testing with a single shared database.

    This uses a single shared database file for all test classes, which aligns
    with production deployment assumptions where each app deployment uses a
    single database that doesn't change during the deployment lifecycle.

    The database persists across test classes, with clear_test_data() providing
    per-test data isolation. This approach:
    - Avoids "readonly database" errors from stale module-level storage refs
    - Eliminates need for module reloading after storage reset
    - Improves test performance by avoiding database file creation/deletion
    - Matches production: single DB per deployment, stable DB path

    Usage:
        @classmethod
        def setUpClass(cls):
            configure_test_db()
            cls.manager = services.create_service_manager()
    """
    global _cleanup_registered

    # Use fixed database path for all tests (not per-test-class)
    # This aligns with production: single DB per deployment
    temp_path = _get_temp_path()

    if temp_path:
        db_path = os.path.join(temp_path, "campus_test.db")
    else:
        db_path = ":memory:"

    # Store the db_path in environment so SQLiteTable.__init__ can find it
    # Use SQLITE_URI for consistency with POSTGRESDB_URI and MONGODB_URI
    from campus.common import env
    env.set('SQLITE_URI', db_path)

    # Register cleanup handler once at end of test run
    if not _cleanup_registered:
        atexit.register(_cleanup_test_storage)
        _cleanup_registered = True


def is_test_mode() -> bool:
    """Check if storage should use test backends based on STORAGE_MODE."""
    from campus.common import env
    storage_mode = env.get("STORAGE_MODE", "0")
    if storage_mode is None:
        return False
    try:
        return int(storage_mode) != 0
    except ValueError:
        return False


def configure_test_storage():
    """Configure storage to use test backends."""
    from campus.common import env
    # Set environment variable to indicate test mode
    env.set('STORAGE_MODE', "1")


def get_table_backend() -> Type[TableInterface]:
    """Get the appropriate table backend based on configuration."""
    if is_test_mode():
        from campus.storage.tables.backend.sqlite import SQLiteTable
        return SQLiteTable
    else:
        from campus.storage.tables.backend.postgres import PostgreSQLTable
        return PostgreSQLTable


def get_collection_backend() -> Type[CollectionInterface]:
    """Get the appropriate collection backend based on configuration."""
    if is_test_mode():
        from campus.storage.documents.backend.memory import MemoryCollection
        return MemoryCollection
    else:
        from campus.storage.documents.backend.mongodb import MongoDBCollection
        return MongoDBCollection


def reset_test_storage():
    """Reset all test storage. Only works in test mode."""
    if is_test_mode():
        from campus.storage.tables.backend.sqlite import SQLiteTable
        from campus.storage.documents.backend.memory import MemoryCollection

        SQLiteTable.reset_database()
        MemoryCollection.reset_storage()


def clear_all_data():
    """Clear all data from test storage while preserving table/collection structure.

    This is faster than reset_test_storage() for per-test cleanup since it
    doesn't require recreating tables and collections. Only works in test mode.

    Use this in setUp() for per-test isolation when you want to clear data
    but preserve the schema defined in setUpClass().
    """
    if is_test_mode():
        from campus.storage.tables.backend.sqlite import SQLiteTable
        from campus.storage.documents.backend.memory import MemoryCollection

        SQLiteTable.clear_database()
        MemoryCollection.clear_storage()
