#!/usr/bin/env python3
"""Campus Client Method Chain - Using Real Flask Apps

This script invokes all Campus client methods, one per line, in a coherent sequence.
Uses actual campus.apps and campus.vault create_app() factories instead of mocks.
"""

import os
import unittest

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


class TestCampusClientMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.campus = create_campus_test_api()

    def test_01_admin_status(self):
        self.campus.admin.status()

    def test_02_admin_init_db(self):
        self.campus.admin.init_db()

    def test_03_vault_clients_new(self):
        self.campus.vault.clients.new("Test App", "Test Description")

    def test_04_vault_clients_list(self):
        self.campus.vault.clients.list()

    def test_05_vault_clients_authenticate(self):
        self.campus.vault.clients.authenticate("test_client", "test_secret")

    def test_06_vault_clients_get(self):
        self.campus.vault.clients.get("test_client")

    def test_07_vault_access_grant(self):
        self.campus.vault.access.grant(
            client_id="test_client", label="apps", permissions=15)

    def test_08_vault_access_check(self):
        self.campus.vault.access.check(client_id="test_client", label="apps")

    def test_09_users_new(self):
        self.campus.users.new(email="alice@example.com", name="Alice")

    def test_10_users_get(self):
        self.campus.users["user_1"].get()

    def test_11_users_profile(self):
        self.campus.users["user_1"].profile()

    def test_12_users_update(self):
        self.campus.users["user_1"].update(name="Alice Updated")

    def test_13_circles_new(self):
        self.campus.circles.new(
            name="Dev Team", description="Development team")

    def test_14_circles_list(self):
        self.campus.circles.list()

    def test_15_circles_get(self):
        self.campus.circles["circle_1"].get()

    def test_16_circles_update(self):
        self.campus.circles["circle_1"].update(
            description="Updated description")

    def test_17_circles_members_list(self):
        self.campus.circles["circle_1"].members.list()

    def test_18_circles_members_add(self):
        self.campus.circles["circle_1"].members.add(
            member_id="user_1", access_value="admin")

    def test_19_circles_members_set(self):
        self.campus.circles["circle_1"].members.set(
            "user_1", access_value="read")

    def test_20_circles_members_remove(self):
        self.campus.circles["circle_1"].members.remove("user_1")

    def test_21_circles_move(self):
        self.campus.circles["circle_1"].move(parent_circle_id="parent")

    def test_22_vault_list(self):
        self.campus.vault.list()

    def test_23_vault_apps_list(self):
        self.campus.vault["apps"].list()

    def test_24_vault_apps_api_key_set(self):
        self.campus.vault["apps"]["api_key"].set(value="secret-value")

    def test_25_vault_apps_api_key_get(self):
        self.campus.vault["apps"]["api_key"].get()

    def test_26_vault_apps_api_key_delete(self):
        self.campus.vault["apps"]["api_key"].delete()

    def test_27_circles_delete(self):
        self.campus.circles["circle_1"].delete()

    def test_28_users_delete(self):
        self.campus.users["user_1"].delete()

    def test_29_vault_access_revoke(self):
        self.campus.vault.access.revoke(client_id="test_client", label="apps")

    def test_30_vault_clients_delete(self):
        self.campus.vault.clients.delete("test_client")

    def test_31_admin_purge_db(self):
        self.campus.admin.purge_db()


if __name__ == "__main__":
    unittest.main()
