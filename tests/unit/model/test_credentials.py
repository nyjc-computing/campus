"""Unit tests for the OAuthToken model (issue #648).

Covers the RFC 6749-compliant interface: token_type handling, stored
expires_in with the expires_at invariant, the scope/scopes views,
provider_fields, and standard-key acceptance in from_resource().
"""

import unittest

from campus.common import schema
from campus.model import credentials

CREATED_AT = schema.DateTime("2026-01-01T00:00:00+00:00")
EXPIRES_AT = schema.DateTime("2026-01-01T01:00:00+00:00")


class TestOAuthTokenConstruction(unittest.TestCase):
    """Tests for OAuthToken field handling at construction."""

    def test_default_token_type_is_bearer(self):
        """token_type should default to "Bearer"."""
        token = credentials.OAuthToken(
            created_at=CREATED_AT,
            expires_at=EXPIRES_AT,
        )
        self.assertEqual(token.token_type, "Bearer")

    def test_token_type_is_case_normalised(self):
        """Bearer spellings should normalise; other types are preserved."""
        for raw in ("bearer", "BEARER", "Bearer"):
            token = credentials.OAuthToken(
                created_at=CREATED_AT,
                expires_at=EXPIRES_AT,
                token_type=raw,
            )
            self.assertEqual(token.token_type, "Bearer", raw)
        token = credentials.OAuthToken(
            created_at=CREATED_AT,
            expires_at=EXPIRES_AT,
            token_type="DPoP",
        )
        self.assertEqual(token.token_type, "DPoP")

    def test_empty_token_type_defaults_to_bearer(self):
        """An empty token_type (e.g. legacy null) should fall back to Bearer."""
        token = credentials.OAuthToken(
            created_at=CREATED_AT,
            expires_at=EXPIRES_AT,
            token_type="",
        )
        self.assertEqual(token.token_type, "Bearer")

    def test_expires_in_derives_expires_at(self):
        """expires_in alone should derive expires_at = created_at + expires_in."""
        token = credentials.OAuthToken(
            created_at=CREATED_AT,
            expires_in=3600,
        )
        self.assertEqual(token.expires_at, EXPIRES_AT)
        self.assertEqual(token.expires_in, 3600)

    def test_expires_at_derives_expires_in(self):
        """expires_at alone (legacy-style) should derive expires_in."""
        token = credentials.OAuthToken(
            created_at=CREATED_AT,
            expires_at=EXPIRES_AT,
        )
        self.assertEqual(token.expires_in, 3600)

    def test_expiry_seconds_is_removed(self):
        """The legacy expiry_seconds alias was removed post-deprecation
        (#648 item 2); constructing with it must fail loudly."""
        with self.assertRaises(TypeError):
            credentials.OAuthToken(
                created_at=CREATED_AT,
                expiry_seconds=3600,
            )

    def test_missing_expiry_raises_value_error(self):
        """Construction without any expiry information should fail."""
        with self.assertRaises(ValueError):
            credentials.OAuthToken(created_at=CREATED_AT)

    def test_expires_at_is_temporal_authority(self):
        """When both expiries are given, expires_in must satisfy the
        invariant expires_at = created_at + expires_in.
        """
        token = credentials.OAuthToken(
            created_at=CREATED_AT,
            expires_at=EXPIRES_AT,
            expires_in=60,  # inconsistent on purpose
        )
        self.assertEqual(token.expires_at, EXPIRES_AT)
        self.assertEqual(token.expires_in, 3600)

    def test_string_datetimes_are_coerced(self):
        """JSON-borne string datetimes should not break expiry derivation."""
        token = credentials.OAuthToken(
            created_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-01-01T01:00:00+00:00",
        )
        self.assertIsInstance(token.expires_at, schema.DateTime)
        self.assertEqual(token.expires_in, 3600)

    def test_scopes_string_is_split(self):
        """A space-delimited scopes string should be stored as a list."""
        token = credentials.OAuthToken(
            created_at=CREATED_AT,
            expires_at=EXPIRES_AT,
            scopes="read write",
        )
        self.assertEqual(token.scopes, ["read", "write"])

    def test_scope_property_roundtrip(self):
        """scope should join scopes on read and split on assignment."""
        token = credentials.OAuthToken(
            created_at=CREATED_AT,
            expires_at=EXPIRES_AT,
            scopes=["read", "write"],
        )
        self.assertEqual(token.scope, "read write")
        token.scope = "read:users read:email"
        self.assertEqual(token.scopes, ["read:users", "read:email"])

    def test_access_token_alias(self):
        """access_token should alias id."""
        token = credentials.OAuthToken(
            id="tok_123",
            created_at=CREATED_AT,
            expires_at=EXPIRES_AT,
        )
        self.assertEqual(token.access_token, "tok_123")


class TestOAuthTokenFromResource(unittest.TestCase):
    """Tests for from_resource() with RFC 6749 and campus payloads."""

    def test_rfc6749_payload(self):
        """A standard token response should populate the model fields."""
        payload = {
            "access_token": "at_123",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "read write",
            "refresh_token": "rt_123",
        }
        token = credentials.OAuthToken.from_resource(payload)

        self.assertEqual(token.id, "at_123")
        self.assertEqual(token.access_token, "at_123")
        self.assertEqual(token.token_type, "Bearer")
        self.assertEqual(token.expires_in, 3600)
        self.assertIsInstance(token.expires_at, schema.DateTime)
        self.assertEqual(token.scopes, ["read", "write"])
        self.assertEqual(token.refresh_token, "rt_123")
        self.assertEqual(token.provider_fields, {})

    def test_rfc6749_payload_with_created_at(self):
        """A provided created_at should anchor the expiry derivation."""
        payload = {
            "access_token": "at_123",
            "expires_in": 600,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        token = credentials.OAuthToken.from_resource(payload)

        self.assertIsInstance(token.expires_at, schema.DateTime)
        self.assertEqual(
            token.expires_at,
            schema.DateTime.utcafter(CREATED_AT, seconds=600)
        )

    def test_token_type_normalised_on_input(self):
        """Non-canonical token_type spellings should normalise to Bearer."""
        payload = {
            "access_token": "at_123",
            "token_type": "bearer",
            "expires_in": 60,
        }
        token = credentials.OAuthToken.from_resource(payload)
        self.assertEqual(token.token_type, "Bearer")

    def test_provider_extras_captured_in_provider_fields(self):
        """Unknown keys should be preserved for internal use."""
        payload = {
            "access_token": "at_123",
            "expires_in": 3600,
            "id_token": "jwt_blob",
            "aud": "client_1",
        }
        token = credentials.OAuthToken.from_resource(payload)

        self.assertEqual(
            token.provider_fields,
            {"id_token": "jwt_blob", "aud": "client_1"}
        )

    def test_access_token_yields_to_id(self):
        """An explicit id should win over the access_token alias."""
        payload = {
            "id": "campus_tok",
            "access_token": "other_tok",
            "expires_in": 60,
        }
        token = credentials.OAuthToken.from_resource(payload)
        self.assertEqual(token.id, "campus_tok")

    def test_expiry_seconds_key_is_no_longer_special(self):
        """The legacy expiry_seconds payload key is no longer mapped;
        per the unknown-key policy it lands in provider_fields."""
        payload = {
            "id": "tok_1",
            "expiry_seconds": 600,
            "expires_in": 600,
        }
        token = credentials.OAuthToken.from_resource(payload)
        self.assertEqual(token.expires_in, 600)
        self.assertEqual(token.provider_fields.get("expiry_seconds"), 600)

    def test_string_expires_in_is_coerced(self):
        """A string expires_in (lenient provider) should coerce to int."""
        payload = {
            "access_token": "at_123",
            "expires_in": "3600",
        }
        token = credentials.OAuthToken.from_resource(payload)
        self.assertEqual(token.expires_in, 3600)
        self.assertIsInstance(token.expires_in, int)

    def test_to_resource_from_resource_roundtrip(self):
        """A token resource should roundtrip through from_resource,
        with the RFC 6749 scope string as the only scope emission.
        """
        token = credentials.OAuthToken(
            id="tok_123",
            created_at=CREATED_AT,
            expires_at=EXPIRES_AT,
            scopes=["read", "write"],
            refresh_token="rt_123",
            provider_fields={"id_token": "jwt_blob"},
        )
        resource = token.to_resource()
        # scope-only emission: the scopes list alias was dropped from
        # resources (#648 deprecation, emission side)
        self.assertIn("scope", resource)
        self.assertEqual(resource["scope"], "read write")
        self.assertNotIn("scopes", resource)
        self.assertNotIn("provider_fields", resource)

        loaded = credentials.OAuthToken.from_resource(resource)
        self.assertEqual(loaded.id, token.id)
        self.assertEqual(loaded.created_at, token.created_at)
        self.assertEqual(loaded.expires_at, token.expires_at)
        self.assertEqual(loaded.expires_in, token.expires_in)
        self.assertEqual(loaded.token_type, token.token_type)
        self.assertEqual(loaded.scopes, token.scopes)
        self.assertEqual(loaded.refresh_token, token.refresh_token)
        # provider_fields is not emitted in resources by design;
        # persistence is covered by the storage roundtrip test
        self.assertEqual(loaded.provider_fields, {})


class TestOAuthTokenStorage(unittest.TestCase):
    """Tests for to_storage()/from_storage() with new and legacy records."""

    def test_to_storage_from_storage_roundtrip(self):
        """All fields, including the #648 additions, should roundtrip.

        Storage keeps the RFC 6749 scope string (#648 decision 4 end
        state); the scopes list is model-side only.
        """
        token = credentials.OAuthToken(
            id="tok_123",
            created_at=CREATED_AT,
            expires_at=EXPIRES_AT,
            token_type="Bearer",
            scopes=["read"],
            provider_fields={"id_token": "jwt_blob"},
        )
        record = token.to_storage()
        self.assertEqual(record["token_type"], "Bearer")
        self.assertEqual(record["expires_in"], 3600)
        self.assertEqual(record["provider_fields"], {"id_token": "jwt_blob"})
        self.assertEqual(record["scope"], "read")
        self.assertNotIn("scopes", record)

        loaded = credentials.OAuthToken.from_storage(record)
        self.assertEqual(loaded.id, token.id)
        self.assertEqual(loaded.expires_at, token.expires_at)
        self.assertEqual(loaded.expires_in, token.expires_in)
        self.assertEqual(loaded.token_type, token.token_type)
        self.assertEqual(loaded.scopes, token.scopes)
        self.assertEqual(loaded.provider_fields, token.provider_fields)

    def test_from_storage_scope_string_record(self):
        """Storage records carrying the scope string should load."""
        record = {
            "id": "tok_123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "expires_at": "2026-01-01T01:00:00+00:00",
            "scope": "read write",
        }
        token = credentials.OAuthToken.from_storage(record)
        self.assertEqual(token.scopes, ["read", "write"])

    def test_from_storage_legacy_scopes_list_tolerated(self):
        """Records written before the storage flip (scopes list) still load."""
        legacy_record = {
            "id": "tok_123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "expires_at": "2026-01-01T01:00:00+00:00",
            "scopes": ["read", "write"],
        }
        token = credentials.OAuthToken.from_storage(legacy_record)

        self.assertEqual(token.expires_in, 3600)
        self.assertEqual(token.token_type, "Bearer")
        self.assertEqual(token.provider_fields, {})
        self.assertEqual(token.scopes, ["read", "write"])

    def test_from_storage_string_datetimes(self):
        """Storage-backed string datetimes should deserialize."""
        record = {
            "id": "tok_123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "expires_at": "2026-01-01T01:00:00+00:00",
        }
        token = credentials.OAuthToken.from_storage(record)
        self.assertIsInstance(token.expires_at, schema.DateTime)
        self.assertIsInstance(token.created_at, schema.DateTime)
        self.assertEqual(token.expires_in, 3600)


class TestUserCredentialsWithToken(unittest.TestCase):
    """Tests for UserCredentials joined-token handling (#631/#633 lineage)."""

    def test_from_resource_with_rfc6749_token(self):
        """UserCredentials should accept a nested RFC 6749 token payload."""
        resource = {
            "id": "cred1",
            "provider": "campus",
            "client_id": "guest",
            "user_id": "user@campus.edu",
            "token": {
                "access_token": "at_123",
                "token_type": "bearer",
                "expires_in": 3600,
                "scope": "read write",
            },
        }
        user_creds = credentials.UserCredentials.from_resource(resource)

        token = user_creds.token
        self.assertIsInstance(token, credentials.OAuthToken)
        self.assertEqual(token.id, "at_123")
        self.assertEqual(token.token_type, "Bearer")
        self.assertEqual(token.expires_in, 3600)
        self.assertEqual(token.scopes, ["read", "write"])
        self.assertIsInstance(token.is_expired(), bool)

    def test_to_resource_nests_token_resource_shape(self):
        """UserCredentials.to_resource should serialize the joined token
        via OAuthToken.to_resource: scope emitted, provider_fields not
        leaked (follow-up to #650: JSON-layer asdict() handling bypassed
        the token's to_resource and dropped scope / leaked extras).
        """
        user_creds = credentials.UserCredentials(
            id="cred1",
            provider="campus",
            client_id="guest",
            user_id="user@campus.edu",
        )
        user_creds.token = credentials.OAuthToken(
            id="at_123",
            created_at=CREATED_AT,
            expires_at=EXPIRES_AT,
            scopes=["read", "write"],
            provider_fields={"id_token": "jwt_blob"},
        )

        resource = user_creds.to_resource()
        token_resource = resource["token"]

        self.assertIsInstance(token_resource, dict)
        self.assertEqual(token_resource["scope"], "read write")
        self.assertNotIn("scopes", token_resource)
        self.assertNotIn("provider_fields", token_resource)

        loaded = credentials.UserCredentials.from_resource(resource)
        self.assertEqual(loaded.token.id, "at_123")
        self.assertEqual(loaded.token.scopes, ["read", "write"])


if __name__ == '__main__':
    unittest.main()
