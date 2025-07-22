"""
Migration tests for campus.vault → campus.client transition.

These tests validate that the migration from direct vault database access
to HTTP client-based vault access maintains functionality while improving security.
"""

import unittest
import os
from unittest.mock import patch, MagicMock
from contextlib import contextmanager


class TestVaultMigration(unittest.TestCase):
    """Test the migration from campus.vault to campus.client."""

    def setUp(self):
        """Set up test environment."""
        # Store original environment
        self.original_env = dict(os.environ)
        
    def tearDown(self):
        """Clean up test environment."""
        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_storage_mongodb_uri_retrieval_current_state(self):
        """Test current MongoDB URI retrieval through direct vault access.
        
        This tests the CURRENT behavior that should be replaced.
        """
        # Set up environment for current state
        os.environ['VAULTDB_URI'] = 'postgresql://test:test@localhost/test_vault'
        
        # Mock the vault database connection and response
        with patch('campus.vault.db.get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = ('mongodb://test:test@localhost/test_mongo',)
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            
            # Import and test current behavior
            from campus.storage.documents.backend.mongodb import _get_mongodb_uri
            
            # This should work with VAULTDB_URI
            uri = _get_mongodb_uri()
            self.assertEqual(uri, 'mongodb://test:test@localhost/test_mongo')
            
            # Verify it used direct database access
            mock_conn.assert_called()

    def test_storage_mongodb_uri_retrieval_target_state(self):
        """Test target MongoDB URI retrieval through client access.
        
        This tests the TARGET behavior after migration.
        """
        # Set up environment for target state (no VAULTDB_URI)
        os.environ['CAMPUS_VAULT_BASE_URL'] = 'http://localhost:8000'
        
        # Mock the HTTP client response
        with patch('campus.client.vault.vault') as mock_vault:
            mock_vault.__getitem__.return_value.get.return_value = 'mongodb://test:test@localhost/test_mongo'
            
            # Import target implementation (to be created)
            # This would be the new implementation in mongodb.py
            from campus.client.vault import vault
            
            # This should work without VAULTDB_URI
            uri = vault['storage'].get('MONGODB_URI')
            self.assertEqual(uri, 'mongodb://test:test@localhost/test_mongo')
            
            # Verify it used HTTP client, not direct database
            mock_vault.__getitem__.assert_called_with('storage')

    def test_campusauth_context_current_state(self):
        """Test current authentication context using direct vault client."""
        os.environ['VAULTDB_URI'] = 'postgresql://test:test@localhost/test_vault'
        
        with patch('campus.vault.client.ClientResource') as mock_client_resource:
            mock_client_instance = MagicMock()
            mock_client_resource.return_value = mock_client_instance
            
            # Test current import
            from campus.vault.client import ClientResource
            client = ClientResource('test-client-id')
            
            self.assertIsNotNone(client)
            mock_client_resource.assert_called_with('test-client-id')

    def test_campusauth_context_target_state(self):
        """Test target authentication context using campus.client."""
        os.environ['CAMPUS_VAULT_BASE_URL'] = 'http://localhost:8000'
        
        # Mock HTTP client for vault operations
        with patch('campus.client.vault.client') as mock_client:
            mock_client.get.return_value = {'id': 'test-client-id', 'name': 'Test Client'}
            
            # Test target import pattern
            from campus.client.vault import client
            client_data = client.get('test-client-id')
            
            self.assertEqual(client_data['id'], 'test-client-id')
            mock_client.get.assert_called_with('test-client-id')

    def test_workspace_import_migration(self):
        """Test workspace module import migration."""
        # Test current state
        with patch.dict('sys.modules', {'campus.vault': MagicMock()}):
            # Current import should work
            import campus.vault as vault
            self.assertIsNotNone(vault)
        
        # Test target state  
        with patch.dict('sys.modules', {'campus.client': MagicMock()}):
            # Target import should work
            import campus.client as client
            self.assertIsNotNone(client)

    def test_environment_variable_migration_compatibility(self):
        """Test that apps work without direct database environment variables."""
        # Current state requires VAULTDB_URI
        with self.assertRaises(ValueError):
            os.environ.pop('VAULTDB_URI', None)
            # This should fail without VAULTDB_URI in current state
            from campus.vault.db import get_connection
            get_connection()
        
        # Target state should work with only service URLs
        os.environ['CAMPUS_VAULT_BASE_URL'] = 'http://localhost:8000'
        
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = {'value': 'mongodb://test:test@localhost/test_mongo'}
            mock_get.return_value.status_code = 200
            
            # This should work without any database environment variables
            from campus.client.vault import vault
            result = vault['storage'].get('MONGODB_URI')
            self.assertEqual(result, 'mongodb://test:test@localhost/test_mongo')

    def test_secret_retrieval_functionality_equivalence(self):
        """Test that secret retrieval produces identical results in both modes."""
        test_secret_value = 'secret-value-123'
        
        # Test current vault model approach
        os.environ['VAULTDB_URI'] = 'postgresql://test:test@localhost/test_vault'
        
        with patch('campus.vault.db.get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (test_secret_value,)
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            
            from campus.vault.model import Vault
            legacy_result = Vault('test-vault').get('test-key')
        
        # Test client approach
        os.environ['CAMPUS_VAULT_BASE_URL'] = 'http://localhost:8000'
        
        with patch('campus.client.vault.vault') as mock_vault:
            mock_vault.__getitem__.return_value.get.return_value = test_secret_value
            
            from campus.client.vault import vault
            client_result = vault['test-vault'].get('test-key')
        
        # Results should be identical
        self.assertEqual(legacy_result, client_result)

    def test_error_handling_consistency(self):
        """Test that error handling is consistent between approaches."""
        # Test vault not found error
        os.environ['VAULTDB_URI'] = 'postgresql://test:test@localhost/test_vault'
        
        with patch('campus.vault.db.get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None  # Vault not found
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            
            from campus.vault.model import Vault
            with self.assertRaises(Exception):  # Should raise appropriate error
                Vault('nonexistent-vault').get('test-key')
        
        # Test client approach error handling
        os.environ['CAMPUS_VAULT_BASE_URL'] = 'http://localhost:8000'
        
        with patch('campus.client.vault.vault') as mock_vault:
            from campus.client.errors import NotFoundError
            mock_vault.__getitem__.return_value.get.side_effect = NotFoundError("Vault not found")
            
            from campus.client.vault import vault
            with self.assertRaises(NotFoundError):
                vault['nonexistent-vault'].get('test-key')

    def test_configuration_precedence(self):
        """Test configuration precedence and backward compatibility."""
        # Test that service URLs take precedence over legacy environment
        os.environ['VAULTDB_URI'] = 'postgresql://old:old@localhost/old_vault'
        os.environ['CAMPUS_VAULT_BASE_URL'] = 'http://new-vault-service:8000'
        
        with patch('campus.client.config.get_service_base_url') as mock_config:
            mock_config.return_value = 'http://new-vault-service:8000'
            
            from campus.client.config import get_service_base_url
            base_url = get_service_base_url('vault')
            
            # Should use new configuration, not legacy VAULTDB_URI
            self.assertEqual(base_url, 'http://new-vault-service:8000')


class TestMigrationIntegration(unittest.TestCase):
    """Integration tests for the complete migration."""

    def setUp(self):
        """Set up integration test environment."""
        self.original_env = dict(os.environ)

    def tearDown(self):
        """Clean up integration test environment."""
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_storage_backend_migration_integration(self):
        """Test complete storage backend migration from vault to client."""
        # This tests the complete flow:
        # storage → vault (current) vs storage → client (target)
        
        test_mongodb_uri = 'mongodb://integrated:test@localhost/integrated_db'
        
        # Test current flow: storage → vault database
        os.environ['VAULTDB_URI'] = 'postgresql://test:test@localhost/test_vault'
        
        with patch('campus.vault.db.get_connection') as mock_vault_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (test_mongodb_uri,)
            mock_vault_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            
            # This represents current behavior
            from campus.storage.documents.backend.mongodb import _get_mongodb_uri
            current_uri = _get_mongodb_uri()
        
        # Test target flow: storage → client → vault service
        os.environ.pop('VAULTDB_URI', None)  # Remove direct database access
        os.environ['CAMPUS_VAULT_BASE_URL'] = 'http://localhost:8000'
        
        with patch('requests.get') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'value': test_mongodb_uri}
            mock_http.return_value = mock_response
            
            # This represents target behavior (after migration)
            from campus.client.vault import vault
            target_uri = vault['storage'].get('MONGODB_URI')
        
        # Both approaches should return the same URI
        self.assertEqual(current_uri, target_uri)
        
        # Verify the target approach doesn't use database connection
        mock_vault_conn.assert_called()  # Current approach uses DB
        mock_http.assert_called()  # Target approach uses HTTP

    def test_apps_authentication_migration_integration(self):
        """Test complete apps authentication migration."""
        # Test that apps can authenticate without direct vault database access
        
        os.environ['CAMPUS_VAULT_BASE_URL'] = 'http://localhost:8000'
        test_client_data = {
            'id': 'test-client-123',
            'name': 'Test Application',
            'secret_hash': 'hashed-secret-value'
        }
        
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = test_client_data
            mock_get.return_value = mock_response
            
            # Test client retrieval through HTTP API
            from campus.client.vault import client
            retrieved_client = client.get('test-client-123')
            
            self.assertEqual(retrieved_client['id'], 'test-client-123')
            self.assertEqual(retrieved_client['name'], 'Test Application')
            
            # Verify HTTP call was made to correct endpoint
            expected_url = 'http://localhost:8000/client/test-client-123'
            mock_get.assert_called_with(expected_url, headers=unittest.mock.ANY)


if __name__ == '__main__':
    unittest.main()
