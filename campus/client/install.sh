#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/../.."

# Ensure namespace marker is present in the local package tree (do not overwrite real __init__.py)
if [ ! -f "$SCRIPT_DIR/campus/__init__.py" ]; then
  mkdir -p "$SCRIPT_DIR/campus"
  cp "$REPO_ROOT/campus/__init__.py" "$SCRIPT_DIR/campus/__init__.py"
fi
cd "$REPO_ROOT/campus/common"
poetry build
cd "$REPO_ROOT/campus/client"
poetry build

# Install both wheels in dependency order
pip install "$REPO_ROOT/campus/common/dist/"campus_suite_common-*.whl
pip install "$REPO_ROOT/campus/client/dist/"campus_suite_client-*.whl

echo "✅ campus-suite-client and dependencies installed successfully."
