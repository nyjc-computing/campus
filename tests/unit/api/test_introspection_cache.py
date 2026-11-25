"""Introspection cache for the api Authenticator backends (#1248).

campus tokens are opaque and validated server-side, so every campus.api
call paid a /root/authenticate round trip — a multi-span journey
introspected the same bearer once per call. The cache keys results by
credential digest for a short TTL; rejections are never cached.
"""

import os
import unittest
from unittest import mock

from campus_python import errors


def _auth_result(user="u1"):
    return {"client": "uid-client-test", "user": user, "scopes": ["read"]}


class TestIntrospectionCache(unittest.TestCase):
    """bearer/basic authenticate results are cached per credential."""

    def setUp(self):
        import campus.api as campus_api

        self.campus_api = campus_api
        campus_api._introspection_cache.clear()
        self.fake = mock.Mock()
        self.fake.auth.root.authenticate.return_value = _auth_result()
        patcher = mock.patch.object(campus_api, "campus", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        env_patcher = mock.patch.dict(
            os.environ, {"AUTH_INTROSPECTION_TTL_SECONDS": "30"}
        )
        env_patcher.start()
        self.addCleanup(env_patcher.stop)

    def test_same_bearer_introspects_once(self):
        first = self.campus_api.bearer_authenticate(token="tok-a")
        second = self.campus_api.bearer_authenticate(token="tok-a")

        self.assertEqual(first, second)
        self.assertEqual(self.fake.auth.root.authenticate.call_count, 1)

    def test_different_bearer_introspects_again(self):
        self.campus_api.bearer_authenticate(token="tok-a")
        self.campus_api.bearer_authenticate(token="tok-b")

        self.assertEqual(self.fake.auth.root.authenticate.call_count, 2)

    def test_ttl_zero_disables_the_cache(self):
        env = mock.patch.dict(
            os.environ, {"AUTH_INTROSPECTION_TTL_SECONDS": "0"}
        )
        with env:
            self.campus_api.bearer_authenticate(token="tok-a")
            self.campus_api.bearer_authenticate(token="tok-a")

        self.assertEqual(self.fake.auth.root.authenticate.call_count, 2)

    def test_rejections_are_never_cached(self):
        self.fake.auth.root.authenticate.side_effect = (
            errors.AccessDeniedError(error_description="revoked")
        )
        with self.assertRaises(self.campus_api.api_errors.UnauthorizedError):
            self.campus_api.bearer_authenticate(token="tok-a")
        with self.assertRaises(self.campus_api.api_errors.UnauthorizedError):
            self.campus_api.bearer_authenticate(token="tok-a")

        # A revocation must be re-observed on every call, not frozen
        # into the cache for the TTL.
        self.assertEqual(self.fake.auth.root.authenticate.call_count, 2)

    def test_basic_credentials_cache_under_their_own_key(self):
        first = self.campus_api.basic_authenticate(
            client_id="uid-client-test", client_secret="s3cret"
        )
        second = self.campus_api.basic_authenticate(
            client_id="uid-client-test", client_secret="s3cret"
        )

        self.assertEqual(first, second)
        self.assertEqual(first["user"], None)
        self.assertEqual(self.fake.auth.root.authenticate.call_count, 1)

    def test_cache_is_bounded(self):
        self.campus_api._INTROSPECTION_CACHE_MAX = 4
        try:
            for i in range(6):
                self.campus_api.bearer_authenticate(token=f"tok-{i}")
            self.assertLessEqual(len(self.campus_api._introspection_cache), 4)
        finally:
            self.campus_api._INTROSPECTION_CACHE_MAX = 4096
