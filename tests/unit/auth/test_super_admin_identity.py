"""campus.tests.unit.auth.test_super_admin_identity

The hardcoded production super-admin identity (2026-11-24 decision):

- ENV=production: super_admin_email() derives
  campus-admin@<WORKSPACE_DOMAIN> in code — AUTH_SUPER_ADMIN is not
  consulted, and a missing WORKSPACE_DOMAIN fails closed to no root.
- Other environments: AUTH_SUPER_ADMIN nominates the root as before.
- assert_login_allowed refuses the hardcoded identity's login outside
  production (403) and is a no-op on production; the block targets the
  hardcoded identity, never whatever AUTH_SUPER_ADMIN names.

Lazy imports where a module touches storage-backed resources; authz
itself is import-safe (its resource imports are function-local).
"""

import os
import unittest

from campus.common import env
from campus.common.errors import api_errors

ENV_VARS = ("ENV", "WORKSPACE_DOMAIN", "AUTH_SUPER_ADMIN")


class SuperAdminIdentityTestCase(unittest.TestCase):
    """Harness: pin and restore the env vars the super-admin reads."""

    def setUp(self):
        self._originals = {
            name: os.environ.get(name) for name in ENV_VARS
        }

    def tearDown(self):
        for name, original in self._originals.items():
            if original is None:
                self.unset_env(name)
            else:
                env.set(name, original)

    def set_env(self, **values: str) -> None:
        for name, value in values.items():
            env.set(name, value)

    @staticmethod
    def unset_env(name: str) -> None:
        """Unset an env var if present (env.delete raises when absent)."""
        if env.contains(name):
            env.delete(name)


class TestSuperAdminEmail(SuperAdminIdentityTestCase):
    """super_admin_email(): hardcoded on production, nominated elsewhere."""

    def test_production_identity_is_hardcoded(self):
        from campus.auth import authz

        self.set_env(
            ENV=env.PRODUCTION,
            WORKSPACE_DOMAIN="nyjc.edu.sg",
            # The env nomination must be ignored on production.
            AUTH_SUPER_ADMIN="root@elsewhere.example",
        )
        self.assertEqual(
            authz.super_admin_email(), "campus-admin@nyjc.edu.sg"
        )

    def test_production_without_workspace_domain_fails_closed(self):
        from campus.auth import authz

        self.set_env(ENV=env.PRODUCTION)
        self.unset_env("WORKSPACE_DOMAIN")
        self.set_env(AUTH_SUPER_ADMIN="root@elsewhere.example")
        self.assertIsNone(authz.super_admin_email())

    def test_non_production_uses_env_nomination(self):
        from campus.auth import authz

        self.set_env(
            ENV=env.DEVELOPMENT,
            WORKSPACE_DOMAIN="nyjc.edu.sg",
            AUTH_SUPER_ADMIN="root@nyjc.edu.sg",
        )
        self.assertEqual(authz.super_admin_email(), "root@nyjc.edu.sg")

    def test_non_production_unset_nomination_means_no_root(self):
        from campus.auth import authz

        self.set_env(ENV=env.DEVELOPMENT, WORKSPACE_DOMAIN="nyjc.edu.sg")
        self.unset_env("AUTH_SUPER_ADMIN")
        self.assertIsNone(authz.super_admin_email())


class TestAssertLoginAllowed(SuperAdminIdentityTestCase):
    """assert_login_allowed(): 403 on development, no-op on production."""

    def test_development_blocks_hardcoded_identity(self):
        from campus.auth import authz

        self.set_env(
            ENV=env.DEVELOPMENT, WORKSPACE_DOMAIN="nyjc.edu.sg"
        )
        with self.assertRaises(api_errors.ForbiddenError):
            authz.assert_login_allowed("campus-admin@nyjc.edu.sg")

    def test_development_block_is_case_and_whitespace_insensitive(self):
        from campus.auth import authz

        self.set_env(
            ENV=env.DEVELOPMENT, WORKSPACE_DOMAIN="nyjc.edu.sg"
        )
        with self.assertRaises(api_errors.ForbiddenError):
            authz.assert_login_allowed(" Campus-Admin@NYJC.edu.sg ")

    def test_development_allows_other_identities(self):
        from campus.auth import authz

        self.set_env(
            ENV=env.DEVELOPMENT,
            WORKSPACE_DOMAIN="nyjc.edu.sg",
            AUTH_SUPER_ADMIN="root@nyjc.edu.sg",
        )
        authz.assert_login_allowed("root@nyjc.edu.sg")
        authz.assert_login_allowed("staff.member@nyjc.edu.sg")

    def test_block_targets_hardcoded_identity_not_env_nomination(self):
        from campus.auth import authz

        # Even when AUTH_SUPER_ADMIN names the hardcoded identity on a
        # lower environment, the login block still applies — the block
        # is keyed to the hardcoded production identity, and the env
        # nomination is inert without a login.
        self.set_env(
            ENV=env.DEVELOPMENT,
            WORKSPACE_DOMAIN="nyjc.edu.sg",
            AUTH_SUPER_ADMIN="campus-admin@nyjc.edu.sg",
        )
        self.assertEqual(
            authz.super_admin_email(), "campus-admin@nyjc.edu.sg"
        )
        with self.assertRaises(api_errors.ForbiddenError):
            authz.assert_login_allowed("campus-admin@nyjc.edu.sg")

    def test_env_unset_defaults_to_development_block(self):
        from campus.auth import authz

        self.unset_env("ENV")
        self.set_env(WORKSPACE_DOMAIN="nyjc.edu.sg")
        with self.assertRaises(api_errors.ForbiddenError):
            authz.assert_login_allowed("campus-admin@nyjc.edu.sg")

    def test_production_allows_hardcoded_identity(self):
        from campus.auth import authz

        self.set_env(
            ENV=env.PRODUCTION, WORKSPACE_DOMAIN="nyjc.edu.sg"
        )
        authz.assert_login_allowed("campus-admin@nyjc.edu.sg")

    def test_noop_without_workspace_domain(self):
        from campus.auth import authz

        # No WORKSPACE_DOMAIN means no hardcoded identity to block.
        self.set_env(ENV=env.DEVELOPMENT)
        self.unset_env("WORKSPACE_DOMAIN")
        authz.assert_login_allowed("campus-admin@nyjc.edu.sg")


if __name__ == "__main__":
    unittest.main()
