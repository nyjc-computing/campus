"""apps.campusauth.context

This module defines the client and user context for the Campus API.
This context is pushed to the flask g object for use in the API routes.
"""

from flask import g

from apps.common.models.client import ClientResource
from apps.common.models.credentials import (
    ClientCredentialsSchema,
    UserCredentialsSchema,
)
from apps.common.models.user import UserResource


class ContextError(Exception):
    """Error raised when the context is invalid."""


class CampusContext:
    """Context for the Campus API."""

    def __init__(self):
        pass

    @property
    def user(self) -> UserResource:
        """Get the user context."""
        if "user" not in g:
            raise ContextError("User context not found")
        return g.user

    @user.setter
    def user(self, value: UserResource):
        """Set the user context."""
        g.user = value

    @property
    def user_credentials(self) -> UserCredentialsSchema:
        """Get the user credentials."""
        if "user_credentials" not in g:
            raise ContextError("User credentials not found")
        return g.user_credentials

    @user_credentials.setter
    def user_credentials(self, value: UserCredentialsSchema):
        """Set the user credentials."""
        g.user_credentials = value

    @property
    def client(self) -> ClientResource:
        """Get the client context."""
        if "client" not in g:
            raise ContextError("Client context not found")
        return g.client

    @client.setter
    def client(self, value: ClientResource):
        """Set the client context."""
        g.client = value

    @property
    def client_credentials(self) -> ClientCredentialsSchema:
        """Get the client credentials."""
        if "client_credentials" not in g:
            raise ContextError("Client credentials not found")
        return g.client_credentials

    @client_credentials.setter
    def client_credentials(self, value: ClientCredentialsSchema):
        """Set the client credentials."""
        g.client_credentials = value
