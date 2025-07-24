#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
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

# Build and install campus-suite-apps
cd "$REPO_ROOT/campus/apps"
poetry build
pip install "$REPO_ROOT/campus/apps/dist/"campus_suite_apps-*.whl

echo "✅ campus-suite-apps and dependencies installed successfully."
