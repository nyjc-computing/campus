"""Create the venue bookings table (campus#1217).

Revision ID: 013
Create Date: 2026-11-23

One row per venue booking (campus.model.VenueBooking): who booked
(user_id), which venue, the purpose text, the HHMM start/end times
and the ISO date, and the approval lifecycle status — "pending" on
creation, decided ("approved"/"denied") by the venue authority
(venues.admin globally, or the venue category's
venues.<category>.admin circle). The exact-duplicate guard (same
venue, date, start and end time) is app-layer in
resources/booking.new: the model's __constraints__ declaration is
not emitted as DDL by the storage generators (same as every campus
model), so the table carries no UNIQUE constraint — matching
init_from_model output byte for byte.

The DDL matches what TableInterface.init_from_model generates for
campus.model.VenueBooking (campus-model 0.2.6). TARGET_DB is "api":
the `venue_bookings` table lives in **campus.api's postgres** (that
is where the bookings routes read it and where dev's startup
self-heal creates it via _init_api_tables) — run the runner in the
api service's context (`railway ssh -s campus.api`, then `python
migrations/runner.py --db api apply`). Non-production environments
self-heal the table at startup, so this run is only required on
production. Idempotent: the CREATE is IF NOT EXISTS.
"""

from campus.storage.tables.backend.postgres import PostgreSQLTable

TARGET_DB = "api"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS "venue_bookings" (
    "id" TEXT PRIMARY KEY NOT NULL,
    "created_at" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "venue_id" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "start_time" TEXT NOT NULL,
    "end_time" TEXT NOT NULL,
    "date" TEXT NOT NULL,
    "status" TEXT NOT NULL
);
"""

_DOWNGRADE_SQL = """
DROP TABLE IF EXISTS "venue_bookings";
"""


def upgrade() -> None:
    """Create the venue bookings table (idempotent)."""
    backend = PostgreSQLTable("venue_bookings")
    backend.init_from_schema(_CREATE_SQL)


def downgrade() -> None:
    """Drop the venue bookings table (rows are lost — bookings only)."""
    backend = PostgreSQLTable("venue_bookings")
    backend.init_from_schema(_DOWNGRADE_SQL)
