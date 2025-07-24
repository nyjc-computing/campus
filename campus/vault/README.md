# Campus Vault

Campus secure secrets management service.

## Installation

This subpackage is intended for users who need only the vault service, or for advanced deployments.

**Recommended installation method:**

```bash
bash install.sh
```

This script will build and install `campus-suite-vault` and its dependencies in the correct order.

> **Note:** Do not use `pip install` or `poetry install` directly for this subpackage unless you are developing locally. The install script ensures all dependencies are present.

## Usage

After installation, you can import Campus vault modules as needed:

```python
from campus.vault import Vault, get_vault
```

## Not for Standalone Use

This package is not intended to be used standalone by most users. For a full Campus deployment, use the `campus/workspace` meta-package.
