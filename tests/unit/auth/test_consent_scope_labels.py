"""Unit tests for consent-scope disclosure labels (#871).

Covers the users:* management-scope labels added to
`_SCOPE_CONSENT_LABELS` and the "mod" verb in the generic
`<resource>:<level>` fallback, both rendered by `_describe_scope`
(#867) on the device verification page.
"""

import unittest

from campus.auth.routes.oauth import _describe_scope


class TestUsersScopeLabels(unittest.TestCase):
    """Curated consent labels for the users:* vocabulary (#871)."""

    def test_users_read_label(self):
        self.assertEqual(
            _describe_scope("users:read"),
            {
                "scope": "users:read",
                "label": "View users",
                "description": "View Campus user records",
            },
        )

    def test_users_mod_label(self):
        self.assertEqual(
            _describe_scope("users:mod"),
            {
                "scope": "users:mod",
                "label": "Activate users",
                "description": "Activate Campus user accounts",
            },
        )

    def test_users_write_label(self):
        self.assertEqual(
            _describe_scope("users:write"),
            {
                "scope": "users:write",
                "label": "Manage users",
                "description": "Create, rename and activate Campus users",
            },
        )

    def test_vaults_read_label(self):
        self.assertEqual(
            _describe_scope("vaults:read")["label"],
            "View vault secrets",
        )

    def test_vaults_write_label(self):
        self.assertEqual(
            _describe_scope("vaults:write")["label"],
            "Manage vault secrets",
        )

    def test_vaults_admin_label(self):
        self.assertEqual(
            _describe_scope("vaults:admin")["label"],
            "Fully manage vault secrets",
        )

    def test_users_admin_label(self):
        self.assertEqual(
            _describe_scope("users:admin"),
            {
                "scope": "users:admin",
                "label": "Fully manage users",
                "description": (
                    "Delete Campus users; includes all lower user management"
                ),
            },
        )


class TestScopeFallback(unittest.TestCase):
    """Generic <resource>:<level> and raw-token fallbacks (#867)."""

    def test_mod_level_verb_fallback(self):
        """An unlisted <resource>:mod scope degrades to the verb map."""
        self.assertEqual(
            _describe_scope("someother:mod"),
            {
                "scope": "someother:mod",
                "label": "Moderate someother",
                "description": None,
            },
        )

    def test_unknown_level_renders_raw(self):
        """A scope with an unknown level renders as the raw token."""
        self.assertEqual(
            _describe_scope("someother:weird"),
            {
                "scope": "someother:weird",
                "label": "someother:weird",
                "description": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
