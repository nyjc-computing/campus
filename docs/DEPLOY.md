# Campus Deployment - Ultra Simple

One codebase, one `main.py`, multiple deployment modes. 
Clients use the `campus_python` library to communicate with deployments via HTTP API.

## ⚠️ Required: `PUBLIC_URL` (breaking change, campus#652)

Every deployment **must** set `PUBLIC_URL` to its full public origin
(`scheme://host[:port]`, no trailing path), e.g.:

```bash
export PUBLIC_URL=https://campusauth-development.up.railway.app   # Railway
export PUBLIC_URL=http://localhost:5000                           # local dev
```

All absolute URL generation (OAuth redirect URIs, device-flow
verification URIs, login callbacks) is built from it. The legacy
`https://{HOSTNAME}` fallback was **removed**: deployments that only set
`HOSTNAME` will raise `OSError` when generating URLs. On Railway, set
`PUBLIC_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}`. In Codespaces the
variable is derived automatically.

## 🔐 Deploy Auth Service

```bash
# Install with dependencies
poetry install

# Configure deployment mode
export DEPLOY=campus.auth
export PUBLIC_URL=https://your-auth-domain.tld
python main.py
```

**What you get:**
- Authentication API: OAuth, session management, credentials
- Client authentication and authorization
- Minimal service for auth operations

## 🌐 Deploy API Service

```bash  
# Install with dependencies
poetry install

# Configure deployment mode  
export DEPLOY=campus.api
export PUBLIC_URL=https://your-api-domain.tld
python main.py
```

**What you get:**
- RESTful API endpoints for Campus resources
- Circle management, Email OTP, etc.
- Full API deployment

## 📊 Deploy Audit Service

```bash
export DEPLOY=campus.audit
export PUBLIC_URL=https://your-audit-domain.tld
python main.py
```

**What you get:**
- Trace span ingestion + versioned traces API (`/audit/v1/*`, audit API keys)
- Audit web UI (`/audit/*`, browser OAuth gate)

The audit service uses its own database (Postgres in dev/prod) and its
own storage tables; none of the auth/api credentials apply to it
directly. Runbook for the tracing pipeline: [audit-tracing.md](audit-tracing.md).

### Required per environment: web UI OAuth gate (#696)

The web UI fails closed until configured — UI pages return 503 and
`/audit/api/*` returns 401 without these:

1. **Register a confidential OAuth client** on the environment's auth
   service (as an authenticated admin client):

   ```bash
   curl -X POST https://<auth-host>/auth/v1/clients/ \
     -u "<admin_client_id>:<admin_client_secret>" \
     -H "Content-Type: application/json" \
     -d '{"name": "audit-web-ui",
          "description": "Confidential OAuth client for the audit web UI browser gate (#696)",
          "redirect_uris": ["https://<audit-host>/audit/callback"]}'
   ```

   The redirect_uri must be exactly `https://<audit-host>/audit/callback`
   built from the audit deployment's `PUBLIC_URL` (fail-closed
   validation, #685).

2. **Mint the client secret** — the creation response does NOT include
   it (only a hash is stored):

   ```bash
   curl -X POST https://<auth-host>/auth/v1/clients/<client_id>/revoke \
     -u "<admin_client_id>:<admin_client_secret>"
   # → {"secret": "<new secret>"}   (revokes any previous secret)
   ```

3. **Set the variables on the audit deployment**:

   ```bash
   AUDIT_OAUTH_CLIENT_ID=<client_id from step 1>
   AUDIT_OAUTH_CLIENT_SECRET=<secret from step 2>
   ```

   These are explicit to the web UI gate (not the ambient
   `CLIENT_ID`/`CLIENT_SECRET` pair), mirroring `AUDIT_API_KEY` (#699).

4. **Verify** (no login needed for the first three):
   - `GET /` → 200, the landing page (campus-wide convention, #842:
     `/` is a landing page, `/health` is the health check)
   - `GET /health` → 200 JSON (public)
   - `GET /audit/` unauthenticated → 302 `/audit/login` → 302 auth
     `/auth/v1/authorize?...` → 302 Google
   - `GET /audit/api/traces` unauthenticated → 401 JSON
   - `GET /audit/v1/health` → 200 (public)

Dev reference: client `uid-client-cfaf0e29` ("audit-web-ui") registered
on the dev auth service, redirecting to
`https://campusaudit-development.up.railway.app/audit/callback`.

### Required for tracing producers: `AUDIT_API_KEY`

Services that emit trace spans to the audit service (auth, api) need
`AUDIT_API_KEY` set to an audit API key (`audit_v1_...`), created via
`POST /audit/v1/apikeys/` on the audit service. See
[audit-tracing.md](audit-tracing.md) for the full runbook.

## 📚 Client Library Usage

The `campus_python` client library is installed separately:

```bash
# Install campus_python client
poetry add git+https://github.com/nyjc-computing/campus-api-python.git@main

# Use in your code
import campus_python
campus = campus_python.Campus()
```

See the [campus-api-python repository](https://github.com/nyjc-computing/campus-api-python) for documentation.

## 🎯 Platform Instructions

### Railway
Set environment variables in Railway dashboard:
- `DEPLOY=campus.auth`, `campus.api`, or `campus.audit`
- `PUBLIC_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}`
- Start command: `gunicorn --bind "0.0.0.0:$PORT" --timeout 120 wsgi:app`

On the **campus.auth** service, configure the operator allowlist
(read at request time, comma-separated, unset/empty = fail-closed
deny):

- `AUTH_OPERATOR_CLIENT_IDS`: client ids granted the deployment-operator
  role on every management blueprint (#854) — the non-delegable root
  used to bootstrap all other authority. Typically the campus-admin
  portal's client id.

#### Management authority: the access-grant store (#883)

Everyone else's management authority lives in the **access-grant
store**, administered via `POST /auth/v1/grants` (the operator, or a
same-vocabulary admin) and queried with `GET /auth/v1/grants` — that
query **is** the "who can administer what" matrix (campus#872): one
API call, no env audit. A designated user needs BOTH legs, ANDed and
fail-closed: a grant row whose level covers the action, and a token
carrying the scope (which requires widening the minting client's
`allowed_scopes` first — see invariant A8).

- `users` vocabulary: `users:read` lists/gets, `users:mod` activates,
  `users:write` creates/updates, `users:admin` deletes.
- `clients` vocabulary: grantable up to `clients:write` (benign field
  updates). A vocabulary-level `clients:admin` row is
  operator-equivalent and rejected (umbrella decision 4): register,
  delete, secret rotation and scope caps are operator-only.
- `vaults` vocabulary (#889): per-label rows at read/write/admin
  (READ→read, CREATE|UPDATE→write, DELETE/ALL→admin) plus
  `vaults:<level>` token scopes; administering vault grants is
  operator-only. Clients keep vault bitflags via
  `/clients/{id}/access/`.
- `credentials` vocabulary: closed — routes stay operator-only.

The designated-admin env vars (`AUTH_ADMIN_USER_IDS`,
`AUTH_USERS_ADMIN_USER_IDS`) were **retired** by the DB-only ruling
(#887/#888, umbrella decision 3) and are no longer read at request
time. A `SUPER_ADMIN` env-nominated root user account is tracked in
campus#897 (umbrella decision 8); once it lands, the matrix answer is
the grants query plus two env roots (`AUTH_OPERATOR_CLIENT_IDS` and
the super-admin).

**Seed runbook (once per deployment, at or before the cutover).**
Grant rows are inert until the gated code deploys, so seeding early
is safe; seeding late means fail-closed lockout for anyone but the
operator. With operator credentials:

```sh
POST /auth/v1/grants/            # Basic auth of an operator client
{"grantee_type": "user", "grantee_id": "admin@domain.edu.sg",
 "resource_type": "users", "level": "admin"}
```

Break-glass alternative when only service SSH is available
(`railway ssh -s campus.auth`):

```sh
cd /app && PYTHONPATH=/app .venv/bin/python -c '
from campus.auth.resources.grant import grants
grants.grant("user", "admin@domain.edu.sg", "users", level="admin")'
```

See `campus/auth/authz.py`, campus#883 (the epic and its decision
record), and docs/auth-token-invariants.md (A8).

**Note:** The `--timeout 120` flag sets a 2-minute timeout (vs default 30s) to handle OAuth flows and external API calls.

### Replit
In Secrets tab, add:
- Key: `DEPLOY`
- Value: `campus.auth`, `campus.api`, or `campus.audit`

Then click Run button (or `python main.py`)

### Local Development
```bash
# Auth service
export DEPLOY=campus.auth
export PUBLIC_URL=http://localhost:5000
python main.py

# API service  
export DEPLOY=campus.api
export PUBLIC_URL=http://localhost:5000
python main.py

# Audit service
export DEPLOY=campus.audit
export PUBLIC_URL=http://localhost:5002
python main.py
```

## 📁 How It Works

- `DEPLOY` environment variable specifies the service module to deploy (e.g., `campus.auth`, `campus.api`, `campus.audit`)
- `main.py` reads the environment variable and starts the appropriate service
- For production, use `wsgi.py` with Gunicorn or other WSGI servers

**Valid deploy modes:** `campus.auth`, `campus.api`, `campus.audit`, or any module with `init_app()`

That's it!
