# Campus Client API Reference

This document provides comprehensive reference documentation for the Campus Client unified interface, based on the actual server API implementation.

## Unified Campus Interface

The Campus Client provides a unified interface for accessing all Campus services through a single entry point.

### Module Interface

```python
from campus.client import Campus

# Initialize with automatic credential loading from environment variables
campus = Campus()

# Access all services through the unified interface
campus.users    # User management
campus.circles  # Circle/group management  
campus.vault    # Secret and configuration management
```

### Configuration

Set environment variables for automatic authentication:

```bash
export CAMPUS_APPS_BASE_URL="https://api.campus.example.com"
export CAMPUS_VAULT_BASE_URL="https://vault.campus.example.com"
export CLIENT_ID="your_client_id"
export CLIENT_SECRET="your_client_secret"
```

The Campus client automatically loads credentials from `CLIENT_ID` and `CLIENT_SECRET` environment variables. No manual credential configuration is required.

## Users Resource

The Users resource provides functionality for managing user accounts and authentication through the unified Campus interface.

### Access Pattern

```python
from campus.client import Campus
campus = Campus()

# All user operations are accessed through campus.users
users_client = campus.users
```

### Methods

#### `campus.users.new(*, email: str, name: str) -> Dict[str, Any]`

Create a new user account.

**Parameters:**
- `email` (str): User's email address (must be unique)
- `name` (str): User's display name

**Returns:** Dictionary containing the newly created user data

**Example:**
```python
user = campus.users.new(email="alice@example.com", name="Alice Smith")
print(f"Created user: {user['email']}")
print(f"User ID: {user['id']}")
```

#### `campus.users.me() -> Dict[str, Any]`

Get the authenticated user.

**Returns:** Dictionary containing the authenticated user data

**Raises:** `AuthenticationError` if not authenticated

**Example:**
```python
current_user = campus.users.me()
print(f"Logged in as: {current_user['email']}")
```

#### `campus.users.update(*, user_id: str, **kwargs) -> Dict[str, Any]`

Update a user's information.

**Parameters:**
- `user_id` (str): The user ID to update
- `**kwargs`: Fields to update (email, name, etc.)

**Returns:** Dictionary containing the updated user data

**Example:**
```python
updated_user = campus.users.update(user_id=user["id"], name="Alice Johnson")
print(f"Updated name to: {updated_user['name']}")
```

### Legacy Resource Interface

For direct resource access, the User resource objects are still available:

#### `campus.users[user_id] -> User`

Access individual user resource for advanced operations.

**Example:**
```python
user_resource = campus.users["user_123"]
profile = user_resource.get_profile()
user_resource.delete()
```

---

## Circles Resource

The Circles resource provides functionality for managing circles (groups) and their memberships through the unified Campus interface.

### Access Pattern

```python
from campus.client import Campus
campus = Campus()

# All circle operations are accessed through campus.circles
circles_client = campus.circles
```

### Methods

#### `campus.circles.new(*, name: str, description: str = "", **kwargs) -> Dict[str, Any]`

Create a new circle.

**Parameters:**
- `name` (str): Circle name
- `description` (str): Circle description (optional)
- `**kwargs`: Additional circle fields

**Returns:** Dictionary containing the newly created circle data

**Example:**
```python
circle = campus.circles.new(name="Engineering Team", description="Software engineering team")
print(f"Created circle: {circle['name']}")
print(f"Circle ID: {circle['id']}")
```

#### `campus.circles.update(*, circle_id: str, **kwargs) -> Dict[str, Any]`

Update a circle's information.

**Parameters:**
- `circle_id` (str): The circle ID to update
- `**kwargs`: Fields to update (name, description, etc.)

**Returns:** Dictionary containing the updated circle data

**Example:**
```python
updated_circle = campus.circles.update(circle_id=circle["id"], name="Platform Team")
print(f"Updated name to: {updated_circle['name']}")
```

### Circle Member Management

#### `campus.circles[circle_id].members` → Members sub-resource

Access member management for a specific circle:

**Example:**
```python
circle_members = campus.circles[circle["id"]].members

# Add a member
circle_members.add(user_id=user["id"], role="admin")

# List all members
members_data = circle_members.list()

# Remove a member
circle_members.remove(user_id="user_456")

# Update member access
circle_members["member_circle_id"].update(access=15)
```

### Legacy Resource Interface

For direct resource access, the Circle resource objects are still available:

#### `campus.circles[circle_id] -> Circle`

Access individual circle resource for advanced operations.

**Example:**
```python
circle_resource = campus.circles["circle_123"]
circle_data = circle_resource.get()
circle_resource.move(parent_circle_id="parent_123")
circle_resource.delete()
```

---

## Error Handling

All Campus Client operations may raise the following exceptions:

### `AuthenticationError`

Raised when authentication is required or has failed.

**Example:**
```python
from campus.client.errors import AuthenticationError

try:
    user = campus.users.me()
except AuthenticationError:
    print("Please set CLIENT_ID and CLIENT_SECRET environment variables")
```

### `AccessDeniedError`

Raised when the client lacks permission for the requested operation.

### `NotFoundError`

Raised when a requested resource doesn't exist.

**Example:**
```python
from campus.client.errors import NotFoundError

try:
    secret = campus.vault["secrets"]["nonexistent_key"].get()
except NotFoundError:
    print("Secret not found")
```

### `ValidationError`

Raised when input data is invalid.

### `NetworkError`

Raised when network communication fails.

## Complete Example

Here's a complete example showing the unified Campus Client interface:

```python
from campus.client import Campus
from campus.client.errors import AuthenticationError, NotFoundError

# Initialize Campus client
campus = Campus()

try:
    # Create a user
    user = campus.users.new(email="alice@example.com", name="Alice")
    print(f"Created user: {user['email']}")
    
    # Update user information  
    updated_user = campus.users.update(user_id=user["id"], name="Alice Smith")
    
    # Create a circle
    circle = campus.circles.new(name="Engineering Team", description="Development team")
    
    # Add user to circle
    campus.circles[circle["id"]].members.add(user_id=user["id"])
    
    # Store secrets in vault
    campus.vault["secrets"]["API_KEY"].set(value="secret_value")
    
    # Retrieve secrets
    api_key = str(campus.vault["secrets"]["API_KEY"])
    print(f"API Key: {api_key}")
    
except AuthenticationError:
    print("Authentication required")
except NotFoundError as e:
    print(f"Resource not found: {e}")
```

## Rate Limiting

Campus services implement rate limiting. Clients should handle `429 Too Many Requests` responses by implementing exponential backoff.

## Best Practices

1. **Use the unified interface**: Import `Campus` and access all services through it
2. **Set environment variables**: Configure `CLIENT_ID` and `CLIENT_SECRET` for automatic authentication
3. **Handle dictionary responses**: All methods return dictionaries, not objects
4. **Handle errors gracefully**: Always catch and handle specific exception types
5. **Use chained subscription**: Access vault secrets with `campus.vault["label"]["key"]`
6. **Validate inputs**: Check data before making API calls
7. **Log operations**: Include request IDs for debugging
