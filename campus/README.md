# Campus

A modular Python application framework for educational institution management, built with Flask and designed around clean architecture principles.

## Overview

Campus is a modular monolith - services can deploy together or separately.

## Architecture

```
campus/
├── auth/           # Authentication and OAuth
│   ├── oauth_proxy/
│   ├── resources/  # Business logic
│   └── routes/     # HTTP endpoints
├── api/            # RESTful API resources
│   ├── resources/  # Business logic
│   └── routes/     # HTTP endpoints
├── audit/          # Audit/tracing service + web UI
├── flask_campus/   # Flask integration glue
├── integrations/   # External service configurations
├── services/       # Email, etc.
├── storage/        # Data persistence
├── webauth/        # WebAuth request primitives (headers, OAuth tokens)
└── yapper/         # Event bus (self-contained)
```

Two layers live in their own distributions, consumed as version-pinned
release wheels:
[campus-common](https://github.com/nyjc-computing/campus-common) ships
the `campus.common` shared kernel, and
[campus-model](https://github.com/nyjc-computing/campus-model) ships
the `campus.model` entity dataclasses.

### Design Principles

1. Separation of Concerns
2. Dependency Inversion
3. Interface Segregation
4. Single Responsibility
5. Open/Closed
6. No Circular Imports

### Services

- **campus.auth**: Authentication, OAuth, credentials (`.resources` for business logic)
- **campus.api**: Circles, files, email OTP (`.resources` for business logic)
- **campus.storage**: Backend-agnostic data persistence
- **campus.model**: Entity dataclasses (no business logic) — [campus-model](https://github.com/nyjc-computing/campus-model) distribution
- **campus.services**: Email, notifications
- **campus.yapper**: Event bus — self-contained, imports no campus package ([docs/yapper.md](../docs/yapper.md))

## Key Components

### 🔐 Auth (`campus.auth`)

- PostgreSQL database (POSTGRESDB_URI)
- Client authentication (CLIENT_ID/CLIENT_SECRET)
- OAuth proxy (Google, GitHub, Discord)
- Session/token handling

### 🌐 API (`campus.api`)

- Circle (group) management
- Files: slug-addressable blobs in object storage (`/api/v1/files/by-slug/...`)
- Email OTP verification
- Resource-based routing

### 💾 Storage (`campus.storage`)

- Multiple backends (PostgreSQL, MongoDB)
- Table/collection abstraction
- Query builder interface

### 🏛️ Model (`campus.model`)

Entity dataclasses (shipped by the [campus-model](https://github.com/nyjc-computing/campus-model) distribution):
- User, Circle, Client, Session, Token
- EmailOTP, HTTP headers, credentials
- No business logic

Business logic in `.resources` submodules (e.g., `campus.auth.resources`).

### 📦 Services (`campus.services`)

- Email notifications
- External integrations

### 📨 Yapper (`campus.yapper`)

- Event bus for domain emissions (`campus.<subject>[.<sub>].<action>` labels)
- Self-contained: imports no campus package; configuration via arguments/environment
- Database URI resolution: argument → provider callable → `YAPPERDB_URI` env → remote vault
- See [docs/yapper.md](../docs/yapper.md)

### 🔌 Client Access

Use `campus_python` client library:
```python
import campus_python
campus = campus_python.Campus()
secret = campus.auth.vaults["deployment"]["key"]
```

See [campus-api-python](https://github.com/nyjc-computing/campus-api-python).

### 🧩 Common (`campus.common`)

Provided by the [campus-common](https://github.com/nyjc-computing/campus-common) distribution (release wheel; interface locked by CI):

- Configuration and feature flags (`env`)
- API/OAuth error taxonomy and Flask error handlers (`errors`)
- Schema definitions (`schema`)
- Time and UID utilities (`utils`)
- Record validation (`validation`)

## Usage Patterns

### Service Access

```python
import campus_python

campus = campus_python.Campus()

# Authenticate
campus.auth.root.authenticate(client_id="...", client_secret="...")

# Access secrets
secret = campus.auth.vaults["deployment"]["DATABASE_URL"]

# Type hints
import campus.model as model
def process(user: model.User): ...
```

### Configuration

```bash
export POSTGRESDB_URI="postgresql://..."
export CLIENT_ID="your_client_id"
export CLIENT_SECRET="your_client_secret"
export DEPLOY="campus.auth"  # or "campus.api"
export ENV="development"     # or "staging", "production"
```

### Development

```bash
# Auth service
export DEPLOY=campus.auth
poetry run python main.py

# API service
export DEPLOY=campus.api
poetry run python main.py

# Tests
poetry run python tests/run_tests.py unit
```

## Deployment

```bash
# Auth
export DEPLOY=campus.auth
gunicorn --bind "0.0.0.0:$PORT" wsgi:app

# API
export DEPLOY=campus.api
gunicorn --bind "0.0.0.0:$PORT" wsgi:app
```

See [DEPLOY.md](../DEPLOY.md).

## Authentication

See [docs/auth-login-flow.md](../docs/auth-login-flow.md) for the
end-to-end browser login flow (session init, Google federated login,
authorization code exchange).

```python
import campus_python

campus = campus_python.Campus()

# With credentials
campus.auth.root.authenticate(
    client_id="your_client_id",
    client_secret="your_client_secret"
)

# With token
campus.auth.root.authenticate(token="access_token")
```

## Development Guidelines

### Adding Services

1. Create package under `campus/`
2. Structure:
   - `resources/` - Business logic
   - `routes/` - HTTP endpoints
   - Entity models in `campus.model`
3. Update `main.py` deployment config
4. Add methods to `campus_python` client

### Avoiding Circular Imports

1. Use `campus_python` for cross-service calls
2. Hierarchy: auth/api → model → storage → common
3. Business logic in `.resources`, not `campus.model`

### Testing

1. Unit tests for each service
2. Mock cross-service dependencies
3. Test `.resources` separately from routes

## Contributing

1. Follow architectural patterns
2. Maintain service independence
3. Test new functionality
4. Business logic in `.resources`, not `campus.model`
5. Update `campus_python` client for new APIs
6. Document config and deployment
