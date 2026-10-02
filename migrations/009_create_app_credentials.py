"""Create app_credentials table.

Revision ID: 009
Create Date: 2026-10-02

The client_credentials grant (RFC 6749 section 4.4, campus#334) issues
client-scoped tokens with no user: AppCredentials links a confidential
client to its single live app token, so bearer authentication
(POST /root/authenticate with a token) can resolve app tokens to the
client alone. The DDL matches what TableInterface.init_from_model
generates for campus.model.AppCredentials; production blocks
init_from_model, so deployments need this migration.
"""

from campus.storage.tables.backend.postgres import PostgreSQLTable


def upgrade():
    """Create app_credentials table."""
    sql = """
    CREATE TABLE IF NOT EXISTS "app_credentials" (
        "id" TEXT PRIMARY KEY NOT NULL,
        "created_at" TEXT NOT NULL,
        "client_id" TEXT NOT NULL,
        "token_id" TEXT UNIQUE NOT NULL
    );
    """
    table = PostgreSQLTable("app_credentials")
    table.init_from_schema(sql)


def downgrade():
    """Drop app_credentials table."""
    sql = 'DROP TABLE IF EXISTS "app_credentials";'
    table = PostgreSQLTable("app_credentials")
    table.init_from_schema(sql)
