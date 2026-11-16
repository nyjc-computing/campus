"""Add allowed_scopes column to vault_clients table.

Revision ID: 006
Create Date: 2026-10-02

The scope-allowlist work (#705, docs/auth-token-invariants.md A1)
adds Client.allowed_scopes: the fail-closed list of scopes a client
may be granted on Campus tokens. CREATE TABLE IF NOT EXISTS
(init_storage) does not alter an existing table, so deployments whose
vault_clients table predates this change lack the column: reads
tolerate its absence, but inserting a client fails with
UndefinedColumn.

The DEFAULT clause backfills existing rows with an empty allowlist —
fail-closed: those clients cannot be granted scopes until an admin
sets allowed_scopes (PATCH /clients/{id}/) to the scopes the client
was approved for.
"""

from campus.storage.tables.backend.postgres import PostgreSQLTable


def upgrade():
    """Add allowed_scopes column to vault_clients."""
    sql = """
    ALTER TABLE "vault_clients" ADD COLUMN IF NOT EXISTS "allowed_scopes" TEXT NOT NULL DEFAULT '[]';
    """

    table = PostgreSQLTable("vault_clients")
    table.init_from_schema(sql)


def downgrade():
    """Drop the allowed_scopes column from vault_clients."""
    sql = """
    ALTER TABLE "vault_clients" DROP COLUMN IF EXISTS "allowed_scopes";
    """

    table = PostgreSQLTable("vault_clients")
    table.init_from_schema(sql)
