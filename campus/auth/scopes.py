"""campus.auth.scopes

Scope algebra for Campus-issued tokens.

Campus tokens carry a scope list validated against the requesting
client's registered allowlist (`Client.allowed_scopes`, fail-closed).
These helpers are the single implementation of that algebra so the
session, authorization-code, and device-code paths cannot drift.

Invariants: docs/auth-token-invariants.md A1-A7.
"""

__all__ = [
    "covers",
    "parse",
    "union",
    "validate_for_client",
]

from campus.common.errors import auth_errors


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


def covers(granted: list[str], requested: list[str]) -> bool:
    """Return True if every requested scope is in the granted set."""
    return set(requested) <= set(granted)


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
