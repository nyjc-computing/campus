"""
User Models

This module provides classes for managing Campus users.
"""

from common.drum import DrumResponse, sqlite
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

    def activate(self, user_id: str) -> DrumResponse:
        """Actions to perform upon first sign-in."""
        return self.storage.update_by_id(
            'user',
            user_id,
            {'activated_at': utc_time.now()}
        )

    def get(self, user_id: str) -> DrumResponse:
        """Get a user by id."""
        return self.storage.get_by_id('user', user_id)

    def update(self, user_id: str, updates: dict) -> DrumResponse:
        """Update a user by id."""
        return self.storage.update_by_id('user', user_id, updates)
