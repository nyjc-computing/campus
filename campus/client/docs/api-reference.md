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
# Authentication
export CLIENT_ID="your_client_id"
export CLIENT_SECRET="your_client_secret"
```

The Campus client automatically:
- Loads credentials from `CLIENT_ID` and `CLIENT_SECRET` environment variables
- Selects appropriate service URLs based on the `ENV` environment variable:
  - **Production**: `https://api.campus.nyjc.app` and `https://vault.campus.nyjc.app`
  - **Other environments**: `https://api.campus.nyjc.dev` and `https://vault.campus.nyjc.dev`

No manual URL configuration is required.

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

## Vault Resource

The Vault resource provides secure storage and retrieval of secrets and configuration data through the unified Campus interface.

### Access Pattern

```python
from campus.client import Campus
campus = Campus()

# All vault operations are accessed through campus.vault
vault_client = campus.vault
```

### Chained Subscription Interface

The vault supports intuitive chained subscription for accessing secrets:

```python
# Access secrets using chained subscription
api_key = campus.vault["secrets"]["API_KEY"]
database_url = campus.vault["config"]["DATABASE_URL"]

# Get secret values
api_key_value = str(api_key)  # Convert to string
api_key_value = api_key.get()  # Explicit get method

# Set secret values
api_key.set(value="new_api_key_value")

# Delete secrets
api_key.delete()
```

### Vault Collection Methods

#### `campus.vault[vault_label] -> VaultCollection`

Access a specific vault collection by label.

**Parameters:**
- `vault_label` (str): The vault identifier (e.g., "secrets", "config", "oauth")

**Returns:** `VaultCollection` object for the specified vault

**Example:**
```python
secrets_vault = campus.vault["secrets"]
config_vault = campus.vault["config"]
```

#### `campus.vault[vault_label].list() -> List[str]`

List all keys in a vault collection.

**Returns:** List of key names

**Example:**
```python
secret_keys = campus.vault["secrets"].list()
print(f"Available secrets: {secret_keys}")
```

### Individual Secret Access

#### `campus.vault[vault_label][key] -> VaultKey`

Access individual secrets using chained subscription.

**Returns:** `VaultKey` object with methods for secret operations

#### VaultKey Methods

##### `vault_key.get() -> str`

Get the secret value.

**Returns:** The secret value as a string

**Raises:** `NotFoundError` if the key doesn't exist

**Example:**
```python
api_key = campus.vault["secrets"]["API_KEY"].get()
```

##### `vault_key.set(*, value: str) -> str`

Set the secret value.

**Parameters:**
- `value` (str): The secret value to store

**Returns:** The secret value that was stored

**Example:**
```python
campus.vault["secrets"]["API_KEY"].set(value="new_secret_value")
```

##### `vault_key.delete() -> bool`

Delete the secret.

**Returns:** True if deleted successfully

**Raises:** `NotFoundError` if the key doesn't exist

**Example:**
```python
campus.vault["secrets"]["old_key"].delete()
```

##### `str(vault_key) -> str`

Convert VaultKey to string (convenience method for getting value).

**Example:**
```python
# These are equivalent:
api_key = str(campus.vault["secrets"]["API_KEY"])
api_key = campus.vault["secrets"]["API_KEY"].get()
```

### Vault Management

#### `campus.vault.list_vaults() -> List[str]`

List all available vault labels.

**Returns:** List of vault label strings

**Example:**
```python
vaults = campus.vault.list_vaults()
print(f"Available vaults: {vaults}")
```

### Access Management

The Access resource manages permissions for vault access through the unified Campus interface.

#### Access Pattern

```python
from campus.client import Campus
campus = Campus()

# Access management is available through campus.vault.access
access_client = campus.vault.access
```

#### Methods

##### `campus.vault.access.grant(client_id: str, vault_label: str, permissions: List[str]) -> None`

Grant vault access to a client.

**Parameters:**
- `client_id` (str): Client identifier
- `vault_label` (str): Vault to grant access to
- `permissions` (List[str]): List of permissions ("read", "write", "admin")

**Example:**
```python
campus.vault.access.grant("app_client_123", "secrets", ["read", "write"])
```

##### `campus.vault.access.revoke(client_id: str, vault_label: str) -> None`

Revoke vault access from a client.

**Parameters:**
- `client_id` (str): Client identifier
- `vault_label` (str): Vault to revoke access from

**Example:**
```python
campus.vault.access.revoke("app_client_123", "secrets")
```

##### `campus.vault.access.check(client_id: str, vault_label: str) -> Dict[str, Any]`

Check client permissions for a vault.

**Parameters:**
- `client_id` (str): Client identifier
- `vault_label` (str): Vault to check

**Returns:** Dictionary with permission details

**Example:**
```python
permissions = campus.vault.access.check("app_client_123", "secrets")
print(f"Permissions: {permissions['permissions']}")
```

### Client Management

The Client resource manages vault client registrations through the unified Campus interface.

#### Access Pattern

```python
from campus.client import Campus
campus = Campus()

# Client management is available through campus.vault.client
client_mgmt = campus.vault.client
```

#### Methods

##### `campus.vault.client.new(name: str, description: str = "") -> Dict[str, Any]`

Create a new vault client.

**Parameters:**
- `name` (str): Client name
- `description` (str, optional): Client description

**Returns:** Dictionary with client information including ID and credentials

**Example:**
```python
client = campus.vault.client.new("MyApp", "Application for processing data")
print(f"Client ID: {client['client_id']}")
print(f"Client Secret: {client['client_secret']}")
```

##### `campus.vault.client.list() -> List[Dict[str, Any]]`

List all vault clients.

**Returns:** List of client dictionaries

**Example:**
```python
clients = campus.vault.client.list()
for client in clients:
    print(f"Client: {client['name']} (ID: {client['client_id']})")
```

##### `campus.vault.client.get(client_id: str) -> Dict[str, Any]`

Get details for a specific client.

**Parameters:**
- `client_id` (str): Client identifier

**Returns:** Dictionary with client details

**Raises:** `NotFoundError` if client doesn't exist

**Example:**
```python
client = campus.vault.client.get("client_123")
print(f"Client name: {client['name']}")
```

##### `campus.vault.client.delete(client_id: str) -> None`

Delete a vault client.

**Parameters:**
- `client_id` (str): Client identifier

**Warning:** This will revoke all vault access for this client.

**Example:**
```python
campus.vault.client.delete("client_123")
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

# Initialize Campus client - URLs are automatically configured based on ENV
# Just need to set CLIENT_ID and CLIENT_SECRET environment variables
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
    print("Authentication required - set CLIENT_ID and CLIENT_SECRET environment variables")
except NotFoundError as e:
    print(f"Resource not found: {e}")
```

## Rate Limiting

Campus services implement rate limiting. Clients should handle `429 Too Many Requests` responses by implementing exponential backoff.

## Best Practices

1. **Use the unified interface**: Import `Campus` and access all services through it
2. **Set authentication environment variables**: Configure `CLIENT_ID` and `CLIENT_SECRET`
3. **Use correct environment**: Set `ENV` to "production" for production deployments
4. **Handle dictionary responses**: All methods return dictionaries, not objects
5. **Handle errors gracefully**: Always catch and handle specific exception types
6. **Use chained subscription**: Access vault secrets with `campus.vault["label"]["key"]`
7. **Validate inputs**: Check data before making API calls
8. **Log operations**: Include request IDs for debugging
