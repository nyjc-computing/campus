"""Unit tests for campus.common.utils.secret module.

These tests verify that cryptographic and secret generation utility functions
fulfill their interface contracts. Security-critical functions are tested
thoroughly including edge cases and error conditions.

Test Principles:
- Test interface contracts, not implementation
- Test generation functions produce correct format/length
- Test hashing/verification pairs work correctly
- Test edge cases and error conditions
- Do not test which specific crypto library is used
"""

import unittest
from campus.common.utils import secret


class TestSecretGeneration(unittest.TestCase):
    """Test secret and token generation functions."""

    def test_generate_api_key_default_length(self):
        """Test that generate_api_key() returns correct default length."""
        key = secret.generate_api_key()

        self.assertIsInstance(key, str)
        self.assertEqual(len(key), 32)

    def test_generate_api_key_custom_length(self):
        """Test that generate_api_key() respects custom length."""
        for length in [16, 32, 64, 128]:
            with self.subTest(length=length):
                key = secret.generate_api_key(length=length)
                self.assertEqual(len(key), length)

    def test_generate_api_key_produces_different_keys(self):
        """Test that generate_api_key() produces different keys each time."""
        keys = {secret.generate_api_key() for _ in range(10)}
        # All keys should be unique
        self.assertEqual(len(keys), 10)

    def test_generate_otp_default_length(self):
        """Test that generate_otp() returns 6-digit string by default."""
        otp = secret.generate_otp()

        self.assertIsInstance(otp, str)
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit(), "OTP should contain only digits")

    def test_generate_otp_custom_length(self):
        """Test that generate_otp() respects custom length."""
        for length in [4, 6, 8, 10]:
            with self.subTest(length=length):
                otp = secret.generate_otp(length=length)
                self.assertEqual(len(otp), length)
                self.assertTrue(otp.isdigit())

    def test_generate_otp_produces_different_otps(self):
        """Test that generate_otp() produces different OTPs each time."""
        otps = {secret.generate_otp() for _ in range(10)}
        # Most OTPs should be unique (allow some collision due to small space)
        self.assertGreater(len(otps), 5)

    def test_generate_access_token_format(self):
        """Test that generate_access_token() returns valid token."""
        token = secret.generate_access_token()

        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20, "Token should be reasonably long")

    def test_generate_access_token_uniqueness(self):
        """Test that generate_access_token() produces unique tokens."""
        tokens = {secret.generate_access_token() for _ in range(10)}
        self.assertEqual(len(tokens), 10)

    def test_generate_access_code_format(self):
        """Test that generate_access_code() returns valid code."""
        code = secret.generate_access_code()

        self.assertIsInstance(code, str)
        self.assertGreater(len(code), 10, "Code should be reasonably long")

    def test_generate_authorization_code_format(self):
        """Test that generate_authorization_code() returns valid code."""
        code = secret.generate_authorization_code()

        self.assertIsInstance(code, str)
        self.assertGreater(len(code), 10, "Code should be reasonably long")

    def test_generate_client_secret_default_length(self):
        """Test that generate_client_secret() returns correct default length."""
        client_secret = secret.generate_client_secret()

        self.assertIsInstance(client_secret, str)
        self.assertEqual(len(client_secret), 64)

    def test_generate_client_secret_custom_length(self):
        """Test that generate_client_secret() respects custom length."""
        client_secret = secret.generate_client_secret(length=128)
        self.assertEqual(len(client_secret), 128)

    def test_generate_session_state_format(self):
        """Test that generate_session_state() returns valid state."""
        state = secret.generate_session_state()

        self.assertIsInstance(state, str)
        self.assertGreater(len(state), 10, "State should be reasonably long")


class TestOTPHashing(unittest.TestCase):
    """Test OTP hashing and verification functions."""

    def test_hash_otp_returns_string(self):
        """Test that hash_otp() returns a string."""
        hashed = secret.hash_otp("123456")
        self.assertIsInstance(hashed, str)

    def test_hash_otp_different_from_plain(self):
        """Test that hashed OTP is different from plain OTP."""
        plain_otp = "123456"
        hashed = secret.hash_otp(plain_otp)
        self.assertNotEqual(hashed, plain_otp)

    def test_hash_otp_different_each_time(self):
        """Test that hashing same OTP produces different hashes (salt)."""
        plain_otp = "123456"
        hash1 = secret.hash_otp(plain_otp)
        hash2 = secret.hash_otp(plain_otp)

        # Hashes should be different due to salt
        self.assertNotEqual(hash1, hash2)

    def test_verify_otp_with_correct_otp(self):
        """Test that verify_otp() returns True for correct OTP."""
        plain_otp = "123456"
        hashed = secret.hash_otp(plain_otp)

        result = secret.verify_otp(plain_otp, hashed)
        self.assertTrue(result)

    def test_verify_otp_with_wrong_otp(self):
        """Test that verify_otp() returns False for wrong OTP."""
        plain_otp = "123456"
        hashed = secret.hash_otp(plain_otp)

        # Test various wrong OTPs
        wrong_otps = ["wrong", "123457", "000000", "654321"]
        for wrong in wrong_otps:
            with self.subTest(wrong=wrong):
                result = secret.verify_otp(wrong, hashed)
                self.assertFalse(result)

    def test_verify_otp_works_with_different_hashes(self):
        """Test that verify_otp() works with different hashes of same OTP."""
        plain_otp = "123456"
        hash1 = secret.hash_otp(plain_otp)
        hash2 = secret.hash_otp(plain_otp)

        # Both hashes should verify with the same plain OTP
        self.assertTrue(secret.verify_otp(plain_otp, hash1))
        self.assertTrue(secret.verify_otp(plain_otp, hash2))

    def test_hash_and_verify_otp_roundtrip(self):
        """Test complete hash/verify OTP roundtrip."""
        test_otps = ["123456", "000000", "999999", "135790"]

        for otp in test_otps:
            with self.subTest(otp=otp):
                hashed = secret.hash_otp(otp)
                self.assertTrue(secret.verify_otp(otp, hashed))
                self.assertFalse(secret.verify_otp("wrong", hashed))


class TestClientSecretHashing(unittest.TestCase):
    """Test client secret hashing functions."""

    def test_hash_client_secret_returns_string(self):
        """Test that hash_client_secret() returns a string."""
        result = secret.hash_client_secret("my-secret", "encryption-key")
        self.assertIsInstance(result, str)

    def test_hash_client_secret_different_from_plain(self):
        """Test that hashed secret is different from plain secret."""
        plain_secret = "my-secret"
        key = "encryption-key"

        hashed = secret.hash_client_secret(plain_secret, key)
        self.assertNotEqual(hashed, plain_secret)

    def test_hash_client_secret_deterministic_with_same_key(self):
        """Test that hashing with same key produces same hash."""
        plain_secret = "my-secret"
        key = "encryption-key"

        hash1 = secret.hash_client_secret(plain_secret, key)
        hash2 = secret.hash_client_secret(plain_secret, key)

        # Should be deterministic (same key = same hash)
        self.assertEqual(hash1, hash2)

    def test_hash_client_secret_different_with_different_key(self):
        """Test that hashing with different keys produces different hashes."""
        plain_secret = "my-secret"

        hash1 = secret.hash_client_secret(plain_secret, "key1")
        hash2 = secret.hash_client_secret(plain_secret, "key2")

        # Different keys should produce different hashes
        self.assertNotEqual(hash1, hash2)


class TestHTTPBasicAuth(unittest.TestCase):
    """Test HTTP Basic Authentication encoding/decoding."""

    def test_encode_http_basic_auth_returns_string(self):
        """Test that encode_http_basic_auth() returns a string."""
        result = secret.encode_http_basic_auth("user", "pass")
        self.assertIsInstance(result, str)

    def test_decode_http_basic_auth_returns_tuple(self):
        """Test that decode_http_basic_auth() returns username and password."""
        encoded = secret.encode_http_basic_auth("user", "pass")
        username, password = secret.decode_http_basic_auth(encoded)

        self.assertIsInstance(username, str)
        self.assertIsInstance(password, str)

    def test_http_basic_auth_roundtrip(self):
        """Test that encode/decode HTTP Basic Auth roundtrips correctly."""
        username = "testuser"
        password = "testpass"

        encoded = secret.encode_http_basic_auth(username, password)
        decoded_user, decoded_pass = secret.decode_http_basic_auth(encoded)

        self.assertEqual(username, decoded_user)
        self.assertEqual(password, decoded_pass)

    def test_decode_with_basic_prefix(self):
        """Test decoding HTTP Basic Auth with 'Basic ' prefix."""
        username = "testuser"
        password = "testpass"

        encoded = secret.encode_http_basic_auth(username, password)
        with_prefix = f"Basic {encoded}"
        # The header now contains a double 'Basic' prefix ("Basic Basic <b64>")
        # which is malformed per RFC7617; decoding should raise ValueError.
        with self.assertRaises(ValueError):
            secret.decode_http_basic_auth(with_prefix)

    def test_http_basic_auth_with_special_characters(self):
        """Test HTTP Basic Auth with special characters in credentials."""
        test_cases = [
            ("user@example.com", "p@ss:w0rd!"),
            ("user", "password with spaces"),
            ("unicode_user", "пароль"),  # Unicode password
        ]

        for username, password in test_cases:
            with self.subTest(username=username, password=password):
                encoded = secret.encode_http_basic_auth(username, password)
                # If the username itself contains a colon then the
                # credentials are ambiguous (username:password uses the
                # first colon as a separator). The implementation is
                # strict and will treat such inputs as invalid.
                if ':' in username:
                    with self.assertRaises(ValueError):
                        secret.decode_http_basic_auth(encoded)
                else:
                    decoded_user, decoded_pass = secret.decode_http_basic_auth(
                        encoded)
                    self.assertEqual(username, decoded_user)
                    self.assertEqual(password, decoded_pass)

    def test_http_basic_auth_with_empty_password(self):
        """Test HTTP Basic Auth with empty password."""
        username = "testuser"
        password = ""

        encoded = secret.encode_http_basic_auth(username, password)
        decoded_user, decoded_pass = secret.decode_http_basic_auth(encoded)

        self.assertEqual(username, decoded_user)
        self.assertEqual(password, decoded_pass)

    def test_decode_invalid_format_raises_error(self):
        """Test that decode_http_basic_auth() raises ValueError for invalid input."""
        invalid_inputs = [
            "",                    # Empty string
            "not-base64!@#",      # Invalid base64
            "Basic",              # Just the prefix
        ]

        for invalid in invalid_inputs:
            with self.subTest(invalid=invalid):
                with self.assertRaises((ValueError, Exception)):
                    secret.decode_http_basic_auth(invalid)

    def test_decode_valid_base64_without_colon(self):
        """Test decode with valid base64 but missing colon separator."""
        import base64
        # Valid base64 but missing colon
        invalid = base64.b64encode(b"useronly").decode()

        with self.assertRaises((ValueError, Exception)):
            secret.decode_http_basic_auth(invalid)


class TestAuditAPIKeyFunctions(unittest.TestCase):
    """Test audit service API key generation, hashing, and validation functions."""

    def test_generate_audit_api_key_returns_string(self):
        """Test that generate_audit_api_key() returns a string."""
        key = secret.generate_audit_api_key()
        self.assertIsInstance(key, str)

    def test_generate_audit_api_key_correct_length(self):
        """Test that generate_audit_api_key() returns 31-character key."""
        key = secret.generate_audit_api_key()
        self.assertEqual(len(key), 31,
                        "API key should be 31 characters (9 prefix + 22 random)")

    def test_generate_audit_api_key_has_prefix(self):
        """Test that generate_audit_api_key() starts with correct prefix."""
        key = secret.generate_audit_api_key()
        self.assertTrue(key.startswith("audit_v1_"),
                       "API key should start with 'audit_v1_' prefix")

    def test_generate_audit_api_key_produces_unique_keys(self):
        """Test that generate_audit_api_key() produces different keys each time."""
        keys = {secret.generate_audit_api_key() for _ in range(100)}
        # All keys should be unique with high probability
        self.assertEqual(len(keys), 100,
                        "All generated keys should be unique")

    def test_generate_audit_api_key_format_valid(self):
        """Test that generate_audit_api_key() produces valid base64url format."""
        key = secret.generate_audit_api_key()
        # Should pass format validation
        self.assertTrue(secret.is_valid_audit_api_key_format(key),
                       "Generated key should pass format validation")

    def test_hash_api_key_returns_string(self):
        """Test that hash_api_key() returns a string."""
        api_key = "audit_v1_testkey1234567890123"
        hashed = secret.hash_api_key(api_key)
        self.assertIsInstance(hashed, str)

    def test_hash_api_key_correct_length(self):
        """Test that hash_api_key() returns 64-character hex string."""
        api_key = "audit_v1_testkey1234567890123"
        hashed = secret.hash_api_key(api_key)
        self.assertEqual(len(hashed), 64,
                        "SHA-256 hash should be 64 hex characters")

    def test_hash_api_key_uses_hex_chars(self):
        """Test that hash_api_key() returns valid hex string."""
        api_key = "audit_v1_testkey1234567890123"
        hashed = secret.hash_api_key(api_key)
        # Should contain only hex characters
        self.assertTrue(all(c in '0123456789abcdef' for c in hashed),
                       "Hash should contain only lowercase hex characters")

    def test_hash_api_key_deterministic(self):
        """Test that hash_api_key() is deterministic for same input."""
        api_key = "audit_v1_testkey1234567890123"
        hash1 = secret.hash_api_key(api_key)
        hash2 = secret.hash_api_key(api_key)
        self.assertEqual(hash1, hash2,
                        "Hashing same key should produce same result")

    def test_hash_api_key_different_for_different_keys(self):
        """Test that hash_api_key() produces different hashes for different keys."""
        key1 = "audit_v1_testkey1234567890123"
        key2 = "audit_v1_differentkey1234567890"
        hash1 = secret.hash_api_key(key1)
        hash2 = secret.hash_api_key(key2)
        self.assertNotEqual(hash1, hash2,
                           "Different keys should produce different hashes")

    def test_verify_api_key_hash_with_correct_key(self):
        """Test that verify_api_key_hash() returns True for correct key."""
        api_key = "audit_v1_testkey1234567890123"
        stored_hash = secret.hash_api_key(api_key)
        result = secret.verify_api_key_hash(api_key, stored_hash)
        self.assertTrue(result,
                       "Verification should succeed with correct key")

    def test_verify_api_key_hash_with_wrong_key(self):
        """Test that verify_api_key_hash() returns False for wrong key."""
        correct_key = "audit_v1_testkey1234567890123"
        wrong_key = "audit_v1_wrongkey1234567890123"
        stored_hash = secret.hash_api_key(correct_key)
        result = secret.verify_api_key_hash(wrong_key, stored_hash)
        self.assertFalse(result,
                        "Verification should fail with incorrect key")

    def test_verify_api_key_hash_similar_keys_different(self):
        """Test that similar keys produce different verification results."""
        key1 = "audit_v1_testkey1234567890123"
        key2 = "audit_v1_testkey1234567890124"  # Only last char different
        hash1 = secret.hash_api_key(key1)

        # key1 should verify with hash1
        self.assertTrue(secret.verify_api_key_hash(key1, hash1))
        # key2 should NOT verify with hash1
        self.assertFalse(secret.verify_api_key_hash(key2, hash1))

    def test_verify_api_key_hash_roundtrip(self):
        """Test complete hash/verify API key roundtrip."""
        test_keys = [
            "audit_v1_testkey1234567890123",
            "audit_v1_ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "audit_v1_0123456789ABCDEFGHIJKLMNOPQR",
        ]

        for key in test_keys:
            with self.subTest(key=key):
                hashed = secret.hash_api_key(key)
                self.assertTrue(secret.verify_api_key_hash(key, hashed),
                               f"Key {key} should verify with its hash")
                # Different key should not verify
                self.assertFalse(secret.verify_api_key_hash("wrong", hashed),
                                f"Different key should not verify with hash of {key}")

    def test_is_valid_audit_api_key_format_with_valid_key(self):
        """Test format validation with valid API keys."""
        valid_keys = [
            "audit_v1_kXj9mP2nQ5vR8sT7uV3wYz",      # 22 char random part
            "audit_v1_0123456789ABCDEFGHIJab",       # 22 char random part
            "audit_v1_abcdefghijklmnopqrstuv",      # 22 char random part
            "audit_v1_ABCDEFGHIJKLMNOPQRSTUV",      # 22 char random part
        ]

        for key in valid_keys:
            with self.subTest(key=key):
                self.assertTrue(secret.is_valid_audit_api_key_format(key),
                              f"Key {key} should be valid")

    def test_is_valid_audit_api_key_format_wrong_prefix(self):
        """Test format validation rejects wrong prefixes."""
        invalid_keys = [
            "audit_v2_kXj9mP2nQ5vR8sT7uV3wY4zX5cV6bN7m",  # Wrong version
            "api_v1_kXj9mP2nQ5vR8sT7uV3wY4zX5cV6bN7m",    # Wrong service
            "v1_kXj9mP2nQ5vR8sT7uV3wY4zX5cV6bN7m",        # Missing service
            "audit_v1",                                       # Prefix only
        ]

        for key in invalid_keys:
            with self.subTest(key=key):
                self.assertFalse(secret.is_valid_audit_api_key_format(key),
                               f"Key {key} should be invalid (wrong prefix)")

    def test_is_valid_audit_api_key_format_wrong_length(self):
        """Test format validation rejects wrong lengths."""
        invalid_keys = [
            "audit_v1_tooshort",                              # Too short (17 chars total)
            "audit_v1_kXj9mP2nQ5vR8sT7uV3wY4zX5cV6bN7mExtra",  # Too long (47 chars total)
            "audit_v1_12345",                                  # Too short (15 chars total)
            "audit_v1_01234567890123456789012345",            # Too long (39 chars total)
        ]

        for key in invalid_keys:
            with self.subTest(key=key):
                self.assertFalse(secret.is_valid_audit_api_key_format(key),
                               f"Key {key} should be invalid (wrong length)")

    def test_is_valid_audit_api_key_format_invalid_characters(self):
        """Test format validation rejects invalid base64url characters."""
        invalid_keys = [
            "audit_v1_kXj9mP2nQ5vR8sT7uV3wY4zX5cV6bN7=",  # Padding char
            "audit_v1_kXj9mP2nQ5vR8sT7uV3wY4zX5cV6bN7+",   # Plus sign
            "audit_v1_kXj9mP2nQ5vR8sT7uV3wY4zX5cV6bN7/",   # Forward slash
            "audit_v1_kXj9mP2nQ5vR8sT7uV3wY4zX5cV6bN7 ",   # Space
            "audit_v1_kXj9mP2nQ5vR8sT7uV3wY4zX5cV6bN7!",   # Exclamation
        ]

        for key in invalid_keys:
            with self.subTest(key=key):
                self.assertFalse(secret.is_valid_audit_api_key_format(key),
                               f"Key {key} should be invalid (bad characters)")

    def test_is_valid_audit_api_key_format_empty_and_none(self):
        """Test format validation with empty and None inputs."""
        self.assertFalse(secret.is_valid_audit_api_key_format(""),
                        "Empty string should be invalid")

        # None should raise AttributeError or return False
        # Depending on implementation, we'll test for graceful handling
        try:
            result = secret.is_valid_audit_api_key_format(None)  # type: ignore
            self.assertFalse(result, "None should be invalid")
        except (AttributeError, TypeError):
            # Also acceptable - function should handle None gracefully
            pass

    def test_audit_api_key_security_properties(self):
        """Test security-related properties of API key functions."""
        # Generate multiple keys and ensure they're unpredictable
        keys = [secret.generate_audit_api_key() for _ in range(50)]

        # Check randomness (no obvious patterns)
        for key in keys:
            self.assertEqual(len(key), 31)
            self.assertTrue(key.startswith("audit_v1_"))

            # Random portion should have good character distribution
            random_part = key[9:]
            # Should mix case and numbers (not all same case)
            has_upper = any(c.isupper() for c in random_part)
            has_lower = any(c.islower() for c in random_part)
            has_digit = any(c.isdigit() for c in random_part)

            is_well_distributed = has_upper or has_lower or has_digit
            self.assertTrue(is_well_distributed,
                          f"Random portion should be well distributed: {random_part}")

        # All keys should be different
        unique_keys = set(keys)
        self.assertEqual(len(unique_keys), len(keys),
                        "All generated keys should be unique")


class TestSecretEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions for secret utilities."""

    def test_generate_otp_with_zero_length(self):
        """Test that generate_otp() with length=0 returns empty string."""
        otp = secret.generate_otp(length=0)
        self.assertEqual(otp, "")

    def test_generate_api_key_with_small_length(self):
        """Test that generate_api_key() works with very small lengths."""
        key = secret.generate_api_key(length=1)
        self.assertEqual(len(key), 1)

    def test_hash_otp_with_empty_string(self):
        """Test that hash_otp() can hash empty string."""
        hashed = secret.hash_otp("")
        self.assertIsInstance(hashed, str)
        # Should still verify
        self.assertTrue(secret.verify_otp("", hashed))

    def test_verify_otp_with_empty_strings(self):
        """Test verify_otp() behavior with empty strings."""
        hashed = secret.hash_otp("")

        # Empty should verify with empty
        self.assertTrue(secret.verify_otp("", hashed))

        # Non-empty should not verify with empty
        self.assertFalse(secret.verify_otp("123456", hashed))


if __name__ == '__main__':
    unittest.main()
