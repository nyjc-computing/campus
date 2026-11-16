"""campus.auth.scopes

Scope algebra for Campus-issued tokens.

Campus tokens carry a scope list validated against the requesting
client's registered allowlist (`Client.allowed_scopes`, fail-closed).
These helpers are the single implementation of that algebra so the
session, authorization-code, and device-code paths cannot drift.

Invariants: docs/auth-token-invariants.md A1-A8.
"""

__all__ = [
    "covers",
    "grants",
    "parse",
    "parse_upstream",
    "union",
    "validate_for_client",
    "validate_upstream_for_client",
]

from campus.common.errors import auth_errors

# Management-scope levels for the <resource>:<level> convention (#865).
# A higher level implies the lower ones on the same resource: a token
# granted clients:admin satisfies a clients:read requirement. "mod"
# sits between read and write (campus-cli#42): moderation-style
# actions such as activating a user that fall short of record
# creation.
_SCOPE_LEVELS = {
    "read": 0,
    "mod": 1,
    "write": 2,
    "admin": 3,
}


def parse(value: str | list[str] | None) -> list[str]:
    """Normalize a scope value to a list.

    Accepts an RFC 6749 space-delimited string, a list, or None.
    Order of first appearance is preserved; duplicates are dropped.
    """
    if value is None:
        return []
    candidates = value.split() if isinstance(value, str) else value
    seen: list[str] = []
    for scope in candidates:
        if scope and scope not in seen:
            seen.append(scope)
    return seen


def parse_upstream(
        value: dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    """Normalize an upstream scope allowlist.

    Accepts a mapping of provider name to scope list (or
    space-delimited string). An empty/None input yields {}.
    """
    if not value:
        return {}
    return {
        provider: parse(scopes_value)
        for provider, scopes_value in value.items()
    }


def covers(granted: list[str], requested: list[str]) -> bool:
    """Return True if every requested scope is in the granted set."""
    return set(requested) <= set(granted)


def grants(granted: list[str], required: str) -> bool:
    """Return True if the granted scopes confer `required` (#865).

    Management scopes follow the `<resource>:<read|mod|write|admin>`
    convention and are monotonic within a resource: `users:admin`
    satisfies a `users:write` requirement, which satisfies
    `users:mod`, which satisfies `users:read`. Scopes of a different
    resource never match, and a required scope outside the convention
    needs an exact match.
    """
    resource, _, level = required.partition(":")
    required_level = _SCOPE_LEVELS.get(level)
    if required_level is None:
        return required in granted
    for scope in granted:
        scope_resource, sep, scope_level = scope.partition(":")
        if (
                sep
                and scope_resource == resource
                and _SCOPE_LEVELS.get(scope_level, -1) >= required_level
        ):
            return True
    return False


def union(*scope_sets: list[str]) -> list[str]:
    """Union of scope sets, preserving order of first appearance."""
    merged: list[str] = []
    for scopes in scope_sets:
        for scope in scopes:
            if scope not in merged:
                merged.append(scope)
    return merged


def validate_for_client(
        allowed_scopes: list[str],
        requested: str | list[str] | None,
) -> list[str]:
    """Validate requested scopes against a client's allowlist.

    Fail-closed: a scope outside the allowlist rejects the whole
    request with `invalid_scope` (RFC 6749 section 4.1.2.1) rather
    than being silently dropped.

    Args:
        allowed_scopes: The client's registered allowlist
        requested: Scopes requested by the caller

    Returns:
        The parsed, validated scope list (empty request passes as [])

    Raises:
        auth_errors.InvalidScopeError: If any requested scope is not
            in the allowlist.
    """
    requested_scopes = parse(requested)
    disallowed = [
        scope for scope in requested_scopes
        if scope not in set(allowed_scopes)
    ]
    if disallowed:
        raise auth_errors.InvalidScopeError(
            f"Requested scopes not allowed for this client: "
            f"{', '.join(disallowed)}",
            disallowed_scopes=disallowed,
        )
    return requested_scopes


def validate_upstream_for_client(
        upstream_scopes: dict[str, list[str]],
        provider: str,
        requested: str | list[str] | None,
) -> list[str]:
    """Validate requested upstream scopes for a provider against a
    client's upstream allowlist.

    Fail-closed (invariant B3): a client with no entry for the provider
    may request none of that provider's scopes beyond the proxy's base
    set — callers merge base scopes separately, so an empty allowlist
    here means "no extras".

    Returns:
        The parsed, validated scope list (empty request passes as []).

    Raises:
        auth_errors.InvalidScopeError: If any requested scope is not
            in the client's allowlist for that provider.
    """
    requested_scopes = parse(requested)
    allowed = upstream_scopes.get(provider, [])
    disallowed = [
        scope for scope in requested_scopes
        if scope not in set(allowed)
    ]
    if disallowed:
        raise auth_errors.InvalidScopeError(
            f"Requested {provider} scopes not allowed for this client: "
            f"{', '.join(disallowed)}",
            provider=provider,
            disallowed_scopes=disallowed,
        )
    return requested_scopes
