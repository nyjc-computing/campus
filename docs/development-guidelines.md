# Development Guidelines

This document captures architectural decisions, design patterns, and development best practices for the Campus project. These guidelines ensure consistency across the codebase and help both human developers and AI agents make appropriate decisions.

## Table of Contents

- [Core Architectural Patterns](#core-architectural-patterns)
- [Environment and Configuration](#environment-and-configuration)
- [Database and Storage](#database-and-storage)
- [Package Architecture](#package-architecture)
- [Testing and CI/CD](#testing-and-cicd)
- [Code Organization](#code-organization)

## Core Architectural Patterns

### Lazy Loading Pattern

**Context**: Classes that require external resources (databases, APIs, vault secrets) should not fail during import or instantiation if those resources are unavailable.

**Pattern**: Defer resource acquisition until first use.

**Implementation**:
```python
class ResourceClient:
    def __init__(self, name: str):
        self.name = name
        self._connection = None
        self._config = None
    
    def _ensure_connection(self):
        """Establish connection on first use."""
        if self._connection is None:
            config = self._get_config()  # May require vault/env vars
            self._connection = create_connection(config)
    
    @property
    def connection(self):
        """Get connection, establishing it if needed."""
        self._ensure_connection()
        return self._connection
    
    def close(self):
        """Clean up resources if established."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
```

**Rationale**: 
- Enables CI/CD builds without requiring production secrets
- Allows package imports in environments where resources aren't available
- Improves startup time by deferring expensive operations

**Examples**: `MongoDBCollection`, database connection classes

### Interface-First Design

**Pattern**: Define abstract interfaces before implementing concrete classes.

**Implementation**:
```python
from abc import ABC, abstractmethod

class StorageInterface(ABC):
    @abstractmethod
    def get_by_id(self, doc_id: str) -> dict:
        """Retrieve a document by ID."""
        pass

class ConcreteStorage(StorageInterface):
    def get_by_id(self, doc_id: str) -> dict:
        # Implementation here
        pass
```

**Rationale**: Enables swappable backends, easier testing, clear contracts

## Environment and Configuration

### Environment Variable Access

**Pattern**: All environment variable access must go through the vault system.

**Correct**:
```python
from campus.vault import get_vault

def get_database_uri():
    storage_vault = get_vault("storage")
    return storage_vault.get("DATABASE_URI")
```

**Incorrect**:
```python
import os
database_uri = os.getenv("DATABASE_URI")  # Don't do this
```

**Rationale**: Centralized secret management, consistent error handling, audit trail

### Configuration Lazy Loading

**Pattern**: Configuration retrieval should be deferred until needed.

**Implementation**:
```python
def _get_config_value():
    """Get configuration value from vault (called lazily)."""
    try:
        vault = get_vault("service_name")
        return vault.get("CONFIG_KEY")
    except Exception as e:
        raise RuntimeError(f"Failed to get config: {e}") from e

class Service:
    def __init__(self):
        self._config = None
    
    def _ensure_config(self):
        if self._config is None:
            self._config = _get_config_value()
    
    def operation(self):
        self._ensure_config()
        # Use self._config here
```

## Database and Storage

### Backend Abstraction

**Pattern**: All storage implementations must implement their respective interfaces.

**Structure**:
```
storage/
├── documents/
│   ├── interface.py          # Abstract interface
│   ├── backend/
│   │   ├── mongodb.py        # MongoDB implementation
│   │   └── other_db.py       # Other implementations
│   └── __init__.py           # Factory functions
└── tables/
    ├── interface.py          # Abstract interface
    ├── backend/
    │   └── postgres.py       # PostgreSQL implementation
    └── __init__.py           # Factory functions
```

### Connection Management

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

## Decision Record

### ADR-001: Lazy Loading for External Resources
- **Date**: 2025-01-21
- **Status**: Adopted
- **Context**: CI/CD builds failing due to missing environment variables during package imports
- **Decision**: Implement lazy loading pattern for all external resource access
- **Consequences**: Enables build-time isolation, requires consistent implementation across codebase

### ADR-002: Namespace Package Architecture
- **Date**: 2025-01-21  
- **Status**: Adopted
- **Context**: Need for modular distribution and independent package versioning
- **Decision**: Use namespace packages with clear dependency ordering
- **Consequences**: Enables selective installation, requires careful dependency management

### ADR-003: Vault-Centralized Configuration
- **Date**: 2025-01-21
- **Status**: Adopted
- **Context**: Need for secure, auditable configuration management
- **Decision**: All environment variable access goes through vault system
- **Consequences**: Centralized secret management, consistent error handling, audit trail

---

## Contributing

When contributing to Campus:

1. **Follow the established patterns** documented above
2. **Add new patterns** to this document when you establish them
3. **Update ADRs** when making architectural decisions
4. **Test your changes** in isolation to ensure they follow lazy loading principles
5. **Document your design decisions** in code comments

This document is living and should be updated as the project evolves.
