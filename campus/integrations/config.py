"""campus.integrations.config

Config for third-party integrations.
"""

__all__ = [
    "HttpScheme",
    "IntegrationConfigSchema",
    "OAuth2AuthorizationCodeConfigSchema",
    "OAuth2ClientCredentialsConfigSchema",
    "OAuth2Flow",
    "Security",
    "SecurityConfigSchema",
    "get_config",
]

import json
import os
from pathlib import Path
from typing import Any

from .base import (
    HttpScheme,
    IntegrationConfigSchema,
    OAuth2Flow,
    OAuth2AuthorizationCodeConfigSchema,
    OAuth2ClientCredentialsConfigSchema,
    Security,
    SecurityConfigSchema,
)

CONFIG_ROOT = os.path.dirname(__file__)


def _chdir_config_root():
    """Change the current working directory to the config root."""
    if os.getcwd() != CONFIG_ROOT:
        os.chdir(CONFIG_ROOT)

def _load_json(file_path: str) -> dict[str, Any]:
    """Load a JSON file and return its content."""
    if Path(file_path).suffix != ".json":
        raise ValueError("{file_path}: File must be .json")
    if Path(file_path).is_absolute():
        raise ValueError(f"{file_path}: File path must be relative")
    fullpath = Path(CONFIG_ROOT) / file_path
    try:
        with open(fullpath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as err:
        raise FileNotFoundError(f"File not found: {fullpath}") from err


def get_config(provider: str, resource: str = "api") -> dict[str, Any]:
    """Get the configuration for a specific integration provider."""
    # Load the provider's config file
    config = _load_json(f"{provider}/{resource}.json")
    return config
