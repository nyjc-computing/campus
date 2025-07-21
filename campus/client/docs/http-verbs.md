# HTTP Verbs and API Patterns

This document describes the HTTP verbs used by Campus Client and the patterns for using them effectively.

## Overview

Campus Client follows RESTful API conventions with clear mappings between HTTP verbs and operations. Understanding these patterns helps you predict API behavior and handle responses correctly.

## HTTP Verb Reference

### GET - Retrieve Resources

**Purpose:** Retrieve existing resources without side effects

**Characteristics:**
- Idempotent (can be called multiple times safely)
- No request body
- Returns resource data
- Supports query parameters for filtering

**Client Methods:**
- `BaseClient._get(path, params=None)`

**Usage Patterns:**

```python
# Get single resources
user = users["user_123"]  # GET /users/user_123
circle = circles["circle_456"]  # GET /circles/circle_456
secret = vault["app"]["api_key"]  # GET /vault/app/api_key

# Get collections
all_users = users.list_users()  # GET /users
all_circles = circles.list()  # GET /circles
vault_keys = vault["app"].list()  # GET /vault/app/list

# Get with parameters
search_results = circles.search("engineering")  # GET /circles/search?q=engineering
user_circles = circles.list_by_user("user_123")  # GET /users/user_123/circles
```

**Response Patterns:**
- Single resources return the resource object
- Collections return arrays wrapped in response objects
- Empty results return empty arrays, not 404 errors

---

### POST - Create Resources

**Purpose:** Create new resources or trigger actions

**Characteristics:**
- Not idempotent (multiple calls create multiple resources)
- Request body contains data
- Returns created resource or action result
- May include Location header for new resources

**Client Methods:**
- `BaseClient._post(path, data, params=None)`

**Usage Patterns:**

```python
# Create new resources
user = users.new("alice@example.com", "Alice")  # POST /users
circle = circles.new("Engineering", "Dev team")  # POST /circles
vault_client = vault.client.new("MyApp", "Description")  # POST /client

# Trigger actions
circle.add_member("user_123", "admin")  # POST /circles/{id}/members/add
circle.move("parent_circle_id")  # POST /circles/{id}/move
vault["secrets"].set("key", "value")  # POST /vault/secrets/key

# Grant permissions
vault.access.grant("client_id", "vault_label", ["read", "write"])  # POST /access/vault_label
```

**Response Patterns:**
- Created resources return the new resource with generated ID
- Actions return success confirmation or result data
- May include metadata like creation timestamps

---

### PATCH - Update Resources

**Purpose:** Partially update existing resources

**Characteristics:**
- Idempotent (multiple identical calls have same effect)
- Request body contains only fields to update
- Returns updated resource or confirmation
- More efficient than PUT for partial updates

**Client Methods:**
- `BaseClient._patch(path, data, params=None)`

**Usage Patterns:**

```python
# Update user information
user.update(name="New Name")  # PATCH /users/{id}
user.update(email="new@example.com", name="Updated Name")  # PATCH /users/{id}

# Update circle details
circle.update(description="New description")  # PATCH /circles/{id}
circle.update(name="Renamed Circle", description="Updated")  # PATCH /circles/{id}

# Update member roles
circle.update_member_role("user_123", "admin")  # PATCH /circles/{id}/members/user_123
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
- Usually returns the updated resource
- May return just success confirmation
- Includes updated timestamps

---

### PUT - Replace Resources

**Purpose:** Completely replace existing resources

**Characteristics:**
- Idempotent (multiple identical calls have same effect)
- Request body contains complete resource representation
- Replaces entire resource (missing fields may be cleared)
- Less commonly used than PATCH

**Client Methods:**
- `BaseClient._put(path, data, params=None)`

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

**Client Methods:**
- `BaseClient._delete(path, params=None)`

**Usage Patterns:**

```python
# Delete resources
user.delete()  # DELETE /users/{id}
circle.delete()  # DELETE /circles/{id}
vault["secrets"].delete("old_key")  # DELETE /vault/secrets/old_key

# Remove relationships
circle.remove_member("user_123")  # DELETE /circles/{id}/members/remove?user_id=user_123
vault.access.revoke("client_id", "vault_label")  # DELETE /access/vault_label?client_id=client_id

# Delete vault clients
vault.client.delete("client_123")  # DELETE /client/client_123
```

**Response Patterns:**
- Usually returns empty response (204 No Content)
- May return confirmation message
- Idempotent: deleting already-deleted resource succeeds

---

## API Design Patterns

### Resource Identification

Campus APIs use consistent patterns for identifying resources:

```python
# Single resource access
users["user_123"]           # /users/user_123
circles["circle_456"]       # /circles/circle_456
vault["app_secrets"]        # /vault/app_secrets

# Nested resource access
vault["app_secrets"]["api_key"]  # /vault/app_secrets/api_key
circle.members()                 # /circles/{id}/members
user.get_profile()              # /users/{id}/profile
```

### Query Parameters

GET requests support filtering and pagination through query parameters:

```python
# Search and filtering
circles.search("engineering")    # ?q=engineering
circles.list_by_user("user_123") # ?user_id=user_123

# Future pagination support
# users.list(limit=50, offset=100)  # ?limit=50&offset=100
```

### Request Bodies

POST and PATCH requests use JSON request bodies:

```python
# Create requests
users.new("email@example.com", "Name")
# → POST /users
# → {"email": "email@example.com", "name": "Name"}

# Update requests  
user.update(name="New Name", email="new@example.com")
# → PATCH /users/{id}
# → {"name": "New Name", "email": "new@example.com"}
```

### Response Formats

APIs return consistent JSON response formats:

```json
// Single resource
{
  "id": "user_123",
  "email": "user@example.com",
  "name": "User Name",
  "created_at": "2025-07-21T10:00:00Z"
}

// Collection response
{
  "users": [
    {
      "id": "user_123",
      "email": "user@example.com",
      "name": "User Name"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}

// Action response
{
  "success": true,
  "message": "User added to circle",
  "result": {
    "user_id": "user_123",
    "circle_id": "circle_456",
    "role": "member"
  }
}
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
user = users["user_123"]        # GET
user.update(name="New Name")    # PATCH  
user.delete()                   # DELETE

# Not idempotent - creates new resources
user = users.new("email", "name")  # POST
```

### Error Handling

Handle specific error types appropriately:

```python
from campus.client.errors import NotFoundError, ValidationError

try:
    user = users["user_123"]
    user.update(email="new@example.com")
except NotFoundError:
    print("User does not exist")
except ValidationError as e:
    print(f"Invalid update data: {e}")
```

### Resource Lifecycle

Follow standard resource lifecycle patterns:

```python
# Create → Read → Update → Delete
user = users.new("alice@example.com", "Alice")  # POST
user_data = user.data                           # GET (cached)
user.update(name="Alice Smith")                 # PATCH
user.delete()                                   # DELETE
```

### Batch Operations

For multiple operations, consider grouping:

```python
# Less efficient - multiple requests
for user_id in user_ids:
    users[user_id].delete()

# More efficient - batch operations (when available)
# users.delete_batch(user_ids)  # Future enhancement
```

### Caching

Understand client-side caching behavior:

```python
user = users["user_123"]
print(user.name)       # Fetches data from server
print(user.name)       # Uses cached data

user.update(name="New Name")  # Clears cache
print(user.name)       # Fetches fresh data
```
