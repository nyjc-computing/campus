"""vault.routes.vault

Flask routes for the vault web API service.

Routes handle authentication and authorization before delegating to the data model.
This follows the principle of handling cross-cutting concerns at the appropriate layer.
"""

from flask import Blueprint, Flask, jsonify, request

from .. import access
from ..auth import (
    check_vault_access,
    require_client_authentication,
    require_vault_permission
)
from ..model import Vault, VaultKeyError

# Create blueprint for vault routes
bp = Blueprint('vault', __name__, url_prefix='/vault')


@bp.route("/list")
@require_client_authentication()
def list_vaults(client_id, **kwargs):
    """List available vault labels"""
    try:
        # TODO: In a more sophisticated implementation, this would return
        # only the vaults that the authenticated client has access to
        return jsonify({"vaults": ["campus", "storage", "oauth"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<label>/list")
@require_client_authentication()
@require_vault_permission(access.READ)
def list_keys(client_id, label):
    """List all keys in a vault"""
    try:
        vault = Vault(label)
        keys = vault.list_keys()
        return jsonify({"label": label, "keys": keys})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<label>/<key>")
@require_client_authentication()
@require_vault_permission(access.READ)
def get_secret(client_id, label, key):
    """Get a secret from a vault"""
    try:
        vault = Vault(label)
        value = vault.get(key)
        return jsonify({"key": key, "value": value})
    except VaultKeyError:
        return jsonify({"error": f"Secret '{key}' not found in vault '{label}'"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<label>/<key>", methods=["POST"])
@require_client_authentication()
# Client needs CREATE OR UPDATE
@require_vault_permission(access.CREATE, access.UPDATE)
def set_secret(client_id, label, key):
    """Set a secret in a vault

    Requires CREATE permission for new keys, UPDATE permission for existing keys.
    The decorator ensures the client has at least one of these permissions.
    """
    try:
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
        check_vault_access(client_id, label, required_permission)

        # Perform the operation
        is_new = vault.set(key, value)
        action = "created" if is_new else "updated"

        return jsonify({
            "status": "success",
            "key": key,
            "action": action
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<label>/<key>", methods=["DELETE"])
@require_client_authentication()
@require_vault_permission(access.DELETE)
def delete_secret(client_id, label, key):
    """Delete a secret from a vault"""
    try:
        vault = Vault(label)
        deleted = vault.delete(key)

        if deleted:
            return jsonify({"status": "success", "key": key, "action": "deleted"})
        else:
            return jsonify({"error": f"Secret '{key}' not found in vault '{label}'"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def init_app(app: Flask | Blueprint) -> None:
    """Initialize the vault routes with the given Flask app or blueprint."""
    app.register_blueprint(bp)
