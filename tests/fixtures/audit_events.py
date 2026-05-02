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
    (e.g., "audit.apikeys.new", "audit.apikeys.auth.success").

    Args:
        event_type: Optional event type to filter by (e.g., "audit.apikeys.new")
        limit: Maximum number of spans to return

    Returns:
        List of span records (dicts) from traces storage
    """
    from campus.audit.resources.traces import traces_storage

    # Build query for audit events
    # Audit events have path equal to event type (exact match)
    if event_type:
        query = {"path": event_type}
    else:
        # Get all spans - will filter for audit events in Python
        query = {}

    try:
        spans = traces_storage.get_matching(
            query,
            order_by="started_at",
            ascending=False,
            limit=limit * 10  # Get more to filter for audit events
        )
        # Filter to only audit events (path starts with "audit.")
        if not event_type:
            spans = [s for s in spans if s.get("path", "").startswith("audit.")]
        return spans[:limit]
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
        # Query all spans for this API key, then filter for audit events
        spans = traces_storage.get_matching(
            {"api_key_id": api_key_id},
            order_by="started_at",
            ascending=False,
            limit=limit * 10  # Get more to filter for audit events
        )
        # Filter to only audit events (path starts with "audit.")
        audit_events = [s for s in spans if s.get("path", "").startswith("audit.")]
        return audit_events[:limit]
    except campus.storage.errors.StorageError:
        return []


def parse_audit_span_data(span: dict[str, Any]) -> dict[str, Any]:
    """Extract audit event data from a TraceSpan record.

    Audit events store metadata in both TraceSpan fields (client_ip, api_key_id)
    and the tags field (event-specific data).

    Args:
        span: TraceSpan record from traces storage

    Returns:
        Combined dict with tags data plus important TraceSpan fields
    """
    # Start with tags (event-specific data)
    data = span.get("tags", {}).copy()

    # Add important fields from the span itself
    if "client_ip" in span:
        data["client_ip"] = span["client_ip"]
    if "api_key_id" in span:
        data["api_key_id"] = span["api_key_id"]

    return data
