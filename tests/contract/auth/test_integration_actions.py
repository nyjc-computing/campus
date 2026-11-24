"""HTTP contract tests for the integration action proxies (#1221).

These verify the /auth/v1/integrations/... proxy surface end-to-end
against the real auth app with the network faked at two seams:

- Google token refresh: patched at the webauth OAuth2 scheme (the
  broker contract tests' idiom); most tests seed a live token so no
  refresh fires.
- Classroom REST: `requests.request` inside the classroom caller
  module is a Mock returning scripted responses, recording every
  upstream call (paths, headers, payloads).

Covered:

- Authority gate (#1221): a user principal needs BOTH the
  `integrations.google.classroom:admin` token scope (#865 leg) AND
  vault access to the google.classroom label (#883/#889 leg); the
  operator client bypasses; other client principals are denied
  (#881 user-attributability).
- Consent-bounded (invariant C3b): a stored grant without the
  required scope answers 403 with `missing_scopes` and NO upstream
  call; no credential answers 404 with the connect hint.
- turn-in: resolves the target's studentSubmission (userId=me),
  no-ops when already TURNED_IN, runs on a live access token, and
  emits `campus.integrations.action` naming actor + target — never
  token values.
- reclaim: Google's FAILED_PRECONDITION (nothing to reclaim) counts
  as success.
- Read verb returns the submission resource; unknown actions 404;
  unauthenticated calls 401.
"""

import unittest
from unittest import mock

import campus.model
from campus.common import env, schema
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers

COURSEWORK_ME = "https://www.googleapis.com/auth/classroom.coursework.me"
INTEGRATIONS_SCOPE = "integrations.google.classroom:admin"
GOOGLE_CLIENT_ID = "test-google-client-id"
ACTOR = schema.UserID("proxy-admin@nyjc.edu.sg")
TARGET = schema.UserID("student@nyjc.edu.sg")
COURSE_ID = "course-1"
COURSEWORK_ID = "cw-1"
SUBMISSION_ID = "sub-1"
BASE_URL = (
    "/auth/v1/integrations/google/classroom/users"
    f"/{TARGET}"
)


def _resp(status_code: int = 200, body: dict | None = None) -> mock.Mock:
    """A fake requests.Response carrying a JSON body."""
    response = mock.Mock()
    response.status_code = status_code
    response.reason = "OK"
    response.content = b"{}" if body is not None else b""
    response.json.return_value = body or {}
    return response


class TestIntegrationActionsContract(unittest.TestCase):
    """HTTP contract tests for the #1221 action proxy surface."""

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
        assert self.app
        self.client = self.app.test_client()
        self.operator_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET)

        from campus.auth import resources as auth_resources
        from campus.auth.resources.grant import grants

        # The integration's vault label: the proxy's config source and
        # the custody authority the gate demands.
        auth_resources.vault["google.classroom"]["CLIENT_ID"] = (
            GOOGLE_CLIENT_ID)
        auth_resources.vault["google.classroom"]["CLIENT_SECRET"] = (
            "test-google-client-secret")
        auth_resources.vault["google.classroom"]["SCOPES"] = COURSEWORK_ME

        # Custody leg: the ACTOR holds vault access to the label.
        grants.grant(
            "user", ACTOR, "vault", "google.classroom", level="read",
        )

        # The acted-on credential: the TARGET user's stored Classroom
        # grant (post-#1095: carries coursework.me).
        auth_resources.credentials["google.classroom"][TARGET].update(
            client_id=GOOGLE_CLIENT_ID,
            token=campus.model.OAuthToken(
                id="google-access-token-1",
                expires_in=3600,
                scopes=[COURSEWORK_ME, "email", "profile"],
            ),
        )

        # The ACTOR's campus bearer, carrying the #1221 management
        # scope plus the vault vocabulary scope (both gate legs).
        self.client_id, _ = self._new_client("proxy-contract-client")
        auth_resources.credentials["campus"][ACTOR].update(
            client_id=self.client_id,
            token=campus.model.OAuthToken(
                id="proxy-admin-bearer",
                expires_in=3600,
                scopes=[
                    "read",
                    INTEGRATIONS_SCOPE,
                    "vaults:read",
                ],
            ),
        )
        self.bearer_headers = {"Authorization": "Bearer proxy-admin-bearer"}

    def _new_client(self, name: str, **client_kwargs) -> tuple[str, str | None]:
        """Create a confidential client as the operator; return (id, secret)."""
        payload = {
            "name": name,
            "description": name,
            **client_kwargs,
        }
        response = self.client.post(
            "/auth/v1/clients/", json=payload, headers=self.operator_headers,
        )
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        return body["id"], body.get("client_secret")

    def _google_mock(self, *responses):
        """Patch the classroom caller's transport with scripted replies.

        Returns (mock, restore) — the mock records every
        requests.request call (method, args, kwargs).
        """
        transport = mock.Mock()
        transport.request.side_effect = list(responses)
        patcher = mock.patch(
            "campus.auth.integration_actions.classroom.requests", transport,
        )
        return transport, patcher

    # --- authority gate -------------------------------------------------

    def test_turn_in_success(self):
        transport, patcher = self._google_mock(
            _resp(200, {"studentSubmissions": [
                {"id": SUBMISSION_ID, "state": "NEW"}]}),
            _resp(200, {"id": SUBMISSION_ID, "state": "NEW"}),
            _resp(200, {"id": SUBMISSION_ID, "state": "TURNED_IN"}),
        )
        with patcher, mock.patch(
                "campus.auth.integration_actions.routes.get_yapper"
        ) as yapper_factory:
            response = self.client.post(
                f"{BASE_URL}/turn-in",
                json={"course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
                headers=self.bearer_headers,
            )
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertTrue(body["turned_in"])
        self.assertFalse(body["already"])
        self.assertEqual(body["submission_id"], SUBMISSION_ID)

        # Upstream calls: list (userId=me) -> get -> :turnIn, all on the
        # TARGET's released access token.
        calls = transport.request.call_args_list
        self.assertEqual(len(calls), 3)
        turn_in_call = calls[2]
        self.assertIn(
            f"/courses/{COURSE_ID}/courseWork/{COURSEWORK_ID}"
            f"/studentSubmissions/{SUBMISSION_ID}:turnIn",
            str(turn_in_call),
        )
        headers = turn_in_call.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer google-access-token-1")

        # Audit names actor + target + action; the body never carries
        # the upstream token.
        emit_calls = yapper_factory.return_value.emit.call_args_list
        events = [call.args[0] for call in emit_calls]
        self.assertIn("campus.integrations.action", events)
        payload = emit_calls[events.index(
            "campus.integrations.action")].args[1]
        self.assertEqual(payload["actor_type"], "user")
        self.assertEqual(payload["actor_id"], str(ACTOR))
        self.assertEqual(payload["user_id"], str(TARGET))
        self.assertEqual(payload["action"], "turn-in")
        self.assertNotIn("google-access-token-1", str(response.get_data()))

    def test_turn_in_already_turned_in_no_op(self):
        transport, patcher = self._google_mock(
            _resp(200, {"studentSubmissions": [
                {"id": SUBMISSION_ID, "state": "TURNED_IN"}]}),
            _resp(200, {"id": SUBMISSION_ID, "state": "TURNED_IN"}),
        )
        with patcher:
            response = self.client.post(
                f"{BASE_URL}/turn-in",
                json={"course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
                headers=self.bearer_headers,
            )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["already"])
        self.assertFalse(body["turned_in"])
        # No :turnIn call ever fired.
        for call in transport.request.call_args_list:
            self.assertNotIn(":turnIn", str(call))

    def test_reclaim_failed_precondition_is_success(self):
        # Reclaim flows list -> :reclaim (two upstream calls).
        transport, patcher = self._google_mock(
            _resp(200, {"studentSubmissions": [
                {"id": SUBMISSION_ID, "state": "TURNED_IN"}]}),
            _resp(400, {"error": {
                "message": "Nothing to reclaim",
                "status": "FAILED_PRECONDITION"}}),
        )
        with patcher:
            response = self.client.post(
                f"{BASE_URL}/reclaim",
                json={"course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
                headers=self.bearer_headers,
            )
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertTrue(body["already"])
        self.assertFalse(body["reclaimed"])

    def test_reclaim_success(self):
        # Reclaim flows list -> :reclaim (two upstream calls).
        transport, patcher = self._google_mock(
            _resp(200, {"studentSubmissions": [
                {"id": SUBMISSION_ID, "state": "TURNED_IN"}]}),
            _resp(200, {"id": SUBMISSION_ID, "state": "RECLAIMED_BY_STUDENT"}),
        )
        with patcher:
            response = self.client.post(
                f"{BASE_URL}/reclaim",
                json={"course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
                headers=self.bearer_headers,
            )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(response.get_json()["reclaimed"])

    def test_modify_attachments_success(self):
        transport, patcher = self._google_mock(
            _resp(200, {"id": SUBMISSION_ID, "state": "NEW"}),
        )
        with patcher:
            response = self.client.post(
                f"{BASE_URL}/modify-attachments",
                json={
                    "course_id": COURSE_ID,
                    "coursework_id": COURSEWORK_ID,
                    "submission_id": SUBMISSION_ID,
                    "attachments": [
                        {"link": {"url": "https://example.test/review"}},
                    ],
                },
                headers=self.bearer_headers,
            )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["attached"], 1)
        call = transport.request.call_args_list[0]
        self.assertIn(":modifyAttachments", str(call))
        self.assertEqual(
            call.kwargs["json"],
            {"addAttachments": [
                {"link": {"url": "https://example.test/review"}}]},
        )

    def test_modify_attachments_rejects_bad_shape(self):
        response = self.client.post(
            f"{BASE_URL}/modify-attachments",
            json={
                "course_id": COURSE_ID,
                "coursework_id": COURSEWORK_ID,
                "submission_id": SUBMISSION_ID,
                "attachments": [{"nope": True}],
            },
            headers=self.bearer_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_get_submission_returns_resource(self):
        transport, patcher = self._google_mock(
            _resp(200, {"studentSubmissions": [
                {"id": SUBMISSION_ID, "state": "NEW"}]}),
            _resp(200, {"id": SUBMISSION_ID, "state": "NEW",
                        "alternateLink": "https://classroom.google.test/x"}),
        )
        with patcher:
            response = self.client.get(
                f"{BASE_URL}/submission",
                query_string={
                    "course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
                headers=self.bearer_headers,
            )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["id"], SUBMISSION_ID)
        self.assertNotIn("google-access-token-1", str(response.get_data()))

    # --- consent-bounded + custody errors ---------------------------------

    def test_missing_scope_403_no_upstream_call(self):
        from campus.auth import resources as auth_resources

        auth_resources.credentials["google.classroom"][TARGET].update(
            client_id=GOOGLE_CLIENT_ID,
            token=campus.model.OAuthToken(
                id="google-narrow-token",
                expires_in=3600,
                scopes=["email", "profile"],  # pre-#1095 grant
            ),
        )
        transport, patcher = self._google_mock()
        with patcher, mock.patch(
                "campus.auth.integration_actions.routes.get_yapper"
        ) as yapper_factory:
            response = self.client.post(
                f"{BASE_URL}/turn-in",
                json={"course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
                headers=self.bearer_headers,
            )
        self.assertEqual(response.status_code, 403, response.get_json())
        error = response.get_json()["error"]
        self.assertEqual(
            error["details"]["missing_scopes"], [COURSEWORK_ME])
        # Consent-bounded: no upstream call, and the failure audited.
        transport.request.assert_not_called()
        emit_calls = yapper_factory.return_value.emit.call_args_list
        events = [call.args[0] for call in emit_calls]
        self.assertIn("campus.integrations.action_fail", events)
        self.assertNotIn("campus.integrations.action", events)

    def test_no_credential_404_connect_hint(self):
        # A target with no google.classroom credential at all.
        stranger = schema.UserID("no-credential@nyjc.edu.sg")
        url = (
            "/auth/v1/integrations/google/classroom/users"
            f"/{stranger}/turn-in"
        )
        transport, patcher = self._google_mock()
        with patcher:
            response = self.client.post(
                url,
                json={"course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
                headers=self.bearer_headers,
            )
        self.assertEqual(response.status_code, 404, response.get_json())
        self.assertIn("connect flow", response.get_json()["error"]["message"])
        transport.request.assert_not_called()

    # --- gate legs --------------------------------------------------------

    def test_gate_denies_without_management_scope(self):
        from campus.auth import resources as auth_resources

        # Capability leg removed: bearer lacks the #1221 scope.
        auth_resources.credentials["campus"][ACTOR].update(
            client_id=self.client_id,
            token=campus.model.OAuthToken(
                id="proxy-admin-bearer",
                expires_in=3600,
                scopes=["read", "vaults:read"],
            ),
        )
        transport, patcher = self._google_mock()
        with patcher:
            response = self.client.post(
                f"{BASE_URL}/turn-in",
                json={"course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
                headers=self.bearer_headers,
            )
        self.assertEqual(response.status_code, 403, response.get_json())
        self.assertIn(
            "integrations.google.classroom:admin",
            response.get_json()["error"]["message"],
        )
        transport.request.assert_not_called()

    def test_gate_denies_without_vault_access(self):
        from campus.auth import resources as auth_resources

        # Custody leg removed: the bearer keeps the management scope
        # but the actor holds no vault grant row and no vaults scope.
        auth_resources.credentials["campus"][ACTOR].update(
            client_id=self.client_id,
            token=campus.model.OAuthToken(
                id="proxy-admin-bearer",
                expires_in=3600,
                scopes=["read", INTEGRATIONS_SCOPE],
            ),
        )
        response = self.client.post(
            f"{BASE_URL}/turn-in",
            json={"course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
            headers=self.bearer_headers,
        )
        self.assertEqual(response.status_code, 403, response.get_json())
        message = response.get_json()["error"]["message"]
        self.assertTrue(
            "#883" in message or "#889" in message or "vault" in message,
            message,
        )

    def test_operator_client_bypasses_the_gate(self):
        transport, patcher = self._google_mock(
            _resp(200, {"studentSubmissions": [
                {"id": SUBMISSION_ID, "state": "NEW"}]}),
            _resp(200, {"id": SUBMISSION_ID, "state": "NEW"}),
            _resp(200, {"id": SUBMISSION_ID, "state": "TURNED_IN"}),
        )
        with patcher:
            response = self.client.post(
                f"{BASE_URL}/turn-in",
                json={"course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
                headers=self.operator_headers,
            )
        self.assertEqual(response.status_code, 200, response.get_json())

    def test_non_operator_client_denied(self):
        # Seed a non-operator confidential client with a known secret
        # (hashed with the deployment's SECRET_KEY, like the resource
        # layer does on secret rotation).
        from campus.auth import resources as auth_resources
        from campus.common.utils import secret as secret_utils

        plain_secret = "plain-client-secret-value"
        record = auth_resources.client.new(
            name="plain-proxy-client",
            description="non-operator client for the #1221 denial test",
            is_public=False,
            secret_hash=secret_utils.hash_client_secret(
                plain_secret, key=env.getsecret("SECRET_KEY")),
        )
        response = self.client.post(
            f"{BASE_URL}/turn-in",
            json={"course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
            headers=get_basic_auth_headers(
                str(record.id), plain_secret),
        )
        self.assertEqual(response.status_code, 403, response.get_json())
        self.assertIn("#1221", response.get_json()["error"]["message"])

    def test_unauthenticated_401(self):
        response = self.client.post(
            f"{BASE_URL}/turn-in",
            json={"course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
        )
        self.assertEqual(response.status_code, 401)

    def test_unknown_action_404(self):
        response = self.client.post(
            f"{BASE_URL}/grade",
            json={"course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
            headers=self.bearer_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_unknown_integration_404(self):
        response = self.client.post(
            "/auth/v1/integrations/google/calendar/users"
            f"/{TARGET}/turn-in",
            json={"course_id": COURSE_ID, "coursework_id": COURSEWORK_ID},
            headers=self.bearer_headers,
        )
        self.assertEqual(response.status_code, 404)
