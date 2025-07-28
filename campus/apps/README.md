# Campus Apps

Campus web applications and API endpoints.

## Installation

This subpackage is intended to be installed as part of a larger Campus deployment or for advanced users who need only the apps service.

**Recommended installation method:**

```bash
poetry install
```

This will install `campus-suite-apps` and all dependencies in a Poetry-managed virtual environment.

> **Note:** Use `poetry install` for development and deployment. Ensure you are in the correct directory for the subpackage you wish to install.

## Usage

After installation, you can import Campus apps modules as needed:

```python
from campus.apps.api import routes
from campus.apps.oauth import GoogleOAuth
```

## Not for Standalone Use

This package is not intended to be used standalone by most users. For a full Campus deployment, use the `campus/workspace` meta-package.
