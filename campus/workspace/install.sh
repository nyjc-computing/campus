#!/bin/bash
set -e

# Build and install all dependencies for the workspace metapackage
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/../.."

# Ensure namespace marker is present in the local package tree (do not overwrite real __init__.py)
if [ ! -f "$SCRIPT_DIR/campus/__init__.py" ]; then
  mkdir -p "$SCRIPT_DIR/campus"
  cp "$REPO_ROOT/campus/__init__.py" "$SCRIPT_DIR/campus/__init__.py"
fi

# Build all required wheels
for pkg in common vault client apps workspace; do
  cd "$REPO_ROOT/campus/$pkg"
  poetry build
  cd "$REPO_ROOT"
done

# Install all wheels in dependency order
pip install "$REPO_ROOT/campus/common/dist/"campus_suite_common-*.whl
pip install "$REPO_ROOT/campus/vault/dist/"campus_suite_vault-*.whl
pip install "$REPO_ROOT/campus/client/dist/"campus_suite_client-*.whl
pip install "$REPO_ROOT/campus/apps/dist/"campus_suite_apps-*.whl
pip install "$REPO_ROOT/campus/workspace/dist/"campus_suite_workspace-*.whl

echo "✅ campus-suite-workspace and all dependencies installed successfully."
