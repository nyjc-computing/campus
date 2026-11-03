"""campus.audit.routes

Flask blueprint modules for the audit service.

This package contains all HTTP route definitions organized by functionality:
- traces.py: Trace ingestion and query endpoints (/traces/*)
- journeys.py: Journey query endpoints (/journeys/*)
- apikeys.py: API key management endpoints (/apikeys/*)

Each module defines route functions that can be attached to blueprints
dynamically. This allows creating fresh blueprints for test isolation.
"""

__all__ = [
    "traces",
    "journeys",
    "apikeys",
]

from . import apikeys, journeys, traces
