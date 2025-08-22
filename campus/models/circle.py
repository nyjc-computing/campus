"""campus.models.circle

This module provides classes for managing Campus circles.

Data structures:
- collections (Circle)
- address tree

Main operations:
- CRUD
- resolve source access for a particular user
- get flat list of users (leaf circles) of any circle
- move circles
"""

from collections.abc import Iterator, Mapping
from typing import NotRequired, TypedDict, Unpack

from campus.common.errors import api_errors
from campus.common.schema import CampusID
from campus.common.utils import uid, utc_time
from campus.common import devops
from campus.models.base import BaseRecord
from campus.storage import (
    errors as storage_errors,
    get_collection
)

# TODO: Replace with OpenAPI-based string-pattern schema
AccessValue = int
CircleID = CampusID
CirclePath = str
CircleTag = str
CircleTree = dict[CircleID, "CircleTree"]

# TODO: Make domain configurable
DOMAIN = "nyjc.edu.sg"
COLLECTION = "circles"


# TODO: Refactor settings into a separate model
@devops.block_env(devops.PRODUCTION)
def init_db():
    """Initialize the collections needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    For MongoDB, collections are created automatically on first insert.
    """
    # Initialize the collection (creates it if needed)
    storage = get_collection(COLLECTION)
    storage.init_collection()

    # Ensure meta record exists
    try:
        meta_record = get_circle_meta()
    except api_errors.NotFoundError:
        # Circle meta record not found in collection
        storage.insert_one({
            # The meta document id is unused but required by the
            # storage interface
            "id": uid.generate_category_uid("meta", length=8),
            "created_at": utc_time.now(),
            "@meta": True
        })
        meta_record = get_circle_meta()

    # Check for existing root circle, otherwise create one
    root_circles = storage.get_matching({"name": DOMAIN})
    assert len(root_circles) <= 1, (
        root_circles, "More than one root circle found"
    )
    if not root_circles:
        root_circle = Circle().new(
            name=DOMAIN,
            description="Root circle",
            tag="root",
            parents={}
        )
    else:
        root_circle = root_circles[0]
    if "root" not in meta_record or not meta_record["root"]:
        update_circle_meta(
            {
                "root": root_circle["id"],
                root_circle["id"]: {}
            }
        )
    # Check for existing admin circle, otherwise create one
    admin_circles = storage.get_matching({"name": "campus-admin"})
    assert len(admin_circles) <= 1, (
        admin_circles, "More than one admin circle found"
    )
    if not admin_circles:
        admin_circle = Circle().new(
            name="campus-admin",
            description="Campus admin circle",
            tag="admin",
            parents={root_circle["id"]: 15}
        )
    else:
        admin_circle = admin_circles[0]


class CircleNew(TypedDict, total=True):
    """Request body schema for a circles.new operation.

    Circles must be created with at least one parent (default: admin).
    The `parents` property maps the circle's full path
      ({parent path} / {circle_id}) to its access value in that parent.
    """
    name: str
    description: NotRequired[str]
    tag: CircleTag
    parents: NotRequired[dict[CirclePath, AccessValue]]


class CircleUpdate(TypedDict, total=False):
    """Request body schema for a circles.update operation."""
    name: str
    description: str
    # tag cannot be updated once created


class CircleRecord(BaseRecord):
    """The circle record stored in the circle collection."""
    name: str
    description: NotRequired[str]
    tag: CircleTag
    members: dict[CircleID, AccessValue]


class CircleResource(CircleRecord, total=False):
    """Response body schema representing the result of a circles.get operation."""
    # TODO: store ancestry tree
    # ancestry: CircleTree
    sources: dict  # SourceID, SourceHeader


class CircleMemberRemove(TypedDict):
    """Request body schema for a circles.members.remove operation"""
    member_id: CircleID


class CircleMemberAdd(CircleMemberRemove):
    """Request body schema for a circles.members.add operation"""
    access_value: AccessValue


class CircleMemberSet(CircleMemberRemove):
    """Request body schema for a circles.members.set operation"""
    access_value: AccessValue


# Meta record classes and helper functions

class CircleMeta(TypedDict, total=False):
    """Circle meta schema for the circles collection.

    A meta record is used to store metadata about the circle collection.
    This record must be present before any circle operations are attempted.
    This is used to store the root circle and the address tree.
    """
    root: CircleID
    # Some keys are required but (intentionally) are unrepresentable
    # in TypedDict
    # These are added here for documentation purposes
    # @meta: bool  # always True
    # <circle_id>: CircleTree  # circle address tree


def get_circle_meta() -> dict:
    """Get the circle meta record from the settings collection."""
    storage = get_collection(COLLECTION)
    try:
        circle_metas = storage.get_matching({"@meta": True})
        if not circle_metas:
            raise api_errors.NotFoundError(
                message=f"Circle meta record not found in collection {COLLECTION}",
                id=DOMAIN
            )
        assert len(circle_metas) == 1, (
            circle_metas, "Expected exactly one circle meta record"
        )
        return circle_metas[0]
    except Exception as e:
        raise api_errors.InternalError(message=str(e), error=e)


def update_circle_meta(update: dict) -> None:
    """Update the circle meta record in the settings collection."""
    storage = get_collection(COLLECTION)
    try:
        storage.update_matching(
            {"@meta": True},
            update
        )
    except Exception as e:
        raise api_errors.InternalError(message=str(e), error=e)


def get_root_circle() -> "CircleRecord":
    """Get the root circle."""
    circle_meta = get_circle_meta()
    if "root" not in circle_meta:
        raise api_errors.InternalError(
            message=f"'root' not set in collection {COLLECTION}",
            id=DOMAIN
        )
    return Circle().get(circle_meta["root"])


def get_tree_root() -> "CircleTree":
    """Get the root of the Circle tree"""
    circle_meta = get_circle_meta()
    if "root" not in circle_meta:
        raise api_errors.InternalError(
            message=f"'root' not set in collection {COLLECTION}",
            id=DOMAIN
        )
    tree_root = circle_meta[circle_meta["root"]]
    return TypedDict("CircleTree", tree_root)  # type: ignore


def get_address_tree() -> "CircleAddressTree":
    """Get the address tree of circles."""
    root = get_tree_root()
    return CircleAddressTree(root=root)


class CircleMember:
    """Circle model for handling database operations related to circle members
    (subcircles).
    """

    def __init__(self):
        """Initialize the Circle model with a storage interface."""
        self.storage = get_collection(COLLECTION)

    def list(self, circle_id: CircleID) -> dict:
        """List all members of a circle."""
        try:
            record = self.storage.get_by_id(circle_id)
            if record is None:
                raise api_errors.ConflictError(
                    message="Circle not found",
                    id=circle_id
                )
            return record.get("members", {})
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="Circle not found",
                id=circle_id
            )
        except storage_errors.StorageError as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def add(self, circle_id: CircleID, **fields: Unpack[CircleMemberAdd]) -> None:
        """Add a member to a circle."""
        member_id = fields["member_id"]
        access_value = fields["access_value"]
        # Check if member circle exists
        try:
            member_circle = self.storage.get_by_id(member_id)
            if member_circle is None:
                raise api_errors.ConflictError(
                    message="Member circle not found",
                    id=member_id
                )
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="Member circle not found",
                id=member_id
            ) from e
        except storage_errors.StorageError as e:
            raise api_errors.InternalError(message=str(e), error=e)

        # Use direct MongoDB access for nested field updates
        storage = get_collection(COLLECTION)
        try:
            storage.update_by_id(
                circle_id,
                {f"members.{member_id}": access_value},
            )
        except storage_errors.NoChangesAppliedError as e:
            raise api_errors.ConflictError(
                message="No changes applied when adding member",
                id=circle_id
            ) from e
        except storage_errors.StorageError as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def remove(self, circle_id: CircleID, **fields: Unpack[CircleMemberRemove]) -> None:
        """Remove a member from a circle."""
        member_id = fields["member_id"]
        # Check if member circle is a member of circle
        try:
            circle = self.storage.get_by_id(circle_id)
            if circle is None:
                raise api_errors.ConflictError(
                    message="Circle not found",
                    id=circle_id
                )
            if member_id not in circle.get("members", {}):
                raise api_errors.ConflictError(
                    message="Member not found in circle",
                    id=member_id
                )
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="Circle not found",
                id=circle_id
            ) from e
        except storage_errors.StorageError as e:
            raise api_errors.InternalError(message=str(e), error=e)

        # Use direct MongoDB access for nested field updates
        storage = get_collection(COLLECTION)
        try:
            storage.update_by_id(
                circle_id,
                {f"members.{member_id}": None},
            )
        except storage_errors.NoChangesAppliedError as e:
            raise api_errors.ConflictError(
                message="No changes applied when removing member",
                id=circle_id
            ) from e
        except storage_errors.StorageError as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def set(self, circle_id: CircleID, **fields: Unpack[CircleMemberSet]) -> None:
        """Set the access of a member of a circle.

        No validation of existing access is carried out.
        """
        # For now, set and add operations are identical
        self.add(circle_id, **fields)


class Circle:
    """Circle model for handling database operations related to circles."""
    members = CircleMember()

    def __init__(self):
        """Initialize the Circle model with a storage interface."""
        self.storage = get_collection(COLLECTION)

    def new(self, **fields: Unpack[CircleNew]) -> CircleResource:
        """This creates a new circle and adds it to the circle collection.

        It does not add it to the circle hierarchy or access control.
        """
        # TODO: Add admin as default parent if not specified
        parents = fields.pop("parents", {})
        if fields["tag"] == "root" and len(parents) > 0:
            raise api_errors.ConflictError(
                message="Root circle cannot have parents",
                id=fields["tag"]
            )
        circle_id = CampusID(uid.generate_category_uid("circle", length=8))
        record = CircleRecord(
            id=circle_id,
            created_at=utc_time.now(),
            name=fields["name"],
            description=fields.get("description", ""),
            tag=fields["tag"],
            members={},
        )
        # TODO: Store ancestry tree
        # TODO: Use transactions for atomic creation of circles and their parents
        # https://www.mongodb.com/docs/languages/python/pymongo-driver/upcoming/write/transactions/
        try:
            self.storage.insert_one(dict(record))
            for parent_id, access_value in parents.items():
                # TODO: Drum notation for updating nested fields
                self.members.add(parent_id, member_id=circle_id,
                                 access_value=access_value)
            # Return as CircleResource (add sources field)
            resource = CircleResource(**record)
            # TODO: join with sources and access values
            resource["sources"] = {}
            return resource
        except storage_errors.StorageError as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def delete(self, circle_id: str) -> None:
        """Delete a circle by id.

        This action is destructive and cannot be undone.
        It should only be done by an admin/owner.
        """
        # TODO: Check circle ancestry, remove from parents' members
        try:
            self.storage.delete_by_id(circle_id)
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="Circle not found",
                id=circle_id
            )
        except storage_errors.StorageError as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def get(self, circle_id: str) -> CircleResource:
        """Get a circle by id from the circle collection."""
        try:
            record = self.storage.get_by_id(circle_id)
            if record is None:
                raise api_errors.ConflictError(
                    message="Circle not found",
                    id=circle_id
                )
            # TODO: join with sources and access values
            resource = CircleResource(**record)
            # TODO: join with sources and access values
            resource["sources"] = {}
            return resource
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="Circle not found",
                id=circle_id
            ) from e
        except storage_errors.StorageError as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def update(self, circle_id: str, **updates: Unpack[CircleUpdate]) -> None:
        """Update a circle by id."""
        try:
            self.storage.update_by_id(circle_id, dict(updates))
        except storage_errors.NoChangesAppliedError as e:
            return None  # No changes applied, nothing to do
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="Circle not found",
                id=circle_id
            ) from e
        except storage_errors.StorageError as e:
            raise api_errors.InternalError(message=str(e), error=e)


class CircleAddressTree(Mapping[CircleID, "CircleAddressTree"]):
    """Circle address tree for managing circle hierarchy.

    While each circle already stores its descendancy information,
    this class provides a more efficient way to trace members of any circle.

    The address tree does not include user circles, for reasons of size and
    speed (MongoDB limits documents to 16MB).
    """

    def __init__(self, root: CircleTree):
        self.root = root

    def __getitem__(self, key: CircleID) -> "CircleAddressTree":
        """Get a circle tree by its ID."""
        if key not in self.root:
            raise KeyError(f"Circle ID {key} not found in address tree.")
        return CircleAddressTree(self.root[key])

    def __iter__(self) -> Iterator[CircleID]:
        """Iterate over the circle IDs in the address tree."""
        return iter(self.root)

    def __len__(self) -> int:
        """Get the number of circles in the address tree."""
        return len(self.root)
