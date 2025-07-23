"""client.apps.users

User management client for creating and managing user accounts.
"""

# pylint: disable=attribute-defined-outside-init

import sys
from typing import List, Dict, Any, Optional
from campus.client.base import HttpClient
from campus.client import config
from campus.client.errors import AuthenticationError


class User:
    """Represents a user resource.

    Provides an interface for interacting with individual user resources,
    including properties for accessing user data and methods for operations.
    """

    def __init__(self, users_client: HttpClient, user_id: str, data: Optional[Dict[str, Any]] = None):
        """Initialize user resource.

        Args:
            users_client: The users client instance
            user_id: The user ID
            data: User data (if already loaded)
        """
        self._client = users_client
        self._user_id = user_id
        self._data = data

    @property
    def id(self) -> str:
        """Get the user ID.

        Returns:
            str: The unique identifier for this user
        """
        return self._user_id

    @property
    def data(self) -> Dict[str, Any]:
        """Get the user data, loading it if necessary.

        Returns:
            Dict[str, Any]: The complete user data from the API
        """
        if self._data is None:
            self._data = self._client.get(f"/users/{self._user_id}")
        return self._data

    @property
    def email(self) -> str:
        """Get the user's email.

        Returns:
            str: The email address of the user
        """
        return self.data.get("email", "")

    @property
    def name(self) -> str:
        """Get the user's name.

        Returns:
            str: The display name of the user
        """
        return self.data.get("name", "")

    def __str__(self) -> str:
        """String representation of the user."""
        return f"User(id={self._user_id}, email={self.email})"

    def update(self, **kwargs) -> None:
        """Update the user.

        Args:
            **kwargs: Fields to update (email, name, etc.)
        """
        self._client.patch(f"/users/{self._user_id}", kwargs)
        # Clear cached data to force reload on next access
        self._data = None

    def delete(self) -> None:
        """Delete the user."""
        self._client.delete(f"/users/{self._user_id}")

    def get_profile(self) -> Dict[str, Any]:
        """Get the user's detailed profile.

        Returns:
            Dict[str, Any]: The user's profile data
        """
        return self._client.get(f"/users/{self._user_id}/profile")


class UsersClient(HttpClient):
    """Client for user operations following HTTP API conventions.

    Provides methods for creating, retrieving, updating, and deleting users,
    as well as managing user authentication and profile information.
    """

    def _get_default_base_url(self) -> str:
        """Get the default base URL for the users service.

        Returns:
            str: Base URL for the apps deployment
        """
        return config.get_service_base_url("users")

    def __getitem__(self, user_id: str) -> User:
        """Get a user by ID."""
        return User(self, user_id)

    def new(self, email: str, name: str) -> User:
        """Create a new user."""
        data = {"email": email, "name": name}
        response = self.post("/users", data)
        user_data = response.get("user", response)
        user_id = user_data["id"]
        return User(self, user_id, user_data)

    def me(self) -> User:
        """Get the authenticated user.

        This method requires the user to be authenticated. If the user is not
        authenticated, an AuthenticationError will be raised.

        Returns:
            User: The authenticated user instance

        Raises:
            AuthenticationError: If the user is not authenticated.
        """
        response = self.get("/me")
        user_data = response.get("user", response)
        user_id = user_data["id"]
        return User(self, user_id, user_data)

    def set_credentials(self, client_id: str, client_secret: str) -> None:
        """Set authentication credentials.

        Args:
            client_id: The client ID for authentication
            client_secret: The client secret for authentication
        """
        super().set_credentials(client_id, client_secret)


# Module Replacement Pattern:
# Replace this module with a UsersClient instance to support both:
# 1. Direct usage: users["user123"]
# 2. Class imports: from campus.client.apps.users import UsersClient
_module_instance = UsersClient()
# Dynamic attribute assignment for class imports - linter warnings expected
_module_instance.UsersClient = UsersClient  # type: ignore[attr-defined]
_module_instance.User = User  # type: ignore[attr-defined]
sys.modules[__name__] = _module_instance  # type: ignore
