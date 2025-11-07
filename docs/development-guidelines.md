# Development Guidelines

This document outlines key architectural patterns and development practices for Campus. Follow these guidelines to maintain consistency and ensure proper integration between services.

## Core Abstractions

### Campus Authentication (`campus.auth`)

**Purpose**: Authentication, OAuth, and credential management for all Campus services.

**Key Principles**:
- Handles user authentication and session management
- OAuth proxy for external providers (Google, GitHub, Discord)
- Client authentication via CLIENT_ID/CLIENT_SECRET
- Business logic resides in `.resources` submodule

**Usage Pattern**:
```python
import campus_python

campus = campus_python.Campus()

# Authenticate client
auth_result = campus.auth.root.authenticate(
    client_id="your_client_id",
    client_secret="your_client_secret"
)

# Access vault secrets
secret = campus.auth.vaults["service"]["DATABASE_URL"]
```

**Implementation Requirements**:
- Handle authentication failures gracefully
- Never cache credentials in class variables

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

### Storage-Model-Resources Pattern

**Architecture**: Separate data persistence, entity representation, and business logic layers.

```
Routes (auth/, api/) → Resources (.resources/) → Storage (storage/) → Model (model/)
```

**Implementation**:
```python
# Model layer - entity representation only (campus.model)
from dataclasses import dataclass

@dataclass
class User:
    id: str
    name: str
    email: str
    created_at: str

# Storage layer - data persistence
class UserStorage:
    def create_user(self, data: dict) -> dict:
        return self.collection.insert_one(data)

# Resources layer - business logic (in .resources submodule)
class UserResource:
    def __init__(self, storage: UserStorage):
        self.storage = storage
    
    def create_with_validation(self, data: dict) -> dict:
        self.validate_email(data['email'])
        return self.storage.create_user(data)

# Routes layer - HTTP endpoints
@app.route('/users', methods=['POST'])
def create_user():
    user_resource = UserResource(get_user_storage())
    return user_resource.create_with_validation(request.json)
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
env = campus.common.devops.ENV
```

**Benefits**:
- Consistent behavior across services
- Centralized utilities reduce code duplication
- Module namespacing prevents naming conflicts

### Entity Models (`campus.model`)

**Purpose**: Entity representation only - no business logic.

**Key Principles**:
- Dataclass definitions for entities (User, Circle, Client, etc.)
- Keyword-only init parameters
- No business logic or data processing
- Minimal dependencies

**Usage Pattern**:
```python
from campus.model import User, Circle

# Use for type hints and data structures
def process_user(user: User) -> dict:
    return {"id": user.id, "name": user.name}
```

**Important**: Business logic belongs in `.resources` submodules, not in `campus.model`.

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
- **Use campus_python client**: Access config through `campus.auth.vaults` via the client library
- **Environment variables**: Use only for deployment settings (ENV, DEPLOY, CLIENT_ID, etc.)
- **Secrets management**: All secrets should be accessed via `campus_python.Campus().auth.vaults`

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

## Testing and CI/CD

### Testing Strategies

Campus provides **three distinct testing strategies** for different use cases:

1. **Development Server Testing** - Test against live Railway services with simulated data
2. **Local Service Testing** - Run services locally in background for integration testing  
3. **Flask Test Client Testing** - In-process testing with no network calls (fastest)

**📖 See [Testing Strategies](testing-strategies.md) for comprehensive documentation and examples.**

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
