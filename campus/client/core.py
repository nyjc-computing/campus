"""campus.client.core

Unified Campus client interface providing consistent access to all services.
"""

import logging
import os

from campus.client.apps.admin import AdminResource
from campus.client.apps.circles import CirclesResource
from campus.client.apps.users import UsersResource
from campus.client.base import ClientFactory
from campus.client.vault.vault import VaultResource

logger = logging.getLogger(__name__)


class Campus:
    """Unified Campus client interface.

    Provides consistent access patterns across all Campus services.
    Automatically loads credentials from CLIENT_ID and CLIENT_SECRET environment variables.

    See the API Reference for usage examples.
    """

    def __init__(self, client_factory: ClientFactory):
        """Initialize unified Campus client with all service clients.

        Credentials are automatically loaded from CLIENT_ID and CLIENT_SECRET
        environment variables. All service clients will be properly authenticated
        if these environment variables are set.
        """
        self.vault = VaultResource(client_factory)
        self.users = UsersResource(client_factory)
        self.circles = CirclesResource(client_factory)
        self.admin = AdminResource(client_factory)
        logging.debug(
            'Campus client instantiated in %s environment',
            os.getenv("ENV", "MISSING")
        )
        logging.debug('Vault client base_url: %s', self.vault.base_url)
        logging.debug('Users client base_url: %s', self.users.base_url)
        logging.debug('Circles client base_url: %s', self.circles.base_url)
        logging.debug('Admin client base_url: %s', self.admin._client.base_url)
