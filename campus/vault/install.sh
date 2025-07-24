#!/bin/bash
set -e

# Build and install campus-suite-vault and its dependencies in the correct order
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/../.."
cd "$REPO_ROOT/campus/common"
poetry build
cd "$REPO_ROOT/campus/vault"
 
# Ensure namespace marker is present
mkdir -p "$SCRIPT_DIR/campus"
cp "$REPO_ROOT/campus/__init__.py" "$SCRIPT_DIR/campus/__init__.py"

poetry build

# Install both wheels in dependency order
pip install "$REPO_ROOT/campus/common/dist/"campus_suite_common-*.whl
pip install "$REPO_ROOT/campus/vault/dist/"campus_suite_vault-*.whl

echo "✅ campus-suite-vault and dependencies installed successfully."
