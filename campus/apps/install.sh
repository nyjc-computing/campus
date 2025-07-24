#!/bin/bash
set -e

# Build and install campus-common (dependency)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/../.."
cd "$REPO_ROOT/campus/common"
poetry build
cd "$REPO_ROOT/campus/apps"
poetry build

# Install both wheels in dependency order
pip install "$REPO_ROOT/campus/common/dist/"campus_suite_common-*.whl
pip install "$REPO_ROOT/campus/apps/dist/"campus_suite_apps-*.whl

echo "✅ campus-suite-apps and dependencies installed successfully."
