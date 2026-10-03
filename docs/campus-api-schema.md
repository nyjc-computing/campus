# Campus API URL Schema

## URL Trailing Slash Convention

The Campus API follows a consistent trailing slash convention to indicate the navigability of resources.

### General Pattern

- **Resource roots** (`/api/v1/`, `/auth/v1/`, `/audit/v1/`) - **ALWAYS** have trailing slash
- **Resource collections** (`/circles/`, `/clients/`, `/assignments/`) - **ALWAYS** have trailing slash
- **Single IDed resources** (`/circles/{id}/`, `/clients/{id}/`, `/assignments/{id}/`) - **ALWAYS** have trailing slash
- **Dead-end subresources** (`/timetable/current`, `/timetable/{id}/metadata`, `/traces/search`) - **NEVER** have trailing slash

### Rationale

The trailing slash is omitted to indicate a dead-end path (no further sub-resource access is possible). This provides a clear visual indicator in the URL structure about whether a resource can have child resources.

### Examples

#### Correct Usage

```python
# Resource roots (with trailing slash)
/api/v1/
/auth/v1/
/audit/v1/

# Resource collections (with trailing slash)
GET    /circles/              # List all circles
POST   /circles/              # Create a new circle
GET    /clients/              # List all clients
POST   /clients/              # Create a new client

# Single resources (with trailing slash)
GET    /circles/{circle_id}/  # Get a specific circle
PATCH  /circles/{circle_id}/  # Update a circle
DELETE /circles/{circle_id}/  # Delete a circle
GET    /clients/{client_id}/  # Get a specific client
PATCH  /clients/{client_id}/  # Update a client

# Sub-resources that can have further navigation (with trailing slash)
GET    /circles/{circle_id}/members/  # List members of a circle
POST   /circles/{circle_id}/members/  # Add a member
GET    /clients/{client_id}/access/   # Get client access

# Dead-end subresources (without trailing slash)
GET    /timetable/current           # Get current timetable ID
PUT    /timetable/current           # Set current timetable
GET    /timetable/{id}/metadata     # Get timetable metadata
PATCH  /timetable/{id}/metadata     # Update timetable metadata
GET    /traces/search               # Search traces (dead-end endpoint)
POST   /clients/{id}/revoke         # Revoke client secret (action endpoint)
GET    /clients/{id}/access/check   # Check access (action endpoint)
GET    /submissions/by-assignment/{id}  # Filter by assignment (dead-end)
GET    /submissions/by-student/{id}     # Filter by student (dead-end)
```

#### Determining Trailing Slash Usage

When adding a new endpoint, ask yourself:

1. **Is this a resource collection?** → Add trailing slash
2. **Can this resource have sub-resources?** → Add trailing slash
3. **Is this a dead-end (action, query, or terminal data)?** → No trailing slash

Examples:

- `/circles/{id}/members/` → Has trailing slash because members can have further actions (e.g., `/members/add`)
- `/circles/{id}/members/add` → No trailing slash because it's a specific action endpoint
- `/traces/search` → No trailing slash because it's a query endpoint with no sub-resources
- `/clients/{id}/revoke` → No trailing slash because it's an action endpoint

---

## Implementation Status

### ✅ Fully Conforms to Pattern

The following endpoints conform correctly to the URL trailing slash convention:

**campus.api.routes.timetable**
- Collections: `/timetable/` (correct)
- Single resources: `/timetable/<id>/` (correct)
- Dead-end subresources: `/timetable/current`, `/timetable/next`, `/timetable/<id>/metadata`, `/timetable/<id>/entries` (correct)

**campus.auth.routes.clients**
- Collections: `/clients/` (correct)
- Single resources: `/clients/<id>/` (correct)
- Sub-resources: `/clients/<id>/access/` (correct)
- Dead-end actions: `/clients/<id>/revoke`, `/clients/<id>/access/check`, `/clients/<id>/access/grant`, `/clients/<id>/access/revoke` (correct)

**campus.auth.routes.sessions**
- Collections: `/sessions/` (correct)
- Single resources: `/sessions/<provider>/<session_id>/` (correct)
- Dead-end endpoints: `/sessions/sweep`, `/sessions/<provider>/authorization_code` (correct)

**campus.audit.routes.traces**
- Collections: `/traces/` (correct)
- Single resources: `/traces/<trace_id>/` (correct)
- Sub-resources: `/traces/<trace_id>/spans/` (correct)
- Dead-end: `/traces/search` (correct)

### ✅ Recently Fixed to Conform

The following endpoints were updated to conform to the URL trailing slash convention in PR #573:

**campus.api.routes.circles**
- ✅ Fixed: `DELETE /circles/<circle_id>/` (now has trailing slash)
- ✅ Fixed: `GET /circles/<circle_id>/` (now has trailing slash)
- ✅ Fixed: `PATCH /circles/<circle_id>/` (now has trailing slash)
- ✅ Fixed: `GET /circles/<circle_id>/members/` (now has trailing slash)
- ✅ Fixed: `PATCH /circles/<circle_id>/members/` (now has trailing slash)

**campus.api.routes.assignments**
- ✅ Fixed: `GET /assignments/<assignment_id>/` (now has trailing slash)
- ✅ Fixed: `PATCH /assignments/<assignment_id>/` (now has trailing slash)
- ✅ Fixed: `DELETE /assignments/<assignment_id>/` (now has trailing slash)

**campus.api.routes.submissions**
- ✅ Fixed: `GET /submissions/<submission_id>/` (now has trailing slash)
- ✅ Fixed: `PATCH /submissions/<submission_id>/` (now has trailing slash)
- ✅ Fixed: `DELETE /submissions/<submission_id>/` (now has trailing slash)

**campus.auth.routes.users**
- ✅ Fixed: `DELETE /users/<user_id>/` (now has trailing slash)
- ✅ Fixed: `GET /users/<user_id>/` (now has trailing slash)
- ✅ Fixed: `PATCH /users/<user_id>/` (now has trailing slash)

---

## Client Implementation Guidance

### Campus-API-Python Client Library

When implementing or maintaining the campus-api-python client library:

1. **Collection paths** should have trailing slashes:
   ```python
   class Circles(ResourceCollection):
       path = "circles/"  # ✅ Correct
   ```

2. **Single resource access** should use trailing slashes:
   ```python
   def get(self) -> Circle:
       resp = self.client.get(
           self.make_path(end_slash=True)  # ✅ Correct for API compliance
       )
   ```

3. **Dead-end subresources** should not have trailing slashes:
   ```python
   def get_current(self) -> str:
       resp = self.client.get(
           self.make_path("current")  # ✅ No trailing slash for dead-end
       )
   ```

### URL Construction Reference

The `ResourceCollection.make_path()` implementation automatically adds trailing slashes for collections and their sub-resources.

The `Resource.make_path()` method supports an `end_slash` parameter to control trailing slash behavior:
- `end_slash=True`: Add trailing slash (for single resources)
- `end_slash=False` or omitted: No trailing slash (for dead-end subresources)

---

## Migration Guide

### For API Consumers

If you're currently using the Campus API and experiencing redirect issues:

1. **Update your URLs** to include trailing slashes for single resources:
   ```python
   # Old (causes redirect):
   GET /api/v1/circles/my-circle
   
   # New (correct):
   GET /api/v1/circles/my-circle/
   ```

2. **Keep dead-end endpoints without trailing slashes**:
   ```python
   # Correct (no change needed):
   GET /api/v1/timetable/current
   GET /api/v1/traces/search
   ```

3. **Use the campus-api-python client library** which handles URL construction automatically:
   ```python
   from campus_python import Campus
   
   campus = Campus(timeout=60)
   circle = campus.api.circles["circle-id"].get()  # Client handles URLs correctly
   ```

---

## Response Envelope (JSON)

Every Campus JSON response body is a **JSON object** — never a bare array,
string, or number. Collection endpoints wrap their items in a named key:

```python
GET /integrations/v1/      # → {"integrations": [...]}
GET /auth/v1/connections/  # → {"connections": [...]}
```

Consumers should unpack the named key rather than treating the response body
as the list itself; a bare-list body fails the response type gate.

---

## Error Envelope

Every non-2xx response carries a single `error` object. Full spec:
[campus/api/docs/api-error-spec.md](../campus/api/docs/api-error-spec.md).

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "One or more fields are invalid",
    "request_id": null,
    "errors": [
      {
        "field": "upstream_scope",
        "code": "UNRECOGNIZED_FIELD",
        "message": "Unexpected field: upstream_scope"
      }
    ]
  }
}
```

- `code` is a machine-readable constant (e.g. `AUTH_INVALID_REQUEST`,
  `VALIDATION_FAILED`); the campus-api-python client library parses it
  (`campus_python.errors`).
- Request-validation failures return **422** with an `errors` array of
  per-field `{field, code, message}` entries; all other statuses follow the
  semantics of the error spec.
- `request_id` is reserved for request tracing and is `null` until tracing
  lands.

---

## Identity and Users

- **`UserID` is the email address** (`campus.schema.UserID` is the email
  type): Campus does not mint synthetic user ids, and users self-provision
  on first identity-provider login. What happens on email change or address
  reuse is an open question (tracked in #767 §1).
- **`User` carries no role or affiliation field** (`id`, `email`, `name`,
  `activated_at` only). "Student vs staff" is absent from core schema
  today; domain concepts that need the distinction (e.g. Classroom scope
  semantics, where Google's grant differs for teacher vs student accounts)
  own it downstream. Whether core should grow a role field is tracked in
  #767 §1.

---

## Provider Naming: identity providers vs integrations

- **Identity providers** use bare names: `google` (login), plus the OAuth
  proxies `github` and `discord`.
- **Integrations** use namespaced providers: `google.<slug>` (e.g.
  `google.classroom`, `google.calendar`).
- The read-only registry `GET /integrations/v1/` (public) returns
  first-party integrations with `slug` (`classroom`), `provider`
  (`google.classroom`), `base_provider` (`google`), and the consumer-facing
  `title` / `description` / `scopes` / `connectable` / `authorize_path`.
- Canonical integration routes are **two-segment**:
  `DELETE /auth/v1/connections/google/<integration>/` (disconnect) and
  `POST /auth/v1/broker/<provider>/<integration>/` (token release). The
  inventory read is `GET /auth/v1/connections/`.
- The **dotted single-segment** forms on identity routes answer with
  integration semantics rather than silently passing: a dotted
  `POST /broker/google.classroom/` denies when the caller's allowlist has
  no `google.classroom` entry (400 + deny event) and 404s with a pointer
  to the canonical route when it does; a dotted
  `DELETE /connections/google.classroom/` 404s with the same pointer.

### Connections metadata semantics

`GET /auth/v1/connections/` returns metadata only — never token values.
Each entry's `expires_at` is the access token's **last-known expiry**, not
connection health: campus refreshes tokens silently server-side on the
next broker release, so a healthy connection usually shows a stale (past)
`expires_at`. Consumers must key "Connected" off the **presence** of the
entry and must not derive an "Expired" badge from `expires_at`.

---

## Version History

- **2026-05-02**: Initial documentation created
- **2026-05-02**: URL pattern fixes deployed in campus PR #573
- **2026-05-02**: Client library updated in campus-api-python PR #26
- **2026-10-03**: Consumer-facing schema decisions from the #733
  integration lane recorded (#767 §2)

---

## Related Documentation

- [campus repository](https://github.com/nyjc-computing/campus)
- [campus-api-python repository](https://github.com/nyjc-computing/campus-api-python)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Architecture Documentation](architecture.md)
