"""palmtree.py

Authentication and authorization service for Campus.
"""

from flask import Blueprint, Flask

from apps.common import errors
from apps.palmtree import routes

# These aliased model imports allow the palmtree package to be used similarly
# to the Campus API
# e.g. palmtree.clients.new(), palmtree.emailotp.request()
from apps.palmtree.routes.clients import clients
from apps.palmtree.routes.emailotp import emailotp
from apps.palmtree.routes.users import users

__all__ = [
    'create_app',
    'init_app',
    'init_db',
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

def init_db() -> None:
    """Initialise the tables needed by Palmtree.
    
    This convenience function makes it easier to initialise tables for all
    models.
    """
    # These imports do not appear at the top of the file to avoid namespace
    # pollution, as they are typically only used in staging.
    from .models import client, otp, user

    for model in (client, otp, user):
        model.init_db()
