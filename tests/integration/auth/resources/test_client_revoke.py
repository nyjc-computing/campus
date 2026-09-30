"""campus.tests.integration.auth.resources.test_client_revoke

Integration tests for ClientResource.revoke() secret-key resolution.

revoke() used env.SECRET_KEY attribute access, which only reads the
process environment. On Railway the SECRET_KEY lives in the service
vault and is resolved through the registered getsecret fallback, so
every POST /clients/{id}/revoke on dev failed with AttributeError
(after #613 fixed the earlier bodyless-request 500). See #634.

The contract fixtures set the SECRET_KEY environment variable directly,
which masks this failure mode; these tests keep the variable out of the
environment so only the getsecret fallback can supply the key.
"""

import os
import unittest


class TestClientRevoke(unittest.TestCase):
    """Integration tests for ClientsResource[{id}].revoke().

    These tests use the tmpfile-based SQLite pattern for reliable test
    isolation (see test_client_seed.py).
    """

    @classmethod
    def setUpClass(cls):
        """Configure test storage and import the resource once."""
        import campus.storage.testing

        # Configure test mode first
        campus.storage.testing.configure_test_storage()

        # Configure tmpfile-based database (fixed path, avoids readonly errors)
        campus.storage.testing.configure_test_db()

        # Lazy import after test mode is configured
        from campus.auth.resources.client import ClientsResource

        ClientsResource.init_storage()
        cls.ClientsResource = ClientsResource

    @classmethod
    def tearDownClass(cls):
        """Clean up test storage after all tests."""
        import campus.storage.testing
        # Only clear data, don't reset database (preserves connections)
        campus.storage.testing.clear_all_data()

    def setUp(self):
        """Clean storage before each test without destroying schema."""
        import campus.storage.testing
        campus.storage.testing.clear_all_data()

    def _create_confidential_client(self):
        """Create a confidential client row and return its id."""
        client = self.ClientsResource().new(
            name="revoke-getsecret-client",
            description="Confidential client for revoke regression tests",
        )
        return client.id

    def test_revoke_resolves_secret_key_via_getsecret_fallback(self):
        """revoke() must work when SECRET_KEY is vault-only.

        Regression test for #634: with the SECRET_KEY environment
        variable absent, revoke() must still rotate and return the new
        secret, and store a hash computed with the fallback key.
        """
        from campus.common import env
        from campus.common.utils import secret as secret_utils
        from campus.auth.resources.client import client_storage

        client_id = self._create_confidential_client()
        fallback_key = "integration-test-secret-key"
        previous_func = env._getsecret_func
        env.register_getsecret(lambda name: fallback_key)
        saved_value = os.environ.pop("SECRET_KEY", None)
        try:
            new_secret = self.ClientsResource()[client_id].revoke()
        finally:
            if saved_value is not None:
                os.environ["SECRET_KEY"] = saved_value
            env.register_getsecret(previous_func)

        self.assertIsInstance(new_secret, str)
        self.assertTrue(len(new_secret) > 0)
        record = client_storage.get_by_id(client_id)
        self.assertEqual(
            record["secret_hash"],
            secret_utils.hash_client_secret(new_secret, fallback_key)
        )

    def test_rotated_secret_authenticates_with_fallback_key(self):
        """A secret rotated via the fallback key validates credentials.

        Ties the revoke fix to is_valid_credentials(), which already
        resolves SECRET_KEY through getsecret: the rotated secret must
        authenticate, and a different secret must not.
        """
        from campus.common import env

        client_id = self._create_confidential_client()
        fallback_key = "integration-test-secret-key"
        previous_func = env._getsecret_func
        env.register_getsecret(lambda name: fallback_key)
        saved_value = os.environ.pop("SECRET_KEY", None)
        try:
            new_secret = self.ClientsResource()[client_id].revoke()
            rotated_valid = self.ClientsResource().is_valid_credentials(
                client_id, new_secret
            )
            wrong_valid = self.ClientsResource().is_valid_credentials(
                client_id, "not-the-rotated-secret"
            )
        finally:
            if saved_value is not None:
                os.environ["SECRET_KEY"] = saved_value
            env.register_getsecret(previous_func)

        self.assertTrue(rotated_valid)
        self.assertFalse(wrong_valid)
