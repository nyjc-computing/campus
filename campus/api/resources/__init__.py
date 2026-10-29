"""campus.api.resources

Namespace for campus.api resources.
Note: These resources directly access storage without authentication,
and with minimal model-based validation.
They are intended for internal use within campus.api.
External clients should access resources via API endpoints.
"""

__all__ = [
    "assignment",
    "circle",
    "emailotp",
    "file",
    "submission",
]

from .assignment import AssignmentsResource
from .circle import CirclesResource
from .emailotp import EmailOTPResource
from .files import FilesResource
from .submission import SubmissionsResource
from .timetable import TimetablesResource

# Initialize resource instances for internal use
assignment = AssignmentsResource()
circle = CirclesResource()
emailotp = EmailOTPResource()
file = FilesResource()
submission = SubmissionsResource()
timetable = TimetablesResource()
