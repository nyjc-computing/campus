"""migrations._init

This module is used to initialize the start state for Campus.
"""

from apps import api as campus

# Create root and admin circles
root_circle = campus.circles.new(
    name="nyjc.edu.sg",
    description="Root circle",
    tag="root",
    parents={}
)
admin_circle = campus.circles.new(
    name="campus-admin",
    description="Campus admin circle",
    tag="admin",
    parents={root_circle["id"]: 15}
)

# Initialise venues
venues = (
    ("3-27", "Admin Block", "level 3", True),
    ("3-28", "Admin Block", "level 3", True),
    ("3-29", "Admin Block", "level 3", True),
    ("3-37", "Admin Block", "level 3", True),
    ("3-39", "Admin Block", "level 3", True),
    ("3-38", "Admin Block", "level 3", True),
    ("3-46", "Admin Block", "level 3", True),
    ("3-47", "Admin Block", "level 3", True),
    ("3-48", "Admin Block", "level 3", True),
    ("3-49", "Admin Block", "level 3", True),
    ("3-50", "Admin Block", "level 3", True),
    ("4-30", "Admin Block", "level 4", True),
    ("4-31", "Admin Block", "level 4", True),
    ("4-32", "Admin Block", "level 4", True),
    ("4-33", "Admin Block", "level 4", True),
    ("4-42", "Admin Block", "level 4", True),
    ("4-43", "Admin Block", "level 4", True),
    ("4-44", "Admin Block", "level 4", True),
    ("4-51", "Admin Block", "level 4", True),
    ("4-52", "Admin Block", "level 4", True),
    ("4-53", "Admin Block", "level 4", True),
    ("4-54", "Admin Block", "level 4", True),
    ("4-55", "Admin Block", "level 4", True),
    ("4-56", "Admin Block", "level 4", True),
    ("4-57", "Admin Block", "level 4", True),
    ("4-58", "Admin Block", "level 4", True),
    ("4-59", "Admin Block", "level 4", True),
    ("4-60", "Admin Block", "level 4", True),
    ("4-61", "Admin Block", "level 4", True),
    ("4-62", "Admin Block", "level 4", True),
    ("5-33", "Admin Block", "level 5", True),
    ("5-34", "Admin Block", "level 5", True),
    ("5-35", "Admin Block", "level 5", True),
    ("5-36", "Admin Block", "level 5", True),
    ("5-44", "Admin Block", "level 5", True),
    ("5-45", "Admin Block", "level 5", True),
    ("5-46", "Admin Block", "level 5", True),
    ("5-54", "Admin Block", "level 5", True),
    ("5-55", "Admin Block", "level 5", True),
    ("5-56", "Admin Block", "level 5", True),
    ("5-57", "Admin Block", "level 5", True),
    ("5-58", "Admin Block", "level 5", True),
    ("5-59", "Admin Block", "level 5", True),
    ("5-60", "Admin Block", "level 5", True),
    ("5-62", "Admin Block", "level 5", True),
    ("5-63", "Admin Block", "level 5", True),
    ("5-64", "Admin Block", "level 5", True),
    ("5-65", "Admin Block", "level 5", True),
    ("Art Room", "Admin Block", "level 2", False),
    ("AVA Room", "Admin Block", "level 5", True),
    ("Bio Lab 1", "Science Block", "level 2", True),
    ("Bio Lab 2", "Science Block", "level 2", True),
    ("C1", "Container Rooms", "level 1", True),
    ("C2", "Container Rooms", "level 1", True),
    ("C3", "Container Rooms", "level 1", True),
    ("C4", "Container Rooms", "level 1", True),
    ("Chem Lab 1", "Science Block", "level 1", True),
    ("Chem Lab 2", "Science Block", "level 1", True),
    ("Chem Lab 3", "Science Block", "level 1", True),
    ("Chem Lab 4", "Science Block", "level 1", True),
    ("Chem Lab 5", "Science Block", "level 1", True),
    ("Chem Lab 6", "Science Block", "level 1", True),
    ("Comp Lab 1", "Admin Block", "level 5", False),
    ("Comp Lab 2", "Admin Block", "level 5", False),
    ("Comp Lab 3", "Admin Block", "level 5", False),
    ("Comp Lab 4", "Admin Block", "level 5", False),
    ("Consultation Room 2", "Library", "level 4", False),
    ("i-space 1", "Science Block", "level 0", True),
    ("i-space 2", "Science Block", "level 0", True),
    ("ITR 1", "Admin Block", "level 5", True),
    ("ITR 2", "Admin Block", "level 5", True),
    ("LT 1", "Admin Block", "level 1", True),
    ("LT 2", "Admin Block", "level 1", True),
    ("LT 3", "Admin Block", "level 1", True),
    ("LT 4", "Admin Block", "level 2", True),
    ("Phy Lab 1", "Science Block", "level 2", True),
    ("Phy Lab 2", "Science Block", "level 2", True),
    ("Phy Lab 3", "Science Block", "level 2", True),
    ("Phy Lab 4", "Science Block", "level 2", True),
    ("Training Room", "Library", "level 4", False),
    ("Staffroom", "Admin Block", "level 3", False),
    ("Staff Workroom", "Staffroom", "level 3", True),
    ("Recording Pod (Chinese)", "Staffroom", "level 3", True),
    ("Recording Pod (GP)", "Staffroom", "level 3", True),
    ("Confab Room", "Admin Block", "level 2", True),
    ("Conference Room", "Admin Block", "level 2", True),
)

# for name, building, level, bookable in venues:
#     campus.venues.new(
#         name=name,
#         building=building,
#         level=level,
#         bookable=bookable,
#     )

holidays = (
    ("2025-01-01", "PUBLIC_HOLIDAY", "New Year's Day"),
    ("2025-01-29", "PUBLIC_HOLIDAY", "Chinese New Year"),
    ("2025-01-30", "PUBLIC_HOLIDAY", "Chinese New Year"),
    ("2025-03-31", "PUBLIC_HOLIDAY", "Hari Raya Puasa"),
    ("2025-04-18", "PUBLIC_HOLIDAY", "Good Friday"),
    ("2025-05-01", "PUBLIC_HOLIDAY", "Labour Day"),
    ("2025-05-12", "PUBLIC_HOLIDAY", "Vesak Day"),
    ("2025-06-07", "PUBLIC_HOLIDAY", "Hari Raya Haji"),
    ("2025-06-09", "DAY_OFF_IN_LIEU", "Hari Raya Haji (day off-in-lieu)"),
    ("2025-07-07", "SCHOOL_HOLIDAY", "Youth Day"),
    ("2025-08-09", "PUBLIC_HOLIDAY", "National Day"),
    ("2025-08-11", "DAY_OFF_IN_LIEU", "National Day (day off-in-lieu)"),
    ("2025-09-05", "SCHOOL_HOLIDAY", "Teachers' Day"),
    ("2025-10-20", "PUBLIC_HOLIDAY", "Deepavali"),
    ("2025-12-25", "PUBLIC_HOLIDAY", "Christmas Day"),
)
# for date, holiday_type, reason in holidays:
#     campus.timetable.holidays.set(
#         date=date,
#         type=holiday_type,
#         reason=reason
#     )

school_term = {
    "Term 1": {
        "start": "2025-01-13",
        "end": "2025-03-14",
        "start_week": 2
    },
    "Term 2": {
        "start": "2025-03-24",
        "end": "2025-05-30"
    },
    "Term 3": {
        "start": "2025-06-30",
        "end": "2025-09-05"
    },
    "Term 4": {
        "start": "2025-09-15",
        "end": "2025-11-28"
    }
}
# for label, term in school_term.items():
#     campus.timetable.schooldays.set(
#         start=term["start"],
#         end=term["end"],
#         start_week=term.get("start_week", 1)
#     )
