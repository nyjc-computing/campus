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
# Import campus client with central namespace
import campus.client as campus

# Create and manage users
user = campus.users.new(email="alice@example.com", name="Alice")
print(f"Created user: {user.email}")

# Update user information
user.update(name="Alice Smith")

# Work with circles (groups)
circle = campus.circles.new(name="Engineering Team", description="Software engineering team")
circle.add_member(user_id=user.id, role="admin")

# Vault operations
campus.vault["secrets"].set(key="api_key", value="secret_value")
api_key = campus.vault["secrets"].get(key="api_key")
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
import campus.client as campus

# Set authentication credentials
campus.users.set_credentials(client_id="client_id", client_secret="client_secret")

# Or configure base URLs at runtime
campus.config.set_service_base_url(service="apps", base_url="https://api.staging.example.com")
```

## API Reference

### Apps Service

#### Users

```python
import campus.client as campus

# User management
user = campus.users.new(email="email@example.com", name="Display Name")
user = campus.users["user_id"]  # Get by ID
current_user = campus.users.me()  # Get authenticated user
all_users = campus.users.list_users()  # List all users

# User operations
user.update(name="New Name", email="new@example.com")
profile = user.get_profile()
user.delete()

# User properties
print(user.id, user.email, user.name)
```

#### Circles

```python
import campus.client as campus

# Circle management
circle = campus.circles.new(name="Circle Name", description="Description")
circle = campus.circles.get_by_id(circle_id="circle_id")
all_circles = campus.circles.list()
user_circles = campus.circles.list_by_user(user_id="user_id")
search_results = campus.circles.search(query="query")

# Circle operations
circle.update(name="New Name", description="New description")
circle.move(parent_id="parent_circle_id")  # Move to different parent
circle.delete()

# Member management
circle.add_member(user_id="user_id", role="admin")
circle.remove_member(user_id="user_id")
circle.update_member_role(user_id="user_id", role="member")
members = circle.members()
users_in_circle = circle.get_users()

# Circle properties
print(circle.id, circle.name, circle.description)
```

### Vault Service

#### Vault Operations

```python
import campus.client as campus

# Vault discovery
available_vaults = campus.vault.list_vaults()

# Secret management
campus.vault["app_secrets"].set(key="database_url", value="postgres://...")
database_url = campus.vault["app_secrets"].get(key="database_url")
campus.vault["app_secrets"].delete(key="old_key")

# Check operations
has_key = campus.vault["app_secrets"].has(key="database_url")
all_keys = campus.vault["app_secrets"].list()
```

#### Access Management

```python
import campus.client as campus

# Grant/revoke access
campus.vault.access.grant(client_id="client_id", vault_label="vault_label", permissions=["read", "write"])
campus.vault.access.revoke(client_id="client_id", vault_label="vault_label")

# Check permissions
permissions = campus.vault.access.check(client_id="client_id", vault_label="vault_label")
```

#### Client Management

```python
import campus.client as campus

# Client operations
client = campus.vault.client.new(name="Client Name", description="Description")
all_clients = campus.vault.client.list()
client_info = campus.vault.client.get(client_id="client_id")
campus.vault.client.delete(client_id="client_id")
```

## Error Handling

Campus Client provides specific exception types for different error conditions:

```python
import campus.client as campus
from campus.client.errors import (
    AuthenticationError,
    AccessDeniedError,
    NotFoundError,
    ValidationError,
    NetworkError
)

try:
    user = campus.users["nonexistent_id"]
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
import campus.client as campus

# Module objects provide direct access to functionality
user = campus.users["user_id"]        # users.UserModule.__getitem__()
circle = campus.circles.new(...)      # circles.CircleModule.new()
secret = campus.vault["app"]["key"]    # vault.VaultModule.__getitem__()
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
