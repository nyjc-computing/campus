"""campus.integrations

This module provides classes for creating and managing Campus integrations,
which are connections to third-party platforms and APIs.
"""

__all__ = [
    "HttpScheme", "OAuth2Flow", "Security",
    "discord", "github", "google"
]

from . import discord, github, google
from .base import (
    HttpScheme,
    OAuth2Flow,
    Security,
)
