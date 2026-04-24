"""campus.model

Models represent single entities in Campus API schema.

They are typically represented as a row in a table, or a document in a
document store.
More complex models may span multiple tables or collections.

Models are represented with dataclasses.
init parameters must be keyword-only; order of parameters should not
matter.
Models are expected to be used across the codebase; they should have
minimal dependencies, ideally none. Data processing logic should be
kept out of models.
"""

__all__ = [
    "Assignment",
    "AuthSession",
    "Circle",
    "ClassroomLink",
    "Client",
    "ClientAccess",
    "DeviceCode",
    "EmailOTP",
    "Feedback",
    "HttpHeader",
    "HttpHeaderWithAuth",
    "InternalModel",
    "LessonGroup",
    "LessonGroupMember",
    "LoginSession",
    "Model",
    "OAuthToken",
    "Question",
    "Response",
    "Submission",
    "Timetable",
    "TimetableEntry",
    "TimetableMetadata",
    "TraceSpan",
    "TraceSummary",
    "TraceTree",
    "TraceTreeNode",
    "User",
    "UserCredentials",
    "Vault",
    "Venue",
    "VenueBooking",
]

from .audit import TraceSpan, TraceSummary, TraceTree, TraceTreeNode
from .base import InternalModel, Model
from .booking import Venue, VenueBooking
from .circle import Circle
from .classroom import (
    Assignment,
    ClassroomLink,
    Feedback,
    Question,
    Response,
    Submission,
)
from .client import Client, ClientAccess
from .credentials import OAuthToken, UserCredentials
from .device_code import DeviceCode
from .emailotp import EmailOTP
from .http.header import HttpHeader, HttpHeaderWithAuth
from .login import LoginSession
from .session import AuthSession
from .timetable import (
    LessonGroup,
    LessonGroupMember,
    Timetable,
    TimetableEntry,
    TimetableMetadata,
)
from .user import User
from .vault import Vault
