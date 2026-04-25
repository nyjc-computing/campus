"""campus.audit.routes

Flask blueprint modules for the audit service.

This package contains all HTTP route definitions organized by functionality:
- traces.py: Trace ingestion and query endpoints (/traces/*)
- health.py: Health check endpoint (/health)

Each module defines route functions that can be attached to blueprints
dynamically. This allows creating fresh blueprints for test isolation.
"""

__all__ = [
    "traces",
]

from . import traces
