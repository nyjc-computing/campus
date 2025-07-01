"""apps.integration.config

Config for third-party integrations.
"""

import json
import os

from .schema import IntegrationConfigSchema


def get_config(provider: str) -> IntegrationConfigSchema:
    """Get the configuration for a specific integration provider."""
    # change cwd to this file's directory
    os.chdir(os.path.dirname(__file__))
    # Load the provider's config file
    try:
        with open(f"{provider}.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as err:
        raise ValueError(
            f"Configuration for provider '{provider}' not found."
        ) from err
    except json.JSONDecodeError as err:
        raise ValueError(
            f"Invalid JSON in configuration for '{provider}': {err}"
        ) from err
