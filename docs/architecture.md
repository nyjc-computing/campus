# Campus Architecture

## Overview

Campus is structured as a **modular monolith** with clear service boundaries that can be deployed together or separately. Each service follows the same architectural patterns while maintaining clean boundaries and avoiding circular dependencies.

## Package Structure

```
campus/
├── auth/           # Authentication and OAuth services
│   ├── oauth_proxy/# OAuth provider integrations
│   ├── resources/  # Business logic
│   └── routes/     # HTTP endpoints
├── api/            # RESTful API resources  
│   ├── resources/  # Business logic
│   └── routes/     # HTTP endpoints
├── common/         # Shared utilities and schemas
├── model/          # Entity representation (dataclasses)
├── services/       # Business services (email, etc.)
├── storage/        # Data persistence layer
├── integrations/   # External service integrations
└── yapper/         # Logging framework
```

## Core Principles

- **Separation of Concerns**: Each service has a single, well-defined responsibility
- **Loose Coupling**: Services communicate through clean interfaces
- **API-First**: Most actions have corresponding HTTP API endpoints
- **Extensible Storage**: Backend-agnostic storage interfaces support multiple implementations

## Service Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Auth          │    │   API           │    │   Common        │
│   OAuth &       │    │   RESTful       │    │   Utilities     │
│   Credentials   │    │   Resources     │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Model         │    │   Services      │    │   Integrations  │
│   Entities      │    │   Email, etc.   │    │   External      │
│   (dataclasses) │    │                 │    │   APIs          │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   Storage       │
                    │   Data Layer    │
                    └─────────────────┘
```

**Client Access:** Services accessed via external `campus_python` client library.

## Package Responsibilities

### `campus.auth`
Authentication and OAuth services:
- User authentication and session management
- OAuth proxy for external providers (Google, GitHub, Discord)
- Client credential management
- Token generation and validation
- Business logic in `.resources` submodule

### `campus.api`
RESTful API resources:
- Circle (group) management
- Email OTP verification
- Resource handlers and routing
- Business logic in `.resources` submodule

### `campus.model`
Entity representation (no business logic):
- Dataclass definitions (User, Circle, Client, Session, Token, etc.)
- HTTP headers and credentials
- Pure data structures with keyword-only init

### `campus.storage`
Data persistence interfaces:
- Backend-agnostic storage abstractions
- Multi-backend support (PostgreSQL, MongoDB)
- Consistent CRUD operations

## Design Patterns

### Lazy Loading
Resources are acquired only when first needed, enabling CI/CD builds without production secrets.

### Interface Segregation
Each service exposes only the interfaces relevant to its clients.

### Dependency Inversion
Higher-level modules depend on abstractions, not concrete implementations.

## Deployment Models

### Service Deployment
Individual services can be deployed independently:
```bash
export DEPLOY=campus.auth
poetry run python main.py
```

or

```bash
export DEPLOY=campus.api
poetry run python main.py
```

### Client Library Usage
External projects use the `campus_python` client library:
```python
import campus_python
campus = campus_python.Campus()
```

See the [campus-api-python repository](https://github.com/nyjc-computing/campus-api-python) for client documentation.

## Configuration

Campus uses environment variables for core configuration:

### Environment Variables
```bash
ENV="development"                # deployment environment
DEPLOY="campus.auth"             # deployment mode (campus.auth, campus.api, etc.)
CLIENT_ID="your-client-id"       # client authentication
CLIENT_SECRET="your-secret"      # client authentication
POSTGRESDB_URI="postgresql://..."# auth service database
```

### Secrets Management
Secrets managed via `campus.auth.vaults` and accessed through `campus_python` client:

```python
import campus_python
campus = campus_python.Campus()
secret = campus.auth.vaults["deployment"]["key"]
```

## Security Architecture

- **Authentication**: OAuth2 with Google integration
- **Authorization**: Role-based access control (RBAC)
- **Secrets Management**: Centralized vault with encrypted storage
- **Data Protection**: Field-level encryption for sensitive data
- **Network Security**: HTTPS-only communication between services

## Testing Architecture

Three-tier testing strategy:
1. **Unit Tests**: Individual component testing with mocks
2. **Integration Tests**: Service-to-service communication testing
3. **End-to-End Tests**: Full application workflow testing

See [TESTING-GUIDE.md](TESTING-GUIDE.md) for detailed testing approaches.
