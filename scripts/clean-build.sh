#!/bin/bash
# Clean build artifacts and caches before container rebuild

echo "🧹 Cleaning Python cache files..."
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete

echo "🧹 Cleaning Poetry virtual environments..."
cd /workspaces/campus
poetry env remove --all 2>/dev/null || true

for dir in campus/*/; do
    if [ -f "$dir/pyproject.toml" ]; then
        echo "  Cleaning $dir"
        cd "$dir"
        poetry env remove --all 2>/dev/null || true
        cd - >/dev/null
    fi
done

echo "✅ Clean complete! Ready for container rebuild."
