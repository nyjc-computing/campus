"""campus.client.apps.users

User management client for creating and managing user accounts.
"""

from campus.client.interface import Resource
from campus.common.http import JsonClient


class UserResource(Resource):
    """Represents a user resource.

    Provides an interface for interacting with individual user resources,
    including properties for accessing user data and methods for operations.
    """

    def delete(self) -> dict:
        """Delete the user."""
        response = self.client.delete(self.path)
        return self._process_response(response)  # type: ignore[return-value]

    def get(self) -> dict:
        """Get the user."""
        response = self.client.get(self.path)
        return self._process_response(response)  # type: ignore[return-value]

    def update(self, **kwargs) -> dict:
        """Update the user.

        Args:
            **kwargs: Fields to update (email, name, etc.)
        """
        response = self.client.patch(self.path, json=kwargs)
        return self._process_response(response)  # type: ignore[return-value]

    def profile(self) -> dict:
        """Get the user's detailed profile."""
        response = self.client.get(self.make_path("profile"))
        return self._process_response(response)  # type: ignore[return-value]


class UsersResource(Resource):
    """Resource for Campus /user endpoint."""

    def __init__(self, client: JsonClient, *, raw: bool = False):
        super().__init__(client, "users", raw=raw)

    def __getitem__(self, user_id: str) -> UserResource:
        """Get a user by ID."""
        return UserResource(self, user_id)

    def new(self, *, email: str, name: str) -> dict:
        """Create a new user."""
        data = {"email": email, "name": name}
        response = self.client.post(self.path, json=data)
        return self._process_response(response)  # type: ignore[return-value]
