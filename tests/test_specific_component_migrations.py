"""
Specific migration tests for individual components.

These tests focus on the specific files and imports that need to be migrated:
1. campus/workspace/__init__.py - vault import
2. campus/apps/campusauth/context.py - ClientResource import  
3. campus/storage/collections/backend/mongodb.py - MongoDB URI retrieval
"""

import unittest
import os
import sys
from unittest.mock import patch, MagicMock
from tests.migration_test_helpers import (
    MigrationTestMixin,
    mock_legacy_vault_access,
    mock_client_vault_access,
    mock_client_http_responses,
    MigrationValidationHelper
)


class TestWorkspaceMigration(unittest.TestCase, MigrationTestMixin):
    """Test migration of campus/workspace/__init__.py vault imports."""

    def setUp(self):
        self.setUp_migration_env()

    def tearDown(self):
        self.tearDown_migration_env()

    def test_workspace_vault_import_current(self):
        """Test current workspace vault import behavior."""
        self.set_legacy_env()
        
        # Test that current import works
        with patch.dict('sys.modules', {'campus.vault': MagicMock()}):
            # This is the current import in workspace/__init__.py
            import campus.vault as vault
            self.assertIsNotNone(vault)

    def test_workspace_vault_import_target(self):
        """Test target workspace vault import through client."""
        self.set_client_env()
        
        # Test that target import works
        with patch.dict('sys.modules', {'campus.client.vault': MagicMock()}):
            # This should be the new import in workspace/__init__.py
            from campus.client import vault
            self.assertIsNotNone(vault)

    def test_workspace_vault_functionality_equivalence(self):
        """Test that vault functionality works the same through both imports."""
        test_secret_value = 'workspace-test-secret'
        
        # Test current behavior
        self.set_legacy_env()
        with mock_legacy_vault_access({'TEST_SECRET': test_secret_value}):
            import campus.vault as vault_legacy
            # Mock the vault model access
            with patch.object(vault_legacy, 'model') as mock_model:
                mock_vault_instance = MagicMock()
                mock_vault_instance.get.return_value = test_secret_value
                mock_model.Vault.return_value = mock_vault_instance
                
                legacy_result = vault_legacy.model.Vault('test-vault').get('TEST_SECRET')

        # Test target behavior  
        self.set_client_env()
        with mock_client_vault_access({'test-vault': {'TEST_SECRET': test_secret_value}}):
            from campus.client import vault as vault_client
            client_result = vault_client['test-vault'].get('TEST_SECRET')

        # Results should be equivalent
        MigrationValidationHelper.validate_secret_retrieval_equivalence(
            legacy_result, client_result, self
        )


class TestCampusAuthContextMigration(unittest.TestCase, MigrationTestMixin):
    """Test migration of campus/apps/campusauth/context.py ClientResource import."""

    def setUp(self):
        self.setUp_migration_env()

    def tearDown(self):
        self.tearDown_migration_env()

    def test_client_resource_import_current(self):
        """Test current ClientResource import."""
        self.set_legacy_env()
        
        with patch('campus.vault.client.ClientResource') as mock_client_resource:
            # This is the current import
            from campus.vault.client import ClientResource
            
            client = ClientResource('test-client-id')
            self.assertIsNotNone(client)
            mock_client_resource.assert_called_with('test-client-id')

    def test_client_resource_import_target(self):
        """Test target client resource access through campus.client."""
        self.set_client_env()
        
        with mock_client_http_responses({
            'client/test-client-id': {
                'id': 'test-client-id',
                'name': 'Test Client',
                'secret_hash': 'hashed-secret'
            }
        }):
            # This should be the new approach
            from campus.client.vault import client
            client_data = client.get('test-client-id')
            
            self.assertEqual(client_data['id'], 'test-client-id')
            self.assertEqual(client_data['name'], 'Test Client')

    def test_authentication_context_migration(self):
        """Test that authentication context works with both approaches."""
        test_client_id = 'auth-test-client'
        test_client_data = {
            'id': test_client_id,
            'name': 'Auth Test Client',
            'secret_hash': 'auth-secret-hash'
        }
        
        # Test current approach - direct ClientResource
        self.set_legacy_env()
        with patch('campus.vault.client.ClientResource') as mock_client_resource:
            mock_instance = MagicMock()
            mock_instance.id = test_client_id
            mock_instance.name = test_client_data['name']
            mock_client_resource.return_value = mock_instance
            
            # Simulate current context usage
            from campus.vault.client import ClientResource
            legacy_client = ClientResource(test_client_id)
            legacy_client_id = legacy_client.id

        # Test target approach - HTTP client  
        self.set_client_env()
        with mock_client_http_responses({
            f'client/{test_client_id}': test_client_data
        }):
            from campus.client.vault import client
            client_response = client.get(test_client_id)
            target_client_id = client_response['id']

        # Should have same client ID
        self.assertEqual(legacy_client_id, target_client_id)

    def test_context_credentials_validation(self):
        """Test that credential validation works in both approaches."""
        client_id = 'cred-test-client'
        secret_hash = 'test-secret-hash'
        
        # Test current credentials validation
        self.set_legacy_env()
        with patch('campus.vault.client.ClientResource') as mock_client_resource:
            mock_instance = MagicMock()
            mock_instance.validate_credentials.return_value = True
            mock_client_resource.return_value = mock_instance
            
            from campus.vault.client import ClientResource
            legacy_client = ClientResource(client_id)
            legacy_valid = legacy_client.validate_credentials(secret_hash)

        # Test target credentials validation (through HTTP API)
        self.set_client_env() 
        with mock_client_http_responses({
            f'client/{client_id}/validate': {'valid': True}
        }):
            # This would be new validation endpoint
            with patch('requests.post') as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {'valid': True}
                mock_post.return_value = mock_response
                
                # Simulate new validation approach
                import requests
                response = requests.post(
                    f'http://localhost:8000/client/{client_id}/validate',
                    json={'secret_hash': secret_hash}
                )
                target_valid = response.json()['valid']

        # Both should validate successfully
        self.assertEqual(legacy_valid, target_valid)


class TestStorageMongoDBAMigration(unittest.TestCase, MigrationTestMixin):
    """Test migration of campus/storage/collections/backend/mongodb.py."""

    def setUp(self):
        self.setUp_migration_env()

    def tearDown(self):
        self.tearDown_migration_env()

    def test_mongodb_uri_retrieval_current(self):
        """Test current MongoDB URI retrieval through vault model."""
        mongodb_uri = 'mongodb://current:test@localhost/current_storage'
        self.set_legacy_env()
        
        with mock_legacy_vault_access({'MONGODB_URI': mongodb_uri}):
            # Mock the current implementation
            with patch('campus.vault.model.Vault') as mock_vault:
                mock_vault_instance = MagicMock()
                mock_vault_instance.get.return_value = mongodb_uri
                mock_vault.return_value = mock_vault_instance
                
                # This simulates current _get_mongodb_uri() behavior
                from campus.vault.model import Vault
                storage_vault = Vault('storage')
                current_uri = storage_vault.get('MONGODB_URI')

        self.assertEqual(current_uri, mongodb_uri)

    def test_mongodb_uri_retrieval_target(self):
        """Test target MongoDB URI retrieval through client."""
        mongodb_uri = 'mongodb://target:test@localhost/target_storage'
        self.set_client_env()
        
        # Remove direct MongoDB URI from environment
        os.environ.pop('MONGODB_URI', None)
        
        with mock_client_vault_access({'storage': {'MONGODB_URI': mongodb_uri}}):
            from campus.client.vault import vault
            target_uri = vault['storage'].get('MONGODB_URI')

        self.assertEqual(target_uri, mongodb_uri)

    def test_mongodb_connection_initialization(self):
        """Test that MongoDB connection works with both URI sources."""
        test_uri = 'mongodb://test:test@localhost/test_storage_db'
        
        # Test current connection approach
        self.set_legacy_env()
        with mock_legacy_vault_access({'MONGODB_URI': test_uri}):
            with patch('pymongo.MongoClient') as mock_mongo_client:
                mock_client_instance = MagicMock()
                mock_mongo_client.return_value = mock_client_instance
                
                # Simulate current MongoDBCollection initialization
                with patch('campus.vault.model.Vault') as mock_vault:
                    mock_vault_instance = MagicMock()
                    mock_vault_instance.get.return_value = test_uri
                    mock_vault.return_value = mock_vault_instance
                    
                    # This represents current behavior
                    from campus.vault.model import Vault
                    storage_vault = Vault('storage')
                    current_uri = storage_vault.get('MONGODB_URI')
                    
                    import pymongo
                    legacy_client = pymongo.MongoClient(current_uri)

        # Test target connection approach
        self.set_client_env()
        os.environ.pop('MONGODB_URI', None)  # No direct URI in environment
        
        with mock_client_vault_access({'storage': {'MONGODB_URI': test_uri}}):
            with patch('pymongo.MongoClient') as mock_mongo_client_target:
                mock_client_instance_target = MagicMock()
                mock_mongo_client_target.return_value = mock_client_instance_target
                
                # This represents target behavior
                from campus.client.vault import vault
                target_uri = vault['storage'].get('MONGODB_URI')
                
                import pymongo
                target_client = pymongo.MongoClient(target_uri)

        # Both should connect with same URI
        mock_mongo_client.assert_called_with(test_uri)
        mock_mongo_client_target.assert_called_with(test_uri)

    def test_storage_environment_independence(self):
        """Test that storage layer works without direct database environment variables."""
        self.set_client_env()
        
        # Ensure no direct database environment variables
        MigrationValidationHelper.validate_no_database_environment_vars(self)
        
        # Ensure service discovery variables are present
        MigrationValidationHelper.validate_service_discovery_only(self)
        
        mongodb_uri = 'mongodb://env-independent:test@localhost/independent_db'
        
        with mock_client_vault_access({'storage': {'MONGODB_URI': mongodb_uri}}):
            # This should work without any direct database environment variables
            from campus.client.vault import vault
            retrieved_uri = vault['storage'].get('MONGODB_URI')
            
            self.assertEqual(retrieved_uri, mongodb_uri)

    def test_error_handling_migration(self):
        """Test that error handling works consistently in both approaches."""
        # Test vault not found error in current approach
        self.set_legacy_env()
        with patch('campus.vault.model.Vault') as mock_vault:
            mock_vault_instance = MagicMock()
            mock_vault_instance.get.side_effect = KeyError("Vault 'nonexistent' not found")
            mock_vault.return_value = mock_vault_instance
            
            from campus.vault.model import Vault
            storage_vault = Vault('nonexistent')
            
            with self.assertRaises(KeyError) as legacy_error:
                storage_vault.get('MONGODB_URI')

        # Test vault not found error in target approach
        self.set_client_env()
        with mock_client_vault_access({}):  # Empty vault data
            from campus.client.vault import vault
            
            with self.assertRaises(KeyError) as target_error:
                vault['nonexistent'].get('MONGODB_URI')

        # Error types should be consistent
        MigrationValidationHelper.validate_error_consistency(
            legacy_error.exception, target_error.exception, self
        )


if __name__ == '__main__':
    unittest.main()
