#!/bin/bash

# Configure Git to use fast-forward pulls
git config pull.ff true

# Set up pre-push hook to catch sanity check failures early
git config core.hooksPath .githooks

# Install Poetry and project dependencies
pip install poetry
poetry install --no-root  # don't install campus package

# Install poetry-shell plugin
poetry self add poetry-plugin-shell

# Activate poetry venv (for pylance auto-import)
poetry shell
