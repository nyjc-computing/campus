"""Unit tests for the UserCredentials.update() write order (#1085).

The token document must be persisted BEFORE the credential row is
re-pointed at it: a failed token write then leaves the old grant fully
intact — the caller's retry re-runs the whole update — instead of
dangling the row at a document that does not exist, which answers
"No campus grant" on every future mint until a full re-login (the
Oct-26 dev-incident shape).
"""

import unittest
from unittest import mock


class TestUserCredentialsUpdateOrder(unittest.TestCase):
    """update() survives a failed token write with the old grant intact."""

    CLIENT_ID = "uid-client-order-test"

    @classmethod
    def setUpClass(cls):
        # Lazy import: campus.auth pulls in storage modules at import
        # time. See AGENTS.md - Storage Initialization Order. The unit
        # suite runs on the SQLite test backend (STORAGE_MODE=1) so no
        # real Postgres/Mongo is touched.
        from campus.storage import testing as storage_testing

        storage_testing.configure_test_db()
        storage_testing.configure_test_storage()
        import sys

        import campus.storage
        from campus.auth.resources import credentials as credentials_resource

        # Rebind the module's storage singletons to the test backends
        # BEFORE init_storage: sibling modules can import campus.auth at
        # collection time (before STORAGE_MODE is set), binding the
        # module globals to Postgres/Mongo. The rebind also fixes the
        # patch target: token_storage is a module-level global (the
        # resources package __init__ shadows the module name with the
        # singleton, so sys.modules is the reliable handle).
        cls.module = sys.modules["campus.auth.resources.credentials"]
        cls.module.cred_storage = campus.storage.get_table("credentials")
        cls.module.token_storage = campus.storage.get_collection("tokens")
        cls.module.app_cred_storage = campus.storage.get_table(
            "app_credentials")

        credentials_resource.init_storage()
        cls.resource = credentials_resource  # the singleton instance

    def setUp(self):
        self.user_id = "campus.test.order@campus.test"
        self.resource["campus"][self.user_id].delete(self.CLIENT_ID)

    def _old_grant(self):
        """Seed one live grant (row + token doc) via the normal path."""
        from campus.common.utils import secret
        from campus.model import OAuthToken

        old = OAuthToken(
            id=secret.generate_access_token(),
            expires_in=7 * 86_400,
            scopes=["basic"],
        )
        self.resource["campus"][self.user_id].update(
            client_id=self.CLIENT_ID, token=old,
        )
        return old

    def _new_token(self):
        from campus.common.utils import secret
        from campus.model import OAuthToken

        return OAuthToken(
            id=secret.generate_access_token(),
            expires_in=7 * 86_400,
            scopes=["basic", "extra"],
        )

    def _live_token_id(self):
        """The token id the credential row currently resolves to."""
        credentials = self.resource["campus"][self.user_id].get(
            self.CLIENT_ID
        )
        return credentials.token.id if credentials.token else None

    def test_failed_token_write_leaves_old_grant_intact(self):
        old = self._old_grant()
        new = self._new_token()

        with (mock.patch.object(
                self.module.token_storage, "insert_one",
                side_effect=RuntimeError("mongo down")),
              self.assertRaises(RuntimeError)):
            self.resource["campus"][self.user_id].update(
                client_id=self.CLIENT_ID, token=new,
            )

        # The row still resolves to the OLD token document: the grant
        # survived the failed write instead of dangling.
        self.assertEqual(self._live_token_id(), old.id)

    def test_retry_after_failed_write_completes(self):
        self._old_grant()
        new = self._new_token()

        with (mock.patch.object(
                self.module.token_storage, "insert_one",
                side_effect=RuntimeError("mongo down")),
              self.assertRaises(RuntimeError)):
            self.resource["campus"][self.user_id].update(
                client_id=self.CLIENT_ID, token=new,
            )

        # The retry re-runs the whole update and lands.
        self.resource["campus"][self.user_id].update(
            client_id=self.CLIENT_ID, token=new,
        )
        self.assertEqual(self._live_token_id(), new.id)

    def test_failed_update_in_place_keeps_existing_doc(self):
        # token_id unchanged: the upsert path updates the doc in place.
        # A failed update must not corrupt anything either.
        old = self._old_grant()
        resubmitted = type(old)(
            id=old.id, expires_at=old.expires_at, scopes=old.scopes,
        )

        with (mock.patch.object(
                self.module.token_storage, "update_by_id",
                side_effect=RuntimeError("mongo down")),
              self.assertRaises(RuntimeError)):
            self.resource["campus"][self.user_id].update(
                client_id=self.CLIENT_ID, token=resubmitted,
            )

        self.assertEqual(self._live_token_id(), old.id)


if __name__ == "__main__":
    unittest.main()
