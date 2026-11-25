"""The flask_test transport double (TestCampusRequest) against its own contract.

TestCampusRequest replaces campus_python's CampusRequest for every
cross-service call the integration and contract suites make, so a double
that drifts from the production client turns into failures that only happen
in the harness — and nothing else exercises the double:
tests/flask_test/test_basic.py is a smoke script outside every suite. These
tests pin its contract in the blocking unit suite; extend them whenever the
SDK's transport changes.

Gaps pinned so far:

- Context-local session credentials (campus-api-python#189, SDK v0.11.1): a
  with_app_session()/with_user_session() block no longer calls
  set_bearer_authorization() — it publishes its bearer, and the 401 refresh
  hook, on ContextVars that only CampusRequest._send() reads. The double
  kept sending the ambient credential (the fixture's ACCESS_TOKEN audit
  key), so every app-session read 401'd ("App credentials for token
  audit_v1_... not found") once campus#1288 relocked the SDK to v0.11.2.
  Integration Tests are non-blocking on weekly, so that merge was not
  stopped.
- put()/put_data()/delete()/patch() did not accept the `query` argument the
  JsonClient ABC declares, and post_data() passed it to the Flask test
  client as `query=` (its parameter is `query_string`) — a TypeError on
  every such call.
"""

import os
import unittest
from unittest import mock

import flask
from campus_python.json_client import _bearer_override, _session_hook

from tests.flask_test import TestCampusRequest, clear_test_apps, register_test_app

BASE_URL = "https://campus.test"


def echo_app() -> flask.Flask:
    """A Flask app that reports how a request arrived."""
    app = flask.Flask(__name__)

    @app.route('/echo', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
    def echo():
        return {
            'method': flask.request.method,
            'query': dict(flask.request.args),
            'content_type': flask.request.content_type,
            'json': flask.request.get_json(silent=True),
            'body': flask.request.get_data(as_text=True),
        }

    return app


def recording_app(seen: list[str | None], accept: str | None = None) -> flask.Flask:
    """A Flask app that records each /probe request's Authorization header.

    Args:
        seen: List the observed Authorization values are appended to
        accept: When set, reply 401 unless the header is `Bearer <accept>`;
            None accepts every request

    Returns:
        A Flask app handling GET /probe
    """
    app = flask.Flask(__name__)

    @app.route('/probe')
    def probe():
        authorization = flask.request.headers.get('Authorization')
        seen.append(authorization)
        if accept is not None and authorization != f'Bearer {accept}':
            return {'error': 'invalid_token'}, 401
        return {'ok': True}

    return app


class TransportTestCase(unittest.TestCase):
    """Isolated app registry, ambient credentials and session state."""

    # The fixture's ambient state: ACCESS_TOKEN holds the per-test audit
    # API key (tests/fixtures/services.py _ensure_audit_api_key).
    AMBIENT_TOKEN = "audit_v1_ambienttracingkey00000"
    client: TestCampusRequest

    def setUp(self):
        environ = mock.patch.dict(os.environ, {
            "ACCESS_TOKEN": self.AMBIENT_TOKEN,
        })
        environ.start()
        self.addCleanup(environ.stop)

        # Session state is process-wide ContextVars: pin it, restore after.
        bearer = _bearer_override.set(None)
        hook = _session_hook.set(None)
        self.addCleanup(_bearer_override.reset, bearer)
        self.addCleanup(_session_hook.reset, hook)

        self.serve(echo_app())
        self.client = TestCampusRequest(base_url=BASE_URL)

    def serve(self, app: flask.Flask) -> None:
        """Make `app` the only app registered behind BASE_URL."""
        clear_test_apps()
        register_test_app(BASE_URL, app, path_prefix="")
        self.addCleanup(clear_test_apps)


class TestVerbQuery(TransportTestCase):
    """Every verb carries its `query` argument through, as the ABC declares."""

    QUERY = {'filename': 'plan.txt'}

    def test_get_sends_its_query(self):
        response = self.client.get('/echo', query=self.QUERY)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['query'], self.QUERY)

    def test_json_verbs_send_query_and_body(self):
        """put()/delete()/patch() take `query` alongside the JSON body."""
        for verb in ('put', 'delete', 'patch'):
            with self.subTest(verb=verb):
                response = getattr(self.client, verb)(
                    '/echo', json={'key': 'value'}, query=self.QUERY,
                )

                self.assertEqual(response.json(), {
                    'method': verb.upper(),
                    'query': self.QUERY,
                    'content_type': 'application/json',
                    'json': {'key': 'value'},
                    'body': '{"key": "value"}',
                })

    def test_raw_body_verbs_send_query_content_type_and_body(self):
        """put_data()/post_data() keep the body verbatim with the query."""
        for verb in ('put_data', 'post_data'):
            with self.subTest(verb=verb):
                response = getattr(self.client, verb)(
                    '/echo', data='raw bytes',
                    content_type='text/plain', query=self.QUERY,
                )

                self.assertEqual(response.json(), {
                    'method': verb.removesuffix('_data').upper(),
                    'query': self.QUERY,
                    'content_type': 'text/plain',
                    'json': None,
                    'body': 'raw bytes',
                })

    def test_raw_body_verbs_without_query_or_content_type(self):
        """A bare put_data()/post_data() call goes through.

        post_data() used to raise TypeError even with nothing optional
        supplied: it always forwarded `query=`.
        """
        for verb in ('put_data', 'post_data'):
            with self.subTest(verb=verb):
                response = getattr(self.client, verb)('/echo', data=b'raw bytes')

                self.assertEqual(response.json(), {
                    'method': verb.removesuffix('_data').upper(),
                    'query': {},
                    'content_type': None,
                    'json': None,
                    'body': 'raw bytes',
                })


class TestSessionBearer(TransportTestCase):
    """The #189 bearer half: a session's credential is what goes out."""

    def setUp(self):
        super().setUp()
        self.seen: list[str | None] = []
        self.serve(recording_app(self.seen))

    def test_session_bearer_wins_over_the_ambient_audit_key(self):
        """Inside a session block the override is sent, not ACCESS_TOKEN.

        The campus#1288 regression: the SDK minted the app token and
        published it on _bearer_override, the double presented the
        fixture's audit key instead, and auth answered "App credentials
        for token audit_v1_... not found".
        """
        _bearer_override.set("app-token")

        response = self.client.get('/probe')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.seen, ["Bearer app-token"])

    def test_session_bearer_wins_over_explicit_client_authorization(self):
        """set_basic_authorization() on the client loses to the override."""
        self.client.set_basic_authorization("client-id", "client-secret")
        _bearer_override.set("app-token")

        self.client.get('/probe')

        self.assertEqual(self.seen, ["Bearer app-token"])

    def test_ambient_credential_is_sent_outside_a_session(self):
        """With no session active, credentials still load from the environment."""
        self.client.get('/probe')

        self.assertEqual(self.seen, [f"Bearer {self.AMBIENT_TOKEN}"])

    def test_session_bearer_does_not_stick_to_the_client(self):
        """After the block the client presents the ambient credential again.

        Leaking a session's bearer onto the shared client is the #189
        failure class; the double must not reintroduce it from its side.
        """
        token = _bearer_override.set("app-token")
        self.client.get('/probe')
        _bearer_override.reset(token)

        self.client.get('/probe')

        self.assertEqual(
            self.seen,
            ["Bearer app-token", f"Bearer {self.AMBIENT_TOKEN}"],
        )


class TestUnauthorizedHook(TransportTestCase):
    """The 401 half: one 401-triggered retry, as in CampusRequest._send()."""

    def reject_every_bearer(self) -> list[str | None]:
        """Serve /probe so that every request is recorded and answered 401."""
        seen: list[str | None] = []
        self.serve(recording_app(seen, accept="no-such-bearer"))
        return seen

    def test_401_in_a_session_retries_once_with_the_refreshed_bearer(self):
        """The session hook's bearer retries the request and replaces the override."""
        seen: list[str | None] = []
        self.serve(recording_app(seen, accept="refreshed"))
        _bearer_override.set("stale")

        def refresh_bearer() -> str:
            _bearer_override.set("refreshed")
            return "refreshed"

        _session_hook.set(refresh_bearer)

        response = self.client.get('/probe')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen, ["Bearer stale", "Bearer refreshed"])
        self.assertEqual(_bearer_override.get(), "refreshed")

    def test_401_without_a_hook_is_returned_as_sent(self):
        """No hook installed: the 401 is handed back, with no second request."""
        seen = self.reject_every_bearer()

        response = self.client.get('/probe')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(seen, [f"Bearer {self.AMBIENT_TOKEN}"])

    def test_hook_returning_none_leaves_the_original_401(self):
        """A refresh that fails surfaces the first response, unretried."""
        seen = self.reject_every_bearer()
        _session_hook.set(lambda: None)

        response = self.client.get('/probe')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(len(seen), 1)

    def test_a_second_401_is_not_retried_again(self):
        """The hook runs at most once per request."""
        seen = self.reject_every_bearer()
        _bearer_override.set("stale")

        def refresh_bearer() -> str:
            _bearer_override.set("still-rejected")
            return "still-rejected"

        _session_hook.set(refresh_bearer)

        response = self.client.get('/probe')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(seen, ["Bearer stale", "Bearer still-rejected"])

    def test_requests_made_inside_the_hook_do_not_reenter_it(self):
        """The hook's own round-trip through this client skips the hook.

        Shaped like the SDK's refresh_bearer(): the override is suspended
        for the re-acquisition, so the mint presents the client's ambient
        credential, never the session's stale bearer. Without the
        re-entrancy guard that round-trip would recurse.
        """
        seen: list[str | None] = []
        self.serve(recording_app(seen, accept="refreshed"))
        _bearer_override.set("stale")

        def refresh_bearer() -> str:
            suspended = _bearer_override.set(None)
            try:
                self.client.get('/probe')
            finally:
                _bearer_override.reset(suspended)
            _bearer_override.set("refreshed")
            return "refreshed"

        _session_hook.set(refresh_bearer)

        response = self.client.get('/probe')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            seen,
            ["Bearer stale", f"Bearer {self.AMBIENT_TOKEN}", "Bearer refreshed"],
        )

    def test_client_hook_refreshes_the_client_authorization(self):
        """set_unauthorized_hook() outside a session updates the client's own header.

        With no override active there is nothing per-request to update, so
        the refreshed bearer lands on the client, as in production.
        """
        seen: list[str | None] = []
        self.serve(recording_app(seen, accept="refreshed"))
        self.client.set_unauthorized_hook(lambda: "refreshed")

        response = self.client.get('/probe')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen, [f"Bearer {self.AMBIENT_TOKEN}", "Bearer refreshed"])
        self.assertEqual(self.client.authorization, "Bearer refreshed")


if __name__ == "__main__":
    unittest.main()
