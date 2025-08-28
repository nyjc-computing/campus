"""campus.models.source.sourcetype
SourceType Models

This module provides classes for creating and managing Campus source types,
which are categories of data sources from third-party platforms and APIs.
"""
from ..integration import (
    CommonCapabilities,
    Url,
)

TABLE = "sourcetypes"


class SourceTypeBase:
    """Base class for source type config objects."""

    def __init__(
            self,
            integration_name: str,
            name: str,
            description: str,
            api_base_url: Url,
            resource_id_format: str,
            scopes: list[str],
            capabilities: CommonCapabilities,
    ):
        self.integration_name = integration_name
        self.name = name
        self.description = description
        self.api_base_url = api_base_url
        self.resource_id_format = resource_id_format
        self.scopes = scopes
        self.capabilities = capabilities

    @classmethod
    def from_dict(cls, data: dict) -> "SourceTypeBase":
        return cls(
            integration_name=data["integration_name"],
            name=data["name"],
            description=data["description"],
            api_base_url=data["api_base_url"],
            resource_id_format=data["resource_id_format"],
            scopes=data["scopes"],
            capabilities=CommonCapabilities(**data["capabilities"]),
        )

    def to_dict(self) -> dict:
        return {
            "integration_name": self.integration_name,
            "name": self.name,
            "description": self.description,
            "api_base_url": self.api_base_url,
            "resource_id_format": self.resource_id_format,
            "scopes": self.scopes,
            "capabilities": self.capabilities,
        }
