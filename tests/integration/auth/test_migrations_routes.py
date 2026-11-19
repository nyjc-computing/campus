"""Integration tests: the migrations gate matrix on campus.auth (#1169).

The campus.auth wiring gates /admin/migrations with the full two-leg
store check — authz.require_resource_permission("migrations", level,
instance="auth") (#1168 vocabulary, #1104 instance scoping). These
tests drive that gate over the REAL access-grant store (tmpfile
SQLite) and through the blueprint's HTTP layer with synthetic
principals (the test_authz_grants.py style): a before_request hook
sets flask.g from test headers, so the matrix exercises gate + route
together without the full token machinery.

Matrix (from the issue): read-only user, write user, admin user,
operator, unauthenticated — plus the #1168 instance scoping (a grant
for ANOTHER service must not open this service's surface) and the
#854/#865 two-leg rule (row and scope are both required).

IMPORTANT: Lazy imports are required to avoid storage initialization
before test mode is configured (see AGENTS.md - Storage Initialization
Order).
"""

import json
import os
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import flask

from tests.integration.base import IsolatedIntegrationTestCase

OPERATOR_ID = "cl_operator"
OPERATOR_ENV = {"AUTH_OPERATOR_CLIENT_IDS": OPERATOR_ID}

# The gate exactly as campus/auth/__init__.py wires it (the same
# closure, spelled out here so the matrix runs without the full auth
# app's token machinery).
SERVICE_INSTANCE = "auth"


def wired_gate(level: str) -> None:
    """The campus.auth migrations gate as wired in init_app (#1169)."""
    from campus.auth import authz

    authz.require_resource_permission(
        "migrations", level, instance=SERVICE_INSTANCE
    )


def _patch_runner_and_ledger():
    """Fake everything behind the gate: ledger reads and the runner.

    Authorized-path requests would otherwise touch Postgres and run
    real migrations; the gate matrix only needs the HTTP layer to get
    past (or not past) the gate.
    """
    import tempfile
    from pathlib import Path

    from migrations import routes as migration_routes

    migrations_dir = Path(tempfile.mkdtemp(prefix="mig-gate-"))
    (migrations_dir / "012_x.py").write_text(
        '"""Fake migration for the gate matrix."""\n'
        'TARGET_DB = "auth"\n',
        encoding="utf-8",
    )
    file = mock.Mock(revision="012", filename="012_x.py",
                     target_db="auth")
    patchers = [
        mock.patch.object(
            migration_routes, "_fetch_history_rows", return_value=[]
        ),
        mock.patch(
            "migrations.runner.discover_migration_files",
            return_value=[file],
        ),
        mock.patch(
            "migrations.runner.filter_files_by_db",
            lambda files, db: list(files),
        ),
        mock.patch(
            "migrations.runner.resolve_scoped_revision",
            lambda arg, files, db: file,
        ),
        mock.patch("migrations.runner.MIGRATIONS_DIR", migrations_dir),
        mock.patch("migrations.runner.main", lambda *a, **k: 0),
    ]
    for patcher in patchers:
        patcher.start()
    return patchers


class MigrationsRouteGateMatrix(unittest.TestCase):
    """(principal x grant row x scope) over the wired gate + routes."""

    @classmethod
    def setUpClass(cls):
        """Configure test storage and init the grant store schema."""
        import campus.storage.testing

        campus.storage.testing.configure_test_storage()
        campus.storage.testing.configure_test_db()

        from campus.auth.resources.grant import GrantsResource
        GrantsResource.init_storage()

        from campus.auth.resources.client import ClientsResource
        ClientsResource.init_storage()

        cls.app = flask.Flask(__name__)

        import campus.common.errors
        campus.common.errors.init_app(cls.app)

        import migrations.routes as migration_routes

        cls.app.register_blueprint(migration_routes.create_blueprint(
            service_db="auth", gate=wired_gate,
        ))

        @cls.app.before_request
        def _fake_authentication():  # pragma: no cover - test hook
            header = flask.request.headers.get("X-Test-Principal")
            if header:
                principal = json.loads(header)
                # Client principals carry attribute identity (the authz
                # helpers read client.id), so dicts become namespaces.
                client = principal.get("client")
                flask.g.current_client = (
                    SimpleNamespace(**client) if client else None
                )
                flask.g.current_user = principal.get("user")

        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        """Clean test storage after all tests."""
        import campus.storage.testing
        campus.storage.testing.clear_all_data()

    def setUp(self):
        """Clean storage before each test without destroying schema."""
        import campus.storage.testing
        campus.storage.testing.clear_all_data()
        self._patchers = _patch_runner_and_ledger()

    def tearDown(self):
        from migrations.routes import _RUN_STATE

        deadline = time.monotonic() + 5
        while _RUN_STATE.is_running("auth"):
            if time.monotonic() > deadline:
                self.fail("apply did not finish within 5s")
            time.sleep(0.01)
        for patcher in self._patchers:
            patcher.stop()

    # -- helpers --------------------------------------------------------

    def _request(self, method, path, principal=None, **kwargs):
        headers = kwargs.pop("headers", {})
        if principal is not None:
            headers["X-Test-Principal"] = json.dumps(principal)
        return self.client.open(
            path, method=method, headers=headers, **kwargs
        )

    @staticmethod
    def user(user_id, scopes):
        return {"user": {"id": user_id, "scopes": scopes},
                "client": {"id": "cl_minter"}}

    @staticmethod
    def client_principal(client_id):
        return {"client": {"id": client_id}, "user": None}

    def grant(self, user_id, level, resource_id="auth"):
        from campus.auth.resources.grant import grants

        grants.grant(
            "user", user_id, "migrations", resource_id, level=level
        )

    # -- unauthenticated / client principals -----------------------------

    def test_no_principal_is_denied_everywhere(self):
        # rollback's required body field is validated by the request
        # unpacking (the codebase-wide convention: unpack first), so it
        # carries a body to reach the gate like the other routes.
        requests = [
            ("GET", "/admin/migrations/", None),
            ("POST", "/admin/migrations/apply", {}),
            ("POST", "/admin/migrations/abort", None),
            ("POST", "/admin/migrations/rollback", {"revision": "012"}),
        ]
        for method, path, body in requests:
            with self.subTest(path=path):
                kwargs = {"json": body} if body is not None else {}
                response = self._request(method, path, **kwargs)
                self.assertEqual(response.status_code, 403, path)

    def test_non_operator_client_principal_is_denied(self):
        from campus.auth.resources.grant import grants
        # Even a client-named grant row must not open the surface
        # (clients are never designated admins, #854).
        grants.grant(
            "client", "cl_x", "migrations", "auth", level="admin"
        )
        principal = self.client_principal("cl_x")
        response = self._request("GET", "/admin/migrations/", principal)
        self.assertEqual(response.status_code, 403)

    # -- the two-leg rule -------------------------------------------------

    def test_scope_without_row_is_denied(self):
        principal = self.user("u1", ["migrations:read"])
        response = self._request("GET", "/admin/migrations/", principal)
        self.assertEqual(response.status_code, 403)

    def test_row_without_scope_is_denied(self):
        self.grant("u1", "read")
        principal = self.user("u1", [])
        response = self._request("GET", "/admin/migrations/", principal)
        self.assertEqual(response.status_code, 403)

    # -- read level -------------------------------------------------------

    def test_read_only_user_can_read_status(self):
        self.grant("u1", "read")
        principal = self.user("u1", ["migrations:read"])
        response = self._request("GET", "/admin/migrations/", principal)
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["service"], "auth")
        self.assertIn("plan", body)
        self.assertIn("history", body)
        self.assertIn("status", body)
        self.assertFalse(body["running"])

    def test_read_only_user_is_denied_on_every_mutation(self):
        self.grant("u1", "read")
        principal = self.user("u1", ["migrations:read"])
        requests = [
            ("POST", "/admin/migrations/apply", {}),
            ("POST", "/admin/migrations/abort", None),
            ("POST", "/admin/migrations/rollback",
             {"revision": "012"}),
        ]
        for method, path, body in requests:
            with self.subTest(path=path):
                kwargs = {"json": body} if body is not None else {}
                response = self._request(method, path, principal,
                                         **kwargs)
                self.assertEqual(response.status_code, 403, path)

    def test_grant_for_another_service_does_not_open_this_one(self):
        """#1168 instance scoping: authority never covers the fleet."""
        self.grant("u1", "admin", resource_id="api")
        principal = self.user("u1", ["migrations:admin"])
        response = self._request("GET", "/admin/migrations/", principal)
        self.assertEqual(response.status_code, 403)

    # -- write level ------------------------------------------------------

    def test_write_user_can_apply_and_abort_gate(self):
        self.grant("u1", "write")
        principal = self.user("u1", ["migrations:write"])
        response = self._request("POST", "/admin/migrations/apply",
                                 principal, json={})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json(),
                         {"started": True, "service": "auth"})
        # The apply fake returns immediately; drain the thread before
        # asserting the abort gate's 409-nothing-running semantics.
        from migrations.routes import _RUN_STATE

        deadline = time.monotonic() + 5
        while _RUN_STATE.is_running("auth"):
            if time.monotonic() > deadline:
                self.fail("apply did not finish within 5s")
            time.sleep(0.01)
        # Abort passes the write gate (409 nothing-running, NOT 403).
        response = self._request("POST", "/admin/migrations/abort",
                                 principal)
        self.assertEqual(response.status_code, 409)

    def test_write_user_is_denied_rollback(self):
        self.grant("u1", "write")
        principal = self.user("u1", ["migrations:write"])
        response = self._request("POST", "/admin/migrations/rollback",
                                 principal, json={"revision": "012"})
        self.assertEqual(response.status_code, 403)

    def test_write_scope_covers_read(self):
        self.grant("u1", "write")
        principal = self.user("u1", ["migrations:write"])
        response = self._request("GET", "/admin/migrations/", principal)
        self.assertEqual(response.status_code, 200)

    # -- admin level ------------------------------------------------------

    def test_admin_user_can_rollback(self):
        self.grant("u1", "admin")
        principal = self.user("u1", ["migrations:admin"])
        response = self._request("POST", "/admin/migrations/rollback",
                                 principal, json={"revision": "012"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"rolled_back": "012"})

    # -- operator / super-admin -------------------------------------------

    def test_operator_client_bypasses_every_level(self):
        with mock.patch.dict(os.environ, OPERATOR_ENV):
            principal = self.client_principal(OPERATOR_ID)
            self.assertEqual(
                self._request(
                    "GET", "/admin/migrations/", principal).status_code,
                200,
            )
            self.assertEqual(
                self._request("POST", "/admin/migrations/apply",
                              principal, json={}).status_code,
                202,
            )
            from migrations.routes import _RUN_STATE

            deadline = time.monotonic() + 5
            while _RUN_STATE.is_running("auth"):
                if time.monotonic() > deadline:
                    self.fail("apply did not finish within 5s")
                time.sleep(0.01)
            self.assertEqual(
                self._request("POST", "/admin/migrations/rollback",
                              principal,
                              json={"revision": "012"}).status_code,
                200,
            )

    def test_user_never_inherits_the_minting_clients_operator_role(self):
        """#854: the user principal is consulted before the bypass."""
        with mock.patch.dict(os.environ, OPERATOR_ENV):
            principal = self.user("u1", [])
            principal["client"] = {"id": OPERATOR_ID}
            response = self._request("GET", "/admin/migrations/",
                                     principal)
            self.assertEqual(response.status_code, 403)

    def test_super_admin_root_passes_without_rows(self):
        """#897: the env-nominated root holds full privileges."""
        with mock.patch.dict(os.environ,
                             {"AUTH_SUPER_ADMIN": "root@nyjc.edu.sg"}):
            principal = {
                "user": {
                    "id": "u_root",
                    "email": "root@nyjc.edu.sg",
                    "scopes": [],
                },
                "client": {"id": "cl_minter"},
            }
            response = self._request("GET", "/admin/migrations/",
                                     principal)
            self.assertEqual(response.status_code, 200)


class TestAuthHook(IsolatedIntegrationTestCase):
    """The auth migrations blueprint must authenticate like every
    other management blueprint (#1185).

    #1182 registered the shared blueprint onto /auth/v1 WITHOUT the
    per-blueprint `before_request(resource_authenticator.authenticate)`
    hook that routes.init_app applies to each route module's own
    blueprint. Requests to /auth/v1/admin/migrations were therefore
    never authenticated at all: g stayed principal-less and the gate
    denied every caller — operator, root, designated admin — with the
    #854 anonymous-client 403.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.auth_client = cls.manager.auth_app.test_client()

    def test_unauthenticated_request_is_401_from_middleware(self):
        """No Authorization header → 401 from the authentication hook
        (the #1185 bug surfaced as the gate's anonymous-client 403).
        Trailing slash: auth sets strict slashes app-wide (#843 era)."""
        response = self.auth_client.get("/auth/v1/admin/migrations/")
        self.assertEqual(response.status_code, 401)

    def test_migrations_blueprint_carries_the_auth_hook(self):
        """The wiring applies the authenticator as a before_request on
        the registered migrations blueprint (app-level funcs keyed by
        the nested blueprint's full name)."""
        self.assertIn("auth.migrations", self.manager.auth_app.blueprints)
        funcs = self.manager.auth_app.before_request_funcs.get(
            "auth.migrations") or []
        self.assertTrue(funcs, "migrations blueprint has no auth hook")


if __name__ == "__main__":
    unittest.main()
