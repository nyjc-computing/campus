"""Create the calendar table (the school calendar, timetable-v2).

Revision ID: 011
Create Date: 2026-11-11

One row per calendar date (campus.model.CalendarDay, keyed by the ISO
date itself): which TT day each cohort runs — j1_code / j2_code from
the ten-TT-day + "Free" vocabulary — plus the seeded term_week label.
The Manage Calendar editor writes one date at a time; the year seed
uses the bulk upsert. The version in force is NOT calendar data (the
timetable pointer trail owns it), matching v1's calendar-editor
boundary.

The DDL matches what TableInterface.init_from_model generates for
campus.model.CalendarDay. Run in the campus.auth context
(`railway ssh -s campus.auth`, then `python migrations/runner.py
apply`); non-production environments self-heal the table at startup
(campus.api's _init_api_tables), so this run is only required on
production. Idempotent: the CREATE is IF NOT EXISTS.
"""

from campus.storage.tables.backend.postgres import PostgreSQLTable

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS "calendar" (
    "id" TEXT PRIMARY KEY NOT NULL,
    "created_at" TEXT NOT NULL,
    "j1_code" TEXT ,
    "j2_code" TEXT ,
    "term_week" TEXT
);
"""

_DOWNGRADE_SQL = """
DROP TABLE IF EXISTS "calendar";
"""


def upgrade() -> None:
    """Create the calendar table (idempotent)."""
    backend = PostgreSQLTable("calendar")
    backend.init_from_schema(_CREATE_SQL)


def downgrade() -> None:
    """Drop the calendar table (rows are lost — the seed regenerates)."""
    backend = PostgreSQLTable("calendar")
    backend.init_from_schema(_DOWNGRADE_SQL)
