"""
User Models

This module provides classes for managing Campus users.
"""

from apps.palmtree.errors import api_errors
from common.drum import sqlite
from common.schema import Message, Response
from common.utils import utc_time


def init_db():
    """Initialize the database with the necessary tables."""
    conn = sqlite.get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user (
            id VARCHAR(255) PRIMARY KEY,
            email TEXT NOT NULL,
            nric_name TEXT NOT NULL,
            activated_at TEXT NOT NULL
        )
    """)
    conn.close()


class UserResponse(Response):
    """Represents a User model response."""


# No need for a User class yet
class User:
    """User model for handling database operations related to users."""

    def __init__(self):
        """Initialize the OTP model with a storage interface.

        Args:
            storage: Implementation of StorageInterface for database
            operations.
        """
        self.storage = sqlite.SqliteDrum()

    def activate(self, user_id: str) -> UserResponse:
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
                return UserResponse("ok", "User activated")
        raise ValueError(f"Unexpected response from storage: {resp}")

    def get(self, user_id: str) -> UserResponse:
        """Get a user by id."""
        resp = self.storage.get_by_id('user', user_id)
        match resp:
            case Response(status="error"):
                raise api_errors.InternalError()
            case Response(status="ok", message=Message.FOUND):
                return UserResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                return UserResponse(*resp)
        raise ValueError(f"Unexpected response from storage: {resp}")

    def update(self, user_id: str, updates: dict) -> UserResponse:
        """Update a user by id."""
        resp = self.storage.update_by_id('user', user_id, updates)
        match resp:
            case Response(status="error"):
                raise api_errors.InternalError()
            case Response(status="ok", message=Message.UPDATED):
                return UserResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                return UserResponse(*resp)
        raise ValueError(f"Unexpected response from storage: {resp}")

