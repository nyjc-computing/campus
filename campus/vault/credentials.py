"""campus.vault.credentials

Credential management for Campus Vault clients.

This module provides functionality for managing client credentials,
including creating, updating, and deleting credentials, as well as
retrieving them for authentication purposes.

Credentials follow the JWT standard and are used for all OAuth2 providers,
including Campus itself.

The JWT claims are interpreted as follows (all claims are optional by spec):
- `iss`: The issuer of the token (the provider)
- `sub`: The subject of the token (the user_id)
- `aud`: The audience of the token (the client_id)
- `exp`: Expiration time
- `nbf`: Not before time (treated as alias of iat)
- `iat`: Issued at time
- `jti`: JWT ID (access_token)
OAuth2 specific claims:
- `client_id`: The client ID associated with the token (alias of jti)
- `scope`: Scopes associated with the token
- `auth_time`: Time of authentication (not used)

Note that refresh tokens are issued separately.

The schema fields follow the abbreviated naming conventions of JWT claims.
but aliased properties are provided for ease of use.

Since credentials follow an RFC spec, they are not part of the Campus API
Schema and do not extend BaseRecord; they are not expected to have `id` or
`created_at` fields.
"""

import dataclasses

from campus.common import devops, schema
from campus.common.errors import api_errors
from campus.common.utils import secret

from . import db

CLAIMS = (
    "iss", "sub", "aud", "exp", "nbf", "iat", "jti",
    "scope", "refresh_token"
)
DEFAULT_EXPIRY_SECONDS = 3600  # 1 hour
TABLE = "credentials"


@devops.block_env(devops.PRODUCTION)
def init_db():
    """Initialize the vault client table.

    This function is intended to be called only in a test or staging
    environment.
    """
    with db.get_connection_context() as conn:
        with conn.cursor() as cursor:
            client_schema = f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    iss TEXT,  -- issuer (provider)
                    sub TEXT,  -- subject (user_id)
                    aud TEXT,  -- audience (client_id)
                    exp INTEGER,  -- expiration
                    iat INTEGER,  -- issued at
                    jti TEXT,  -- JWT ID (access_token)
                    scope TEXT,
                    refresh_token TEXT,
                    PRIMARY KEY (iss, sub, aud),
                    CHECK(exp > iat)
                )
            """
            cursor.execute(client_schema)


def get_provider(provider: str) -> "ProviderCredentials":
    """Get a ProviderCredentials instance for the given provider.

    This is a convenience function for programmatic access to provider
    credentials.

    For the new architecture, this returns a ProviderCredentials model
    instance. Authentication and permission checking should be handled
    at the application layer.
    """
    return ProviderCredentials(provider)


@dataclasses.dataclass(frozen=True)
class JWToken:
    """JWToken representation for credentials.
    
    Issued JWTokens should not be modified after creation.
    Revoke and re-issue instead.

    Fields are optional following JWT spec (RFC 7519).
    """
    iss: str | None = None
    sub: str | None = None
    aud: str | None = None
    exp: int | None = None
    iat: int | None = None
    jti: str | None = None
    scope: str | None = None
    refresh_token: str | None = None

    @property
    def nbf(self) -> int | None:
        return self.iat

    @property
    def provider(self) -> str | None:
        return self.iss

    @property
    def client_id(self) -> str | None:
        return self.aud

    @property
    def user_id(self) -> str | None:
        return self.sub

    @property
    def issued_at(self) -> schema.DateTime | None:
        return schema.DateTime.from_timestamp(self.iat) if self.iat else None

    @property
    def expires_at(self) -> schema.DateTime | None:
        return schema.DateTime.from_timestamp(self.exp) if self.exp else None

    @property
    def access_token(self) -> str | None:
        return self.jti

    @property
    def scopes(self) -> list[str]:
        return self.scope.split(" ") if self.scope else []

    def to_dict(self) -> dict[str, object | None]:
        """Convert the JWToken to a dictionary."""
        return {
            claim: getattr(self, claim)
            for claim in CLAIMS
            if getattr(self, claim) is not None
        }

    def to_tuple(self) -> tuple:
        """Convert the JWToken to a tuple for database insertion."""
        return (
            self.iss,
            self.sub,
            self.aud,
            self.exp,
            self.iat,
            self.jti,
            self.scope,
            self.refresh_token
        )

    def get_missing_scopes(self, requested_scopes: list[str]) -> list[str]:
        """Validate the requested scopes against the token's granted scopes.
        Returns the missing scopes.
        """
        return [
            scope for scope in requested_scopes
            if scope not in self.scopes
        ]

    def replace(self, **changes) -> "JWToken":
        """Return a new JWToken with the given changes applied."""
        return dataclasses.replace(self, **changes)


class ProviderCredentials:

    def __init__(self, provider: str):
        self.provider = provider

    def create_credentials(
        self,
        *,
        user_id: schema.UserID | None = None,
        client_id: schema.CampusID | None,
        expiry_seconds: int = DEFAULT_EXPIRY_SECONDS,
        issued_at: schema.DateTime | None = None,
        access_token: str | None = None,
        scopes: list[str] | None = None,
        refresh_token: str | None = None,
    ) -> JWToken:
        """Create new credentials for a given provider, client, and user.

        Args:
            issued_at: The time the credentials are issued (default: now)
            client_id: The client ID associated with the credentials
            user_id: The user ID associated with the credentials
            scopes: The scopes to associate with the credentials
            expires_in: Expiration time in seconds (default: 3600)
        """
        issued_at = issued_at or schema.DateTime.utcnow()
        expires_at = schema.DateTime.utcafter(issued_at, seconds=expiry_seconds)
        token = JWToken(
            iss=self.provider,
            sub=user_id,
            aud=client_id,
            exp=expires_at.to_timestamp(),
            iat=issued_at.to_timestamp() if issued_at else None,
            jti=access_token or secret.generate_access_token(),
            scope=" ".join(scopes) if scopes else None,
            refresh_token=refresh_token
        )
        self.store_credentials(token)
        return token

    def delete_credentials(
        self,
        *,
        client_id: schema.CampusID | None = None,
        user_id: schema.UserID | None = None
    ) -> None:
        """Delete credentials by provider and either client_id or user_id.

        Args:
            client_id: The client ID associated with the credentials
            user_id: The user ID associated with the credentials
        """
        match_queries = []
        match_params = [self.provider]
        if client_id is not None:
            match_queries.append("aud = ?")
            match_params.append(client_id)
        if user_id is not None:
            match_queries.append("sub = ?")
            match_params.append(user_id)
        if not match_queries:
            raise api_errors.InvalidRequestError(
                message="Either client_id or user_id must be provided"
            )
        where_clause = " AND ".join(match_queries)
        with db.get_connection_context() as conn:
            db.execute_query(
                conn,
                f"""
                DELETE FROM {TABLE}
                WHERE iss = ? AND {where_clause}
                """,
                match_params
            )

    def get_credentials(
            self,
            *,
            client_id: schema.CampusID,
            user_id: schema.UserID
    ) -> JWToken:
        """Retrieve credentials by provider and either client_id or user_id.

        Args:
            client_id: The client ID associated with the credentials
            user_id: The user ID associated with the credentials

        Returns:
            The credentials record
        """
        with db.get_connection_context() as conn:
            record = db.execute_query(
                conn,
                f"""
                SELECT * FROM {TABLE}
                WHERE iss = %s AND aud = %s AND sub = %s
                """,
                (self.provider, client_id, user_id),
                fetch_one=True
            )
            if not record:
                raise api_errors.NotFoundError(
                    message="Credentials not found",
                    provider=self.provider,
                    client_id=client_id,
                    user_id=user_id
                )            
            return JWToken(**record)

    def list_by_client(
            self,
            client_id: schema.CampusID
    ) -> list[JWToken]:
        """List all credentials for a given client ID.

        Args:
            client_id: The client ID associated with the credentials

        Returns:
            A list of JWToken objects
        """
        with db.get_connection_context() as conn:
            records = db.execute_query(
                conn,
                f"""
                SELECT * FROM {TABLE}
                WHERE iss = %s AND aud = %s
                """,
                (self.provider, client_id),
                fetch_all=True
            )
            if records is None:
                return []
            return [JWToken(**record) for record in records]

    def list_by_user(
            self,
            user_id: schema.UserID
    ) -> list[JWToken]:
        """List all credentials for a given user ID.

        Args:
            user_id: The user ID associated with the credentials

        Returns:
            A list of JWToken objects
        """
        with db.get_connection_context() as conn:
            records = db.execute_query(
                conn,
                f"""
                SELECT * FROM {TABLE}
                WHERE iss = %s AND sub = %s
                """,
                (self.provider, user_id),
                fetch_all=True
            )
            if records is None:
                return []
            return [JWToken(**record) for record in records]

    def store_credentials(
        self,
        token: JWToken
    ) -> None:
        """Store credentials in the database.

        Args:
            token: The JWToken object to store
        """
        # Credentials may already exist; overwrite them
        with db.get_connection_context() as conn:
            db.execute_query(
                conn,
                f"""
                INSERT INTO {TABLE}
                    (iss, sub, aud, exp, iat, jti, scope, refresh_token)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (iss, sub, aud) DO UPDATE SET
                    exp = EXCLUDED.exp,
                    iat = EXCLUDED.iat,
                    jti = EXCLUDED.jti,
                    scope = EXCLUDED.scope,
                    refresh_token = EXCLUDED.refresh_token
                """,
                token.to_tuple(),
                fetch_one=False,
                fetch_all=False
            )
