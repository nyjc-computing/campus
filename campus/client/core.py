"""campus.client.core

Unified Campus client interface providing consistent access to all services.
"""

import logging
import os

from campus.client.apps.admin import AdminResource
from campus.client.apps.circles import CirclesResource
from campus.client.apps.users import UsersResource
from campus.client.wrapper import ClientFactory
from campus.client.vault.vault import VaultResource

logger = logging.getLogger(__name__)


class Campus:
    """Unified Campus client interface.

    Provides consistent access patterns across all Campus services.
    Automatically loads credentials from CLIENT_ID and CLIENT_SECRET environment variables.

    See the API Reference for usage examples.
    """

    def __init__(
            self,
            client_factory: ClientFactory,
            **client_factories: ClientFactory
    ):
        """Initialize unified Campus client with all service clients.

        Credentials are automatically loaded from CLIENT_ID and CLIENT_SECRET
        environment variables. All service clients will be properly authenticated
        if these environment variables are set.
        """
        self.vault = VaultResource(
            client_factories.get("vault", client_factory)(), "vault"
        )
        self.users = UsersResource(
            client_factories.get("users", client_factory)(), "users"
        )
        self.circles = CirclesResource(
            client_factories.get("circles", client_factory)(), "circles"
        )
        self.admin = AdminResource(
            client_factories.get("admin", client_factory)(), "admin"
        )
        logging.debug(
            'Campus client instantiated in %s environment',
            os.getenv("ENV", "MISSING")
        )
        logging.debug('Vault base_url: %s', self.vault.client.base_url)
        logging.debug('Users base_url: %s', self.users.client.base_url)
        logging.debug('Circles base_url: %s', self.circles.client.base_url)
        logging.debug('Admin base_url: %s', self.admin.client.base_url)
