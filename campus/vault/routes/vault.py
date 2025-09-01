"""campus.vault.routes.vault

Flask routes for the vault web API service.

Routes handle authentication and authorization before delegating to the data model.
This follows the principle of handling cross-cutting concerns at the appropriate layer.
"""

from flask import Blueprint, Flask, jsonify, request

import campus.common.validation.flask as flask_validation

# Create blueprint for vault routes
bp = Blueprint('vault', __name__, url_prefix='/vault')


@bp.get("/")
@auth.require_client_authentication()
def list_vaults() -> flask_validation.JsonResponse:
    """List available vault labels"""
    # TODO: In a more sophisticated implementation, this would return
    # only the vaults that the authenticated client has access to
    return jsonify({"vaults": ["campus", "storage", "oauth"]})


@bp.get("/<label>/")
@auth.require_client_authentication()
@auth.require_vault_permission(access.READ)
def list_keys(label) -> flask_validation.JsonResponse:
    """List all keys in a vault"""
    vault = Vault(label)
    keys = vault.list_keys()
    return jsonify({"label": label, "keys": keys})


@bp.get("/<label>/<key>")
@auth.require_client_authentication()
@auth.require_vault_permission(access.READ)
def get_secret(label, key) -> flask_validation.JsonResponse:
    """Get a secret from a vault"""
    vault = Vault(label)
    value = vault.get(key)
    return jsonify({"key": key, "value": value})


@bp.post("/<label>/<key>")
def set_secret(label, key) -> flask_validation.JsonResponse:
    """Set a secret in a vault

    Requires CREATE permission for new keys, UPDATE permission for existing keys.
    The decorator ensures the client has at least one of these permissions.
    """
    data = request.get_json()
    if not data or "value" not in data:
        return jsonify({"error": "Missing 'value' in request body"}), 400

    value = data.get("value")
    if not isinstance(value, str):
        return jsonify({"error": "'value' must be a string"}), 400

    vault = Vault(label)

    # Check if key exists to determine specific permission and validate
    key_exists = vault.has(key)
    required_permission = access.UPDATE if key_exists else access.CREATE

    # Verify client has the specific permission required for this operation
    auth.check_vault_access(client_id, label, required_permission)

    # Perform the operation
    is_new = vault.set(key, value)
    action = "created" if is_new else "updated"

    return jsonify({
        "status": "success",
        "key": key,
        "action": action
    })


@bp.delete("/<label>/<key>")
@auth.require_client_authentication()
@auth.require_vault_permission(access.DELETE)
def delete_secret(label, key) -> flask_validation.JsonResponse:
    """Delete a secret from a vault"""
    vault = Vault(label)
    deleted = vault.delete(key)

    if deleted:
        return jsonify({"status": "success", "key": key, "action": "deleted"})
    else:
        return jsonify({"error": f"Secret '{key}' not found in vault '{label}'"}), 404


def init_app(app: Flask | Blueprint) -> None:
    """Initialize the vault routes with the given Flask app or blueprint."""
    app.register_blueprint(bp)
