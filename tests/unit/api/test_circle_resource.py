"""Unit tests for the circles resource @meta handling.

Regression coverage for #501/#760: the @meta bootstrap record lives in
the circles collection but is not itself a circle, so CirclesResource.list()
must exclude it instead of failing to hydrate it (the root cause of the
dev GET /circles/ 500).

Also covers #501/#761: best-effort circle name uniqueness (create +
rename) and PATCH-on-missing-circle surfacing as ConflictError (the
memory collection backend used to silently no-op update_by_id).
"""

import unittest

from campus.common import env

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")


class TestCirclesResourceList(unittest.TestCase):
    """CirclesResource.list() must exclude the @meta bookkeeping record."""

    def setUp(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def tearDown(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def test_list_excludes_meta_record(self):
        """list() skips the @meta record instead of failing hydration."""
        from campus.api.resources.circle import CirclesResource, circle_storage

        # init_storage seeds the @meta record, root and admin circles —
        # the same state that triggers the dev 500 without the filter.
        CirclesResource.init_storage()

        circles = CirclesResource().list()

        names = [circle.name for circle in circles]
        self.assertIn("nyjc.edu.sg", names)
        self.assertIn("campus-admin", names)
        # Hydrated circles only: every record must carry circle fields
        self.assertTrue(all(circle.tag for circle in circles))

        # The filter excludes but never removes the meta record
        metas = circle_storage.get_matching({"@meta": True})
        self.assertEqual(len(metas), 1)


class TestCirclesResourceNameUniqueness(unittest.TestCase):
    """Circle names are unique (best-effort, exact match) on create + rename."""

    def setUp(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def tearDown(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def _new_circle(self, name: str, tag: str = "test"):
        from campus.api import resources
        return resources.circle.new(name=name, tag=tag)

    def test_new_rejects_duplicate_name(self):
        """new() raises ConflictError when the name is already taken."""
        from campus.common.errors import api_errors

        self._new_circle("Dup Circle", tag="first")
        with self.assertRaises(api_errors.ConflictError):
            self._new_circle("Dup Circle", tag="second")

    def test_update_rejects_duplicate_name(self):
        """update() raises ConflictError when renaming onto another circle."""
        from campus.common.errors import api_errors

        self._new_circle("First Circle")
        second = self._new_circle("Second Circle")

        from campus.api import resources
        with self.assertRaises(api_errors.ConflictError):
            resources.circle[str(second.id)].update(name="First Circle")

        # The failed rename changed nothing
        unchanged = resources.circle[str(second.id)].get()
        self.assertEqual(unchanged.name, "Second Circle")

    def test_update_own_name_is_noop(self):
        """update() allows renaming a circle to its own name."""
        from campus.api import resources

        circle = self._new_circle("Stable Circle")
        resources.circle[str(circle.id)].update(name="Stable Circle")

        unchanged = resources.circle[str(circle.id)].get()
        self.assertEqual(unchanged.name, "Stable Circle")

    def test_update_missing_circle_raises_conflict(self):
        """update() raises ConflictError (not a silent no-op) for a missing circle."""
        from campus.api import resources
        from campus.common.errors import api_errors

        with self.assertRaises(api_errors.ConflictError):
            resources.circle["no_such_circle"].update(name="New Name")


class TestCirclesResourceBootstrap(unittest.TestCase):
    """init_storage seeds the access-control bootstrap circles (idempotently)."""

    def setUp(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def tearDown(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def test_bootstrap_seeds_resource_and_role_circles(self):
        """Each guarded resource gets a resource circle and an admin role circle."""
        from campus.api.resources.circle import BOOTSTRAP_RESOURCES, CirclesResource

        CirclesResource.init_storage()

        names = {c.name for c in CirclesResource().list()}
        for resource_name in BOOTSTRAP_RESOURCES:
            self.assertIn(resource_name, names)
            self.assertIn(f"{resource_name}.admin", names)

    def test_bootstrap_role_circle_hierarchy(self):
        """Role circles are tagged "role" and members of their resource circle."""
        from campus.api.resources.circle import (
            RESOURCE_TAG,
            ROLE_TAG,
            CirclesResource,
            circle_storage,
        )
        from campus.common import schema

        CirclesResource.init_storage()

        resource_record = circle_storage.get_matching(
            {"name": "circles"}
        )[0]
        role_record = circle_storage.get_matching(
            {"name": "circles.admin"}
        )[0]

        self.assertEqual(resource_record["tag"], RESOURCE_TAG)
        self.assertEqual(role_record["tag"], ROLE_TAG)
        self.assertIn(
            role_record[schema.CAMPUS_KEY],
            resource_record["members"],
        )

    def test_bootstrap_seeds_admin_user(self):
        """Every temporary bootstrap admin is a member of every role circle."""
        from campus.api.resources.circle import (
            BOOTSTRAP_ACCESS_VALUE,
            BOOTSTRAP_ADMIN_USERS,
            BOOTSTRAP_RESOURCES,
            CirclesResource,
            circle_storage,
        )

        CirclesResource.init_storage()

        for resource_name in BOOTSTRAP_RESOURCES:
            role_record = circle_storage.get_matching(
                {"name": f"{resource_name}.admin"}
            )[0]
            for admin_user in BOOTSTRAP_ADMIN_USERS:
                self.assertEqual(
                    role_record["members"].get(admin_user),
                    BOOTSTRAP_ACCESS_VALUE,
                )

    def test_bootstrap_seeds_user_circle(self):
        """Every bootstrap admin's user circle exists, tagged "user"."""
        from campus.api.resources.circle import (
            BOOTSTRAP_ADMIN_USERS,
            USER_TAG,
            CirclesResource,
            circle_storage,
        )

        CirclesResource.init_storage()

        for admin_user in BOOTSTRAP_ADMIN_USERS:
            user_circles = circle_storage.get_matching(
                {"name": str(admin_user)}
            )
            self.assertEqual(len(user_circles), 1)
            self.assertEqual(user_circles[0]["tag"], USER_TAG)

    def test_bootstrap_is_idempotent(self):
        """Re-running init_storage adds no circles and raises no conflict."""
        from campus.api.resources.circle import CirclesResource

        CirclesResource.init_storage()
        count_after_first = len(CirclesResource().list())

        CirclesResource.init_storage()
        self.assertEqual(len(CirclesResource().list()), count_after_first)


class TestCircleUserMembers(unittest.TestCase):
    """Users join circles through their email-named user circles."""

    def setUp(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def tearDown(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def _new_circle(self, name: str, tag: str = "test"):
        from campus.api import resources
        return resources.circle.new(name=name, tag=tag)

    def _new_user_circle(self, email: str):
        """A user circle, named after the email account."""
        return self._new_circle(email, tag="user")

    def test_add_and_remove_user_member(self):
        """A user is added via their user circle and removed again."""
        from campus.api import resources

        self._new_user_circle("teacher@campus.test")
        circle = self._new_circle("User Member Circle")
        members = resources.circle.members
        members.add(str(circle.id), "teacher@campus.test", 15)

        self.assertEqual(
            members.list(str(circle.id)).get("teacher@campus.test"), 15
        )

        members.remove(str(circle.id), "teacher@campus.test")
        self.assertNotIn(
            "teacher@campus.test", members.list(str(circle.id))
        )

    def test_user_member_requires_user_circle(self):
        """An email-shaped member without a user circle is rejected."""
        from campus.api import resources
        from campus.common.errors import api_errors

        circle = self._new_circle("No User Circle")
        with self.assertRaises(api_errors.ConflictError):
            resources.circle.members.add(
                str(circle.id), "ghost@campus.test", 15
            )

    def test_user_member_with_dotted_email(self):
        """Dots in user-circle member keys are preserved, not split."""
        from campus.api import resources

        self._new_user_circle("t.user@campus.test")
        circle = self._new_circle("Dotted Email Circle")
        resources.circle.members.add(str(circle.id), "t.user@campus.test", 15)

        stored = resources.circle.members.list(str(circle.id))
        self.assertIn("t.user@campus.test", stored)
        # The dict must not have been split into nested keys
        self.assertNotIn("t", stored)

    def test_add_member_with_unknown_id_shape_raises_conflict(self):
        """Member IDs that address no circle are rejected."""
        from campus.api import resources
        from campus.common.errors import api_errors

        circle = self._new_circle("Bad Member Circle")
        with self.assertRaises(api_errors.ConflictError):
            resources.circle.members.add(str(circle.id), "some-member-id", 15)

    def test_add_missing_circle_member_raises_conflict(self):
        """A circle_-prefixed member ID must exist."""
        from campus.api import resources
        from campus.common.errors import api_errors

        circle = self._new_circle("Missing Member Circle")
        with self.assertRaises(api_errors.ConflictError):
            resources.circle.members.add(
                str(circle.id), "circle_nosuch00", 15
            )

    def test_add_user_member_to_missing_circle_raises_conflict(self):
        """Adding any member to a missing circle is a conflict, not a 500."""
        from campus.api import resources
        from campus.common.errors import api_errors

        self._new_user_circle("teacher@campus.test")
        with self.assertRaises(api_errors.ConflictError):
            resources.circle.members.add(
                "circle_nosuch00", "teacher@campus.test", 15
            )


if __name__ == "__main__":
    unittest.main()
