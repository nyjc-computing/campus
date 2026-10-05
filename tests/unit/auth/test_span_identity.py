"""Unit tests for the auth provider's span-identity stash (#820).

Browser hops don't run the Authenticator, so the provider stashes
client/user for the tracing middleware's span enrichment the same way
it stashes the journey id (#803).
"""

import unittest

import flask

from campus.auth import provider


class TestStashSpanIdentity(unittest.TestCase):
    """_stash_span_identity() writes g.client_id/g.user_id."""

    def setUp(self):
        self.app = flask.Flask(__name__)

    def test_stashes_both_ids(self):
        with self.app.test_request_context("/"):
            provider._stash_span_identity(
                client_id="uid-client-abc", user_id="user@nyjc.edu.sg"
            )

            self.assertEqual(flask.g.client_id, "uid-client-abc")
            self.assertEqual(flask.g.user_id, "user@nyjc.edu.sg")

    def test_falsy_values_are_not_stashed(self):
        with self.app.test_request_context("/"):
            provider._stash_span_identity(client_id=None, user_id=None)

            self.assertFalse(hasattr(flask.g, "client_id"))
            self.assertFalse(hasattr(flask.g, "user_id"))

    def test_ids_are_stringified(self):
        with self.app.test_request_context("/"):
            provider._stash_span_identity(
                client_id=provider.schema.CampusID("uid-client-abc"),
            )

            self.assertEqual(flask.g.client_id, "uid-client-abc")
            self.assertIsInstance(flask.g.client_id, str)

    def test_device_id_stashed_as_g_device(self):
        """device_id (#825) rides the same stash, under g.device."""
        with self.app.test_request_context("/"):
            provider._stash_span_identity(device_id="uid-device-abc")

            self.assertEqual(flask.g.device, "uid-device-abc")

    def test_missing_device_id_not_stashed(self):
        with self.app.test_request_context("/"):
            provider._stash_span_identity(device_id=None)

            self.assertFalse(hasattr(flask.g, "device"))


if __name__ == "__main__":
    unittest.main()
