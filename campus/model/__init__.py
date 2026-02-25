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
    "EmailOTP",
    "Feedback",
    "HttpHeader",
    "HttpHeaderWithAuth",
    "InternalModel",
    "LoginSession",
    "Model",
    "Question",
    "OAuthToken",
    "Response",
    "Submission",
    "User",
    "UserCredentials",
    "Vault",
    "WeekDay",
    "TimeSlot",
    "VenueTimeSlot",
    "LessonGroup",
    "TimetableEntry",
    "Timetable",
]

from .assignment import Assignment, ClassroomLink, Question
from .base import InternalModel, Model
from .circle import Circle
from .client import Client, ClientAccess
from .credentials import OAuthToken, UserCredentials
from .http.header import HttpHeader, HttpHeaderWithAuth
from .emailotp import EmailOTP
from .login import LoginSession
from .session import AuthSession
from .submission import Feedback, Response, Submission
from .user import User
from .vault import Vault
from .timetable import WeekDay, TimeSlot, VenueTimeSlot, LessonGroup, TimetableEntry, Timetable
