"""campus.auth.authz

Fail-closed authorization for campus.auth management blueprints (#854,
#865, #881).

Authentication (campus.auth.middleware) establishes who is calling and
pushes the principal into flask.g; this module decides what the
principal may do on the management blueprints (vaults, clients, users,
credentials). Every helper fails closed: a principal that matches no
rule is denied.

Design intent (#881): client principals hold the bare minimum access
their role needs — the vault role — which in most cases means
read-only; where a client genuinely needs write access it is granted
reviewed vault_access bitflags per label. Mutating admin actions
(registering a redirect_uri, editing registration data) must be
attributable to a user: a shared client secret cannot satisfy
accountability, so those mutations are reserved for the operator and
designated admin users (#865), never client principals.

Principals:

- Operator clients: confidential clients whose ids are listed in the
  AUTH_OPERATOR_CLIENT_IDS env var (comma-separated, read at request
  time so deployments can rotate the list without a code change). The
  operator manages every deployment resource: all vault labels, other
  clients' records and vault access, users, credentials. Fail-closed:
  an unset or empty var means the deployment has no operator at all.
- Client principals: authenticated confidential clients (HTTP Basic,
  or an app-scoped client_credentials bearer, which resolves to the
  client itself). A client is read-only on registration data (#881):
  it may read its own record and rotate its own secret (rotation is
  human-mediated by construction — the rotated secret must be written
  into the deployment env by an operator), and it may touch a vault
  label only where it holds the matching vault_access bitflag
  (campus.model.client.ClientAccess), the per-label permission model
  the /clients/{id}/access/ routes administer. Where a reviewed
  exception to read-only is granted, the rationale is recorded on the
  client's description so auditors see why.
- Designated admin users (#865): user principals designated by the
  access-grant store (#883) — a grant row for the vocabulary whose
  level covers the required management scope
  (`<resource>:<read|mod|write|admin>`, e.g. users:write) — with the
  bearer token carrying that scope. Both legs are required and
  ANDed: designation without the scope confers nothing, and scope
  without designation must never confer management authority (the
  exact regression #854 closed). The users blueprint consults the
  store exclusively (#887, DB-only: AUTH_USERS_ADMIN_USER_IDS is no
  longer read); the clients blueprint still consults the transitional
  AUTH_ADMIN_USER_IDS env list until #888 retires it. The ceiling
  stays operator-controlled end to end: a user token can carry a
  management scope only if the minting client's allowed_scopes cap
  includes it (docs/auth-token-invariants.md A1/A8). Users never
  inherit the operator role of the client they were minted through,
  and management mutations by user principals land in campus.audit
  stamped with the acting user id (#802).
- User principals (other): bearer tokens minted for an end user
  (device flow, browser sessions). They carry end-user authority only
  and are denied on every management route regardless of scope;
  blueprints whose scope vocabulary is still reserved (vaults,
  credentials) deny them outright.

Enforcement lives in the route modules (the resources must stay
ungated for in-process callers such as the OAuth proxies and the
connect flow).

The generalized gate (#883, #885): require_resource_permission backs
every vocabulary with the access-grant store — a designated user needs
a grant row AND a token scope, clients keep vault bitflags, and the
operator bypasses. The per-blueprint rollout (users first, #887)
swaps each route family onto it.
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
    "require_admin_user_or_operator",
    "require_operator",
    "require_operator_only_client_fields",
    "require_resource_permission",
    "require_self_or_operator",
    "require_vault_permission",
    "session_user_visible",
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

# Management-scope vocabulary, v1: clients (#865, still on the
# transitional env list until #888) and users (#887, store-backed).
# clients:read lists/gets any client record; clients:write updates
# benign fields on any client (name, description, redirect_uris);
# clients:admin registers, deletes, rotates secrets, sets scope caps
# (allowed_scopes, upstream_scopes, token_bridge) and administers
# vault-access grants. users:read lists/gets any user record;
# users:mod activates a user; users:write creates and updates users
# (implies mod); users:admin deletes users (implies write). The
# vaults/credentials vocabularies stay reserved (operator-only) until
# a need exists.
CLIENTS_READ = "clients:read"
CLIENTS_WRITE = "clients:write"
CLIENTS_ADMIN = "clients:admin"

# Client record fields reserved for the clients:admin scope: the scope
# caps and the token-bridge flag are operator-controlled registration
# data (docs/auth-token-invariants.md A1/B3/C1); a client-principal
# edit would let the client widen its own authority (and client
# principals may not PATCH at all post-#881).
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


def admin_user_ids(envvar: str = ADMIN_USER_IDS_ENVVAR) -> frozenset[str]:
    """Parse a designated-admin user-id allowlist (#865).

    Read at request time (not import time), exactly mirroring
    operator_client_ids: an unset or empty var means the deployment
    has no designated admins for that vocabulary.
    """
    raw = env.get(envvar) or ""
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


def session_user_visible(session_client_id: str | None) -> bool:
    """True if the current principal may see a session's embedded user (#879).

    Only the session-owning client (the app that created the session
    and drives its login flow) and the deployment operator may receive
    the user record embedded in session reads and finalization: the
    owning client needs it to hydrate the signed-in user without the
    operator-gated users routes. User bearer tokens get nothing here
    (the #854 rule — a user principal is never the session's client),
    and the users routes remain the user-facing path.
    """
    if is_user_principal() or session_client_id is None:
        return False
    client = getattr(flask.g, "current_client", None)
    if client is not None and str(client.id) == str(session_client_id):
        return True
    return is_operator()


def forbid_user_principal(action: str) -> None:
    """Reject end-user bearer tokens on management routes (#854).

    A user token's scopes (and the client it was minted through) carry
    no management authority: management routes are for the operator,
    designated admin users (#865), and the read/rotate self-service
    client principals keep (#881).

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

    The user-principal leg of the transitional clients-vocabulary
    gate (env-var identity AND token scope) — retained until #888
    moves the clients blueprint onto the access-grant store
    (#887 retired the users leg). Passes only if the caller is a
    user principal AND its id is listed in AUTH_ADMIN_USER_IDS AND
    the token's scopes cover `scope`. Neither leg alone suffices —
    scope alone must never confer management authority (#854). A
    no-op for client principals: the operator and self-service
    rules apply to them.

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


def require_admin_user_or_operator(
        admin_scope: str,
        action: str,
) -> None:
    """Require a designated admin user or the operator for `action` (#881).

    Mutating admin actions must be attributable to a user principal: a
    shared client secret cannot satisfy accountability, so client
    principals — including the client whose record is being changed —
    are denied, and the error points at the user-principal path (the
    `admin_scope` vocabulary, #865) alongside the operator. The client
    leg of this gate is what narrowed PATCH /clients/{id}/: reads and
    human-mediated secret rotation stay self-service
    (require_self_or_operator), record mutations do not.

    Raises:
        api_errors.ForbiddenError: If the caller is a client principal
            other than the operator, or a user principal failing
            either designated-admin leg (identity/capability, as
            require_admin_user).
    """
    if is_user_principal():
        require_admin_user(admin_scope, action)
        return
    if is_operator():
        return
    raise api_errors.ForbiddenError(
        f"Client principals may not {action} (#881): mutating admin "
        "actions must be attributable to a user — use a designated "
        f"admin user token with '{admin_scope}' (#865) or the operator "
        f"principal ({OPERATOR_CLIENT_IDS_ENVVAR})"
    )


def require_self_or_operator(
        client_id: str,
        action: str,
        admin_scope: str | None = None,
) -> None:
    """Require the operator principal or the named client itself.

    "Self" means the authenticated client IS the client named in the
    path: clients may act on their own record (reads and secret
    rotation — record mutations are user-attributable, #881, see
    require_admin_user_or_operator) but not on anyone else's.

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

    Called on the PATCH /clients/{id}/ path after
    require_admin_user_or_operator: client principals never reach it
    (#881 denies them on the whole route), so the live check is the
    user leg — a clients:write admin user is limited to benign fields
    (name, description, redirect_uris); only a clients:admin user (or
    the operator) may set the scope caps and the token-bridge flag.
    The client-principal branch stays as fail-closed defense in depth:
    it independently rejects a non-operator client attempting these
    fields even if a future route wires this helper without the #881
    gate.

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
            f"Client principals may not change {', '.join(attempted)}: "
            "these are operator-controlled registration fields "
            "(docs/auth-token-invariants.md A1/B3/C1)"
        )


# The vault vocabulary in the generalized gate (#885): vault rows
# carry bitflags (ClientAccess) rather than scope levels, and the
# vocabulary stays reserved for user principals until #889 pins their
# matrix.
_VAULT_RESOURCE = "vault"


def require_resource_permission(
        resource: str,
        level: str | None = None,
        instance: str | None = None,
        *,
        bits: int | None = None,
) -> None:
    """Require designated authority over a management resource (#883, #885).

    The generalized gate over the access-grant store. User principals
    are consulted first so a user never inherits the minting client's
    operator role (#854):

    - a user principal needs BOTH legs of the #865 model, identity leg
      moved to the store (umbrella decision 3): a grant row whose
      level covers `resource:level` AND a token scope covering it —
      either leg alone confers nothing. Fail-closed on a missing or
      malformed row (umbrella decision 6). On the vault vocabulary
      user bearers are denied outright, exactly as before, until #889
      pins their matrix;
    - the operator client bypasses every check;
    - any other client principal is denied on the level vocabularies
      (clients are never designated admins, #854/#865) and keeps
      bitflag semantics on vault labels (`bits`).

    Raises:
        api_errors.ForbiddenError: If the caller lacks authority.
    """
    if is_user_principal():
        if resource == _VAULT_RESOURCE:
            forbid_user_principal(f"access the vault '{instance}'")
        # Lazy import: keeps the authz module importable ahead of the
        # storage backend's test-mode initialization.
        from .resources.grant import grants

        user = flask.g.current_user
        row = grants.get(
            "user", str(user.get("id")), resource, instance or ""
        )
        held = row.get("level") if row else None
        required = f"{resource}:{level}"
        if not held or not scopes.grants([f"{resource}:{held}"], required):
            raise api_errors.ForbiddenError(
                f"No access grant designates this user for "
                f"'{required}' (#883): designated authority is "
                "administered via the access-grant store"
            )
        if not scopes.grants(_user_token_scopes(), required):
            raise api_errors.ForbiddenError(
                f"Token lacks '{required}' (#865): a designated user "
                "must hold the management scope to act on this "
                "resource"
            )
        return
    if is_operator():
        return
    if resource == _VAULT_RESOURCE:
        if bits is None:
            # Reached with no bitflag operand (e.g. an admin route
            # asking for vault authority): fail closed, not 500.
            raise api_errors.ForbiddenError(
                "Vault access requires a client principal holding "
                "the matching bitflags"
            )
        _require_vault_bitflags(instance or "", bits)
        return
    client = getattr(flask.g, "current_client", None)
    who = f"Client '{client.id}'" if client else "Client principals"
    raise api_errors.ForbiddenError(
        f"{who} hold no '{resource}' management authority (#854): "
        "management routes accept the operator, designated user "
        "grants, or the resource client itself, never other clients"
    )


def _require_vault_bitflags(label: str, bits: int) -> None:
    """Vault bitflag check for client principals (#854, unchanged).

    The caller has already settled the operator and user-principal
    legs; a client principal must hold the requested bitflag(s) for
    the label in its vault grant (administered via
    /clients/{id}/access/). A mask matches when the client holds ANY
    of its bits, so POST set accepts a client with either CREATE or
    UPDATE. Fail-closed: no grant row for the label is denied, as is
    an unauthenticated caller.

    Raises:
        api_errors.ForbiddenError: If the caller lacks the permission.
    """
    client = getattr(flask.g, "current_client", None)
    if client is None:
        raise api_errors.ForbiddenError(
            "Vault access requires a client principal"
        )
    # Lazy import: keeps the authz module importable ahead of the
    # storage backend's test-mode initialization.
    from .resources import client as client_resource

    held = client_resource[client.id].access.get(label)
    if not held & bits:
        raise api_errors.ForbiddenError(
            f"Client '{client.id}' lacks {_describe_bitflags(bits)} "
            f"access to vault '{label}': grant it via "
            f"/clients/{client.id}/access/ as the operator"
        )


def require_vault_permission(label: str, permission: int) -> None:
    """Require vault_access permission on a vault label (#854).

    Thin wrapper over require_resource_permission (#885), behavior
    identical: the operator client bypasses the bitflag check; user
    bearer tokens are denied outright (checked first, so a user never
    inherits the minting client's operator role); any other client
    principal must hold the requested bitflag(s) for the label in its
    vault grant.

    Raises:
        api_errors.ForbiddenError: If the caller lacks the permission.
    """
    require_resource_permission(
        _VAULT_RESOURCE, instance=label, bits=permission
    )
