"""apps.oauth

OAuth2 routes for integrations.
"""

from flask import Blueprint, Flask

from apps.common import errors
from common import devops

from . import google

__all__ = [
    'create_app',
    'init_app',
    'init_db',
]


def create_app() -> Flask:
    """Factory function to create the oauth app.
    
    This is called if oauth is run as a standalone app, without the /oauth
    url prefix.
    """
    app = Flask(__name__)
    init_app(app)
    errors.init_app(app)
    return app

def init_app(app: Flask | Blueprint) -> None:
    """Initialise the oauth blueprint with the given Flask app."""
    # Organise API routes under api blueprint
    bp = Blueprint('oauth', __name__, url_prefix='/oauth')
    google.init_app(bp)
    app.register_blueprint(bp)

@devops.block_env(devops.PRODUCTION)
def init_db() -> None:
    """Initialise the tables needed by oauth.
    
    This convenience function makes it easier to initialise tables for all
    models.
    """
    