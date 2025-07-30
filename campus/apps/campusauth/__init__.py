"""campus.apps.campusauth

Web endpoints for Campus authentication.
"""

from flask import Blueprint, Flask

from campus.common import devops

from .authentication import (
    authenticate_client,
    client_auth_required
)
from .context import ctx

__all__ = [
    'create_app',
    'init_app',
    'init_db',
    'authenticate_client',
    'client_auth_required',
    "ctx"
]


def create_app() -> Flask:
    """Factory function to create the campusauth app.
    
    This is called if campusauth is run as a standalone app.
    """
    from campus.common import errors
    app = Flask(__name__)
    init_app(app)
    errors.init_app(app)
    return app

def init_app(app: Flask | Blueprint) -> None:
    """Initialise the campusauth blueprint with the given Flask app."""
    from . import routes
    routes.init_app(app)

@devops.block_env(devops.PRODUCTION)
def init_db() -> None:
    """Initialise the tables needed.
    
    This convenience function makes it easier to initialise tables for all
    models.
    """
    # campusauth relies on existing models and does not use any drums.
