"""Add public client columns to vault_clients table.

Revision ID: 004
Create Date: 2026-09-29

Adds the is_public and redirect_uris columns introduced by the public
OAuth client support (PR #604) to deployments whose vault_clients table
predates that change. CREATE TABLE IF NOT EXISTS does not alter an
existing table, so databases initialized before PR #604 lack these
columns: reads tolerate their absence, but any INSERT naming them fails
with UndefinedColumn.

The DEFAULT clauses backfill existing rows (all pre-existing clients
are confidential) and are required because the columns are NOT NULL.
"""

from campus.storage.tables.backend.postgres import PostgreSQLTable


def upgrade():
    """Add is_public and redirect_uris columns to vault_clients."""
    sql = """
    ALTER TABLE "vault_clients" ADD COLUMN IF NOT EXISTS "is_public" BOOLEAN NOT NULL DEFAULT FALSE;
    ALTER TABLE "vault_clients" ADD COLUMN IF NOT EXISTS "redirect_uris" TEXT NOT NULL DEFAULT '[]';
    """

    table = PostgreSQLTable("vault_clients")
    table.init_from_schema(sql)


def downgrade():
    """Drop public client columns from vault_clients."""
    sql = """
    ALTER TABLE "vault_clients" DROP COLUMN IF EXISTS "is_public";
    ALTER TABLE "vault_clients" DROP COLUMN IF EXISTS "redirect_uris";
    """

    table = PostgreSQLTable("vault_clients")
    table.init_from_schema(sql)
