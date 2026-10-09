"""campus.auth.routes.clients

Flask routes for Campus client management.

These routes handle creating, listing, retrieving, and deleting clients.
Client records are deployment registration data (redirect URIs, scope
caps, the token-bridge flag), so every route is authorization-gated,
not just authenticated (#854):

- the operator principal (AUTH_OPERATOR_CLIENT_IDS) may manage every
  client: register, update (including scope caps and the token-bridge
  flag), delete, rotate secrets, and administer vault access grants;
- any other authenticated client may manage only itself: read its own
  record, update its own profile fields (name, description,
  redirect_uris — never the scope caps or token_bridge), rotate its
  own secret, and list clients (ids and display names only — the audit
  UI resolves client names this way);
- designated admin users (#865) may act with their own user
  credentials where the route's management scope matches their token:
  clients:read to list/get any record (including vault-access views),
  clients:write to update benign fields on any client, clients:admin
  to register, delete, rotate secrets, set scope caps and administer
  vault-access grants. Both the AUTH_ADMIN_USER_IDS listing and the
  scope are required (ANDed, fail-closed);
- any other user bearer token is denied on every route regardless of
  scope.

Authentication is handled in a global routes.before_request hook.
"""

import flask

from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import authz, get_yapper, scopes
from ..resources import client as client_resource

# Create blueprint for client management routes
bp = flask.Blueprint('clients', __name__, url_prefix='/clients')


@bp.post("/")
@flask_campus.unpack_request
def new(
        name: str,
        description: str,
        is_public: bool = False,
        redirect_uris: list[str] | None = None,
        allowed_scopes: list[str] | None = None,
        upstream_scopes: dict[str, list[str]] | None = None,
        token_bridge: bool = False
) -> flask_campus.JsonResponse:
    """Register a new client.

    POST /clients/
    Authorization: operator only, plus designated admin users holding
    clients:admin (#865) — client registration mints a new principal.

    Body: {
        "name": "Client Name",
        "description": "Client description",
        "is_public": false,  # Optional: true for CLI/mobile apps
        "redirect_uris": [],  # Optional: OAuth redirect URIs
        "allowed_scopes": [],  # Optional: scope allowlist (fail-closed)
        "upstream_scopes": {},  # Optional: per-provider upstream allowlist
        "token_bridge": false  # Optional: upstream token release access
    }

    Returns: {
        "id": "client_abc123",
        "name": "Client Name",
        "description": "Client description",
        "is_public": false,
        "redirect_uris": [],
        "allowed_scopes": [],
        "upstream_scopes": {},
        "token_bridge": false,
        "created_at": "2025-07-20T10:30:00Z"
    }

    Public clients (is_public=true) don't have a client_secret and are used
    for CLI, mobile apps, and native applications that cannot securely store
    credentials per RFC 6749 Section 2.1.

    allowed_scopes is the fail-closed scope allowlist
    (docs/auth-token-invariants.md A1): a client with an empty allowlist
    can be granted no scopes. upstream_scopes caps the third-party
    provider scopes a client may be granted through the OAuth proxies
    (invariant B3); an absent provider entry allows only that proxy's
    base scopes. token_bridge grants access to the upstream token
    release endpoint (invariant C1): confidential clients only, never
    public ones.
    """
    authz.require_operator(
        "register clients", admin_scope=authz.CLIENTS_ADMIN
    )
    if is_public and token_bridge:
        raise api_errors.InvalidRequestError(
            "Public clients cannot be granted token bridge access",
        )
    client = client_resource.new(
        name=name,
        description=description,
        is_public=is_public,
        redirect_uris=redirect_uris or [],
        allowed_scopes=scopes.parse(allowed_scopes),
        upstream_scopes=scopes.parse_upstream(upstream_scopes),
        token_bridge=token_bridge
    )
    get_yapper().emit('campus.clients.create', {"client_id": client.id})
    return client.to_resource(), 200


@bp.get("/")
@flask_campus.unpack_request
def list_all() -> flask_campus.JsonResponse:
    """List all clients

    GET /clients
    Authorization: any client principal (#854), or a designated admin
    user with clients:read (#865) — the resource carries display
    metadata only (no secret material), and the audit UI resolves
    client ids to names through this route. Other user bearer tokens
    are denied.

    Returns: {
        "clients": [
            {
                "id": "client_abc123",
                "name": "Client Name",
                "description": "Client description",
                "created_at": "2025-07-20T10:30:00Z"
            }
        ]
    }
    """
    # Designated admin users with clients:read may list too (#865);
    # any client principal keeps its existing listing authority.
    authz.require_admin_user(authz.CLIENTS_READ, "list clients")
    clients = [
        client.to_resource()
        for client in client_resource.list_all()
    ]
    return {"clients": clients}, 200


@bp.delete("/<client_id>/")
@flask_campus.unpack_request
def delete_client(client_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Delete a client

    DELETE /clients/{client_id}
    Authorization: operator only, or a designated admin user with
    clients:admin (#865) — even the client itself may not delete its
    own record.

    Returns: {}
    """
    authz.require_operator(
        "delete clients", admin_scope=authz.CLIENTS_ADMIN
    )
    client_resource[client_id].delete()
    get_yapper().emit('campus.clients.delete', {"client_id": client_id})
    return {}, 200


@bp.get("/<client_id>/")
@flask_campus.unpack_request
def get_client(client_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Get details of a specific client

    GET /clients/{client_id}
    Authorization: the client itself, or operator (#854), or a
    designated admin user with clients:read (#865).

    Returns: {
        "client": {
            "id": "client_abc123",
            "name": "Client Name",
            "description": "Client description",
            "created_at": "2025-07-20T10:30:00Z"
        }
    }
    """
    authz.require_self_or_operator(
        client_id, "view", admin_scope=authz.CLIENTS_READ
    )
    client = client_resource[client_id].get()
    return client.to_resource(), 200


@bp.post("/<client_id>/revoke")
@flask_campus.unpack_request
def revoke_client(client_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Revoke a client's secret and generate a new one.

    POST /clients/{client_id}/revoke
    Authorization: the client itself (rotating its own credential is
    self-management), or operator (#854), or a designated admin user
    with clients:admin (#865).

    Returns: {"secret": new_secret}
    """
    authz.require_self_or_operator(
        client_id,
        "rotate the secret of",
        admin_scope=authz.CLIENTS_ADMIN,
    )
    new_secret = client_resource[client_id].revoke()
    get_yapper().emit("campus.clients.revoke", {"client_id": client_id})
    return {"secret": new_secret}, 200


@bp.patch("/<client_id>/")
@flask_campus.unpack_request
def update_client(
        client_id: schema.CampusID,
        name: str | None = None,
        description: str | None = None,
        redirect_uris: list[str] | None = None,
        allowed_scopes: list[str] | None = None,
        upstream_scopes: dict[str, list[str]] | None = None,
        token_bridge: bool | None = None
) -> flask_campus.JsonResponse:
    """Update a client's details.

    PATCH /clients/{client_id}
    Authorization: the client itself may update its profile fields
    (name, description, redirect_uris) but not its scope caps or the
    token-bridge flag; the operator may update everything (#854);
    designated admin users may update benign fields with clients:write
    and the scope caps with clients:admin (#865).

    Body: {
        "name": "New Client Name",
        "description": "New description",
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"],  # Optional
        "allowed_scopes": ["read", "write"],  # Optional
        "upstream_scopes": {"google": [...]}  # Optional
    }
    Returns: {
        "id": "client_abc123",
        "name": "New Client Name",
        "description": "New description",
        "is_public": false,
        "redirect_uris": [],
        "allowed_scopes": [],
        "upstream_scopes": {},
        "created_at": "2025-07-20T10:30:00Z"
    }

    Note: is_public cannot be changed after client creation.
    allowed_scopes is the fail-closed scope allowlist
    (docs/auth-token-invariants.md A1): sessions and device codes may
    only request scopes it contains. upstream_scopes caps the
    third-party provider scopes the client may be granted through the
    OAuth proxies (invariant B3). allowed_scopes, upstream_scopes and
    token_bridge are operator-controlled: a self-managing client
    changing them is rejected (403).
    """
    authz.require_self_or_operator(
        client_id, "update", admin_scope=authz.CLIENTS_WRITE
    )
    # Raises unless the caller is the operator client or a designated
    # admin user holding clients:admin (allowed_scopes/upstream_scopes/
    # token_bridge are never self-service, #865).
    authz.require_operator_only_client_fields({
        "allowed_scopes": allowed_scopes,
        "upstream_scopes": upstream_scopes,
        "token_bridge": token_bridge,
    })
    updates = {}
    if name is not None:
        updates["name"] = name
    if description is not None:
        updates["description"] = description
    if redirect_uris is not None:
        updates["redirect_uris"] = redirect_uris
    if allowed_scopes is not None:
        updates["allowed_scopes"] = scopes.parse(allowed_scopes)
    if upstream_scopes is not None:
        updates["upstream_scopes"] = scopes.parse_upstream(upstream_scopes)
    if token_bridge is not None:
        existing = client_resource[client_id].get()
        if token_bridge and existing.is_public:
            raise api_errors.InvalidRequestError(
                "Public clients cannot be granted token bridge access",
                client_id=client_id
            )
        updates["token_bridge"] = token_bridge
    if not updates:
        raise api_errors.InvalidRequestError(
            "No updates provided",
            client_id=client_id
        )
    client_resource[client_id].update(**updates)
    updated_client = client_resource[client_id].get()
    get_yapper().emit("campus.clients.update", {"client_id": client_id})
    return updated_client.to_resource(), 200


@bp.get("/<client_id>/access/")
@flask_campus.unpack_request
def get_client_access(
        client_id: schema.CampusID,
        vault: str | None = None,
) -> flask_campus.JsonResponse:
    """Check a client's access.

    GET /clients/{client_id}/access
    Authorization: the client itself, or operator (#854), or a
    designated admin user with clients:read (#865).

    Returns: {
        "client_id": "client_abc123",
        "access": int
    }
    """
    authz.require_self_or_operator(
        client_id,
        "view the vault access of",
        admin_scope=authz.CLIENTS_READ,
    )
    if vault:
        access = client_resource[client_id].access.get(vault)
        return {"vault": vault, "access": access}, 200
    else:
        access_list = client_resource[client_id].access.list()
        return {"access": access_list}, 200


@bp.get("/<client_id>/access/check")
@flask_campus.unpack_request
def check_client_access(
        client_id: schema.CampusID,
        vault: str,
        permission: int
) -> flask_campus.JsonResponse:
    """Check a client's access.

    GET /clients/{client_id}/access/check
    Authorization: the client itself, or operator (#854), or a
    designated admin user with clients:read (#865).

    Returns: {
        "client_id": "client_abc123",
        "has_access": true
    }
    """
    authz.require_self_or_operator(
        client_id,
        "check the vault access of",
        admin_scope=authz.CLIENTS_READ,
    )
    has_access = client_resource[client_id].access.check(
        vault_label=vault,
        permission=permission
    )
    return {"vault": vault, "permission": has_access}, 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('clients', __name__, url_prefix='/clients')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/", "new", new, methods=["POST"])
    new_bp.add_url_rule("/", "list_all", list_all, methods=["GET"])
    new_bp.add_url_rule("/<client_id>/", "delete_client", delete_client, methods=["DELETE"])
    new_bp.add_url_rule("/<client_id>/", "get_client", get_client, methods=["GET"])
    new_bp.add_url_rule("/<client_id>/revoke", "revoke_client", revoke_client, methods=["POST"])
    new_bp.add_url_rule("/<client_id>/", "update_client", update_client, methods=["PATCH"])
    new_bp.add_url_rule("/<client_id>/access/", "get_client_access", get_client_access, methods=["GET"])
    new_bp.add_url_rule("/<client_id>/access/check", "check_client_access", check_client_access, methods=["GET"])
    new_bp.add_url_rule("/<client_id>/access/grant", "grant_client_access", grant_client_access, methods=["POST"])
    new_bp.add_url_rule("/<client_id>/access/revoke", "revoke_client_access", revoke_client_access, methods=["POST"])
    new_bp.add_url_rule("/<client_id>/access/", "update_client_access", update_client_access, methods=["PATCH"])

    return new_bp


@bp.post("/<client_id>/access/grant")
@flask_campus.unpack_request
def grant_client_access(
        client_id: schema.CampusID,
        vault: str,
        permission: int
) -> flask_campus.JsonResponse:
    """Grant a client access to a vault.

    POST /clients/{client_id}/access/grant
    Authorization: operator only (#854), or a designated admin user
    with clients:admin (#865) — vault access administration is never
    self-service, not even on the client's own record.

    Body: {
        "vault": "vault_label",
        "permission": permission_to_grant[int]
    }

    Returns: {
        "vault": "vault_label",
        "permission": updated_permission[int]
    }
    """
    authz.require_operator(
        "grant vault access", admin_scope=authz.CLIENTS_ADMIN
    )
    client_resource[client_id].access.grant(
        vault_label=vault,
        permission=permission
    )
    updated_permission = client_resource[client_id].access.get(vault)
    get_yapper().emit("campus.clients.access.update", {"client_id": client_id})
    return {"vault": vault, "permission": updated_permission}, 200


@bp.post("/<client_id>/access/revoke")
@flask_campus.unpack_request
def revoke_client_access(
        client_id: schema.CampusID,
        vault: str,
        permission: int
) -> flask_campus.JsonResponse:
    """Revoke a client's access to a vault.

    POST /clients/{client_id}/access/revoke
    Authorization: operator only (#854), or a designated admin user
    with clients:admin (#865).

    Body: {
        "vault": "vault_label",
        "permission": permission_to_revoke[int]
    }

    Returns: {
        "vault": "vault_label",
        "permission": updated_permission[int]
    }
    """
    authz.require_operator(
        "revoke vault access", admin_scope=authz.CLIENTS_ADMIN
    )
    client_resource[client_id].access.revoke(
        vault_label=vault,
        permission=permission
    )
    updated_permission = client_resource[client_id].access.get(vault)
    get_yapper().emit("campus.clients.access.update", {"client_id": client_id})
    return {"vault": vault, "permission": updated_permission}, 200


@bp.patch("/<client_id>/access/")
@flask_campus.unpack_request
def update_client_access(
        client_id: schema.CampusID,
        vault: str,
        permission: int
) -> flask_campus.JsonResponse:
    """Update (replace) a client's access permissions for a vault.

    PATCH /clients/{client_id}/access/
    Authorization: operator only (#854), or a designated admin user
    with clients:admin (#865).

    Body: {
        "vault": "vault_label",
        "permission": new_permission[int]
    }

    Returns: {
        "vault": "vault_label",
        "permission": updated_permission[int]
    }
    """
    authz.require_operator(
        "update vault access", admin_scope=authz.CLIENTS_ADMIN
    )
    client_resource[client_id].access.update(
        vault_label=vault,
        permission=permission
    )
    updated_permission = client_resource[client_id].access.get(vault)
    get_yapper().emit("campus.clients.access.update", {"client_id": client_id})
    return {"vault": vault, "permission": updated_permission}, 200
