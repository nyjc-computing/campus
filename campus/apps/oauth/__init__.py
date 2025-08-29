"""campus.apps.oauth

OAuth2 routes for integrations.
"""

from flask import Blueprint, Flask

from campus.common import devops

from . import google



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


__all__ = [
    'init_app',
    'init_db',
]
    