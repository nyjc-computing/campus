"""campus.auth.authz

Fail-closed authorization for campus.auth management blueprints (#854,
#865).

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
- Designated admin users (#865): user principals whose ids are listed
  in the AUTH_ADMIN_USER_IDS env var (comma-separated, read at request
  time, mirroring AUTH_OPERATOR_CLIENT_IDS) and whose bearer token
  carries the required management scope
  (`<resource>:<read|write|admin>`, e.g. clients:write). Both legs are
  required and ANDed: designation without the scope confers nothing,
  and scope without designation must never confer management authority
  (the exact regression #854 closed). Unset/empty means the deployment
  has no user admins. The ceiling stays operator-controlled end to
  end: a user token can carry clients:* only if the minting client's
  allowed_scopes cap includes them (docs/auth-token-invariants.md
  A1/A8). Users never inherit the operator role of the client they
  were minted through, and management mutations by user principals
  land in campus.audit stamped with the acting user id (#802).
- User principals (other): bearer tokens minted for an end user
  (device flow, browser sessions). They carry end-user authority only
  and are denied on every management route regardless of scope;
  blueprints whose scope vocabulary is still reserved (vaults, users,
  credentials) deny them outright.

Enforcement lives in the route modules (the resources must stay
ungated for in-process callers such as the OAuth proxies and the
connect flow).
"""

__all__ = [
    "CLIENTS_ADMIN",
    "CLIENTS_READ",
    "CLIENTS_WRITE",
    "admin_user_ids",
    "forbid_user_principal",
    "has_admin_scope",
    "is_operator",
    "operator_client_ids",
    "require_admin_user",
    "require_operator",
    "require_operator_only_client_fields",
    "require_self_or_operator",
    "require_vault_permission",
]

import flask

from campus.common import env
from campus.common.errors import api_errors
from campus.model.client import ClientAccess

from . import scopes

# Comma-separated client ids granted the operator role on the management
# blueprints (vaults, clients, users, credentials). Configure per
# deployment (e.g. the campus-admin portal's client); unset means no
# principal may manage the deployment.
OPERATOR_CLIENT_IDS_ENVVAR = "AUTH_OPERATOR_CLIENT_IDS"

# Comma-separated user ids granted limited management authority (#865).
# A listed user still needs the matching management scope on its token;
# unset or empty means the deployment has no user admins.
ADMIN_USER_IDS_ENVVAR = "AUTH_ADMIN_USER_IDS"

# Management-scope vocabulary, v1: clients only (#865). clients:read
# unlocks list/get of any client record; clients:write updates benign
# fields on any client (name, description, redirect_uris); clients:admin
# registers, deletes, rotates secrets, sets scope caps (allowed_scopes,
# upstream_scopes, token_bridge) and administers vault-access grants.
# The vaults/users/credentials vocabularies stay reserved
# (operator-only) until a need exists.
CLIENTS_READ = "clients:read"
CLIENTS_WRITE = "clients:write"
CLIENTS_ADMIN = "clients:admin"

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


def admin_user_ids() -> frozenset[str]:
    """Parse the designated-admin user-id allowlist (#865).

    Read at request time (not import time), exactly mirroring
    operator_client_ids: an unset or empty var means the deployment
    has no user admins.
    """
    raw = env.get(ADMIN_USER_IDS_ENVVAR) or ""
    return frozenset({
        user_id.strip()
        for user_id in raw.split(",")
        if user_id.strip()
    })


def is_operator() -> bool:
    """Return True if the authenticated client is a deployment operator.

    Only meaningful for client principals: user bearers set
    current_client to the client they were minted through, and the
    require_* helpers therefore always consult user principals first
    so a user never inherits the minting client's operator role (#854).
    """
    client = getattr(flask.g, "current_client", None)
    return client is not None and str(client.id) in operator_client_ids()


def is_user_principal() -> bool:
    """Return True if the request authenticated as a user bearer."""
    return getattr(flask.g, "current_user", None) is not None


def _user_token_scopes() -> list[str]:
    """Scopes granted to the authenticated user's bearer token.

    Empty for client principals (they hold no token scopes) and for
    tokens authenticated without their token record — fail-closed.
    """
    user = getattr(flask.g, "current_user", None)
    if not isinstance(user, dict):
        return []
    return list(user.get("scopes") or [])


def has_admin_scope(required: str) -> bool:
    """True if the caller is a designated admin user (#865) whose
    token carries a scope conferring `required`.

    Both legs ANDed, fail-closed: a client principal (or a user
    principal with no scopes visible) never satisfies this.
    """
    if not is_user_principal():
        return False
    user = flask.g.current_user
    return (
        str(user.get("id")) in admin_user_ids()
        and scopes.grants(_user_token_scopes(), required)
    )


def forbid_user_principal(action: str) -> None:
    """Reject end-user bearer tokens on management routes (#854).

    A user token's scopes (and the client it was minted through) carry
    no management authority: management routes are for the operator
    and self-managing clients only.

    Retained for the blueprints whose management-scope vocabulary is
    reserved (#865): vaults, users, credentials.
    """
    if is_user_principal():
        raise api_errors.ForbiddenError(
            f"User access tokens cannot {action} (#854): management "
            "routes accept the deployment operator client or the "
            "resource client itself, never user tokens"
        )


def require_admin_user(scope: str, action: str) -> None:
    """Require a designated admin user token carrying `scope` (#865).

    The user-principal leg of the clients management gates: passes
    only if the caller is a user principal AND its id is listed in
    AUTH_ADMIN_USER_IDS AND the token's scopes cover `scope`. Neither
    leg alone suffices — scope alone must never confer management
    authority (#854). A no-op for client principals: the operator and
    self-service rules apply to them.

    Raises:
        api_errors.ForbiddenError: Distinguishing the failed leg —
            "not a designated admin" (identity) vs "token lacks
            `<scope>`" (capability).
    """
    if not is_user_principal():
        return
    user = flask.g.current_user
    if str(user.get("id")) not in admin_user_ids():
        raise api_errors.ForbiddenError(
            f"Only designated admin users may {action} (#865): this "
            f"user id is not listed in {ADMIN_USER_IDS_ENVVAR} on the "
            "campus.auth deployment"
        )
    if not scopes.grants(_user_token_scopes(), scope):
        raise api_errors.ForbiddenError(
            f"Token lacks '{scope}' (#865): designated admin users "
            f"must hold the '{scope}' management scope to {action}"
        )


def require_operator(action: str, admin_scope: str | None = None) -> None:
    """Require the operator principal for the given action.

    User principals are denied unless the action opens a
    management-scope vocabulary (#865): with `admin_scope` set, a
    designated admin user whose token carries that scope may also act
    (e.g. register clients with clients:admin).

    Raises:
        api_errors.ForbiddenError: If the caller is an unauthorized
            user principal or a non-operator client.
    """
    if is_user_principal():
        if admin_scope is None:
            forbid_user_principal(action)
        else:
            require_admin_user(admin_scope, action)
        return
    if not is_operator():
        raise api_errors.ForbiddenError(
            f"Only the operator principal may {action}: add the "
            f"caller's client id to {OPERATOR_CLIENT_IDS_ENVVAR} "
            "on the campus.auth deployment"
        )


def require_self_or_operator(
        client_id: str,
        action: str,
        admin_scope: str | None = None,
) -> None:
    """Require the operator principal or the named client itself.

    "Self" means the authenticated client IS the client named in the
    path: clients may manage their own record but not anyone else's.

    User principals are denied unless the action opens a
    management-scope vocabulary (#865): with `admin_scope` set, a
    designated admin user whose token carries that scope may act on
    any client's record (e.g. view with clients:read).

    Raises:
        api_errors.ForbiddenError: If the caller is an unauthorized
            user principal or a non-operator client acting on another
            client.
    """
    if is_user_principal():
        if admin_scope is None:
            forbid_user_principal(action)
        else:
            require_admin_user(admin_scope, action)
        return
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
    """Reject operator-only field edits by non-admin principals.

    Called on the PATCH /clients/{id}/ self-management path after
    require_self_or_operator: a client renaming itself or registering
    its own redirect URIs is fine, but the scope caps and the
    token-bridge flag are operator-controlled. The operator client may
    set them, and so may a designated admin user whose token carries
    clients:admin (#865) — a clients:write admin user is still limited
    to benign fields.

    Raises:
        api_errors.ForbiddenError: If any operator-only field is
            present and the caller may not set it.
    """
    # User principals are checked first: a user bearer minted through
    # the operator client must not inherit the operator's field
    # authority (#854) — only the clients:admin scope grants it (#865).
    if is_user_principal():
        if has_admin_scope(CLIENTS_ADMIN):
            return
        attempted = [
            field for field in _OPERATOR_ONLY_CLIENT_FIELDS
            if updates.get(field) is not None
        ]
        if attempted:
            raise api_errors.ForbiddenError(
                f"Changing {', '.join(attempted)} requires the "
                f"'{CLIENTS_ADMIN}' management scope (#865) or the "
                "operator principal: these are operator-controlled "
                "registration fields "
                "(docs/auth-token-invariants.md A1/B3/C1)"
            )
        return
    if is_operator():
        return
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
