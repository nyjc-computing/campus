# Campus Architecture

## Overview

Campus is structured as a **modular monolith** with clear service boundaries that can be deployed together or separately. Each service follows the same architectural patterns while maintaining clean boundaries and avoiding circular dependencies.

## Package Structure

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

## Core Principles

- **🔄 Separation of Concerns**: Each service has a single, well-defined responsibility
- **🔌 Loose Coupling**: Services communicate through clean interfaces
- **� API-First**: Most actions have corresponding HTTP API endpoints
- **� Extensible Storage**: Backend-agnostic storage interfaces support multiple implementations

## Service Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   🌐 Apps       │    │   🔌 Client     │    │   🛠️ Common     │
│   Web APIs      │    │   Interfaces    │    │   Utilities     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   🏛️ Models     │    │   🔐 Vault      │    │   📧 Services   │
│   Business      │    │   Secrets       │    │   Email, etc.   │
│   Logic         │    │   Management    │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   💾 Storage    │
                    │   Data Layer    │
                    └─────────────────┘
```

## Package Responsibilities

### `campus.apps`
Web applications and API endpoints:
- Flask applications with route definitions
- Authentication and authorization middleware
- OAuth integrations
- API request/response handling

### `campus.client`
Client interfaces for accessing Campus services:
- HTTP client libraries
- Service discovery and configuration
- Authentication token management
- Clean Python APIs for external integration

### `campus.common`
Shared utilities and schemas:
- Common data structures and validation
- Utility functions used across services
- Configuration management helpers
- Error handling and logging utilities

### `campus.models`
Data models and business logic:
- Core business entities (User, Circle, etc.)
- Domain-specific logic and validation
- Model relationships and constraints
- Data transformation utilities

### `campus.services`
Supporting business services:
- Email service for notifications
- External integrations
- Background job processing
- Service-to-service communication

### `campus.storage`
Data persistence interfaces:
- Backend-agnostic storage abstractions
- Alignment with Campus API schema
- Database connection management
- Multi-backend support (PostgreSQL, MongoDB)

### `campus.vault`
Secure secrets management:
- Credential storage and retrieval
- Access control and permissions
- Encryption and key management
- Configuration secrets management

## Design Patterns

### Lazy Loading
Resources are acquired only when first needed, enabling CI/CD builds without production secrets.

### Interface Segregation
Each service exposes only the interfaces relevant to its clients.

### Dependency Inversion
Higher-level modules depend on abstractions, not concrete implementations.

## Deployment Models

### Monolithic Deployment
Single application instance with all services:
```bash
export DEPLOY=apps
poetry run python main.py
```

### Vault-Only Deployment
Lightweight secrets management service:
```bash
export DEPLOY=vault  
poetry run python main.py
```

### Client Library Usage
Independent client for external integration:
```python
from campus.client import Campus
client = Campus()
```

## Configuration

Campus uses environment variables for core configuration and the vault service for all other secrets:

### Environment Variables
```bash
ENV="development"           # deployment environment
CLIENT_ID="your-client-id"  # OAuth client credentials  
CLIENT_SECRET="your-secret"
VAULTDB_URI="postgresql://user:pass@localhost/vault"  # vault database
```

### Vault-Managed Secrets
All other configuration (storage connections, email settings, API keys) is managed through the vault service for enhanced security.

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

See [testing-strategies.md](testing-strategies.md) for detailed testing approaches.
