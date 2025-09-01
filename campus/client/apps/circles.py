"""campus.client.apps.circles

Circle management client for creating and managing circles.
"""

from typing import Any

from campus.client.interface import Resource
from campus.common.http import JsonClient, JsonResponse


class CircleMembers(Resource):
    """Represents circle members sub-resource.

    Provides methods for managing circle membership following the server API.
    """

    def list(self) -> JsonResponse:
        """Get circle members and their access values."""
        response = self.client.get(self.path)
        return response

    def add(self, *, member_id: str, **kwargs) -> JsonResponse:
        """Add a member to the circle.

        Args:
            member_id: User ID to add
            **kwargs: Additional parameters (e.g., role, access)
        """
        data = {"member_id": member_id, **kwargs}
        response = self.client.post(self.make_path("add"), json=data)
        return response

    def remove(self, member_id: str) -> JsonResponse:
        """Remove a member from the circle.

        Args:
            member_id: User ID to remove
        """
        data = {"member_id": member_id}
        response = self.client.delete(self.make_path("remove"), json=data)
        return response

    def set(self, member_id: str, access_value: int) -> JsonResponse:
        """Set circle member access.

        Args:
            member_id: User ID to remove
            access_value: Access value to set
        """
        data = {"member_id": member_id, "access_value": access_value}
        response = self.client.put(self.make_path("set"), json=data)
        return response


class CircleResource(Resource):
    """Represents a single circle resource.

    Provides an interface for interacting with individual circle resources.
    Does not encapsulate data, only provides methods for operations.
    """

    def __init__(self, parent: "CirclesResource", circle_id: str):
        """Initialize circle resource.

        Args:
            circles_client: The circles client instance
            circle_id: The circle ID
        """
        super().__init__(parent, circle_id)
        self.circle_id = circle_id

    @property
    def members(self) -> CircleMembers:
        """Get the members sub-resource."""
        return CircleMembers(self, "members")

    def delete(self) -> JsonResponse:
        """Delete the circle."""
        response = self.client.delete(self.path)
        return response

    def get(self) -> JsonResponse:
        """Get circle details."""
        response = self.client.get(self.path)
        return response

    def move(self, *, parent_circle_id: str) -> JsonResponse:
        """Move the circle to a new parent.

        Args:
            parent_circle_id: ID of the new parent circle

        Raises:
            ValueError: If parent_circle_id is the same as the current circle ID
        """
        if parent_circle_id == self.circle_id:
            raise ValueError(
                "The parent_circle_id cannot be the same as the current circle ID.")
        data = {"parent_circle_id": parent_circle_id}
        response = self.client.post(self.make_path("move"), json=data)
        return response

    def update(self, **kwargs) -> JsonResponse:
        """Update the circle.

        Args:
            **kwargs: Fields to update (name, description, etc.)
        """
        response = self.client.patch(self.path, json=kwargs)
        return response


class CirclesResource(Resource):
    """Resource for Campus /circles endpoint."""

    def __init__(self, client: JsonClient):
        super().__init__(client, "circles")

    def __getitem__(self, circle_id: str) -> CircleResource:
        """Get a circle by ID.

        Args:
            circle_id: The circle ID
        """
        return CircleResource(self, circle_id)

    def list(self, **filters: Any) -> JsonResponse:
        """Return a list of matching circles.

        Args:
            **filters: Optional filters to apply (e.g., name, tag)
        """
        response = self.client.get(self.path, params=filters)
        return response

    def new(self, *, name: str, description: str = "", **kwargs) -> JsonResponse:
        """Create a new circle.

        Args:
            name: Circle name
            description: Circle description
            **kwargs: Additional circle fields
        """
        data = {"name": name, "description": description, **kwargs}
        response = self.client.post(self.path, json=data)
        return response
