"""
Circle Models

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

from apps.common.errors import api_errors
from apps.api.models.base import BaseRecord, ModelResponse
from common.drum.mongodb import PK, get_conn, get_drum
from common.schema import CampusID, UserID, Message, Response
from common.utils import uid, utc_time

# TODO: Replace with OpenAPI-based string-pattern schema
AccessValue = int
CircleID = CampusID
CirclePath = str
CircleTag = str
CircleTree = dict[CircleID, "CircleTree"]

# TODO: Make domain configurable
DOMAIN = "nyjc.edu.sg"
TABLE = "circles"


# TODO: Refactor settings into a separate model
def init_db():
    """Initialize the collections needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    For MongoDB, collections are created automatically on first insert.
    """
    # Check for existing root circle
    storage = get_conn()
    circle_meta = get_circle_meta()
    if (circle_meta is None or "root" not in circle_meta):
        # Create admin and root circles
        root_circle = Circle().new(
            name=DOMAIN,
            description="Root circle",
            tag="root",
            parents={}
        ).data
        Circle().new(
            name="campus-admin",
            description="Campus admin circle",
            tag="admin",
            parents={root_circle[PK]: 15}
        ).data
        # Create or update circle meta record
        storage[TABLE].update_one(
            {"@meta": True},
            {
                "$set": {
                    "@meta": True,
                    "root": root_circle[PK],
                    root_circle[PK]: {},  # circle address tree
                }
            },
            upsert=False
        )


class CircleMeta(TypedDict, total=False):
    """Circle meta schema for the circles collection.

    This is used to store the root circle and the address tree.
    """
    # Some keys are required but (intentionally) cannot be represented
    # in TypedDict
    # These are added here for documentation purposes
    # @meta: bool  # always True
    # <circle_id>: CircleTree  # circle address tree
    root: CircleID


class CircleNew(TypedDict, total=True):
    """Request body schema for a circles.new operation.

    Circles must be created with at least one parent (default: admin).
    The `parents` property maps the circle's full path
      ({parent path} / {circle_id}) to its access value in that parent.
    """
    name: str
    description: NotRequired[str]
    tag: CircleTag
    parents: dict[CirclePath, AccessValue]


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


class CircleResource(CircleRecord, total=False):
    """Response body schema representing the result of a circles.get operation."""
    members: dict[CircleID, AccessValue]
    sources: dict  # SourceID, SourceHeader


def get_circle_meta() -> "CircleMeta":
    """Get the circle meta record from the settings collection."""
    storage = get_conn()
    circle_meta = storage[TABLE].find_one({"@meta": True})
    if circle_meta is None:
        raise api_errors.InternalError(
            message=f"Circle meta record not found in collection {TABLE}",
            id=DOMAIN
        )
    # Since some keys required in CircleMeta cannot be represented as
    # identifiers, we use the TypedDict constructor
    return TypedDict("CircleMeta", circle_meta)  # type: ignore

def get_root_circle() -> "CircleRecord":
    """Get the root circle ID from the settings collection."""
    circle_meta = get_circle_meta()
    if "root" not in circle_meta:
        raise api_errors.InternalError(
            message=f"'root' not set in collection {TABLE}",
            id=DOMAIN
        )
    return Circle().get(circle_meta["root"]).data

def get_tree_root() -> "CircleTree":
    """Get the root of the Circle tree"""
    circle_meta = get_circle_meta()
    if "root" not in circle_meta:
        raise api_errors.InternalError(
            message=f"'root' not set in collection {TABLE}",
            id=DOMAIN
        )
    tree_root = circle_meta[circle_meta["root"]]
    return TypedDict("CircleTree", tree_root)  # type: ignore

def get_address_tree() -> "CircleAddressTree":
    """Get the address tree of circles."""
    root = get_tree_root()
    return CircleAddressTree(root=root)


class Circle:
    """Circle model for handling database operations related to circles."""

    def __init__(self):
        """Initialize the Circle model with a storage interface."""
        self.storage = get_drum()

    def 

    def new(self, **fields: Unpack[CircleNew]) -> ModelResponse:
        """This creates a new circle and adds it to the circle collection.

        It does not add it to the circle hierarchy or access control.
        """
        circle_id = uid.generate_category_uid("circle", length=8)
        if fields["tag"] == "root" and len(fields["parents"]) > 0:
            raise api_errors.InvalidRequestError(
                message="Root Circle cannot have parent",
                id=circle_id,
            )
        elif fields["tag"] != "root" and len(fields["parents"]) == 0:
            raise api_errors.InvalidRequestError(
                message="Circle must have at least one parent",
                id=circle_id,
            )
        record = CircleRecord(
            id=circle_id,
            created_at=utc_time.now(),
            **fields,
        )
        resp = self.storage.insert(TABLE, record)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.SUCCESS):
                return ModelResponse(status="ok", message=Message.CREATED, data=resp.data)
        raise ValueError(f"Unexpected response from storage: {resp}")

    def delete(self, circle_id: str) -> ModelResponse:
        """Delete a circle by id.
        
        This action is destructive and cannot be undone.
        It should only be done by an admin/owner.
        """
        resp = self.storage.delete_by_id(TABLE, circle_id)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.DELETED):
                return ModelResponse(**resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Circle not found",
                    id=circle_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

    def get(self, circle_id: str) -> ModelResponse:
        """Get a circle by id from the circle collection."""
        resp = self.storage.get_by_id(TABLE, circle_id)
        # TODO: join with sources and access values
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.FOUND):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Circle not found",
                    id=circle_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

    def update(self, circle_id: str, **updates: Unpack[CircleUpdate]) -> ModelResponse:
        """Update a circle by id."""
        resp = self.storage.update_by_id('circles', circle_id, updates)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.UPDATED):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Circle not found",
                    id=circle_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")


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
    