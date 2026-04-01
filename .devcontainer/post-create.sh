#!/bin/bash

# Configure Git to use fast-forward pulls only
git config pull.ff true

# Set up pre-push hook to catch sanity check failures early
git config core.hooksPath .githooks

# Install Poetry (already in image but ensure it's available)
pip install poetry --quiet

# Install poetry-shell plugin
poetry self add poetry-plugin-shell

# Install project dependencies (don't install campus package)
poetry install --no-root

# Activate poetry venv (for pylance auto-import)
poetry shell
