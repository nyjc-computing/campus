FROM mcr.microsoft.com/devcontainers/python:3.11

# Remove any problematic third-party apt source (yarn) added by the base image
# so `apt-get update` does not fail due to a missing GPG key, then install gh
RUN rm -f /etc/apt/sources.list.d/yarn*.list || true \
    && rm -f /etc/apt/trusted.gpg.d/yarn*.gpg || true \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry globally
RUN pip install --no-cache-dir poetry

# Add poetry shell plugin
RUN poetry self add poetry-plugin-shell

# Verify installations
RUN gh --version && poetry --version
