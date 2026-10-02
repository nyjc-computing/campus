"""Unit tests for campus.common.webauth.http Authorization handling.

Regression tests for #725: malformed Authorization header values must
surface as UnauthorizedError (401) at the webauth boundary, never as a
raw ValueError that escapes to the 500 handler.
"""

import base64
import os
import unittest

os.environ["ENV"] = "development"

from campus.common.errors import api_errors
from campus.common.webauth import http as webauth_http


def _basic(client_id: str, client_secret: str) -> str:
    encoded = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()
    return f"Basic {encoded}"


class TestWithHeaderAcceptsWellFormed(unittest.TestCase):
    """Well-formed Basic/Bearer headers construct the scheme object."""

    def test_valid_basic(self):
        auth = webauth_http.HttpAuthenticationScheme.with_header(
            provider="campus",
            http_header={"Authorization": _basic("cid", "sec")},
        )
        self.assertEqual(auth.scheme, "basic")
        self.assertEqual(
            auth.header.authorization.credentials(),
            ("cid", "sec"),
        )

    def test_valid_bearer(self):
        auth = webauth_http.HttpAuthenticationScheme.with_header(
            provider="campus",
            http_header={"Authorization": "Bearer tok123"},
        )
        self.assertEqual(auth.scheme, "bearer")
        self.assertEqual(auth.header.authorization.token, "tok123")


class TestWithHeaderRejectsMalformed(unittest.TestCase):
    """Malformed Authorization values raise UnauthorizedError (#725)."""

    def test_missing_authorization_header(self):
        with self.assertRaises(api_errors.UnauthorizedError):
            webauth_http.HttpAuthenticationScheme.with_header(
                provider="campus",
                http_header={},
            )

    def test_scheme_without_value(self):
        with self.assertRaises(api_errors.UnauthorizedError):
            webauth_http.HttpAuthenticationScheme.with_header(
                provider="campus",
                http_header={"Authorization": "Bearer"},
            )

    def test_unknown_scheme(self):
        with self.assertRaises(api_errors.UnauthorizedError):
            webauth_http.HttpAuthenticationScheme.with_header(
                provider="campus",
                http_header={"Authorization": "Digest abc"},
            )

    def test_basic_without_separator(self):
        encoded = base64.b64encode(b"no-separator").decode()
        with self.assertRaises(api_errors.UnauthorizedError):
            webauth_http.HttpAuthenticationScheme.with_header(
                provider="campus",
                http_header={"Authorization": f"Basic {encoded}"},
            )

    def test_basic_undecodable(self):
        with self.assertRaises(api_errors.UnauthorizedError):
            webauth_http.HttpAuthenticationScheme.with_header(
                provider="campus",
                http_header={"Authorization": "Basic !!!"},
            )


if __name__ == "__main__":
    unittest.main()
