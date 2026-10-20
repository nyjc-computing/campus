"""campus.audit.web

Flask blueprint modules for the audit web UI.

This package contains all web UI route definitions for the audit service.
Each module defines route functions that can be attached to blueprints
dynamically for test isolation.

- ui: HTML pages for browsing traces
- data: JSON data endpoints for the UI's JavaScript
- auth: browser OAuth gate (login/callback/logout, spec §5 / issue #696)
- keys: the key-management page (issue #927)
"""

__all__ = [
    "auth",
    "data",
    "keys",
    "ui",
]

from . import auth, data, keys, ui
