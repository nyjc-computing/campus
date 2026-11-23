"""tests.fixtures.circles

Helpers for circle access control in tests.

The api gates mutation routes behind `<resource>.admin` role circles
(docs/circles-access-control.md). Tests exercising those routes grant
their user membership through this helper. It works directly against
the resource layer, which stays ungated for in-process callers.
"""

__all__ = ["grant_circle_admin", "grant_category_booking_admin"]


def grant_circle_admin(user_id: str, *families: str) -> None:
    """Grant `user_id` the admin role on the given api resource families.

    Ensures the user's circle exists (named after the email account)
    and adds it to each `<family>.admin` role circle, which
    `CirclesResource.init_storage()` (run by clear_test_data) seeds.

    Idempotent: an existing user circle or membership is reused.
    """
    from campus.api import resources
    from campus.api.resources.circle import circle_storage
    from campus.common import schema

    if not circle_storage.get_matching({"name": user_id}):
        resources.circle.new(name=user_id, tag="user")

    for family in families:
        role = circle_storage.get_matching({"name": f"{family}.admin"})
        assert role, f"No '{family}.admin' role circle: run the bootstrap"
        role_id = schema.CampusID(role[0][schema.CAMPUS_KEY])
        if user_id not in role[0].get("members", {}):
            resources.circle.members.add(
                role_id,
                member_id=schema.CampusID(user_id),
                access_value=15,
            )

def grant_category_booking_admin(user_id: str, category: str) -> None:
    """Grant `user_id` booking authority on a venue category (campus#1217).

    Creates the standalone `venues.<category-slug>.admin` role circle
    if absent (the bootstrap deliberately does not seed scoped
    circles - they are school data), ensures the user's circle
    exists, and adds the user at access 15. NOT a member of
    `venues.admin`: the scoped circles stay a separate branch so
    transitive resolution cannot widen them to all-venue authority.
    """
    from campus.api import resources
    from campus.api.authz import category_slug
    from campus.api.resources.circle import circle_storage
    from campus.common import schema

    if not circle_storage.get_matching({"name": user_id}):
        resources.circle.new(name=user_id, tag="user")

    role_name = f"venues.{category_slug(category)}.admin"
    role = circle_storage.get_matching({"name": role_name})
    if not role:
        resources.circle.new(name=role_name, tag="role")
        role = circle_storage.get_matching({"name": role_name})
    role_id = schema.CampusID(role[0][schema.CAMPUS_KEY])
    if user_id not in role[0].get("members", {}):
        resources.circle.members.add(
            role_id,
            member_id=schema.CampusID(user_id),
            access_value=15,
        )
