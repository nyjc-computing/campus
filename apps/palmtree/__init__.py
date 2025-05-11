"""palmtree.py

Authentication and authorization service for Campus.
"""

from flask import Blueprint, Flask

from apps.common import errors

from . import routes
# These aliased imports allow the palmtree package to be used similarly to the
# Campus API
# e.g. palmtree.clients.new(), palmtree.emailotp.request()
from routes.clients import clients
from routes.emailotp import emailotp
from routes.users import users

__all__ = [
    'create_app',
    'init_app',
    'clients',
    'emailotp',
    'users'
]


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
    routes.users.init_app(bp)
    routes.clients.init_app(bp)
    routes.emailotp.init_app(bp)
    app.register_blueprint(bp)
