"""campus.apps.api

Web API for Campus services.
"""

__all__ = []

from flask import Blueprint, Flask

from campus.apps.api import routes


def init_app(app: Flask | Blueprint) -> None:
    """Initialise the API blueprint with the given Flask app."""
    # Organise API routes under api blueprint
    bp = Blueprint('api_v1', __name__, url_prefix='/api/v1')
    # Users need to be initialised first as other blueprints
    # rely on user table
    routes.circles.init_app(bp)
    routes.emailotp.init_app(bp)
    routes.users.init_app(bp)
    routes.admin.init_app(bp)
    app.register_blueprint(bp)
