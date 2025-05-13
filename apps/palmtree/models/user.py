"""
User Models

This module provides classes for managing Campus users.
"""
import os

from apps.common.errors import api_errors
from apps.palmtree.models.base import ModelResponse
from common import devops
if devops.ENV in (devops.STAGING, devops.PRODUCTION):
    from common.drum.postgres import get_conn, get_drum
else:
    from common.drum.sqlite import get_conn, get_drum
from common.schema import Message, Response
from common.utils import utc_time


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
            CREATE TABLE IF NOT EXISTS "user" (
                id VARCHAR(255) PRIMARY KEY,
                email TEXT NOT NULL,
                nric_name TEXT NOT NULL,
                activated_at TEXT DEFAULT NULL
            )
        """)
    except Exception:
        # init_db() is not expected to be called in production, so we don't
        # need to handle errors gracefully.
        raise
    else:
        conn.commit()
    finally:
        conn.close()


# No need for a User class yet
class User:
    """User model for handling database operations related to users."""

    def __init__(self):
        """Initialize the OTP model with a storage interface.

        Args:
            storage: Implementation of StorageInterface for database
            operations.
        """
        self.storage = get_drum()

    def activate(self, user_id: str) -> ModelResponse:
        """Actions to perform upon first sign-in."""
        resp = self.storage.update_by_id(
            'user',
            user_id,
            {'activated_at': utc_time.now()}
        )
        match resp:
            case Response(status="error"):
                raise api_errors.InternalError()
            case Response(status="ok", message=Message.UPDATED):
                return ModelResponse("ok", "User activated")
        raise ValueError(f"Unexpected response from storage: {resp}")
    
    def new(self, user_id: str, email: str) -> ModelResponse:
        """Create a new user."""
        resp = self.storage.insert(
            'user',
            {'id': user_id, 'email': email}
        )
        match resp:
            case Response(status="error"):
                raise api_errors.InternalError()
            case Response(status="ok", message=Message.CREATED):
                return ModelResponse(**resp)
        raise ValueError(f"Unexpected response from storage: {resp}")
    
    def delete(self, user_id: str) -> ModelResponse:
        """Delete a user by id."""
        resp = self.storage.delete_by_id('user', user_id)
        match resp:
            case Response(status="error"):
                raise api_errors.InternalError()
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
        resp = self.storage.get_by_id('user', user_id)
        match resp:
            case Response(status="error"):
                raise api_errors.InternalError()
            case Response(status="ok", message=Message.FOUND):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="User not found",
                    user_id=user_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

    def update(self, user_id: str, updates: dict) -> ModelResponse:
        """Update a user by id."""
        resp = self.storage.update_by_id('user', user_id, updates)
        match resp:
            case Response(status="error"):
                raise api_errors.InternalError()
            case Response(status="ok", message=Message.UPDATED):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="User not found",
                    user_id=user_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

