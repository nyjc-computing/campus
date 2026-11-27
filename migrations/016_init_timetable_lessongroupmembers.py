"""Create the timetable_lessongroupmembers table (#1331).

Revision ID: 016
Create Date: 2026-11-27

TARGET_DB is "api": the ``timetable_lessongroupmembers`` table lives in
**campus.api's postgres** — that is where TimetablesResource reads and
writes the per-version lesson-group roster (the members route, the
create-time roster bulk insert and the version delete cascade all go
through it).

`GET /api/v1/timetable/{id}/members` 500s on production with
``psycopg2.errors.UndefinedTable: relation "timetable_lessongroupmembers"
does not exist`` (#1331). Root cause: #1325 shipped the route together
with ``TimetablesResource.init_storage()``, which creates the table via
``init_from_model`` at boot — but production is migrations-only (#1103
blocks ``init_from_model`` in production), and no migration ever created
the table. It exists only where a non-production boot's startup init
ran. This migration is that missing DDL.

upgrade() replays the exact ``init_storage`` call, through the same
storage layer the resource uses — no service-module imports (protocol:
migrations run in contexts where only campus.storage and campus.model
resolve)::

    get_table("timetable_lessongroupmembers").init_from_model(
        "timetable_lessongroupmembers", model.LessonGroupMember
    )

The postgres backend's ``_model_to_sql_schema`` emits
``CREATE TABLE IF NOT EXISTS``, so the migration is idempotent — a
re-run (or an environment where dev's boot init already made the table)
is a no-op. The generated shape (campus-model 0.2.7) is ``id`` TEXT
PRIMARY KEY NOT NULL, ``created_at``/``timetable_id``/
``lessongroup_id``/``ade_participant`` TEXT NOT NULL. The model's
``__constraints__`` Unique(...) is a plain class attribute, not a
dataclass field, so the storage generators do not emit it as DDL (same
as every campus model — 013's precedent): the table carries no UNIQUE
constraint, byte-for-byte what ``init_storage`` creates, so dev and
prod converge on the same shape.

Non-production environments need no manual run: boot ``init_storage``
self-heals the table and the development startup auto-apply (#1256)
records this revision applied on the next deployment. Production is the
environment this fixes. ``init_from_model`` is production-blocked, so a
deliberate production run takes the documented per-process override
(``ENV=development`` on the runner invocation — runner.py docstring),
as the campus-migrate job context or ``railway ssh -s campus.api -e
production`` run requires:

    python migrations/runner.py --db api apply
"""

import campus.model as model
from campus.storage import get_table

TARGET_DB = "api"

ROLLBACK_SUPPORTED = "ddl"


def upgrade() -> None:
    """Create the timetable_lessongroupmembers table (idempotent).

    The same call TimetablesResource.init_storage() makes at boot in
    non-production environments (#1331 root cause).
    """
    get_table("timetable_lessongroupmembers").init_from_model(
        "timetable_lessongroupmembers",
        model.LessonGroupMember,
    )


def downgrade() -> None:
    """Drop the timetable_lessongroupmembers table (rows are lost —
    roster members only; versions, lessongroups and entries are
    unaffected). Non-production boots recreate the table at startup.
    """
    from campus.storage.tables.backend.postgres import PostgreSQLTable

    sql = 'DROP TABLE IF EXISTS "timetable_lessongroupmembers";'
    table = PostgreSQLTable("timetable_lessongroupmembers")
    table.init_from_schema(sql)
