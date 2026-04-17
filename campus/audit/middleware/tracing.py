"""campus.audit.middleware.tracing

Tracing middleware implementation for capturing HTTP request-response spans.
"""

import concurrent.futures
import json
import logging
import time
import typing

import flask

from campus.audit.client import AuditClient
from campus.common import schema
from campus.common.utils import uid

logger = logging.getLogger(__name__)

class ExecutorManager:
    """Manages executor lifecycle with clear ownership and state tracking.

    This class provides:
    - Explicit state tracking (created, running, shut down)
    - Idempotent shutdown operations
    - Safe executor recreation for tests
    - Clear error messages for lifecycle violations

    Lifecycle States:
    - Created: Manager exists but executor not yet initialized
    - Running: Executor is accepting tasks
    - Shut down: Executor has been shut down and won't accept new tasks

    Example:
        manager = ExecutorManager()
        executor = manager.get_executor()
        manager.shutdown(wait=True)
        manager.recreate()  # For tests that need a fresh executor
    """

    def __init__(self, max_workers: int = 2, thread_name_prefix: str = "audit_ingest"):
        """Initialize the executor manager.

        Args:
            max_workers: Maximum number of worker threads
            thread_name_prefix: Prefix for thread names
        """
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._shutdown = False
        self._max_workers = max_workers
        self._thread_name_prefix = thread_name_prefix

    def get_executor(self) -> concurrent.futures.ThreadPoolExecutor:
        """Get or create the thread pool executor.

        Returns:
            ThreadPoolExecutor instance for submitting tasks

        Raises:
            RuntimeError: If executor has been shut down
        """
        if self._shutdown:
            raise RuntimeError(
                "Executor has been shut down. Call recreate() to create a new executor."
            )

        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix=self._thread_name_prefix
            )

        return self._executor

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the executor idempotently.

        This method is safe to call multiple times. After the first call,
        subsequent calls are no-ops.

        Args:
            wait: If True, wait for pending tasks to complete
        """
        if self._executor is not None and not self._shutdown:
            self._executor.shutdown(wait=wait)
            self._shutdown = True

    def recreate(self) -> None:
        """Recreate the executor after shutdown.

        This is primarily useful for tests that need a fresh executor.
        If the executor is currently running, this will shut it down first.

        Raises:
            RuntimeError: If shutdown fails during recreation
        """
        # Shutdown existing executor if it's running
        if self._executor is not None and not self._shutdown:
            self.shutdown(wait=True)

        # Create new executor and reset shutdown state
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix=self._thread_name_prefix
        )
        self._shutdown = False

    @property
    def is_shutdown(self) -> bool:
        """Check if the executor has been shut down.

        Returns:
            True if executor has been shut down, False otherwise
        """
        return self._shutdown

    @property
    def is_initialized(self) -> bool:
        """Check if the executor has been initialized.

        Returns:
            True if executor has been created, False otherwise
        """
        return self._executor is not None


# Thread pool manager for async ingestion (avoid blocking requests)
_ingestion_executor_manager = ExecutorManager(
    max_workers=2,
    thread_name_prefix="audit_ingest"
)

# Backward compatibility: expose the executor directly
# This is deprecated - use _ingestion_executor_manager instead
_ingestion_executor: concurrent.futures.ThreadPoolExecutor | None = None

# Client singleton (lazy initialized)
_audit_client: AuditClient | None = None
# Track credentials used to create the client, for detecting when they change
_client_credentials: tuple[str, str] | None = None


def _get_audit_client() -> AuditClient:
    """Get or create the audit client singleton.

    The client is recreated if credentials have changed since last creation,
    ensuring each test class gets a client with its own credentials.

    Returns:
        AuditClient instance for sending spans to audit service.

    Raises:
        ValueError: If CLIENT_ID or CLIENT_SECRET are not set in environment.
    """
    global _audit_client, _client_credentials

    # Get current credentials from environment
    from campus.common import env

    # Check if credentials are available (they may be deleted during test cleanup)
    client_id = env.get("CLIENT_ID")
    client_secret = env.get("CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError(
            "CLIENT_ID and CLIENT_SECRET must be set in environment "
            "to create audit client"
        )

    current_credentials = (client_id, client_secret)

    # Recreate client if credentials have changed or client doesn't exist
    if _audit_client is None or _client_credentials != current_credentials:
        _audit_client = AuditClient()
        _client_credentials = current_credentials

    return _audit_client


def start_span() -> None:
    """Start a root span for the incoming request.

    - Generates or reuses trace_id from X-Request-ID header
    - Generates span_id for this request
    - Stores timing data in flask.g

    Stores in flask.g:
        - trace_id: 32-char hex trace identifier
        - span_id: 16-char hex span identifier
        - trace_start: timestamp for duration calculation
    """
    # Get or generate trace_id from X-Request-ID header
    trace_id = flask.request.headers.get("X-Request-ID") or uid.generate_trace_id()

    # Generate span_id for this request
    span_id = uid.generate_span_id()

    # Store in flask.g for use in after_request
    flask.g.trace_id = trace_id
    flask.g.span_id = span_id
    flask.g.trace_start = time.perf_counter()


def end_span(response: flask.Response) -> flask.Response:
    """Complete the span and ingest to audit service.

    - Builds TraceSpan from flask.request, flask.g, and response
    - Ingests asynchronously to avoid blocking
    - Echoes trace_id in response headers

    Args:
        response: The Flask response object

    Returns:
        Response with X-Request-ID header added
    """
    # Get trace data from flask.g (set by start_span)
    trace_id = getattr(flask.g, "trace_id", None)
    span_id = getattr(flask.g, "span_id", None)
    trace_start = getattr(flask.g, "trace_start", None)

    if not all([trace_id, span_id, trace_start]):
        # Tracing wasn't started properly, skip ingestion
        return response

    # Type narrowing: we know these are not None after the check
    trace_id = typing.cast(str, trace_id)
    span_id = typing.cast(str, span_id)
    trace_start = typing.cast(float, trace_start)

    # Calculate duration
    duration_ms = (time.perf_counter() - trace_start) * 1000

    # Build span from context
    span = build_span_from_context(trace_id, span_id, response, duration_ms)

    # Ingest asynchronously (don't block the response)
    _ingest_span_async(span)

    # Echo trace_id in response header
    response.headers["X-Request-ID"] = trace_id

    return response


def build_span_from_context(
    trace_id: str,
    span_id: str,
    response: flask.Response,
    duration_ms: float,
) -> dict:
    """Build a span dict from request/response context.

    Args:
        trace_id: The trace identifier
        span_id: The span identifier
        response: The Flask response object
        duration_ms: Request duration in milliseconds

    Returns:
        Dictionary representation of the span for ingestion.
    """
    request = flask.request

    # Extract headers (strip Authorization)
    headers = dict(request.headers)
    headers.pop("Authorization", None)
    headers.pop("authorization", None)  # Case-insensitive

    # Get request body (only for supported content types)
    request_body = _extract_request_body(request)

    # Get response body (truncated to 64KB)
    response_body = _extract_response_body(response)

    # Build span dict matching TraceSpan schema
    span = {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": None,  # Root spans have no parent
        "started_at": schema.DateTime.utcnow(),
        "duration_ms": round(duration_ms, 3),
        "status_code": response.status_code,
        "method": request.method,
        "path": request.path,
        "query_params": dict(request.args),
        "request_headers": headers,
        "request_body": request_body,
        "response_headers": dict(response.headers),
        "response_body": response_body,
        "client_ip": request.remote_addr,
        "user_agent": request.user_agent.string if request.user_agent else None,
        "error_message": None,  # No error for successful requests
        "tags": {},  # No tags by default
        # Optional: populated by auth middleware if available
        "api_key_id": getattr(flask.g, "api_key_id", None),
        "client_id": getattr(flask.g, "client_id", None),
        "user_id": getattr(flask.g, "user_id", None),
    }

    return span


def _extract_request_body(request: flask.Request) -> dict | str | None:
    """Extract request body safely.

    Only extracts for supported content types (JSON, form data).
    Returns None for unsupported types (files, binary, etc).

    Args:
        request: The Flask request object.

    Returns:
        Request body as dict, str, or None.
    """
    # Don't extract body for file uploads or unsupported content types
    if request.files:
        return None
    if request.content_length and request.content_length > 1_000_000:  # 1MB
        return None

    content_type = request.content_type or ""

    if "application/json" in content_type:
        try:
            return request.json
        except Exception:
            return None
    elif "application/x-www-form-urlencoded" in content_type:
        return dict(request.form)
    elif "text/" in content_type:
        try:
            return request.data.decode("utf-8")
        except Exception:
            return None

    return None


def _extract_response_body(response: flask.Response) -> dict | str | None:
    """Extract response body with 64KB truncation.

    Args:
        response: The Flask response object.

    Returns:
        Response body truncated to 64KB, or None if not applicable.
    """
    # Don't try to extract from streaming responses
    if response.is_streamed:
        return None

    # Don't extract if no response data
    if not response.response:
        return None

    try:
        # Get response data
        if isinstance(response.response, list):
            # Join bytes from list
            parts = typing.cast(list, response.response)
            if all(isinstance(p, bytes) for p in parts):
                data = bytes(b"".join(typing.cast(list[bytes], parts)))
            else:
                # Mixed types, convert to string
                data = "".join(str(p) for p in parts)
        elif isinstance(response.response, str):
            data = response.response.encode("utf-8")
        else:
            data = typing.cast(bytes, response.response)

        # Decode if possible
        if isinstance(data, bytes):
            try:
                data = data.decode("utf-8")
            except UnicodeDecodeError:
                return "<binary data>"

        # Truncate to 64KB
        max_size = 64 * 1024
        if len(data) > max_size:
            data = data[:max_size]

        # Try to parse as JSON for structured logging
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return data

        return data
    except Exception:
        return None


def _ingest_span_async(span: dict) -> None:
    """Ingest span asynchronously using thread pool.

    Args:
        span: Span data to ingest.
    """
    def _do_ingest():
        try:
            client = _get_audit_client()
            client.traces.new(span)
        except ValueError as e:
            # Credentials not available (e.g., during test cleanup)
            # This is expected during shutdown, so log at debug level
            logger.debug(f"Skipping trace ingestion: {e}")
        except Exception as e:
            # Don't let tracing errors break the application
            logger.warning(f"Failed to ingest trace span: {e}")

    try:
        executor = _ingestion_executor_manager.get_executor()
        executor.submit(_do_ingest)
    except RuntimeError as e:
        # Executor has been shut down (e.g., during test cleanup)
        # Log and continue - don't break the application
        logger.debug(f"Cannot submit span to executor: {e}")


def ingest_span(span: dict) -> None:
    """Send span to audit service via HTTP.

    This is a synchronous wrapper for backward compatibility.
    The actual ingestion happens asynchronously to avoid blocking.

    Args:
        span: Span data dictionary to ingest
    """
    _ingest_span_async(span)


def shutdown_executor(wait: bool = True) -> None:
    """Shutdown the trace ingestion executor.

    This is primarily useful for tests that need to wait for async operations
    to complete before making assertions. The shutdown is idempotent - safe
    to call multiple times.

    Args:
        wait: If True, wait for pending tasks to complete

    Note:
        This is typically called automatically during test cleanup.
        Manual calls are only needed when you need to synchronize with async operations.
    """
    _ingestion_executor_manager.shutdown(wait=wait)


def recreate_executor() -> None:
    """Recreate the trace ingestion executor after shutdown.

    This is primarily useful for tests that need a fresh executor.
    If the executor is currently running, it will be shut down first.

    Example:
        # In test setup
        recreate_executor()

        # Run test that uses tracing
        # ...

        # In test teardown
        shutdown_executor(wait=True)

    Warning:
        This should only be used in tests, not in production code.
    """
    _ingestion_executor_manager.recreate()


def get_executor_state() -> dict:
    """Get the current state of the executor for debugging/testing.

    Returns:
        Dictionary with keys:
        - 'initialized': True if executor has been created
        - 'shutdown': True if executor has been shut down
    """
    return {
        'initialized': _ingestion_executor_manager.is_initialized,
        'shutdown': _ingestion_executor_manager.is_shutdown,
    }
