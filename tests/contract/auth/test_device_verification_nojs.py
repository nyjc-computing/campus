"""HTTP contract tests for the no-JS form fallback of the device verification page (#1266).

With scripts disabled, the verification page's form posts to
``POST /auth/v1/oauth/device`` and the browser follows a redirect back
to the page. ``status=success`` or ``status=error&error_code=`` in the
query string then drives the page's fallback states, so that redirect
is what tells the user how their request went.

Contract invariants:
- An approval lands the user on the code's pre-filled page in the
  success state, whichever URL form the page was opened on, and the
  CLI's token request then succeeds.
- A refused code lands the user back on the pre-filled page in the
  matching error state.
- A malformed code lands on the bare page with ``invalid_code``.
- Nothing in the request chooses the redirect target: it stays on the
  verification page.
"""

import re
import unittest
from urllib.parse import parse_qs, urlsplit

from tests.fixtures import services

DEVICE_PAGE = "/auth/v1/oauth/device"
USER_ID = "contract.test@campus.test"
EXPIRED_MESSAGE = "This user code has expired."
USED_MESSAGE = "This user code has already been used."
INVALID_MESSAGE = "The user code you entered is invalid."


def shown_state_view(page: str) -> str | None:
    """Which fallback state view the page renders without its script."""
    found = re.search(r'id="(successView|errorView)" class="state-view "', page)
    return found.group(1) if found else None


def target_of(location: str) -> tuple[str, dict[str, list[str]]]:
    """Split a redirect Location into its path and query."""
    parts = urlsplit(location)
    return parts.path, parse_qs(parts.query)


class TestDeviceVerificationNoJsFallbackContract(unittest.TestCase):
    """HTTP contract tests for the form fallback on the device page (#1266)."""

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

    def _new_code(self) -> dict:
        """Mint a pending device code through the public endpoint."""
        response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            data={"client_id": "guest"},
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def _submit_form(self, typed: str, post_to: str = DEVICE_PAGE, **fields: str):
        """Submit the verification form as a signed-in browser without scripts.

        Returns the redirect's Location and the page the browser lands
        on when it follows it.
        """
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = USER_ID
            response = client.post(
                post_to,
                data={"user_code": typed, **fields},
                content_type="application/x-www-form-urlencoded",
            )
            self.assertEqual(response.status_code, 302)
            location = response.headers["Location"]
            landed = client.get(location)
        self.assertEqual(landed.status_code, 200)
        return location, landed.get_data(as_text=True)

    def _token_request(self, created: dict):
        """The CLI's polling request for an approved device code."""
        return self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": created["device_code"],
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded",
        )

    def test_approval_lands_on_the_prefilled_page_and_the_cli_gets_tokens(self):
        """An approved request ends on the code's page in the success state.

        The usual pre-filled link is ``/device?user_code=XXXX-XXXX``.
        The redirect used to append a second ``?`` to it, which dropped
        both the outcome and the code, so a user without scripts got no
        confirmation at all. Pages cached from before the fix still post
        the redirect target the form used to carry; it must not matter.
        """
        posted_from = {
            "query-form page": {
                "redirect_url": f"https://campus.test{DEVICE_PAGE}?user_code=CODE",
            },
            "path-form page": {
                "redirect_url": f"https://campus.test{DEVICE_PAGE}/CODE",
            },
            "bare page, code typed": {},
        }
        for label, fields in posted_from.items():
            with self.subTest(posted_from=label):
                created = self._new_code()
                code = created["user_code"]
                fields = {k: v.replace("CODE", code) for k, v in fields.items()}

                location, page = self._submit_form(code, **fields)

                self.assertEqual(
                    target_of(location),
                    (DEVICE_PAGE, {"user_code": [code], "status": ["success"]}),
                )
                self.assertEqual(shown_state_view(page), "successView")
                self.assertIn(f'value="{code}"', page)
                # And the CLI waiting on that code can now collect its tokens
                token = self._token_request(created)
                self.assertEqual(token.status_code, 200)
                self.assertIn("access_token", token.get_json())

    def test_form_posted_to_the_path_form_route_behaves_the_same(self):
        """The path-form page also accepts the form's POST directly."""
        created = self._new_code()
        code = created["user_code"]

        location, page = self._submit_form(code, post_to=f"{DEVICE_PAGE}/{code}")

        self.assertEqual(
            target_of(location),
            (DEVICE_PAGE, {"user_code": [code], "status": ["success"]}),
        )
        self.assertEqual(shown_state_view(page), "successView")

    def test_code_matches_ignoring_case_and_surrounding_space(self):
        """A code typed in lowercase, or padded with spaces, still approves."""
        created = self._new_code()
        code = created["user_code"]

        location, page = self._submit_form(f"  {code.lower()} ")

        self.assertEqual(target_of(location)[1]["status"], ["success"])
        self.assertEqual(shown_state_view(page), "successView")

    def test_refused_code_lands_back_in_the_matching_error_state(self):
        """Each refusal names its reason on the code's pre-filled page."""
        from campus.auth.resources import device_code as device_code_resource

        def never_issued() -> str:
            return "ZZZZ-9999"

        def marked_expired() -> str:
            code = self._new_code()["user_code"]
            dc = device_code_resource.peek_by_user_code(code)
            assert dc is not None
            device_code_resource.update(dc.id, state="expired")
            return code

        def approved_a_moment_ago() -> str:
            code = self._new_code()["user_code"]
            self._submit_form(code)
            return code

        refusals = {
            "invalid_code": (never_issued, INVALID_MESSAGE),
            "expired": (marked_expired, EXPIRED_MESSAGE),
            "already_used": (approved_a_moment_ago, USED_MESSAGE),
        }
        for error_code, (prepare, message) in refusals.items():
            with self.subTest(error_code=error_code):
                code = prepare()

                location, page = self._submit_form(code)

                self.assertEqual(
                    target_of(location),
                    (
                        DEVICE_PAGE,
                        {
                            "user_code": [code],
                            "status": ["error"],
                            "error_code": [error_code],
                        },
                    ),
                )
                self.assertEqual(shown_state_view(page), "errorView")
                self.assertIn(message, page)
                self.assertIn(f'value="{code}"', page)

    def test_malformed_code_lands_on_the_bare_page(self):
        """A malformed code names no page of its own, and is not echoed."""
        for typed in ("", "ABCD-123", "ABCD-12345", "ABCD 1234", "ABCD_1234",
                      "ABCD-1234?status=success", "../../evil"):
            with self.subTest(typed=typed):
                location, page = self._submit_form(typed)

                self.assertEqual(
                    target_of(location),
                    (DEVICE_PAGE, {"status": ["error"], "error_code": ["invalid_code"]}),
                )
                self.assertEqual(shown_state_view(page), "errorView")
                self.assertIn(INVALID_MESSAGE, page)

    def test_nothing_in_the_request_chooses_the_redirect_target(self):
        """The redirect stays on the verification page whatever is posted.

        The page's form no longer sends a target, but a request can.
        One that was honoured would send a signed-in user wherever it
        says.
        """
        targets = (
            "https://evil.example/login",
            "//evil.example/login",
            "/\\evil.example/login",
            "https://campus.test/auth/v1/somewhere-else",
        )
        for target in targets:
            outcomes = {
                "approval": (self._new_code()["user_code"], "success"),
                "refusal": ("ZZZZ-9999", "error"),
                "malformed": ("not-a-code", "error"),
            }
            for outcome, (typed, status) in outcomes.items():
                with self.subTest(target=target, outcome=outcome):
                    location, _ = self._submit_form(typed, redirect_url=target)

                    path, query = target_of(location)
                    self.assertEqual(path, DEVICE_PAGE)
                    self.assertEqual(query["status"], [status])
                    for foreign in ("evil", "somewhere-else", "campus.test"):
                        self.assertNotIn(foreign, location)


if __name__ == "__main__":
    unittest.main()
