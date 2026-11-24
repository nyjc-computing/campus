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

# Access-control bootstrap (docs/circles-access-control.md, ratified
# 2026-11-23, campus#1216): each guarded API resource family gets a
# grant circle (tag RESOURCE_TAG) that authorization resolves against.
# There are no role circles: authority is the access value carried by
# the membership edge into the grant circle, plus the `campus`
# wildcard (admin on every family) and the primary-group baseline
# (`staff:viewer`, `student:guest`). Grant circles hang under the
# root circle.
RESOURCE_TAG = "resource"
ROLE_TAG = "role"  # legacy tag; no longer seeded, kept for migration filters
BOOTSTRAP_RESOURCES = (
    "circles",
    "timetable",
    "assignments",
    "submissions",
    "subjcombi",
    "users",
    "venues",
    "files",
    "hostedapps",
)
# "bookings" is deliberately absent (campus#1217/#1218): booking
# authority is venue-derived (the family tables classify booking ops
# against the venues grant circle, category-narrowed). Environments
# that still hold the retired circles from the old bootstrap delete
# them; the seed never re-creates them.

# Circles contain only circles: a user participates through their user
# circle (tag USER_TAG), named after their email account, which also
# holds their private resources. Adding a user to a circle means adding
# their user circle, so email-shaped member IDs must address an
# existing user circle.
USER_TAG = "user"

# The reserved wildcard circle (docs/circles-access-control.md): a
# campus:admin membership confers admin on every resource family.
# Checked by the authz layer before family resolution. Seeded empty
# except for the bootstrap admins below (init_storage runs in
# non-production environments; production seeds its own platform
# admin via the migration).
CAMPUS_CIRCLE_NAME = "campus"

# Bootstrap seeding, temporary: these accounts' user circles are
# created and contained in the `campus` wildcard at init until
# user-circle provisioning has management flows. The second account
# is a shared automation admin (campus-test-admin) so live testing
# never runs as a personal account.
BOOTSTRAP_ADMIN_USERS: tuple[schema.CampusID, ...] = (
    schema.CampusID("ng_jun_siang@nyjc.edu.sg"),
    schema.CampusID("campus-test-admin@nyjc.edu.sg"),
)

# Access values (ratified 2026-11-23, campus#1216): 8-bit dual-scope
# constants `0 | G-c G-m G-r | S-c S-m S-r | 0(reserved)`. c⇒m⇒r holds
# within each field; group roles mirror into self. Edge values MUST be
# one of these five constants — no arbitrary integers (validated at
# member add/update and circle creation).
ACCESS_ADMIN = 0b01111110   # 126
ACCESS_EDITOR = 0b00110110  # 54
ACCESS_VIEWER = 0b00010010  # 18
ACCESS_SELF = 0b00001110    # 14
ACCESS_GUEST = 0b00000010   # 2

ACCESS_CONSTANTS: dict[str, int] = {
    "admin": ACCESS_ADMIN,
    "editor": ACCESS_EDITOR,
    "viewer": ACCESS_VIEWER,
    "self": ACCESS_SELF,
    "guest": ACCESS_GUEST,
}
ACCESS_NAMES: dict[int, str] = {v: k for k, v in ACCESS_CONSTANTS.items()}

GROUP_FIELD_MASK = 0b01110000  # bits 6..4: G-c G-m G-r
SELF_FIELD_MASK = 0b00001110   # bits 3..1: S-c S-m S-r
PERMISSION_SHIFTS = {"create": 2, "modify": 1, "read": 0}

# The primary groups whose membership value is an account's
# platform-wide baseline (docs/circles-access-control.md, "Baseline").
# Provisioning artifacts: the bootstrap does not create them.
PRIMARY_GROUPS = ("staff", "student")


def is_access_constant(value: object) -> bool:
    """True if the value is one of the five ratified constants."""
    return isinstance(value, int) and value in ACCESS_CONSTANTS.values()


def validate_access_constant(value: object) -> int:
    """Validate an edge access value against the constant set.

    Raises:
        InvalidRequestError: If the value is not one of the five
            ratified constants (the pre-ratification 4-bit values
            included).
    """
    if not isinstance(value, int) or value not in ACCESS_CONSTANTS.values():
        raise api_errors.InvalidRequestError(
            "Access value must be one of the ratified constants "
            f"{sorted(ACCESS_CONSTANTS.items())} — got {value!r} "
            "(campus#1216)"
        )
    return value


def has_permission(value: int, scope: str, permission: str) -> bool:
    """True if the value carries `permission` in the field for `scope`.

    The G field lives at bit base 4 (b6..b4 = c,m,r), the S field at
    bit base 1 (b3..b1 = c,m,r); permission names map to their offset
    within the field (c⇒m⇒r means a create check answers only the
    create bit; callers gate read ops with "read").
    """
    base = 4 if scope == "group" else 1
    return bool(value & (1 << (PERMISSION_SHIFTS[permission] + base)))


def _member_kind(member_id: str) -> str:
    """Classify a member ID: "user" (email-shaped) or "circle".

    Email-shaped IDs name a user circle (user circles are named after
    the email account; campus.common.schema.UserID is an Email). Every
    other ID addresses a circle by UID. Circle UIDs have used both the
    legacy ("circle_...") and current ("uid-circle-...") schemes, so
    membership keys are not prefix-matched.
    """
    return "user" if "@" in member_id else "circle"


def resolve_member(
        circle_id: schema.CampusID,
        member_id: schema.CampusID,
        *,
        transitive: bool = True,
) -> dict | None:
    """Resolve one membership through the shared resolver (#1202).

    The single implementation of "can this member be reached from this
    circle": the enforcement gate (campus.api.authz) and the membership
    probe route both answer through it, so their semantics cannot
    drift. Resolution is a pure graph walk over membership edges —
    circles contain only circles, so every member key addresses a
    circle: email-shaped keys name leaf user circles (personal circles,
    the account being their member), every other key addresses a circle
    by UID.

    Args:
        circle_id: The circle from which resolution starts.
        member_id: The member identifier to resolve, as stored (a
            circle UID or the email name of a user circle).
        transitive: Follow member group circles beyond the direct
            members dict. False answers the direct-only question
            (the probe's back-compat default).

    Returns:
        None if the member is not reachable (the fail-closed negative
        callers probe for), otherwise a dict:

            {
                "member_id": str,      # as passed
                "access_value": int,   # max across resolving paths
                "direct": bool,        # edge on the circle itself
                "via": list[str],      # circle names target->hit
            }

        access_value is the maximum over all resolving paths: edges are
        uniform (a circle is a member wherever it appears, directly or
        through groups), so the most permissive path is the member's
        effective access (#1202 ruling).

    Raises:
        ConflictError: If the circle does not exist.
        InternalError: For storage errors.
    """
    try:
        record = circle_storage.get_by_id(circle_id)
        if record is None:
            raise api_errors.ConflictError(
                "Circle not found",
                id=circle_id
            )
    except campus.storage.errors.NotFoundError:
        raise api_errors.ConflictError(
            "Circle not found",
            id=circle_id
        ) from None
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e

    key = str(member_id)
    direct_value = record.get("members", {}).get(key)

    if not transitive:
        if direct_value is None:
            return None
        return {
            "member_id": key,
            "access_value": direct_value,
            "direct": True,
            "via": [],
        }

    # Breadth-first walk over membership edges, cycle-safe: one visit
    # per distinct circle, so DAGs and cycles both terminate. Email-
    # shaped keys name user circles (addressable by name, not UID), so
    # the walk never descends through them — it only matches them as
    # keys, the same rule the #1197 enforcement walk used. A stale
    # member key (circle deleted after being added) fails closed for
    # that key only: resolution continues through the remaining edges.
    from campus.storage import errors as storage_errors

    best: dict | None = None
    best_depth = -1
    # parent maps a circle key to the record it was reached from, for
    # reconstructing the containment chain of the shortest hit path.
    parents: dict[str, dict] = {}
    pending: list[tuple[dict, int]] = [(record, 0)]
    visited: set[str] = set()
    while pending:
        current, depth = pending.pop(0)
        current_key = str(current.get(schema.CAMPUS_KEY))
        if current_key in visited:
            continue
        visited.add(current_key)
        members = current.get("members", {})
        if key in members:
            # First hit at the shallowest depth wins the via chain;
            # deeper or later hits only compete on access_value.
            if best is None or depth < best_depth:
                best = {
                    "member_id": key,
                    "access_value": members[key],
                    "direct": current is record,
                    "via": _member_chain(current, parents),
                }
                best_depth = depth
            elif members[key] > best["access_value"]:
                best["access_value"] = members[key]
        for member_key in members:
            if _member_kind(str(member_key)) != "circle":
                continue
            member_key = str(member_key)
            if member_key in visited or member_key in parents:
                continue
            try:
                member_record = circle_storage.get_by_id(
                    schema.CampusID(member_key)
                )
            except storage_errors.NotFoundError:
                continue
            except campus.storage.errors.StorageError as e:
                raise api_errors.InternalError.from_exception(e) from e
            if not member_record:
                continue
            parents[member_key] = current
            pending.append((member_record, depth + 1))
    return best


def _member_chain(hit: dict, parents: dict[str, dict]) -> list[str]:
    """Reconstruct the containment chain target->hit as circle names.

    `parents` maps each reached circle's key to the record it was
    reached from; the chain of names (UID if unnamed) reads in the
    containment direction, e.g. ["staff", "teachers"] for
    role -> staff -> teachers -> user circle. An empty chain is a
    direct edge.
    """
    chain: list[str] = []
    current = hit
    while True:
        current_key = str(current.get(schema.CAMPUS_KEY))
        parent = parents.get(current_key)
        if parent is None:
            break
        chain.append(str(current.get("name") or current_key))
        current = parent
    chain.reverse()
    return chain


def resolve_family_access(
        family_name: str,
        member_id: schema.CampusID,
        narrow_to_label: str | None = None,
) -> dict | None:
    """Resolve a principal's effective access on a grant circle.

    The ratified resolution (docs/circles-access-control.md): the
    principal's baseline (the value on their primary-group membership
    — `staff`/`student`) combined with every family-directed edge
    reachable through member circles, reduced to two effective fields
    — group-scope (`g`) and self-scope (`s`).

    Category narrowing applies to the group field only: when
    `narrow_to_label` names a member circle of the family (a venue
    category subcircle, matched by label) that contains the principal,
    the group field comes exclusively from that edge — a booking in a
    category the principal scope-manages is not also widened by their
    family-level edges. The self field is never narrowed: own-scope
    authority survives whatever category edges exist.

    Args:
        family_name: The grant circle's name ("venues", "timetable").
        member_id: The principal's user ID (their user circle's email
            name).
        narrow_to_label: Optional member-circle label whose edge, when
            applicable to the principal, becomes the sole source of
            the group field.

    Returns:
        None if the grant circle does not exist (callers deny
        fail-closed), otherwise:

            {
                "g": int,        # effective group-scope field
                "s": int,        # effective self-scope field
                "baseline": int, # the primary-group value (0 if none)
                "narrowed": bool,# group field came from a category edge
            }

    Non-constant values (legacy edges awaiting migration) still
    contribute whatever their bit fields carry — the gates check
    bits, not membership, so a legacy 15 yields self-scope authority
    and no group-scope authority until the edge is rewritten.
    """
    from campus.storage import errors as storage_errors

    try:
        matches = circle_storage.get_matching({"name": family_name})
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    if not matches:
        return None
    family = matches[0]

    email = str(member_id)

    baseline = 0
    for group_name in PRIMARY_GROUPS:
        try:
            group_matches = circle_storage.get_matching({"name": group_name})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        if group_matches:
            direct = group_matches[0].get("members", {}).get(email)
            if direct is not None and direct > baseline:
                baseline = direct

    applicable: list[tuple[int, str | None, bool]] = []
    for member_key, value in family.get("members", {}).items():
        member_key = str(member_key)
        if member_key == email:
            applicable.append((int(value), None, False))
            continue
        if _member_kind(member_key) != "circle":
            continue
        try:
            member_record = circle_storage.get_by_id(
                schema.CampusID(member_key)
            )
        except storage_errors.NotFoundError:
            continue
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        if not member_record:
            continue
        if resolve_member(
                schema.CampusID(member_record[schema.CAMPUS_KEY]),
                member_id,
        ) is not None:
            # A member circle tagged "category" is a venue-category
            # subcircle: its edge applies only to resources in its own
            # category (the narrowest-path rule) — it must not widen
            # the family-level max for other categories.
            label = str(member_record.get("name") or "")
            is_category = member_record.get("tag") == "category"
            applicable.append((int(value), label, is_category))

    narrowed = False
    if narrow_to_label is not None:
        category_edges = [
            v & GROUP_FIELD_MASK
            for v, label, is_cat in applicable
            if is_cat and label == narrow_to_label
        ]
    else:
        category_edges = []
    other_g = [
        v & GROUP_FIELD_MASK for v, _, is_cat in applicable if not is_cat
    ]
    if category_edges:
        g_values = category_edges
        narrowed = True
    else:
        g_values = other_g
    g = max([baseline & GROUP_FIELD_MASK, *g_values]) if g_values \
        else baseline & GROUP_FIELD_MASK
    s = max([baseline & SELF_FIELD_MASK]
            + [v & SELF_FIELD_MASK for v, _, _ in applicable]) \
        if applicable else baseline & SELF_FIELD_MASK
    return {"g": g, "s": s, "baseline": baseline, "narrowed": narrowed}


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
        the @meta record, the root circle, the reserved `campus`
        wildcard circle (holding the bootstrap admins), and a grant
        circle per guarded resource family — no role circles
        (docs/circles-access-control.md, ratified campus#1216).
        Idempotent.
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

        # The reserved `campus` wildcard circle (docs/circles-access-
        # control.md): a campus:admin membership confers admin on every
        # resource family. Seeded empty of members except the bootstrap
        # admins below (non-production init; production seeds its own
        # platform admin via migration).
        campus_circles = circle_storage.get_matching(
            {"name": CAMPUS_CIRCLE_NAME}
        )
        assert len(campus_circles) <= 1, (
            campus_circles, "More than one campus wildcard circle found"
        )
        if not campus_circles:
            campus_circle = CirclesResource().new(
                name=CAMPUS_CIRCLE_NAME,
                description=(
                    "Platform admin wildcard: admin on every resource family"
                ),
                tag="group",
                parents={root_circle.id: ACCESS_ADMIN},
            )
        else:
            campus_circle = model.Circle.from_storage(campus_circles[0])

        # User circles for the bootstrap admins
        # (docs/circles-access-control.md): users participate through
        # their user circle, named after the email account; it also
        # holds the user's private resources. Created standalone (no
        # parents) — memberships are the access grants, not the
        # user circle's position in the tree. Temporary until
        # user-circle provisioning has a flow.
        for admin_user in BOOTSTRAP_ADMIN_USERS:
            _ensure_circle(
                str(admin_user),
                tag=USER_TAG,
                description=(
                    f"Personal circle for {admin_user} (private resources)"
                ),
            )
            # Bootstrap admins hold the wildcard, not per-family grants.
            _ensure_member(
                campus_circle.id,
                admin_user,
                ACCESS_ADMIN,
            )

        # Grant circles (docs/circles-access-control.md): one per
        # guarded API resource family, contained in the root. No role
        # circles — authority is the value on the membership edge into
        # the grant circle (plus the campus wildcard and the
        # primary-group baseline). Idempotent: name-keyed lookups make
        # re-runs no-ops.
        for resource_name in BOOTSTRAP_RESOURCES:
            _ensure_circle(
                resource_name,
                tag=RESOURCE_TAG,
                description=(
                    f"Authorization circle for the {resource_name} resource"
                ),
                parents={root_circle.id: ACCESS_ADMIN},
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

    def get(
            self,
            circle_id: schema.CampusID,
            member_id: schema.CampusID
    ) -> int | None:
        """Get one member's access value: the membership probe.

        An absent member is an expected negative answer (None), not an
        error — callers probe "is this principal in this circle" and
        treat any non-answer as denial. A missing circle is still an
        error, consistent with list/add/remove.

        Args:
            circle_id: The circle ID
            member_id: The member identifier as stored (circle UID or
                user-circle email name)

        Returns:
            The member's access value, or None if the circle has no
            such member

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
            return record.get("members", {}).get(str(member_id))
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

        Circles contain only circles. A member ID is either a circle
        UID or the email name of the user's circle (user circles are
        named after the email account); both must address an existing
        circle. Members are keyed by the identifier they were added
        with (the user-circle email is itself stable, so no UID
        resolution is needed).

        Args:
            circle_id: The parent circle ID
            member_id: The member circle's ID, or the email name of an
                existing user circle
            access_value: The access level for the member

        Raises:
            ConflictError: If the member circle or user circle does not
                exist, the parent circle does not exist, or the member
                is already present with the same access
            InternalError: For storage errors
        """
        access_value = validate_access_constant(access_value)
        if _member_kind(str(member_id)) == "user":
            # Email-shaped IDs name the user's circle; the user circle
            # must exist for the membership to be valid.
            try:
                user_circles = circle_storage.get_matching(
                    {"name": str(member_id)}
                )
                if not user_circles:
                    raise api_errors.ConflictError(
                        "User circle not found",
                        id=member_id
                    )
            except campus.storage.errors.StorageError as e:
                raise api_errors.InternalError.from_exception(e) from e
        else:
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

        # Read-modify-write the whole members dict: member identifiers
        # may be email names, whose dots a `members.{member_id}` update
        # key would parse as nested-field paths (both document
        # backends).
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
            member_id: The member identifier to remove (circle UID or
                user-circle email name, as added)

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

    def resolve(
            self,
            circle_id: schema.CampusID,
            member_id: schema.CampusID,
            *,
            transitive: bool = True,
    ) -> dict | None:
        """Resolve one membership through the shared resolver (#1202).

        Resource-layer surface for the module-level resolve_member:
        the gate (campus.api.authz) imports the module function
        directly; route handlers and in-process callers go through
        this method. See resolve_member for semantics.

        Args:
            circle_id: The circle from which resolution starts.
            member_id: The member identifier to resolve, as stored.
            transitive: Follow member group circles beyond the direct
                members dict.

        Returns:
            None if the member is not reachable, otherwise the
            resolution dict (member_id, access_value, direct, via).

        Raises:
            ConflictError: If the circle does not exist.
            InternalError: For storage errors.
        """
        return resolve_member(
            circle_id,
            member_id,
            transitive=transitive,
        )
