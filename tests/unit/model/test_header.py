"""Unit tests for campus.model.http.header authorization models."""

import base64
import unittest

from campus.model.http.header import HttpAuthProperty


class TestHttpAuthPropertyScheme(unittest.TestCase):
    """Scheme prefix contract: 'Basic '/'Bearer ' or ValueError."""

    def test_valid_bearer_round_trip(self):
        prop = HttpAuthProperty.for_bearer("token123")
        self.assertEqual(prop.scheme, "bearer")
        self.assertEqual(prop.token, "token123")

    def test_valid_basic_round_trip(self):
        prop = HttpAuthProperty.for_basic("client", "secret")
        self.assertEqual(prop.scheme, "basic")
        self.assertEqual(prop.credentials(), ("client", "secret"))

    def test_scheme_without_value_rejected(self):
        # curl trims trailing whitespace, so "Authorization: Bearer "
        # arrives as "Bearer" — the observed #725 payload.
        for value in ("Bearer", "Basic", ""):
            with self.assertRaises(ValueError):
                HttpAuthProperty(value)

    def test_unknown_scheme_rejected(self):
        with self.assertRaises(ValueError):
            HttpAuthProperty("Digest abc")

    def test_non_string_rejected(self):
        with self.assertRaises(TypeError):
            HttpAuthProperty(None)  # type: ignore[arg-type]


class TestHttpAuthPropertyCredentials(unittest.TestCase):
    """Basic credential decoding contract."""

    def test_credentials_round_trip(self):
        encoded = base64.b64encode(b"client:secret").decode()
        prop = HttpAuthProperty(f"Basic {encoded}")
        self.assertEqual(prop.credentials(), ("client", "secret"))

    def test_undecodable_base64_raises_value_error(self):
        # Non-alphabet characters are discarded by b64decode; "!!!" is
        # entirely invalid and leaves an empty payload (no separator).
        prop = HttpAuthProperty("Basic !!!")
        with self.assertRaises(ValueError):
            prop.credentials()

    def test_credentials_without_separator_raise_value_error(self):
        # ValueError, not assert: asserts vanish under python -O, and
        # the error message must never echo the decoded credentials.
        encoded = base64.b64encode(b"no-separator").decode()
        prop = HttpAuthProperty(f"Basic {encoded}")
        with self.assertRaises(ValueError) as ctx:
            prop.credentials()
        self.assertNotIn("no-separator", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
