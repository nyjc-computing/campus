"""campus.model.integration

Integration registry model for Campus.

This module defines the model for entries in the read-only
integrations registry (GET /integrations/v1/, #688): the first-party
integrations Campus offers, with their public catalog metadata.
Registry entries are derived from the registered OAuth proxies at
runtime and carry no secrets.
"""

import typing
from dataclasses import dataclass, field


@dataclass(eq=False, kw_only=True)
class Integration:
    """Dataclass representation of an integrations registry entry.

    Attributes mirror the registry endpoint response (#688):

    - provider: fully-qualified integration id (e.g. "google.classroom")
    - slug: URL slug used in connect flows (e.g. "classroom")
    - base_provider: upstream OAuth proxy the flow runs through
      (e.g. "google")
    - title, description: public catalog copy
    - scopes: the integration's configured scope cap
    - connectable: whether the connect flow is open (proxy configured
      AND connect enabled)
    - authorize_path: auth-server path that starts the connect flow
    """

    provider: str
    slug: str
    base_provider: str
    title: str
    description: str
    scopes: list[str] = field(default_factory=list)
    connectable: bool = False
    authorize_path: str = ""

    @classmethod
    def from_resource(cls, resource: dict[str, typing.Any]) -> typing.Self:
        """Create an Integration from a registry resource dictionary."""
        return cls(
            provider=resource["provider"],
            slug=resource["slug"],
            base_provider=resource["base_provider"],
            title=resource["title"],
            description=resource["description"],
            scopes=list(resource.get("scopes") or []),
            connectable=bool(resource.get("connectable") or False),
            authorize_path=resource.get("authorize_path") or "",
        )

    def to_resource(self) -> dict[str, typing.Any]:
        """Convert to a registry resource dictionary."""
        return {
            "provider": self.provider,
            "slug": self.slug,
            "base_provider": self.base_provider,
            "title": self.title,
            "description": self.description,
            "scopes": list(self.scopes),
            "connectable": self.connectable,
            "authorize_path": self.authorize_path,
        }
