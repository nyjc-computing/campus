"""campus.vault.routes.access

Flask routes for vault access control management.

These routes handle granting, revoking, and checking access permissions for vault clients.
Admin operations require ALL permissions, access checking requires READ permissions.
"""

from typing import TypedDict

from flask import Blueprint, Flask

from campus.common import flask as campus_flask
from campus.common.errors import api_errors

from .. import access
from ..auth import require_client_authentication, require_vault_permission

# Create blueprint for access management routes
bp = Blueprint('access', __name__, url_prefix='/access')


def init_app(app: Flask | Blueprint) -> None:
    """Initialize the access routes with the given Flask app or blueprint."""
    app.register_blueprint(bp)


class GetVaultAccess(TypedDict):
    """Schema for a request to get access."""
    client_id: str


class GrantVaultAccess(TypedDict):
    """Schema for a request to grant access."""
    client_id: str
    permissions: list[str] | int


class RevokeVaultAccess(TypedDict):
    """Schema for a request to revoke access."""
    client_id: str


@bp.post("/<label>")
@require_client_authentication
@require_vault_permission(access.ALL)  # Require admin-level permissions
def grant_vault_access(label) -> campus_flask.JsonResponse:
    """Grant access to a vault for a client

    POST /access/{vault_label}
    Body: {
        "client_id": "target_client_id",
        "permissions": ["READ", "CREATE"] or 7
    }

    Args:
        client_id: The authenticated client making this request (injected by decorator)
        label: The vault label from the URL path
    """
    payload = campus_flask.validate_request_and_extract_json(
        GrantVaultAccess.__annotations__,
        on_error=api_errors.raise_api_error
    )
    target_client_id = payload["client_id"]
    permissions = payload["permissions"]
    access_value = access.permissions_to_access(permissions)
    access.grant_access(target_client_id, label, access_value)

    return {
        "client_id": target_client_id,
        "label": label,
        "permissions": access_value
    }, 200


@bp.delete("/<label>")
@require_client_authentication
@require_vault_permission(access.ALL)  # Require admin-level permissions
def revoke_vault_access(label: str) -> campus_flask.JsonResponse:
    """Revoke access to a vault for a client

    DELETE /access/{vault_label}?client_id={client_id}

    Args:
        client_id: The authenticated client making this request (injected by decorator)
        label: The vault label from the URL path
    """

    payload = campus_flask.validate_request_and_extract_json(
        RevokeVaultAccess.__annotations__,
        on_error=api_errors.raise_api_error
    )
    target_client_id = payload["client_id"]

    access.revoke_access(target_client_id, label)

    return {
        "client_id": target_client_id,
        "label": label,
        "action": "revoked"
    }, 200


@bp.get("/<label>")
@require_client_authentication
@require_vault_permission(access.READ)
def get_vault_access(label) -> campus_flask.JsonResponse:
    """Check if a client has access to a vault

    GET /access/{vault_label}?client_id={client_id}
    Returns: {
        "client_id": "...",
        "label": "...", 
        "permissions": {
            "READ": true,
            "CREATE": false,
            "UPDATE": true,
            "DELETE": false
        }
    }

    Args:
        client_id: The authenticated client making this request (injected by decorator)
        label: The vault label from the URL path
    """
    payload = campus_flask.validate_request_and_extract_urlparams(
        GetVaultAccess.__annotations__,
        on_error=api_errors.raise_api_error
    )
    target_client_id = payload["client_id"]
    # Check each permission level
    permissions = {
        "READ": access.has_access(target_client_id, label, access.READ),
        "CREATE": access.has_access(target_client_id, label, access.CREATE),
        "UPDATE": access.has_access(target_client_id, label, access.UPDATE),
        "DELETE": access.has_access(target_client_id, label, access.DELETE)
    }

    return {
        "client_id": target_client_id,
        "label": label,
        "permissions": permissions
    }, 200
