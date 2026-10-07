"""campus.auth.authz

Fail-closed authorization for campus.auth management blueprints (#854).

Authentication (campus.auth.middleware) establishes who is calling and
pushes the principal into flask.g; this module decides what the
principal may do on the management blueprints (vaults, clients, users,
credentials). Every helper fails closed: a principal that matches no
rule is denied.

Principals:

- Operator clients: confidential clients whose ids are listed in the
  AUTH_OPERATOR_CLIENT_IDS env var (comma-separated, read at request
  time so deployments can rotate the list without a code change). The
  operator manages every deployment resource: all vault labels, other
  clients' records and vault access, users, credentials. Fail-closed:
  an unset or empty var means the deployment has no operator at all.
- Client principals: authenticated confidential clients (HTTP Basic,
  or an app-scoped client_credentials bearer, which resolves to the
  client itself). A client may manage only itself — read its record,
  update its profile fields, rotate its own secret — and may touch a
  vault label only where it holds the matching vault_access bitflag
  (campus.model.client.ClientAccess), the per-label permission model
  the /clients/{id}/access/ routes administer.
- User principals: bearer tokens minted for an end user (device flow,
  browser sessions). These carry end-user authority only: they get
  nothing on the management routes regardless of their scopes, and
  never inherit the operator role of the client they were minted
  through (#854).

Enforcement lives in the route modules (the resources must stay
ungated for in-process callers such as the OAuth proxies and the
connect flow).
"""

__all__ = [
    "forbid_user_principal",
    "is_operator",
    "operator_client_ids",
    "require_operator",
    "require_self_or_operator",
    "require_vault_permission",
]

import flask

from campus.common import env
from campus.common.errors import api_errors
from campus.model.client import ClientAccess

# Comma-separated client ids granted the operator role on the management
# blueprints (vaults, clients, users, credentials). Configure per
# deployment (e.g. the campus-admin portal's client); unset means no
# principal may manage the deployment.
OPERATOR_CLIENT_IDS_ENVVAR = "AUTH_OPERATOR_CLIENT_IDS"

# Client record fields a client may NOT change on itself: the scope
# caps and the token-bridge flag are operator-controlled registration
# data (docs/auth-token-invariants.md A1/B3/C1); self-service edits
# would let a client widen its own authority.
_OPERATOR_ONLY_CLIENT_FIELDS = (
    "allowed_scopes",
    "upstream_scopes",
    "token_bridge",
)

_BITFLAG_NAMES = {
    ClientAccess.READ: "READ",
    ClientAccess.CREATE: "CREATE",
    ClientAccess.UPDATE: "UPDATE",
    ClientAccess.DELETE: "DELETE",
}


def _describe_bitflags(mask: int) -> str:
    """Render a permission bitflag mask as a human-readable name list."""
    names = [
        name
        for bit, name in _BITFLAG_NAMES.items()
        if mask & bit
    ]
    return " or ".join(names) if names else str(mask)


def operator_client_ids() -> frozenset[str]:
    """Parse the operator client-id allowlist from the environment.

    Read at request time (not import time) so deployments and tests
    can change the list without a process restart.
    """
    raw = env.get(OPERATOR_CLIENT_IDS_ENVVAR) or ""
    return frozenset({
        client_id.strip()
        for client_id in raw.split(",")
        if client_id.strip()
    })


def is_operator() -> bool:
    """Return True if the authenticated client is a deployment operator."""
    client = getattr(flask.g, "current_client", None)
    return client is not None and str(client.id) in operator_client_ids()


def forbid_user_principal(action: str) -> None:
    """Reject end-user bearer tokens on management routes (#854).

    A user token's scopes (and the client it was minted through) carry
    no management authority: management routes are for the operator
    and self-managing clients only.
    """
    if getattr(flask.g, "current_user", None) is not None:
        raise api_errors.ForbiddenError(
            f"User access tokens cannot {action} (#854): management "
            "routes accept the deployment operator client or the "
            "resource client itself, never user tokens"
        )


def require_operator(action: str) -> None:
    """Require the operator principal for the given action.

    Raises:
        api_errors.ForbiddenError: If the caller is a user principal or
            a non-operator client.
    """
    forbid_user_principal(action)
    if not is_operator():
        raise api_errors.ForbiddenError(
            f"Only the operator principal may {action}: add the "
            f"caller's client id to {OPERATOR_CLIENT_IDS_ENVVAR} "
            "on the campus.auth deployment"
        )


def require_self_or_operator(client_id: str, action: str) -> None:
    """Require the operator principal or the named client itself.

    "Self" means the authenticated client IS the client named in the
    path: clients may manage their own record but not anyone else's.

    Raises:
        api_errors.ForbiddenError: If the caller is a user principal or
            a non-operator client acting on another client.
    """
    forbid_user_principal(action)
    if is_operator():
        return
    client = getattr(flask.g, "current_client", None)
    if client is not None and str(client.id) == str(client_id):
        return
    raise api_errors.ForbiddenError(
        f"Clients may not {action} another client's record; only the "
        f"operator principal ({OPERATOR_CLIENT_IDS_ENVVAR}) can"
    )


def require_operator_only_client_fields(updates: dict) -> None:
    """Reject operator-only field edits by a self-managing client.

    Called on the PATCH /clients/{id}/ self-management path after
    require_self_or_operator: a client renaming itself or registering
    its own redirect URIs is fine, but the scope caps and the
    token-bridge flag are operator-controlled.

    Raises:
        api_errors.ForbiddenError: If any operator-only field is present.
    """
    attempted = [
        field for field in _OPERATOR_ONLY_CLIENT_FIELDS
        if updates.get(field) is not None
    ]
    if attempted:
        raise api_errors.ForbiddenError(
            f"Self-management may not change {', '.join(attempted)}: "
            "these are operator-controlled registration fields "
            "(docs/auth-token-invariants.md A1/B3/C1)"
        )


def require_vault_permission(label: str, permission: int) -> None:
    """Require vault_access permission on a vault label (#854).

    Authorization model for the vaults blueprint:

    - the operator client bypasses the bitflag check;
    - user bearer tokens are denied outright;
    - any other client principal must hold the requested bitflag(s)
      for the label in its vault_access records (the permission model
      administered via /clients/{id}/access/). A mask matches when the
      client holds ANY of its bits, so POST set accepts a client with
      either CREATE or UPDATE.

    Fail-closed: a client with no vault_access record for the label is
    denied, as is a deployment with no operator configured.

    Raises:
        api_errors.ForbiddenError: If the caller lacks the permission.
    """
    forbid_user_principal(f"access the vault '{label}'")
    if is_operator():
        return
    client = getattr(flask.g, "current_client", None)
    if client is None:
        raise api_errors.ForbiddenError(
            "Vault access requires a client principal"
        )
    # Lazy import: keeps the authz module importable ahead of the
    # storage backend's test-mode initialization.
    from .resources import client as client_resource

    held = client_resource[client.id].access.get(label)
    if not held & permission:
        raise api_errors.ForbiddenError(
            f"Client '{client.id}' lacks {_describe_bitflags(permission)} "
            f"access to vault '{label}': grant it via "
            f"/clients/{client.id}/access/ as the operator"
        )
