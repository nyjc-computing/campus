#!/usr/bin/env python3
"""Campus Client Method Chain - Using Real Flask Apps

This script invokes all Campus client methods, one per line, in a coherent sequence.
Uses actual campus.apps and campus.vault create_app() factories instead of mocks.
"""

import os

from campus.client import Campus
import campus.apps
import campus.vault
from tests import flask_test


# Set required environment variables for testing
os.environ['ENV'] = 'testing'
os.environ['CLIENT_ID'] = 'test_client_id'
os.environ['CLIENT_SECRET'] = 'test_client_secret'
os.environ['VAULTDB_URI'] = 'sqlite:///:memory:'


def create_campus_test_api() -> Campus:
    """Create a Campus API client for testing.

    This client uses instantiated Flask apps and their test clients
    to test API functionality.
    """

    # Vault needs to be instantiated first, as Apps depends on it
    campus.vault.init_db()
    vault_client_factory = flask_test.create_client_factory(
        flask_test.configure_test_app(
            campus.vault.create_app()
        )
    )

    # TODO: Design elegant way to init_db() all app models
    # campus.apps.init_db()
    apps_client_factory = flask_test.create_client_factory(
        flask_test.configure_test_app(
            campus.apps.create_app()
        )
    )

    campus_client = Campus({
        "campus.apps": apps_client_factory(),
        "campus.vault": vault_client_factory(),
    })

    return campus_client


def test_all_methods():
    """Execute all Campus client methods on the test client."""

    campus = create_campus_test_api()
    # TODO: use fuzzing to test methods

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


if __name__ == "__main__":
    test_all_methods()
