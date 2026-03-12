# Campus Style Guide

This document defines coding standards for the Campus project.

**For documentation standards**, see [development-guidelines.md](development-guidelines.md).

**For code review checklist**, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Python Code Standards

### Code Conventions

Follow established Python conventions:
- **PEP 8**: Python code style guide
- **PEP 257**: Docstring conventions
- **Type hints**: Use type annotations for function parameters and return values

### Import Structure

Organize imports in this order:
1. **Built-in modules** (standard library)
2. **Third-party packages** (installed via pip/poetry)
3. **Campus packages** (absolute imports starting with `campus.`)
4. **Local imports** (relative imports from current module)

```python
# Built-in imports
import os
import sys
from typing import Dict, List

# Third-party imports
import flask
import requests

# Campus package imports
from campus.common import utils
from campus.common.errors import CampusError
import campus.storage

# Local imports
from .models import User
from .utils import validate_input
```

### Package Import Requirements

**Preferred**: Module-level imports

```python
# Within same service
from campus.auth import resources

# Cross-service (e.g., from campus.api)
from campus.auth import resources as auth_resources
from campus.api import resources

# Common utilities
from campus.common import utils, devops
import campus.storage
from campus import model

# Use through module namespaces
user_id = utils.uid()
timestamp = utils.utc_time()
users = campus.storage.get_collection("users")
```

**Avoid** importing individual functions:
```python
# Don't do this - loses context
from campus.common.utils import uid, utc_time
from campus.auth.resources import create_user
```

Rationale: Module namespacing maintains clarity and prevents conflicts.

### Function Calling Conventions

Call functions through module namespaces:
```python
# Good
from campus.common import utils
from campus.auth import resources

user_id = utils.uid()
user = resources.create_user(data)
```

Avoid direct function imports:
```python
# Avoid - loses context
from campus.common.utils import uid
from campus.auth.resources import create_user

uid()  # Unclear origin
```

### Docstrings

**All functions, classes, and modules must have docstrings.**

Use Google-style docstrings:

```python
def create_user(name: str, email: str, role: str = "student") -> User:
    """Create a new user with the specified details.

    Args:
        name: Full name of the user
        email: Valid email address
        role: User role (student, teacher, admin)

    Returns:
        User object with generated ID and timestamps

    Raises:
        ValidationError: If email format is invalid
        CampusError: If user creation fails

    Example:
        >>> user = create_user("John Doe", "john@example.com", "student")
        >>> print(user.id)
        'usr_123abc'
    """
```

### Error Handling

Use specific exception types:
```python
# Good - specific errors
from campus.common.errors import ValidationError, CampusError

def validate_user_data(data: Dict) -> None:
    if not data.get('email'):
        raise ValidationError("Email is required")
    if '@' not in data['email']:
        raise ValidationError("Invalid email format")
```

## Git Commit Standards

### Requirements
- **All commits must have a message** - never use `git commit` without `-m`
- Use conventional commit format: `<type>(<scope>): <description>`
- Follow [Writing Good Commit Messages](https://nyjc-computing.github.io/nanyang-system-developers/contributors/training/commit-messages.html) guidelines

### Commit Types
- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation changes
- **style**: Code style changes (formatting, etc.)
- **refactor**: Code refactoring
- **test**: Adding or updating tests
- **chore**: Build process or auxiliary tool changes
