"""Unit tests for how the device-code lookups report an expired code (#1268).

A device code expires by the clock: nothing flips its stored state
until something reads it. Both lookups mark a code ``expired`` when they
find it past its ``expires_at`` and refuse it with an error of its own,
so callers can tell an expired code from one that was never issued.
``get_by_user_code`` used to raise NotFoundError for both, so the
submit handlers told a user with an expired code that the code was
invalid.
"""

import unittest


class TestExpiredCodeLookups(unittest.TestCase):
    """An expired code is refused as expired; an unknown one is not found."""

    @classmethod
    def setUpClass(cls):
        # Lazy import: campus.auth pulls in storage modules at import
        # time. See AGENTS.md - Storage Initialization Order. The
        # resources package rebinds the name to the singleton instance.
        from campus.auth.resources import device_code as device_code_resource

        device_code_resource.init_storage()

    def setUp(self):
        from campus.auth.resources import device_code as device_code_resource
        from campus.common import schema
        from campus.common.errors import api_errors

        self.api_errors = api_errors
        self.resource = device_code_resource
        self.expired = device_code_resource.create(
            client_id="guest",
            scopes=["read"],
        )
        # The realistic case: still "pending" in storage, because nothing
        # has read the code since it passed its validity limit.
        device_code_resource.update(
            self.expired.id,
            expires_at=str(schema.DateTime.utcafter(seconds=-60)),
        )

    def test_user_code_lookup_refuses_an_expired_code_as_expired(self):
        with self.assertRaises(self.api_errors.InvalidRequestError):
            self.resource.get_by_user_code(self.expired.user_code)

    def test_user_code_lookup_marks_the_code_expired(self):
        with self.assertRaises(self.api_errors.InvalidRequestError):
            self.resource.get_by_user_code(self.expired.user_code)

        marked = self.resource.peek_by_user_code(self.expired.user_code)
        self.assertEqual(marked.state, "expired")

    def test_device_code_lookup_refuses_an_expired_code_the_same_way(self):
        with self.assertRaises(self.api_errors.InvalidRequestError):
            self.resource.get_by_device_code(self.expired.device_code)

    def test_an_unknown_code_is_not_found(self):
        with self.assertRaises(self.api_errors.NotFoundError):
            self.resource.get_by_user_code("ZZZZ-9999")

        with self.assertRaises(self.api_errors.NotFoundError):
            self.resource.get_by_device_code("no-such-device-code")

    def test_a_live_code_is_returned(self):
        live = self.resource.create(client_id="guest", scopes=["read"])

        self.assertEqual(self.resource.get_by_user_code(live.user_code).id, live.id)
        self.assertEqual(
            self.resource.get_by_device_code(live.device_code).id, live.id
        )


if __name__ == "__main__":
    unittest.main()
