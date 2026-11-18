"""The shared Authenticator hydrates flask.g.current_scopes (#1183).

The capability leg of the two-leg management model (#865) reads the
bearer's granted scopes from the request context; this pins the
hydration for every service that wires the shared Authenticator
(campus.api passes the authenticate response's `scopes` through).
"""

import unittest

import flask


class TestAuthenticatorCurrentScopes(unittest.TestCase):
    """bearer authenticate results carry scopes into the request ctx."""

    @staticmethod
    def _authenticator(bearer_result):
        from campus.auth.middleware import Authenticator

        return Authenticator(
            basic_authenticator=lambda client_id, secret: {
                "client": {"id": client_id}},
            bearer_authenticator=lambda token: bearer_result,
        )

    def test_bearer_scopes_reach_the_request_context(self):
        authenticator = self._authenticator({
            "client": {"id": "cl_1"},
            "user": {"id": "u1"},
            "scopes": ["migrations:write"],
        })
        app = flask.Flask(__name__)
        with app.test_request_context(
                headers={"Authorization": "Bearer tok123"}):
            authenticator.authenticate()
            self.assertEqual(flask.g.current_scopes, ["migrations:write"])
            self.assertEqual(flask.g.current_user, {"id": "u1"})
            self.assertEqual(flask.g.current_client, {"id": "cl_1"})

    def test_result_without_scopes_yields_empty_list(self):
        """Fail-closed by default: no scopes key means an empty list,
        never None leaking into gate algebra."""
        authenticator = self._authenticator({"client": {"id": "cl_1"}})
        app = flask.Flask(__name__)
        with app.test_request_context(
                headers={"Authorization": "Bearer tok123"}):
            authenticator.authenticate()
            self.assertEqual(flask.g.current_scopes, [])


if __name__ == "__main__":
    unittest.main()
