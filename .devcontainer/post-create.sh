#!/bin/bash

# Configure Git to use fast-forward pulls
git config pull.ff true

# Set up pre-push hook to catch sanity check failures early
git config core.hooksPath .githooks

# Install project dependencies (gh and poetry already in image)
poetry install --no-root  # don't install campus package

# Activate poetry venv (for pylance auto-import)
poetry shell
