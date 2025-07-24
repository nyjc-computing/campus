# HTTP Verbs and API Patterns

This document describes the HTTP verbs used by Campus Client and the patterns for using them effectively with the unified Campus interface.

## Overview

Campus Client follows RESTful API conventions with clear mappings between HTTP verbs and operations. The unified Campus interface provides consistent access patterns that map to HTTP methods behind the scenes.

## HTTP Method to Campus Client Mapping

### Path Parameters vs Query Parameters

**Path Parameters** - Used for resource identification:
```python
# Path parameters are mapped using subscription syntax []
campus.users["user_123"]           # → GET /users/user_123
campus.circles["circle_456"]       # → GET /circles/circle_456  
campus.vault["secrets"]["API_KEY"] # → GET /vault/secrets/API_KEY
```

**Query Parameters** - Used for method arguments:
```python
# Query parameters are mapped using method calls with keyword arguments
campus.users.new(email="alice@example.com", name="Alice")        # → POST /users
campus.circles.new(name="Engineering", description="Dev team")   # → POST /circles
campus.users.update(user_id="user_123", name="New Name")        # → PATCH /users/user_123
```

## HTTP Verb Reference

### GET - Retrieve Resources

**Purpose:** Retrieve existing resources without side effects

**Characteristics:**
- Idempotent (can be called multiple times safely)
- No request body
- Returns resource data
- Supports query parameters for filtering

**Campus Client Patterns:**

**Campus Client Patterns:**

```python
# Resource access via path parameters (subscription syntax)
user_resource = campus.users["user_123"]     # → GET /users/user_123 (when accessed)
circle_resource = campus.circles["circle_456"] # → GET /circles/circle_456 (when accessed)
vault_key = campus.vault["secrets"]["API_KEY"] # → GET /vault/secrets/API_KEY (when accessed)

# Direct data retrieval methods
current_user = campus.users.me()             # → GET /me
vault_keys = campus.vault["secrets"].list()  # → GET /vault/secrets/list
available_vaults = campus.vault.list_vaults() # → GET /vault/list

# Resource object methods (legacy interface)
user_profile = campus.users["user_123"].get_profile() # → GET /users/user_123/profile
circle_data = campus.circles["circle_456"].get()      # → GET /circles/circle_456
members_data = campus.circles["circle_456"].members.list() # → GET /circles/circle_456/members
```

**Response Patterns:**
- Dictionary-based responses: `user['email']`, `circle["name"]`
- Resource objects for advanced operations
- Collections return lists or dictionaries

---

### POST - Create Resources

**Purpose:** Create new resources or trigger actions

**Characteristics:**
- Not idempotent (multiple calls create multiple resources)
- Request body contains data
- Returns created resource or action result
- May include Location header for new resources

**Campus Client Patterns:**

```python
# Create new resources (returns dictionaries)
user = campus.users.new(email="alice@example.com", name="Alice")     # → POST /users
circle = campus.circles.new(name="Engineering", description="Dev team") # → POST /circles

# Vault secret operations
campus.vault["secrets"]["API_KEY"].set(value="secret_value")         # → POST /vault/secrets/API_KEY

# Vault management
vault_client = campus.vault.client.new(name="MyApp", description="App") # → POST /client

# Trigger actions via resource objects
campus.circles["circle_456"].members.add(user_id="user_123", role="admin") # → POST /circles/circle_456/members/add
campus.vault.access.grant(client_id="client_123", vault_label="secrets", permissions=["read"]) # → POST /access/secrets
```

**Response Patterns:**
- Created resources return dictionaries with generated IDs
- Actions return success confirmation or result data
- Access via dictionary keys: `user['id']`, `circle["name"]`

---

### PATCH - Update Resources

**Purpose:** Partially update existing resources

**Characteristics:**
- Idempotent (multiple identical calls have same effect)
- Request body contains only fields to update
- Returns updated resource or confirmation
- More efficient than PUT for partial updates

**Campus Client Patterns:**

```python
# Update via unified interface methods
updated_user = campus.users.update(user_id="user_123", name="New Name")           # → PATCH /users/user_123
updated_circle = campus.circles.update(circle_id="circle_456", description="New") # → PATCH /circles/circle_456

# Update via resource objects (legacy interface)
campus.users["user_123"].update(name="New Name", email="new@example.com")         # → PATCH /users/user_123
campus.circles["circle_456"].update(description="New description")                # → PATCH /circles/circle_456

# Update member access
campus.circles["circle_456"].members["member_id"].update(access=15)               # → PATCH /circles/circle_456/members/member_id
```

**Request Body Patterns:**
```json
// Only include fields being updated
{
  "name": "New Name",
  "email": "new@example.com"
}
```

**Response Patterns:**
- Unified interface methods return updated resource dictionaries
- Resource object methods may return confirmation
- Includes updated timestamps and data

---

### PUT - Replace Resources

**Purpose:** Completely replace existing resources

**Characteristics:**
- Idempotent (multiple identical calls have same effect)
- Request body contains complete resource representation
- Replaces entire resource (missing fields may be cleared)
- Less commonly used than PATCH

**Client Methods:**
- `HttpClient._put(path, data, params=None)`

**Usage Patterns:**

Campus Client currently uses PATCH for updates rather than PUT, following the principle of partial updates. PUT would be used for complete resource replacement:

```python
# Complete resource replacement (theoretical)
# PUT would replace ALL fields, clearing any not specified
user_data = {
    "email": "user@example.com",
    "name": "Full Name",
    "role": "admin",
    "preferences": {...}
}
# client._put(f"/users/{user_id}", user_data)
```

---

### DELETE - Remove Resources

**Purpose:** Delete existing resources

**Characteristics:**
- Idempotent (deleting non-existent resource succeeds)
- No request body
- May support query parameters
- Returns confirmation or empty response

**Campus Client Patterns:**

```python
# Delete via resource objects
campus.users["user_123"].delete()                    # → DELETE /users/user_123
campus.circles["circle_456"].delete()                # → DELETE /circles/circle_456

# Delete vault secrets
campus.vault["secrets"]["old_key"].delete()          # → DELETE /vault/secrets/old_key

# Remove relationships
campus.circles["circle_456"].members.remove(user_id="user_123") # → DELETE /circles/circle_456/members/remove

# Delete vault clients and revoke access
campus.vault.client.delete(client_id="client_123")   # → DELETE /client/client_123
campus.vault.access.revoke(client_id="client_123", vault_label="secrets") # → DELETE /access/secrets
```

**Response Patterns:**
- Usually returns boolean `True` for success
- May return confirmation message
- Idempotent: deleting already-deleted resource succeeds

---

## Campus Client API Patterns

### Resource Identification

Campus Client uses consistent patterns for identifying resources through subscription syntax:

```python
# Path parameter mapping via subscription []
campus.users["user_123"]           # → /users/user_123
campus.circles["circle_456"]       # → /circles/circle_456
campus.vault["app_secrets"]        # → /vault/app_secrets

# Chained path parameters
campus.vault["app_secrets"]["api_key"]  # → /vault/app_secrets/api_key

# Nested resource access
campus.circles["circle_456"].members           # → /circles/circle_456/members/*
campus.circles["circle_456"].members["mem_789"] # → /circles/circle_456/members/mem_789
```

### Query Parameter Mapping

Method arguments become query parameters or request body data:

```python
# Query parameters via method arguments
campus.users.new(email="alice@example.com", name="Alice")
# → POST /users with body: {"email": "alice@example.com", "name": "Alice"}

campus.users.update(user_id="user_123", name="New Name")  
# → PATCH /users/user_123 with body: {"name": "New Name"}

campus.circles["circle_456"].members.add(user_id="user_123", role="admin")
# → POST /circles/circle_456/members/add with body: {"user_id": "user_123", "role": "admin"}
```

### Unified vs Legacy Interface

**Unified Interface** (Recommended):
```python
# Dictionary responses, simple method calls
user = campus.users.new(email="alice@example.com", name="Alice")  # Returns Dict[str, Any]
updated_user = campus.users.update(user_id=user["id"], name="Alice Smith")
```

**Legacy Resource Interface** (Advanced use cases):
```python
# Object-oriented access for complex operations
user_resource = campus.users["user_123"]    # Returns User object
user_profile = user_resource.get_profile()  # Advanced method
user_resource.delete()                       # Direct resource manipulation
```

### Request Bodies

POST and PATCH requests use JSON request bodies generated from method arguments:

```python
# Create requests - keyword arguments become request body
campus.users.new(email="alice@example.com", name="Alice")
# → POST /users
# → Body: {"email": "alice@example.com", "name": "Alice"}

# Update requests - only specified fields included
campus.users.update(user_id="user_123", name="New Name", email="new@example.com")
# → PATCH /users/user_123  
# → Body: {"name": "New Name", "email": "new@example.com"}

# Action requests - all arguments become body data
campus.circles["circle_456"].members.add(user_id="user_123", role="admin")
# → POST /circles/circle_456/members/add
# → Body: {"user_id": "user_123", "role": "admin"}
```

### Response Formats

Campus Client returns dictionaries for easy data access:

```python
# User creation response
user = campus.users.new(email="alice@example.com", name="Alice")
print(user['id'])       # Access via dictionary key
print(user['email'])    # alice@example.com
print(user['name'])     # Alice

# Circle creation response  
circle = campus.circles.new(name="Engineering", description="Dev team")
print(circle["id"])     # Generated circle ID
print(circle["name"])   # Engineering

# Vault secret response
api_key_value = str(campus.vault["secrets"]["API_KEY"])  # Direct string conversion
# OR
api_key_value = campus.vault["secrets"]["API_KEY"].get()  # Explicit get method
```

## Error Responses

All HTTP verbs may return error responses with consistent formats:

### 400 Bad Request
```json
{
  "error": "validation_error",
  "message": "Invalid email format",
  "details": {
    "field": "email",
    "value": "invalid-email"
  }
}
```

### 401 Unauthorized
```json
{
  "error": "authentication_required",
  "message": "Valid authentication credentials required"
}
```

### 403 Forbidden
```json
{
  "error": "access_denied",
  "message": "Insufficient permissions for this operation"
}
```

### 404 Not Found
```json
{
  "error": "not_found",
  "message": "User not found",
  "resource_type": "user",
  "resource_id": "user_123"
}
```

### 422 Unprocessable Entity
```json
{
  "error": "validation_error",
  "message": "Validation failed",
  "validation_errors": [
    {
      "field": "email",
      "message": "Email already exists"
    }
  ]
}
```

### 429 Too Many Requests
```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests",
  "retry_after": 60
}
```

### 500 Internal Server Error
```json
{
  "error": "internal_error",
  "message": "An unexpected error occurred",
  "request_id": "req_123456"
}
```

## Best Practices

### Idempotency

Understand which operations are idempotent:

```python
# Idempotent - safe to retry
user_data = campus.users["user_123"].get()      # GET
updated_user = campus.users.update(user_id="user_123", name="New Name")  # PATCH  
campus.users["user_123"].delete()               # DELETE

# Not idempotent - creates new resources each time
user = campus.users.new(email="alice@example.com", name="Alice")  # POST
```

### Error Handling

Handle specific error types appropriately:

```python
from campus.client.errors import NotFoundError, ValidationError, AuthenticationError

try:
    user = campus.users.new(email="alice@example.com", name="Alice")
    updated_user = campus.users.update(user_id=user["id"], email="new@example.com")
except NotFoundError:
    print("User does not exist")
except ValidationError as e:
    print(f"Invalid update data: {e}")
except AuthenticationError:
    print("Please set CLIENT_ID and CLIENT_SECRET environment variables")
```

### Resource Lifecycle with Dictionary Interface

Follow standard resource lifecycle patterns using the unified interface:

```python
# Create → Read → Update → Delete
user = campus.users.new(email="alice@example.com", name="Alice")  # POST → Dict
print(f"Created user: {user['email']}")                          # Dict access
updated_user = campus.users.update(user_id=user["id"], name="Alice Smith")  # PATCH → Dict
campus.users[user["id"]].delete()                                # DELETE
```

### Path vs Query Parameter Selection

**Use Path Parameters (subscription syntax) for:**
- Resource identification: `campus.users["user_123"]`
- Hierarchical access: `campus.vault["secrets"]["API_KEY"]`
- Nested resources: `campus.circles["circle_456"].members`

**Use Query Parameters (method arguments) for:**
- Resource creation: `campus.users.new(email="...", name="...")`
- Resource updates: `campus.users.update(user_id="...", name="...")`
- Action parameters: `members.add(user_id="...", role="...")`

### Caching Behavior

Understand client-side caching with resource objects:

```python
# Resource object caching (legacy interface)
user_resource = campus.users["user_123"]
print(user_resource.name)       # Fetches data from server
print(user_resource.name)       # Uses cached data

user_resource.update(name="New Name")  # Clears cache
print(user_resource.name)       # Fetches fresh data

# Unified interface (no caching - always fresh)
user = campus.users.update(user_id="user_123", name="New Name")  # Always returns fresh data
```
