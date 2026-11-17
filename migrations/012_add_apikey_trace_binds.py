"""Add trace-read scoping bind columns to the audit apikeys table.

Revision ID: 012
Create Date: 2026-11-17

TARGET_DB is "audit": the apikeys table belongs to the audit service
(its own postgres since the #970 split).

#944 per-key trace-read scoping: APIKey.trace_user_id /
APIKey.trace_client_id (campus-model v0.2.3) are opaque match-values
the audit service forces into every traces:read query. Both are
nullable TEXT — NULL on an axis means no bind on that axis, and NULL
on both means unscoped (the operator/admin key class), so existing
keys keep their current global-read behavior until a scoped key is
explicitly minted.

Idempotent (ADD COLUMN IF NOT EXISTS): safe to re-run against any
environment where the columns were added by other means. Backfill is
not needed — the unscoped-NULL default IS the desired state for every
pre-existing key.
"""

from campus.storage.tables.backend.postgres import PostgreSQLTable

TARGET_DB = "audit"


def upgrade():
    """Add nullable trace_user_id / trace_client_id TEXT columns."""
    sql = """
    ALTER TABLE "apikeys"
    ADD COLUMN IF NOT EXISTS "trace_user_id" TEXT,
    ADD COLUMN IF NOT EXISTS "trace_client_id" TEXT;
    """
    table = PostgreSQLTable("apikeys")
    table.init_from_schema(sql)


def downgrade():
    """Drop the trace bind columns (reads then treat every key as
    unscoped again, matching pre-#944 behavior)."""
    sql = """
    ALTER TABLE "apikeys"
    DROP COLUMN IF EXISTS "trace_user_id",
    DROP COLUMN IF EXISTS "trace_client_id";
    """
    table = PostgreSQLTable("apikeys")
    table.init_from_schema(sql)
