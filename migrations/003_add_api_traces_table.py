"""Add spans table for audit/trace functionality.

Revision ID: 003
Create Date: 2025-04-08
"""

from campus.storage.tables.backend.postgres import PostgreSQLTable


def upgrade():
    """Create spans table with indexes for trace queries."""
    sql = """
    CREATE TABLE IF NOT EXISTS "spans" (
        "id" TEXT PRIMARY KEY,
        "trace_id" TEXT NOT NULL,
        "span_id" TEXT NOT NULL,
        "parent_span_id" TEXT,
        "method" TEXT NOT NULL,
        "path" TEXT NOT NULL,
        "query_params" JSONB DEFAULT '{}',
        "request_headers" JSONB DEFAULT '{}',
        "request_body" JSONB,
        "status_code" SMALLINT,
        "response_headers" JSONB DEFAULT '{}',
        "response_body" JSONB,
        "started_at" TIMESTAMPTZ NOT NULL,
        "duration_ms" NUMERIC(10,2) NOT NULL,
        "api_key_id" TEXT,
        "client_id" TEXT,
        "user_id" TEXT,
        "client_ip" INET,
        "user_agent" TEXT,
        "error_message" TEXT,
        "tags" JSONB DEFAULT '{}'
    );

    -- Indexes for common query patterns
    CREATE INDEX idx_spans_started_at ON "spans"("started_at" DESC);
    CREATE INDEX idx_spans_path ON "spans"("path", "started_at" DESC);
    CREATE INDEX idx_spans_api_key ON "spans"("api_key_id", "started_at" DESC);
    CREATE INDEX idx_spans_status ON "spans"("status_code") WHERE "status_code" >= 400;
    CREATE INDEX idx_spans_trace_id ON "spans"("trace_id");
    CREATE INDEX idx_spans_parent_span ON "spans"("trace_id", "parent_span_id");

    -- JSONB indexes for querying headers/bodies/tags
    CREATE INDEX idx_spans_tags ON "spans" USING GIN("tags");
    """

    table = PostgreSQLTable("spans")
    table.init_from_schema(sql)


def downgrade():
    """Drop spans table."""
    sql = "DROP TABLE IF EXISTS \"spans\";"
    table = PostgreSQLTable("spans")
    table.init_from_schema(sql)
