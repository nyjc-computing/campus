"""tests.fixtures.circles

Helpers for circle access control in tests.

The api gates routes behind access values on membership edges
(docs/circles-access-control.md, ratified campus#1216): authority is
the value on an edge into the family's grant circle (or through a
member circle), the `campus` wildcard, and the primary-group
baseline. Tests exercise those routes by granting edges through
these helpers, which work directly against the resource layer — it
stays ungated for in-process callers.
"""

__all__ = [
    "grant_circle_admin",
    "grant_family_access",
    "grant_category_booking_admin",
    "grant_staff_baseline",
    "grant_campus_admin",
]


def _ensure_user_circle(user_id: str) -> None:
    from campus.api import resources
    from campus.api.resources.circle import circle_storage

    if not circle_storage.get_matching({"name": user_id}):
        resources.circle.new(name=user_id, tag="user")


def grant_family_access(user_id: str, family: str, access_value: int) -> None:
    """Grant `user_id` a direct edge into a family's grant circle.

    The generic form: the user circle joins the family circle itself
    at `access_value` (a ratified constant). Idempotent.
    """
    from campus.api import resources
    from campus.api.resources.circle import (
        circle_storage,
        validate_access_constant,
    )
    from campus.common import schema

    validate_access_constant(access_value)
    _ensure_user_circle(user_id)
    family_circles = circle_storage.get_matching({"name": family})
    assert family_circles, f"No '{family}' grant circle: run the bootstrap"
    family_id = schema.CampusID(family_circles[0][schema.CAMPUS_KEY])
    if user_id not in family_circles[0].get("members", {}):
        resources.circle.members.add(
            family_id,
            member_id=schema.CampusID(user_id),
            access_value=access_value,
        )


def grant_circle_admin(user_id: str, *families: str) -> None:
    """Grant `user_id` admin authority on the given api resource families.

    Pre-ratification name kept for call-site stability: the decision
    this helper encodes is a direct `family:admin` edge (group-scope
    create/modify/read), which `require_resource_admin` gates through.
    Idempotent.
    """
    from campus.api.resources.circle import ACCESS_ADMIN

    for family in families:
        grant_family_access(user_id, family, ACCESS_ADMIN)


def grant_campus_admin(user_id: str) -> None:
    """Grant `user_id` the `campus` wildcard (admin on every family)."""
    from campus.api import resources
    from campus.api.resources.circle import (
        ACCESS_ADMIN,
        CAMPUS_CIRCLE_NAME,
        circle_storage,
    )
    from campus.common import schema

    _ensure_user_circle(user_id)
    campus_circles = circle_storage.get_matching({"name": CAMPUS_CIRCLE_NAME})
    assert campus_circles, "No 'campus' wildcard circle: run the bootstrap"
    campus_id = schema.CampusID(campus_circles[0][schema.CAMPUS_KEY])
    if user_id not in campus_circles[0].get("members", {}):
        resources.circle.members.add(
            campus_id,
            member_id=schema.CampusID(user_id),
            access_value=ACCESS_ADMIN,
        )


def grant_staff_baseline(user_id: str) -> None:
    """Give `user_id` the staff baseline (viewer) + own-booking powers.

    Creates the `staff` primary group if absent, adds the user at
    `viewer` (the staff baseline: read everything school-wide), and
    contains the group in `venues` at `self` so the user can create,
    edit, and withdraw their own bookings. Idempotent.
    """
    from campus.api import resources
    from campus.api.resources.circle import (
        ACCESS_SELF,
        ACCESS_VIEWER,
        circle_storage,
    )
    from campus.common import schema


    _ensure_user_circle(user_id)
    staff_circles = circle_storage.get_matching({"name": "staff"})
    if not staff_circles:
        resources.circle.new(
            name="staff",
            tag="group",
            description="Primary staff group (baseline viewer)",
        )
        staff_circles = circle_storage.get_matching({"name": "staff"})
    staff_id = schema.CampusID(staff_circles[0][schema.CAMPUS_KEY])
    if user_id not in staff_circles[0].get("members", {}):
        resources.circle.members.add(
            staff_id,
            member_id=schema.CampusID(user_id),
            access_value=ACCESS_VIEWER,
        )
    # staff → venues at self: own-bookings management for all staff.
    venues_circles = circle_storage.get_matching({"name": "venues"})
    assert venues_circles, "No 'venues' grant circle: run the bootstrap"
    venues_id = schema.CampusID(venues_circles[0][schema.CAMPUS_KEY])
    if str(staff_id) not in venues_circles[0].get("members", {}):
        resources.circle.members.add(
            venues_id,
            member_id=staff_id,
            access_value=ACCESS_SELF,
        )


def grant_category_booking_admin(user_id: str, category: str) -> None:
    """Grant `user_id` booking authority on a venue category.

    The ratified shape: a member-list subcircle whose label is the
    category slug, contained in the `venues` grant circle with an
    edge at `admin` — the user joins the SUBCIRCLE (containment), and
    authority resolves through the subcircle's family edge,
    category-narrowed. NOT any other family's edges: the subcircle
    grants nothing outside its category. Idempotent.
    """
    from campus.api import resources
    from campus.api.authz import category_slug
    from campus.api.resources.circle import (
        ACCESS_ADMIN,
        ACCESS_VIEWER,
        circle_storage,
    )
    from campus.common import schema

    _ensure_user_circle(user_id)
    slug = category_slug(category)
    venues_circles = circle_storage.get_matching({"name": "venues"})
    assert venues_circles, "No 'venues' grant circle: run the bootstrap"
    venues_id = schema.CampusID(venues_circles[0][schema.CAMPUS_KEY])

    subcircle_matches = circle_storage.get_matching({"name": slug})
    if not subcircle_matches:
        resources.circle.new(
            name=slug,
            tag="category",
            description=f"Venue-category booking approvers: {category}",
            parents={venues_id: ACCESS_ADMIN},
        )
        subcircle_matches = circle_storage.get_matching({"name": slug})
    subcircle_id = schema.CampusID(subcircle_matches[0][schema.CAMPUS_KEY])
    if user_id not in subcircle_matches[0].get("members", {}):
        resources.circle.members.add(
            subcircle_id,
            member_id=schema.CampusID(user_id),
            access_value=ACCESS_VIEWER,
        )
