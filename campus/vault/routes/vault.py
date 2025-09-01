"""campus.vault.routes.vault

Flask routes for the vault web API service.

Routes handle authentication and authorization before delegating to the data model.
This follows the principle of handling cross-cutting concerns at the appropriate layer.
"""

from typing import TypedDict

from flask import Blueprint, Flask, g

from campus.common.errors import api_errors
import campus.common.validation.flask as flask_validation

from .. import access, model
from ..auth import (
    check_vault_access,
    require_client_authentication,
    require_vault_permission
)

# Create blueprint for vault routes
bp = Blueprint('vault', __name__, url_prefix='/vault')


def init_app(app: Flask | Blueprint) -> None:
    """Initialize the vault routes with the given Flask app or blueprint."""
    app.register_blueprint(bp)


class SetSecretValue(TypedDict):
    """Schema for a request to set a secret value."""
    value: str


@bp.get("/")
@require_client_authentication()
def list_vaults() -> flask_validation.JsonResponse:
    """List available vault labels"""
    labels = model.Vault.get_labels(g.current_client.id)
    return {"vaults": labels}, 200


@bp.get("/<label>/")
@require_client_authentication()
@require_vault_permission(access.READ)
def list_keys(label: str) -> flask_validation.JsonResponse:
    """List all keys in a vault"""
    vault = model.Vault(label)
    keys = vault.list_keys()
    return {"label": label, "keys": keys}, 200


@bp.get("/<label>/<key>")
@require_client_authentication()
@require_vault_permission(access.READ)
def get_secret(label: str, key: str) -> flask_validation.JsonResponse:
    """Get a secret from a vault"""
    vault = model.Vault(label)
    value = vault.get(key)
    return {"key": key, "value": value}, 200


@bp.post("/<label>/<key>")
@require_client_authentication()
# Client needs CREATE OR UPDATE
@require_vault_permission(access.CREATE, access.UPDATE)
def set_secret(label: str, key: str) -> flask_validation.JsonResponse:
    """Set a secret in a vault

    Requires CREATE permission for new keys, UPDATE permission for existing
    keys.
    The decorator ensures the client has at least one of these permissions.
    """
    payload = flask_validation.validate_request_and_extract_json(
        SetSecretValue.__annotations__,
        on_error=api_errors.raise_api_error
    )
    value = payload["value"]
    vault = model.Vault(label)

    # Check if key exists to determine specific permission and validate
    required_permission = access.UPDATE if vault.has(key) else access.CREATE

    # Verify client has the specific permission required for this operation
    check_vault_access(g.current_client.id, label, required_permission)

    # Perform the operation
    is_new = vault.set(key, value)
    action = "created" if is_new else "updated"

    return {
        "status": "success",
        "key": key,
        "action": action
    }, 200


@bp.delete("/<label>/<key>")
@require_client_authentication()
@require_vault_permission(access.DELETE)
def delete_secret(label, key) -> flask_validation.JsonResponse:
    """Delete a secret from a vault"""
    vault = model.Vault(label)
    deleted = vault.delete(key)

    if deleted:
        return {"status": "success", "key": key, "action": "deleted"}, 200
    else:
        return {"error": f"Secret '{key}' not found in vault '{label}'"}, 404
