#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
REPO_ROOT="$SCRIPT_DIR/../.."

# Ensure namespace marker is present in the local package tree (do not overwrite real __init__.py)
if [ ! -f "$SCRIPT_DIR/campus/__init__.py" ]; then
  mkdir -p "$SCRIPT_DIR/campus"
  cp "$REPO_ROOT/campus/__init__.py" "$SCRIPT_DIR/campus/__init__.py"
fi

# Install dependencies and build wheels for all meta-package dependencies
for pkg in common vault storage client models apps workspace; do
  cd "$REPO_ROOT/campus/$pkg"
  poetry install --no-root
  poetry build
  pip install "$REPO_ROOT/campus/$pkg/dist/"campus_suite_${pkg}-*.whl
  cd "$REPO_ROOT"
done

echo "✅ campus-suite-workspace and all dependencies installed successfully."
