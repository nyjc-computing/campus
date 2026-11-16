"""Add submissions table.

Revision ID: 002
Create Date: 2025-01-29
"""
from campus.storage.tables.backend.postgres import PostgreSQLTable


def upgrade():
    """Create submissions table."""
    sql = """
    CREATE TABLE IF NOT EXISTS "submissions" (
        "id" TEXT PRIMARY KEY,
        "created_at" TIMESTAMP NOT NULL,
        "assignment_id" TEXT NOT NULL,
        "student_id" TEXT NOT NULL,
        "course_id" TEXT NOT NULL,
        "responses" JSONB NOT NULL DEFAULT '[]',
        "feedback" JSONB NOT NULL DEFAULT '[]',
        "submitted_at" TIMESTAMP,
        "updated_at" TIMESTAMP NOT NULL,
        CONSTRAINT fk_assignment FOREIGN KEY ("assignment_id")
            REFERENCES "assignments"("id") ON DELETE CASCADE
    );

    CREATE INDEX idx_submissions_assignment ON "submissions"("assignment_id");
    CREATE INDEX idx_submissions_student ON "submissions"("student_id");
    CREATE INDEX idx_submissions_course ON "submissions"("course_id");
    CREATE INDEX idx_submissions_responses ON "submissions" USING GIN("responses");
    CREATE INDEX idx_submissions_feedback ON "submissions" USING GIN("feedback");

    -- One submission per student per assignment per course
    CREATE UNIQUE INDEX idx_submissions_unique
        ON "submissions"("assignment_id", "student_id", "course_id");
    """

    table = PostgreSQLTable("submissions")
    table.init_from_schema(sql)


def downgrade():
    """Drop submissions table."""
    sql = "DROP TABLE IF EXISTS \"submissions\";"
    table = PostgreSQLTable("submissions")
    table.init_from_schema(sql)
