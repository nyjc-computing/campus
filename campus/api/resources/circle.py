"""campus.api.resources.circle

Circle resource for Campus API.
"""

import typing

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid
import campus.model
import campus.storage

circle_storage = campus.storage.get_collection("circles")

# TODO: Make domain configurable
DOMAIN = "nyjc.edu.sg"


def _from_record(
        record: dict[str, typing.Any],
) -> campus.model.Circle:
    """Convert a storage record to a Circle model instance."""
    return campus.model.Circle(
        id=schema.CampusID(record['id']),
        created_at=schema.DateTime(record['created_at']),
        name=record['name'],
        description=record.get('description', ''),
        tag=record['tag'],
        members=record.get('members', {}),
        sources=record.get('sources', {})
    )


def get_circle_meta() -> dict:
    """Get the circle meta record from the circles collection."""
    try:
        circle_metas = circle_storage.get_matching({"@meta": True})
    except Exception as e:
        raise api_errors.InternalError.from_exception(e) from e

    if not circle_metas:
        raise api_errors.NotFoundError(
            f"Circle meta record not found in collection circles",
            id=DOMAIN
        )

    assert len(circle_metas) == 1, (
        circle_metas, "Expected exactly one circle meta record"
    )
    return circle_metas[0]


def update_circle_meta(update: dict) -> None:
    """Update the circle meta record in the circles collection."""
    try:
        circle_storage.update_matching(
            {"@meta": True},
            update
        )
    except Exception as e:
        raise api_errors.InternalError.from_exception(e) from e


class CirclesResource:
    """Represents the circles resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for circle management."""
        # Initialize the collection (creates it if needed)
        circle_storage.init_collection()

        # Ensure meta record exists
        try:
            meta_record = get_circle_meta()
        except api_errors.NotFoundError:
            # Circle meta record not found in collection
            circle_storage.insert_one({
                schema.CAMPUS_KEY: uid.generate_category_uid("meta", length=8),
                "created_at": schema.DateTime.utcnow(),
                "@meta": True
            })
            meta_record = get_circle_meta()

        # Check for existing root circle, otherwise create one
        root_circles = circle_storage.get_matching({"name": DOMAIN})
        assert len(root_circles) <= 1, (
            root_circles, "More than one root circle found"
        )
        if not root_circles:
            root_circle = CirclesResource().new(
                name=DOMAIN,
                description="Root circle",
                tag="root",
                parents={}
            )
        else:
            root_circle = _from_record(root_circles[0])

        if "root" not in meta_record or not meta_record["root"]:
            update_circle_meta(
                {
                    "root": root_circle.id,
                    root_circle.id: {}
                }
            )

        # Check for existing admin circle, otherwise create one
        admin_circles = circle_storage.get_matching({"name": "campus-admin"})
        assert len(admin_circles) <= 1, (
            admin_circles, "More than one admin circle found"
        )
        if not admin_circles:
            CirclesResource().new(
                name="campus-admin",
                description="Campus admin circle",
                tag="admin",
                parents={root_circle.id: 15}
            )

    def __getitem__(self, circle_id: schema.CampusID) -> "CircleResource":
        """Get a circle resource by circle ID.

        Args:
            circle_id: The circle ID

        Returns:
            CircleResource instance
        """
        return CircleResource(circle_id)

    @property
    def members(self) -> "CircleMembersResource":
        """Get the circle members resource.

        Returns:
            CircleMembersResource instance
        """
        return CircleMembersResource(self)

    def list(self, **filters: typing.Any) -> list[campus.model.Circle]:
        """List all circles matching the given filters.

        Args:
            **filters: Keyword arguments to filter the circles

        Returns:
            List of Circle instances
        """
        try:
            records = circle_storage.get_matching(filters)
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return [_from_record(record) for record in records]

    def new(self, **fields: typing.Any) -> campus.model.Circle:
        """Create a new circle.

        Args:
            **fields: Fields for circle creation (name, description, tag, parents)

        Returns:
            Circle instance

        Raises:
            ConflictError: For validation errors or storage conflicts
        """
        parents = fields.pop("parents", {})
        if fields["tag"] == "root" and len(parents) > 0:
            raise api_errors.ConflictError(
                "Root circle cannot have parents",
                id=fields["tag"]
            )

        circle_id = schema.CampusID(
            uid.generate_category_uid("circle", length=8)
        )
        circle = campus.model.Circle(
            id=circle_id,
            created_at=schema.DateTime.utcnow(),
            name=fields["name"],
            description=fields.get("description", ""),
            tag=fields["tag"],
            members={},
            sources={}
        )

        try:
            circle_storage.insert_one(circle.to_storage())
            for parent_id, access_value in parents.items():
                self.members.add(
                    parent_id,
                    member_id=circle_id,
                    access_value=access_value
                )
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        return circle


class CircleResource:
    """Represents a single circle in Campus API Schema."""

    def __init__(self, circle_id: schema.CampusID):
        self.circle_id = circle_id

    @property
    def members(self) -> "CircleMembersResource":
        """Get the circle members resource for this specific circle.

        Returns:
            CircleMembersResource instance bound to this circle
        """
        resource = CircleMembersResource(CirclesResource())
        resource._circle_id = self.circle_id
        return resource

    def delete(self) -> None:
        """Delete the circle.

        Raises:
            ConflictError: If circle not found
            InternalError: For storage errors
        """
        try:
            circle_storage.delete_by_id(self.circle_id)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Circle not found",
                id=self.circle_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def get(self) -> campus.model.Circle:
        """Get the circle record.

        Returns:
            Circle instance

        Raises:
            ConflictError: If circle not found
            InternalError: For storage errors
        """
        try:
            record = circle_storage.get_by_id(self.circle_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Circle not found",
                    id=self.circle_id
                )
            return _from_record(record)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Circle not found",
                id=self.circle_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def update(self, **updates: typing.Any) -> None:
        """Update the circle record.

        Args:
            **updates: Fields to update (name, description)

        Raises:
            ConflictError: If circle not found
            InternalError: For storage errors
        """
        try:
            circle_storage.update_by_id(self.circle_id, updates)
        except campus.storage.errors.NoChangesAppliedError:
            return None  # No changes applied, nothing to do
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Circle not found",
                id=self.circle_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e


class CircleMembersResource:
    """Represents the circle members resource in Campus API Schema."""

    def __init__(self, parent: CirclesResource):
        self._parent = parent
        self._circle_id: schema.CampusID | None = None

    def list(self, circle_id: schema.CampusID) -> dict[str, int]:
        """List all members of a circle.

        Args:
            circle_id: The circle ID

        Returns:
            Dictionary mapping member IDs to access values

        Raises:
            ConflictError: If circle not found
            InternalError: For storage errors
        """
        try:
            record = circle_storage.get_by_id(circle_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Circle not found",
                    id=circle_id
                )
            return record.get("members", {})
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Circle not found",
                id=circle_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def add(
            self,
            circle_id: schema.CampusID,
            member_id: schema.CampusID,
            access_value: int
    ) -> None:
        """Add a member to a circle.

        Args:
            circle_id: The parent circle ID
            member_id: The member circle ID to add
            access_value: The access level for the member

        Raises:
            ConflictError: If member circle not found or no changes applied
            InternalError: For storage errors
        """
        # Check if member circle exists
        try:
            member_circle = circle_storage.get_by_id(member_id)
            if member_circle is None:
                raise api_errors.ConflictError(
                    "Member circle not found",
                    id=member_id
                )
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Member circle not found",
                id=member_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        # Use direct MongoDB access for nested field updates
        try:
            circle_storage.update_by_id(
                circle_id,
                {f"members.{member_id}": access_value},
            )
        except campus.storage.errors.NoChangesAppliedError:
            raise api_errors.ConflictError(
                "No changes applied when adding member",
                id=circle_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def remove(
            self,
            circle_id: schema.CampusID,
            member_id: schema.CampusID
    ) -> None:
        """Remove a member from a circle.

        Args:
            circle_id: The parent circle ID
            member_id: The member circle ID to remove

        Raises:
            ConflictError: If circle not found or member not in circle
            InternalError: For storage errors
        """
        # Check if member circle is a member of circle
        try:
            circle = circle_storage.get_by_id(circle_id)
            if circle is None:
                raise api_errors.ConflictError(
                    "Circle not found",
                    id=circle_id
                )
            if member_id not in circle.get("members", {}):
                raise api_errors.ConflictError(
                    "Member not found in circle",
                    id=member_id
                )
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Circle not found",
                id=circle_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        # Use direct MongoDB access for nested field updates
        try:
            circle_storage.update_by_id(
                circle_id,
                {f"members.{member_id}": None},
            )
        except campus.storage.errors.NoChangesAppliedError:
            raise api_errors.ConflictError(
                "No changes applied when removing member",
                id=circle_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def set(
            self,
            circle_id: schema.CampusID,
            member_id: schema.CampusID,
            access_value: int
    ) -> None:
        """Set the access level of a member in a circle.

        Args:
            circle_id: The parent circle ID
            member_id: The member circle ID
            access_value: The new access level

        Raises:
            ConflictError: If member circle not found
            InternalError: For storage errors
        """
        # For now, set and add operations are identical
        self.add(circle_id, member_id, access_value)
