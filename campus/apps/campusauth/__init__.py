"""campus.apps.campusauth

Web endpoints for Campus authentication.
"""

from flask import Blueprint, Flask

from campus.common import devops

from .authentication import (
    authenticate_client,
    client_auth_required
)


# pylint: disable=import-outside-toplevel

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


__all__ = [
    'init_app',
    'init_db',
    'authenticate_client',
    'client_auth_required',
]
