"""campus.vault.routes.clients

Flask routes for vault client management.

These routes handle creating, listing, retrieving, and deleting vault clients.
Admin operations require ALL permissions, read operations require READ permissions.
"""

from typing import TypedDict

from flask import Blueprint, Flask

from campus.common.errors import api_errors
import campus.common.validation.flask as flask_validation
import campus.yapper

from .. import client
from ..auth import require_client_authentication

# Create blueprint for client management routes
bp = Blueprint('clients', __name__, url_prefix='/clients')

# Lazy-loaded yapper instance to avoid circular dependencies
_yapper_instance = None


def get_yapper():
    """Get yapper instance, creating it lazily to avoid circular
    dependencies."""
    global _yapper_instance
    if _yapper_instance is None:
        _yapper_instance = campus.yapper.create()
    return _yapper_instance


def init_app(app: Flask | Blueprint) -> None:
    """Initialize the client routes with the given Flask app or
    blueprint.
    """
    app.register_blueprint(bp)


class VaultClientNew(TypedDict):
    """Request schema for creating a new vault client."""
    name: str
    description: str


class AuthenticateClient(TypedDict):
    """Request schema for authenticating a vault client."""
    client_id: str
    client_secret: str


@bp.post("/")
@require_client_authentication
def create_vault_client() -> flask_validation.JsonResponse:
    """Create a new vault client.

    POST /client
    Body: {
        "name": "Client Name",
        "description": "Client description"
    }

    Returns: {
        "status": "success",
        "client": {
            "id": "client_abc123",
            "name": "Client Name",
            "description": "Client description",
            "created_at": "2025-07-20T10:30:00Z"
        },
        "client_secret": "secret_xyz789"
    }
    """
    payload = flask_validation.validate_request_and_extract_json(
        VaultClientNew.__annotations__,
        on_error=api_errors.raise_api_error
    )
    # Create the client
    client_resource = client.create_client(**payload)
    return client_resource, 201


@bp.get("/")
@require_client_authentication
def list_vault_clients() -> flask_validation.JsonResponse:
    """List all vault clients

    GET /client
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
    clients = client.list_clients()
    return {"clients": clients}, 200


# Authenticate a vault client by client_id and client_secret
@bp.post("/authenticate")
# Client authentication not required (since API clients would need to
# use this route to authenticate)
def authenticate_vault_client() -> flask_validation.JsonResponse:
    """Authenticate a vault client by client_id and client_secret.

    POST /client/authenticate
    Body: {"client_id": ..., "client_secret": ...}

    Returns: {"status": "success", "client_id": ...} or error JSON
    """
    payload = flask_validation.validate_request_and_extract_json(
        AuthenticateClient.__annotations__,
        on_error=api_errors.raise_api_error
    )
    client.authenticate_client(**payload)
    return {"client_id": payload["client_id"]}, 200


@bp.get("/<client_id>")
@require_client_authentication
def get_vault_client(client_id) -> flask_validation.JsonResponse:
    """Get details of a specific vault client

    GET /client/{client_id}
    Returns: {
        "client": {
            "id": "client_abc123",
            "name": "Client Name",
            "description": "Client description", 
            "created_at": "2025-07-20T10:30:00Z"
        }
    }
    """
    client_resource = client.get_client(client_id)
    return client_resource, 200


@bp.delete("/<client_id>")
@require_client_authentication
def delete_vault_client(client_id) -> flask_validation.JsonResponse:
    """Delete a vault client

    DELETE /client/{client_id}
    Returns: {
        "status": "success",
        "client_id": "client_abc123",
        "action": "deleted"
    }
    """
    client.delete_client(client_id)
    get_yapper().emit('campus.clients.delete')
    return {"client_id": client_id, "action": "deleted"}, 200
