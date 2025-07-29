# Campus Vault

Campus secure secrets management service.

## Installation

This subpackage is intended for users who need only the vault service, or for advanced deployments.

**Recommended installation method:**

```bash
poetry install
```

This will install `campus-suite-vault` and all dependencies in a Poetry-managed virtual environment.

> **Note:** Use `poetry install` for development and deployment. Ensure you are in the correct directory for the subpackage you wish to install.

## Usage

After installation, you can import Campus vault modules as needed:

```python
from campus.vault import Vault, get_vault
```

## Not for Standalone Use

This package is not intended to be used standalone by most users. For a full Campus deployment, use the `campus` meta-package (the root of the repository).
