"""campus.audit.resources

Namespace for campus.audit resources.
Note: These resources directly access storage without authentication,
and with minimal model-based validation.
They are intended for internal use within campus.audit.
External clients should access resources via API endpoints.
"""

__all__ = [
    "apikeys",
    "traces",
]

from .apikeys import APIKeysResource
from .traces import TracesResource

# Initialize resource instances for internal use
traces = TracesResource()
apikeys = APIKeysResource()
