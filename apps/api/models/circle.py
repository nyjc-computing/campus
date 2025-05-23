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
    # Create admin and root circles
    root_circle = Circle().new(
        name=DOMAIN,
        description="Root circle",
        tag="root",
        parents={}
    ).data
    admin_circle = Circle().new(
        name="campus-admin",
        description="Campus admin account",
        tag="admin",
        parents={root_circle[PK]: 15}
    ).data

    storage = get_conn()
    storage["settings"].update(
        {"category": "admin"},
        {"$set": {"circle_id": admin_circle[PK]}},
        upsert=True
    )
    storage["settings"].update(
        {"category": "circles"},
        {"$set": {"root": root_circle[PK]}},
        upsert=True
    )

    # Create circle address tree
    storage[TABLE].insert_one({root_circle[PK]: {}})


def get_root_circle() -> "CircleRecord":
    """Get the root circle ID from the settings collection."""
    storage = get_conn()
    circle_settings = storage["settings"].find_one({"category": "circles"})
    if circle_settings is None:
        raise api_errors.InternalError(
            message="Root circle not found in settings",
            id=DOMAIN
        )
    return Circle().get(circle_settings["root"]).data


def get_tree_root() -> CircleTree:
    """Get the root of the Circle tree"""
    root = get_root_circle()
    return get_conn()[TABLE].find_one(
        {root[PK]: {"$exists": True}}
    )


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


class CircleRecord(CircleNew, BaseRecord):
    """The circle record stored in the circle collection."""


class CircleResource(CircleRecord, total=False):
    """Response body schema representing the result of a circles.get operation."""
    children: dict[CircleID, AccessValue]
    sources: dict  # SourceID, SourceHeader


class Circle:
    """Circle model for handling database operations related to circles."""

    def __init__(self):
        """Initialize the Circle model with a storage interface."""
        self.storage = get_drum()

    def new(self, **fields: Unpack[CircleNew]) -> ModelResponse:
        """This creates a new circle and adds it to the circle collection.

        It does not add it to the circle hierarchy or access control.
        """
        circle_id = uid.generate_category_uid("circle", length=8)
        if len(fields["parents"]) == 0:
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


class CircleAddressTree:
    """Circle address tree for managing circle hierarchy.

    While each circle already stores its descendancy information,
    this class provides a more efficient way to trace members of any circle.

    The address tree does not include user circles, for reasons of size and
    speed (MongoDB limits documents to 16MB).
    """

    def __init__(self):
        """Initialize the address tree with a storage interface."""
        self.storage = get_drum()
        self.tree: CircleTree = {}
        self._load_tree()

    def _load_tree(self):
        """Load the address tree from the database."""
        # TODO: Recursive conversion of PK from _id
        self.tree = get_tree_root()
