"""tests.fixtures.yapper

Functions for initialising campus.yapper for testing use
"""

import os
import subprocess

from . import require, setup


def ensure_yapper_database() -> bool:
    """Ensure yapperdb exists, create if needed."""
    print("🗃️  Ensuring yapper database exists...")

    # Use environment variables (should be set by setup_testing_env)
    pg_env = os.environ

    # Check if yapperdb exists
    try:
        result = subprocess.run([
            'psql', '-h', pg_env['PGHOST'], '-U', pg_env['PGUSER'], '-d', 'postgres',
            '-t', '-A', '-c', "SELECT 1 FROM pg_database WHERE datname='yapperdb';"
        ],
            env=pg_env,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0 and result.stdout.strip() == '1':
            print("✅ yapperdb database already exists")
            return True
        else:
            print("📝 Creating yapperdb database...")
            # Create yapperdb
            create_result = subprocess.run([
                'psql', '-h', pg_env['PGHOST'], '-U', pg_env['PGUSER'], '-d', 'postgres',
                '-c', 'CREATE DATABASE yapperdb;'
            ],
                env=pg_env,
                capture_output=True,
                text=True,
                timeout=10
            )

            if create_result.returncode == 0:
                print("✅ yapperdb database created successfully")
                return True
            else:
                print(
                    f"❌ Failed to create yapperdb: {create_result.stderr.strip()}")
                return False

    except Exception as e:
        print(f"❌ Error ensuring yapper database exists: {e}")
        return False


def init():
    """Initialize yapper fixtures for testing.

    This function:
    - Ensures yapperdb database exists
    - Initializes 'yapper' vault label
    - Sets YAPPERDB_URI as a vault secret (not environment variable)
    - Gives client access to 'yapper' label

    ENV must be 'testing' and client credentials must be set before calling.
    """
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")
    require.envvar("CLIENT_SECRET")

    # Ensure database exists first
    if not ensure_yapper_database():
        raise RuntimeError("Failed to ensure yapper database exists")

    import campus.vault

    # Give test client access to yapper vault
    campus.vault.access.grant_access(
        client_id=client_id,
        label="yapper",
        access=campus.vault.access.ALL
    )

    # Set up yapper vault with database URI as a secret
    yapper_vault = campus.vault.get_vault("yapper")
    db_uri = setup.get_db_uri("yapperdb")
    yapper_vault.set("YAPPERDB_URI", db_uri)
