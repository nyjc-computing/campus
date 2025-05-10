"""palmtree.py

Authentication and authorization service for Campus.
"""

from flask import Blueprint, Flask

from apps.common import errors
from .routes import clients
from .routes import emailotp
from .routes import users


def create_app() -> Flask:
    """Factory function to create the Palmtree app.
    
    This is called if Palmtree is run as a standalone app.
    """
    app = Flask(__name__)
    init_app(app)
    errors.init_app(app)
    return app

def init_app(app: Flask) -> None:
    """Initialise the Palmtree API blueprint with the given Flask app."""
    # Organise API routes under api blueprint
    bp = Blueprint('api_v1', __name__, url_prefix='/api/v1')
    # Users need to be initialised first as other blueprints
    # rely on user table
    users.init_app(bp)
    clients.init_app(bp)
    emailotp.init_app(bp)
    app.register_blueprint(bp)
