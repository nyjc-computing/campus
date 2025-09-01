"""campus.client.core

Unified Campus client interface providing consistent access to all services.
"""

import logging
import os
from typing import Mapping

from campus import config
from campus.client.apps import AdminResource, CirclesResource, UsersResource
from campus.client.vault import VaultResource
from campus.common.http import JsonClient, get_client

AppName = str  # e.g. "campus.apps", "campus.vault"

logging.basicConfig(level=logging.INFO)
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

    def __init__(self, override: Mapping[AppName, JsonClient] | None = None):
        """Initialize unified Campus client with all service clients.

        Credentials are automatically loaded from CLIENT_ID and CLIENT_SECRET
        environment variables. All service clients will be properly
        authenticated if these environment variables are set.

        Args:
            override: Optional mapping of app names to JSON clients.
        """
        app_names = (
            "campus.apps",
            "campus.vault"
        )
        # if-for structure for easier reading & cleaner "happy path"
        # see https://matklad.github.io/2023/11/15/push-ifs-up-and-fors-down.html
        if override is None:
            # Use client factory with default base URLs
            clients = {
                app_name: get_client(
                    base_url=config.get_base_url(app_name))
                for app_name in app_names
            }
        else:
            # Use provided overrides if present,
            # otherwise use client factory with default base URLs
            clients = {
                app_name: (
                    override.get(app_name)
                    or get_client(base_url=config.get_base_url(app_name))
                )
                for app_name in app_names
            }
        self.vault = VaultResource(clients["campus.vault"])
        self.admin = AdminResource(clients["campus.apps"])
        self.circles = CirclesResource(clients["campus.apps"])
        self.users = UsersResource(clients["campus.apps"])
        logging.debug(
            'Campus client instantiated in %s environment',
            os.getenv("ENV", "MISSING")
        )
        logging.debug('Vault base_url: %s', self.vault.client.base_url)
        logging.debug('Users base_url: %s', self.users.client.base_url)
        logging.debug('Circles base_url: %s', self.circles.client.base_url)
        logging.debug('Admin base_url: %s', self.admin.client.base_url)
