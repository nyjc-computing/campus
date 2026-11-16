"""Add token_bridge column to vault_clients table.

Revision ID: 008
Create Date: 2026-10-02

The token-bridge work (#705, docs/auth-token-invariants.md C1) adds
Client.token_bridge: only confidential clients flagged for bridge
access may release a user's upstream access tokens via
/auth/v1/broker. CREATE TABLE IF NOT EXISTS (init_storage) does not
alter an existing table, so deployments whose vault_clients table
predates this change lack the column: reads tolerate their absence,
but inserting a client fails with UndefinedColumn.

The DEFAULT clause backfills existing rows as False — fail-closed:
no client may use the bridge until an admin sets token_bridge
(PATCH /clients/{id}/).
"""

from campus.storage.tables.backend.postgres import PostgreSQLTable


def upgrade():
    """Add token_bridge column to vault_clients."""
    sql = """
    ALTER TABLE "vault_clients" ADD COLUMN IF NOT EXISTS "token_bridge" BOOLEAN NOT NULL DEFAULT FALSE;
    """

    table = PostgreSQLTable("vault_clients")
    table.init_from_schema(sql)


def downgrade():
    """Drop the token_bridge column from vault_clients."""
    sql = """
    ALTER TABLE "vault_clients" DROP COLUMN IF EXISTS "token_bridge";
    """

    table = PostgreSQLTable("vault_clients")
    table.init_from_schema(sql)
