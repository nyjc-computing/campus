"""tests.fixtures.vault

Functions for initialising campus.vault for testing use
"""

import os
import subprocess

from . import require, setup
from .setup import set_db_uri


def ensure_vault_database() -> bool:
    """Ensure vaultdb exists, create if needed."""
    print("🗃️  Ensuring vault database exists...")

    # Use environment variables (should be set by setup_testing_env)
    pg_env = os.environ

    # Check if vaultdb exists
    try:
        result = subprocess.run([
            'psql', '-h', pg_env['PGHOST'], '-U', pg_env['PGUSER'], '-d', 'postgres',
            '-t', '-A', '-c', "SELECT 1 FROM pg_database WHERE datname='vaultdb';"
        ],
            env=pg_env,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0 and result.stdout.strip() == '1':
            print("✅ vaultdb database already exists")
            return True
        else:
            print("📝 Creating vaultdb database...")
            # Create vaultdb
            create_result = subprocess.run([
                'psql', '-h', pg_env['PGHOST'], '-U', pg_env['PGUSER'], '-d', 'postgres',
                '-c', 'CREATE DATABASE vaultdb;'
            ],
                env=pg_env,
                capture_output=True,
                text=True,
                timeout=10
            )

            if create_result.returncode == 0:
                print("✅ vaultdb database created successfully")
                return True
            else:
                print(
                    f"❌ Failed to create vaultdb: {create_result.stderr.strip()}")
                return False

    except Exception as e:
        print(f"❌ Error ensuring vault database exists: {e}")
        return False


def init():
    """Initialize vault fixtures for testing.

    This function:
    - Ensures vaultdb database exists
    - Sets up VAULTDB_URI using postgres env vars
    - Initializes vault database
    - Creates test client and sets CLIENT_ID/CLIENT_SECRET env vars
    - Sets up vault's own SECRET_KEY in 'vault' vault
    - Gives client access to 'vault' label

    ENV must be 'testing' and postgres env vars must be set before calling.
    """
    require.env("testing")

    # Ensure database exists first
    if not ensure_vault_database():
        raise RuntimeError("Failed to ensure vault database exists")

    setup.set_db_uri("VAULTDB_URI", "vaultdb")
    import campus.vault
    campus.vault.init_db()

    # Set up vault's own SECRET_KEY (for vault service client authentication)
    # We need to bootstrap this manually since there's no client yet
    from campus.vault import get_vault
    vault_vault = get_vault("vault")
    vault_vault.set("SECRET_KEY", "vault-secret-key")

    # Create client for testing (use unique name with timestamp)
    import time
    client_name = f"test-client-{int(time.time())}"
    clientconfig = campus.vault.client.create_client(
        name=client_name,
        description="Campus test client"
    )
    client, secret = clientconfig["client"], clientconfig["secret"]

    # Set client credentials in environment
    os.environ["CLIENT_ID"] = client["id"]
    os.environ["CLIENT_SECRET"] = secret

    # Give client access to vault label
    campus.vault.access.grant_access(
        client_id=client["id"],
        label="vault",
        access=campus.vault.access.ALL
    )


def give_vault_access(
        label: str,
        *,
        read: bool | None = None,
        create: bool | None = None,
        update: bool | None = None,
        delete: bool | None = None,
        all: bool | None = None
):
    """Give the configured client access to the labelled vault."""
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")

    # all cannot be specified with the other access levels
    if all and (read or create or update or delete):
        raise ValueError("Cannot specify 'all' with other access values")

    import campus.vault
    access_value = 0
    if all:
        access_value = campus.vault.access.ALL
    else:
        if read:
            access_value += campus.vault.access.READ
        if create:
            access_value += campus.vault.access.CREATE
        if update:
            access_value += campus.vault.access.UPDATE
        if delete:
            access_value += campus.vault.access.DELETE

    campus.vault.access.grant_access(
        client_id=client_id,
        label=label,
        access=access_value
    )
