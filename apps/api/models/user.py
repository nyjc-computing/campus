"""
User Models

This module provides classes for managing Campus users.
"""
import os

from typing import NotRequired, TypedDict, Unpack

from apps.common.errors import api_errors
from apps.api.models.base import BaseRecord, ModelResponse
from common import devops
from common.schema import Message, Response
from common.utils import utc_time
from common.validation.record import validate_keys
if devops.ENV in (devops.STAGING, devops.PRODUCTION):
    from common.drum.postgres import get_conn, get_drum
else:
    from common.drum.sqlite import get_conn, get_drum

TABLE = "users"


def init_db():
    """Initialize the tables needed by the model.

    This function is intended to be called only in a test environment (using a
    local-only db like SQLite), or in a staging environment before upgrading to
    production.
    """
    # TODO: Refactor into decorator
    if os.getenv('ENV', 'development') == 'production':
        raise AssertionError(
            "Database initialization detected in production environment"
        )
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS "users" (
                id TEXT PRIMARY KEY NOT NULL,
                email TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                activated_at TEXT DEFAULT NULL,
                UNIQUE(email)
            )
        """)
    except Exception:  # pylint: disable=try-except-raise
        # init_db() is not expected to be called in production, so we don't
        # need to handle errors gracefully.
        raise
    else:
        conn.commit()
    finally:
        conn.close()


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
        """Initialize the OTP model with a storage interface.

        Args:
            storage: Implementation of StorageInterface for database
            operations.
        """
        self.storage = get_drum()

    def activate(self, email: str) -> ModelResponse:
        """Actions to perform upon first sign-in."""
        user_id, _ = email.split('@')
        resp = self.storage.update_by_id(
            TABLE,
            user_id,
            {'activated_at': utc_time.now()}
        )
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.UPDATED):
                return ModelResponse("ok", "User activated")
        raise ValueError(f"Unexpected response from storage: {resp}")
    
    def new(self, **fields: Unpack[UserNew]) -> ModelResponse:
        """Create a new user."""
        validate_keys(fields, UserNew.__annotations__, required=True)
        user_id, _ = fields["email"].split('@')
        record = UserResource(
            id=user_id,
            created_at=utc_time.now(),
            **fields,
            # do not activate user on creation
        )
        resp = self.storage.insert(TABLE, record)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.SUCCESS):
                return ModelResponse(status="ok", message=Message.CREATED, data=resp.data)
        raise ValueError(f"Unexpected response from storage: {resp}")
    
    def delete(self, user_id: str) -> ModelResponse:
        """Delete a user by id."""
        resp = self.storage.delete_by_id(TABLE, user_id)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.DELETED):
                return ModelResponse(**resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="User not found",
                    user_id=user_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

    def get(self, user_id: str) -> ModelResponse:
        """Get a user by id."""
        resp = self.storage.get_by_id(TABLE, user_id)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.FOUND):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="User not found",
                    user_id=user_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

    def update(self, user_id: str, **updates: Unpack[UserUpdate]) -> ModelResponse:
        """Update a user by id."""
        resp = self.storage.update_by_id(TABLE, user_id, updates)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.UPDATED):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="User not found",
                    user_id=user_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

