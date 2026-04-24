"""campus.audit.web

Flask blueprint modules for the audit web UI.

This package contains all web UI route definitions for the audit service.
Each module defines route functions that can be attached to blueprints
dynamically for test isolation.
"""

__all__ = [
    "ui",
]

from . import ui
