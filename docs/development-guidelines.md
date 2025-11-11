# Development Guidelines

This document outlines key architectural patterns and development practices for Campus. Follow these guidelines to maintain consistency and ensure proper integration between services.

## Core Abstractions

### Campus Authentication (`campus.auth`)

**Purpose**: Authentication, OAuth, and credential management.

**Key Principles**:
- User authentication and session management
- OAuth proxy (Google, GitHub, Discord)
- Client authentication via CLIENT_ID/CLIENT_SECRET
- Business logic in `.resources` submodule

**Usage Pattern**:
```python
import campus_python

campus = campus_python.Campus()

# Authenticate
auth_result = campus.auth.root.authenticate(
    client_id="your_client_id",
    client_secret="your_client_secret"
)

# Access secrets
secret = campus.auth.vaults["deployment"]["DATABASE_URL"]
```

**Implementation**:
```python
# Within campus.auth
from campus.auth import resources
from campus import model

# Cross-service (e.g., in campus.api)
from campus.auth import resources as auth_resources
```

### Campus Storage (`campus.storage`)

**Purpose**: Unified data persistence layer with multiple backend support.

**Storage Interface Requirements**:
All storage implementations must provide:
- `id` field - unique identifier (string)
- `created_at` field - creation timestamp (RFC3339 UTC)
- Standard CRUD operations
- Consistent error handling

**Usage Pattern**:
```python
import campus.storage

# Document storage (MongoDB-style)
users = campus.storage.get_collection("users")
user = users.create({"name": "John", "email": "john@example.com"})

# Table storage (SQL-style)  
sessions = campus.storage.get_table("sessions")
session = sessions.find_by_id("session_123")
```

**Backend Abstraction**:
```python
from abc import ABC, abstractmethod

class StorageInterface(ABC):
    @abstractmethod
    def create(self, data: dict) -> dict:
        pass
    
    @abstractmethod
    def find_by_id(self, doc_id: str) -> dict:
        pass

class MongoDBStorage(StorageInterface):
    def create(self, data: dict) -> dict:
        # Implementation
        pass
```

### Storage-Model-Resources Pattern

**Architecture**: Separate data persistence, entity representation, and business logic.

```
Routes → Resources (.resources/) → Storage → Model
```

**Implementation**:
```python
# Model layer - entity representation (campus.model)
from dataclasses import dataclass

@dataclass
class User:
    id: str
    name: str
    email: str
    created_at: str

# Resources layer - business logic (campus.auth.resources)
from campus.auth import resources
import campus.storage

def create_user(data: dict) -> dict:
    # Validation logic
    users = campus.storage.get_collection("users")
    return users.create(data)

# Routes layer - HTTP endpoints
from campus.auth import resources

@app.route('/users', methods=['POST'])
def create_user():
    return resources.create_user(request.json)
```

### Campus Common (`campus.common`)

**Purpose**: Shared utilities used across services.

**Key Modules**:
- `utils` - ID generation, time handling
- `devops` - Environment detection
- `errors` - Standardized error types
- `http` - HTTP utilities

**Usage Pattern**:
```python
from campus.common import utils, devops, errors

user_id = utils.uid()
timestamp = utils.utc_time()
env = devops.ENV
```

### Entity Models (`campus.model`)

**Purpose**: Entity representation only - no business logic.

**Key Principles**:
- Dataclass definitions (User, Circle, Client, Session, Token, etc.)
- Keyword-only init
- No business logic

**Usage Pattern**:
```python
from campus import model

def process_user(user: model.User) -> dict:
    return {"id": user.id, "name": user.name}
```

Business logic belongs in `.resources` submodules, not `campus.model`.

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

**Prefer module-level imports**:
```python
# Within same service
from campus.auth import resources

# Cross-service (e.g., from campus.api)
from campus.auth import resources as auth_resources
from campus.api import resources

# Common utilities
from campus.common import utils, devops
```

**Avoid importing individual functions**:
```python
# Avoid - loses context
from campus.common.utils import uid, utc_time
from campus.auth.resources import create_user

uid()  # Unclear origin
```

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
- **Use campus_python client**: Access config via `campus.auth.vaults`
- **Environment variables**: Only for deployment (ENV, DEPLOY, CLIENT_ID, CLIENT_SECRET, POSTGRESDB_URI)
- **Secrets management**: Access via `campus_python.Campus().auth.vaults[deployment][key]`

### Architecture Violations
- **Business logic in models**: Keep `campus.model` as pure data structures; put logic in `.resources`
- **Missing .resources**: Each service (auth, api) should have its business logic in `.resources` submodule

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

### Testing and CI/CD

Campus provides three testing strategies:

1. **Development Server Testing** - Live Railway services
2. **Local Service Testing** - Local background services (currently broken)
3. **Flask Test Client Testing** - In-process, no network (fastest)

See [Testing Strategies](testing-strategies.md) for details.

### Import Shadowing Prevention

**Critical**: Avoid directory names that shadow Python standard library modules.

**Examples to Avoid**:
- `collections/` (shadows `collections` module)
- `json/` (shadows `json` module)
- `os/` (shadows `os` module)

**Solution**: Use descriptive names like `document_collections/`, `json_utils/`, etc.

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
