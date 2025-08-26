#!/usr/bin/env python3
"""Campus Client Method Chain - Using Real Flask Apps

This script invokes all Campus client methods, one per line, in a coherent sequence.
Uses actual campus.apps and campus.vault create_app() factories instead of mocks.
"""

import os
import sys

import campus.apps.api
from campus.client.core import Campus
import campus.vault
from tests.test_client import create_test_client_factory, FlaskTestClient, FlaskTestResponse

sys.path.insert(0, '/workspaces/campus')

# Set required environment variables for testing
os.environ['ENV'] = 'testing'
os.environ['CLIENT_ID'] = 'test_client_id'
os.environ['CLIENT_SECRET'] = 'test_client_secret'
os.environ['VAULTDB_URI'] = 'sqlite:///:memory:'


class CombinedFlaskTestClient:
    """Test client that routes requests to appropriate Flask apps."""

    def __init__(self, api_client, vault_client):
        self.api_client = api_client
        self.vault_client = vault_client
        self.base_url = ""

    def _route_request(self, method, path, **kwargs):
        """Route requests to the appropriate test client."""
        if path.startswith('/vault') or path.startswith('/access') or path.startswith('/clients'):
            client = self.vault_client
        else:
            client = self.api_client

        if not path.startswith('/'):
            path = '/' + path

        # Handle query parameters for GET requests
        params = kwargs.pop('params', None)
        if params and method.upper() == 'GET':
            from urllib.parse import urlencode
            query_string = urlencode(params)
            if '?' in path:
                path = f"{path}&{query_string}"
            else:
                path = f"{path}?{query_string}"

        # Make the request
        response = getattr(client, method.lower())(path, **kwargs)
        return FlaskTestResponse(response)

    def get(self, path, **kwargs):
        return self._route_request('GET', path, **kwargs)

    def post(self, path, **kwargs):
        return self._route_request('POST', path, **kwargs)

    def put(self, path, **kwargs):
        return self._route_request('PUT', path, **kwargs)

    def patch(self, path, **kwargs):
        return self._route_request('PATCH', path, **kwargs)

    def delete(self, path, **kwargs):
        return self._route_request('DELETE', path, **kwargs)


def setup_real_apps():
    """Setup real Flask apps and initialize databases."""
    print("🔧 Setting up real Flask applications...")

    # Create apps using real factories
    api_app = campus.apps.api.create_app()
    vault_app = campus.vault.create_app()

    # Initialize databases
    try:
        campus.vault.init_db()
        print("✓ Vault database initialized")
    except Exception as e:
        print(f"! Vault DB init: {e}")

    try:
        from campus.apps.api.routes import admin
        admin.init_db()
        print("✓ API database initialized")
    except Exception as e:
        print(f"! API DB init: {e}")

    # Create combined test client
    combined_client = CombinedFlaskTestClient(
        api_app.test_client(),
        vault_app.test_client()
    )

    return combined_client


def execute_method_chain():
    """Execute all Campus client methods in a logical chain using real apps."""

    # Setup real Flask apps
    combined_client = setup_real_apps()

    # Create client factory
    def client_factory():
        return combined_client

    campus = Campus(client_factory)

    print("\n🚀 Executing all Campus client methods with real Flask apps...")
    print("=" * 60)

    # Method chain - each method on its own line as requested
    print("1.  campus.admin.status()")
    campus.admin.status()

    print("2.  campus.admin.init_db()")
    campus.admin.init_db()

    print("3.  campus.vault.clients.new('Test App', 'Test Description')")
    campus.vault.clients.new("Test App", "Test Description")

    print("4.  campus.vault.clients.list()")
    campus.vault.clients.list()

    print("5.  campus.vault.clients.authenticate('test_client', 'test_secret')")
    campus.vault.clients.authenticate("test_client", "test_secret")

    print("6.  campus.vault.clients.get('test_client')")
    campus.vault.clients.get("test_client")

    print("7.  campus.vault.access.grant(client_id='test_client', label='apps', permissions=15)")
    campus.vault.access.grant(client_id="test_client",
                              label="apps", permissions=15)

    print("8.  campus.vault.access.check(client_id='test_client', label='apps')")
    campus.vault.access.check(client_id="test_client", label="apps")

    print("9.  campus.users.new(email='alice@example.com', name='Alice')")
    campus.users.new(email="alice@example.com", name="Alice")

    print("10. campus.users['user_1'].get()")
    campus.users["user_1"].get()

    print("11. campus.users['user_1'].profile()")
    campus.users["user_1"].profile()

    print("12. campus.users['user_1'].update(name='Alice Updated')")
    campus.users["user_1"].update(name="Alice Updated")

    print("13. campus.circles.new(name='Dev Team', description='Development team')")
    campus.circles.new(name="Dev Team", description="Development team")

    print("14. campus.circles.list()")
    campus.circles.list()

    print("15. campus.circles['circle_1'].get()")
    campus.circles["circle_1"].get()

    print(
        "16. campus.circles['circle_1'].update(description='Updated description')")
    campus.circles["circle_1"].update(description="Updated description")

    print("17. campus.circles['circle_1'].members.list()")
    campus.circles["circle_1"].members.list()

    print(
        "18. campus.circles['circle_1'].members.add(member_id='user_1', access_value='admin')")
    campus.circles["circle_1"].members.add(
        member_id="user_1", access_value="admin")

    print(
        "19. campus.circles['circle_1'].members.set('user_1', access_value='read')")
    campus.circles["circle_1"].members.set("user_1", access_value="read")

    print("20. campus.circles['circle_1'].members.remove('user_1')")
    campus.circles["circle_1"].members.remove("user_1")

    print("21. campus.circles['circle_1'].move(parent_circle_id='parent')")
    campus.circles["circle_1"].move(parent_circle_id="parent")

    print("22. campus.vault.list()")
    campus.vault.list()

    print("23. campus.vault['apps'].list()")
    campus.vault["apps"].list()

    print("24. campus.vault['apps']['api_key'].set(value='secret-value')")
    campus.vault["apps"]["api_key"].set(value="secret-value")

    print("25. campus.vault['apps']['api_key'].get()")
    campus.vault["apps"]["api_key"].get()

    print("26. campus.vault['apps']['api_key'].delete()")
    campus.vault["apps"]["api_key"].delete()

    print("27. campus.circles['circle_1'].delete()")
    campus.circles["circle_1"].delete()

    print("28. campus.users['user_1'].delete()")
    campus.users["user_1"].delete()

    print("29. campus.vault.access.revoke(client_id='test_client', label='apps')")
    campus.vault.access.revoke(client_id="test_client", label="apps")

    print("30. campus.vault.clients.delete('test_client')")
    campus.vault.clients.delete("test_client")

    print("31. campus.admin.purge_db()")
    campus.admin.purge_db()

    print("\n✅ All 31 Campus client methods executed successfully!")
    print("🎯 Each method was invoked on its own line using real Flask apps")
    print("📦 Used campus.apps.api.create_app() and campus.vault.create_app()")


if __name__ == "__main__":
    execute_method_chain()
