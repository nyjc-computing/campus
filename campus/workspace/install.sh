#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
REPO_ROOT="$SCRIPT_DIR/../.."

# Ensure namespace marker is present in the local package tree (do not overwrite real __init__.py)
if [ ! -f "$SCRIPT_DIR/campus/__init__.py" ]; then
  mkdir -p "$SCRIPT_DIR/campus"
  cp "$REPO_ROOT/campus/__init__.py" "$SCRIPT_DIR/campus/__init__.py"
fi

# Build and install campus-suite-common
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

# Build and install campus-suite-client
cd "$REPO_ROOT/campus/client"
poetry build
pip install "$REPO_ROOT/campus/client/dist/"campus_suite_client-*.whl

# Build and install campus-suite-models
cd "$REPO_ROOT/campus/models"
poetry build
pip install "$REPO_ROOT/campus/models/dist/"campus_suite_models-*.whl

# Build and install campus-suite-apps
cd "$REPO_ROOT/campus/apps"
poetry build
pip install "$REPO_ROOT/campus/apps/dist/"campus_suite_apps-*.whl

# Build and install campus-suite-workspace
cd "$REPO_ROOT/campus/workspace"
poetry build
pip install "$REPO_ROOT/campus/workspace/dist/"campus_suite_workspace-*.whl

echo "✅ campus-suite-workspace and all dependencies installed successfully."
