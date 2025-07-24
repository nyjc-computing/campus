# Building the Campus Python Monorepo

## Overview
This monorepo contains all core packages for the Campus ecosystem, organized under the `campus` namespace. The build protocol described here ensures that all subpackages and their dependencies are handled correctly, and that namespace package requirements are satisfied. This process is designed for reliability in both development and CI environments, and to avoid common pitfalls with Python monorepo packaging.

## Build & Install Process

1. **Namespace Package Marker**
   - Each subpackage's install script ensures that the `campus/__init__.py` namespace marker is present in the package tree. This is required for correct namespace package resolution, but must not overwrite any real `__init__.py` files.

2. **Dependency Installation**
   - Each install script uses Poetry to install all dependencies for its subpackage (and any direct dependencies) in the current environment. This is necessary because pip does not resolve local path dependencies from wheels built in a monorepo.

3. **Wheel Build & Install**
   - Each subpackage is built as a wheel using Poetry, then installed with pip. This ensures the package is importable and ready for use. The workspace meta-package script builds and installs all subpackages in dependency order.

## Why This Protocol?

- **Namespace Package Pitfalls**: Python namespace packages require a marker file (`__init__.py`) in every subpackage tree. Standard build tools do not always propagate this marker, so each install script copies it if missing.
- **Local Path Dependencies**: When using Poetry with `{ path = ... }` dependencies, wheels built from subpackages do not include these dependencies in their METADATA. Pip will not install them automatically, so the script must install dependencies explicitly with Poetry.
- **Import Collisions**: The monorepo avoids naming collisions (e.g., between `campus.py` and `campus/` directory) by renaming files as needed (e.g., `campus.py` → `core.py`).
- **Reproducibility**: The scripts ensure a clean, repeatable build and install process, suitable for both local development and CI/CD pipelines.

## Usage

To build and install any subpackage and its dependencies:

```bash
cd campus/<subpackage>
bash install.sh
```

To build and install the entire Campus suite (all subpackages):

```bash
cd campus/workspace
bash install.sh
```

This will:
- Ensure the namespace marker is present in all subpackage trees
- Install all dependencies for each subpackage using Poetry
- Build wheels for all subpackages
- Install the wheels with pip in dependency order

## Troubleshooting
- If you see import errors (e.g., `No module named 'flask'`), ensure you are using the provided `install.sh` scripts and not installing wheels directly with pip.
- If you rename or move files, clear all `__pycache__` directories and `.pyc` files before rebuilding.
- For monorepo-wide builds, always use the workspace-level install script for a clean environment.

---
For more details, see `PACKAGING.md` and `README.md` in the repo root.
