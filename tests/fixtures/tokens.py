"""tests.fixtures.tokens

Test token creation utilities for integration tests.
"""

import base64

from campus.common import devops, env, schema


def create_test_token(
    user_id: schema.UserID,
    scopes: list[str] | None = None,
    expiry_seconds: int = 3600,
    grant_vault_access: bool = True
) -> str:
    """Create a test bearer token for integration tests.

    This creates a token directly in the credentials storage,
    bypassing the OAuth flow (which requires Google).

    Args:
        user_id: The user ID to create the token for
        scopes: OAuth scopes to grant (defaults to full access)
        expiry_seconds: Token lifetime in seconds
        grant_vault_access: Whether to grant vault access to the client

    Returns:
        The bearer token string

    Example:
        >>> from tests.fixtures.tokens import create_test_token
        >>> token = create_test_token("test.user@campus.test")
        >>> headers = {"Authorization": f"Bearer {token}"}
    """
    from campus.auth import resources as auth_resources
    from campus.model import ClientAccess

    # Ensure we're in test mode
    if env.get("ENV") != devops.TESTING:
        env.ENV = devops.TESTING

    client_id = env.CLIENT_ID

    # Grant vault access to test client (for vault endpoint tests)
    if grant_vault_access and client_id:
        try:
            auth_resources.client[client_id].access.grant(
                vault_label="vault",
                permission=ClientAccess.ALL
            )
        except Exception:
            # Client may not have vault access table initialized
            pass

    # Create test user if it doesn't exist
    try:
        auth_resources.user[user_id].get()
    except Exception:
        # User doesn't exist, create it
        name = user_id.split('@')[0] if '@' in str(user_id) else str(user_id)
        auth_resources.user.new(
            id=str(user_id),
            created_at=schema.DateTime.utcnow(),
            email=str(user_id),
            name=name,
            activated_at=schema.DateTime.utcnow()  # Activate the user
        )

    # Create token via credentials resource
    token = auth_resources.credentials["campus"][user_id].new(
        client_id=client_id,
        scopes=scopes or ["read", "write"],
        expiry_seconds=expiry_seconds
    )

    return token.id


def create_test_client_credentials(
    name: str = "test-client",
    description: str = "Test client for integration tests"
) -> tuple[str, str]:
    """Create a test client with credentials.

    Returns:
        Tuple of (client_id, client_secret)

    Example:
        >>> client_id, secret = create_test_client_credentials()
        >>> encoded = base64.b64encode(f'{client_id}:{secret}'.encode()).decode()
        >>> headers = {"Authorization": f"Basic {encoded}"}
    """
    from campus.auth import resources as auth_resources

    # Create new client
    client = auth_resources.client.new(name=name, description=description)

    # Generate secret
    secret = auth_resources.client[client.id].revoke()

    return client.id, secret


def get_basic_auth_headers(client_id: str, client_secret: str) -> dict[str, str]:
    """Create Basic Auth headers from credentials.

    Args:
        client_id: The client ID
        client_secret: The client secret

    Returns:
        Headers dict with Authorization header
    """
    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def get_bearer_auth_headers(token: str) -> dict[str, str]:
    """Create Bearer Auth headers from token.

    Args:
        token: The bearer token

    Returns:
        Headers dict with Authorization header
    """
    return {"Authorization": f"Bearer {token}"}
