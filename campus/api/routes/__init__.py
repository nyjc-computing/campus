"""campus.api.routes

This is a namespace module for the Campus API routes.
"""

__all__ = [
    "bookings",
    "calendar",
    "circles",
    "emailotp",
    "assignments",
    "files",
    "hostedapps",
    "subjcombi",
    "submissions",
    "timetable",
]

from . import (
    assignments,
    bookings,
    calendar,
    circles,
    emailotp,
    files,
    hostedapps,
    subjcombi,
    submissions,
    timetable,
)
