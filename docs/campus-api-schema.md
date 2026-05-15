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

## Version History

- **2026-05-02**: Initial documentation created
- **2026-05-02**: URL pattern fixes deployed in campus PR #573
- **2026-05-02**: Client library updated in campus-api-python PR #26

---

## Related Documentation

- [campus repository](https://github.com/nyjc-computing/campus)
- [campus-api-python repository](https://github.com/nyjc-computing/campus-api-python)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Architecture Documentation](architecture.md)
