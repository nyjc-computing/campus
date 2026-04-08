"""Add api_traces table for audit/trace functionality.

Revision ID: 003
Create Date: 2025-04-08
"""

from campus.storage.tables.backend.postgres import PostgreSQLTable


def upgrade():
    """Create api_traces table with indexes for trace queries."""
    sql = """
    CREATE TABLE IF NOT EXISTS "api_traces" (
        "id" TEXT PRIMARY KEY,
        "trace_id" TEXT NOT NULL,
        "span_id" TEXT UNIQUE,
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
    CREATE INDEX idx_traces_started_at ON "api_traces"("started_at" DESC);
    CREATE INDEX idx_traces_path ON "api_traces"("path", "started_at" DESC);
    CREATE INDEX idx_traces_api_key ON "api_traces"("api_key_id", "started_at" DESC);
    CREATE INDEX idx_traces_status ON "api_traces"("status_code") WHERE "status_code" >= 400;
    CREATE INDEX idx_traces_trace_id ON "api_traces"("trace_id");
    CREATE INDEX idx_traces_trace_span ON "api_traces"("trace_id", "parent_span_id", "span_id");

    -- JSONB indexes for querying headers/bodies/tags
    CREATE INDEX idx_traces_tags ON "api_traces" USING GIN("tags");
    """

    table = PostgreSQLTable("api_traces")
    table.init_from_schema(sql)


def downgrade():
    """Drop api_traces table."""
    sql = "DROP TABLE IF EXISTS \"api_traces\";"
    table = PostgreSQLTable("api_traces")
    table.init_from_schema(sql)
