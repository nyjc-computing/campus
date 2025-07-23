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
from campus.client import Campus

# Set CLIENT_ID and CLIENT_SECRET environment variables for authentication
campus = Campus()
user = campus.users.new(email="alice@example.com", name="Alice")
print(f"Created user: {user['email']}")

# Update user information
campus.users.update(name="Alice Smith")

# Work with circles (groups)
circle = campus.circles.new(name="Engineering Team", description="Software engineering team")
campus.circles[circle["id"]].members.add(user_id=user["id"])

# Vault operations
campus.vault["secrets"]["API_KEY"].set(value="secret_value")
api_key = campus.vault["secrets"]["API_KEY"]
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

## API Reference

See docs/api-reference.md for detailed API documentation.

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

## Support

For issues and questions:

- **GitHub Issues**: [https://github.com/nyjc-computing/campus/issues](https://github.com/nyjc-computing/campus/issues)
- **Questions**: #general on Discord for general questions, #campus for specific questions
