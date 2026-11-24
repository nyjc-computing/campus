"""campus.auth.authz

Fail-closed authorization for campus.auth management blueprints (#854,
#865, #881).

Authentication (campus.auth.middleware) establishes who is calling and
pushes the principal into flask.g; this module decides what the
principal may do on the management blueprints (vaults, clients, users,
credentials, sessions). Every helper fails closed: a principal that
matches no rule is denied.

Scope boundary (ratified 2026-11-06): the grant store authorizes these
management blueprints only. Domain-resource authorization lives in
campus.api (circle-backed, `campus/api/authz.py`) and never consults
this store.

Design intent (#881): client principals hold the bare minimum access
their role needs — the vault role — which in most cases means
read-only; where a client genuinely needs write access it is granted
reviewed vault_access bitflags per label. Mutating admin actions
(registering a redirect_uri, editing registration data) must be
attributable to a user: a shared client secret cannot satisfy
accountability, so those mutations are reserved for the operator and
designated admin users (#865), never client principals.

Principals:

- Super-admin root (#897, decision 8): the single user account
  configured as the super-admin (matched by account email), holding
  full privileges on every resource with no grant rows and no
  token-scope requirement — the human break-glass root, used
  primarily to seed sub-admin grants. On ENV=production the identity
  is hardcoded to campus-admin@<WORKSPACE_DOMAIN> (2026-11-24
  decision; AUTH_SUPER_ADMIN is not consulted there) and its
  interactive login is blocked on every other environment
  (assert_login_allowed); elsewhere it is nominated via
  AUTH_SUPER_ADMIN. Authority comes from the
  account's own identity, never from the minting client; the
  clients:admin grant-shape rejection still applies to it.
- Operator clients: confidential clients whose ids are listed in the
  AUTH_OPERATOR_CLIENT_IDS env var (comma-separated, read at request
  time so deployments can rotate the list without a code change). The
  operator manages every deployment resource: all vault labels and
  their enumeration, other clients' records and vault access, users,
  credentials, sessions. Fail-closed: an unset or empty var means
  the deployment has no operator at all.
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
  exact regression #854 closed). Both the users (#887) and clients
  (#888) blueprints consult the store exclusively — the
  AUTH_ADMIN_USER_IDS / AUTH_USERS_ADMIN_USER_IDS env lists are no
  longer read at request time (DB-only ruling, umbrella decision 3).
  The clients vocabulary is grantable up to clients:write: a
  vocabulary-level clients:admin row is operator-equivalent and is
  rejected by the grant routes (decision 4), so clients:admin-level
  actions are operator-only by construction. The vaults vocabulary
  grants per-label user access at read/write/admin (#889), but
  administering vault GRANTS stays operator-only. The ceiling stays
  operator-controlled end to end: a user token can carry a
  management scope only if the minting client's allowed_scopes cap
  includes it (docs/auth-token-invariants.md A1/A8). Users never
  inherit the operator role of the client they were minted through,
  and management mutations by user principals land in campus.audit
  stamped with the acting user id (#802).
- User principals (other): bearer tokens minted for an end user
  (device flow, browser sessions). They carry end-user authority only
  and are denied on every management route regardless of scope,
  except per-label vault access via grant rows and vaults:* scopes
  (#889), label enumeration for holders of any vault grant
  (#1055), and the sessions/credentials vocabularies (#1055,
  store-backed: a grant row AND the scope, like every vocabulary).

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
    "CREDENTIALS_READ",
    "CREDENTIALS_WRITE",
    "GRANT_CHECK_CLIENT_IDS_ENVVAR",
    "MIGRATIONS_ADMIN",
    "MIGRATIONS_READ",
    "MIGRATIONS_WRITE",
    "SESSIONS_READ",
    "SESSIONS_WRITE",
    "SUPER_ADMIN_LOCALPART",
    "assert_login_allowed",
    "forbid_user_principal",
    "grant_check_client_ids",
    "has_admin_scope",
    "is_grant_check_caller",
    "is_operator",
    "is_super_admin",
    "operator_client_ids",
    "require_admin_user",
    "require_admin_user_or_operator",
    "require_operator",
    "require_operator_only_client_fields",
    "require_resource_permission",
    "require_self_or_operator",
    "require_session_access",
    "require_vault_enumeration",
    "require_vault_permission",
    "session_user_visible",
    "super_admin_email",
]

import logging

import flask

from campus.common import env
from campus.common.errors import api_errors
from campus.model.client import ClientAccess

from . import scopes

logger = logging.getLogger(__name__)

# Comma-separated client ids granted the operator role on the management
# blueprints (vaults, clients, users, credentials). Configure per
# deployment (e.g. the campus-admin portal's client); unset means no
# principal may manage the deployment.
OPERATOR_CLIENT_IDS_ENVVAR = "AUTH_OPERATOR_CLIENT_IDS"

# The super-admin root account (#897, decision 8): one user account
# holding full privileges on every resource with no grant rows and no
# token-scope requirement — the identity leg alone suffices. Its
# primary use is seeding sub-admin grants via /grants/.
#
# On ENV=production the identity is hardcoded (2026-11-24 decision):
# campus-admin@<WORKSPACE_DOMAIN> — the local part is fixed in code
# below and the domain comes from WORKSPACE_DOMAIN, so no env
# nomination is consulted and AUTH_SUPER_ADMIN is not required on
# production deployments. Elsewhere (development/test) the account is
# nominated via AUTH_SUPER_ADMIN, read at request time; the value is
# the account email. The hardcoded identity's interactive login is
# blocked outside production — see assert_login_allowed.
SUPER_ADMIN_ENVVAR = "AUTH_SUPER_ADMIN"

# Fixed local part of the production super-admin identity: the
# break-glass root on the deployment's Google Workspace domain.
SUPER_ADMIN_LOCALPART = "campus-admin"

# Management-scope vocabulary, v1: clients (#888, store-backed;
# grantable up to write — admin rows are operator-equivalent,
# umbrella decision 4) and users (#887, store-backed).
# clients:read lists/gets any client record; clients:write updates
# benign fields on any client (name, description, redirect_uris);
# clients:admin registers, deletes, rotates secrets, sets scope caps
# (allowed_scopes, upstream_scopes, token_bridge) and administers
# vault-access grants. users:read lists/gets any user record;
# users:mod activates a user; users:write creates and updates users
# (implies mod); users:admin deletes users (implies write). The
# sessions vocabulary (#1055, store-backed, grantable up to write —
# no admin-level session actions exist) opens the session admin
# surface: sessions:read enumerates and reads session metadata,
# sessions:write revokes. The credentials vocabulary opens with the
# same shape in #1055: credentials:read reads credential records,
# credentials:write disconnects/updates them. Vault rows grant
# per-label user access at read/write/admin (#889), but
# administering vault GRANTS stays operator-only. The ceiling stays
# operator-controlled end to end: a user token can carry a
# management scope only if the minting client's allowed_scopes cap
# includes it (docs/auth-token-invariants.md A1/A8). Users never
# inherit the operator role of the client they were minted through,
# and management mutations by user principals land in campus.audit
# stamped with the acting user id (#802).
CLIENTS_READ = "clients:read"
CLIENTS_WRITE = "clients:write"
CLIENTS_ADMIN = "clients:admin"

# Sessions vocabulary (#1055): the campus-admin sessions view. read
# enumerates sessions (GET /sessions/) and reads per-id metadata;
# write revokes (the DELETE route, distinct from the owning client's
# flow-finalize by the audit event). Grantable up to write; admin
# rows are rejected as inert (nothing sits above revoke), so grant
# administration for the vocabulary stays operator-only.
SESSIONS_READ = "sessions:read"
SESSIONS_WRITE = "sessions:write"

# Credentials vocabulary (#1055): the campus-admin credentials view.
# read lists/reads credential records — metadata only by default,
# the raw token requires the operator principal and an explicit
# ?include=token opt-in on per-record reads. write disconnects
# (DELETE, optionally against an arbitrary client's record) and
# updates. Grantable up to write; credentials:admin rows are
# rejected as inert (nothing sits above write), so grant
# administration for the vocabulary stays operator-only.
CREDENTIALS_READ = "credentials:read"
CREDENTIALS_WRITE = "credentials:write"

# Timetable vocabulary: the NYXchange timetable resource (v2 upload
# gate and the #124 processing flow). read views timetable data;
# write creates/updates timetable versions and replaces the special
# timetable files; admin governs the vocabulary's grants — the level
# the timetable upload endpoint gates on. mod rows are rejected as
# inert (no moderation action exists on timetables).
TIMETABLE_READ = "timetable:read"
TIMETABLE_WRITE = "timetable:write"
TIMETABLE_ADMIN = "timetable:admin"

# Migrations vocabulary (#1168): the campus-admin Migrations view and
# the per-service migration management routes (#1169). read views the
# plan delta and ledger history; write triggers apply and abort
# (implies read); admin rolls back / restores from backup (implies
# write) — the destructive cap, granted sparingly. Rows are
# instance-scoped by service DB (#1104): resource_id names the service
# ("auth", "api" or "audit"), so authority covers one service's
# migration surface, never the whole fleet (the ratified subsets
# ruling). mod rows are rejected as inert, and there are no
# vocabulary-level migration rows — grant administration for the
# vocabulary stays operator-only by construction.
MIGRATIONS_READ = "migrations:read"
MIGRATIONS_WRITE = "migrations:write"
MIGRATIONS_ADMIN = "migrations:admin"

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


def _production_super_admin_email() -> str | None:
    """The hardcoded production super-admin email (2026-11-24 decision).

    campus-admin@<WORKSPACE_DOMAIN>: the local part is fixed and the
    domain comes from the deployment's WORKSPACE_DOMAIN. An unset or
    empty domain means no super-admin root (fail-closed), mirroring the
    unset-env case.
    """
    domain = (env.get("WORKSPACE_DOMAIN") or "").strip()
    if not domain:
        return None
    return f"{SUPER_ADMIN_LOCALPART}@{domain}"


def super_admin_email() -> str | None:
    """The super-admin account email, if one is configured.

    ENV=production: hardcoded to campus-admin@<WORKSPACE_DOMAIN>
    (2026-11-24 decision) — AUTH_SUPER_ADMIN is not consulted there.

    Other environments: the AUTH_SUPER_ADMIN env nomination, read at
    request time (not import time) mirroring operator_client_ids;
    unset or empty means the deployment has no super-admin root.
    """
    if env.ENV == env.PRODUCTION:
        return _production_super_admin_email()
    raw = env.get(SUPER_ADMIN_ENVVAR) or ""
    return raw.strip() or None


def assert_login_allowed(email: str) -> None:
    """Reject an interactive login as the hardcoded super-admin
    identity outside production (2026-11-24 decision).

    campus-admin@<WORKSPACE_DOMAIN> may only authenticate on
    ENV=production — the one environment where it holds root
    authority. On ENV=development (the default when ENV is unset) its
    login is refused with a 403 and a server-side warning, so the
    break-glass identity can never mint credentials on a lower
    environment. Call at every identity acceptance point: the Google
    consent callback (the hop every login flow shares), verify_login,
    and the device-flow bind.

    Raises:
        api_errors.ForbiddenError: If `email` names the hardcoded
            super-admin identity and the deployment is not production.
    """
    if env.ENV == env.PRODUCTION:
        return
    blocked = _production_super_admin_email()
    if blocked and str(email).strip().lower() == blocked.lower():
        logger.warning(
            "Blocked login attempt as the production super-admin "
            "identity '%s' on ENV=%s", blocked, env.ENV,
        )
        raise api_errors.ForbiddenError(
            f"Login is blocked for '{blocked}' on this environment: "
            "that account is reserved as the production super-admin "
            "(break-glass) identity; sign in with your own account"
        )


# Client ids allowed to use the migrations leg of GET /grants/check
# (#1168): the deployment's api/audit services settle the designation
# leg of their migration management routes (#1169) there — the grant
# store lives only in campus.auth's database, so the other services
# cannot check it directly. Scoped to migrations checks only; every
# other vocabulary keeps the operator/admin gate. Fail-closed: unset
# or empty means no client may use this leg.
GRANT_CHECK_CLIENT_IDS_ENVVAR = "AUTH_GRANT_CHECK_CLIENT_IDS"


def grant_check_client_ids() -> frozenset[str]:
    """Parse the migrations grant-check allowlist from the environment.

    Read at request time (not import time), mirroring
    operator_client_ids: deployments rotate the list without a process
    restart.
    """
    raw = env.get(GRANT_CHECK_CLIENT_IDS_ENVVAR) or ""
    return frozenset({
        client_id.strip()
        for client_id in raw.split(",")
        if client_id.strip()
    })


def is_grant_check_caller() -> bool:
    """True if the authenticated client may settle migrations checks.

    Only meaningful for client principals (the calling service's own
    client credentials), like is_operator.
    """
    client = getattr(flask.g, "current_client", None)
    return (client is not None
            and str(client.id) in grant_check_client_ids())


def is_super_admin() -> bool:
    """True if the caller is the configured super-admin (#897).

    Authority comes from the account's own identity — never from the
    client it was minted through — so this is only meaningful for
    user principals and is matched against the principal's record
    email (enriched at authentication time). Fail-closed: no
    configured super-admin email (unset AUTH_SUPER_ADMIN outside
    production, or no WORKSPACE_DOMAIN on production) or no email on
    the principal means no root.
    """
    if not is_user_principal():
        return False
    email = super_admin_email()
    if email is None:
        return False
    user = flask.g.current_user
    return str(user.get("email") or "") == email


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
    """True if the caller is a designated admin user (#865/#888)
    whose grant row and token both cover `required`.

    Both legs ANDed, fail-closed: a client principal (or a user
    principal failing either leg) never satisfies this.
    """
    if not is_user_principal():
        return False
    if is_super_admin():
        return True
    resource, _, level = required.partition(":")
    try:
        _require_user_designation(resource, level)
    except api_errors.ForbiddenError:
        return False
    return True


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
    if session_client_id is None:
        return False
    if is_user_principal():
        return is_super_admin()
    client = getattr(flask.g, "current_client", None)
    if client is not None and str(client.id) == str(session_client_id):
        return True
    return is_operator()


def require_session_access(
        session_client_id: str | None,
        action: str,
        admin_scope: str | None = None,
) -> None:
    """Require authority over a single auth session (#1055).

    The per-id session routes are flow surface, not open reads: the
    session-owning client drives its own login flow (create, read,
    bind, finalize), the deployment operator administers every
    session, and — when `admin_scope` names a management vocabulary —
    a designated admin user whose grant row and token cover it
    (#865). Every other principal is denied: session records carry the
    embedded user (#879) and flow material such as the authorization
    code, and before #1055 any authenticated bearer could read and
    finalize a session it had merely learned the id of (the same gap
    class #854 closed on the other management blueprints).

    Args:
        session_client_id: The session record's client_id (the client
            that created it); ownership is decided against the
            authenticated client principal. User principals are never
            a session's owning client (#854).
        action: Verb phrase for error messages.
        admin_scope: Optional management scope opening the route to
            designated admin users (e.g. a sessions vocabulary level).

    Raises:
        api_errors.ForbiddenError: If the caller lacks authority.
    """
    if not is_user_principal():
        client = getattr(flask.g, "current_client", None)
        if client is not None and str(client.id) == str(session_client_id):
            return
    require_operator(action, admin_scope=admin_scope)


def forbid_user_principal(action: str) -> None:
    """Reject end-user bearer tokens on management routes (#854).

    A user token's scopes (and the client it was minted through) carry
    no management authority: management routes are for the operator,
    designated admin users (#865), and the read/rotate self-service
    client principals keep (#881).

    Retained where no vocabulary leg exists — the logins blueprint —
    and as fail-closed defense in depth on the routes that do open a
    leg. The vaults (#889) and sessions/credentials (#1055)
    vocabularies have since opened their own user-principal legs;
    this helper no longer speaks for them.
    """
    if is_user_principal():
        raise api_errors.ForbiddenError(
            f"User access tokens cannot {action} (#854): management "
            "routes accept the deployment operator client or the "
            "resource client itself, never user tokens"
        )


def require_admin_user(scope: str, action: str) -> None:
    """Require a designated admin user token carrying `scope` (#865).

    The user-principal designation leg, store-backed since #888: the
    identity leg is a grant row in the access-grant store (#883)
    whose level covers `scope`, AND the bearer token must carry it.
    Neither leg alone suffices — scope alone must never confer
    management authority (#854). A no-op for client principals: the
    operator and self-service rules apply to them.

    Raises:
        api_errors.ForbiddenError: Distinguishing the failed leg —
            "no access grant designates this user" (identity) vs
            "token lacks `<scope>`" (capability).
    """
    if not is_user_principal():
        return
    if is_super_admin():
        return
    resource, _, level = scope.partition(":")
    _require_user_designation(resource, level)


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
        if is_super_admin():
            return
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
        if is_super_admin():
            return
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
        if is_super_admin():
            return
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


def _require_user_designation(
        resource: str,
        level: str,
        instance: str = "",
) -> None:
    """The two-leg designation check for the current user principal.

    Identity leg: a grant row in the access-grant store (#883) whose
    level covers `resource:level`. Capability leg: the bearer token
    carries it. Either leg alone fails with a message naming the
    failed leg. Fail-closed on missing or malformed rows (umbrella
    decision 6).

    Raises:
        api_errors.ForbiddenError: On a failed leg.
    """
    # Lazy import: keeps the authz module importable ahead of the
    # storage backend's test-mode initialization.
    from .resources.grant import grants

    user = flask.g.current_user
    row = grants.get("user", str(user.get("id")), resource, instance)
    held = row.get("level") if row else None
    vocabulary = _scope_name(resource)
    required = f"{vocabulary}:{level}"
    if not held or not scopes.grants([f"{vocabulary}:{held}"], required):
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


# The vault vocabulary in the generalized gate (#885): vault rows
# carry bitflags (ClientAccess) for client principals. Since #889,
# user principals access vault labels through per-label grant rows
# and vaults:* token scopes, with the umbrella decision-1 mapping
# READ->read, CREATE|UPDATE->write, DELETE/ALL->admin (the
# destructive bit caps the level; mod is unused for vaults).
_VAULT_RESOURCE = "vault"


# Store resource_type -> management-scope name: the vault resource
# is scoped as "vaults:*" on tokens (#889); every other vocabulary
# shares its store name.
_SCOPE_RESOURCE_NAMES = {
    _VAULT_RESOURCE: "vaults",
}


def _scope_name(resource: str) -> str:
    """The token-scope vocabulary name for a store resource_type."""
    return _SCOPE_RESOURCE_NAMES.get(resource, resource)


def _bits_to_level(bits: int) -> str:
    """The minimum vault scope level covering a bitflag mask (#889)."""
    from campus.model.client import ClientAccess

    if bits & ClientAccess.DELETE:
        return "admin"
    if bits & (ClientAccess.CREATE | ClientAccess.UPDATE):
        return "write"
    return "read"


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
      with one carve-out: a client may hold a **read-level** grant row
      (#1226 — the users directory facade forwards its queries under
      the api service's credential, and the acting person is
      attributed one layer up at the facade). Clients never reach
      mod/write/admin here: mutation attribution stays person-only
      (#854/#865). Clients keep bitflag semantics on vault labels
      (`bits`).

    Raises:
        api_errors.ForbiddenError: If the caller lacks authority.
    """
    if is_user_principal():
        if is_super_admin():
            return
        assert level is not None  # gates always name a level
        _require_user_designation(resource, level, instance or "")
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
    # The read-level client carve-out (#1226): one leg — clients
    # authenticate by credential (HTTP Basic), so there is no
    # token-scope leg; the credential plus an operator-administered
    # grant row is the assurance, the same structure as the vault
    # bitflag path.
    if level == "read":
        client = getattr(flask.g, "current_client", None)
        if client is not None:
            from .resources.grant import grants

            if grants.check(
                "client", str(client.id), resource, level="read"
            ):
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

    Thin wrapper over require_resource_permission (#885; user legs
    since #889): the operator client bypasses; a user principal needs
    a per-label vault grant row whose level covers the mapped level
    (READ->read, CREATE|UPDATE->write, DELETE->ALL->admin) AND a
    vaults:* token scope — checked first, so a user never inherits
    the minting client's operator role (#854); any other client
    principal must hold the requested bitflag(s) for the label in its
    vault grant.

    Raises:
        api_errors.ForbiddenError: If the caller lacks the permission.
    """
    require_resource_permission(
        _VAULT_RESOURCE,
        level=_bits_to_level(permission),
        instance=label,
        bits=permission,
    )


def require_vault_enumeration() -> None:
    """Require authority to enumerate vault labels (#1055).

    Labels themselves are not secret — per-label keys() has been
    grantable since #854 — but enumerating the deployment's label
    list is an administrative view. Allowed: the operator client,
    the super-admin root, and a user principal holding ANY per-label
    vault grant row (#889) whose token carries vaults:read. Client
    principals stay per-label (#881 minimal read): bitflag holders
    keep keys()/get/set/delete on their labels but cannot enumerate
    the label list.

    Raises:
        api_errors.ForbiddenError: If the caller lacks authority.
    """
    if is_user_principal():
        if is_super_admin():
            return
        # Lazy import: keeps the authz module importable ahead of the
        # storage backend's test-mode initialization.
        from .resources.grant import grants

        user = flask.g.current_user
        rows = grants.list(
            grantee_type="user",
            grantee_id=str(user.get("id")),
            resource_type=_VAULT_RESOURCE,
        )
        if rows and scopes.grants(_user_token_scopes(), "vaults:read"):
            return
        raise api_errors.ForbiddenError(
            "Listing vault labels requires a vault grant row AND the "
            "'vaults:read' scope (#1055): designation and capability "
            "are both required, like every management vocabulary"
        )
    if is_operator():
        return
    raise api_errors.ForbiddenError(
        "Enumerating vault labels requires the operator principal "
        f"({OPERATOR_CLIENT_IDS_ENVVAR}) or a designated user with a "
        "vault grant and the 'vaults:read' scope (#1055); client "
        "principals hold per-label access only (#881)"
    )


# --- Integration action proxies (#1221) --------------------------------------

def integration_admin_scope(provider: str) -> str:
    """The management scope authorizing action proxies for an integration.

    `integrations.<provider>:admin` — named per integration so a
    designation for one integration's actions never implies another's
    (the dotted resource parses fine through the monotonic algebra:
    `scopes.grants` partitions on the first colon).
    """
    return f"integrations.{provider}:admin"


def require_integration_action(provider: str, action: str) -> None:
    """Gate for integration action proxies (#1221).

    An action proxy performs an upstream-provider verb (e.g. Classroom
    turnIn) on a TARGET user's stored credential at an administrator's
    request. The gate composes the two independent authorities the
    issue pins — neither suffices alone, and neither grants the other:

    - capability leg: the caller's token carries
      `integrations.<provider>:admin` (#865). Who can HOLD the scope
      is curated by the operator through the minting client's
      allowed_scopes; mint time validates the ask against that
      allowlist.
    - custody leg: vault access to the integration's vault label
      (#883/#889) — the credentials being acted on are that label's,
      so the actor must hold at least read authority over it. Checked
      via require_vault_permission, whose user leg is the per-label
      grant row + `vaults:*` token scope.

    The operator client and the super-admin root bypass (house
    pattern); any other client principal is denied outright — action
    proxies mutate user-bound upstream state and must stay
    user-attributable (#881).

    Args:
        provider: the namespaced provider (e.g. "google.classroom").
        action: the allowlisted action name; surfaced in denial
            messages only.

    Raises:
        api_errors.ForbiddenError: If the caller lacks authority.
    """
    del action  # surfaced by callers in audit events, not in the gate
    if is_user_principal():
        if is_super_admin():
            return
        required = integration_admin_scope(provider)
        if not scopes.grants(_user_token_scopes(), required):
            raise api_errors.ForbiddenError(
                f"Token lacks '{required}' (#865): integration action "
                "proxies require the per-integration management scope, "
                "mintable only against a client whose allowed_scopes "
                "carries it"
            )
        from campus.model.client import ClientAccess

        # Lazy imports: keep authz importable ahead of storage
        # initialization, same as the other designation checks.
        from . import integrations as integrations_registry

        vault_label = integrations_registry.resolve(provider).vault_label
        require_vault_permission(vault_label, ClientAccess.READ)
        return
    if is_operator():
        return
    client = getattr(flask.g, "current_client", None)
    who = f"Client '{client.id}'" if client else "Client principals"
    raise api_errors.ForbiddenError(
        f"{who} may not drive integration action proxies (#1221): "
        "actions on user-bound upstream credentials are "
        "user-attributable (#881) — call them with a designated "
        "user's bearer token or as the operator"
    )
