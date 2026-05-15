"""campus.audit.helpers

Helper modules for campus.audit service.
"""

from .audit_events import (
    audit_event,
    emit_audit_event,
)

__all__ = [
    "emit_audit_event",
    "audit_event",
]
