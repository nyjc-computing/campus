"""campus.client.core

Unified Campus client interface providing consistent access to all services.
"""

import logging
import os

from campus import config
from campus.client.apps import AdminResource, CirclesResource, UsersResource
from campus.client.vault.vault import VaultResource
from campus.common.http import get_client

logger = logging.getLogger(__name__)


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

    def __init__(self):
        """Initialize unified Campus client with all service clients.

        Credentials are automatically loaded from CLIENT_ID and CLIENT_SECRET
        environment variables. All service clients will be properly authenticated
        if these environment variables are set.
        """
        apps_base_url = config.get_app_base_url("campus.apps")
        vault_base_url = config.get_app_base_url("campus.vault")
        # Not using item iteration because pylint can't detect value types
        # from an unpacked TypedDict and considers values as `object` instead
        # pylint: disable=consider-using-dict-items
        self.admin = AdminResource(get_client(base_url=apps_base_url))
        self.circles = CirclesResource(get_client(base_url=apps_base_url))
        self.users = UsersResource(get_client(base_url=apps_base_url))
        self.vault = VaultResource(get_client(base_url=vault_base_url))
        logging.debug(
            'Campus client instantiated in %s environment',
            os.getenv("ENV", "MISSING")
        )
        logging.debug('Vault base_url: %s', self.vault.client.base_url)
        logging.debug('Users base_url: %s', self.users.client.base_url)
        logging.debug('Circles base_url: %s', self.circles.client.base_url)
        logging.debug('Admin base_url: %s', self.admin.client.base_url)
