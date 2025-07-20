"""vault.routes.access

Flask routes for vault access control management.

These routes handle granting, revoking, and checking access permissions for vault clients.
Admin operations require ALL permissions, access checking requires READ permissions.
"""

from flask import Blueprint, Flask, jsonify, request

from .. import access
from ..auth import require_vault_permission

# Create blueprint for access management routes
bp = Blueprint('access', __name__, url_prefix='/access')


@bp.route("", methods=["POST"])
@require_vault_permission(access.ALL)  # Require admin-level permissions
def grant_vault_access(client_id):
    """Grant access to a vault for a client
    
    POST /access
    Body: {
        "client_id": "target_client_id",
        "label": "vault_label", 
        "permissions": ["READ", "CREATE"] or 7
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing request body"}), 400
            
        required_fields = ["client_id", "label", "permissions"]
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({"error": f"Missing required fields: {missing_fields}"}), 400
            
        target_client_id = data["client_id"]
        label = data["label"]
        permissions = data["permissions"]
        
        # Validate permissions - should be an integer or list of permission names
        if isinstance(permissions, list):
            # Convert permission names to bitflags
            permission_map = {
                "READ": access.READ,
                "CREATE": access.CREATE, 
                "UPDATE": access.UPDATE,
                "DELETE": access.DELETE,
                "ALL": access.ALL
            }
            
            access_flags = 0
            for perm in permissions:
                if perm not in permission_map:
                    return jsonify({"error": f"Invalid permission: {perm}"}), 400
                access_flags |= permission_map[perm]
        elif isinstance(permissions, int):
            access_flags = permissions
        else:
            return jsonify({"error": "Permissions must be integer or list of permission names"}), 400
            
        # Grant the access
        access.grant_access(target_client_id, label, access_flags)
        
        return jsonify({
            "status": "success",
            "client_id": target_client_id,
            "label": label,
            "permissions": access_flags
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<target_client_id>/<label>", methods=["DELETE"])
@require_vault_permission(access.ALL)  # Require admin-level permissions
def revoke_vault_access(client_id, target_client_id, label):
    """Revoke access to a vault for a client
    
    DELETE /access/{client_id}/{label}
    """
    try:
        access.revoke_access(target_client_id, label)
        
        return jsonify({
            "status": "success",
            "client_id": target_client_id,
            "label": label,
            "action": "revoked"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<target_client_id>/<label>", methods=["GET"])
@require_vault_permission(access.READ)
def check_vault_access(client_id, target_client_id, label):
    """Check if a client has access to a vault
    
    GET /access/{client_id}/{label}
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
    """
    try:
        # Check each permission level
        permissions = {
            "READ": access.has_access(target_client_id, label, access.READ),
            "CREATE": access.has_access(target_client_id, label, access.CREATE),
            "UPDATE": access.has_access(target_client_id, label, access.UPDATE), 
            "DELETE": access.has_access(target_client_id, label, access.DELETE)
        }
        
        return jsonify({
            "client_id": target_client_id,
            "label": label,
            "permissions": permissions
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def init_app(app: Flask | Blueprint) -> None:
    """Initialize the access routes with the given Flask app or blueprint."""
    app.register_blueprint(bp)
