#!/bin/bash
set -e

# Build and install campus-common (dependency)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/../.."
cd "$REPO_ROOT/campus/common"
poetry build
cd "$REPO_ROOT/campus/vault"
poetry build

# Install both wheels in dependency order
pip install "$REPO_ROOT/campus/common/dist/"campus_suite_common-*.whl
pip install "$REPO_ROOT/campus/vault/dist/"campus_suite_vault-*.whl

echo "✅ campus-suite-vault and dependencies installed successfully."
