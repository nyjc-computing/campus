"""campus.vault.auth

Authentication and authorization utilities for vault routes.

This module provides utilities for authenticating clients and checking
permissions at the route level, separating these concerns from the data model.
"""

import logging
from functools import wraps
from typing import Tuple

from flask import request, jsonify, g

from campus.common.errors import api_errors

from . import access, client

# Set up detailed logging for authentication debugging
auth_logger = logging.getLogger('campus.vault.auth')
auth_logger.setLevel(logging.DEBUG)


def get_client_credentials() -> Tuple[str, str]:
    """Get client credentials from request headers or environment.

    First checks for Authorization header with Basic or Bearer token format,
    then falls back to environment variables.

    Returns:
        Tuple of (client_id, client_secret)

    Raises:
        ClientAuthenticationError: If credentials are missing or invalid
    """
    auth_logger.debug("🔍 AUTH: Starting credential extraction")
    auth_logger.debug(f"🔍 AUTH: Request path: {request.path}")
    auth_logger.debug(f"🔍 AUTH: Request method: {request.method}")

    # Check for Authorization header first
    auth_header = request.headers.get('Authorization')
    auth_logger.debug(
        f"🔍 AUTH: Authorization header present: {bool(auth_header)}")

    if auth_header:
        auth_logger.debug(f"🔍 AUTH: Auth header type: {auth_header[:20]}...")
        if auth_header.startswith('Basic '):
            # Handle Basic authentication
            auth_logger.debug("🔍 AUTH: Processing Basic authentication")
            from campus.common.utils.secret import decode_http_basic_auth
            try:
                client_id, client_secret = decode_http_basic_auth(auth_header)
                if client_id and client_secret:
                    auth_logger.debug(
                        f"🔍 AUTH: Basic auth successful - client_id: {client_id}")
                    return client_id, client_secret
                else:
                    auth_logger.debug(
                        "🔍 AUTH: Basic auth failed - empty credentials")
            except ValueError as e:
                auth_logger.debug(f"🔍 AUTH: Basic auth decode error: {e}")
                pass  # Fall through to other auth methods
        elif auth_header.startswith('Bearer '):
            # Extract token from Bearer format
            auth_logger.debug("🔍 AUTH: Processing Bearer authentication")
            token = auth_header[7:]  # Remove 'Bearer ' prefix
            # For now, expect format: client_id:client_secret (base64 encoded could be added later)
            if ':' in token:
                client_id, client_secret = token.split(':', 1)
                if client_id and client_secret:
                    auth_logger.debug(
                        f"🔍 AUTH: Bearer auth successful - client_id: {client_id}")
                    return client_id, client_secret
                else:
                    auth_logger.debug(
                        "🔍 AUTH: Bearer auth failed - empty credentials")
            else:
                auth_logger.debug("🔍 AUTH: Bearer token missing ':' separator")

    # No valid credentials found in Authorization header
    auth_logger.error(
        "🔍 AUTH: No valid credentials found in Authorization header")
    raise api_errors.UnauthorizedError(
        message="Authentication required. Provide credentials in Authorization header.")


def authenticate_client() -> str:
    """Authenticate the client and return the client ID.

    Returns:
        The authenticated client ID

    Raises:
        ClientAuthenticationError: If authentication fails
    """
    auth_logger.debug("🔍 AUTH: Starting client authentication")
    try:
        client_id, client_secret = get_client_credentials()
        auth_logger.debug(f"🔍 AUTH: Got credentials for client: {client_id}")

        # Authenticate using vault's client system
        auth_logger.debug("🔍 AUTH: Calling client.authenticate_client")
        client.authenticate_client(client_id, client_secret)
        auth_logger.debug(
            f"🔍 AUTH: Client authentication successful for: {client_id}")
        return client_id
    except Exception as e:
        auth_logger.error(f"🔍 AUTH: Client authentication failed: {e}")
        raise


def check_vault_access(client_id: str, vault_label: str, required_permission: int) -> None:
    """Check if client has required permission for vault label.

    Args:
        client_id: The authenticated client ID
        vault_label: The vault label to check access for
        required_permission: The permission bitflag required (READ, CREATE, UPDATE, DELETE)

    Raises:
        VaultAccessDeniedError: If client lacks the required permission
    """
    auth_logger.debug(
        f"🔍 AUTH: Checking vault access for client {client_id}, label '{vault_label}', permission {required_permission}")

    has_permission = access.has_access(
        client_id, vault_label, required_permission)
    auth_logger.debug(f"🔍 AUTH: Access check result: {has_permission}")

    if not has_permission:
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


def require_client_authentication(f):
    """Decorator to require client authentication only.

    This decorator:
    1. Authenticates the client
    2. Injects client into the flask g context

    Can be used alone for service-level operations, or combined with 
    require_vault_permission for vault-specific operations.

    Usage:
        # Service-level operations (client management, vault listing)
        @require_client_authentication
        def create_client():
            # Route implementation

        # Combined with vault permission checking (place this decorator on top)
        @require_client_authentication
        @require_vault_permission(access.READ)
        def get_secret(label, key):
            # Route implementation
    """
    # Errors are caught by error handler
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_logger.debug(
            f"🔍 AUTH: Starting authentication for route: {f.__name__}")
        auth_logger.debug(f"🔍 AUTH: Route args: {args}, kwargs: {kwargs}")

        try:
            client_id = authenticate_client()
            auth_logger.debug(f"🔍 AUTH: Client authenticated: {client_id}")

            client_info = client.get_client(client_id)
            g.current_client = client_info
            auth_logger.debug(f"🔍 AUTH: Client info loaded for {client_id}")

            result = f(*args, **kwargs)
            auth_logger.debug(
                f"🔍 AUTH: Route {f.__name__} completed successfully")
            return result
        except Exception as e:
            auth_logger.error(f"🔍 AUTH: Route {f.__name__} failed: {e}")
            raise
    return decorated_function


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
            auth_logger.debug(
                f"🔍 AUTH: Starting vault permission check for route: {f.__name__}")
            auth_logger.debug(
                f"🔍 AUTH: Required permissions: {required_permissions}")
            auth_logger.debug(f"🔍 AUTH: Route kwargs: {kwargs}")

            try:
                # Extract client_id (should be injected by require_client_authentication)
                client_id = kwargs.get('client_id')
                if not client_id:
                    auth_logger.debug(
                        "🔍 AUTH: No client_id in kwargs - checking g.current_client")
                    # Try to get from Flask g context
                    if hasattr(g, 'current_client') and g.current_client:
                        client_id = g.current_client.get('id')
                        auth_logger.debug(
                            f"🔍 AUTH: Got client_id from g.current_client: {client_id}")
                    else:
                        auth_logger.error("🔍 AUTH: No client_id available")
                        return jsonify({"error": "Client authentication required"}), 401

                # Extract vault label from route parameters
                vault_label = kwargs.get('label')
                auth_logger.debug(
                    f"🔍 AUTH: Vault label from kwargs: {vault_label}")

                if not vault_label:
                    auth_logger.error("🔍 AUTH: No vault label in kwargs")
                    return jsonify({"error": "Vault label required"}), 400

                # Check if client has ANY of the required permissions (OR logic)
                has_any_permission = False
                for permission in required_permissions:
                    auth_logger.debug(
                        f"🔍 AUTH: Checking permission {permission} for client {client_id} on label '{vault_label}'")
                    if access.has_access(client_id, vault_label, permission):
                        auth_logger.debug(
                            f"🔍 AUTH: Permission {permission} granted")
                        has_any_permission = True
                        break
                    else:
                        auth_logger.debug(
                            f"🔍 AUTH: Permission {permission} denied")

                if not has_any_permission:
                    auth_logger.error(
                        f"🔍 AUTH: Access denied - client {client_id} lacks required permissions for vault '{vault_label}'")
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
