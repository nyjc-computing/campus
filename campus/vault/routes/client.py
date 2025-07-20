"""vault.routes.client

Flask routes for vault client management.

These routes handle creating, listing, retrieving, and deleting vault clients.
Admin operations require ALL permissions, read operations require READ permissions.
"""

from flask import Blueprint, Flask, jsonify, request

from .. import access, client
from ..auth import require_vault_permission

# Create blueprint for client management routes
bp = Blueprint('client', __name__, url_prefix='/client')


@bp.route("", methods=["POST"])
@require_vault_permission(access.ALL)  # Require admin-level permissions
def create_vault_client(client_id):
    """Create a new vault client
    
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
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing request body"}), 400
            
        required_fields = ["name", "description"]
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({"error": f"Missing required fields: {missing_fields}"}), 400
            
        # Create the client
        client_resource, client_secret = client.create_client(
            name=data["name"],
            description=data["description"]
        )
        
        return jsonify({
            "status": "success",
            "client": client_resource,
            "client_secret": client_secret
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("", methods=["GET"])
@require_vault_permission(access.READ)
def list_vault_clients(client_id):
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
    try:
        clients = client.list_clients()
        return jsonify({"clients": clients})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<target_client_id>", methods=["GET"])
@require_vault_permission(access.READ)
def get_vault_client(client_id, target_client_id):
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
    try:
        client_resource = client.get_client(target_client_id)
        return jsonify({"client": client_resource})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<target_client_id>", methods=["DELETE"])
@require_vault_permission(access.ALL)  # Require admin-level permissions
def delete_vault_client(client_id, target_client_id):
    """Delete a vault client
    
    DELETE /client/{client_id}
    Returns: {
        "status": "success",
        "client_id": "client_abc123",
        "action": "deleted"
    }
    """
    try:
        client.delete_client(target_client_id)
        
        return jsonify({
            "status": "success",
            "client_id": target_client_id,
            "action": "deleted"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def init_app(app: Flask | Blueprint) -> None:
    """Initialize the client routes with the given Flask app or blueprint."""
    app.register_blueprint(bp)
