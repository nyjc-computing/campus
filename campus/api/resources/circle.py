"""campus.api.resources.circle

Circle resource for Campus API.
"""

import typing

import campus.model as model
import campus.storage
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid

circle_storage = campus.storage.get_collection("circles")

# TODO: Make domain configurable
DOMAIN = "nyjc.edu.sg"

# Access-control bootstrap (docs/circles-access-control.md): each guarded
# API resource family gets a resource circle (tag RESOURCE_TAG), and each
# resource circle gets an admin role circle (tag ROLE_TAG) named
# "<resource>.admin" — role circles carry the principals (users, circles)
# granted the role and never contain resources of their own. Resource
# circles hang under the root circle; role circles hang under their
# resource circle.
RESOURCE_TAG = "resource"
ROLE_TAG = "role"
BOOTSTRAP_RESOURCES = (
    "circles",
    "timetable",
    "assignments",
    "bookings",
    "submissions",
)

# Bootstrap seeding, temporary: added to every <resource>.admin role
# circle at init until role administration has a management flow.
BOOTSTRAP_ADMIN_USER: schema.CampusID = schema.CampusID(
    "ng_jun_siang@nyjc.edu.sg"
)

# Access-value convention: 15 denotes full access, mirroring the seeded
# campus-admin -> root edge. Exact semantics are still to be decided.
BOOTSTRAP_ACCESS_VALUE = 15


def _member_kind(member_id: str) -> str:
    """Classify a member ID: "user" (email-shaped) or "circle".

    User IDs are emails (campus.common.schema.UserID is an Email);
    every other ID addresses a circle record and must exist. Circle
    UIDs have used both the legacy ("circle_...") and current
    ("uid-circle-...") schemes, so membership keys are not
    prefix-matched.
    """
    return "user" if "@" in member_id else "circle"



def get_circle_meta() -> dict:
    """Get the circle meta record from the circles collection."""
    try:
        circle_metas = circle_storage.get_matching({"@meta": True})
    except Exception as e:
        raise api_errors.InternalError.from_exception(e) from e

    if not circle_metas:
        raise api_errors.NotFoundError(
            "Circle meta record not found in collection circles",
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


def ensure_name_available(
        name: str,
        exclude_id: schema.CampusID | None = None
) -> None:
    """Raise ConflictError if a circle already uses the given name.

    Best-effort uniqueness: a pre-write exact-match lookup (case-sensitive),
    not a storage invariant — concurrent writes may still race.
    """
    try:
        matches = circle_storage.get_matching({"name": name})
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    for record in matches:
        if record.get(schema.CAMPUS_KEY) != exclude_id:
            raise api_errors.ConflictError(
                f"Circle name already exists: {name}",
                id=name
            )


def _ensure_circle(
        name: str,
        *,
        tag: str,
        description: str = "",
        parents: dict[schema.CampusID, int] | None = None,
) -> model.Circle:
    """Return the circle named `name`, creating it if absent (bootstrap).

    Bootstrap-only counterpart to ensure_name_available: asserts the
    single-record invariant before reusing an existing circle. Heals
    missing circles only — missing membership edges are manual repairs.
    """
    matches = circle_storage.get_matching({"name": name})
    assert len(matches) <= 1, (
        matches, f"More than one circle named {name}"
    )
    if matches:
        return model.Circle.from_storage(matches[0])
    return CirclesResource().new(
        name=name,
        tag=tag,
        description=description,
        **{"parents": parents} if parents else {},
    )


def _ensure_member(
        circle_id: schema.CampusID,
        member_id: schema.CampusID,
        access_value: int,
) -> None:
    """Add `member_id` to the circle unless already present (bootstrap)."""
    record = circle_storage.get_by_id(circle_id)
    if str(member_id) not in (record or {}).get("members", {}):
        CirclesResource().members.add(
            circle_id,
            member_id=member_id,
            access_value=access_value,
        )


class CirclesResource:
    """Represents the circles resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for circle management.

        Seeds the access-control bootstrap on top of the collection:
        the @meta record, the root and campus-admin sentinels, and the
        per-resource authorization circles with their admin role
        circles (docs/circles-access-control.md). Idempotent.
        """
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
            root_circle = model.Circle.from_storage(root_circles[0])

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

        # Resource authorization circles (docs/circles-access-control.md):
        # a resource circle per guarded API resource family, each with an
        # admin role circle for role assignment. Idempotent: name-keyed
        # lookups make re-runs no-ops.
        for resource_name in BOOTSTRAP_RESOURCES:
            resource_circle = _ensure_circle(
                resource_name,
                tag=RESOURCE_TAG,
                description=(
                    f"Authorization circle for the {resource_name} resource"
                ),
                parents={root_circle.id: BOOTSTRAP_ACCESS_VALUE},
            )
            role_circle = _ensure_circle(
                f"{resource_name}.admin",
                tag=ROLE_TAG,
                description=f"Admin role for the {resource_name} resource",
                parents={resource_circle.id: BOOTSTRAP_ACCESS_VALUE},
            )
            # Temporary bootstrap admin (BOOTSTRAP_ADMIN_USER).
            _ensure_member(
                role_circle.id,
                BOOTSTRAP_ADMIN_USER,
                BOOTSTRAP_ACCESS_VALUE,
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

    def list(self, **filters: typing.Any) -> list[model.Circle]:
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
        # @meta bookkeeping records share this collection but lack circle
        # fields (name/tag), so they cannot be hydrated as Circle models.
        records = [record for record in records if not record.get("@meta")]
        return [model.Circle.from_storage(record) for record in records]

    def new(self, **fields: typing.Any) -> model.Circle:
        """Create a new circle.

        Args:
            **fields: Fields for circle creation (name, description, tag, parents)

        Returns:
            Circle instance

        Raises:
            ConflictError: If the name is already used by another circle
                (best-effort check), or a root circle is given parents
        """
        parents = fields.pop("parents", {})
        if fields["tag"] == "root" and len(parents) > 0:
            raise api_errors.ConflictError(
                "Root circle cannot have parents",
                id=fields["tag"]
            )
        ensure_name_available(fields["name"])

        circle_id = schema.CampusID(
            uid.generate_category_uid("circle", length=8)
        )
        circle = model.Circle(
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

    def get(self) -> model.Circle:
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
            return model.Circle.from_storage(record)
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
            ConflictError: If circle not found or the new name is
                already used by another circle
            InternalError: For storage errors
        """
        if "name" in updates:
            ensure_name_available(updates["name"], exclude_id=self.circle_id)
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
            member_id: The member ID to add — a circle ID (`circle_...`)
                or a user ID (email). User membership is accepted
                without an existence check (the resource layer cannot
                validate user IDs against campus.auth); an unknown user
                ID is inert because enforcement matches caller IDs.
            access_value: The access level for the member

        Raises:
            ConflictError: If a circle member ID does not exist, the
                parent circle does not exist, or the member is already
                present with the same access
            InternalError: For storage errors
        """
        if _member_kind(str(member_id)) == "circle":
            # Circle members must exist. User members (emails) are
            # accepted without an existence check: the resource layer
            # cannot validate user IDs against campus.auth, and an
            # unknown user ID is inert because enforcement matches
            # caller IDs.
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

        # Read-modify-write the whole members dict: member IDs may be
        # user emails, whose dots a `members.{member_id}` update key
        # would parse as nested-field paths (both document backends).
        try:
            record = circle_storage.get_by_id(circle_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Circle not found",
                    id=circle_id
                )
            members = dict(record.get("members", {}))
            members[str(member_id)] = access_value
            circle_storage.update_by_id(circle_id, {"members": members})
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Circle not found",
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
            member_id: The member ID to remove (circle ID or user email)

        Raises:
            ConflictError: If circle not found or member not in circle
            InternalError: For storage errors
        """
        # Read-modify-write the whole members dict (see add for why).
        try:
            record = circle_storage.get_by_id(circle_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Circle not found",
                    id=circle_id
                )
            members = dict(record.get("members", {}))
            if str(member_id) not in members:
                raise api_errors.ConflictError(
                    "Member not found in circle",
                    id=member_id
                )
            del members[str(member_id)]
            circle_storage.update_by_id(circle_id, {"members": members})
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Circle not found",
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
