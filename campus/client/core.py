"""campus.client.core

Unified Campus client interface providing consistent access to all services.
"""

from campus.client.apps.admin import AdminClient
from campus.client.apps.circles import CirclesClient
from campus.client.apps.users import UsersClient
from campus.client.vault.vault import VaultClient


class Campus:
    """Unified Campus client interface.

    Provides consistent access patterns across all Campus services.
    Automatically loads credentials from CLIENT_ID and CLIENT_SECRET environment variables.

    See the API Reference for usage examples.
    """

    def __init__(self):
        """Initialize unified Campus client with all service clients.

        Credentials are automatically loaded from CLIENT_ID and CLIENT_SECRET
        environment variables. All service clients will be properly authenticated
        if these environment variables are set.
        """
        self.vault = VaultClient()
        self.users = UsersClient()
        self.circles = CirclesClient()
        self.admin = AdminClient()
