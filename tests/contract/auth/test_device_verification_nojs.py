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
- A refused code lands the user back on the pre-filled page with its
  reason: ``expired`` for a code past its validity limit, even when
  nothing had marked it yet (#1268).
- A malformed code lands on the bare page with ``invalid_code``.
- Nothing in the request chooses the redirect target: it stays on the
  verification page.
- The page a refusal lands on shows one thing (#1279): the error view
  with the real message when there is nothing left to submit, or the
  form with a single alert when the code can be corrected.
"""

import re
import unittest
from urllib.parse import parse_qs, urlsplit

from tests.fixtures import services

DEVICE_PAGE = "/auth/v1/oauth/device"
USER_ID = "contract.test@campus.test"
INVALID_MESSAGE = "The user code you entered is invalid. Please check and try again."
EXPIRED_MESSAGE = (
    "This user code has expired. Please restart the authentication "
    "process on your CLI application to get a new code."
)
USED_MESSAGE = (
    "This user code has already been used. Please restart the "
    "authentication process on your CLI application to get a new code."
)
UNKNOWN_MESSAGE = "An unexpected error occurred. Please try again."


def target_of(location: str) -> tuple[str, dict[str, list[str]]]:
    """Split a redirect Location into its path and query."""
    parts = urlsplit(location)
    return parts.path, parse_qs(parts.query)


def landing(page: str) -> dict:
    """What a landed page shows without its script."""
    def shown(el: str, cls: str) -> bool:
        found = re.search(r'id="%s" class="%s ?(hidden)?"' % (el, cls), page)
        return bool(found and not found.group(1))

    def text(marker: str, end: str) -> str | None:
        found = re.search(r'id="%s">(.*?)%s' % (marker, end), page, re.S)
        return found.group(1) if found else None

    prefilled = re.search(r'id="userCode"[^>]*value="([^"]*)"', page)
    return {
        "success_view": shown("successView", "state-view"),
        "error_view": shown("errorView", "state-view"),
        "form": shown("formView", "form-container"),
        "title": text("errorTitle", "</h2>"),
        "message": text("errorMessage", "</p>"),
        # The form's alert for the outcome; the page's own notice for
        # the code has an id and so is not matched
        "alerts": [
            " ".join(a.split())
            for a in re.findall(r'<div class="alert error show"[^>]*>(.*?)</div>', page, re.S)
        ],
        "prefilled": prefilled.group(1) if prefilled else None,
        "try_again_left_to_script": bool(
            re.search(r'<button[^>]*id="tryAgainBtn"[^>]*\shidden>', page)
        ),
    }


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

    def _assert_lands_on(self, location: str, code: str | None, **query: str):
        expected = {name: [value] for name, value in query.items()}
        if code:
            expected = {"user_code": [code], **expected}
        self.assertEqual(target_of(location), (DEVICE_PAGE, expected))

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

                self._assert_lands_on(location, code, status="success")
                state = landing(page)
                self.assertTrue(state["success_view"])
                self.assertFalse(state["form"])
                self.assertEqual(state["prefilled"], code)
                # And the CLI waiting on that code can now collect its tokens
                token = self._token_request(created)
                self.assertEqual(token.status_code, 200)
                self.assertIn("access_token", token.get_json())

    def test_form_posted_to_the_path_form_route_behaves_the_same(self):
        """The path-form page also accepts the form's POST directly."""
        created = self._new_code()
        code = created["user_code"]

        location, page = self._submit_form(code, post_to=f"{DEVICE_PAGE}/{code}")

        self._assert_lands_on(location, code, status="success")
        self.assertTrue(landing(page)["success_view"])

    def test_code_matches_ignoring_case_and_surrounding_space(self):
        """A code typed in lowercase, or padded with spaces, still approves."""
        created = self._new_code()
        code = created["user_code"]

        location, page = self._submit_form(f"  {code.lower()} ")

        self.assertEqual(target_of(location)[1]["status"], ["success"])
        self.assertTrue(landing(page)["success_view"])

    def test_refused_code_lands_back_in_its_own_error_state(self):
        """Each refusal names its reason, and the landed page shows that alone.

        A terminal error leaves nothing to submit, so the page shows
        the error view with the real message and hides the form (#1279).
        An unknown code can be corrected, so the form stays, with one
        alert. A code that expired by the clock, and was never marked,
        is an expired code, not an invalid one (#1268).
        """
        from campus.auth.resources import device_code as device_code_resource
        from campus.common import schema

        def never_issued() -> str:
            return "ZZZZ-9999"

        def marked_expired() -> str:
            code = self._new_code()["user_code"]
            dc = device_code_resource.peek_by_user_code(code)
            assert dc is not None
            device_code_resource.update(dc.id, state="expired")
            return code

        def expired_by_clock() -> str:
            code = self._new_code()["user_code"]
            dc = device_code_resource.peek_by_user_code(code)
            assert dc is not None
            device_code_resource.update(
                dc.id,
                expires_at=str(schema.DateTime.utcafter(seconds=-60)),
            )
            return code

        def approved_a_moment_ago() -> str:
            code = self._new_code()["user_code"]
            self._submit_form(code)
            return code

        refusals = [
            # label, how to get the code, error_code, title, message, terminal
            ("never issued", never_issued, "invalid_code", None, INVALID_MESSAGE, False),
            ("marked expired", marked_expired, "expired", "Code Expired", EXPIRED_MESSAGE, True),
            ("expired by the clock", expired_by_clock, "expired", "Code Expired", EXPIRED_MESSAGE, True),
            ("already used", approved_a_moment_ago, "already_used", "Authorization Failed", USED_MESSAGE, True),
        ]
        for label, prepare, error_code, title, message, terminal in refusals:
            with self.subTest(refused=label):
                code = prepare()

                location, page = self._submit_form(code)

                self._assert_lands_on(
                    location, code, status="error", error_code=error_code
                )
                state = landing(page)
                self.assertEqual(state["prefilled"], code)
                self.assertTrue(state["try_again_left_to_script"])
                if terminal:
                    self.assertTrue(state["error_view"])
                    self.assertFalse(state["form"])
                    self.assertEqual(state["title"], title)
                    self.assertEqual(state["message"], message)
                else:
                    self.assertFalse(state["error_view"])
                    self.assertTrue(state["form"])
                    self.assertEqual(state["alerts"], [message])

    def test_malformed_code_lands_on_the_bare_page(self):
        """A malformed code names no page of its own, and is not echoed.

        It can be corrected, so the form stays, with a single alert.
        """
        for typed in ("", "ABCD-123", "ABCD-12345", "ABCD 1234", "ABCD_1234",
                      "ABCD-1234?status=success", "../../evil"):
            with self.subTest(typed=typed):
                location, page = self._submit_form(typed)

                self._assert_lands_on(
                    location, None, status="error", error_code="invalid_code"
                )
                state = landing(page)
                self.assertFalse(state["error_view"])
                self.assertTrue(state["form"])
                self.assertEqual(state["alerts"], [INVALID_MESSAGE])
                self.assertIsNone(state["prefilled"])

    def test_an_unrecognised_outcome_keeps_the_form(self):
        """An outcome the page does not know is treated as retryable."""
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = USER_ID
            page = client.get(
                f"{DEVICE_PAGE}?status=error&error_code=nonsense"
            ).get_data(as_text=True)

        state = landing(page)
        self.assertFalse(state["error_view"])
        self.assertTrue(state["form"])
        self.assertEqual(state["alerts"], [UNKNOWN_MESSAGE])

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
