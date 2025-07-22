"""vault.auth

Authentication and authorization utilities for vault routes.

This module provides utilities for authenticating clients and checking
permissions at the route level, separating these concerns from the data model.
"""

import os
from functools import wraps
from typing import Tuple

from flask import request, jsonify

from . import access, client


class VaultAuthError(Exception):
    """Base exception for vault authentication errors."""
    pass


class ClientAuthenticationError(VaultAuthError):
    """Exception for client authentication failures."""
    pass


class VaultAccessDeniedError(VaultAuthError):
    """Exception for vault access permission failures."""
    
    def __init__(self, client_id: str, label: str, permission: str):
        super().__init__(
            f"Client '{client_id}' does not have {permission} permission for vault '{label}'"
        )
        self.client_id = client_id
        self.label = label
        self.permission = permission


def get_client_credentials() -> Tuple[str, str]:
    """Get client credentials from request headers or environment.
    
    First checks for Authorization header with Bearer token format,
    then falls back to environment variables.
    
    Returns:
        Tuple of (client_id, client_secret)
        
    Raises:
        ClientAuthenticationError: If credentials are missing or invalid
    """
    # Check for Authorization header first
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        # Extract token from Bearer format
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        # For now, expect format: client_id:client_secret (base64 encoded could be added later)
        if ':' in token:
            client_id, client_secret = token.split(':', 1)
            if client_id and client_secret:
                return client_id, client_secret
    
    # Fall back to environment variables
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    
    if not client_id:
        raise ClientAuthenticationError("CLIENT_ID missing from Authorization header or environment")
    if not client_secret:
        raise ClientAuthenticationError("CLIENT_SECRET missing from Authorization header or environment")
        
    return client_id, client_secret


def authenticate_client() -> str:
    """Authenticate the client and return the client ID.
    
    Returns:
        The authenticated client ID
        
    Raises:
        ClientAuthenticationError: If authentication fails
    """
    try:
        client_id, client_secret = get_client_credentials()
        
        # Authenticate using vault's client system
        client.authenticate_client(client_id, client_secret)
        return client_id
        
    except client.ClientAuthenticationError as e:
        raise ClientAuthenticationError(f"Client authentication failed: {e}") from e


def check_vault_access(client_id: str, vault_label: str, required_permission: int) -> None:
    """Check if client has required permission for vault label.
    
    Args:
        client_id: The authenticated client ID
        vault_label: The vault label to check access for
        required_permission: The permission bitflag required (READ, CREATE, UPDATE, DELETE)
        
    Raises:
        VaultAccessDeniedError: If client lacks the required permission
    """
    if not access.has_access(client_id, vault_label, required_permission):
        permission_names = []
        if required_permission & access.READ:
            permission_names.append("READ")
        if required_permission & access.CREATE:
            permission_names.append("CREATE")
        if required_permission & access.UPDATE:
            permission_names.append("UPDATE")
        if required_permission & access.DELETE:
            permission_names.append("DELETE")

        permission_str = "|".join(permission_names) if permission_names else str(required_permission)
        raise VaultAccessDeniedError(client_id, vault_label, permission_str)


def require_client_authentication():
    """Decorator to require client authentication only.
    
    This decorator:
    1. Authenticates the client
    2. Injects client_id into the route function
    
    Usage:
        @require_client_authentication()
        def create_client(client_id):
            # Route implementation
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # Authenticate client
                client_id = authenticate_client()
                
                # Inject client_id into kwargs and call the route function
                kwargs['client_id'] = client_id
                return f(*args, **kwargs)
                
            except ClientAuthenticationError as e:
                return jsonify({"error": f"Authentication failed: {e}"}), 401
            except Exception as e:
                return jsonify({"error": f"Internal error: {e}"}), 500
                
        return decorated_function
    return decorator


def require_vault_permission(required_permission: int):
    """Decorator to require vault permission for a route.
    
    This decorator:
    1. Authenticates the client
    2. Checks vault access permission
    3. Injects client_id into the route function
    
    Args:
        required_permission: The permission bitflag required (READ, CREATE, UPDATE, DELETE)
        
    Usage:
        @require_vault_permission(access.READ)
        def get_secret(client_id, label, key):
            # Route implementation
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # Authenticate client
                client_id = authenticate_client()
                
                # Extract vault label from route parameters
                vault_label = kwargs.get('label')
                if not vault_label:
                    return jsonify({"error": "Vault label required"}), 400
                
                # Check access permission
                check_vault_access(client_id, vault_label, required_permission)
                
                # Inject client_id into kwargs and call the route function
                kwargs['client_id'] = client_id
                return f(*args, **kwargs)
                
            except ClientAuthenticationError as e:
                return jsonify({"error": f"Authentication failed: {e}"}), 401
            except VaultAccessDeniedError as e:
                return jsonify({"error": f"Access denied: {e}"}), 403
            except Exception as e:
                return jsonify({"error": f"Internal error: {e}"}), 500
                
        return decorated_function
    return decorator
