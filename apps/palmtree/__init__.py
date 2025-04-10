"""palmtree.py

Authentication and authorization service for Campus.
"""

from flask import Blueprint, Flask

from .routes import clients
from .routes import emailotp
from .routes import users


def api_internal_server_error(err):
    # TODO: Error logging
    return {"message": "Internal server error"}, 500
def create_app() -> Flask:
    """Factory function to create the Palmtree app."""
    # Organise API routes under api blueprint
    bp = Blueprint('api_v1', __name__, url_prefix='/api/v1')
    bp.register_error_handler(Exception, api_internal_server_error)
    # Users need to be initialised first as other blueprints
    # rely on user table
    users.init_app(bp)
    clients.init_app(bp)
    emailotp.init_app(bp)

    app = Flask(__name__)
    app.register_blueprint(bp)
    return app
