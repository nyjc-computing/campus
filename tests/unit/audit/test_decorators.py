"""Unit tests for campus.audit.decorators scope authorization.

These tests verify the scope_matches wildcard logic and the
require_scopes decorator behavior in a Flask request context.

Issue: #575
"""

import unittest

import flask

from campus.audit.decorators import require_scopes, scope_matches
from campus.common.errors import api_errors


class TestScopeMatches(unittest.TestCase):
    """Test the wildcard matching between granted and required scopes."""

    def test_exact_match(self):
        """A granted scope satisfies its exact requirement."""
        self.assertTrue(scope_matches("traces:read", "traces:read"))

    def test_no_match(self):
        """A granted scope does not satisfy a different requirement."""
        self.assertFalse(scope_matches("traces:read", "traces:write"))
        self.assertFalse(scope_matches("metrics:read", "traces:read"))

    def test_global_wildcard_grants_everything(self):
        """The "*" granted scope satisfies any requirement."""
        self.assertTrue(scope_matches("*", "traces:read"))
        self.assertTrue(scope_matches("*", "traces:write"))
        self.assertTrue(scope_matches("*", "metrics:read"))
        self.assertTrue(scope_matches("*", "*"))

    def test_category_wildcard_grants_same_category(self):
        """A "traces:*" granted scope satisfies traces requirements."""
        self.assertTrue(scope_matches("traces:*", "traces:read"))
        self.assertTrue(scope_matches("traces:*", "traces:write"))

    def test_category_wildcard_does_not_cross_categories(self):
        """A category wildcard does not satisfy other categories."""
        self.assertFalse(scope_matches("traces:*", "metrics:read"))

    def test_required_wildcard_matches_only_itself(self):
        """A wildcard in the required position only matches itself."""
        self.assertTrue(scope_matches("traces:*", "traces:*"))
        self.assertFalse(scope_matches("traces:read", "traces:*"))


class TestRequireScopes(unittest.TestCase):
    """Test the require_scopes decorator against flask.g.api_key_scopes."""

    def setUp(self):
        self.app = flask.Flask(__name__)

    def _call(self, scopes, func, *args, **kwargs):
        """Call func under a request context with the given key scopes."""
        with self.app.test_request_context():
            flask.g.api_key_scopes = scopes
            return func(*args, **kwargs)

    def test_endpoint_requires_at_least_one_scope(self):
        """require_scopes() without arguments is a programming error."""
        with self.assertRaises(ValueError):
            require_scopes()

    def test_access_allowed_with_matching_scope(self):
        """The handler runs when the key holds the required scope."""

        @require_scopes("traces:read")
        def handler():
            return "ok"

        self.assertEqual(self._call(["traces:read"], handler), "ok")

    def test_access_denied_without_matching_scope(self):
        """ForbiddenError is raised when the scope is missing."""

        @require_scopes("traces:write")
        def handler():
            return "ok"

        with self.assertRaises(api_errors.ForbiddenError):
            self._call(["traces:read"], handler)

    def test_access_denied_without_authentication(self):
        """ForbiddenError is raised when no key scopes are on flask.g."""

        @require_scopes("traces:read")
        def handler():
            return "ok"

        with self.app.test_request_context():
            with self.assertRaises(api_errors.ForbiddenError):
                handler()

    def test_category_wildcard_grants_access(self):
        """A "traces:*" key scope satisfies concrete requirements."""

        @require_scopes("traces:write")
        def handler():
            return "ok"

        self.assertEqual(self._call(["traces:*"], handler), "ok")

    def test_global_wildcard_grants_access(self):
        """A "*" key scope satisfies any requirement."""

        @require_scopes("traces:read", "metrics:read")
        def handler():
            return "ok"

        self.assertEqual(self._call(["*"], handler), "ok")

    def test_all_required_scopes_must_be_satisfied(self):
        """Every required scope must be granted (conjunctive)."""

        @require_scopes("traces:read", "traces:write")
        def handler():
            return "ok"

        self.assertEqual(
            self._call(["traces:read", "traces:write"], handler), "ok"
        )

        with self.assertRaises(api_errors.ForbiddenError):
            self._call(["traces:read"], handler)

    def test_decorator_preserves_function_name(self):
        """functools.wraps keeps the handler's identity for Flask."""

        @require_scopes("traces:read")
        def handler():
            return "ok"

        self.assertEqual(handler.__name__, "handler")


if __name__ == "__main__":
    unittest.main()
