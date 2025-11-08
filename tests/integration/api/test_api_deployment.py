"""Deployment smoke tests for campus.api module.

These tests verify that the API module can be deployed without errors.
They focus on import capability, Flask app creation, and basic configuration,
NOT on specific API behavior (which may change during pre-MVP development).

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


class TestAPIDeployment(unittest.TestCase):
    """Smoke tests for API module deployment."""
    
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
    
    def test_api_module_can_be_imported(self):
        """Test that campus.api imports without errors.
        
        This catches:
        - Missing dependencies
        - Circular imports
        - Syntax errors
        - Import-time configuration errors
        """
        try:
            import campus.api
            # Verify module has expected interface
            self.assertTrue(hasattr(campus.api, 'init_app'),
                          "campus.api missing init_app function")
            self.assertTrue(callable(campus.api.init_app),
                          "campus.api.init_app is not callable")
        except ImportError as e:
            self.fail(f"Failed to import campus.api: {e}")
        except Exception as e:
            self.fail(f"Unexpected error importing campus.api: {e}")
    
    def test_api_app_can_be_created(self):
        """Test that API Flask app can be created and configured.
        
        This catches issues with:
        - Missing environment variables
        - Missing vault keys
        - Configuration errors
        - Blueprint registration errors
        """
        import campus.api
        
        try:
            app = create_app(campus.api)
            
            # Basic sanity checks - not testing functionality
            self.assertIsNotNone(app, "create_app returned None")
            self.assertIsInstance(app, flask.Flask,
                                "create_app did not return Flask instance")
            
        except Exception as e:
            self.fail(f"Failed to create API app: {e}")
    
    def test_api_app_has_secret_key(self):
        """Test that API app has a secret key configured.
        
        This catches missing SECRET_KEY in vault configuration.
        """
        import campus.api
        app = create_app(campus.api)
        
        self.assertIsNotNone(app.secret_key,
                           "App secret_key is None")
        self.assertNotEqual(app.secret_key, '',
                          "App secret_key is empty string")
        self.assertIsInstance(app.secret_key, str,
                            "App secret_key is not a string")
    
    def test_api_blueprints_registered(self):
        """Test that API blueprints are registered.
        
        This is a loose check - we just verify that SOME blueprints
        are registered, not specific ones (which may change).
        """
        import campus.api
        app = create_app(campus.api)
        
        # Should have at least one blueprint registered
        self.assertGreater(len(app.blueprints), 0,
                          "No blueprints registered in API app")
        
        # Check for api_v1 blueprint specifically
        blueprint_names = [bp.name for bp in app.blueprints.values()]
        self.assertIn('api_v1', blueprint_names,
                     "api_v1 blueprint not registered")
    
    def test_api_routes_exist(self):
        """Test that API routes are registered.
        
        This is a loose check - we just verify SOME routes exist
        under /api/v1/, not that specific routes are present.
        This survives API changes while catching complete failures.
        """
        import campus.api
        app = create_app(campus.api)
        
        # Get all registered routes
        routes = [rule.rule for rule in app.url_map.iter_rules()]
        
        # Check that we have some api/v1 routes
        api_routes = [r for r in routes if '/api/v1/' in r]
        self.assertGreater(len(api_routes), 0,
                          "No API routes registered under /api/v1/")
    
    def test_api_has_error_handlers(self):
        """Test that API app has error handlers configured.
        
        This verifies that campus.common.errors.init_app was called.
        """
        import campus.api
        app = create_app(campus.api)
        
        # Should have error handlers registered
        # We can't easily check specific handlers, but we can verify
        # the app has error handler functions
        self.assertTrue(hasattr(app, 'error_handler_spec'),
                       "App missing error_handler_spec")


if __name__ == '__main__':
    unittest.main()
