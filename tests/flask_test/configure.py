"""tests.flask_test.configure

Configuration utilities for Flask apps in testing environments.
"""

from flask import Flask
from campus.common import devops


def configure_for_testing(app: Flask) -> None:
    """Configure the Flask app for testing.

    This function sets up Flask applications with testing-specific configuration:
    - Enables debug mode for better error messages
    - Sets testing flag to True
    - Adds a simple health check route
    - Configures proper error handling for tests

    Args:
        app: Flask application to configure
    """
    # Enable testing mode
    app.config['TESTING'] = True
    app.config['DEBUG'] = True

    # Disable CSRF for easier testing
    app.config['WTF_CSRF_ENABLED'] = False

    # Add a simple health check route for testing
    @app.route('/test/health')
    def test_health_check():
        return {
            'status': 'healthy',
            'environment': devops.ENV,
            'testing': True,
            'service': app.name
        }, 200

    # Initialize error handling (but don't override deployment-specific routes)
    import campus.common.errors
    campus.common.errors.init_app(app)
