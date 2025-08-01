"""campus.models.user

This module provides classes for managing Campus users.
"""
from typing import NotRequired, TypedDict, Unpack

from campus.models.base import BaseRecord
from campus.common.errors import api_errors
from campus.common.utils import uid, utc_time
from campus.common import devops
from campus.storage import get_table
from campus.storage import errors as storage_errors

TABLE = "users"


@devops.block_env(devops.PRODUCTION)
def init_db():
    """Initialize the tables needed by the model.

    This function is intended to be called only in a test environment (using a
    local-only db like SQLite), or in a staging environment before upgrading to
    production.
    """
    storage = get_table(TABLE)
    schema = f"""
        CREATE TABLE IF NOT EXISTS "{TABLE}" (
            id TEXT PRIMARY KEY NOT NULL,
            email TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            activated_at TEXT DEFAULT NULL,
            UNIQUE(email)
        )
    """
    storage.init_table(schema)


class UserNew(TypedDict, total=True):
    """Request body schema for a users.new operation."""
    email: str
    name: str


class UserUpdate(TypedDict, total=False):
    """Request body schema for a users.update operation."""
    # Currently nothing for the user to update yet


class UserResource(UserNew, BaseRecord, TypedDict, total=True):
    """Response body schema representing the result of a users.get operation."""
    activated_at: NotRequired[utc_time.datetime]


class User:
    """User model for handling database operations related to users."""

    def __init__(self):
        """Initialize the User model with a table storage interface."""
        self.storage = get_table(TABLE)

    def activate(self, email: str) -> None:
        """Actions to perform upon first sign-in."""
        user_id = uid.generate_user_uid(email)
        try:
            self.storage.update_by_id(user_id, {'activated_at': utc_time.now()})
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="User not found",
                user_id=user_id
            )
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def new(self, **fields: Unpack[UserNew]) -> UserResource:
        """Create a new user."""
        user_id = uid.generate_user_uid(fields["email"])
        record = dict(
            id=user_id,
            created_at=utc_time.now(),
            **fields,
            # do not activate user on creation
        )
        try:
            self.storage.insert_one(record)
        except storage_errors.ConflictError as e:
            raise api_errors.ConflictError(
                message="User already exists",
                user_id=user_id,
                error=e
            ) from e
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
        else:
            return record  # type: ignore

    def delete(self, user_id: str) -> None:
        """Delete a user by id."""
        try:
            self.storage.delete_by_id(user_id)
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="User not found",
                user_id=user_id
            ) from e
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def get(self, user_id: str) -> UserResource:
        """Get a user by id."""
        try:
            user = self.storage.get_by_id(user_id)
        except storage_errors.NotFoundError as e:
            raise api_errors.NotFoundError(
                message="User not found",
                user_id=user_id
            ) from e
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
        else:
            return user  # type: ignore

    def update(self, user_id: str, **updates: Unpack[UserUpdate]) -> None:
        """Update a user by id."""
        try:
            self.storage.update_by_id(user_id, dict(updates))
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="User not found",
                user_id=user_id
            ) from e
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
