"""campus.auth.integrations

Registry of first-party upstream integrations (#733).

An integration is a namespaced provider string — `google.classroom`,
`google.calendar` — backed by its own upstream OAuth client. The base
provider string (`google`) remains the identity/login client and is not
part of this registry.

The registry itself is code (reviewed like any allowlist); the
integration's secrets and scope cap are data, held in the vault under a
label mirroring the provider string:

| key             | meaning                                                  |
|-----------------|----------------------------------------------------------|
| CLIENT_ID       | the integration's upstream OAuth client id (required)    |
| CLIENT_SECRET   | the integration's upstream OAuth client secret (required)|
| SCOPES          | space-delimited static scope cap of that client          |
| CONNECT_TARGETS | comma-separated HTTPS origins the connect flow may redirect to |

A registry entry with no vault client is inert: it resolves but every
guarded surface answers 404 until the vault keys are seeded
(fail-closed). This is how `google.calendar` can ship as a stub before
its Google client exists.
"""

__all__ = [
    "Integration",
    "IntegrationConfig",
    "REGISTRY",
    "get",
    "get_config",
    "resolve",
]

from dataclasses import dataclass
from typing import TYPE_CHECKING

from campus.common.errors import api_errors

from . import resources, scopes

if TYPE_CHECKING:
    from .resources.vault import VaultResource


@dataclass(frozen=True)
class Integration:
    """A first-party upstream integration (namespaced provider)."""
    slug: str           # "classroom"
    provider: str       # "google.classroom" — the namespaced provider string
    base_provider: str  # "google" — the identity/login provider
    vault_label: str    # "google.classroom" — mirrors the provider string
    title: str          # display name for connect UX
    description: str = ""  # one-line public description for consumer UX


@dataclass(frozen=True)
class IntegrationConfig:
    """The integration's vault-sourced runtime configuration."""
    client_id: str
    client_secret: str
    scopes: list[str]
    connect_targets: tuple[str, ...]


REGISTRY: dict[str, Integration] = {
    "classroom": Integration(
        slug="classroom",
        provider="google.classroom",
        base_provider="google",
        vault_label="google.classroom",
        title="Google Classroom",
        description=(
            "Connect Google Classroom to your Campus account so "
            "Campus apps can read your courses and coursework."
        ),
    ),
    # Stub: inert until a vault label with a real client is seeded.
    "calendar": Integration(
        slug="calendar",
        provider="google.calendar",
        base_provider="google",
        vault_label="google.calendar",
        title="Google Calendar",
        description=(
            "Connect Google Calendar to your Campus account "
            "(coming soon)."
        ),
    ),
}


def get(slug: str) -> Integration:
    """Return the registry entry for a slug.

    Raises:
        api_errors.NotFoundError: If the slug is not in the registry.
    """
    integration = REGISTRY.get(slug)
    if integration is None:
        raise api_errors.NotFoundError(
            f"Unknown integration {slug!r}",
            integration=slug,
        )
    return integration


def resolve(provider: str) -> Integration:
    """Resolve a namespaced provider string to its registry entry.

    Splits on the first dot and validates both halves against the
    registry, so unknown slugs and base-provider mismatches are both
    404s.

    Raises:
        api_errors.NotFoundError: If the string is not a registered
            integration provider.
    """
    base, sep, slug = provider.partition(".")
    if not sep:
        raise api_errors.NotFoundError(
            f"{provider!r} is not a namespaced integration provider",
            provider=provider,
        )
    integration = get(slug)
    if integration.provider != provider:
        raise api_errors.NotFoundError(
            f"Unknown integration provider {provider!r}",
            provider=provider,
            integration=integration.slug,
        )
    return integration


def get_config(integration: Integration) -> IntegrationConfig:
    """Load an integration's vault label at call time, fail-closed.

    Missing CLIENT_ID/CLIENT_SECRET means the integration exists in the
    registry but has no upstream OAuth client: the caller must treat it
    as inert (this raises 404). Missing/empty SCOPES yields an empty
    scope cap and missing/empty CONNECT_TARGETS disables the connect
    flow — both deny everything rather than widen access.

    Raises:
        api_errors.NotFoundError: If the vault label has no upstream
            OAuth client configured.
    """
    label = resources.vault[integration.vault_label]
    try:
        client_id = label["CLIENT_ID"]
        client_secret = label["CLIENT_SECRET"]
    except KeyError:
        raise api_errors.NotFoundError(
            f"Integration {integration.provider!r} is not configured; "
            "its vault label has no upstream OAuth client",
            integration=integration.slug,
            provider=integration.provider,
        ) from None
    return IntegrationConfig(
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes.parse(_optional(label, "SCOPES")),
        connect_targets=_parse_origins(_optional(label, "CONNECT_TARGETS")),
    )


def _optional(label: "VaultResource", key: str) -> str:
    """Read an optional vault key, defaulting to the empty string."""
    try:
        return label[key] or ""
    except KeyError:
        return ""


def _parse_origins(value: str) -> tuple[str, ...]:
    """Parse the comma-separated CONNECT_TARGETS origin list."""
    return tuple(
        origin.strip()
        for origin in value.split(",")
        if origin.strip()
    )
