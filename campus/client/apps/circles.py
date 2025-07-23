"""client.apps.circles

Circle management client for creating and managing circles.
"""

# pylint: disable=attribute-defined-outside-init

import sys
from typing import List, Dict, Any, Optional
from campus.client.base import HttpClient
from campus.client.errors import NotFoundError
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

    def add(self, user_id: str, **kwargs) -> None:
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
        self._client.patch(f"/circles/{self._circle_id}/members/{self._member_circle_id}", kwargs)


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

    def move(self, parent_circle_id: str) -> None:
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

    def new(self, name: str, description: str = "", **kwargs) -> Circle:
        """Create a new circle.
        
        Server: POST /circles

        Args:
            name: Circle name
            description: Circle description
            **kwargs: Additional circle fields

        Returns:
            Circle instance for the created circle
        """
        data = {"name": name, "description": description, **kwargs}
        response = self.post("/circles", data)
        circle_data = response.get("circle", response)
        circle_id = circle_data["id"]
        return Circle(self, circle_id)

    def set_credentials(self, client_id: str, client_secret: str) -> None:
        """Set authentication credentials.

        Args:
            client_id: The client ID for authentication
            client_secret: The client secret for authentication
        """
        super().set_credentials(client_id, client_secret)


# Module Replacement Pattern:
# Replace this module with a CirclesClient instance to support both:
# 1. Direct usage: circles["circle123"]
# 2. Class imports: from campus.client.apps.circles import CirclesClient
_module_instance = CirclesClient()
# Dynamic attribute assignment for class imports - linter warnings expected
_module_instance.CirclesClient = CirclesClient  # type: ignore[attr-defined]
_module_instance.Circle = Circle  # type: ignore[attr-defined]
sys.modules[__name__] = _module_instance  # type: ignore