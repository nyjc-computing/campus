"""vault.routes

Flask routes for the vault web API service.
"""

from flask import Blueprint, Flask, jsonify, request

# Create blueprint for vault routes
bp = Blueprint('vault', __name__, url_prefix='/vault')


@bp.route("/vaults")
def list_vaults():
    """List available vault labels"""
    try:
        # Simple implementation - just return known labels
        return jsonify({"vaults": ["campus", "storage", "oauth"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<label>/<key>")
def get_secret(label, key):
    """Get a secret from a vault"""
    try:
        # Import get_vault function locally to avoid circular imports
        from . import get_vault
        vault = get_vault(label)
        value = vault.get(key)
        return jsonify({"key": key, "value": value})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<label>/<key>", methods=["POST"])
def set_secret(label, key):
    """Set a secret in a vault"""
    try:
        # Import get_vault function locally to avoid circular imports
        from . import get_vault
        data = request.get_json()
        value = data.get("value")
        
        vault = get_vault(label)
        vault.set(key, value)
        return jsonify({"status": "success", "key": key})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def init_app(app: Flask | Blueprint) -> None:
    """Initialize the vault routes with the given Flask app or blueprint."""
    app.register_blueprint(bp)
