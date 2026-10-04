"""campus.audit.resources.apikeys

API key resource for Campus audit service.

URL path mapping:
    /apikeys                    → APIKeysResource (list, create)
    /apikeys/{api_key_id}       → APIKeyResource (get, update, delete)
"""

__all__ = []

import logging
from typing import Any

import campus.model as model
import campus.storage
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import secret
from campus.storage import errors as storage_errors

apikeys_storage = campus.storage.tables.get_db("apikeys")

logger = logging.getLogger(__name__)


def ensure_operator_key() -> bool:
    """Ensure the audit operator API key exists (startup bootstrap).

    The operator key is the only key class that holds the apikeys:*
    scopes, so API-key management survives the loss of every other key
    (#796: apikeys routes are scope-gated, so a key without
    apikeys:write can neither create keys nor elevate itself).

    This seed cannot go through the HTTP API: creating a key requires
    an authenticated key with apikeys:write, which cannot exist before
    the first one does (chicken-and-egg). It must be applied directly
    against storage, from the AUDIT_OPERATOR_API_KEY env var.

    Follows the campus.auth public-client bootstrap pattern
    (ensure_public_client): runs on every startup, idempotent, and an
    existing record is never modified — rotate by deleting this record
    and restarting with a new AUDIT_OPERATOR_API_KEY value.

    Returns:
        True if the key was created, False if it already existed or
        AUDIT_OPERATOR_API_KEY is unset (nothing to seed).

    Raises:
        ValueError: If AUDIT_OPERATOR_API_KEY is set but not a valid
            audit API key format (it could never authenticate).
        campus.storage.errors.StorageError: If the key record cannot
            be read or created.
    """
    import campus.config
    from campus.common import env

    plaintext = env.get("AUDIT_OPERATOR_API_KEY")
    if not plaintext:
        return False
    if not secret.is_valid_audit_api_key_format(plaintext):
        raise ValueError(
            "AUDIT_OPERATOR_API_KEY is set but not a valid audit API "
            "key format. Expected: audit_v1_<22-char-base64url> "
            "(see secret.generate_audit_api_key)"
        )

    key_id = schema.CampusID(campus.config.AUDIT_OPERATOR_API_KEY_ID)
    try:
        apikeys_storage.get_by_id(key_id)
        return False
    except storage_errors.NotFoundError:
        pass

    api_key = model.APIKey(
        id=key_id,
        name=schema.String("operator"),
        owner_id=schema.UserID("campus-devops"),
        scopes=[schema.String(scope)
                for scope in campus.config.AUDIT_OPERATOR_API_KEY_SCOPES],
        key_hash=schema.String(secret.hash_api_key(plaintext)),
    )
    try:
        apikeys_storage.insert_one(api_key.to_storage())
    except storage_errors.ConflictError:
        # Either a concurrent worker seeded this key first, or the
        # fixed id is held by some other record (never expected).
        try:
            apikeys_storage.get_by_id(key_id)
            return False  # Concurrently seeded; desired end state reached
        except storage_errors.NotFoundError:
            logger.error(
                "Cannot seed audit operator key '%s': the id is held "
                "by a different record. Remove that record, then "
                "restart the service to retry the seed.",
                key_id,
            )
            return False
    logger.info("Seeded audit operator key '%s'", key_id)
    return True


class APIKeysResource:
    """Represents the API keys resource in Campus audit API."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for API keys."""
        apikeys_storage.init_from_model("apikeys", model.APIKey)

    def __getitem__(self, api_key_id: str) -> "APIKeyResource":
        """Get an API key resource by ID.

        Maps to URL path: /apikeys/{api_key_id}

        Args:
            api_key_id: The API key identifier

        Returns:
            APIKeyResource instance
        """
        return APIKeyResource(api_key_id)

    def list_keys(
            self,
            owner_id: str | None,
            active_only: bool = True,
            limit: int = 50,
    ) -> list[model.APIKey]:
        """List API keys with optional filtering.

        Args:
            owner_id: Optional filter by owner ID
            active_only: If True, only return non-revoked keys
            limit: Optional max number of keys to return

        Returns:
            List of API keys matching the criteria
        """
        query = {}
        if owner_id is not None:
            query["owner_id"] = owner_id
        if active_only:
            query["revoked_at"] = None
        results = apikeys_storage.get_matching(
            query,
            limit=limit
        )
        return [model.APIKey.from_storage(r) for r in results]

    def new(
            self,
            name: str,
            owner_id: str,
            scopes: str,
            rate_limit: int | None = None,
            expires_at: schema.DateTime | None = None
    ) -> tuple[model.APIKey, str]:
        """Create a new API key.

        Args:
            name: Name for the API key
            owner_id: ID of the account owning the key (for organizational purposes)
            scopes: Comma-separated string of scopes/permissions
            rate_limit: Optional rate limit for the key
            expires_at: Optional expiration datetime for the key

        Returns:
            The created API key (including the plaintext key value)

        Note:
            campus.audit is a standalone service with no users/clients.
            owner_id is for organizational purposes only.
        """
        apikey_value = secret.generate_audit_api_key()
        record = {
            "name": schema.String(name),
            "owner_id": schema.UserID(owner_id),
            "scopes": [schema.String(scope) for scope in scopes.split(",")],
            "key_hash": secret.hash_api_key(apikey_value),
        }
        if rate_limit is not None:
            record["rate_limit"] = schema.Integer(rate_limit)
        if expires_at is not None:
            record["expires_at"] = schema.DateTime(expires_at)
        api_key = model.APIKey(**record)
        try:
            apikeys_storage.insert_one(api_key.to_storage())
        except storage_errors.ConflictError:
            raise api_errors.ConflictError(
                f"Conflict while inserting api_key to db: "
                f"{api_key.to_resource()}"
            ) from None
        else:
            # Audit event logged at routes layer (campus/audit/routes/apikeys.py)
            # Note: No actor tracking - campus.audit is standalone service with no users/clients
            return api_key, apikey_value

    def verify(self, api_key: str) -> model.APIKey | None:
        """Verify if the provided API key is valid and return its record.

        This method scans all API keys to find a matching hash, since
        requests contain the API key value, not the ID.

        Args:
            api_key: The plaintext API key to verify

        Returns:
            The API key model if valid and active (not expired or
            revoked), None otherwise. The model carries the key's
            scopes for the authorization layer (#575).
        """
        api_key_hash = secret.hash_api_key(api_key)

        # Query for non-revoked API keys with matching hash; expiry is
        # checked on the model below
        query = {
            "key_hash": api_key_hash,
            "revoked_at": None
        }

        try:
            results = apikeys_storage.get_matching(query, limit=1)
            if results:
                key_record = model.APIKey.from_storage(results[0])
                if not key_record.is_active():
                    return None
                # Update last_used timestamp for audit trail
                apikeys_storage.update_by_id(
                    key_record.id,
                    {"last_used": schema.DateTime.utcnow()}
                )
                return key_record
        except (storage_errors.NotFoundError, IndexError):
            pass

        return None


class APIKeyResource:
    """Represents a single API key resource."""

    def __init__(self, api_key_id: str):
        self.api_key_id = api_key_id

    def get(self) -> model.APIKey | None:
        """Get API key details by ID.

        Returns the api key if found, otherwise returns None
        """
        try:
            record = apikeys_storage.get_by_id(self.api_key_id)
        except storage_errors.NotFoundError:
            return None
        else:
            return model.APIKey.from_storage(record)

    def regenerate(self) -> str:
        """Regenerate the API key value while keeping the same ID.

        Returns:
            Hash of new API key, if successfully regenerated

        Raises:
            NotFoundError: if API key not found
        """
        new_key = secret.generate_audit_api_key()
        try:
            apikeys_storage.update_by_id(
                self.api_key_id,
                {"key_hash": secret.hash_api_key(new_key)}
            )
        except storage_errors.NotFoundError:
            raise api_errors.NotFoundError(
                f"API key {self.api_key_id} not found"
            ) from None
        else:
            # Audit event logged at routes layer (campus/audit/routes/apikeys.py)
            # Note: No actor tracking - campus.audit is standalone service with no users/clients
            return new_key

    def revoke(self) -> bool:
        """Revoke (delete) the API key."""
        try:
            apikeys_storage.update_by_id(
                self.api_key_id,
                {"revoked_at": schema.DateTime.utcnow()}
            )
        except storage_errors.NotFoundError:
            return False
        else:
            # Audit event logged at routes layer (campus/audit/routes/apikeys.py)
            # Note: No actor tracking - campus.audit is standalone service with no users/clients
            return True

    def update(self, **updates: Any) -> None:
        """Update mutable fields of the API key.

        Arguments:
            **updates: key=value pairs to update

        Raises:
            ForbiddenError if the API key has been revoked
            InvalidRequestError if one or more fields are invalid
            NotFoundError if the API key doesn't exist
        """
        if not updates:
             raise api_errors.InvalidRequestError(
                 "No mutable fields provided for update"
             )
        current = self.get()
        if current is None:
            raise api_errors.NotFoundError(
                f"API key {self.api_key_id} not found"
            ) from None
        if current.is_revoked():
            raise api_errors.ForbiddenError(
                f"API key {self.api_key_id} has been revoked and can no "
                "longer be updated"
            )
        try:
            model.APIKey.validate_update(updates)
        except ValueError as e:
            raise api_errors.InvalidRequestError(str(e)) from None
        try:
            apikeys_storage.update_by_id(self.api_key_id, updates)
        except storage_errors.NotFoundError:
            raise api_errors.NotFoundError(
                f"API key {self.api_key_id} not found"
            ) from None

        # Audit event logged at routes layer (campus/audit/routes/apikeys.py)
        # Note: No actor tracking - campus.audit is standalone service with no users/clients
