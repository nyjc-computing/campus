#!/usr/bin/env bash
set -e

# Build and install campus-storage and its dependencies in the correct order

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/../.."

# Ensure namespace marker is present in the local package tree (do not overwrite real __init__.py)
if [ ! -f "$SCRIPT_DIR/campus/__init__.py" ]; then
  mkdir -p "$SCRIPT_DIR/campus"
  cp "$REPO_ROOT/campus/__init__.py" "$SCRIPT_DIR/campus/__init__.py"
fi

# Build and install campus-suite-common first
cd "$REPO_ROOT/campus/common"
poetry build
pip install "$REPO_ROOT/campus/common/dist/"campus_suite_common-*.whl

# Build and install campus-suite-vault
cd "$REPO_ROOT/campus/vault"
poetry build
pip install "$REPO_ROOT/campus/vault/dist/"campus_suite_vault-*.whl

# Build and install campus-suite-storage
cd "$REPO_ROOT/campus/storage"
poetry build
pip install "$REPO_ROOT/campus/storage/dist/"campus_suite_storage-*.whl

echo "✅ campus-suite-storage and dependencies installed successfully."
