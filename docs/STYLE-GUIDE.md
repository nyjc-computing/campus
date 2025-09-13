# Campus Style Guide

This document defines coding and documentation standards for the Campus project.

## Documentation Standards

### Writing Style
- **Brief and precise**: Avoid verbose explanations; focus on essential information
- **Clear structure**: Use headings, lists, and code blocks to organize content
- **Consistent terminology**: Use established terms throughout the project
- **Active voice**: Prefer "Configure the database" over "The database should be configured"

### Documentation Format
- Use Markdown for all documentation files
- Include table of contents for documents longer than 50 lines
- End code blocks with proper language specification (```python, ```bash, etc.)
- Use relative links for internal documentation references

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
from campus.vault import get_vault
from campus.storage import PostgreSQLStorage
from campus.common.errors import CampusError

# Local imports
from .models import User
from .utils import validate_input
```

### Package Import Requirements

Organise imports in ascending order by name, uppercase followed by lowercase.

**Critical**: Campus core packages must be imported at package level:

```python
# Required - import packages, not individual functions
import campus.vault
import campus.storage

# Modules and submodules may be imported from packages
from campus.common import devops
from campus.common.utils import utc_time
from campus.storage import get_collection, get_table

# Then call functions through modules
vault = campus.vault.get_vault()
storage = campus.storage.create_storage()
campus.common.devops.deploy.create_app()
```

**Avoid** importing individual functions from modules:
```python
# Don't do this - breaks polymorphism and modularity
from campus.common.devops.deploy import create_app
from campus.common.utils.utc_time import now
```

**Rationale**: Some modules intentionally have similarly named functions for polymorphism. Importing through modules maintains clear namespacing and prevents naming conflicts.

### Function Calling Conventions

**Prefer** calling functions through their modules:
```python
# Good - clear module context
.deploy.create_app()
campus.vault.access.check_permission()

# Acceptable for frequently used utilities
from campus.common import utils
result = utils.validate_email(email)
```

**Avoid** importing functions directly when modules provide context:
```python
# Avoid - loses module context
from campus.common.devops.deploy import create_app
create_app()  # Unclear which create_app this is
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

## Common Pitfalls

### Development Environment
- **Always use Poetry**: Run `poetry run python` instead of just `python`
- **Check your environment**: Use `poetry env info` to verify active environment

### Import Issues
- **Avoid circular imports**: Structure imports to prevent dependency cycles
- **Use absolute imports**: Prefer `campus.vault` over relative imports in most cases

### Testing
- **Use appropriate test strategy**: See [testing-strategies.md](testing-strategies.md)
- **Test edge cases**: Include error conditions and boundary values

### Configuration
- **Never commit secrets**: Use vault service for all sensitive configuration
- **Document configuration**: Update docs when adding new config options

## Code Review Guidelines

### Before Submitting
- [ ] All tests pass locally
- [ ] Code follows style guide
- [ ] Documentation is updated
- [ ] Commit messages follow format
- [ ] No secrets in code

### Review Focus Areas
- **Security**: Check for potential vulnerabilities
- **Performance**: Look for inefficient operations
- **Maintainability**: Ensure code is readable and well-structured
- **Testing**: Verify adequate test coverage
- **Documentation**: Confirm docs match implementation
