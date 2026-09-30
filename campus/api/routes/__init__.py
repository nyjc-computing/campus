"""campus.apps.api.routes

This is a namespace module for the Campus API routes.
"""

__all__ = [
    "bookings",
    "circles",
    "emailotp",
    "assignments",
    "submissions",
    "timetable",
]

from . import (
    assignments,
    bookings,
    circles,
    emailotp,
    submissions,
    timetable,
)
