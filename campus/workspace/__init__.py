"""campus.workspace

Meta-package that provides the complete Campus ecosystem.

This package imports and exposes all Campus subpackages, making it easy to
deploy the entire Campus system as a single package while maintaining the
modular development structure.

## What This Provides

- **Complete Campus System**: All campus.* modules bundled together
- **Deployment Ready**: Works with any Poetry version (Replit, Heroku, etc.)
- **Modular Development**: Individual packages maintained for development

## Quick Start

```python
# Import everything via workspace
import campus.workspace as workspace

# Or import specific modules directly from namespace
from campus import models, vault, storage, apps
```

## Package Contents

- `campus.common`: Foundational utilities and integration configs
- `campus.vault`: Secure credential and secret management  
- `campus.storage`: Database backends (MongoDB, PostgreSQL)
- `campus.client`: External API integration libraries
- `campus.models`: Data models and schemas
- `campus.apps`: Web applications and services

## Architecture

Campus is built as a collection of modular packages:
- campus.common: Foundational utilities and integration configurations
- campus.vault: Secure credential and secret management
- campus.storage: Database backends (MongoDB, PostgreSQL)
- campus.client: External API integration libraries
- campus.models: Data models and schemas
- campus.apps: Web applications and services

## Deployment Strategy

This workspace solves the Poetry version compatibility issue for platforms
like Replit that use older Poetry versions:

### Problem Solved
- Older Poetry versions don't support `package-mode = false`
- Individual package dependencies can cause deployment failures
- Complex configuration switching was too cumbersome

### Solution
- Root pyproject.toml uses standard Poetry configuration (no modern features)
- All dependencies consolidated in single package
- Individual subpackages maintained for modular development
- No special deployment steps required

## Usage

```python
# Import the complete Campus system
import campus.workspace as workspace

# Or import specific modules directly
from campus import models, vault, storage
from campus.apps import factory

# Option 1: Use through workspace re-exports
user = workspace.models.User(...)
vault_client = workspace.vault.get_vault("storage")

# Option 2: Use direct namespace imports
user = models.User(...)
secret = vault.get_secret("database_url")
```

## Development vs Deployment

**Development**: Individual packages for modular work, junior developer onboarding
**Deployment**: Single consolidated package, works with any Poetry version
**Result**: Same code works everywhere, no configuration switching needed
"""

# Import all Campus packages to make them available
import campus.common as common
import campus.vault as vault
import campus.storage as storage
# import campus.client as client  # TODO: Re-enable when client refactoring is complete
import campus.models as models
import campus.apps as apps

# Re-export for convenience
__all__ = [
    'common',
    'vault', 
    'storage',
    # 'client',  # TODO: Re-enable when client refactoring is complete
    'models',
    'apps'
]

# Version information
__version__ = "0.1.0"
