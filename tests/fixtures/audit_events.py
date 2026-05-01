"""Test fixtures for audit event testing.

Provides helper functions to query and verify audit events
emitted by campus.audit service operations.

Audit events are stored as TraceSpan records in the traces table
(spans storage) with special fields to identify them as audit events
rather than regular HTTP request spans.
"""

from typing import Any

import campus.storage


def get_audit_spans(event_type: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Query traces table for audit event spans.

    Audit events are TraceSpan records where path contains the event type
    (e.g., "campus.apikeys.new", "campus.apikeys.auth.success").

    Args:
        event_type: Optional event type to filter by (e.g., "campus.apikeys.new")
        limit: Maximum number of spans to return

    Returns:
        List of span records (dicts) from traces storage
    """
    from campus.audit.resources.traces import traces_storage

    # Build query for audit events
    # Audit events have path starting with "campus.apikeys." or "campus.traces." etc.
    if event_type:
        query = {"path": event_type}
    else:
        # Get all audit events (paths starting with "campus.")
        query = {"path": campus.storage.startswith("campus.")}

    try:
        spans = traces_storage.get_matching(
            query,
            order_by="started_at",
            ascending=False,
            limit=limit
        )
        return spans
    except campus.storage.errors.StorageError:
        return []


def get_audit_events_by_api_key(api_key_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Query all audit events for a specific API key.

    Args:
        api_key_id: The API key identifier
        limit: Maximum number of events to return

    Returns:
        List of span records from traces storage
    """
    from campus.audit.resources.traces import traces_storage

    try:
        # Query spans where api_key_id matches and path starts with "campus."
        spans = traces_storage.get_matching(
            {"api_key_id": api_key_id, "path": campus.storage.startswith("campus.")},
            order_by="started_at",
            ascending=False,
            limit=limit
        )
        return spans
    except campus.storage.errors.StorageError:
        return []


def parse_audit_span_data(span: dict[str, Any]) -> dict[str, Any]:
    """Extract audit event data from a TraceSpan record.

    Audit events store their metadata in the tags field.

    Args:
        span: TraceSpan record from traces storage

    Returns:
        Parsed audit event data from tags field
    """
    # Audit event data is stored in the tags field
    return span.get("tags", {})
