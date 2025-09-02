"""tests.fixtures.storage

Functions for initialising campus.storage for testing use
"""

import os
import subprocess

from . import require, setup


def ensure_storage_database() -> bool:
    """Ensure storagedb exists, create if needed."""
    print("🗃️  Ensuring storage database exists...")

    # Use environment variables (should be set by setup_testing_env)
    pg_env = os.environ

    # Check if storagedb exists
    try:
        result = subprocess.run([
            'psql', '-h', pg_env['PGHOST'], '-U', pg_env['PGUSER'], '-d', 'postgres',
            '-t', '-A', '-c', "SELECT 1 FROM pg_database WHERE datname='storagedb';"
        ],
            env=pg_env,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0 and result.stdout.strip() == '1':
            print("✅ storagedb database already exists")
            return True
        else:
            print("📝 Creating storagedb database...")
            # Create storagedb
            create_result = subprocess.run([
                'psql', '-h', pg_env['PGHOST'], '-U', pg_env['PGUSER'], '-d', 'postgres',
                '-c', 'CREATE DATABASE storagedb;'
            ],
                env=pg_env,
                capture_output=True,
                text=True,
                timeout=10
            )

            if create_result.returncode == 0:
                print("✅ storagedb database created successfully")
                return True
            else:
                print(
                    f"❌ Failed to create storagedb: {create_result.stderr.strip()}")
                return False

    except Exception as e:
        print(f"❌ Error ensuring storage database exists: {e}")
        return False


def init():
    """Initialize storage fixtures for testing.

    This function:
    - Ensures storagedb database exists
    - Initializes 'storage' vault label
    - Sets POSTGRESDB_URI as a vault secret (not environment variable)
    - Gives client access to 'storage' label

    ENV must be 'testing' and client credentials must be set before calling.
    """
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")
    require.envvar("CLIENT_SECRET")

    # Ensure database exists first
    if not ensure_storage_database():
        raise RuntimeError("Failed to ensure storage database exists")

    import campus.vault

    # Give test client access to storage vault
    campus.vault.access.grant_access(
        client_id=client_id,
        label="storage",
        access=campus.vault.access.ALL
    )

    # Set up storage vault with database URI as a secret
    storage_vault = campus.vault.get_vault("storage")
    db_uri = setup.get_db_uri("storagedb")
    storage_vault.set("POSTGRESDB_URI", db_uri)
