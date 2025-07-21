"""
Migration Test Helpers

Utilities for testing the migration from campus.vault to campus.client.
Designed to work in environments both with and without database access.
"""

import os
import unittest
from unittest.mock import Mock, patch, MagicMock
from contextlib import contextmanager


class MigrationTestHelper:
    """Helper class for migration testing scenarios."""
    
    @staticmethod
    def has_vault_environment():
        """Check if vault database environment is available."""
        return bool(os.environ.get('VAULTDB_URI'))
    
    @staticmethod
    def has_mongodb_environment():
        """Check if MongoDB environment is available."""
        return bool(os.environ.get('MONGODB_URI'))
    
    @staticmethod
    def has_full_environment():
        """Check if full testing environment is available."""
        return (MigrationTestHelper.has_vault_environment() and 
                MigrationTestHelper.has_mongodb_environment())
    
    @staticmethod
    @contextmanager
    def mock_vault_environment():
        """Mock environment variables for testing without real databases."""
        mock_env = {
            'VAULTDB_URI': 'postgresql://test:test@localhost/test_vault',
            'MONGODB_URI': 'mongodb://test:test@localhost/test_mongo',
            'ENV': 'testing'
        }
        
        with patch.dict(os.environ, mock_env):
            yield
    
    @staticmethod
    @contextmanager
    def mock_client_environment():
        """Mock environment for client-based access."""
        mock_env = {
            'CAMPUS_VAULT_BASE_URL': 'http://localhost:8000',
            'CAMPUS_APPS_BASE_URL': 'http://localhost:9000', 
            'ENV': 'testing'
        }
        
        # Clear database URIs to ensure no direct access
        clear_vars = ['VAULTDB_URI', 'MONGODB_URI']
        
        with patch.dict(os.environ, mock_env, clear=False):
            for var in clear_vars:
                if var in os.environ:
                    del os.environ[var]
            yield


class MockVaultClient:
    """Mock vault client for testing client-based access patterns."""
    
    def __init__(self):
        self.vaults = {
            'storage': {
                'MONGODB_URI': 'mongodb://mocked:uri@localhost/test'
            },
            'apps': {
                'SECRET_KEY': 'mocked-secret-key'
            }
        }
    
    def __getitem__(self, vault_name):
        return MockVaultInstance(self.vaults.get(vault_name, {}))


class MockVaultInstance:
    """Mock vault instance for testing."""
    
    def __init__(self, secrets):
        self.secrets = secrets
    
    def get(self, key):
        if key not in self.secrets:
            raise KeyError(f"Secret '{key}' not found")
        return self.secrets[key]
    
    def set(self, key, value):
        self.secrets[key] = value
    
    def has(self, key):
        return key in self.secrets


class MockClientResource:
    """Mock ClientResource for testing authentication context migration."""
    
    def __init__(self, client_id="test-client", name="Test Client"):
        self.id = client_id
        self.name = name
        self.description = "Mock client for testing"


def skip_if_no_environment(test_func):
    """Decorator to skip tests if full environment is not available."""
    def wrapper(self):
        if not MigrationTestHelper.has_full_environment():
            self.skipTest("Requires full database environment (VAULTDB_URI and MONGODB_URI)")
        return test_func(self)
    return wrapper


def skip_if_no_vault(test_func):
    """Decorator to skip tests if vault environment is not available."""
    def wrapper(self):
        if not MigrationTestHelper.has_vault_environment():
            self.skipTest("Requires vault database environment (VAULTDB_URI)")
        return test_func(self)
    return wrapper


def mock_only_test(test_func):
    """Decorator for tests that only run with mocked dependencies."""
    def wrapper(self):
        if MigrationTestHelper.has_full_environment():
            self.skipTest("This test only runs in mocked environment")
        return test_func(self)
    return wrapper


class MigrationTestCase(unittest.TestCase):
    """Base test case with migration testing utilities."""
    
    def setUp(self):
        self.helper = MigrationTestHelper()
        self.mock_vault_client = MockVaultClient()
    
    def assert_equivalent_results(self, legacy_result, client_result, message=None):
        """Assert that legacy and client approaches produce equivalent results."""
        self.assertEqual(legacy_result, client_result, 
                        message or "Legacy and client results should be equivalent")
    
    def assert_no_database_env_required(self, func, *args, **kwargs):
        """Assert that a function works without database environment variables."""
        # Temporarily remove database env vars
        vault_uri = os.environ.pop('VAULTDB_URI', None)
        mongo_uri = os.environ.pop('MONGODB_URI', None)
        
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            if 'VAULTDB_URI' in str(e) or 'MONGODB_URI' in str(e):
                self.fail(f"Function {func.__name__} still requires database environment variables: {e}")
            raise
        finally:
            # Restore environment variables
            if vault_uri:
                os.environ['VAULTDB_URI'] = vault_uri
            if mongo_uri:
                os.environ['MONGODB_URI'] = mongo_uri

import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch, MagicMock
from typing import Dict, Any, Optional


class MigrationTestMixin:
    """Mixin class providing migration testing utilities."""

    def setUp_migration_env(self):
        """Set up test environment for migration testing."""
        self.original_env = dict(os.environ)
        # Clear any existing vault-related environment variables
        self.clear_vault_env()

    def tearDown_migration_env(self):
        """Clean up migration test environment."""
        os.environ.clear()
        os.environ.update(self.original_env)

    def clear_vault_env(self):
        """Clear all vault-related environment variables."""
        vault_env_vars = [
            'VAULTDB_URI',
            'MONGODB_URI', 
            'CAMPUS_VAULT_BASE_URL',
            'CAMPUS_APPS_BASE_URL'
        ]
        for var in vault_env_vars:
            os.environ.pop(var, None)

    def set_legacy_env(self):
        """Set up environment for legacy vault access."""
        os.environ['VAULTDB_URI'] = 'postgresql://test:test@localhost/test_vault'
        os.environ['MONGODB_URI'] = 'mongodb://test:test@localhost/test_mongo'

    def set_client_env(self):
        """Set up environment for client-based vault access."""
        os.environ['CAMPUS_VAULT_BASE_URL'] = 'http://localhost:8000'
        os.environ['CAMPUS_APPS_BASE_URL'] = 'http://localhost:8001'


@contextmanager
def mock_legacy_vault_access(secret_values: Dict[str, str]):
    """Mock legacy vault database access.
    
    Args:
        secret_values: Dictionary mapping secret keys to values
    """
    with patch('campus.vault.db.get_connection') as mock_conn:
        mock_cursor = MagicMock()
        
        def mock_fetchone():
            # Return the appropriate secret value based on the query
            return (list(secret_values.values())[0],) if secret_values else None
            
        mock_cursor.fetchone.return_value = mock_fetchone()
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        
        yield mock_conn


@contextmanager 
def mock_client_vault_access(vault_data: Dict[str, Dict[str, str]]):
    """Mock client-based vault access.
    
    Args:
        vault_data: Dictionary mapping vault names to their secret key-value pairs
        Example: {'storage': {'MONGODB_URI': 'mongodb://...'}}
    """
    with patch('campus.client.vault.vault') as mock_vault:
        def mock_vault_getitem(vault_name):
            mock_vault_instance = MagicMock()
            vault_secrets = vault_data.get(vault_name, {})
            mock_vault_instance.get.side_effect = lambda key: vault_secrets.get(key)
            return mock_vault_instance
            
        mock_vault.__getitem__.side_effect = mock_vault_getitem
        yield mock_vault


@contextmanager
def mock_client_http_responses(responses: Dict[str, Any]):
    """Mock HTTP responses for client requests.
    
    Args:
        responses: Dictionary mapping URL patterns to response data
    """
    with patch('requests.get') as mock_get, \
         patch('requests.post') as mock_post, \
         patch('requests.delete') as mock_delete:
        
        def create_mock_response(data, status_code=200):
            mock_response = MagicMock()
            mock_response.status_code = status_code
            mock_response.json.return_value = data
            return mock_response
        
        # Configure mock responses
        for url_pattern, response_data in responses.items():
            if isinstance(response_data, dict) and 'status_code' in response_data:
                mock_response = create_mock_response(
                    response_data.get('data', {}), 
                    response_data['status_code']
                )
            else:
                mock_response = create_mock_response(response_data)
            
            # Set up responses for different HTTP methods
            mock_get.return_value = mock_response
            mock_post.return_value = mock_response
            mock_delete.return_value = mock_response
        
        yield {
            'get': mock_get,
            'post': mock_post, 
            'delete': mock_delete
        }


class MigrationValidationHelper:
    """Helper class for validating migration correctness."""

    @staticmethod
    def validate_secret_retrieval_equivalence(
        legacy_result: Any, 
        client_result: Any,
        test_case: unittest.TestCase
    ):
        """Validate that legacy and client approaches return equivalent results."""
        test_case.assertEqual(
            legacy_result, 
            client_result,
            f"Legacy result {legacy_result} != Client result {client_result}"
        )

    @staticmethod
    def validate_no_database_environment_vars(test_case: unittest.TestCase):
        """Validate that no direct database environment variables are required."""
        prohibited_vars = ['VAULTDB_URI', 'MONGODB_URI']
        for var in prohibited_vars:
            test_case.assertNotIn(
                var, 
                os.environ,
                f"Prohibited environment variable {var} should not be required"
            )

    @staticmethod
    def validate_service_discovery_only(test_case: unittest.TestCase):
        """Validate that only service discovery environment variables are used."""
        required_service_vars = ['CAMPUS_VAULT_BASE_URL']
        for var in required_service_vars:
            test_case.assertIn(
                var,
                os.environ, 
                f"Required service discovery variable {var} should be present"
            )

    @staticmethod
    def validate_error_consistency(
        legacy_error: Exception,
        client_error: Exception, 
        test_case: unittest.TestCase
    ):
        """Validate that error handling is consistent between approaches."""
        test_case.assertEqual(
            type(legacy_error).__name__,
            type(client_error).__name__,
            f"Error types should match: {type(legacy_error)} vs {type(client_error)}"
        )


class MigrationTestRunner:
    """Utility for running migration tests in different modes."""

    def __init__(self, test_case):
        self.test_case = test_case

    def clear_vault_env(self):
        """Clear all vault-related environment variables."""
        vault_env_vars = [
            'VAULTDB_URI',
            'MONGODB_URI', 
            'CAMPUS_VAULT_BASE_URL',
            'CAMPUS_APPS_BASE_URL'
        ]
        for var in vault_env_vars:
            os.environ.pop(var, None)

    def set_legacy_env(self):
        """Set up environment for legacy vault access."""
        os.environ['VAULTDB_URI'] = 'postgresql://test:test@localhost/test_vault'
        os.environ['MONGODB_URI'] = 'mongodb://test:test@localhost/test_mongo'

    def set_client_env(self):
        """Set up environment for client-based vault access."""
        os.environ['CAMPUS_VAULT_BASE_URL'] = 'http://localhost:8000'
        os.environ['CAMPUS_APPS_BASE_URL'] = 'http://localhost:8001'

    def run_dual_mode_test(self, test_func, test_data: Dict[str, Any]):
        """Run a test in both legacy and client modes.
        
        Args:
            test_func: Function that takes (mode, test_data) and runs the test
            test_data: Data needed for the test
        """
        # Run in legacy mode
        self.clear_vault_env()
        self.set_legacy_env()
        
        legacy_result = test_func('legacy', test_data)
        
        # Run in client mode  
        self.clear_vault_env()
        self.set_client_env()
        
        client_result = test_func('client', test_data)
        
        # Validate equivalence
        MigrationValidationHelper.validate_secret_retrieval_equivalence(
            legacy_result, 
            client_result,
            self.test_case
        )
        
        return legacy_result, client_result


def create_test_vault_data() -> Dict[str, Dict[str, str]]:
    """Create test vault data for migration tests."""
    return {
        'storage': {
            'MONGODB_URI': 'mongodb://test:test@localhost/test_storage',
            'REDIS_URI': 'redis://test:test@localhost/test_redis'
        },
        'apps': {
            'SECRET_KEY': 'test-secret-key-123',
            'DATABASE_URL': 'postgresql://test:test@localhost/test_apps'
        },
        'auth': {
            'JWT_SECRET': 'jwt-secret-key-456',
            'OAUTH_CLIENT_SECRET': 'oauth-secret-789'
        }
    }


def create_test_client_data() -> Dict[str, Any]:
    """Create test client data for migration tests."""
    return {
        'test-client-1': {
            'id': 'test-client-1',
            'name': 'Test Client 1',
            'secret_hash': 'hashed-secret-1'
        },
        'test-client-2': {
            'id': 'test-client-2', 
            'name': 'Test Client 2',
            'secret_hash': 'hashed-secret-2'
        }
    }
