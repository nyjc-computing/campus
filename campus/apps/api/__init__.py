"""apps.api

Web API for Campus services.
"""

from flask import Blueprint, Flask

from campus.apps.api import routes
from campus.apps import errors

# These aliased model imports allow the api package to be used similarly
# to the Campus API
# e.g. api.circles.new(), api.emailotp.request()
from campus.apps.api.routes.circles import circles
from campus.apps.api.routes.emailotp import emailotp
from campus.apps.api.routes.users import users
from campus.common import devops

__all__ = [
    'create_app',
    'init_app',
    'init_db',
    'circles',
    'emailotp',
    'users'
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
    routes.users.init_app(bp)
    routes.clients.init_app(bp)
    routes.emailotp.init_app(bp)
    app.register_blueprint(bp)


@devops.block_env(devops.PRODUCTION)
def init_db() -> None:
    """Initialise the tables needed by api.

    This convenience function makes it easier to initialise tables for all
    models.
    """
    # These imports do not appear at the top of the file to avoid namespace
    # pollution, as they are typically only used in staging.
    from campus.apps.models import emailotp, user
    from campus.services.vault import client

    for model in (emailotp, user):
        model.init_db()

    # Initialize vault client database
    client.init_db()


@devops.block_env(devops.PRODUCTION)
def purge() -> None:
    """Purge the database.

    This function is intended to be used in a test environment to reset the
    database state.
    """
    # These imports do not appear at the top of the file to avoid namespace
    # pollution, as they are typically not used in production.
    from warnings import warn  # type: ignore[import-untyped]
    from campus.storage import purge_all  # type: ignore[import-untyped]

    if devops.ENV == devops.STAGING:
        warn(f"Purging database in {devops.ENV} environment.", stacklevel=2)
        if input("Are you sure? (y/n): ").lower() == 'y':
            # User confirmed the purge
            purge_all()
    else:
        purge_all()
