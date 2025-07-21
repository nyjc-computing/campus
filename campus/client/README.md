# Campus Client Library

A Python HTTP client library for interacting with Campus vault and apps services.

## Overview

Campus Client provides a convenient, Pythonic interface for accessing Campus services. It's designed to handle authentication, service discovery, and provide clean APIs for common operations.

## Features

- **Service-based organization**: Separate modules for apps and vault services
- **Flexible configuration**: Environment-based or manual service URL configuration
- **Clean interfaces**: Hidden implementation details with intuitive module APIs
- **Full API coverage**: Support for all documented Campus service endpoints
- **Authentication handling**: Built-in OAuth2 and token management
- **Error handling**: Comprehensive error types with meaningful messages

## Installation

```bash
pip install campus-client
```

## Quick Start

### Basic Usage

```python
# Import service modules
from campus.client.apps import users, circles
from campus.client.vault import vault

# Create and manage users
user = users.new("alice@example.com", "Alice")
print(f"Created user: {user.email}")

# Update user information
user.update(name="Alice Smith")

# Work with circles (groups)
circle = circles.new("Engineering Team", "Software engineering team")
circle.add_member(user.id, "admin")

# Vault operations
vault["secrets"].set("api_key", "secret_value")
api_key = vault["secrets"].get("api_key")
```

### Configuration

#### Environment Variables

```bash
# Service base URLs
export CAMPUS_APPS_BASE_URL="https://api.campus.example.com"
export CAMPUS_VAULT_BASE_URL="https://vault.campus.example.com"

# Authentication (optional - can be set programmatically)
export CAMPUS_CLIENT_ID="your_client_id"
export CAMPUS_CLIENT_SECRET="your_client_secret"
```

#### Programmatic Configuration

```python
from campus.client.apps import users

# Set authentication credentials
users.set_credentials("client_id", "client_secret")

# Or configure base URLs at runtime
from campus.client import config
config.set_service_base_url("apps", "https://api.staging.example.com")
```

## API Reference

### Apps Service

#### Users

```python
from campus.client.apps import users

# User management
user = users.new("email@example.com", "Display Name")
user = users["user_id"]  # Get by ID
current_user = users.me()  # Get authenticated user
all_users = users.list_users()  # List all users

# User operations
user.update(name="New Name", email="new@example.com")
profile = user.get_profile()
user.delete()

# User properties
print(user.id, user.email, user.name)
```

#### Circles

```python
from campus.client.apps import circles

# Circle management
circle = circles.new("Circle Name", "Description")
circle = circles.get_by_id("circle_id")
all_circles = circles.list()
user_circles = circles.list_by_user("user_id")
search_results = circles.search("query")

# Circle operations
circle.update(name="New Name", description="New description")
circle.move("parent_circle_id")  # Move to different parent
circle.delete()

# Member management
circle.add_member("user_id", "admin")
circle.remove_member("user_id")
circle.update_member_role("user_id", "member")
members = circle.members()
users_in_circle = circle.get_users()

# Circle properties
print(circle.id, circle.name, circle.description)
```

### Vault Service

#### Vault Operations

```python
from campus.client.vault import vault

# Vault discovery
available_vaults = vault.list_vaults()

# Secret management
vault["app_secrets"].set("database_url", "postgres://...")
database_url = vault["app_secrets"].get("database_url")
vault["app_secrets"].delete("old_key")

# Check operations
has_key = vault["app_secrets"].has("database_url")
all_keys = vault["app_secrets"].list()
```

#### Access Management

```python
from campus.client.vault import vault

# Grant/revoke access
vault.access.grant("client_id", "vault_label", ["read", "write"])
vault.access.revoke("client_id", "vault_label")

# Check permissions
permissions = vault.access.check("client_id", "vault_label")
```

#### Client Management

```python
from campus.client.vault import vault

# Client operations
client = vault.client.new("Client Name", "Description")
all_clients = vault.client.list()
client_info = vault.client.get("client_id")
vault.client.delete("client_id")
```

## Error Handling

Campus Client provides specific exception types for different error conditions:

```python
from campus.client.errors import (
    AuthenticationError,
    AccessDeniedError,
    NotFoundError,
    ValidationError,
    NetworkError
)

try:
    user = users["nonexistent_id"]
except NotFoundError:
    print("User not found")
except AuthenticationError:
    print("Authentication required")
except ValidationError as e:
    print(f"Invalid input: {e}")
```

## Architecture

### Service Organization

```
campus.client/
├── apps/           # Apps service clients
│   ├── users.py    # User management
│   └── circles.py  # Circle (group) management
├── vault/          # Vault service clients
│   ├── vault.py    # Secret storage
│   ├── access.py   # Access control
│   └── client.py   # Client management
├── base.py         # Shared HTTP client
├── config.py       # Configuration management
└── errors.py       # Exception definitions
```

### Module Pattern

Campus Client uses a module replacement pattern to provide clean interfaces:

```python
# These imports return module objects, not classes
from campus.client.apps import users, circles
from campus.client.vault import vault

# Module objects provide direct access to functionality
user = users["user_id"]        # users.UserModule.__getitem__()
circle = circles.new(...)      # circles.CircleModule.new()
secret = vault["app"]["key"]   # vault.VaultModule.__getitem__()
```

This design hides implementation details and provides intuitive APIs.

### HTTP Client

All service modules share a common `BaseClient` that handles:

- **Authentication**: OAuth2 token management
- **Request/Response**: JSON serialization and HTTP error handling
- **URL Construction**: Service discovery and path building
- **Error Mapping**: HTTP status codes to Python exceptions

## Contributing

### Development Setup

```bash
# Clone the repository
git clone https://github.com/nyjc-computing/campus.git
cd campus

# Install in development mode
pip install -e .

# Run tests
python -m pytest tests/
```

### Testing

Campus Client includes comprehensive tests for all functionality:

```bash
# Run specific test modules
python -m pytest tests/test_users.py
python -m pytest tests/test_circles.py
python -m pytest tests/test_vault.py

# Test with coverage
python -m pytest --cov=campus.client tests/
```

## License

This project is licensed under the MIT License. See LICENSE for details.

## Support

For issues and questions:

- **GitHub Issues**: [https://github.com/nyjc-computing/campus/issues](https://github.com/nyjc-computing/campus/issues)
- **Documentation**: [https://campus.nyjc.dev/docs](https://campus.nyjc.dev/docs)
- **Email**: computing@nyjc.edu.sg
