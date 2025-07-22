# Campus

A modular Python application framework for educational institution management, built with Flask and designed around clean architecture principles.

## Overview

Campus is organized as a collection of independent, loosely-coupled services that can be deployed together or separately. Each service follows the same architectural patterns while maintaining clear boundaries and avoiding circular dependencies.

## Architecture

### Package Structure

```
campus/
├── apps/           # Web applications and API services
├── client/         # Client interfaces for accessing Campus services
├── common/         # Shared utilities and schemas
├── models/         # Data models and business logic
├── services/       # Business services (email, etc.)
├── storage/        # Data persistence layer
├── vault/          # Secrets management service
└── workspace/      # Development workspace utilities
```

### Design Principles

1. **Separation of Concerns**: Each package has a single, well-defined responsibility
2. **Dependency Inversion**: Higher-level modules don't depend on lower-level modules
3. **Interface Segregation**: Clients depend only on interfaces they actually use
4. **Single Responsibility**: Each module has one reason to change
5. **Open/Closed**: Open for extension, closed for modification
6. **Circular Import Avoidance**: Clear dependency hierarchy prevents import cycles

### Service Independence

Each major service (`vault`, `storage`, `models`) is designed to be independently deployable:

- **campus.vault**: Secrets management with its own database and authentication
- **campus.storage**: Data persistence layer with flexible backend support
- **campus.models**: Business logic and domain models
- **campus.apps**: Web applications and API endpoints
- **campus.services**: Supporting services (email, notifications, etc.)

## Key Components

### 🔐 Vault (`campus.vault`)

Secure secrets management service with:
- Independent PostgreSQL database (no circular dependencies)
- Client authentication with CLIENT_ID/CLIENT_SECRET
- Bitflag permission system (READ, CREATE, UPDATE, DELETE)
- RESTful API with three blueprints:
  - `/vault/*` - Secret operations
  - `/access/*` - Permission management
  - `/client/*` - Client management

### 💾 Storage (`campus.storage`)

Abstract data persistence layer supporting:
- Multiple backends (PostgreSQL, MongoDB, etc.)
- Table/collection abstraction
- Query builder interface
- Connection pooling and transaction management

### 🏛️ Models (`campus.models`)

Domain models and business logic:
- User management and authentication
- Circle (group) management and permissions
- Session handling and state management
- Email OTP verification
- Source attribution and tracking

### 🌐 Apps (`campus.apps`)

Web applications and API services:
- Flask applications with blueprint architecture
- RESTful API endpoints
- Authentication and authorization middleware
- Health checks and monitoring

### 🔌 Client (`campus.client`)

HTTP-like interfaces for accessing Campus services:
- Namespace-based imports to avoid circular dependencies
- RESTful conventions (`users["id"].get()`, `vault["label"].set()`)
- Automatic authentication and error handling
- Individual service clients (`vault`, `users`, `circles`)

### 🛠️ Common (`campus.common`)

Shared utilities and schemas:
- Configuration management and feature flags
- Validation utilities (Flask integration, naming, records)
- Schema definitions and data structures
- Time utilities and UID generation
- Secret management utilities

## Usage Patterns

### Service Access

Instead of direct imports that can create circular dependencies:

```python
# ❌ Avoid - can create circular imports
from campus.vault.model import Vault
from campus.models.user import User

# ✅ Use - namespace clients prevent circular imports
import campus.client.vault as vault
import campus.client.users as users

secret = vault["apps"].get("DATABASE_URL")
user = users["user123"]
```

### Configuration

Services use environment variables for configuration:

```bash
# Vault service
export VAULTDB_URI="postgresql://..."
export CLIENT_ID="your_client_id"
export CLIENT_SECRET="your_client_secret"

# Storage service  
export STORAGE_URI="postgresql://..."

# Application secrets - SECRET_KEY now stored in vault under 'campus' label
# No SECRET_KEY environment variable needed
```

### Development

Each service can be developed and tested independently:

```bash
# Test vault service
cd campus/vault && python -m pytest

# Run vault standalone
python -c "from campus.vault import create_app; create_app().run()"

# Test client interfaces
python -c "import campus.client.vault as vault; print(vault.list_vaults())"
```

## Deployment

### Standalone Services

Each service can be deployed independently:

```python
# Deploy vault service
from campus.vault import create_app
app = create_app()

# Deploy main application
from campus.apps import create_app  
app = create_app()
```

### Integrated Application

All services can be combined in a single deployment:

```python
from flask import Flask
from campus import vault, apps, services

app = Flask(__name__)
vault.init_app(app)
apps.init_app(app)
services.init_app(app)
```

## Authentication & Security

### Client Authentication

Services use CLIENT_ID/CLIENT_SECRET for inter-service communication:

```python
# Automatic authentication via environment
import campus.client.vault as vault
secret = vault["apps"].get("key")  # Uses CLIENT_ID/CLIENT_SECRET

# Explicit authentication for scripts
vault.set_credentials("client_id", "client_secret")
```

### Permission System

Vault uses bitflag permissions for fine-grained access control:

```python
from campus.vault import access

# Grant specific permissions
access.grant_access("client_id", "apps", access.READ | access.CREATE)

# Check permissions
has_read = access.has_access("client_id", "apps", access.READ)
```

## Development Guidelines

### Adding New Services

1. Create service package under `campus/`
2. Follow the established patterns:
   - `__init__.py` - Main module with `create_app()` and `init_app()`
   - `model.py` - Data access layer
   - `routes.py` - HTTP API endpoints
   - `db.py` - Database utilities (if needed)
3. Add client interface in `campus.client.{service}`
4. Update main application integration

### Avoiding Circular Imports

1. Use `campus.client.*` for cross-service communication
2. Import dependencies at function level when needed
3. Keep clear dependency hierarchy: apps → client → models → storage
4. Services should be independently importable

### Testing

1. Each service should have comprehensive unit tests
2. Use mocking for cross-service dependencies
3. Integration tests should test the full stack
4. Client interfaces should be tested separately

## Contributing

1. Follow the established architectural patterns
2. Maintain service independence
3. Add comprehensive tests for new functionality
4. Update client interfaces when adding new service methods
5. Document configuration requirements and deployment steps

## License

[License information would go here]
