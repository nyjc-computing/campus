# Audit Tracing Pipeline

How request spans flow from producers — campus services (`campus.auth`,
`campus.api`) and traced client apps (campus-classroom first, #816) —
into the audit service (`campus.audit`), and how to enable the pipeline.
Parent epic: #424; enablement issue: #699.

## How it works

- `campus/common/devops/deploy.py` registers tracing middleware for
  `DEPLOY in ('campus.auth', 'campus.api')` when
  `AUDIT_TRACING_ENABLED=1` (read once at app creation — flipping the
  flag is a redeploy, not a runtime change). `campus.audit` does not
  trace its own requests.
- Client apps that depend on `campus-suite` wire the same middleware
  themselves: `campus.audit.middleware.init_app(app)` behind their own
  `AUDIT_TRACING_ENABLED` gate (see the classroom app factory for the
  reference wiring). A traced client app's requests become root spans,
  and the campus SDK calls it makes become their child spans (#816).
- The middleware wraps every request in a span and ingests it via HTTP
  `POST /audit/v1/traces/` (`{"spans": [span]}`) from a background
  thread pool. **Ingestion failures never affect user requests** — they
  degrade to warning logs (`Failed to ingest trace span`).
- Static-asset requests (`static`/`*.static` endpoints,
  `/favicon.ico`) are **not spanned** (#818): they can never carry
  child spans (push_context skips static too, #689) and would only
  flood the traces list with 1-span rows. HTML page loads stay traced —
  they are the waterfall roots that give page-fired SDK calls
  parentage (#816).
- `campus.audit` does not self-trace, but can emit audit *events*
  (`AUDIT_EVENTS_ENABLED=1`, login-attempt/API-key events) directly into
  its own storage.

## Trace context propagation (#794)

Requests spawned by a traced service become **child spans** of the
originating request, which is what the audit UI's waterfall draws:

- Inbound: `X-Request-ID` (trace id, pre-existing) and `X-Parent-Span-ID`
  (caller's span id) promote the request from a new root to a child of
  the caller's span, within the caller's trace.
- Outbound: the `campus_python` SDK instruments its own sessions at
  client construction (`campus_python.tracing.instrument_requests_session`,
  campus-api-python#93), so every call made while handling a traced
  request — campus.api's `authenticate`, a client app's session lookup —
  carries both headers and lands as a child span. Headers are computed
  per call from the active request context — safe for shared sessions,
  and calls from outside a request context (e.g. the ingestion executor
  thread) stay unparented. The mirrored copy in
  `campus.audit.middleware.tracing` remains for server-side sessions
  built on `campus.common.http`; the two are idempotent across each
  other.
- In tests, `tests.flask_test.TestCampusRequest` merges the same headers
  so the api→auth chain behaves as in production.
- Span `started_at` is the wall-clock request start (captured in
  `before_request`), so waterfall offsets are real start deltas.
- `TraceTree.from_spans` adopts spans whose parent was not ingested
  under the earliest-started root — nothing disappears from the view.
- Header trust matches `X-Request-ID`: internal observability only, not
  a security boundary. W3C `traceparent` interop is possible future work
  (it would extend both propagation implementations).

## Login-journey tagging (#803)

Each browser hop of a login flow is its own trace (navigations do not
replay `X-Request-ID`), so campus.auth correlates them out-of-band:

- `GET /auth/v1/authorize` — the flow's first browser touch — sets an
  opaque `campus_journey` cookie (~30 min Max-Age, SameSite=Lax) and
  records the id on the auth session.
- The tracing middleware stamps every span's `tags.journey_id` from that
  cookie; the server-to-server `POST /auth/v1/token` (which never
  carries the cookie) copies the id from the auth session into
  `flask.g`, and the middleware stamps it from there.
- `GET /audit/v1/traces/search?journey_id=...` filters traces by the
  tag; the audit web UI groups a journey at `/audit/journeys/<id>` and
  chips journey traces in the traces list.

Journey membership lives in the free-form `tags` dict (zero
migrations) and is matched in Python over a capped recent-span scan —
fine at the audit UI's scale; promote to a dedicated column only if
that ever gets slow.

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

Key scopes follow the `#575` model: producers hold `traces:*` scopes
(`traces:write` to ingest spans, `traces:read`/`traces:search` to
query); the **operator key** holds `apikeys:read`/`apikeys:write`,
which gate all `/audit/v1/apikeys` routes (#796). A producer key can
neither create keys nor elevate itself.

**Bootstrap (operator key):** set `AUDIT_OPERATOR_API_KEY=<plaintext>`
on the campus.audit deployment. The service seeds it at startup under
the fixed id `uid-apikey-operator-0000` (config:
`AUDIT_OPERATOR_API_KEY_ID`) with `AUDIT_OPERATOR_API_KEY_SCOPES`,
following the same idempotent startup-seed pattern as campus.auth's
public client: an existing record is never modified — rotate by
deleting that record and restarting with a new value. Manual recovery /
initial setup: `AUDIT_OPERATOR_API_KEY=… python
scripts/seed_audit_operator_key.py`. Generate the plaintext with
`secret.generate_audit_api_key()` (`audit_v1_` + 22-char base64url);
keep it out of the repo.

**Subsequent (producer) keys:** `POST /audit/v1/apikeys/` with the
operator key (name, owner_id, `scopes` such as
`"traces:write,traces:read"`); the response contains the plaintext.
Set it as `AUDIT_API_KEY` on the producer.

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
