# Campus Apps

Campus web applications and API endpoints.

## Installation

This subpackage is intended to be installed as part of a larger Campus deployment or for advanced users who need only the apps service.

**Recommended installation method:**

```bash
bash install.sh
```

This script will build and install `campus-suite-apps` and its dependencies in the correct order.

> **Note:** Do not use `pip install` or `poetry install` directly for this subpackage unless you are developing locally. The install script ensures all dependencies are present.

## Usage

After installation, you can import Campus apps modules as needed:

```python
from campus.apps.api import routes
from campus.apps.oauth import GoogleOAuth
```

## Not for Standalone Use

This package is not intended to be used standalone by most users. For a full Campus deployment, use the `campus/workspace` meta-package.
