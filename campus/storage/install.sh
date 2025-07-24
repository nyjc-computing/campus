#!/usr/bin/env bash
set -e

# Build and install campus-storage and its dependencies in the correct order

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/../.."

# Ensure namespace marker is present
mkdir -p "$SCRIPT_DIR/campus"
cp "$REPO_ROOT/campus/__init__.py" "$SCRIPT_DIR/campus/__init__.py"

cd "$REPO_ROOT/campus/common"
poetry install
poetry build

cd "$REPO_ROOT/campus/vault"
bash install.sh

cd "$REPO_ROOT/campus/storage"
poetry install
poetry build
poetry run pip install dist/*.whl

echo "✅ campus-storage and dependencies installed."
