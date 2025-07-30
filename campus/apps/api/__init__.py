"""campus.apps.api

Web API for Campus services.
"""

from flask import Blueprint, Flask

from campus.apps.api import routes
from campus.common import errors

__all__ = [
    'create_app',
    'init_app',
]


def create_app() -> Flask:
    """Factory function to create the api app.

    This is called if api is run as a standalone app.
    """
    app = Flask(__name__)
    init_app(app)
    errors.init_app(app)
    return app


def init_app(app: Flask | Blueprint) -> None:
    """Initialise the API blueprint with the given Flask app."""
    # Organise API routes under api blueprint
    bp = Blueprint('v1', __name__, url_prefix='/api/v1')
    # Users need to be initialised first as other blueprints
    # rely on user table
    routes.circles.init_app(bp)
    routes.emailotp.init_app(bp)
    routes.users.init_app(bp)
    routes.admin.init_app(bp)
    app.register_blueprint(bp)
