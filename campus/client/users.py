"""client.users

User management client for creating and managing user accounts.
"""

import sys
from typing import List, Dict, Any, Optional
from .base import BaseClient


class User:
    """Represents a user resource."""

    def __init__(self, users_client: BaseClient, user_id: str, data: Optional[Dict[str, Any]] = None):
        """Initialize user resource."""
        self._client = users_client
        self._user_id = user_id
        self._data = data

    @property
    def id(self) -> str:
        """Get the user ID."""
        return self._user_id

    @property
    def data(self) -> Dict[str, Any]:
        """Get the user data, loading it if necessary."""
        if self._data is None:
            self._data = self._client._get(f"/users/{self._user_id}")
        return self._data

    @property
    def email(self) -> str:
        """Get the user's email."""
        return self.data.get("email", "")

    @property
    def name(self) -> str:
        """Get the user's name."""
        return self.data.get("name", "")

    def __str__(self) -> str:
        """String representation of the user."""
        return f"User(id={self._user_id}, email={self.email})"


class UsersClient(BaseClient):
    """Client for user operations following HTTP API conventions."""

    def _get_default_base_url(self) -> str:
        """Get the default base URL for the users service."""
        return "https://api.campus.nyjc.dev"

    def __getitem__(self, user_id: str) -> User:
        """Get a user by ID."""
        return User(self, user_id)

    def new(self, email: str, name: str) -> User:
        """Create a new user."""
        data = {"email": email, "name": name}
        response = self._post("/users", data)
        user_data = response.get("user", response)
        user_id = user_data["id"]
        return User(self, user_id, user_data)

    def list(self) -> List[User]:
        """List all users."""
        response = self._get("/users")
        users_data = response.get("users", [])

        return [
            User(self, user_data["id"], user_data)
            for user_data in users_data
        ]


class UsersModule:
    """Custom module wrapper that supports subscription syntax."""

    def __init__(self):
        self._client = UsersClient()

    def __getitem__(self, user_id: str) -> User:
        """Support users["user123"] syntax."""
        return self._client[user_id]

    def new(self, email: str, name: str) -> User:
        """Create a new user."""
        return self._client.new(email, name)

    def list_users(self) -> List[User]:
        """List all users."""
        return self._client.list()

    def set_credentials(self, client_id: str, client_secret: str) -> None:
        """Set authentication credentials."""
        self._client.set_credentials(client_id, client_secret)

    @property
    def client(self) -> UsersClient:
        """Direct access to the client instance."""
        return self._client


# Replace this module with our custom class
sys.modules[__name__] = UsersModule()  # type: ignore
