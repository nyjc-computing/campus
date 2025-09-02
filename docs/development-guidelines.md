# Development Guidelines

This document outlines key architectural patterns and development practices for Campus. Follow these guidelines to maintain consistency and ensure proper integration between services.

## Core Abstractions

### Campus Vault (`campus.vault`)

**Purpose**: Centralized secrets management for all Campus services.

**Key Principles**:
- All configuration secrets must go through vault (never use `os.getenv()` directly)
- Vault service is independent - imports only from `campus.common`
- Other services depend on vault for database credentials and API keys

**Usage Pattern**:
```python
from campus.vault import get_vault

# Get secrets for your service
vault = get_vault("service_name")
database_url = vault.get("DATABASE_URL")
api_key = vault.get("EXTERNAL_API_KEY")
```

**Implementation Requirements**:
- Handle vault unavailability gracefully
- Never cache vault credentials in class variables

### Campus Storage (`campus.storage`)

**Purpose**: Unified data persistence layer with multiple backend support.

**Storage Interface Requirements**:
All storage implementations must provide:
- `id` field - unique identifier (string)
- `created_at` field - creation timestamp (ISO 8601 UTC)
- Standard CRUD operations
- Consistent error handling

**Usage Pattern**:
```python
from campus.storage import get_collection, get_table

# Document storage (MongoDB-style)
users = get_collection("users", User)
user = users.create({"name": "John", "email": "john@example.com"})

# Table storage (SQL-style)  
sessions = get_table("sessions", Session)
session = sessions.find_by_id("session_123")
```

**Backend Abstraction**:
```python
# Define interface first
class StorageInterface(ABC):
    @abstractmethod
    def create(self, data: dict) -> dict:
        pass
    
    @abstractmethod
    def find_by_id(self, doc_id: str) -> dict:
        pass

# Implement for specific backends
class MongoDBStorage(StorageInterface):
    def create(self, data: dict) -> dict:
        data['id'] = generate_id()
        data['created_at'] = utc_time()
        return self.collection.insert_one(data)
```

### Storage-Model-Views Pattern

**Architecture**: Separate data persistence, business logic, and presentation layers.

```
Views (apps/) → Models (models/) → Storage (storage/)
```

**Implementation**:
```python
# Storage layer - data persistence
class UserStorage:
    def create_user(self, data: dict) -> dict:
        return self.collection.insert_one(data)

# Model layer - business logic
class User:
    def __init__(self, storage: UserStorage):
        self.storage = storage
    
    def create_with_validation(self, data: dict) -> dict:
        self.validate_email(data['email'])
        return self.storage.create_user(data)

# View layer - HTTP endpoints
@app.route('/users', methods=['POST'])
def create_user():
    user_model = User(get_user_storage())
    return user_model.create_with_validation(request.json)
```

### Campus Common (`campus.common`)

**Purpose**: Standardized utilities and patterns used across all services.

**Key Modules**:
- `campus.common.utils` - ID generation, time handling, validation
- `campus.common.devops` - Environment detection, configuration
- `campus.common.errors` - Standardized error types
- `campus.common.http` - HTTP utilities and middleware

**Usage Pattern**:
```python
import campus.common.utils
import campus.common.devops

# Use through module namespaces
user_id = campus.common.utils.uid()
timestamp = campus.common.utils.utc_time()
env = campus.common.devops.get_environment()
```

**Benefits**:
- Consistent behavior across services
- Centralized utilities reduce code duplication
- Module namespacing prevents naming conflicts

## Development Patterns

### Interface-First Design

**Pattern**: Define abstract interfaces for polymorphic concrete classes.

```python
from abc import ABC, abstractmethod

class EmailSender(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> bool:
        pass

class SMTPSender(EmailSender):
    def send(self, to: str, subject: str, body: str) -> bool:
        # SMTP implementation
        pass
```

**Benefits**:
- Enables swappable implementations
- Easier testing with mock implementations
- Clear contracts between components

### Function Calling Conventions

**Prefer calling functions through modules**:
```python
# Good - clear module context
import campus.common.devops
import campus.vault

app = campus.common.devops.deploy.create_app()
vault = campus.vault.get_vault("service_name")
```

**Avoid importing individual functions**:
```python
# Avoid - loses module context and creates naming conflicts
from campus.common.devops.deploy import create_app
from campus.vault import get_vault

create_app()  # Unclear which create_app this is
```

**Rationale**: Some modules have similarly named functions for polymorphism. Module namespacing maintains clarity and prevents conflicts.

## Common Pitfalls

### Environment Issues
- **Always use Poetry**: Run `poetry run python` instead of bare `python`
- **Check environment**: Use `poetry env info` to verify active environment
- **Install dependencies**: Run `poetry install` after pulling changes

### Import Problems
- **Circular imports**: Structure dependencies to prevent cycles
- **Package imports**: Import packages, not individual functions (see [Style Guide](STYLE-GUIDE.md))
- **Standard library shadowing**: Avoid directory names like `collections/`, `json/`

### Configuration Errors
- **Never use `os.getenv()`**: All configuration must go through `campus.vault`
- **Environment variables**: Use only for deployment settings (ENV, CLIENT_ID, etc.)
- **Secrets management**: Store all API keys, database URLs in vault

### Testing Issues
- **Use appropriate strategy**: See [Testing Strategies](testing-strategies.md)
- **Mock external dependencies**: Don't hit real databases/APIs in unit tests
- **Import testing**: Test that classes can be imported without external resources

### Storage Interface Violations
- **Missing required fields**: All storage objects need `id` and `created_at`
- **Inconsistent error handling**: Use standardized error types from `campus.common.errors`
- **Direct database access**: Use storage interfaces instead of direct DB connections

## Development Workflow

### Adding New Features

1. **Design interfaces first** - Define abstract classes for new functionality
2. **Follow storage pattern** - Implement storage-model-views separation
3. **Test thoroughly** - Use appropriate testing strategy for your changes
4. **Update documentation** - Include usage examples and interface contracts

### Modifying Existing Code

1. **Understand dependencies** - Check which services depend on your changes
2. **Maintain interfaces** - Don't break existing abstract contracts
3. **Test backwards compatibility** - Ensure existing code still works
4. **Update all implementations** - If changing interfaces, update all backends

### Integration Guidelines

1. **Import at package level** - `import campus.vault` not `from campus.vault import get_vault`
2. **Use module functions** - `campus.common.utils.uid()` not `from campus.common.utils import uid`
3. **Handle errors consistently** - Use `campus.common.errors` for standardized exceptions

For detailed coding standards, see [Style Guide](STYLE-GUIDE.md).

For testing approaches, see [Testing Strategies](testing-strategies.md).

**Pattern**: Database connections should be managed lazily with proper cleanup.

**Requirements**:
- Connection established only when needed
- Provide `close()` method for cleanup
- Handle connection failures gracefully
- Support connection pooling where appropriate

### Primary Key Mapping

**Pattern**: Abstract database-specific primary key handling.

**Example**: MongoDB uses `_id`, Campus uses `id` - handle mapping transparently in the backend.

## Package Architecture

### Namespace Package Structure

**Pattern**: Use namespace packages for modular distribution.

**Structure**:
```
campus/
├── __init__.py              # Namespace package
├── common/                  # Shared utilities
├── vault/                   # Secret management
├── storage/                 # Storage interfaces
├── client/                  # Client libraries
└── apps/                    # Web applications
```

### Dependency Ordering

**Critical**: Packages must be buildable in dependency order:

1. **Independent**: `common` (no dependencies)
2. **Dependent**: `vault`, `client`, `models` (depend on `common`)
3. **Storage**: `storage` (depends on `vault` + `common`)
4. **Final**: `apps`, `workspace` (depend on multiple others)

### Development Setup

**Pattern**: Use Poetry's editable install for local development.

**Command**:
```bash
# In the campus root directory
poetry install --all-extras
```

## Testing and CI/CD

### Testing Strategies

Campus provides **three distinct testing strategies** for different use cases:

1. **Development Server Testing** - Test against live Railway services with simulated data
2. **Local Service Testing** - Run services locally in background for integration testing  
3. **Flask Test Client Testing** - In-process testing with no network calls (fastest)

**📖 See [Testing Strategies](testing-strategies.md) for comprehensive documentation and examples.**

### Test Organization and Structure

**Test Separation**: Tests are organized by package and type for maintainability and reliability.

**Directory Structure**:
```
tests/
  unit/                 # Unit tests (no external dependencies)
    apps/
      test_client.py    # Client interface tests
      test_models.py    # Model logic tests  
      test_routes.py    # Route logic tests
    vault/
      test_client.py    # Client interface tests
      test_models.py    # Model logic tests
      test_routes.py    # Route logic tests
    yapper/
      test_models.py    # Model logic tests
  integration/          # Integration tests (require environment setup)
    apps/
      test_models_users.py
      test_models_circles.py
    vault/
      test_vault_integration.py
    yapper/
      test_yapper.py
```

**Test Commands**:
```bash
# Run only unit tests (reliable, no external deps)
poetry run python -m unittest discover tests/unit

# Run only integration tests (may need environment setup)
poetry run python -m unittest discover tests/integration

# Run specific package unit tests
poetry run python -m unittest discover tests/unit/apps
poetry run python -m unittest discover tests/unit/vault

# Run all tests
poetry run python -m unittest discover tests
```

**Testing Principles**:
- **Unit tests**: Test internal logic only, mock external dependencies
- **Integration tests**: Test full package functionality with real dependencies
- **No package class mocking**: Test real implementations, may mock `campus.common`
- **Environment independence**: Unit tests must not rely on environment variables

### Build Environment Isolation

**Requirement**: All packages must build successfully without external dependencies.

**Implementation**:
- Use lazy loading for external resources
- Mock environment variables only when absolutely necessary
- Prefer dependency ordering over environment setup

### Poetry Configuration

**Required settings** for CI/CD:
```bash
poetry config virtualenvs.use-poetry-python false
poetry config virtualenvs.create true
poetry config virtualenvs.in-project false
```

**Rationale**: Ensures Poetry uses the Python version from actions/setup-python instead of Poetry's bundled Python.

### Import Shadowing Prevention

**Critical**: Avoid directory names that shadow Python standard library modules.

**Examples to Avoid**:
- `collections/` (shadows `collections` module)
- `json/` (shadows `json` module)
- `os/` (shadows `os` module)

**Solution**: Use descriptive names like `document_collections/`, `json_utils/`, etc.

## Code Organization

### Module Structure

**Pattern**: Consistent module organization across packages.

```
package/
├── __init__.py              # Public API
├── interface.py             # Abstract interfaces
├── backend/                 # Implementation backends
│   ├── __init__.py
│   └── implementation.py
├── errors.py                # Package-specific exceptions
└── utils.py                 # Utility functions
```

### Dependency Management

**Pattern**: Include campus-suite as a git dependency.

```toml
# Production use
[tool.poetry.dependencies]
campus-suite = {git = "https://github.com/nyjc-computing/campus.git", branch = "main"}

# Development use (staging branch)
[tool.poetry.group.dev.dependencies]
campus-suite = {git = "https://github.com/nyjc-computing/campus.git", branch = "staging"}

# Pin to specific commit for reproducibility
[tool.poetry.dependencies]
campus-suite = {git = "https://github.com/nyjc-computing/campus.git", rev = "abc123def"}

# Install with specific features
[tool.poetry.dependencies]
campus-suite = {git = "https://github.com/nyjc-computing/campus.git", branch = "main", extras = ["vault"]}  # vault only
campus-suite = {git = "https://github.com/nyjc-computing/campus.git", branch = "main", extras = ["apps"]}   # apps only
campus-suite = {git = "https://github.com/nyjc-computing/campus.git", branch = "main", extras = ["full"]}   # all features
```

### Import Organization

**Pattern**: Organize imports by source.

```python
# Standard library
import os
from typing import Dict, List

# Third-party
import requests
from flask import Flask

# Campus packages
from campus.common import utils
from campus.vault import get_vault

# Local package
from .interface import Interface
from .errors import CustomError
```

### Error Handling

**Pattern**: Use package-specific exception hierarchies.

```python
class StorageError(Exception):
    """Base exception for storage operations."""
    pass

class NotFoundError(StorageError):
    """Raised when a requested item is not found."""
    pass

class ConnectionError(StorageError):
    """Raised when database connection fails."""
    pass
```

## Documentation Standards

### Docstring Requirements

**Pattern**: Use consistent docstring format.

```python
def function_name(param: str) -> dict:
    """Brief description of the function.
    
    Longer description if needed. Explain the purpose,
    behavior, and any important details.
    
    Args:
        param: Description of the parameter
        
    Returns:
        Description of the return value
        
    Raises:
        SpecificError: When this specific condition occurs
        
    Example:
        >>> result = function_name("test")
        >>> print(result)
        {"key": "value"}
    """
```

### Code Comments

**Guidelines**:
- Explain **why**, not **what**
- Document non-obvious design decisions
- Include rationale for architectural choices
- Reference related issues or documentation

---

## Contributing

When contributing to Campus:

1. **Follow the established patterns** documented above
2. **Add new patterns** to this document when you establish them
3. **Test your changes** in isolation to ensure they follow lazy loading principles
4. **Document your design decisions** in code comments

This document is living and should be updated as the project evolves.
