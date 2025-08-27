"""campus.client.core

Unified Campus client interface providing consistent access to all services.
"""

import logging
import os
from typing import TypedDict, Unpack

from campus.client.apps.admin import AdminResource
from campus.client.apps.circles import CirclesResource
from campus.client.apps.users import UsersResource
from campus.client.wrapper import ClientFactory
from campus.client.vault.vault import VaultResource

logger = logging.getLogger(__name__)


class CampusInit(TypedDict):
    """Keyword arguments for Campus.__init__()"""
    vault: ClientFactory
    users: ClientFactory
    circles: ClientFactory
    admin: ClientFactory


class Campus:
    """Unified Campus client interface.

    Provides consistent access patterns across all Campus services.
    Automatically loads credentials from CLIENT_ID and CLIENT_SECRET environment variables.

    See the API Reference for usage examples.
    """
    vault: VaultResource
    users: UsersResource
    circles: CirclesResource
    admin: AdminResource

    def __init__(self, **client_factories: Unpack[CampusInit]):
        """Initialize unified Campus client with all service clients.

        Credentials are automatically loaded from CLIENT_ID and CLIENT_SECRET
        environment variables. All service clients will be properly authenticated
        if these environment variables are set.
        """
        # Not using item iteration because pylint can't detect value types
        # from an unpacked TypedDict and considers values as `object` instead
        # pylint: disable=consider-using-dict-items
        for resource in client_factories:
            setattr(self,
                    resource,
                    VaultResource(client_factories[resource](), resource))
        logging.debug(
            'Campus client instantiated in %s environment',
            os.getenv("ENV", "MISSING")
        )
        logging.debug('Vault base_url: %s', self.vault.client.base_url)
        logging.debug('Users base_url: %s', self.users.client.base_url)
        logging.debug('Circles base_url: %s', self.circles.client.base_url)
        logging.debug('Admin base_url: %s', self.admin.client.base_url)
