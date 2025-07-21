# Campus Client API Reference

This document provides comprehensive reference documentation for all Campus Client resources and their available operations.

## Apps Service Resources

### Users Resource

The Users resource provides functionality for managing user accounts and authentication.

#### Module Interface

```python
from campus.client.apps import users
```

#### Methods

##### `users.new(email: str, name: str) -> User`

Create a new user account.

**Parameters:**
- `email` (str): User's email address (must be unique)
- `name` (str): User's display name

**Returns:** `User` object for the newly created user

**Example:**
```python
user = users.new("alice@example.com", "Alice Smith")
print(f"Created user {user.id} with email {user.email}")
```

##### `users["user_id"] -> User`

Retrieve an existing user by their ID.

**Parameters:**
- `user_id` (str): The unique identifier for the user

**Returns:** `User` object

**Raises:** `NotFoundError` if user doesn't exist

**Example:**
```python
user = users["user_123"]
print(f"User name: {user.name}")
```

##### `users.me() -> User`

Get the currently authenticated user.

**Returns:** `User` object for the authenticated user

**Raises:** `AuthenticationError` if not authenticated

**Example:**
```python
current_user = users.me()
print(f"Logged in as: {current_user.email}")
```

##### `users.list_users() -> List[User]`

List all users in the system.

**Returns:** List of `User` objects

**Note:** This may be a large result set. Consider pagination for production use.

**Example:**
```python
all_users = users.list_users()
print(f"Total users: {len(all_users)}")
```

##### `users.set_credentials(client_id: str, client_secret: str) -> None`

Set authentication credentials for this users client.

**Parameters:**
- `client_id` (str): OAuth2 client ID
- `client_secret` (str): OAuth2 client secret

**Example:**
```python
users.set_credentials("my_client_id", "my_client_secret")
```

#### User Object Methods

##### `user.update(**kwargs) -> None`

Update user information.

**Parameters:**
- `**kwargs`: Fields to update (email, name, etc.)

**Example:**
```python
user.update(name="Alice Johnson", email="alice.johnson@example.com")
```

##### `user.delete() -> None`

Delete the user account.

**Warning:** This operation is irreversible.

**Example:**
```python
user.delete()
```

##### `user.get_profile() -> Dict[str, Any]`

Get detailed user profile information.

**Returns:** Dictionary containing complete user profile data

**Example:**
```python
profile = user.get_profile()
print(f"User joined: {profile['created_at']}")
print(f"Last login: {profile['last_login']}")
```

#### User Object Properties

##### `user.id -> str`

The unique identifier for the user.

##### `user.email -> str`

The user's email address.

##### `user.name -> str`

The user's display name.

##### `user.data -> Dict[str, Any]`

Complete user data from the API (cached, reloaded on updates).

---

### Circles Resource

The Circles resource provides functionality for managing groups and their memberships.

#### Module Interface

```python
from campus.client.apps import circles
```

#### Methods

##### `circles.new(name: str, description: str = "", parent_id: str = None) -> Circle`

Create a new circle.

**Parameters:**
- `name` (str): Circle name
- `description` (str, optional): Circle description
- `parent_id` (str, optional): Parent circle ID for nested circles

**Returns:** `Circle` object for the newly created circle

**Example:**
```python
engineering = circles.new("Engineering", "Software engineering team")
frontend = circles.new("Frontend", "Frontend developers", engineering.id)
```

##### `circles.get_by_id(circle_id: str) -> Circle`

Retrieve a circle by its ID.

**Parameters:**
- `circle_id` (str): The unique identifier for the circle

**Returns:** `Circle` object

**Raises:** `NotFoundError` if circle doesn't exist

**Example:**
```python
circle = circles.get_by_id("circle_123")
```

##### `circles["circle_id"] -> Circle`

Shorthand for `get_by_id()`.

**Example:**
```python
circle = circles["circle_123"]
```

##### `circles.list() -> List[Circle]`

List all circles.

**Returns:** List of `Circle` objects

**Example:**
```python
all_circles = circles.list()
```

##### `circles.list_by_user(user_id: str) -> List[Circle]`

List circles that a specific user is a member of.

**Parameters:**
- `user_id` (str): User ID to filter by

**Returns:** List of `Circle` objects

**Example:**
```python
user_circles = circles.list_by_user("user_123")
```

##### `circles.search(query: str) -> List[Circle]`

Search circles by name or description.

**Parameters:**
- `query` (str): Search term

**Returns:** List of matching `Circle` objects

**Example:**
```python
results = circles.search("engineering")
```

##### `circles.set_credentials(client_id: str, client_secret: str) -> None`

Set authentication credentials for this circles client.

#### Circle Object Methods

##### `circle.update(**kwargs) -> None`

Update circle information.

**Parameters:**
- `**kwargs`: Fields to update (name, description, etc.)

**Example:**
```python
circle.update(name="New Name", description="Updated description")
```

##### `circle.delete() -> None`

Delete the circle.

**Warning:** This will also remove all memberships.

**Example:**
```python
circle.delete()
```

##### `circle.move(parent_circle_id: str) -> None`

Move circle to a different parent.

**Parameters:**
- `parent_circle_id` (str): New parent circle ID

**Example:**
```python
circle.move("new_parent_circle_id")
```

##### `circle.add_member(user_id: str, role: str = "member") -> None`

Add a user to the circle.

**Parameters:**
- `user_id` (str): User ID to add
- `role` (str): Member role ("admin", "member", "viewer")

**Example:**
```python
circle.add_member("user_123", "admin")
```

##### `circle.remove_member(user_id: str) -> None`

Remove a user from the circle.

**Parameters:**
- `user_id` (str): User ID to remove

**Example:**
```python
circle.remove_member("user_123")
```

##### `circle.update_member_role(user_id: str, role: str) -> None`

Update a member's role in the circle.

**Parameters:**
- `user_id` (str): User ID
- `role` (str): New role ("admin", "member", "viewer")

**Example:**
```python
circle.update_member_role("user_123", "admin")
```

##### `circle.members() -> List[Dict[str, Any]]`

Get all circle members.

**Returns:** List of member dictionaries with user info and roles

**Example:**
```python
members = circle.members()
for member in members:
    print(f"User {member['user_id']} has role {member['role']}")
```

##### `circle.get_users() -> List[Dict[str, Any]]`

Get detailed user information for all circle members.

**Returns:** List of user dictionaries

**Example:**
```python
users_in_circle = circle.get_users()
for user in users_in_circle:
    print(f"{user['name']} ({user['email']})")
```

#### Circle Object Properties

##### `circle.id -> str`

The unique identifier for the circle.

##### `circle.name -> str`

The circle's name.

##### `circle.description -> str`

The circle's description.

##### `circle.data -> Dict[str, Any]`

Complete circle data from the API.

---

## Vault Service Resources

### Vault Resource

The Vault resource provides secure storage and retrieval of secrets and configuration data.

#### Module Interface

```python
from campus.client.vault import vault
```

#### Methods

##### `vault.list_vaults() -> List[str]`

List all available vault labels.

**Returns:** List of vault label strings

**Example:**
```python
vaults = vault.list_vaults()
print(f"Available vaults: {vaults}")
```

##### `vault["vault_label"] -> VaultInstance`

Access a specific vault by label.

**Parameters:**
- `vault_label` (str): The vault identifier

**Returns:** `VaultInstance` object for the specified vault

**Example:**
```python
app_secrets = vault["app_secrets"]
database_config = vault["database_config"]
```

#### VaultInstance Methods

##### `vault_instance.list() -> List[str]`

List all keys in this vault.

**Returns:** List of key names

**Example:**
```python
keys = vault["app_secrets"].list()
print(f"Available secrets: {keys}")
```

##### `vault_instance.get(key: str) -> str`

Retrieve a secret value.

**Parameters:**
- `key` (str): The secret key name

**Returns:** Secret value as string

**Raises:** `NotFoundError` if key doesn't exist

**Example:**
```python
api_key = vault["app_secrets"].get("external_api_key")
```

##### `vault_instance.set(key: str, value: str) -> None`

Store a secret value.

**Parameters:**
- `key` (str): The secret key name
- `value` (str): The secret value

**Example:**
```python
vault["app_secrets"].set("database_password", "secure_password_123")
```

##### `vault_instance.delete(key: str) -> None`

Delete a secret.

**Parameters:**
- `key` (str): The secret key name

**Raises:** `NotFoundError` if key doesn't exist

**Example:**
```python
vault["app_secrets"].delete("old_api_key")
```

##### `vault_instance.has(key: str) -> bool`

Check if a key exists.

**Parameters:**
- `key` (str): The secret key name

**Returns:** True if key exists, False otherwise

**Example:**
```python
if vault["app_secrets"].has("database_password"):
    password = vault["app_secrets"].get("database_password")
```

---

### Access Management Resource

The Access resource manages permissions for vault access.

#### Module Interface

```python
from campus.client.vault import vault
# Access is available as vault.access
```

#### Methods

##### `vault.access.grant(client_id: str, vault_label: str, permissions: List[str]) -> None`

Grant vault access to a client.

**Parameters:**
- `client_id` (str): Client identifier
- `vault_label` (str): Vault to grant access to
- `permissions` (List[str]): List of permissions ("read", "write", "admin")

**Example:**
```python
vault.access.grant("app_client_123", "app_secrets", ["read", "write"])
```

##### `vault.access.revoke(client_id: str, vault_label: str) -> None`

Revoke vault access from a client.

**Parameters:**
- `client_id` (str): Client identifier
- `vault_label` (str): Vault to revoke access from

**Example:**
```python
vault.access.revoke("app_client_123", "app_secrets")
```

##### `vault.access.check(client_id: str, vault_label: str) -> Dict[str, Any]`

Check client permissions for a vault.

**Parameters:**
- `client_id` (str): Client identifier
- `vault_label` (str): Vault to check

**Returns:** Dictionary with permission details

**Example:**
```python
permissions = vault.access.check("app_client_123", "app_secrets")
print(f"Permissions: {permissions['permissions']}")
```

---

### Client Management Resource

The Client resource manages vault client registrations.

#### Module Interface

```python
from campus.client.vault import vault
# Client management is available as vault.client
```

#### Methods

##### `vault.client.new(name: str, description: str = "") -> Dict[str, Any]`

Create a new vault client.

**Parameters:**
- `name` (str): Client name
- `description` (str, optional): Client description

**Returns:** Dictionary with client information including ID and credentials

**Example:**
```python
client = vault.client.new("MyApp", "Application for processing data")
print(f"Client ID: {client['client_id']}")
print(f"Client Secret: {client['client_secret']}")
```

##### `vault.client.list() -> List[Dict[str, Any]]`

List all vault clients.

**Returns:** List of client dictionaries

**Example:**
```python
clients = vault.client.list()
for client in clients:
    print(f"Client: {client['name']} (ID: {client['client_id']})")
```

##### `vault.client.get(client_id: str) -> Dict[str, Any]`

Get details for a specific client.

**Parameters:**
- `client_id` (str): Client identifier

**Returns:** Dictionary with client details

**Raises:** `NotFoundError` if client doesn't exist

**Example:**
```python
client = vault.client.get("client_123")
print(f"Client name: {client['name']}")
```

##### `vault.client.delete(client_id: str) -> None`

Delete a vault client.

**Parameters:**
- `client_id` (str): Client identifier

**Warning:** This will revoke all vault access for this client.

**Example:**
```python
vault.client.delete("client_123")
```

---

## Error Handling

All resources may raise the following exceptions:

### `AuthenticationError`

Raised when authentication is required or has failed.

### `AccessDeniedError`

Raised when the client lacks permission for the requested operation.

### `NotFoundError`

Raised when a requested resource doesn't exist.

### `ValidationError`

Raised when input data is invalid.

### `NetworkError`

Raised when network communication fails.

## Rate Limiting

Campus services implement rate limiting. Clients should handle `429 Too Many Requests` responses by implementing exponential backoff.

## Best Practices

1. **Cache credentials**: Set credentials once per application lifecycle
2. **Handle errors gracefully**: Always catch and handle specific exception types
3. **Use context managers**: For operations that require cleanup
4. **Avoid polling**: Use webhooks or event-driven patterns when possible
5. **Validate inputs**: Check data before making API calls
6. **Log operations**: Include request IDs for debugging
