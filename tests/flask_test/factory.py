"""tests.flask_test.factory

Factory functions for creating Flask test apps for Campus services.
"""

from campus.common import env


def create_test_app(module):
    """Create a single Flask app for testing with proper test configuration.

    This function handles all the proper setup for testing a single service:
    - Sets test environment variables 
    - Enables test storage mode
    - Creates and configures Flask app

    Args:
        module: Campus service module (e.g., campus.auth, campus.api)

    Returns:
        Flask app configured for testing

    Example:
        import campus.auth
        from tests.flask_test import create_test_app

        app = create_test_app(campus.auth)
        # App is ready for FlaskTestClient testing
    """
    from tests.fixtures import setup
    from campus.common.devops.deploy import create_app
    from .configure import configure_for_testing

    # Set proper environment variables
    setup.set_test_env_vars()
    env.STORAGE_MODE = "1"

    # Create and configure app
    app = create_app(module)
    configure_for_testing(app)

    return app
