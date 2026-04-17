# Implementation Plan: Campus Trace API (Issue 424)

## Overview

Create a new `campus.audit` deployment that implements the Campus Trace API as specified in [campus-trace-api-prd-v3.md](./docs/campus-trace-api-prd-v3.md).

## 1. Models (`campus.model`)

### 1.1 Trace Span Model (`campus.model.TraceSpan`)

Location: `campus/model/trace.py`

```python
from dataclasses import dataclass, field
from typing import Any
from campus.common import schema
from campus.model.base import InternalModel

@dataclass(kw_only=True)
class TraceSpan(InternalModel):
    """Represents a single span in a trace."""

    # Primary identifiers
    id: schema.CampusID
    trace_id: str  # 32-char hex (OpenTelemetry-compatible)
    span_id: str   # 16-char hex (OpenTelemetry-compatible)
    parent_span_id: str | None = None

    # Request data
    method: str  # GET, POST, etc.
    path: str
    query_params: dict[str, Any] = field(default_factory=dict)
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: dict[str, Any] | None = None

    # Response data
    status_code: int | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: dict[str, Any] | None = None

    # Timing
    started_at: schema.DateTime
    duration_ms: float  # NUMERIC(10,2)

    # Identity (nullable - populated after auth)
    api_key_id: str | None = None
    client_id: str | None = None
    user_id: str | None = None

    # Client info
    client_ip: str  # INET type
    user_agent: str | None = None

    # Error info
    error_message: str | None = None

    # Metadata
    tags: dict[str, Any] = field(default_factory=dict)
```

### 1.2 Database Schema

Table: `api_traces`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID (PK) | |
| `trace_id` | TEXT, NOT NULL | |
| `span_id` | TEXT | UNIQUE |
| `parent_span_id` | TEXT | nullable |
| `method` | TEXT, NOT NULL | |
| `path` | TEXT, NOT NULL | |
| `query_params` | JSONB | |
| `request_headers` | JSONB | |
| `request_body` | JSONB | |
| `status_code` | SMALLINT | |
| `response_headers` | JSONB | |
| `response_body` | JSONB | |
| `started_at` | TIMESTAMPTZ, NOT NULL | |
| `duration_ms` | NUMERIC(10,2) | |
| `api_key_id` | TEXT | |
| `client_id` | TEXT | |
| `user_id` | TEXT | |
| `client_ip` | INET | |
| `user_agent` | TEXT | |
| `error_message` | TEXT | |
| `tags` | JSONB | |

### 1.3 Indexes

```sql
CREATE INDEX idx_traces_started_at ON api_traces(started_at DESC);
CREATE INDEX idx_traces_path ON api_traces(path, started_at DESC);
CREATE INDEX idx_traces_api_key ON api_traces(api_key_id, started_at DESC);
CREATE INDEX idx_traces_status ON api_traces(status_code) WHERE status_code >= 400;
CREATE INDEX idx_traces_trace_id ON api_traces(trace_id);
CREATE INDEX idx_traces_trace_span ON api_traces(trace_id, parent_span_id, span_id);
```

## 2. Blueprint Structure

### 2.1 Module Organization

```
campus/audit/
├── __init__.py           # Blueprint initialization
├── docs/                 # Documentation (already exists)
│   └── campus-trace-api-prd-v3.md
├── model.py              # TraceSpan model definition
├── resources/            # Data access layer
│   ├── __init__.py
│   └── traces.py         # Trace resource operations
├── routes/               # HTTP route handlers
│   ├── __init__.py
│   ├── traces.py         # Trace endpoints (GET/POST /traces, etc.)
│   ├── metrics.py        # Metrics endpoints (future work)
│   └── health.py         # Health check endpoint
├── middleware/           # Trace capture middleware
│   ├── __init__.py
│   └── tracing.py        # Request tracing middleware
└── templates/            # Web UI templates
    ├── base.html
    ├── traces.html
    └── trace_detail.html
```

### 2.2 Blueprint Initialization (`campus.audit.__init__.py`)

```python
"""campus.audit

Trace API and observability service for Campus.
"""

__all__ = ["init_app"]

import flask

def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialize the audit blueprint."""
    from . import middleware, resources, routes

    bp = flask.Blueprint("audit", __name__, url_prefix="/audit/v1")

    # Initialize storage
    resources.traces.TraceResource.init_storage()

    # Register routes
    routes.traces.init_app(bp)
    routes.health.init_app(bp)
    # routes.metrics.init_app(bp)  # Future work

    # Register middleware (if app is Flask)
    if isinstance(app, flask.Flask):
        middleware.tracing.init_app(app)

    app.register_blueprint(bp)
```

## 3. Route Structure & Authentication

### 3.1 Authentication Strategy: **Bearer Auth**

**Decision:** Use Bearer token authentication for audit endpoints.

**Rationale:**
- Audit endpoints are internal observability tools, not public-facing
- Bearer tokens align with OAuth2 flows already in use in Campus
- Allows service-to-service authentication for middleware ingestion
- Basic auth is simpler but less suitable for programmatic access

**Implementation:**
```python
@bp.before_request
def authenticate():
    """Validate API key for audit endpoints."""
    from campus.common.webauth import http
    from campus.common.errors import auth_errors

    # Health check is public
    if flask.request.path.endswith("/health"):
        return

    httpauth = http.HttpAuthenticationScheme.with_header(
        provider="audit",
        http_header=dict(flask.request.headers)
    )

    if not httpauth.header or not httpauth.header.authorization:
        raise auth_errors.UnauthorizedClientError("Missing Authorization header")

    if httpauth.scheme != "bearer":
        raise auth_errors.InvalidRequestError("Only Bearer authentication supported")

    token = httpauth.header.authorization.token
    # Validate against campus.auth or internal audit API keys
    if not _validate_audit_token(token):
        raise auth_errors.UnauthorizedClientError("Invalid audit API key")
```

### 3.2 Route Endpoints

#### 3.2.1 Trace Routes (`routes/traces.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/traces` | POST | Ingest spans (batch or single) |
| `/traces` | GET | List recent traces |
| `/traces/<trace_id>` | GET | Get full trace tree |
| `/traces/<trace_id>/spans/<span_id>` | GET | Get single span detail |
| `/traces/search` | GET | Filter/search traces |

#### 3.2.2 Health Route (`routes/health.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (no auth required) |

#### 3.2.3 Metrics Routes (Future Work - `routes/metrics.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/metrics/throughput` | GET | Requests per minute |
| `/metrics/latency` | GET | Latency percentiles |
| `/metrics/errors` | GET | Error rate |
| `/metrics/usage` | GET | DAU/MAU by client |

## 4. Resources Layer (`resources/traces.py`)

Following the pattern from `campus.auth.resources`:

```python
"""campus.audit.resources.traces

Data access layer for trace spans.
"""

import typing
from campus.common import schema
from campus.model import TraceSpan
import campus.storage

traces_storage = campus.storage.get_table("api_traces")

class TraceResource:
    """Resource for individual trace operations."""

    @staticmethod
    def init_storage() -> None:
        """Initialize traces table from model."""
        traces_storage.init_from_model("api_traces", TraceSpan)

    def insert_span(self, span: TraceSpan) -> schema.CampusID:
        """Insert a single span."""
        traces_storage.insert_one(span.to_storage())
        return span.id

    def insert_batch(self, spans: list[TraceSpan]) -> dict[int, Exception]:
        """Insert multiple spans, returning any errors."""
        rows = [span.to_storage() for span in spans]
        return traces_storage.insert_many(rows, max_retries=2)

    def get_trace_tree(self, trace_id: str) -> list[TraceSpan]:
        """Get all spans for a trace as a tree."""
        # Uses recursive CTE for parent-child traversal
        records = traces_storage.get_matching({"trace_id": trace_id})
        return [TraceSpan.from_storage(r) for r in records]

    def list_recent(self, since: schema.DateTime | None = None,
                    limit: int = 50) -> list[TraceSpan]:
        """List recent root spans."""
        query = {}
        if since:
            query["started_at"] = {"$gte": since}
        records = traces_storage.get_matching(query, limit=limit)
        return [TraceSpan.from_storage(r) for r in records]

    # ... additional methods for search, filtering, etc.
```

## 5. Web UI

### 5.1 Technology Stack: **Flask + Vanilla JavaScript**

**Decision:** Use plain Flask templates with vanilla JavaScript.

**Rationale:**
- No build step or framework dependencies
- Aligns with Campus philosophy of simplicity
- Sufficient for the requirements (trace explorer, waterfall view)
- Easy for incoming cohorts to understand and modify

### 5.2 UI Components

| Page | Purpose |
|------|---------|
| `/` | Trace list with search/filter |
| `/trace/<trace_id>` | Trace detail with waterfall visualization |
| `/metrics` | Metrics dashboard (future work) |

### 5.3 Template Structure (`templates/`)

```html
<!-- templates/base.html -->
<!DOCTYPE html>
<html>
<head>
    <title>Campus Trace Explorer</title>
    <link rel="stylesheet" href="/static/audit.css">
</head>
<body>
    <nav>
        <a href="/">Traces</a>
        <a href="/metrics">Metrics</a>
    </nav>
    <main>{% block content %}{% endblock %}</main>
    <script src="/static/audit.js"></script>
</body>
</html>
```

### 5.4 Waterfall Visualization

Vanilla JS implementation using offset/duration data:

```javascript
// Render span waterfall
function renderWaterfall(spans) {
    const container = document.getElementById('waterfall');
    spans.forEach(span => {
        const row = document.createElement('div');
        row.className = 'span-row';
        row.innerHTML = `
            <div class="span-offset">${span.offset_ms.toFixed(1)}ms</div>
            <div class="span-bar" style="width: ${span.duration_ms}ms; margin-left: ${span.offset_ms}px">
                <span class="span-method">${span.method}</span>
                <span class="span-path">${span.path}</span>
                <span class="span-status">${span.status_code}</span>
            </div>
        `;
        container.appendChild(row);
    });
}
```

## 6. Middleware for Trace Capture

### 6.1 Tracing Middleware (`middleware/tracing.py`)

```python
"""campus.audit.middleware.tracing

Request tracing middleware for automatic span capture.
"""

import flask
import uuid
import time
from campus.audit.model import TraceSpan
from campus.audit.resources import traces
from campus.common import schema

def init_app(app: flask.Flask) -> None:
    """Register tracing middleware."""

    @app.before_request
    def start_span():
        """Start a root span for each request."""
        # Generate or use existing trace ID
        trace_id = flask.request.headers.get('X-Request-ID') or _generate_trace_id()
        span_id = _generate_span_id()

        flask.g.trace_start = time.time()
        flask.g.trace_id = trace_id
        flask.g.span_id = span_id

    @app.after_request
    def end_span(response):
        """Complete and record the span."""
        if not hasattr(flask.g, 'trace_start'):
            return response

        duration_ms = (time.time() - flask.g.trace_start) * 1000

        # Strip Authorization header
        headers = dict(flask.request.headers)
        headers.pop('Authorization', None)

        span = TraceSpan(
            id=schema.CampusID.new(),
            trace_id=flask.g.trace_id,
            span_id=flask.g.span_id,
            parent_span_id=None,
            method=flask.request.method,
            path=flask.request.path,
            query_params=dict(flask.request.args),
            request_headers=headers,
            request_body=_get_request_body(),
            status_code=response.status_code,
            response_headers=dict(response.headers),
            response_body=_get_response_body(response),
            started_at=schema.DateTime.utcnow(),
            duration_ms=duration_ms,
            client_ip=flask.request.remote_addr,
            user_agent=flask.request.headers.get('User-Agent'),
        )

        # Send to trace API asynchronously
        _ingest_span(span)

        # Echo trace ID
        response.headers['X-Request-ID'] = flask.g.trace_id

        return response

def _generate_trace_id() -> str:
    """Generate OpenTelemetry-compatible trace ID (32 hex chars)."""
    return uuid.uuid4().hex + uuid.uuid4().hex[:16]

def _generate_span_id() -> str:
    """Generate OpenTelemetry-compatible span ID (16 hex chars)."""
    return uuid.uuid4().hex[:16]

def _get_request_body() -> dict | None:
    """Safely extract request body."""
    # Implementation handles JSON parsing
    ...

def _get_response_body(response) -> dict | None:
    """Extract response body with 64KB truncation."""
    # Implementation handles truncation
    ...
```

## 7. Configuration

### 7.1 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AUDIT_API_KEY` | API key for audit endpoints | (required) |
| `AUDIT_RETENTION_DAYS` | Trace retention period | 7 |
| `AUDIT_INGESTION_RATE_LIMIT` | Max POST /traces requests/sec | 100 |
| `AUDIT_QUERY_RATE_LIMIT` | Max GET requests/min | 30 |

## 8. Future Considerations

### 8.1 Metrics (Planned)

The blueprint structure anticipates metrics endpoints. Implementation will:

1. Add `campus/model/metrics.py` with aggregation models
2. Implement `routes/metrics.py` with percentile calculations
3. Use SQL aggregates for efficient computation

### 8.2 W3C Trace Context (Planned)

Future upgrade path:

1. Parse `Traceparent` header: `00-{trace_id}-{span_id}-{flags}`
2. Enforce 32-char trace IDs, 16-char span IDs
3. Maintain `X-Request-ID` fallback compatibility

### 8.3 Cleanup Job

Daily cron to delete old traces:

```python
def cleanup_old_traces():
    """Delete traces older than retention period."""
    retention = int(os.getenv('AUDIT_RETENTION_DAYS', 7))
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
    traces_storage.delete_matching({
        "started_at": {"$lt": cutoff.isoformat()}
    })
```

## 9. Testing Strategy

1. **Unit Tests**: Model validation, resource layer
2. **Contract Tests**: API endpoint behavior
3. **Integration Tests**: Middleware capture, trace tree reconstruction
4. **UI Tests**: Manual browser testing for waterfall visualization

## 10. File Creation Checklist

- [ ] `campus/model/trace.py` - TraceSpan model
- [ ] `campus/audit/__init__.py` - Blueprint init
- [ ] `campus/audit/model.py` - Import/export model
- [ ] `campus/audit/resources/__init__.py`
- [ ] `campus/audit/resources/traces.py` - Data access
- [ ] `campus/audit/routes/__init__.py`
- [ ] `campus/audit/routes/traces.py` - Trace endpoints
- [ ] `campus/audit/routes/health.py` - Health check
- [ ] `campus/audit/middleware/__init__.py`
- [ ] `campus/audit/middleware/tracing.py` - Trace capture
- [ ] `campus/audit/templates/base.html`
- [ ] `campus/audit/templates/traces.html`
- [ ] `campus/audit/templates/trace_detail.html`
- [ ] `campus/audit/static/audit.css`
- [ ] `campus/audit/static/audit.js`
- [ ] Tests in `tests/unit/audit/` and `tests/contract/audit/`
