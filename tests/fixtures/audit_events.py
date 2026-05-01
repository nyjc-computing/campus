"""Test fixtures for audit event testing.

Provides helper functions to query and verify audit events
emitted by campus.audit service operations.
"""

from typing import Any

import campus.storage


def get_yapper_events(label: str, limit: int = 50) -> list[dict[str, Any]]:
    """Query yapper events table for events matching label.

    Args:
        label: Event label to filter by (e.g., "campus.apikeys.new")
        limit: Maximum number of events to return

    Returns:
        List of event dicts with keys: id, label, data, created_at
    """
    from campus.common import env

    # Get yapper database URI from vault
    from campus.auth import resources as auth_resources
    yapper_vault = auth_resources.vault["campus.yapper"]
    db_path = yapper_vault["YAPPERDB_URI"]

    # Query yapper events table directly
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, label, data, created_at FROM events WHERE label = ? ORDER BY created_at DESC LIMIT ?",
        (label, limit)
    )
    events = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return events


def get_audit_events_by_api_key(api_key_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Query all audit events for a specific API key.

    Args:
        api_key_id: The API key identifier
        limit: Maximum number of events to return

    Returns:
        List of event dicts from yapper events table
    """
    from campus.common import env

    # Get yapper database URI from vault
    from campus.auth import resources as auth_resources
    yapper_vault = auth_resources.vault["campus.yapper"]
    db_path = yapper_vault["YAPPERDB_URI"]

    # Query yapper events table
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Search for api_key_id in event data (stored as JSON string)
    cursor.execute(
        "SELECT id, label, data, created_at FROM events WHERE data LIKE ? ORDER BY created_at DESC LIMIT ?",
        (f'%{api_key_id}%', limit)
    )
    events = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return events


def parse_event_data(data_string: str) -> dict[str, Any]:
    """Parse yapper event data string into dict.

    Args:
        data_string: JSON string from yapper events table

    Returns:
        Parsed dict (may be nested)
    """
    import json
    return json.loads(data_string.replace("'", '"'))
