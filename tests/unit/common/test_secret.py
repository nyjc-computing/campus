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
        
        decoded_user, decoded_pass = secret.decode_http_basic_auth(with_prefix)
        
        self.assertEqual(username, decoded_user)
        self.assertEqual(password, decoded_pass)
    
    def test_http_basic_auth_with_special_characters(self):
        """Test HTTP Basic Auth with special characters in credentials."""
        test_cases = [
            ("user@example.com", "p@ss:w0rd!"),
            ("user", "password with spaces"),
            ("user:name", "pass:word"),
            ("unicode_user", "пароль"),  # Unicode password
        ]
        
        for username, password in test_cases:
            with self.subTest(username=username, password=password):
                encoded = secret.encode_http_basic_auth(username, password)
                decoded_user, decoded_pass = secret.decode_http_basic_auth(encoded)
                
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
