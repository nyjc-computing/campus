"""campus.auth.routes.clients

Flask routes for Campus client management.

These routes handle creating, listing, retrieving, and deleting clients.
Admin operations require ALL permissions, read operations require READ permissions.

Authentication is handled in a global routes.before_request hook.
"""

import flask

from campus.common import flask_campus, schema
from campus.common.errors import api_errors
import campus.yapper

from ..resources import client as client_resource

# Create blueprint for client management routes
bp = flask.Blueprint('clients', __name__, url_prefix='/clients')

# Lazy-loaded yapper instance to avoid circular dependencies
_yapper_instance = None


def get_yapper():
    """Get yapper instance, creating it lazily to avoid circular
    dependencies."""
    global _yapper_instance
    if _yapper_instance is None:
        _yapper_instance = campus.yapper.create()
    return _yapper_instance


@bp.post("/")
@flask_campus.unpack_request
def new(name: str, description: str) -> flask_campus.JsonResponse:
    """Create a new vault client.

    POST /client
    Body: {
        "name": "Client Name",
        "description": "Client description"
    }

    Returns: {
        "id": "client_abc123",
        "name": "Client Name",
        "description": "Client description",
        "created_at": "2025-07-20T10:30:00Z"
    }
    """
    # Note that no client_secret is generated here
    # Apps are expected to generate the secret separately
    client = client_resource.new(name=name, description=description)
    get_yapper().emit('campus.clients.create')
    return client.to_resource(), 200


@bp.get("/")
@flask_campus.unpack_request
def list_all() -> flask_campus.JsonResponse:
    """List all clients

    GET /clients
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
    clients = [
        client.to_resource()
        for client in client_resource.list_all()
    ]
    return {"clients": clients}, 200


@bp.delete("/<client_id>")
@flask_campus.unpack_request
def delete_client(client_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Delete a vault client

    DELETE /client/{client_id}
    Returns: {
        "status": "success",
        "client_id": "client_abc123",
        "action": "deleted"
    }
    """
    client_resource[client_id].delete()
    get_yapper().emit('campus.clients.delete')
    return {}, 200


@bp.get("/<client_id>")
@flask_campus.unpack_request
def get_client(client_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Get details of a specific client

    GET /clients/{client_id}
    Returns: {
        "client": {
            "id": "client_abc123",
            "name": "Client Name",
            "description": "Client description", 
            "created_at": "2025-07-20T10:30:00Z"
        }
    }
    """
    client = client_resource[client_id].get()
    return client.to_resource(), 200


@bp.post("/<client_id>/revoke")
@flask_campus.unpack_request
def revoke_client(client_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Revoke a client's secret and generate a new one.

    POST /clients/{client_id}/revoke
    Returns: {"secret": new_secret}
    """
    new_secret = client_resource[client_id].revoke()
    return {"secret": new_secret}, 200


@bp.patch("/<client_id>")
@flask_campus.unpack_request
def update_client(
        client_id: schema.CampusID,
        name: str | None = None,
        description: str | None = None
) -> flask_campus.JsonResponse:
    """Update a client's details.

    PATCH /clients/{client_id}
    Body: {
        "name": "New Client Name",
        "description": "New description"
    }
    Returns: {
        "id": "client_abc123",
        "name": "New Client Name",
        "description": "New description",
        "created_at": "2025-07-20T10:30:00Z"
    }
    """
    updates = {}
    if name is not None:
        updates["name"] = name
    if description is not None:
        updates["description"] = description
    if not updates:
        raise api_errors.InvalidRequestError(
            "No updates provided",
            client_id=client_id
        )
    client_resource[client_id].update(**updates)
    updated_client = client_resource[client_id].get()
    return updated_client.to_resource(), 200


@bp.get("/<client_id>/access")
@flask_campus.unpack_request
def get_client_access(
        client_id: schema.CampusID,
        vault: str | None = None,
) -> flask_campus.JsonResponse:
    """Check a client's access.

    GET /clients/{client_id}/access
    Returns: {
        "client_id": "client_abc123",
        "access": int
    }
    """
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
    Returns: {
        "client_id": "client_abc123",
        "has_access": true
    }
    """
    has_access = client_resource[client_id].access.check(
        vault_label=vault,
        permission=permission
    )
    return {"vault": vault, "permission": has_access}, 200


@bp.post("/<client_id>/access/grant")
@flask_campus.unpack_request
def grant_client_access(
        client_id: schema.CampusID,
        vault: str,
        permission: int
) -> flask_campus.JsonResponse:
    """Grant a client access to a vault.

    POST /clients/{client_id}/access/grant
    Body: {
        "vault": "vault_label",
        "permission": permission_to_grant[int]
    }

    Returns: {
        "vault": "vault_label",
        "permission": updated_permission[int]
    }
    """
    client_resource[client_id].access.grant(
        vault_label=vault,
        permission=permission
    )
    updated_permission = client_resource[client_id].access.get(vault)
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
    Body: {
        "vault": "vault_label",
        "permission": permission_to_revoke[int]
    }

    Returns: {
        "vault": "vault_label",
        "permission": updated_permission[int]
    }
    """
    client_resource[client_id].access.revoke(
        vault_label=vault,
        permission=permission
    )
    updated_permission = client_resource[client_id].access.get(vault)
    return {"vault": vault, "permission": updated_permission}, 200
