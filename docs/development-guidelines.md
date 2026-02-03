# Development Guidelines

This document outlines key architectural patterns and development practices for Campus.

**Looking for the contribution workflow?** See [CONTRIBUTING.md](CONTRIBUTING.md).

**For coding standards and import conventions**, see [STYLE-GUIDE.md](STYLE-GUIDE.md).

## The Storage-Model-Resources Pattern

This is the foundational architectural pattern in Campus. Understanding this pattern is essential before working with any part of the codebase.

```
Routes → Resources → Storage → Model
```

### Model Layer (`campus.model`)

**Purpose:** Entity representation only - pure data structures with no business logic.

Models are dataclasses that define the shape of your data:

```python
from dataclasses import dataclass

@dataclass
class User:
    id: str
    name: str
    email: str
    created_at: str
```

**Key principles:**
- Keyword-only init
- No methods beyond data conversion helpers (`to_storage()`, `to_resource()`)
- No business logic
- No dependencies on other campus packages (except `campus.common` for types)

### Storage Layer (`campus.storage`)

**Purpose:** Backend-agnostic data persistence with multiple backend support.

Storage provides CRUD operations independent of the underlying database:

```python
import campus.storage

# Document storage (MongoDB-style)
users = campus.storage.get_collection("users")
user = users.create({"name": "John", "email": "john@example.com"})

# Table storage (SQL-style)
sessions = campus.storage.get_table("sessions")
session = sessions.find_by_id("session_123")
```

**Storage interface requirements:**
- `id` field - unique identifier (string)
- `created_at` field - creation timestamp (RFC3339 UTC)
- Standard CRUD operations
- Consistent error handling

### Resources Layer (`.resources/`)

**Purpose:** Business logic - the "brains" of your application.

Resources are classes that encapsulate business operations. They bridge the gap between HTTP requests and data storage.

**Resource types:**

1. **Collection Resources** - Operate on multiple items
```python
class CirclesResource:
    """Represents the circles resource in Campus API Schema."""

    def list(self, **filters) -> list[Circle]:
        """List all circles matching filters."""
        records = circle_storage.get_matching(filters)
        return [_from_record(r) for r in records]

    def new(self, **fields) -> Circle:
        """Create a new circle with validation."""
        # Validation logic here
        # Storage operations here
        return circle
```

2. **Item Resources** - Operate on single items
```python
class CircleResource:
    """Represents a single circle in Campus API Schema."""

    def __init__(self, circle_id: CampusID):
        self.circle_id = circle_id

    def get(self) -> Circle:
        """Get the circle record."""
        record = circle_storage.get_by_id(self.circle_id)
        return _from_record(record)

    def update(self, **updates) -> None:
        """Update the circle record."""
        circle_storage.update_by_id(self.circle_id, updates)

    def delete(self) -> None:
        """Delete the circle record."""
        circle_storage.delete_by_id(self.circle_id)
```

3. **Sub-Resources** - Nested resources under a parent
```python
class CircleMembersResource:
    """Represents the circle members resource."""

    def __init__(self, parent: CirclesResource):
        self._parent = parent

    def list(self, circle_id: CampusID) -> dict:
        """List all members of a circle."""
        # Implementation

    def add(self, circle_id: CampusID, member_id: CampusID, access_value: int) -> None:
        """Add a member to a circle."""
        # Implementation
```

**Resources are exported from `__init__.py`:**
```python
# campus/api/resources/__init__.py
from .circle import CirclesResource
circle = CirclesResource()  # Module-level instance
```

### Routes Layer (`.routes/`)

**Purpose:** HTTP endpoints - thin wrappers that call Resource methods.

Routes use Flask blueprints and delegate to resource instances:

```python
from campus.api import resources

bp = flask.Blueprint('circles', __name__, url_prefix='/circles')

@bp.get('/')
def list_circles(tag: str | None = None):
    """List all circles matching filter requirements."""
    result = resources.circle.list(**{"tag": tag} if tag else {})
    return {"data": [c.to_resource() for c in result]}, 200

@bp.post('/')
def new_circle(name: str, description: str, tag: str, parents: dict | None = None):
    """Create a new circle."""
    circle = resources.circle.new(name=name, description=description, tag=tag, parents=parents)
    return {"data": circle.to_resource()}, 201
```

**Key principles for routes:**
- Minimal logic - just parameter extraction and response formatting
- Delegate all business logic to Resources
- Use `flask_campus.unpack_request` decorator for request parsing

## Package Structure

```
campus/
├── auth/       # Authentication and OAuth services
│   ├── oauth_proxy/
│   ├── resources/      # Business logic
│   └── routes/         # HTTP endpoints
├── api/        # RESTful API resources
│   ├── resources/      # Business logic
│   └── routes/         # HTTP endpoints
├── common/     # Shared utilities
├── model/      # Entity representation (dataclasses)
├── services/   # Business services (email, etc.)
├── storage/    # Data persistence layer
├── integrations/  # External service integrations
└── yapper/     # Logging framework
```

**Key rule:** Business logic lives in `.resources/` submodules. Models (`campus.model`) are pure data structures.

## Core Abstractions

### Campus Storage (`campus.storage`)

Backend-agnostic data persistence with multiple backend support.

**Usage:**
```python
import campus.storage

# Document storage (MongoDB-style)
users = campus.storage.get_collection("users")
user = users.create({"name": "John", "email": "john@example.com"})

# Table storage (SQL-style)
sessions = campus.storage.get_table("sessions")
session = sessions.find_by_id("session_123")
```

### Campus Authentication (`campus.auth`)

**Purpose:** Authentication, OAuth, and credential management.

**Via campus_python client:**
```python
import campus_python

campus = campus_python.Campus()

# Authenticate
auth_result = campus.auth.root.authenticate(
    client_id="your_client_id",
    client_secret="your-client_secret"
)

# Access secrets
secret = campus.auth.vaults["deployment"]["DATABASE_URL"]
```

**Within codebase:**
```python
# Within same service
from campus.auth import resources

# Cross-service (e.g., from campus.api)
from campus.auth import resources as auth_resources
```

### Campus Common (`campus.common`)

Shared utilities used across services.

**Key modules:**
- `utils` - ID generation, time handling
- `devops` - Environment detection
- `errors` - Standardized error types
- `http` - HTTP utilities

```python
from campus.common import utils, devops, errors

user_id = utils.uid()
timestamp = utils.utc_time()
env = devops.ENV
```

### Entity Models (`campus.model`)

**Purpose:** Entity representation only - no business logic.

```python
from campus import model

def process_user(user: model.User) -> dict:
    return {"id": user.id, "name": user.name}
```

## Development Patterns

### Interface-First Design

Define abstract interfaces for polymorphic concrete classes.

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

**Benefits:**
- Enables swappable implementations
- Easier testing with mock implementations
- Clear contracts between components

## Common Pitfalls

### Storage Initialization Order

Test fixtures must lazy-import `campus.storage` modules. Otherwise storage backends initialize before test mode is set.

```python
# Bad - initializes storage immediately
from campus.storage import tables

# Good - lazy import
def test_something():
    from campus.storage import tables
```

### Import Problems

- **Circular imports:** Structure dependencies to prevent cycles
- **Standard library shadowing:** Avoid directory names like `collections/`, `json/`, `os/`
- **Package imports:** Import packages, not individual functions (see [STYLE-GUIDE.md](STYLE-GUIDE.md))

### Architecture Violations

- **Business logic in models:** Keep `campus.model` as pure data structures; put logic in `.resources`
- **Missing .resources:** Each service (auth, api) should have business logic in `.resources` submodule

### Storage Interface Violations

- **Missing required fields:** All storage objects need `id` and `created_at`
- **Inconsistent error handling:** Use standardized error types from `campus.common.errors`
- **Direct database access:** Use storage interfaces instead of direct DB connections

### Configuration

- **Use campus_python client:** Access config via `campus.auth.vaults`
- **Environment variables:** Only for deployment (ENV, DEPLOY, CLIENT_ID, CLIENT_SECRET, POSTGRESDB_URI)
- **Secrets management:** Access via `campus_python.Campus().auth.vaults[deployment][key]`

## Adding New Features

1. **Design interfaces first** - Define abstract classes for new functionality
2. **Follow storage pattern** - Implement storage-model-resources separation
3. **Test thoroughly** - Use appropriate testing strategy (see [TESTING-GUIDE.md](TESTING-GUIDE.md))
4. **Update documentation** - Include usage examples and interface contracts

## Modifying Existing Code

1. **Understand dependencies** - Check which services depend on your changes
2. **Maintain interfaces** - Don't break existing abstract contracts
3. **Test backwards compatibility** - Ensure existing code still works
4. **Update all implementations** - If changing interfaces, update all backends

## Documentation Standards

### Writing Style

- **Brief and precise**: Avoid verbose explanations; focus on essential information
- **Clear structure**: Use headings, lists, and code blocks to organize content
- **Consistent terminology**: Use established terms throughout the project
- **Active voice**: Prefer "Configure the database" over "The database should be configured"

### Docstring Requirements

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

- Explain **why**, not **what**
- Document non-obvious design decisions
- Include rationale for architectural choices
- Reference related issues or documentation

---

This document is living and should be updated as the project evolves.
