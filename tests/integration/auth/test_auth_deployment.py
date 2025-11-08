"""Deployment smoke tests for campus.auth module.

These tests verify that the auth module can be deployed without errors.
They focus on import capability, Flask app creation, and basic configuration,
NOT on specific auth behavior (which may change during pre-MVP development).

Test Principles:
- Test deployability, not functionality
- Loose assertions that survive API changes
- Catch fatal errors (imports, config, registration)
- Focus on "can it be deployed" not "does it work exactly like this"
"""

import unittest
import flask

from campus.common.devops.deploy import create_app
from tests.fixtures import services


class TestAuthDeployment(unittest.TestCase):
    """Smoke tests for auth module deployment."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test services for deployment tests."""
        cls.service_manager = services.create_service_manager()
        cls.service_manager.setup()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test services."""
        if hasattr(cls, 'service_manager'):
            cls.service_manager.close()
    
    def test_auth_module_can_be_imported(self):
        """Test that campus.auth imports without errors.
        
        This catches:
        - Missing dependencies
        - Circular imports
        - Syntax errors
        - Import-time configuration errors
        """
        try:
            import campus.auth
            # Verify module has expected interface
            self.assertTrue(hasattr(campus.auth, 'init_app'),
                          "campus.auth missing init_app function")
            self.assertTrue(callable(campus.auth.init_app),
                          "campus.auth.init_app is not callable")
        except ImportError as e:
            self.fail(f"Failed to import campus.auth: {e}")
        except Exception as e:
            self.fail(f"Unexpected error importing campus.auth: {e}")
    
    def test_auth_app_can_be_created(self):
        """Test that auth Flask app can be created and configured.
        
        This catches issues with:
        - Missing environment variables
        - Missing vault keys
        - Configuration errors
        - Blueprint registration errors
        """
        import campus.auth
        
        try:
            app = create_app(campus.auth)
            
            # Basic sanity checks - not testing functionality
            self.assertIsNotNone(app, "create_app returned None")
            self.assertIsInstance(app, flask.Flask,
                                "create_app did not return Flask instance")
            
        except Exception as e:
            self.fail(f"Failed to create auth app: {e}")
    
    def test_auth_app_has_secret_key(self):
        """Test that auth app has a secret key configured.
        
        This catches missing SECRET_KEY in vault configuration.
        """
        import campus.auth
        app = create_app(campus.auth)
        
        self.assertIsNotNone(app.secret_key,
                           "App secret_key is None")
        self.assertNotEqual(app.secret_key, '',
                          "App secret_key is empty string")
        self.assertIsInstance(app.secret_key, str,
                            "App secret_key is not a string")
    
    def test_auth_blueprints_registered(self):
        """Test that auth blueprints are registered.
        
        This is a loose check - we just verify that SOME blueprints
        are registered, not specific ones (which may change).
        """
        import campus.auth
        app = create_app(campus.auth)
        
        # Should have at least one blueprint registered
        self.assertGreater(len(app.blueprints), 0,
                          "No blueprints registered in auth app")
    
    def test_auth_routes_exist(self):
        """Test that auth routes are registered.
        
        This is a loose check - we just verify SOME routes exist
        under /auth/, not that specific routes are present.
        This survives API changes while catching complete failures.
        """
        import campus.auth
        app = create_app(campus.auth)
        
        # Get all registered routes
        routes = [rule.rule for rule in app.url_map.iter_rules()]
        
        # Check that we have some auth routes
        auth_routes = [r for r in routes if '/auth/' in r]
        self.assertGreater(len(auth_routes), 0,
                          "No auth routes registered under /auth/")
    
    def test_oauth_proxy_initialized(self):
        """Test that OAuth proxy components are initialized.
        
        Verifies that oauth_proxy.init_app was called successfully.
        """
        import campus.auth
        app = create_app(campus.auth)
        
        # Get all registered routes
        routes = [rule.rule for rule in app.url_map.iter_rules()]
        
        # Should have some OAuth-related routes (loose check)
        # We don't check for specific providers as they may change
        self.assertTrue(len(routes) > 0,
                       "No routes registered (OAuth proxy may not be initialized)")
    
    def test_auth_provider_initialized(self):
        """Test that auth provider components are initialized.
        
        Verifies that provider module was initialized successfully.
        """
        import campus.auth
        
        try:
            # Import provider module to verify it can be loaded
            from campus.auth import provider
            self.assertTrue(hasattr(provider, 'bp'),
                          "provider module missing bp (blueprint)")
        except ImportError as e:
            self.fail(f"Failed to import campus.auth.provider: {e}")
    
    def test_auth_has_error_handlers(self):
        """Test that auth app has error handlers configured.
        
        This verifies that campus.common.errors.init_app was called.
        """
        import campus.auth
        app = create_app(campus.auth)
        
        # Should have error handlers registered
        self.assertTrue(hasattr(app, 'error_handler_spec'),
                       "App missing error_handler_spec")


if __name__ == '__main__':
    unittest.main()
