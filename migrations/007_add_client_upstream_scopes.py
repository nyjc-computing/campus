"""Add upstream_scopes column to vault_clients table.

Revision ID: 007
Create Date: 2026-10-02

The upstream-scope work (#705, docs/auth-token-invariants.md B3) adds
Client.upstream_scopes: the per-provider allowlist of third-party
(e.g. Google) scopes a client may be granted through Campus's OAuth
proxies. CREATE TABLE IF NOT EXISTS (init_storage) does not alter an
existing table, so deployments whose vault_clients table predates this
change lack the column: reads tolerate its absence, but inserting a
client fails with UndefinedColumn.

The DEFAULT clause backfills existing rows with an empty object —
fail-closed: those clients receive only the proxies' base scopes until
an admin sets upstream_scopes (PATCH /clients/{id}/) to the provider
scopes the client was approved for.
"""

from campus.storage.tables.backend.postgres import PostgreSQLTable


def upgrade():
    """Add upstream_scopes column to vault_clients."""
    sql = """
    ALTER TABLE "vault_clients" ADD COLUMN IF NOT EXISTS "upstream_scopes" TEXT NOT NULL DEFAULT '{}';
    """

    table = PostgreSQLTable("vault_clients")
    table.init_from_schema(sql)


def downgrade():
    """Drop the upstream_scopes column from vault_clients."""
    sql = """
    ALTER TABLE "vault_clients" DROP COLUMN IF EXISTS "upstream_scopes";
    """

    table = PostgreSQLTable("vault_clients")
    table.init_from_schema(sql)
