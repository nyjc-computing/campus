# Audit Tracing Pipeline

How request spans flow from producer services (`campus.auth`, `campus.api`)
into the audit service (`campus.audit`), and how to enable the pipeline.
Parent epic: #424; enablement issue: #699.

## How it works

- `campus/common/devops/deploy.py` registers tracing middleware for
  `DEPLOY in ('campus.auth', 'campus.api')` when
  `AUDIT_TRACING_ENABLED=1` (read once at app creation — flipping the
  flag is a redeploy, not a runtime change). `campus.audit` does not
  trace its own requests.
- The middleware wraps every request in a span and ingests it via HTTP
  `POST /audit/v1/traces/` (`{"spans": [span]}`) from a background
  thread pool. **Ingestion failures never affect user requests** — they
  degrade to warning logs (`Failed to ingest trace span`).
- `campus.audit` does not self-trace, but can emit audit *events*
  (`AUDIT_EVENTS_ENABLED=1`, login-attempt/API-key events) directly into
  its own storage.

## Trace context propagation (#794)

Requests spawned by a traced service become **child spans** of the
originating request, which is what the audit UI's waterfall draws:

- Inbound: `X-Request-ID` (trace id, pre-existing) and `X-Parent-Span-ID`
  (caller's span id) promote the request from a new root to a child of
  the caller's span, within the caller's trace.
- Outbound: `tracing.instrument_requests_session()` wraps a
  `requests.Session` so calls made while handling a traced request carry
  both headers. `campus.api.init_app` instruments the `campus_python`
  client's auth session (the `authenticate` call every api request
  makes). Headers are computed per call — safe for shared sessions, and
  calls from outside a request context (e.g. the ingestion executor
  thread) stay unparented.
- In tests, `tests.flask_test.TestCampusRequest` merges the same headers
  so the api→auth chain behaves as in production.
- Span `started_at` is the wall-clock request start (captured in
  `before_request`), so waterfall offsets are real start deltas.
- `TraceTree.from_spans` adopts spans whose parent was not ingested
  under the earliest-started root — nothing disappears from the view.
- Header trust matches `X-Request-ID`: internal observability only, not
  a security boundary. W3C `traceparent` interop is possible future work,
  as is moving the SDK session instrumentation into campus-api-python.

## Authentication (`AUDIT_API_KEY`)

Producers authenticate to the audit API with a **Bearer `audit_v1_` API
key**. Set it on each producer:

```bash
AUDIT_API_KEY=audit_v1_<22-char-base64url>
```

Priority in `campus.audit.client`:

1. `AuditClient.json_client_class` (test injection only)
2. `AUDIT_API_KEY` — explicit Bearer auth, scoped to the audit client
   only (#699)
3. Ambient env (`ACCESS_TOKEN`, then `CLIENT_ID`/`CLIENT_SECRET` Basic)

**Never** set `ACCESS_TOKEN=<audit key>` to "fix" auth: that variable is
ambient/shared — every other `DefaultClient` consumer on the producer
would silently inherit the header. `AUDIT_API_KEY` exists precisely to
avoid that footgun. The audit API itself rejects Basic auth with a clear
401; Bearer + valid `audit_v1_` format + match against the `apikeys`
table is the only accepted scheme.

## Minting and bootstrapping keys

The key CRUD endpoints (`/audit/v1/apikeys`) themselves require an
authenticated `audit_v1_` key, so the **first** key must be seeded
out-of-band:

1. **Bootstrap (no key exists yet):** generate a key with the same
   format as `campus.common.utils.secret.generate_audit_api_key()`
   (`audit_v1_` + 22-char base64url), insert
   `sha256(key)` (hex, per `hash_api_key`) into the audit DB's
   `apikeys` table (`key_hash` column, `revoked_at` NULL), e.g. over
   the database's public proxy. Keep the plaintext for the producer env.
2. **Subsequent keys:** `POST /audit/v1/apikeys/` with the existing key
   (name, owner_id, scopes); the response contains the plaintext key.

Verify a key works: `GET /audit/v1/traces/` with
`Authorization: Bearer <key>` → 200 (401 on failure).

## Enabling on a deployment

1. Set `AUDIT_API_KEY=<key>` on the producer.
2. Set `AUDIT_TRACING_ENABLED=1` (and `AUDIT_EVENTS_ENABLED=1` if event
   coverage is wanted) and redeploy.
3. Generate traffic and confirm spans appear in the audit UI (`/audit/`)
   or `GET /audit/v1/traces/`. Watch producer logs for
   `Failed to ingest trace span` warnings.

Roll out one producer at a time (canary) — ingestion is fail-safe, so a
misconfigured producer only loses spans, never requests.
