FROM mcr.microsoft.com/devcontainers/python:3.11

# Install GitHub CLI and Poetry
RUN apt-get update && apt-get install -y \
    gh \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry globally
RUN pip install --no-cache-dir poetry

# Add poetry shell plugin
RUN poetry self add poetry-plugin-shell

# Verify installations
RUN gh --version && poetry --version
