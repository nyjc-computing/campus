"""HTTP contract tests for how an expired device code is reported (#1268).

A device code expires by the clock: nothing flips its stored state
until something reads it. So the realistic case is a code that is still
``pending`` in storage but past its ``expires_at``. Both submit paths
used to report such a code as ``invalid_code``, because the lookup
raised "not found" for it; the page's script then told the user to
check a code that was right.

Contract invariants, for a code that expired by the clock:
- The script-enabled submit path refuses it with ``expired`` (409), on
  every attempt.
- The no-JS form fallback sends the browser back with
  ``error_code=expired``, on every attempt.
- A code that was never issued is still ``invalid_code`` on both.
- The token endpoint's answer for the same code is unchanged.
"""

import unittest
from urllib.parse import parse_qs, urlsplit

from tests.fixtures import services

DEVICE_PAGE = "/auth/v1/oauth/device"
USER_ID = "contract.test@campus.test"


class TestExpiredDeviceCodeReportContract(unittest.TestCase):
    """HTTP contract tests for an expired code on the device page (#1268)."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()
        self.client = self.app.test_client()

    def _expired_by_clock(self) -> dict:
        """A device code that is past its validity limit, still "pending"."""
        from campus.auth.resources import device_code as device_code_resource
        from campus.common import schema

        created = self.client.post(
            "/auth/v1/oauth/device_authorize",
            data={"client_id": "guest"},
            content_type="application/x-www-form-urlencoded",
        ).get_json()
        dc = device_code_resource.peek_by_user_code(created["user_code"])
        assert dc is not None
        device_code_resource.update(
            dc.id,
            expires_at=str(schema.DateTime.utcafter(seconds=-60)),
        )
        return created

    def _signed_in(self):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = USER_ID
        return client

    def _submit_with_script(self, client, user_code: str):
        """What the page's script sends: POST /oauth/device/authorize."""
        return client.post(
            "/auth/v1/oauth/device/authorize",
            json={"user_code": user_code, "user_id": USER_ID},
        )

    def _submit_without_script(self, client, user_code: str):
        """What the form itself sends when the page has no script."""
        return client.post(
            DEVICE_PAGE,
            data={"user_code": user_code},
            content_type="application/x-www-form-urlencoded",
        )

    def _error_code_of_redirect(self, response) -> str | None:
        return parse_qs(urlsplit(response.headers["Location"]).query).get(
            "error_code"
        )[0]

    def test_script_path_reports_an_expired_code_as_expired(self):
        """A clock-expired code is refused as `expired`, every time."""
        created = self._expired_by_clock()
        client = self._signed_in()

        for attempt in (1, 2):
            with self.subTest(attempt=attempt):
                response = self._submit_with_script(client, created["user_code"])

                self.assertEqual(response.status_code, 409)
                error = response.get_json()["error"]
                self.assertEqual(error["code"], "expired")
                self.assertEqual(error["details"]["state"], "expired")
                self.assertIn("expired", error["message"])

    def test_no_script_path_reports_an_expired_code_as_expired(self):
        """The form fallback sends the browser back with error_code=expired."""
        created = self._expired_by_clock()
        client = self._signed_in()

        for attempt in (1, 2):
            with self.subTest(attempt=attempt):
                response = self._submit_without_script(
                    client, created["user_code"]
                )

                self.assertEqual(response.status_code, 302)
                self.assertEqual(
                    self._error_code_of_redirect(response), "expired"
                )

    def test_an_unknown_code_is_still_invalid_on_both_paths(self):
        """Telling the two apart must not blur an unknown code into an expired one."""
        client = self._signed_in()

        with_script = self._submit_with_script(client, "ZZZZ-9999")
        self.assertEqual(with_script.status_code, 404)
        self.assertEqual(with_script.get_json()["error"]["code"], "invalid_code")

        without_script = self._submit_without_script(client, "ZZZZ-9999")
        self.assertEqual(without_script.status_code, 302)
        self.assertEqual(self._error_code_of_redirect(without_script), "invalid_code")

    def test_token_endpoint_answer_is_unchanged(self):
        """The CLI still learns that the code expired from its own polling."""
        created = self._expired_by_clock()

        response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": created["device_code"],
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded",
        )

        self.assertEqual(response.status_code, 400)
        error = response.get_json()["error"]
        self.assertEqual(error["details"]["oauth_error"], "expired_token")


if __name__ == "__main__":
    unittest.main()
