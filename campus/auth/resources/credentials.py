"""campus.auth.resources.credentials

Credentials resource for Campus API.

This includes user credentials and tokens.

Credentials link an issued token to a provider, client, and user.
"""

import campus.config as config
import campus.model as model
import campus.storage
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import secret, uid, utc_time

token_storage = campus.storage.get_collection("tokens")
cred_storage = campus.storage.get_table("credentials")
app_cred_storage = campus.storage.get_table("app_credentials")


class CredentialsResource:
    """Represents the credentials resource in Campus API Schema."""

    def list_connections(
            self,
            user_id: schema.UserID | str,
    ) -> list[model.UserCredentials]:
        """List a user's upstream connections (design §2.7, #733).

        Every non-campus credential row for the user, with the linked
        token loaded where one exists. Campus login tokens are not
        connections (invariant C5): they are revoked via /oauth/revoke,
        not listed or disconnected here.
        """
        records = cred_storage.get_matching({"user_id": str(user_id)})
        connections: list[model.UserCredentials] = []
        for record in records:
            if record["provider"] == "campus":
                continue
            connections.append(
                self._with_token(model.UserCredentials.from_storage(record))
            )
        return connections

    def disconnect(
            self,
            provider: str,
            user_id: schema.UserID | str,
    ) -> list[model.UserCredentials]:
        """Delete all of a user's credential rows for a provider, plus
        the token records they point at (design §2.7: the same
        primitive as UserCredentialsResource.delete + token cleanup).

        Returns the deleted rows with tokens loaded, so callers can
        audit what was removed and answer 404 when nothing was.
        """
        records = cred_storage.get_matching({
            "provider": provider,
            "user_id": str(user_id),
        })
        deleted: list[model.UserCredentials] = []
        for record in records:
            credentials = self._with_token(
                model.UserCredentials.from_storage(record)
            )
            cred_storage.delete_by_id(record["id"])
            if record.get("token_id"):
                token_storage.delete_by_id(record["token_id"])
            deleted.append(credentials)
        return deleted

    @staticmethod
    def _with_token(credentials: model.UserCredentials) -> model.UserCredentials:
        """Load the linked token record into a credential, if any."""
        if credentials.token_id:
            token_record = token_storage.get_by_id(credentials.token_id)
            if token_record:
                credentials.token = model.OAuthToken.from_storage(
                    token_record
                )
        return credentials

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for credentials resource."""
        token_storage.init_from_model(
            "tokens", model.OAuthToken
        )
        cred_storage.init_from_model(
            "credentials", model.UserCredentials
        )
        app_cred_storage.init_from_model(
            "app_credentials", model.AppCredentials
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
            user_id: schema.UserID | str
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

    def get_by_refresh_token(
            self,
            refresh_token: str
    ) -> model.UserCredentials:
        """Get credentials by refresh token value.

        Resolves the token record by its refresh_token field, then the
        credential record linked to that token via token_id.

        Args:
            refresh_token: The refresh token string

        Returns:
            UserCredentials instance with token loaded
        """
        token_records = token_storage.get_matching(
            {"refresh_token": refresh_token}
        )
        if not token_records:
            raise api_errors.NotFoundError(
                "Credentials for this refresh token not found."
            )
        token_record = token_records[0]
        records = cred_storage.get_matching({
            "provider": self.provider,
            "token_id": token_record["id"],
        })
        if not records:
            raise api_errors.NotFoundError(
                f"Credentials for provider {self.provider} and token "
                f"{token_record['id']} not found."
            )
        credentials = model.UserCredentials.from_storage(records[0])
        credentials.token = model.OAuthToken.from_storage(token_record)
        return credentials

    def revoke(
            self,
            *,
            token: str,
            client_id: str,
            token_type_hint: str | None = None,
    ) -> bool:
        """Revoke a token and its linked credential records (RFC 7009).

        Lookup follows the token_type_hint ("access_token" or
        "refresh_token"), falling back to the other token type when
        the hinted lookup misses (RFC 7009 section 2.1). Revoking
        either value kills the whole pair: both live on one token
        record, and bearer authentication resolves the credential by
        token id, so deleting the credential record invalidates the
        access token immediately.

        The client_id must match the credential record's client; a
        mismatch revokes nothing — one client must not be able to
        revoke another client's tokens.

        Args:
            token: The access token or refresh token value
            client_id: The client requesting the revocation
            token_type_hint: Optional RFC 7009 token type hint

        Returns:
            True if a credential record was revoked, False if no
            matching record exists (callers return 200 either way per
            RFC 7009 section 2.2).
        """
        lookups = (self._find_token_id_by_access,
                   self._find_token_id_by_refresh)
        if token_type_hint == "refresh_token":
            lookups = tuple(reversed(lookups))
        for lookup in lookups:
            token_id = lookup(token)
            if token_id is not None:
                return self._revoke_token_record(token_id, client_id)
        return False

    def _find_token_id_by_access(self, token: str) -> str | None:
        """Resolve an access token value to its token record id.

        An access token is stored as the token record's id.
        """
        if token_storage.get_by_id(token):
            return token
        return None

    def _find_token_id_by_refresh(self, token: str) -> str | None:
        """Resolve a refresh token value to its token record id."""
        records = token_storage.get_matching({"refresh_token": token})
        if records:
            return records[0]["id"]
        return None

    def _revoke_token_record(self, token_id: str, client_id: str) -> bool:
        """Delete the credential and token records for a token id.

        Covers both credential families: user credentials (this
        provider's rows) and app credentials from the
        client_credentials grant. Only records belonging to client_id
        are deleted; if none match, nothing is revoked.
        """
        records = cred_storage.get_matching({
            "provider": self.provider,
            "token_id": token_id,
        })
        matching = [r for r in records if r["client_id"] == client_id]
        if not matching:
            return app_credentials.revoke_token(token_id, client_id)
        for record in matching:
            cred_storage.delete_by_id(record["id"])
        token_storage.delete_by_id(token_id)
        return True

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
            user_id: schema.UserID | str
    ):
        self.parent = parent
        self.user_id = schema.UserID(user_id)

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
            expires_in: int = (
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
            expires_in=expires_in,
            scopes=scopes,
        )
        token_storage.insert_one(token.to_storage())
        records = cred_storage.get_matching({
            "provider": self.parent.provider,
            "user_id": str(self.user_id),
            "client_id": client_id,
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
            # The superseded token record must not linger: its refresh
            # token would stay resolvable, making a rotated refresh
            # token replayable (#678)
            token_storage.delete_by_id(cred_record['token_id'])
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


class AppCredentialsResource:
    """Represents the app (client-scoped) credentials resource.

    Holds the single live token issued per confidential client via the
    client_credentials grant (RFC 6749 section 4.4). The client is the
    resource owner — there is no user — so bearer authentication
    resolves these credentials to a client only.
    """

    def get(self, token_id: str) -> model.AppCredentials:
        """Get app credentials by token ID.

        Args:
            token_id: The token identifier (the access token value)

        Returns:
            AppCredentials instance with token loaded

        Raises:
            api_errors.NotFoundError: If no app credential links this
                token to a client
        """
        records = app_cred_storage.get_matching({"token_id": token_id})
        if not records:
            raise api_errors.NotFoundError(
                f"App credentials for token {token_id} not found."
            )
        credentials = model.AppCredentials.from_storage(records[0])
        token_record = token_storage.get_by_id(token_id)
        if token_record:
            credentials.token = model.OAuthToken.from_storage(token_record)
        return credentials

    def issue(self, client_id: str, scopes: list[str]) -> model.OAuthToken:
        """Issue (or reuse) the client's live app token.

        Reuse semantics: when the client already holds an unexpired
        token carrying exactly the requested scopes, it is returned
        as-is. Downstream clients (campus-python's with_app_session)
        fetch a token per call, so without reuse every call would mint
        and retain a new token record. Any mismatch — no live token,
        expiry, or a different scope set — supersedes: a fresh token is
        issued and the replaced token record deleted (invariant A5,
        docs/auth-token-invariants.md).

        App tokens never carry a refresh token (RFC 6749 section 4.4.3);
        expiry is handled by re-running the grant.

        Args:
            client_id: The confidential client identifier
            scopes: The validated scope list (already checked against
                the client's allowlist by the caller, invariant A1)

        Returns:
            OAuthToken instance for the client's live app session
        """
        records = app_cred_storage.get_matching({"client_id": client_id})
        old_token_record = None
        if records:
            old = model.AppCredentials.from_storage(records[0])
            if old.token_id:
                old_token_record = token_storage.get_by_id(old.token_id)
            if old_token_record is not None:
                existing = model.OAuthToken.from_storage(old_token_record)
                if not existing.is_expired() and set(existing.scopes) == set(scopes):
                    return existing

        token = model.OAuthToken(
            id=secret.generate_access_token(),
            expires_in=config.DEFAULT_TOKEN_EXPIRY_DAYS * utc_time.DAY_SECONDS,
            scopes=scopes,
        )
        token_storage.insert_one(token.to_storage())
        if records:
            app_cred_storage.update_by_id(
                records[0]["id"],
                {"token_id": token.id}
            )
            # Supersession is deletion (invariant A5): the replaced
            # token record must not linger as a resolvable bearer.
            if old_token_record is not None:
                token_storage.delete_by_id(old_token_record["id"])
        else:
            credential = model.AppCredentials(
                id=uid.generate_category_uid("app_credentials"),
                client_id=client_id,
                token_id=token.id,
            )
            app_cred_storage.insert_one(credential.to_storage())
        return token

    def revoke_token(self, token_id: str, client_id: str) -> bool:
        """Delete the app credential and token records for a token id.

        The client_id must match the credential record's client; a
        mismatch revokes nothing, mirroring the user-credential
        revocation rules (RFC 7009 section 2.2).

        Returns:
            True if an app credential record was revoked, False if no
            matching record exists
        """
        records = app_cred_storage.get_matching({"token_id": token_id})
        matching = [r for r in records if r["client_id"] == client_id]
        if not matching:
            return False
        for record in matching:
            app_cred_storage.delete_by_id(record["id"])
        token_storage.delete_by_id(token_id)
        return True


app_credentials = AppCredentialsResource()
