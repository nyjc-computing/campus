"""Unit tests for the scope algebra helpers (campus.auth.scopes).

Covers the management-scope implication added for #865: within the
`<resource>:<read|mod|write|admin>` convention a higher level
satisfies a lower requirement on the same resource, and never across
resources. The "mod" level sits between read and write
(campus-cli#42).
"""

import unittest

from campus.auth import scopes


class TestParse(unittest.TestCase):
    """scopes.parse normalizes scope values."""

    def test_parse_string_list_and_none(self):
        self.assertEqual(scopes.parse("a b a"), ["a", "b"])
        self.assertEqual(scopes.parse(["b", "a", "b"]), ["b", "a"])
        self.assertEqual(scopes.parse(None), [])

    def test_parse_management_scopes(self):
        self.assertEqual(
            scopes.parse("clients:read clients:write"),
            ["clients:read", "clients:write"],
        )


class TestGrants(unittest.TestCase):
    """scopes.grants: management-scope implication (#865)."""

    def test_exact_match_grants(self):
        self.assertTrue(scopes.grants(["clients:read"], "clients:read"))

    def test_higher_level_implies_lower(self):
        self.assertTrue(scopes.grants(["clients:write"], "clients:read"))
        self.assertTrue(scopes.grants(["clients:admin"], "clients:write"))
        self.assertTrue(scopes.grants(["clients:admin"], "clients:read"))

    def test_lower_level_never_implies_higher(self):
        self.assertFalse(scopes.grants(["clients:read"], "clients:write"))
        self.assertFalse(scopes.grants(["clients:write"], "clients:admin"))

    def test_mod_level_sits_between_read_and_write(self):
        """users:mod implies read; write and admin imply mod (#42)."""
        self.assertTrue(scopes.grants(["users:mod"], "users:read"))
        self.assertTrue(scopes.grants(["users:write"], "users:mod"))
        self.assertTrue(scopes.grants(["users:admin"], "users:mod"))
        self.assertFalse(scopes.grants(["users:read"], "users:mod"))
        self.assertFalse(scopes.grants(["users:mod"], "users:write"))
        self.assertFalse(scopes.grants(["clients:admin"], "users:mod"))

    def test_other_resource_never_grants(self):
        self.assertFalse(scopes.grants(["vaults:admin"], "clients:read"))
        self.assertFalse(scopes.grants(["clients"], "clients:read"))
        self.assertFalse(scopes.grants(["read"], "clients:read"))

    def test_missing_scope_denies(self):
        self.assertFalse(scopes.grants([], "clients:read"))
        self.assertFalse(scopes.grants(["read", "write"], "clients:read"))

    def test_non_leveled_scope_requires_exact_match(self):
        self.assertTrue(scopes.grants(["offline_access"], "offline_access"))
        self.assertFalse(scopes.grants(["clients:admin"], "offline_access"))


class TestCovers(unittest.TestCase):
    """scopes.covers stays exact-set membership (token-request path)."""

    def test_covers_is_exact(self):
        self.assertTrue(scopes.covers(["a", "b"], ["a"]))
        # covers() has no implication: a management level does not
        # cover a lower one as a requested token scope.
        self.assertFalse(scopes.covers(["clients:admin"], ["clients:read"]))


if __name__ == "__main__":
    unittest.main()
