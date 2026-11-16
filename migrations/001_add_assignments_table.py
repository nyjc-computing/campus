"""Add assignments table.

Revision ID: 001
Create Date: 2025-01-28
"""
from campus.storage.tables.backend.postgres import PostgreSQLTable


def upgrade():
    """Create assignments table."""
    sql = """
    CREATE TABLE IF NOT EXISTS "assignments" (
        "id" TEXT PRIMARY KEY,
        "created_at" TIMESTAMP NOT NULL,
        "title" TEXT NOT NULL,
        "description" TEXT NOT NULL DEFAULT '',
        "questions" JSONB NOT NULL DEFAULT '[]',
        "created_by" TEXT NOT NULL,
        "updated_at" TIMESTAMP NOT NULL,
        "classroom_links" JSONB NOT NULL DEFAULT '[]'
    );

    CREATE INDEX idx_assignments_created_by ON "assignments"("created_by");
    CREATE INDEX idx_assignments_questions ON "assignments" USING GIN("questions");
    CREATE INDEX idx_assignments_classroom_links ON "assignments" USING GIN("classroom_links");
    """

    table = PostgreSQLTable("assignments")
    table.init_from_schema(sql)


def downgrade():
    """Drop assignments table."""
    sql = "DROP TABLE IF EXISTS \"assignments\";"
    table = PostgreSQLTable("assignments")
    table.init_from_schema(sql)
