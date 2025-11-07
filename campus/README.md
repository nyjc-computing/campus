# Campus

A modular Python application framework for educational institution management, built with Flask and designed around clean architecture principles.

## Overview

Campus is organized as a collection of independent, loosely-coupled services that can be deployed together or separately. Each service follows the same architectural patterns while maintaining clear boundaries and avoiding circular dependencies.

## Architecture

### Package Structure

```
campus/
├── auth/           # Authentication and OAuth services
│   ├── resources/  # Business logic for auth operations
│   └── routes/     # HTTP endpoints
├── api/            # RESTful API resources
│   ├── resources/  # Business logic for API operations
│   └── routes/     # HTTP endpoints
├── common/         # Shared utilities and schemas
├── model/          # Entity representation (dataclasses)
├── services/       # Business services (email, etc.)
├── storage/        # Data persistence layer
├── integrations/   # External service integrations
└── yapper/         # Logging framework
```

### Design Principles

1. **Separation of Concerns**: Each package has a single, well-defined responsibility
2. **Dependency Inversion**: Higher-level modules don't depend on lower-level modules
3. **Interface Segregation**: Clients depend only on interfaces they actually use
4. **Single Responsibility**: Each module has one reason to change
5. **Open/Closed**: Open for extension, closed for modification
6. **Circular Import Avoidance**: Clear dependency hierarchy prevents import cycles

### Service Independence

Each major service (`auth`, `api`, `storage`) is designed to be independently deployable:

- **campus.auth**: Authentication and OAuth services with credential management (business logic in `.resources`)
- **campus.api**: RESTful API resources for Campus entities (business logic in `.resources`)
- **campus.storage**: Data persistence layer with flexible backend support
- **campus.model**: Entity representation using dataclasses (no business logic)
- **campus.services**: Supporting services (email, notifications, etc.)

## Key Components

### 🔐 Auth (`campus.auth`)

Authentication and OAuth service with:
- Independent PostgreSQL database (VAULTDB_URI)
- Client authentication with CLIENT_ID/CLIENT_SECRET
- OAuth proxy for external providers (Google, GitHub, Discord)
- Session management and token handling
- RESTful API with multiple endpoints for auth operations

### 🌐 API (`campus.api`)

RESTful API resources with:
- Circle (group) management endpoints
- Email OTP verification
- Resource-based routing
- Authentication via campus_python client

### 💾 Storage (`campus.storage`)

Abstract data persistence layer supporting:
- Multiple backends (PostgreSQL, MongoDB, etc.)
- Table/collection abstraction
- Query builder interface
- Connection pooling and transaction management

### 🏛️ Model (`campus.model`)

Entity representation using dataclasses:
- User, Circle, Client entities
- Session and Token structures
- EmailOTP, Vault structures
- HTTP headers and credentials
- Pure data structures with no business logic

Business logic is implemented in `.resources` submodules within each service (e.g., `campus.auth.resources`, `campus.api.resources`).

### 📦 Services (`campus.services`)

Supporting business services:
- Email service for notifications
- External integrations
- Cross-cutting concerns

### 🔌 Client Access

Campus services are accessed through the external `campus_python` client library:
- RESTful API conventions
- Automatic authentication and error handling
- Service clients for auth, users, circles, etc.
- See [campus-api-python repository](https://github.com/nyjc-computing/campus-api-python)

### 🛠️ Common (`campus.common`)

Shared utilities and schemas:
- Configuration management and feature flags
- Validation utilities (Flask integration, naming, records)
- Schema definitions and data structures
- Time utilities and UID generation
- Secret management utilities

## Usage Patterns

### Service Access

Services are accessed through the `campus_python` client library:

```python
# Use campus_python client library
import campus_python

campus = campus_python.Campus()

# Access authentication services
auth_result = campus.auth.root.authenticate(client_id="...", client_secret="...")

# Access vault services
secret = campus.auth.vaults["apps"]["DATABASE_URL"]

# Entity models are imported directly when needed for type hints
from campus.model import User, Circle
```

### Configuration

Services use environment variables for configuration:

```bash
# Authentication service database
export VAULTDB_URI="postgresql://..."
export CLIENT_ID="your_client_id"
export CLIENT_SECRET="your_client_secret"

# Deployment mode
export DEPLOY="campus.auth"  # or "campus.api"

# Environment
export ENV="development"  # or "staging", "production"
```

### Development

Each service can be developed and tested independently:

```bash
# Run auth service standalone
export DEPLOY=campus.auth
poetry run python main.py

# Run API service standalone  
export DEPLOY=campus.api
poetry run python main.py

# Run tests
poetry run python tests/run_tests.py unit
```

## Deployment

### Standalone Services

Each service can be deployed independently using the deployment mode:

```bash
# Deploy auth service
export DEPLOY=campus.auth
gunicorn --bind "0.0.0.0:$PORT" wsgi:app

# Deploy API service
export DEPLOY=campus.api
gunicorn --bind "0.0.0.0:$PORT" wsgi:app
```

See [DEPLOY.md](../DEPLOY.md) for detailed deployment instructions.

## Authentication & Security

### Client Authentication

Services use CLIENT_ID/CLIENT_SECRET for authentication:

```python
# Use campus_python client library
import campus_python

campus = campus_python.Campus()

# Authenticate with credentials
auth_result = campus.auth.root.authenticate(
    client_id="your_client_id",
    client_secret="your_client_secret"
)

# Or authenticate with token
auth_result = campus.auth.root.authenticate(token="access_token")
```

## Development Guidelines

### Adding New Services

1. Create service package under `campus/`
2. Follow the established patterns:
   - `__init__.py` - Main module with `init_app()`
   - `resources/` - Business logic and data access
   - `routes/` - HTTP API endpoints
   - Entity models in `campus.model` (if needed)
3. Update deployment configuration in `main.py`
4. Add client methods to `campus_python` library (separate repo)

### Avoiding Circular Imports

1. Use `campus_python` client for cross-service communication
2. Import dependencies at function level when needed
3. Keep clear dependency hierarchy: auth/api → model → storage → common
4. Services should be independently importable
5. Business logic stays in `.resources`, not in `campus.model`

### Testing

1. Each service should have comprehensive unit tests
2. Use mocking for cross-service dependencies
3. Integration tests should test the full stack
4. Test business logic in `.resources` modules separately from routes

## Contributing

1. Follow the established architectural patterns
2. Maintain service independence
3. Add comprehensive tests for new functionality
4. Keep business logic in `.resources` modules, not in entity models
5. Update `campus_python` client library when adding new API endpoints
6. Document configuration requirements and deployment steps

## License

[License information would go here]
