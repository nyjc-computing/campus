"""campus.oauth.routes

This module contains the route definitions for Campus and third-party
OAuth2 authentication.
"""

__all__ = [
    # "campus",
    "discord",
    "github",
    "google",
]

import flask

from . import (
    # campus,
    discord,
    github,
    google,
)


def init_app(app: flask.Blueprint | flask.Flask) -> None:
    """Initialize the OAuth routes with the given Flask app/blueprint."""
    # campus.init_app(app)
    discord.init_app(app)
    github.init_app(app)
    google.init_app(app)
