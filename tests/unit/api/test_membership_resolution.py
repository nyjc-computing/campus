"""Unit tests for the shared membership resolver (#1202).

resources.circle.resolve_member is the single implementation of
"can this member be reached from this circle": the enforcement gate
(campus.api.authz.require_resource_admin) and the transitive probe
(GET /circles/{id}/members/{member_id}?resolve=transitive) both answer
through it, so their decisions must agree — asserted directly by the
randomized consistency test at the bottom.
"""

import random
import unittest

import flask

from campus.common import env
from campus.common.errors import api_errors

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")

TEST_USER = "teacher@campus.test"
OUTSIDER = "outsider@campus.test"


class TestResolveMember(unittest.TestCase):
    """resolve_member answers the graph question with #1197 semantics."""

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

    def _group(self, name: str) -> str:
        from campus.api import resources
        from campus.common import schema
        return str(schema.CampusID(
            resources.circle.new(name=name, tag="group").id
        ))

    def _role_id(self, family: str = "timetable"):
        from campus.api.resources.circle import circle_storage
        from campus.common import schema
        role = circle_storage.get_matching({"name": f"{family}.admin"})
        assert role, f"No '{family}.admin' role circle: run the bootstrap"
        return schema.CampusID(role[0][schema.CAMPUS_KEY])

    def _add(self, circle_id, member_id, access_value=15):
        from campus.api import resources
        from campus.common import schema
        resources.circle.members.add(
            circle_id if not isinstance(circle_id, str) else
            schema.CampusID(circle_id),
            member_id=schema.CampusID(member_id),
            access_value=access_value,
        )

    def test_direct_hit(self):
        """A direct edge resolves with direct=True and an empty via."""
        from campus.api.resources.circle import resolve_member
        from campus.common import schema

        self._user_circle(TEST_USER)
        role_id = self._role_id()
        self._add(role_id, TEST_USER, 15)
        self.assertEqual(
            resolve_member(role_id, schema.CampusID(TEST_USER)),
            {
                "member_id": TEST_USER,
                "access_value": 15,
                "direct": True,
                "via": [],
            },
        )

    def test_direct_only_mode_ignores_groups(self):
        """transitive=False answers the direct-only question (#1098)."""
        from campus.api.resources.circle import resolve_member
        from campus.common import schema

        self._user_circle(TEST_USER)
        group_id = self._group("students")
        self._add(group_id, TEST_USER)
        self._add(self._role_id(), group_id)
        self.assertIsNone(
            resolve_member(
                self._role_id(), schema.CampusID(TEST_USER),
                transitive=False,
            )
        )

    def test_transitive_via_group_reports_chain(self):
        """A group-only member resolves with the containment chain."""
        from campus.api.resources.circle import resolve_member
        from campus.common import schema

        self._user_circle(TEST_USER)
        group_id = self._group("students")
        self._add(group_id, TEST_USER)
        self._add(self._role_id(), group_id)
        self.assertEqual(
            resolve_member(self._role_id(), schema.CampusID(TEST_USER)),
            {
                "member_id": TEST_USER,
                "access_value": 15,
                "direct": False,
                "via": ["students"],
            },
        )

    def test_transitive_nested_chain(self):
        """The via chain lists every hop, target to hit (#1197 walk)."""
        from campus.api.resources.circle import resolve_member
        from campus.common import schema

        self._user_circle(TEST_USER)
        outer = self._group("staff")
        inner = self._group("teachers")
        self._add(inner, TEST_USER)
        self._add(outer, inner)
        self._add(self._role_id(), outer)
        resolution = resolve_member(
            self._role_id(), schema.CampusID(TEST_USER)
        )
        self.assertEqual(resolution["via"], ["staff", "teachers"])
        self.assertFalse(resolution["direct"])

    def test_multi_path_reports_max_access_value(self):
        """access_value is the max across resolving paths (#1202 ruling).

        Edges are uniform — a circle is a member wherever it appears —
        so the most permissive path is the member's effective access.
        """
        from campus.api.resources.circle import resolve_member
        from campus.common import schema

        self._user_circle(TEST_USER)
        group_id = self._group("students")
        self._add(group_id, TEST_USER, 10)
        self._add(self._role_id(), group_id, 15)
        # Direct edge with a LOWER value than the group path.
        self._add(self._role_id(), TEST_USER, 5)
        resolution = resolve_member(
            self._role_id(), schema.CampusID(TEST_USER)
        )
        self.assertTrue(resolution["direct"])
        self.assertEqual(resolution["access_value"], 10)
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
        good = self._group("students")
        self._add(good, TEST_USER)
        role_id = self._role_id()
        self._add(role_id, stale)
        self._add(role_id, good)
        circle_storage.delete_by_id(schema.CampusID(stale))
        resolution = resolve_member(role_id, schema.CampusID(TEST_USER))
        self.assertIsNotNone(resolution)
        self.assertEqual(resolution["via"], ["students"])

    def test_unreachable_member_resolves_none(self):
        """No path to the member is the fail-closed negative (None)."""
        from campus.api.resources.circle import resolve_member
        from campus.common import schema

        self._user_circle(TEST_USER)
        detached = self._group("other-dept")
        self._add(detached, TEST_USER)
        self.assertIsNone(
            resolve_member(self._role_id(), schema.CampusID(TEST_USER))
        )

    def test_cycle_terminates(self):
        """A cycle between member groups terminates (#1197)."""
        from campus.api.resources.circle import resolve_member
        from campus.common import schema

        self._user_circle(TEST_USER)
        a = self._group("cycle-a")
        b = self._group("cycle-b")
        self._add(a, TEST_USER)
        self._add(b, a)
        self._add(a, b)
        self._add(self._role_id(), b)
        resolution = resolve_member(
            self._role_id(), schema.CampusID(TEST_USER)
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
        """The resolver answers for group members, not only users.

        The probe accepts any member identifier as stored; resolving a
        circle UID walks the same graph (e.g. "is this group under
        this circle").
        """
        from campus.api.resources.circle import resolve_member
        from campus.common import schema

        outer = self._group("staff")
        inner = self._group("teachers")
        self._add(inner, schema.CampusID(outer))
        self._add(self._role_id(), schema.CampusID(inner))
        resolution = resolve_member(
            self._role_id(), schema.CampusID(outer)
        )
        self.assertIsNotNone(resolution)
        self.assertEqual(resolution["via"], ["teachers"])


class TestGateProbeConsistency(unittest.TestCase):
    """Gate decision == transitive probe decision, by construction.

    The property behind #1202: require_resource_admin and
    resolve_member(transitive=True) must answer identically for the
    same (user, role circle) pair, on any graph. Randomized small
    graphs (seeded, reproducible) with direct edges, nested groups,
    cycles, and stale keys.
    """

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

    def _build_random_graph(self, rng: random.Random, seed: int) -> tuple:
        """Wire a random membership graph; returns the user emails.

        Groups may reference each other freely (cycles included);
        users attach to random groups and, sometimes, directly to the
        role circle. Some groups are deleted after wiring (stale keys).
        Names embed the seed: builds share one storage, and circle
        names are unique (best-effort).
        """
        from campus.api import resources
        from campus.api.resources.circle import circle_storage
        from campus.common import schema

        role = circle_storage.get_matching({"name": "circles.admin"})[0]
        role_id = schema.CampusID(role[schema.CAMPUS_KEY])

        groups = []
        for i in range(rng.randint(3, 7)):
            group = resources.circle.new(
                name=f"grp-{seed}-{i}", tag="group"
            )
            groups.append(str(schema.CampusID(group.id)))
        # Random inter-group edges (nesting and cycles).
        for group_id in groups:
            for _ in range(rng.randint(0, 2)):
                target = rng.choice(groups)
                if target != group_id:
                    self._add(group_id, target, rng.randint(1, 15))
        users = []
        for i in range(rng.randint(2, 5)):
            email = f"user{seed}-{i}@campus.test"
            resources.circle.new(name=email, tag="user")
            users.append(email)
            for _ in range(rng.randint(0, 2)):
                self._add(rng.choice(groups), email, rng.randint(1, 15))
            if rng.random() < 0.3:
                self._add(role_id, email, rng.randint(1, 15))
        # Stale keys: wire then delete some groups.
        for group_id in groups[:rng.randint(0, 2)]:
            self._add(role_id, group_id, 15)
            circle_storage.delete_by_id(schema.CampusID(group_id))
        # The role circle must keep at least one live reference path or
        # the graph is trivially all-negative — re-add a live group.
        live = groups[-1]
        self._add(role_id, live, 15)
        return users, role_id

    def _add(self, circle_id, member_id, access_value):
        from campus.api import resources
        from campus.common import schema
        resources.circle.members.add(
            schema.CampusID(str(circle_id)),
            member_id=schema.CampusID(member_id),
            access_value=access_value,
        )

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

    def test_gate_equals_transitive_probe(self):
        """For every user on random graphs: gate == probe(transitive)."""
        from campus.api.resources.circle import resolve_member
        from campus.common import schema

        for seed in range(20):
            rng = random.Random(seed)
            users, role_id = self._build_random_graph(rng, seed)
            for user_id in users:
                gate = self._gate_passes(user_id)
                probe = resolve_member(
                    role_id, schema.CampusID(user_id)
                ) is not None
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
            users, role_id = self._build_random_graph(rng, seed)
            for user_id in users:
                direct = resolve_member(
                    role_id, schema.CampusID(user_id), transitive=False,
                ) is not None
                transitive = resolve_member(
                    role_id, schema.CampusID(user_id)
                ) is not None
                if direct:
                    self.assertTrue(
                        transitive,
                        f"seed={seed} user={user_id}"
                    )


if __name__ == "__main__":
    unittest.main()
