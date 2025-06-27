"""apps/api

Web API for Campus services.
"""

from flask import Blueprint, Flask

from apps.common import errors
from apps.api import routes

# These aliased model imports allow the api package to be used similarly
# to the Campus API
# e.g. api.clients.new(), api.emailotp.request()
from apps.api.routes.circles import circles
from apps.api.routes.clients import clients
from apps.api.routes.emailotp import emailotp
from apps.api.routes.users import users

__all__ = [
    'create_app',
    'init_app',
    'init_db',
    'circles',
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

def init_app(app: Flask | Blueprint) -> None:
    """Initialise the Palmtree API blueprint with the given Flask app."""
    # Organise API routes under api blueprint
    bp = Blueprint('v1', __name__, url_prefix='/api/v1')
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

def purge() -> None:
    """Purge the database.
    
    This function is intended to be used in a test environment to reset the
    database state.
    """
    # These imports do not appear at the top of the file to avoid namespace
    # pollution, as they are typically not used in production.
    from warnings import warn

    from common import devops

    if devops.ENV in (devops.STAGING, devops.PRODUCTION):
        warn(f"Purging database in {devops.ENV} environment.", stacklevel=2)
        if input("Are you sure? (y/n): ").lower() == 'y':
            # User confirmed the purge
            from common.drum.postgres import purge
            purge()
    else:
        from common.drum.sqlite import purge
        purge()
