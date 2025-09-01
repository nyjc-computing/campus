"""campus.vault.auth

Authentication and authorization utilities for vault routes.

This module provides utilities for authenticating clients and checking
permissions at the route level, separating these concerns from the data model.
"""

import os
from functools import wraps
from typing import Tuple

from flask import request, jsonify

from campus.common.errors import api_errors

from . import access, client


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
        raise api_errors.UnauthorizedError(
            message="CLIENT_ID missing from Authorization header or environment")
    if not client_secret:
        raise api_errors.UnauthorizedError(
            message="CLIENT_SECRET missing from Authorization header or environment")

    return client_id, client_secret


def authenticate_client() -> str:
    """Authenticate the client and return the client ID.

    Returns:
        The authenticated client ID

    Raises:
        ClientAuthenticationError: If authentication fails
    """
    client_id, client_secret = get_client_credentials()
    # Authenticate using vault's client system
    client.authenticate_client(client_id, client_secret)
    return client_id


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
        permission_str = "|".join(
            permission_names) if permission_names else str(required_permission)
        raise api_errors.ForbiddenError(
            message=f"Client '{client_id}' does not have {permission_str} permission for vault '{vault_label}'", client_id=client_id, label=vault_label, permission=permission_str)


def require_client_authentication():
    """Decorator to require client authentication only.

    This decorator:
    1. Authenticates the client
    2. Injects client_id into the route function

    Can be used alone for service-level operations, or combined with 
    require_vault_permission for vault-specific operations.

    Usage:
        # Service-level operations (client management, vault listing)
        @require_client_authentication()
        def create_client(client_id):
            # Route implementation

        # Combined with vault permission checking (place this decorator on top)
        @require_client_authentication()
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

                # Inject client_id into kwargs and call the route function
                kwargs['client_id'] = client_id
                return f(*args, **kwargs)

            except api_errors.APIError as e:
                response = jsonify(e.to_dict())
                response.status_code = getattr(e, 'status_code', 500)
                return response
            except Exception as e:
                response = jsonify(
                    {"message": f"Internal error: {e}", "error_code": "SERVER_ERROR", "details": {}})
                response.status_code = 500
                return response

        return decorated_function
    return decorator


def require_vault_permission(*required_permissions: int):
    """Decorator to require vault permission for a route.

    This decorator only checks vault permissions - it expects client_id to already
    be available (either injected by @require_client_authentication or passed directly).

    Args:
        *required_permissions: One or more permission bitflags. If multiple are provided,
                              the client needs ANY of them (OR logic), not all.
                              Examples:
                              - require_vault_permission(access.READ)
                              - require_vault_permission(access.CREATE, access.UPDATE)

    Usage:
        # Combined with client authentication (place @require_client_authentication on top)
        @require_client_authentication()
        @require_vault_permission(access.READ)
        def get_secret(client_id, label, key):
            # Route implementation

        # Multiple permissions (client needs CREATE OR UPDATE)
        @require_client_authentication()
        @require_vault_permission(access.CREATE, access.UPDATE)
        def set_secret(client_id, label, key):
            # Route can handle specific CREATE vs UPDATE logic internally

        # Or use standalone if client_id is available through other means
        @require_vault_permission(access.READ)
        def some_internal_function(client_id, label):
            # Route implementation
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # Extract client_id (should be injected by require_client_authentication)
                client_id = kwargs.get('client_id')
                if not client_id:
                    return jsonify({"error": "Client authentication required"}), 401

                # Extract vault label from route parameters
                vault_label = kwargs.get('label')
                if not vault_label:
                    return jsonify({"error": "Vault label required"}), 400

                # Check if client has ANY of the required permissions (OR logic)
                has_any_permission = False
                for permission in required_permissions:
                    if access.has_access(client_id, vault_label, permission):
                        has_any_permission = True
                        break

                if not has_any_permission:
                    # Build permission names for error message
                    permission_names = []
                    for permission in required_permissions:
                        names = []
                        if permission & access.READ:
                            names.append("READ")
                        if permission & access.CREATE:
                            names.append("CREATE")
                        if permission & access.UPDATE:
                            names.append("UPDATE")
                        if permission & access.DELETE:
                            names.append("DELETE")
                        permission_names.append(
                            "|".join(names) if names else str(permission))

                    permission_str = " OR ".join(permission_names)
                    raise api_errors.ForbiddenError(
                        message=f"Client '{client_id}' does not have {permission_str} permission for vault '{vault_label}'",
                        client_id=client_id, label=vault_label, permission=permission_str)

                # Call the route function
                return f(*args, **kwargs)

            except api_errors.ForbiddenError as e:
                response = jsonify(e.to_dict())
                response.status_code = getattr(e, 'status_code', 403)
                return response
            except Exception as e:
                response = jsonify(
                    {"message": f"Internal error: {e}", "error_code": "SERVER_ERROR", "details": {}})
                response.status_code = 500
                return response

        return decorated_function
    return decorator
