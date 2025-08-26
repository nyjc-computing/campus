"""campus.vault.routes.vault

Flask routes for the vault web API service.

Routes handle authentication and authorization before delegating to the data model.
This follows the principle of handling cross-cutting concerns at the appropriate layer.
"""

from flask import Blueprint, Flask, g, request

import campus.common.validation.flask as flask_validation

from .. import access
from ..auth import (
    check_vault_access,
    require_client_authentication,
    require_vault_permission
)
from ..model import Vault

# Create blueprint for vault routes
bp = Blueprint('vault', __name__, url_prefix='/vault')


@bp.route("/")
@require_client_authentication()
def list_vaults() -> flask_validation.JsonResponse:
    """List available vault labels"""
    # TODO: In a more sophisticated implementation, this would return
    # only the vaults that the authenticated client has access to
    return {"vaults": ["campus", "storage", "oauth"]}, 200


@bp.route("/<label>/")
@require_client_authentication()
@require_vault_permission(access.READ)
def list_keys(label) -> flask_validation.JsonResponse:
    """List all keys in a vault"""
    vault = Vault(label)
    keys = vault.list_keys()
    return {"label": label, "keys": keys}, 200


@bp.route("/<label>/<key>")
@require_client_authentication()
@require_vault_permission(access.READ)
def get_secret(label, key) -> flask_validation.JsonResponse:
    """Get a secret from a vault"""
    vault = Vault(label)
    value = vault.get(key)
    return {"key": key, "value": value}, 200


@bp.route("/<label>/<key>", methods=["POST"])
@require_client_authentication()
# Client needs CREATE OR UPDATE
@require_vault_permission(access.CREATE, access.UPDATE)
def set_secret(label, key) -> flask_validation.JsonResponse:
    """Set a secret in a vault

    Requires CREATE permission for new keys, UPDATE permission for existing keys.
    The decorator ensures the client has at least one of these permissions.
    """
    data = request.get_json()
    if not data or "value" not in data:
        return {"error": "Missing 'value' in request body"}, 400

    value = data.get("value")
    if not isinstance(value, str):
        return {"error": "'value' must be a string"}, 400

    vault = Vault(label)

    # Check if key exists to determine specific permission and validate
    key_exists = vault.has(key)
    required_permission = access.UPDATE if key_exists else access.CREATE

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


@bp.route("/<label>/<key>", methods=["DELETE"])
@require_client_authentication()
@require_vault_permission(access.DELETE)
def delete_secret(label, key) -> flask_validation.JsonResponse:
    """Delete a secret from a vault"""
    vault = Vault(label)
    deleted = vault.delete(key)

    if deleted:
        return {"status": "success", "key": key, "action": "deleted"}, 200
    else:
        return {"error": f"Secret '{key}' not found in vault '{label}'"}, 404


def init_app(app: Flask | Blueprint) -> None:
    """Initialize the vault routes with the given Flask app or blueprint."""
    app.register_blueprint(bp)
