"""campus.client.Campus

Unified Campus client interface providing consistent access to all services.
"""

from .vault.vault import VaultClient
from .apps.users import UsersClient  
from .apps.circles import CirclesClient


class Campus:
    """Unified Campus client interface.
    
    Provides consistent access patterns across all Campus services:
    - Path parameters via subscription: campus.vault["storage"]
    - Query parameters via methods: campus.vault.new(name="...", description="...")
    
    Example:
        ```python
        from campus.client import Campus
        campus = Campus()
        
        # Set credentials for all services
        campus.set_credentials("client_id", "client_secret")
        
        # Path parameter access
        storage_vault = campus.vault["storage"]
        MONGODB_URI = storage_vault["MONGODB_URI"]
        user = campus.users["user_id"]
        circle = campus.circles["circle_id"]
        
        # Query parameter access
        client = campus.vault.new(name="client_name", description="...")
        user = campus.users.new(email="user@example.com", name="User Name")
        circle = campus.circles.new(name="circle_name", description="...")
        ```
    """

    def __init__(self):
        """Initialize unified Campus client with all service clients."""
        self.vault = VaultClient()
        self.users = UsersClient()
        self.circles = CirclesClient()

    def set_credentials(self, client_id: str, client_secret: str) -> None:
        """Set authentication credentials for all service clients.
        
        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
        """
        self.vault.set_credentials(client_id, client_secret)
        self.users.set_credentials(client_id, client_secret)
        self.circles.set_credentials(client_id, client_secret)
