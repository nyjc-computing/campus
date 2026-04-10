"""campus.auth.resources.credentials

Credentials resource for Campus API.

This includes user credentials and tokens.

Credentials link an issued token to a provider, client, and user.
"""

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import secret, uid, utc_time
import campus.config as config
import campus.model as model
import campus.storage

token_storage = campus.storage.get_collection("tokens")
cred_storage = campus.storage.get_table("credentials")


class CredentialsResource:
    """Represents the credentials resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for credentials resource."""
        token_storage.init_from_model(
            "tokens", model.OAuthToken
        )
        cred_storage.init_from_model(
            "credentials", model.UserCredentials
        )

    def __getitem__(
            self,
            provider: str
    ) -> "ProviderCredentialsResource":
        """Get a credential resource by provider.

        Args:
            provider: The provider identifier

        Returns:
            ProviderCredentialsResource instance
        """
        return ProviderCredentialsResource(provider)


class ProviderCredentialsResource:
    """Represents credentials for a specific provider."""

    def __init__(self, provider: str):
        self.provider = provider

    def __getitem__(
            self,
            user_id: schema.UserID
    ) -> "UserCredentialsResource":
        """Get access token by user ID.

        Args:
            user_id: The user identifier

        Returns:
            access token (string)
        """
        return UserCredentialsResource(self, user_id)

    def get(self, token_id: str) -> model.UserCredentials:
        """Get credentials by token ID.

        Args:
            token_id: The token identifier

        Returns:
            UserCredentials instance
        """
        query: dict[str, str] = {
            "provider": self.provider,
            "token_id": token_id
        }
        records = cred_storage.get_matching(query)
        if not records:
            raise api_errors.NotFoundError(
                f"Credentials for provider {self.provider} "
                f"and token {token_id} not found."
            )
        return model.UserCredentials.from_storage(records[0])

    def list_all(
            self,
            user_id: str | None = None
    ) -> list[model.UserCredentials]:
        """List all credentials for this provider.

        Returns:
            List of UserCredentials instances
        """
        records = cred_storage.get_matching(dict(
            provider=self.provider,
            **{"user_id": user_id} if user_id else {}
        ))
        return [
            model.UserCredentials.from_storage(record)
            for record in records
        ]


class UserCredentialsResource:
    """Represents credentials for a specific user.

    Note: Credentials are issued for a specific client, so client_id
    must always be specified in operations on this resource.

    client_id while not secret is considered sensitive information and
    so is not passed in the URL path but rather as part of the request
    body.
    """

    def __init__(
            self,
            parent: ProviderCredentialsResource,
            user_id: schema.UserID
    ):
        self.parent = parent
        self.user_id = user_id

    def delete(self, client_id: str) -> None:
        """Delete credentials for this user-client."""
        cred_storage.delete_matching({
            "provider": self.parent.provider,
            "user_id": str(self.user_id),
            "client_id": client_id
        })

    def get(self, client_id: str) -> model.UserCredentials:
        """Get credentials for this user-client.

        Returns:
            UserCredentials instance with token loaded
        """
        query: dict[str, str] = {
            "provider": self.parent.provider,
            "user_id": str(self.user_id),
            "client_id": client_id
        }
        records = cred_storage.get_matching(query)
        if not records:
            raise api_errors.NotFoundError(
                f"Credentials for provider {self.parent.provider} "
                f"and user {self.user_id} not found.",
                query=query
            )
        cred_record = records[0]
        credentials = model.UserCredentials.from_storage(
            cred_record
        )
        # Load token from token_storage using token_id
        if cred_record.get('token_id'):
            token_record = token_storage.get_by_id(cred_record['token_id'])
            if token_record:
                credentials.token = model.OAuthToken.from_storage(
                    token_record
                )
        return credentials

    def new(
            self,
            *,
            client_id: str,
            scopes: list[str],
            expiry_seconds: int = (
                config.DEFAULT_TOKEN_EXPIRY_DAYS
                * utc_time.DAY_SECONDS
            ),
    ) -> model.OAuthToken:
        """Create a new Campus OAuth token."""
        assert self.parent.provider == "campus", (
            f"Unable to issue token for provider {self.parent.provider!r}"
        )
        token_id = secret.generate_access_token()
        token = model.OAuthToken(
            id=token_id,
            expiry_seconds=expiry_seconds,
            scopes=scopes,
        )
        token_storage.insert_one(token.to_storage())
        records = cred_storage.get_matching({
            "provider": self.parent.provider,
            "user_id": str(self.user_id),
        })
        if records:  # Existing credentials
            cred_storage.update_by_id(
                records[0]['id'],
                {"token_id": token_id}
            )
        else:  # New credentials
            credential = model.UserCredentials(
                id=uid.generate_category_uid("user_credentials"),
                provider=self.parent.provider,
                user_id=self.user_id,
                client_id=client_id,
                token_id=token_id
            )
            cred_storage.insert_one(credential.to_storage())
        return token

    def update(
            self,
            client_id: str,
            token: model.OAuthToken
    ) -> model.UserCredentials:
        """Update access token.

        Checks for existing credentials for this user-client pair and
        updates the token ID if it has changed. Also stores/updates
        the token itself.

        Args:
            client_id: The client identifier
            **token: Token fields to update
        """
        records = cred_storage.get_matching({
            "provider": self.parent.provider,
            "user_id": str(self.user_id),
            "client_id": client_id
        })
        if not records:  # No existing credentials
            credentials = model.UserCredentials(
                id=uid.generate_category_uid("user_credentials"),
                provider=self.parent.provider,
                user_id=self.user_id,
                client_id=client_id,
                token_id=token.id
            )
            cred_storage.insert_one(credentials.to_storage())
        elif records[0]['token_id'] != token.id:  # token_id changed
            cred_record = records[0]
            # UserCredentials.from_storage requires token
            credentials = model.UserCredentials.from_storage(
                cred_record
            )
            cred_storage.update_by_id(
                credentials.id,
                {"token_id": token.id}
            )
        else:  # token_id unchanged, just load existing credentials
            credentials = model.UserCredentials.from_storage(
                records[0]
            )
        credentials.token = token

        # Store/update token
        if token_storage.get_by_id(token.id):
            token_storage.update_by_id(token.id, token.to_storage())
        else:
            token_storage.insert_one(token.to_storage())
        return credentials
