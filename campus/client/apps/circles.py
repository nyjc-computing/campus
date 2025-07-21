"""client.apps.circles

Circle (group) management client for creating and managing organizational units.
"""

import sys
from typing import List, Dict, Any, Optional
from campus.client.base import BaseClient
from campus.client.errors import NotFoundError
from campus.client import config


class Circle:
    """Represents a circle resource with HTTP-like methods.

    Provides an interface for interacting with individual circle resources,
    including properties for accessing circle data and methods for operations.
    """

    def __init__(self, circles_client: BaseClient, circle_id: str, data: Optional[Dict[str, Any]] = None):
        """Initialize circle resource.

        Args:
            circles_client: The circles client instance
            circle_id: The circle ID
            data: Circle data (if already loaded)
        """
        self._client = circles_client
        self._circle_id = circle_id
        self._data = data

    @property
    def id(self) -> str:
        """Get the circle ID.

        Returns:
            str: The unique identifier for this circle
        """
        return self._circle_id

    @property
    def data(self) -> Dict[str, Any]:
        """Get the circle data, loading it if necessary.

        Returns:
            Dict[str, Any]: The complete circle data from the API
        """
        if self._data is None:
            self._data = self._client._get(f"/circles/{self._circle_id}")
        return self._data

    @property
    def name(self) -> str:
        """Get the circle's name.

        Returns:
            str: The display name of the circle
        """
        return self.data.get("name", "")

    @property
    def description(self) -> str:
        """Get the circle's description.

        Returns:
            str: The description text of the circle
        """
        return self.data.get("description", "")

    @property
    def created_at(self) -> str:
        """Get the circle's creation timestamp.

        Returns:
            str: ISO formatted timestamp of when the circle was created
        """
        return self.data.get("created_at", "")

    @property
    def owner_id(self) -> str:
        """Get the circle owner's user ID.

        Returns:
            str: The user ID of the circle's owner
        """
        return self.data.get("owner_id", "")

    def update(self, **kwargs) -> None:
        """Update the circle.

        Args:
            **kwargs: Fields to update (name, description, etc.)
        """
        self._client._put(f"/circles/{self._circle_id}", kwargs)
        # Clear cached data to force reload on next access
        self._data = None

    def delete(self) -> None:
        """Delete the circle."""
        self._client._delete(f"/circles/{self._circle_id}")

    def members(self) -> List[Dict[str, Any]]:
        """Get circle members.

        Returns:
            List of member data with user info and role
        """
        response = self._client._get(f"/circles/{self._circle_id}/members")
        return response.get("members", [])

    def add_member(self, user_id: str, role: str = "member") -> None:
        """Add a member to the circle.

        Args:
            user_id: User ID to add
            role: Member role (default: "member")
        """
        self._client._post(f"/circles/{self._circle_id}/members", {
            "user_id": user_id,
            "role": role
        })

    def remove_member(self, user_id: str) -> None:
        """Remove a member from the circle.

        Args:
            user_id: User ID to remove
        """
        self._client._delete(f"/circles/{self._circle_id}/members/{user_id}")

    def update_member_role(self, user_id: str, role: str) -> None:
        """Update a member's role in the circle.

        Args:
            user_id: User ID to update
            role: New role for the member
        """
        self._client._put(f"/circles/{self._circle_id}/members/{user_id}", {
            "role": role
        })

    def is_member(self, user_id: str) -> bool:
        """Check if a user is a member of the circle.

        Args:
            user_id: User ID to check

        Returns:
            True if user is a member, False otherwise
        """
        try:
            self._client._get(f"/circles/{self._circle_id}/members/{user_id}")
            return True
        except NotFoundError:
            return False

    def move(self, parent_circle_id: str) -> None:
        """Move the circle to a new parent.

        Args:
            parent_circle_id: ID of the new parent circle

        Raises:
            ValueError: If parent_circle_id is the same as the current circle ID
        """
        if parent_circle_id == self._circle_id:
            raise ValueError("The parent_circle_id cannot be the same as the current circle ID.")
        self._client._post(f"/circles/{self._circle_id}/move", {
            "parent_circle_id": parent_circle_id
        })

    def get_users(self) -> List[Dict[str, Any]]:
        """Get users in the circle.

        Returns:
            List of user data with role information
        """
        response = self._client._get(f"/circles/{self._circle_id}/users")
        return response.get("users", [])

    def __str__(self) -> str:
        """String representation of the circle."""
        return f"Circle(id={self._circle_id}, name={self.name})"

    def __repr__(self) -> str:
        """Detailed string representation of the circle."""
        return f"Circle(id={self._circle_id}, name={self.name}, description={self.description})"


class CirclesClient(BaseClient):
    """Client for circle operations following HTTP API conventions.

    Provides methods for creating, retrieving, updating, and deleting circles,
    as well as managing circle memberships and relationships.
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

    def get_by_id(self, circle_id: str) -> Circle:
        """Get a circle by ID (alternative to __getitem__).

        Args:
            circle_id: The circle ID

        Returns:
            Circle instance
        """
        return self[circle_id]

    def new(self, name: str, description: str = "", **kwargs) -> Circle:
        """Create a new circle.

        Args:
            name: Circle name
            description: Circle description
            **kwargs: Additional circle fields

        Returns:
            Circle instance for the created circle
        """
        data = {"name": name, "description": description, **kwargs}
        response = self._post("/circles", data)
        circle_data = response.get("circle", response)
        circle_id = circle_data["id"]
        return Circle(self, circle_id, circle_data)

    def list(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Circle]:
        """List all circles.

        Args:
            limit: Maximum number of circles to return
            offset: Number of circles to skip

        Returns:
            List of Circle instances
        """
        params = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset

        response = self._get("/circles", params=params if params else None)
        circles_data = response.get("circles", [])

        return [
            Circle(self, circle_data["id"], circle_data)
            for circle_data in circles_data
        ]

    def search(self, query: str) -> List[Circle]:
        """Search for circles.

        Args:
            query: Search query (name, description, etc.)

        Returns:
            List of matching Circle instances
        """
        response = self._get("/circles/search", params={"q": query})
        circles_data = response.get("circles", [])

        return [
            Circle(self, circle_data["id"], circle_data)
            for circle_data in circles_data
        ]

    def list_by_user(self, user_id: str) -> List[Circle]:
        """List circles that a user is a member of.

        Args:
            user_id: User ID to get circles for

        Returns:
            List of Circle instances
        """
        response = self._get(f"/users/{user_id}/circles")
        circles_data = response.get("circles", [])

        return [
            Circle(self, circle_data["id"], circle_data)
            for circle_data in circles_data
        ]


class CirclesModule:
    """Custom module wrapper that supports subscription syntax."""

    def __init__(self):
        self._client = CirclesClient()

    def __getitem__(self, circle_id: str) -> Circle:
        """Support circles["circle123"] syntax."""
        return self._client[circle_id]

    def get_by_id(self, circle_id: str) -> Circle:
        """Get a circle by ID."""
        return self._client.get_by_id(circle_id)

    def new(self, name: str, description: str = "", **kwargs) -> Circle:
        """Create a new circle."""
        return self._client.new(name, description, **kwargs)

    def list(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Circle]:
        """List all circles."""
        return self._client.list(limit, offset)

    def search(self, query: str) -> List[Circle]:
        """Search for circles."""
        return self._client.search(query)

    def list_by_user(self, user_id: str) -> List[Circle]:
        """List circles that a user is a member of."""
        return self._client.list_by_user(user_id)

    def set_credentials(self, client_id: str, client_secret: str) -> None:
        """Set authentication credentials."""
        self._client.set_credentials(client_id, client_secret)

    @property
    def client(self) -> CirclesClient:
        """Direct access to the client instance."""
        return self._client


# Replace this module with our custom class
sys.modules[__name__] = CirclesModule()  # type: ignore
