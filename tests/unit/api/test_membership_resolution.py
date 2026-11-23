"""Unit tests for the shared membership resolvers.

resources.circle.resolve_member is the single implementation of
"can this member be reached from this circle" (value at the hit
circle); resolve_family_access is the ratified family resolution
(baseline + family-directed edges, category-narrowed) that the
enforcement gate answers through. Both are exercised here, with the
gate == family-resolution consistency pinned by randomized graphs.
"""

import random
import unittest

import flask

from campus.common import env, schema
from campus.common.errors import api_errors

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")

TEST_USER = "teacher@campus.test"
OUTSIDER = "outsider@campus.test"

# The ratified constants, for graph wiring.
CONSTANTS = (2, 14, 18, 54, 126)


class ResolverTestBase(unittest.TestCase):
    """Shared harness: fresh bootstrapped circle store per test."""

    def setUp(self):
        from campus.api.resources.circle import (
            CirclesResource,
            circle_storage,
        )

        circle_storage.delete_matching({})
        CirclesResource.init_storage()

    def tearDown(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def _user_circle(self, email: str) -> None:
        from campus.api import resources
        from campus.api.resources.circle import circle_storage
        if not circle_storage.get_matching({"name": email}):
            resources.circle.new(name=email, tag="user")

    def _group(self, name: str, tag: str = "group") -> str:
        from campus.api import resources
        from campus.common import schema
        return str(schema.CampusID(
            resources.circle.new(name=name, tag=tag).id
        ))

    def _family_id(self, family: str = "timetable"):
        from campus.api.resources.circle import circle_storage
        from campus.common import schema
        matches = circle_storage.get_matching({"name": family})
        assert matches, f"No '{family}' grant circle: run the bootstrap"
        return schema.CampusID(matches[0][schema.CAMPUS_KEY])

    def _add(self, circle_id, member_id, access_value=126):
        from campus.api import resources
        from campus.common import schema
        resources.circle.members.add(
            circle_id if not isinstance(circle_id, str) else
            schema.CampusID(circle_id),
            member_id=schema.CampusID(member_id),
            access_value=access_value,
        )


class TestResolveMember(ResolverTestBase):
    """resolve_member answers the graph question (#1197 semantics)."""

    def test_direct_hit(self):
        """A direct edge resolves with direct=True and an empty via."""
        from campus.api.resources.circle import ACCESS_ADMIN, resolve_member
        from campus.common import schema

        self._user_circle(TEST_USER)
        family_id = self._family_id()
        self._add(family_id, TEST_USER, ACCESS_ADMIN)
        self.assertEqual(
            resolve_member(family_id, schema.CampusID(TEST_USER)),
            {
                "member_id": TEST_USER,
                "access_value": ACCESS_ADMIN,
                "direct": True,
                "via": [],
            },
        )

    def test_direct_only_mode_ignores_groups(self):
        """transitive=False answers the direct-only question (#1098)."""
        from campus.api.resources.circle import resolve_member

        self._user_circle(TEST_USER)
        group_id = self._group("students-group")
        self._add(group_id, TEST_USER)
        self._add(self._family_id(), group_id)
        self.assertIsNone(
            resolve_member(
                self._family_id(), schema.CampusID(TEST_USER),
                transitive=False,
            )
        )

    def test_transitive_via_group_reports_chain(self):
        """A group-only member resolves with the containment chain."""
        from campus.api.resources.circle import ACCESS_GUEST, resolve_member

        self._user_circle(TEST_USER)
        group_id = self._group("students-group")
        self._add(group_id, TEST_USER, ACCESS_GUEST)
        self._add(self._family_id(), group_id)
        self.assertEqual(
            resolve_member(self._family_id(), schema.CampusID(TEST_USER)),
            {
                "member_id": TEST_USER,
                "access_value": ACCESS_GUEST,  # the user→group edge value
                "direct": False,
                "via": ["students-group"],
            },
        )

    def test_transitive_nested_chain(self):
        """The via chain lists every hop, target to hit (#1197 walk)."""
        from campus.api.resources.circle import resolve_member

        self._user_circle(TEST_USER)
        outer = self._group("outer-group")
        inner = self._group("inner-group")
        self._add(inner, TEST_USER)
        self._add(outer, inner)
        self._add(self._family_id(), outer)
        resolution = resolve_member(
            self._family_id(), schema.CampusID(TEST_USER)
        )
        self.assertEqual(resolution["via"], ["outer-group", "inner-group"])
        self.assertFalse(resolution["direct"])

    def test_multi_path_reports_max_access_value(self):
        """access_value is the max across resolving paths (#1202 ruling).

        Edges are uniform — a circle is a member wherever it appears —
        so the most permissive path is the member's effective access.
        """
        from campus.api.resources.circle import (
            ACCESS_ADMIN,
            ACCESS_GUEST,
            resolve_member,
        )

        self._user_circle(TEST_USER)
        group_id = self._group("students-group")
        self._add(group_id, TEST_USER, ACCESS_ADMIN)
        self._add(self._family_id(), group_id, ACCESS_GUEST)
        # Direct edge with a LOWER constant than the group path.
        self._add(self._family_id(), TEST_USER, ACCESS_GUEST)
        resolution = resolve_member(
            self._family_id(), schema.CampusID(TEST_USER)
        )
        self.assertTrue(resolution["direct"])
        self.assertEqual(resolution["access_value"], ACCESS_ADMIN)
        self.assertEqual(resolution["via"], [])

    def test_stale_group_key_fails_closed_per_key(self):
        """A deleted member circle is skipped; the rest still resolve."""
        from campus.api.resources.circle import (
            circle_storage,
            resolve_member,
        )
        from campus.common import schema

        self._user_circle(TEST_USER)
        stale = self._group("graduated-cohort")
        good = self._group("students-group")
        self._add(good, TEST_USER)
        family_id = self._family_id()
        self._add(family_id, stale)
        self._add(family_id, good)
        circle_storage.delete_by_id(schema.CampusID(stale))
        resolution = resolve_member(family_id, schema.CampusID(TEST_USER))
        self.assertIsNotNone(resolution)
        self.assertEqual(resolution["via"], ["students-group"])

    def test_unreachable_member_resolves_none(self):
        """No path to the member is the fail-closed negative (None)."""
        from campus.api.resources.circle import resolve_member

        self._user_circle(TEST_USER)
        detached = self._group("other-dept")
        self._add(detached, TEST_USER)
        self.assertIsNone(
            resolve_member(self._family_id(), schema.CampusID(TEST_USER))
        )

    def test_cycle_terminates(self):
        """A cycle between member groups terminates (#1197)."""
        from campus.api.resources.circle import resolve_member

        self._user_circle(TEST_USER)
        a = self._group("cycle-a")
        b = self._group("cycle-b")
        self._add(a, TEST_USER)
        self._add(b, a)
        self._add(a, b)
        self._add(self._family_id(), b)
        resolution = resolve_member(
            self._family_id(), schema.CampusID(TEST_USER)
        )
        self.assertIsNotNone(resolution)

    def test_missing_circle_raises_conflict(self):
        """A missing target circle is an error, not a negative."""
        from campus.api.resources.circle import resolve_member
        from campus.common import schema

        with self.assertRaises(api_errors.ConflictError):
            resolve_member(
                schema.CampusID("nonexistent_id"),
                schema.CampusID(TEST_USER),
            )

    def test_resolves_circle_uid_members_too(self):
        """The resolver answers for group members, not only users."""
        from campus.api.resources.circle import resolve_member
        from campus.common import schema

        outer = self._group("outer-group")
        inner = self._group("inner-group")
        self._add(inner, schema.CampusID(outer))
        self._add(self._family_id(), schema.CampusID(inner))
        resolution = resolve_member(
            self._family_id(), schema.CampusID(outer)
        )
        self.assertIsNotNone(resolution)
        self.assertEqual(resolution["via"], ["inner-group"])


class TestResolveFamilyAccess(ResolverTestBase):
    """resolve_family_access: baseline + family edges, per scope."""

    def test_baseline_only(self):
        """A primary-group membership alone is the platform floor."""
        from campus.api.resources.circle import (
            ACCESS_GUEST,
            resolve_family_access,
        )
        from campus.common import schema

        self._user_circle(TEST_USER)
        student_id = self._group("student")
        self._add(student_id, TEST_USER, ACCESS_GUEST)
        access = resolve_family_access("timetable", schema.CampusID(TEST_USER))
        self.assertEqual(access["baseline"], ACCESS_GUEST)
        self.assertEqual(access["s"], ACCESS_GUEST & 0b00001110)
        self.assertEqual(access["g"], ACCESS_GUEST & 0b01110000)

    def test_family_edge_raises_above_baseline(self):
        """A family-directed edge lifts the effective fields."""
        from campus.api.resources.circle import (
            ACCESS_ADMIN,
            ACCESS_VIEWER,
            resolve_family_access,
        )
        from campus.common import schema

        self._user_circle(TEST_USER)
        staff_id = self._group("staff")
        self._add(staff_id, TEST_USER, ACCESS_VIEWER)
        family_id = self._family_id()
        self._add(family_id, staff_id, ACCESS_ADMIN)
        access = resolve_family_access("timetable", schema.CampusID(TEST_USER))
        self.assertEqual(access["g"], ACCESS_ADMIN & 0b01110000)
        self.assertEqual(access["s"], ACCESS_ADMIN & 0b00001110)

    def test_uncategorized_returns_none_for_missing_family(self):
        """No grant circle: the fail-closed None the gate denies on."""
        from campus.api.resources.circle import resolve_family_access
        from campus.common import schema

        self._user_circle(TEST_USER)
        self.assertIsNone(
            resolve_family_access("bookings", schema.CampusID(TEST_USER))
        )


class TestGateProbeConsistency(ResolverTestBase):
    """Gate decision == family resolution, by construction.

    The property behind #1202, restated for the ratified model:
    require_resource_admin (effective G-create on the family) and
    resolve_family_access must answer identically on any graph.
    Randomized small graphs (seeded, reproducible) with direct edges,
    nested member circles, cycles, and stale keys.
    """

    def _build_random_graph(self, rng: random.Random, seed: int) -> tuple:
        """Wire a random membership graph; returns the user emails.

        Member circles may reference each other freely (cycles
        included); users attach to random circles and, sometimes,
        directly to the family. Some circles are deleted after wiring
        (stale keys). Names embed the seed: builds share one storage,
        and circle names are unique (best-effort).
        """
        from campus.api import resources
        from campus.api.resources.circle import circle_storage
        from campus.common import schema

        family_id = self._family_id("circles")

        circles = []
        for i in range(rng.randint(3, 7)):
            circle = resources.circle.new(
                name=f"grp-{seed}-{i}", tag="group"
            )
            circles.append(str(schema.CampusID(circle.id)))
        # Random inter-circle edges (nesting and cycles).
        for circle_id in circles:
            for _ in range(rng.randint(0, 2)):
                target = rng.choice(circles)
                if target != circle_id:
                    self._add(circle_id, target, rng.choice(CONSTANTS))
        users = []
        for i in range(rng.randint(2, 5)):
            email = f"user{seed}-{i}@campus.test"
            resources.circle.new(name=email, tag="user")
            users.append(email)
            for _ in range(rng.randint(0, 2)):
                self._add(rng.choice(circles), email, rng.choice(CONSTANTS))
            if rng.random() < 0.3:
                self._add(family_id, email, rng.choice(CONSTANTS))
        # Stale keys: wire then delete some circles.
        for circle_id in circles[:rng.randint(0, 2)]:
            self._add(family_id, circle_id, rng.choice(CONSTANTS))
            circle_storage.delete_by_id(schema.CampusID(circle_id))
        # The family must keep at least one live reference path or the
        # graph is trivially all-negative — re-add a live circle.
        live = circles[-1]
        self._add(family_id, live, rng.choice(CONSTANTS))
        return users

    def _gate_passes(self, user_id: str, resource: str = "circles") -> bool:
        from campus.api.authz import require_resource_admin

        app = flask.Flask(__name__)
        with app.test_request_context():
            flask.g.current_user = {"id": user_id}
            try:
                require_resource_admin(resource)
            except api_errors.ForbiddenError:
                return False
        return True

    def test_gate_equals_family_resolution(self):
        """For every user on random graphs: gate == effective G-create."""
        from campus.api.resources.circle import (
            has_permission,
            resolve_family_access,
        )
        from campus.common import schema

        for seed in range(20):
            rng = random.Random(seed)
            users = self._build_random_graph(rng, seed)
            for user_id in users:
                gate = self._gate_passes(user_id)
                access = resolve_family_access(
                    "circles", schema.CampusID(user_id)
                )
                probe = access is not None and has_permission(
                    access["g"], "group", "create"
                )
                self.assertEqual(
                    gate, probe,
                    f"seed={seed} user={user_id}: "
                    f"gate={gate} probe={probe}"
                )

    def test_direct_answer_never_exceeds_transitive(self):
        """A direct hit implies a transitive hit (fast-path safety)."""
        from campus.api.resources.circle import resolve_member
        from campus.common import schema

        for seed in range(20):
            rng = random.Random(seed)
            users = self._build_random_graph(rng, seed)
            family_id = self._family_id("circles")
            for user_id in users:
                direct = resolve_member(
                    family_id, schema.CampusID(user_id), transitive=False,
                ) is not None
                transitive = resolve_member(
                    family_id, schema.CampusID(user_id)
                ) is not None
                if direct:
                    self.assertTrue(
                        transitive,
                        f"seed={seed} user={user_id}"
                    )


if __name__ == "__main__":
    unittest.main()
