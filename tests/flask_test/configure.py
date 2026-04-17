"""tests.flask_test.configure

Configuration utilities for Flask apps in testing environments.
"""

import flask

from campus.common import devops
from campus.common import env


def configure_for_testing(app: flask.Flask) -> None:
    """Configure the Flask app for testing.

    This function sets up Flask applications with testing-specific configuration:
    - Enables debug mode for better error messages
    - Sets testing flag to True
    - Configures test storage backends
    - Adds a simple health check route
    - Configures proper error handling for tests

    Args:
        app: Flask application to configure
    """
    # Enable testing mode
    app.config['TESTING'] = True
    app.config['DEBUG'] = True

    # Configure test storage backends
    env.set('STORAGE_MODE', "1")

    # Disable CSRF for easier testing
    app.config['WTF_CSRF_ENABLED'] = False

    # Add a simple health check route for testing
    @app.route('/test/health')
    def test_health_check():
        from campus.storage.testing import is_test_mode
        return {
            'status': 'healthy',
            'environment': devops.ENV,
            'testing': True,
            'service': app.name,
            'storage_mode': 'test' if is_test_mode() else 'production'
        }, 200

    # Initialize error handling (but don't override deployment-specific routes)
    import campus.common.errors
    campus.common.errors.init_app(app)
