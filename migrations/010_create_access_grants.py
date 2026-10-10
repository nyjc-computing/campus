"""Create access_grants table, backfilling and retiring vault_access.

Revision ID: 010
Create Date: 2026-10-10

The generalized access-grant store (#883, #884): grant rows keyed by
(grantee_type, grantee_id, resource_type, resource_id) with a bitflag
mask for vault grants and a scope level for management grants. Every
existing vault_access row (client, label, access) is backfilled as a
(client, vault:<label>, bits) grant — ids and created_at are preserved
— and the retired table is dropped. downgrade() recreates vault_access
from the vault grant rows and drops access_grants (non-vault grants
are lost on downgrade; they postdate this revision by definition).

The DDL matches what TableInterface.init_from_model generates for
campus.model.AccessGrant. Run in the campus.auth context
(`railway ssh -s campus.auth`, then `python migrations/runner.py
apply`); non-production environments self-heal the new table at
startup but still need this run to carry existing vault_access rows
across. On an environment without vault_access (fresh database), the
DO block skips the backfill and drop — only the CREATE runs.
"""

from campus.storage.tables.backend.postgres import PostgreSQLTable

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS "access_grants" (
    "id" TEXT PRIMARY KEY NOT NULL,
    "created_at" TEXT NOT NULL,
    "grantee_type" TEXT NOT NULL,
    "grantee_id" TEXT NOT NULL,
    "resource_type" TEXT NOT NULL,
    "resource_id" TEXT NOT NULL,
    "bits" INTEGER,
    "level" TEXT
);
"""

_BACKFILL_SQL = """
DO $$
BEGIN
    IF to_regclass('vault_access') IS NOT NULL THEN
        INSERT INTO "access_grants" (
            "id", "created_at", "grantee_type", "grantee_id",
            "resource_type", "resource_id", "bits", "level"
        )
        SELECT
            "id", "created_at", 'client', "client_id",
            'vault', "label", "access", NULL
        FROM "vault_access"
        ON CONFLICT DO NOTHING;
        DROP TABLE "vault_access";
    END IF;
END $$;
"""

_DOWNGRADE_SQL = """
DO $$
BEGIN
    IF to_regclass('access_grants') IS NOT NULL THEN
        CREATE TABLE IF NOT EXISTS "vault_access" (
            "id" TEXT PRIMARY KEY NOT NULL,
            "created_at" TEXT NOT NULL,
            "client_id" TEXT NOT NULL,
            "label" TEXT NOT NULL,
            "access" INTEGER NOT NULL
        );
        INSERT INTO "vault_access" ("id", "created_at", "client_id", "label", "access")
        SELECT "id", "created_at", "grantee_id", "resource_id", "bits"
        FROM "access_grants"
        WHERE "grantee_type" = 'client'
          AND "resource_type" = 'vault'
          AND "bits" IS NOT NULL
        ON CONFLICT DO NOTHING;
        DROP TABLE "access_grants";
    END IF;
END $$;
"""


def upgrade():
    """Create access_grants, backfill from vault_access, drop it."""
    table = PostgreSQLTable("access_grants")
    table.init_from_schema(_CREATE_SQL)
    table.init_from_schema(_BACKFILL_SQL)


def downgrade():
    """Recreate vault_access from vault grants, drop access_grants."""
    table = PostgreSQLTable("vault_access")
    table.init_from_schema(_DOWNGRADE_SQL)
