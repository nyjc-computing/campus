"""client.apps.circles

Circle management client for creating and managing circles.
"""

# pylint: disable=attribute-defined-outside-init

from typing import List, Dict, Any
from campus.client.base import HttpClient
from campus.client import config


class CircleMembers:
    """Represents circle members sub-resource.

    Provides methods for managing circle membership following the server API.
    """

    def __init__(self, circles_client: HttpClient, circle_id: str):
        """Initialize circle members sub-resource.

        Args:
            circles_client: The circles client instance
            circle_id: The circle ID
        """
        self._client = circles_client
        self._circle_id = circle_id

    def list(self) -> Dict[str, Any]:
        """Get circle members and their access values.

        Server: GET /circles/{circle_id}/members

        Returns:
            Dict containing members data with access values
        """
        return self._client.get(f"/circles/{self._circle_id}/members")

    def add(self, *, user_id: str, **kwargs) -> None:
        """Add a member to the circle.

        Server: POST /circles/{circle_id}/members/add

        Args:
            user_id: User ID to add
            **kwargs: Additional parameters (e.g., role, access)
        """
        data = {"user_id": user_id, **kwargs}
        self._client.post(f"/circles/{self._circle_id}/members/add", data)

    def remove(self, user_id: str) -> None:
        """Remove a member from the circle.

        Server: DELETE /circles/{circle_id}/members/remove

        Args:
            user_id: User ID to remove
        """
        data = {"user_id": user_id}
        self._client.delete(f"/circles/{self._circle_id}/members/remove", data)

    def users(self) -> Dict[str, Any]:
        """Get users in the circle.

        Server: GET /circles/{circle_id}/users
        Status: Returns 501 (not implemented yet)

        Returns:
            Dict containing users data
        """
        return self._client.get(f"/circles/{self._circle_id}/users")

    def __getitem__(self, member_circle_id: str) -> 'CircleMember':
        """Get a specific member for updates.

        Args:
            member_circle_id: The member circle ID

        Returns:
            CircleMember instance for patch operations
        """
        return CircleMember(self._client, self._circle_id, member_circle_id)


class CircleMember:
    """Represents a specific circle member for patch operations."""

    def __init__(self, circles_client: HttpClient, circle_id: str, member_circle_id: str):
        """Initialize circle member resource.

        Args:
            circles_client: The circles client instance
            circle_id: The circle ID
            member_circle_id: The member circle ID
        """
        self._client = circles_client
        self._circle_id = circle_id
        self._member_circle_id = member_circle_id

    def update(self, **kwargs) -> None:
        """Update a member's access in the circle.

        Server: PATCH /circles/{circle_id}/members/{member_circle_id}

        Args:
            **kwargs: Fields to update (e.g., access)
        """
        self._client.patch(
            f"/circles/{self._circle_id}/members/{self._member_circle_id}", kwargs)


class Circle:
    """Represents a circle resource.

    Provides an interface for interacting with individual circle resources.
    Does not encapsulate data, only provides methods for operations.
    """

    def __init__(self, circles_client: HttpClient, circle_id: str):
        """Initialize circle resource.

        Args:
            circles_client: The circles client instance
            circle_id: The circle ID
        """
        self._client = circles_client
        self._circle_id = circle_id

    @property
    def id(self) -> str:
        """Get the circle ID.

        Returns:
            str: The unique identifier for this circle
        """
        return self._circle_id

    def get(self) -> Dict[str, Any]:
        """Get circle details.

        Server: GET /circles/{circle_id}

        Returns:
            Dict[str, Any]: The complete circle data from the API
        """
        return self._client.get(f"/circles/{self._circle_id}")

    @property
    def data(self) -> Dict[str, Any]:
        """Get circle data (convenience property).

        Returns:
            Dict[str, Any]: The complete circle data from the API
        """
        return self.get()

    def update(self, **kwargs) -> None:
        """Update the circle.

        Server: PATCH /circles/{circle_id}

        Args:
            **kwargs: Fields to update (name, description, etc.)
        """
        self._client.patch(f"/circles/{self._circle_id}", kwargs)

    def delete(self) -> None:
        """Delete the circle.

        Server: DELETE /circles/{circle_id}
        """
        self._client.delete(f"/circles/{self._circle_id}")

    @property
    def members(self) -> CircleMembers:
        """Get the members sub-resource.

        Returns:
            CircleMembers: Sub-resource for member management
        """
        return CircleMembers(self._client, self._circle_id)

    def move(self, *, parent_circle_id: str) -> None:
        """Move the circle to a new parent.

        Server: POST /circles/{circle_id}/move
        Status: Not implemented (returns 501)

        Args:
            parent_circle_id: ID of the new parent circle

        Raises:
            ValueError: If parent_circle_id is the same as the current circle ID
        """
        if parent_circle_id == self._circle_id:
            raise ValueError(
                "The parent_circle_id cannot be the same as the current circle ID.")
        data = {"parent_circle_id": parent_circle_id}
        self._client.post(f"/circles/{self._circle_id}/move", data)

    def __str__(self) -> str:
        """String representation of the circle."""
        return f"Circle(id={self._circle_id})"

    def __repr__(self) -> str:
        """Detailed string representation of the circle."""
        return f"Circle(id={self._circle_id})"


class CirclesClient(HttpClient):
    """Client for circle operations following HTTP API conventions.

    Provides methods for creating, retrieving, updating, and deleting circles,
    following the actual server API implementation.
    """

    def _get_default_base_url(self) -> str:
        """Get the default base URL for the circles service.

        Returns:
            str: Base URL for the apps deployment
        """
        return config.get_service_base_url("circles")

    def __getitem__(self, circle_id: str) -> Circle:
        """Get a circle by ID.

        Args:
            circle_id: The circle ID

        Returns:
            Circle instance
        """
        return Circle(self, circle_id)

    def new(self, *, name: str, description: str = "", **kwargs) -> Dict[str, Any]:
        """Create a new circle.

        Server: POST /circles

        Args:
            name: Circle name
            description: Circle description
            **kwargs: Additional circle fields

        Returns:
            Dict[str, Any]: The created circle data
        """
        data = {"name": name, "description": description, **kwargs}
        response = self.post("/circles", data)
        return response.get("circle", response)

    def update(self, *, circle_id: str, **kwargs) -> Dict[str, Any]:
        """Update a circle.

        Args:
            circle_id: The circle ID to update
            **kwargs: Fields to update (name, description, etc.)

        Returns:
            Dict[str, Any]: The updated circle data
        """
        response = self.patch(f"/circles/{circle_id}", kwargs)
        return response.get("circle", response)

    def get_circle(self, circle_id: str) -> Dict[str, Any]:
        """Get a circle by ID.

        Args:
            circle_id: The circle ID

        Returns:
            Dict[str, Any]: The circle data
        """
        response = super().get(f"/circles/{circle_id}")
        return response.get("circle", response)
