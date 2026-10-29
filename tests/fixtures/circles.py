"""tests.fixtures.circles

Helpers for circle access control in tests.

The api gates mutation routes behind `<resource>.admin` role circles
(docs/circles-access-control.md). Tests exercising those routes grant
their user membership through this helper. It works directly against
the resource layer, which stays ungated for in-process callers.
"""

__all__ = ["grant_circle_admin"]


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
