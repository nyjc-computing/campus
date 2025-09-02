#!/usr/bin/env python3
"""Test Flask test client strategy with storage backends"""

from tests.flask_test.client import FlaskTestClient
from tests.flask_test.configure import configure_for_testing
import campus.vault
from campus.common.devops.deploy import create_app
import os
os.environ["CAMPUS_ENV"] = "testing"
os.environ["STORAGE_MODE"] = "1"


def test_vault_with_storage():
    """Test that vault works with test storage configuration."""
    print("Testing vault service with test storage...")

    # Create vault app
    app = create_app(campus.vault)

    # Configure testing environment
    configure_for_testing(app)

    # Debug: Print all registered routes
    print("Registered routes:")
    for rule in app.url_map.iter_rules():
        print(f"  {rule.rule} -> {rule.endpoint}")

    # Test with FlaskTestClient
    with FlaskTestClient(app) as client:
        # Test the test health endpoint we added
        response = client.get("/test/health")
        print(f"Test health endpoint: {response.status_code}")
        print(f"Response: {response.json()}")

        if response.status_code == 200:
            print("✅ Vault with test storage works! (Health check passed)")
        else:
            print(f"❌ Unexpected status code: {response.status_code}")


if __name__ == "__main__":
    test_vault_with_storage()
