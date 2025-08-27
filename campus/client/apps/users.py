"""campus.client.apps.users

User management client for creating and managing user accounts.
"""

from campus.client.wrapper import Resource
from campus.client.interface import JsonResponse


class UserResource(Resource):
    """Represents a user resource.

    Provides an interface for interacting with individual user resources,
    including properties for accessing user data and methods for operations.
    """

    def delete(self) -> JsonResponse:
        """Delete the user."""
        response = self.client.delete(self.path)
        return response

    def get(self) -> JsonResponse:
        """Get the user."""
        response = self.client.get(self.path)
        return response

    def update(self, **kwargs) -> JsonResponse:
        """Update the user.

        Args:
            **kwargs: Fields to update (email, name, etc.)
        """
        response = self.client.patch(self.path, json=kwargs)
        return response

    def profile(self) -> JsonResponse:
        """Get the user's detailed profile."""
        response = self.client.get(self.make_path("profile"))
        return response


class UsersResource(Resource):
    """Resource for Campus /user endpoint."""

    def __getitem__(self, user_id: str) -> UserResource:
        """Get a user by ID."""
        return UserResource(self, user_id)

    def new(self, *, email: str, name: str) -> JsonResponse:
        """Create a new user."""
        data = {"email": email, "name": name}
        response = self.client.post(self.path, json=data)
        return response
