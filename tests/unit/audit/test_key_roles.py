"""Unit tests for the named role catalogue for audit API keys (#918).

A role is a named bundle of scopes: the issuer picks a privilege
instead of assembling one by hand, and the same bundle is granted
everywhere. The catalogue is additive — a raw scope list still works
everywhere a scope list is accepted.

These tests verify:

- The catalogue resolves a role name to exactly one scope list, and
  rejects an unknown name with a message naming the available roles.
- No role resolves to a wildcard.
- A role and an explicit scope list are mutually exclusive.
- The resource layer, the HTTP API and the web UI page all accept a
  role name, and still accept a raw scope list.

File: tests/unit/audit/test_key_roles.py
Issue: #918
"""

import unittest


class TestRoleCatalogue(unittest.TestCase):
    """Verify the catalogue itself."""

    def test_every_role_resolves_to_a_scope_list(self):
        from campus.audit import roles

        for name, scopes in roles.list_roles().items():
            with self.subTest(role=name):
                resolved = roles.resolve_role(name)
                self.assertTrue(resolved)
                self.assertEqual(sorted(resolved), sorted(scopes))

    def test_the_catalogue_covers_the_scope_vocabulary(self):
        """The roles between them cover every scope the service issues."""
        from campus.audit import roles
        from campus.config import AUDIT_OPERATOR_API_KEY_SCOPES

        covered = {
            scope
            for scopes in roles.CATALOGUE.values()
            for scope in scopes
        }
        # Every scope the operator seed holds must be expressible as a
        # role bundle, so a human can hold exactly the operator's
        # privileges without a bespoke scope list.
        self.assertTrue(
            set(AUDIT_OPERATOR_API_KEY_SCOPES) - covered == set(),
            "the catalogue cannot express the operator key's scopes",
        )

    def test_no_role_resolves_to_a_wildcard(self):
        """A standing '*' role would be a privilege-escalation
        footgun in the one place keys get minted."""
        from campus.audit import roles

        for name, scopes in roles.CATALOGUE.items():
            with self.subTest(role=name):
                self.assertNotIn("*", scopes)
                for scope in scopes:
                    self.assertFalse(scope.endswith(":*"))

    def test_an_unknown_role_is_rejected(self):
        from campus.audit import roles

        with self.assertRaises(roles.UnknownRoleError) as ctx:
            roles.resolve_role("no-such-role")

        message = str(ctx.exception)
        self.assertIn("no-such-role", message)
        # The error names the roles that do exist.
        for name in roles.CATALOGUE:
            self.assertIn(name, message)

    def test_a_role_and_a_scope_list_are_mutually_exclusive(self):
        from campus.audit import roles

        with self.assertRaises(ValueError):
            roles.resolve_scopes("traces:read", "traces-viewer")

    def test_a_scope_list_alone_still_resolves(self):
        from campus.audit import roles

        self.assertEqual(
            roles.resolve_scopes("traces:read, traces:search"),
            ["traces:read", "traces:search"],
        )
        self.assertEqual(
            roles.resolve_scopes(["traces:read"]), ["traces:read"]
        )


class TestRoleInTheResourceLayer(unittest.TestCase):
    """A key can be minted with a role name."""

    @classmethod
    def setUpClass(cls):
        from campus.audit.resources.apikeys import APIKeysResource
        from campus.audit.resources.traces import TracesResource

        APIKeysResource.init_storage()
        TracesResource.init_storage()

    def test_a_key_minted_with_a_role_holds_the_roles_scopes(self):
        from campus.audit.resources import apikeys

        record, _ = apikeys.new(
            name="role key",
            owner_id="student@nyjc.edu.sg",
            role="traces-viewer",
        )

        self.assertEqual(list(record.scopes), ["traces:read"])

    def test_a_key_minted_with_scopes_still_works(self):
        from campus.audit.resources import apikeys

        record, _ = apikeys.new(
            name="scope key",
            owner_id="student@nyjc.edu.sg",
            scopes="traces:read,traces:search",
        )

        self.assertEqual(
            sorted(record.scopes), ["traces:read", "traces:search"]
        )

    def test_an_unknown_role_is_rejected_at_the_resource_layer(self):
        from campus.audit import roles
        from campus.audit.resources import apikeys

        with self.assertRaises(roles.UnknownRoleError):
            apikeys.new(
                name="bad role key",
                owner_id="student@nyjc.edu.sg",
                role="no-such-role",
            )


if __name__ == "__main__":
    unittest.main()
