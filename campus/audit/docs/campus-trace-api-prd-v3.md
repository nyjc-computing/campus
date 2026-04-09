# Campus Trace API — Product Requirements Document

**Programme:** Nanyang System Developers, Nanyang Junior College
**Status:** Draft
**Version:** 0.3
**Date:** 2026-04-08

---

## 1. Purpose

Campus is an HTTP API data backend designed for easy maintenance across complete student cohort turnover every two years. The Trace API is an internal observability service that records, stores, and exposes request-response traces for every API call passing through Campus. It serves two audiences:

- **Web frontend** — a browser-based dashboard for exploring traces, viewing waterfalls, and reviewing metrics during fortnightly and quarterly reviews.
- **CLI agents** — scripts and developer tools that query traces programmatically for debugging and automated analysis.

## 2. Goals

1. Provide full request-response trace capture for all Campus API traffic with zero manual instrumentation per endpoint.
2. Enable trace waterfall reconstruction showing parent-child span relationships and timing.
3. Surface operational metrics (throughput, latency, error rate, usage by client) to support fortnightly metrics reviews and quarterly strategic reviews.
4. Keep the system simple enough that an incoming student cohort can understand and maintain it without prior experience.

## 3. Non-Goals

- Distributed tracing across multiple services (Campus is a single API for now).
- Real-time alerting or anomaly detection.
- Log aggregation — this captures structured traces, not freeform logs.

## 4. Data Model

### 4.1 Schema

Each row in `api_traces` represents a single span (one request-response cycle).

| Column | Type | Description |
|---|---|---|
| `id` | UUID, PK | Internal row identifier |
| `trace_id` | TEXT, NOT NULL | Groups spans belonging to the same top-level request |
| `span_id` | TEXT | Unique identifier for this span |
| `parent_span_id` | TEXT, nullable | Parent span; NULL for root spans |
| `method` | TEXT, NOT NULL | HTTP method (GET, POST, etc.) |
| `path` | TEXT, NOT NULL | Request path (e.g. `/api/v1/students`) |
| `query_params` | JSONB | Query string parameters |
| `request_headers` | JSONB | Request headers (Authorization stripped) |
| `request_body` | JSONB | Request body |
| `status_code` | SMALLINT | HTTP response status |
| `response_headers` | JSONB | Response headers |
| `response_body` | JSONB | Response body (truncated to 64 KB) |
| `started_at` | TIMESTAMPTZ, NOT NULL | Span start time |
| `duration_ms` | NUMERIC(10,2) | Span duration in milliseconds |
| `api_key_id` | TEXT | API key used for this request |
| `client_id` | TEXT, nullable | OAuth client identifier; NULL until auth succeeds |
| `user_id` | TEXT, nullable | User identifier; NULL until auth succeeds |
| `client_ip` | INET | Client IP address |
| `user_agent` | TEXT | User-Agent header |
| `error_message` | TEXT | Error detail for failed requests |
| `tags` | JSONB | Arbitrary key-value metadata |

### 4.2 Indexes

| Index | Columns | Notes |
|---|---|---|
| `idx_traces_started_at` | `started_at DESC` | Default list ordering |
| `idx_traces_path` | `path, started_at DESC` | Filter by endpoint |
| `idx_traces_api_key` | `api_key_id, started_at DESC` | Per-client queries |
| `idx_traces_status` | `status_code` (partial: `>= 400`) | Error investigation |
| `idx_traces_trace_id` | `trace_id` | Trace lookup |
| `idx_traces_trace_span` | `trace_id, parent_span_id, span_id` | Recursive tree traversal |

### 4.3 Design Decisions

- **JSONB for headers and bodies.** Request/response shapes vary across endpoints. JSONB avoids schema migrations and allows ad-hoc queries via JSON operators.
- **`client_id` and `user_id` as nullable columns.** Identity is unknown until the auth span completes. Failed or unauthenticated requests leave these NULL.
- **`api_key_id` as a separate column from `client_id`.** API key identifies the credential used; client ID identifies the OAuth application. These may diverge as auth evolves.
- **Authorization headers stripped before storage.** The middleware must remove sensitive headers from `request_headers` before writing.

## 5. API Surface

### 5.1 Authentication

All Trace API endpoints require a valid API key passed via the `Authorization` header. The API key is recorded in the `api_key_id` column of each trace.

### 5.2 Request Identification

All requests include an `X-Request-ID` header for correlation. If the client provides one, the server uses it; otherwise the server generates a UUID. The server echoes the value back in the response `X-Request-ID` header. This value is stored as the `trace_id` for the corresponding trace.

ID values should use OpenTelemetry-compatible format (32 lowercase hex characters) to ease future migration to W3C Trace Context (see §9.8).

### 5.3 Content Negotiation

All GET endpoints support two representations via the `Accept` header:

| Accept | Format | Audience |
|---|---|---|
| `application/json` | Structured JSON | Web frontend |
| `text/plain` | Compact human-readable text | CLI agents, scripts |

### 5.4 Endpoints

#### Ingestion

**`POST /traces`** — Ingest spans.

Request body:

```json
{
  "spans": [
    {
      "trace_id": "string",
      "span_id": "string",
      "parent_span_id": "string | null",
      "method": "string",
      "path": "string",
      "status_code": 200,
      "started_at": "ISO 8601",
      "duration_ms": 142.5,
      "query_params": {},
      "request_headers": {},
      "request_body": null,
      "response_headers": {},
      "response_body": null,
      "client_id": "string | null",
      "user_id": "string | null",
      "api_key_id": "string",
      "client_ip": "string",
      "user_agent": "string",
      "error_message": "string | null",
      "tags": {}
    }
  ]
}
```

Accepts a single span or a batch. Returns `201 Created` with inserted span IDs on full success, or `207 Multi-Status` on partial failure with per-span status indicators so the caller can identify and retry failed spans.

#### Query — Traces

**`GET /traces`** — List recent traces, newest first.

Query params: `since`, `until`, `limit` (default 50).

Response includes a pagination cursor (`cursor.next`, `cursor.has_more`) based on keyset pagination over `started_at`. Pagination is not yet functional but the cursor is present in all responses to allow clients to adopt it without API changes.

JSON response:

```json
{
  "traces": [ ... ],
  "cursor": { "next": "ISO 8601", "has_more": true }
}
```

Plain text response:

```
trace abc123  142.5ms  OK   client:timetable-app  user:js
trace def456   15.8ms  FAIL client:—              user:—

--- more: cursor=2026-03-27T09:58:12.000Z ---
```

**`GET /traces/:traceId`** — Full trace tree with child spans.

JSON returns a nested tree structure with `children` arrays. Plain text returns an offset-timing waterfall:

```
trace abc123  142.5ms  OK  client:timetable-app  user:js

+0.0ms    142.5ms  GET /api/v1/students           200
+0.1ms    15.2ms     POST /auth/token/validate     200
+18.0ms   98.3ms     GET /api/v1/db/query          200
```

**`GET /traces/:traceId/spans/:spanId`** — Single span detail including full headers and bodies.

**`GET /traces/search`** — Filter traces.

Query params: `path`, `status` (e.g. `5xx`, `4xx`, `200`), `api_key_id`, `client_id`, `user_id`, `since`, `until`, `limit`.

#### Query — Metrics

**`GET /metrics/throughput`** — Requests per minute over a time window.

Query params: `window` (default `1h`), `bucket` (default `1m`), `path`.

**`GET /metrics/latency`** — Latency percentiles (p50, p90, p99) by endpoint.

Query params: `window` (default `24h`), `bucket` (default `1h`), `path`.

**`GET /metrics/errors`** — Error rate and top failing endpoints.

Query params: `window` (default `24h`), `path`.

**`GET /metrics/usage`** — DAU/MAU by API key or client.

Query params: `window` (default `30d`), `group_by` (`api_key_id` | `client_id`).

#### Operational

**`GET /health`** — Returns `200 OK` (plain text) or `{"status": "ok"}` (JSON).

## 6. Trace Reconstruction

The waterfall is reconstructed using a recursive CTE that walks the span tree from the root span (where `parent_span_id IS NULL`) through all children, producing depth-first chronological ordering. The `idx_traces_trace_span` composite index ensures this query is efficient.

Each span carries:

- **Offset from root start** (`+0.0ms`, `+12.0ms`) — when this span began relative to the trace.
- **Own duration** (`142.5ms`, `98.3ms`) — how long this span took.
- **Depth** — indentation level in the tree.

These three values are sufficient for both visual rendering (web frontend) and analytical queries (CLI agents).

## 7. Identity Resolution

OAuth token validation happens as a child span within each trace. The lifecycle:

1. Request arrives. Trace starts with `client_id` and `user_id` both NULL.
2. Auth span executes. On success, identity is resolved.
3. `client_id` and `user_id` are set on the root span and propagated to the trace record.

Three resulting states:

| State | `client_id` | `user_id` | Example |
|---|---|---|---|
| Auth succeeded | Populated | Populated | Normal authenticated request |
| Auth failed | NULL | NULL | Invalid token; trace has status 401 |
| No auth required | NULL | NULL | Health check, public endpoint |

## 8. Retention

Trace data is subject to a configurable retention window. A daily cleanup job deletes traces older than the window, chunked to avoid long database locks.

| Setting | Value | Notes |
|---|---|---|
| Current retention | 7 days | Suitable for development phase |
| Target retention | 3 years (1095 days) | Long-term target |
| Config key | `traceRetentionDays` | Single integer, no code change required to adjust |
| Cleanup method | Daily cron, chunked `DELETE` (10k rows per batch) | Upgrade to `pg_partman` monthly partitioning when moving to 3-year retention |

## 9. Implementation Notes

### 9.1 Middleware-Based Ingestion

Traces are captured by a middleware layer that automatically wraps each incoming request. This avoids per-endpoint instrumentation and ensures complete coverage. The middleware:

1. Starts a root span on request entry.
2. Captures method, path, headers (with Authorization stripped), and body.
3. Passes trace context to downstream handlers for child span creation.
4. On response completion, records status code, response data, and duration.
5. Writes the completed span(s) to the database via `POST /traces`.

### 9.2 OpenTelemetry Compatibility

The `trace_id` and `span_id` fields follow OpenTelemetry conventions (32 hex char trace IDs, 16 hex char span IDs), allowing future integration with OTel collectors or exporters (e.g. Jaeger, Grafana Tempo) without schema changes. Trace context is currently propagated via the `X-Request-ID` header (§5.2), with a planned upgrade path to W3C Trace Context headers (§9.8).

### 9.3 Sensitive Data

The middleware must strip the `Authorization` header from `request_headers` before writing. Other sensitive fields (e.g. tokens in request bodies) should be handled via a configurable redaction list.

### 9.4 Body Truncation

Response bodies are truncated to 64 KB before storage. Bodies exceeding this limit are cut at the byte boundary and a `_truncated: true` flag is added to the stored JSONB. Request bodies are stored in full, as they are typically small and under the caller's control.

### 9.5 CORS

The web frontend is expected to be served from the same origin as the Trace API. No CORS configuration is required. If this changes in future, standard CORS headers should be added to all endpoints.

### 9.6 Rate Limiting

Query endpoints are rate-limited per API key to prevent dashboard polling or runaway scripts from impacting Campus API performance.

| Endpoint group | Limit |
|---|---|
| `POST /traces` | 100 requests/second |
| `GET /traces/*`, `GET /traces/search` | 30 requests/minute |
| `GET /metrics/*` | 10 requests/minute |
| `GET /health` | No limit |

Exceeded limits return `429 Too Many Requests` with a `Retry-After` header. Implementation uses a simple sliding window counter per API key, stored in-memory (no external dependency like Redis needed at this scale).

### 9.7 Pagination (Future)

All list endpoints return cursor objects now. When implemented, pagination uses keyset pagination over `started_at` via a `cursor` query parameter. No endpoint signature changes required.

### 9.8 W3C Trace Context (Future)

The current `X-Request-ID` header provides request correlation. A future upgrade to W3C Trace Context (`Traceparent`/`Tracestate` headers per the W3C Trace Context specification) requires:

1. Parse the `Traceparent` header (`00-{trace_id}-{span_id}-{flags}`).
2. Enforce 32 hex char trace IDs and 16 hex char span IDs (already recommended in §5.2).
3. Echo `Traceparent` in responses.
4. Continue accepting `X-Request-ID` as a fallback for backward compatibility.

No database migration or endpoint changes are needed — the schema already stores trace and span IDs in compatible TEXT columns.

## 10. Resolved Decisions

| Question | Decision | Section |
|---|---|---|
| Batch write isolation | `207 Multi-Status` on partial failure with per-span results | §5.4 Ingestion |
| Span body storage | Response bodies truncated at 64 KB; request bodies stored in full | §9.4 Body Truncation |
| CORS | Same-origin; no CORS configuration needed | §9.5 CORS |
| Rate limiting | Sliding window per API key; 30/min for queries, 10/min for metrics | §9.6 Rate Limiting |
