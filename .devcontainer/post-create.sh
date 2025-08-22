#!/bin/bash

# Configure Git to use fast-forward pulls
git config pull.ff true

# Ensure we're using Python 3.11
echo "Python version: $(python --version)"
echo "Python path: $(which python)"

# Install Poetry and project dependencies
pip install poetry
poetry env use python3.11 || poetry env use python3 || poetry env use python
poetry install --no-root  # don't install campus package

# Install poetry-shell plugin
poetry self add poetry-plugin-shell

# Activate poetry venv (for pylance auto-import)
poetry shell
