"""tests.fixtures.postgres

Functions for PostgreSQL database management during testing.
"""

import os  # Keep os.environ for subprocess full environment
import subprocess

from campus.common import devops


def database_exists(database_name: str) -> bool:
    """Check if a PostgreSQL database exists.

    Args:
        database_name: Name of the database to check

    Returns:
        True if database exists, False otherwise

    Raises:
        FileNotFoundError: If psql command is not available
        subprocess.SubprocessError: If database connection fails
        OSError: If required postgres environment variables are not set
    """
    # Use environment variables (should be set by setup_testing_env)
    pg_env = os.environ

    try:
        result = subprocess.run([
            'psql', '-h', pg_env['PGHOST'], '-U', pg_env['PGUSER'], '-d', 'postgres',
            '-t', '-A', '-c', f"SELECT 1 FROM pg_database WHERE datname='{database_name}';"
        ],
            env=pg_env,
            capture_output=True,
            text=True,
            timeout=10
        )
    except FileNotFoundError as e:
        raise FileNotFoundError(
            "psql command not found. PostgreSQL client tools must be installed for database operations."
        ) from e

    if result.returncode != 0:
        raise subprocess.SubprocessError(
            f"Failed to check database existence: {result.stderr.strip()}")

    return result.stdout.strip() == '1'


def create_database(database_name: str) -> None:
    """Create a PostgreSQL database.

    Args:
        database_name: Name of the database to create

    Raises:
        FileNotFoundError: If psql command is not available
        subprocess.SubprocessError: If database creation fails
        OSError: If required postgres environment variables are not set
    """
    # Use environment variables (should be set by setup_testing_env)
    pg_env = os.environ

    try:
        result = subprocess.run([
            'psql', '-h', pg_env['PGHOST'], '-U', pg_env['PGUSER'], '-d', 'postgres',
            '-c', f'CREATE DATABASE {database_name};'
        ],
            env=pg_env,
            capture_output=True,
            text=True,
            timeout=10
        )
    except FileNotFoundError as e:
        raise FileNotFoundError(
            "psql command not found. PostgreSQL client tools must be installed for database operations."
        ) from e

    if result.returncode != 0:
        raise subprocess.SubprocessError(
            f"Failed to create database {database_name}: {result.stderr.strip()}")


def ensure_database_exists(database_name: str) -> None:
    """Ensure a PostgreSQL database exists, creating it if necessary.

    Args:
        database_name: Name of the database to ensure exists

    Raises:
        FileNotFoundError: If psql command is not available
        subprocess.SubprocessError: If database operations fail
        OSError: If required postgres environment variables are not set
    """
    print(f"🗃️  Ensuring {database_name} database exists...")

    try:
        if database_exists(database_name):
            print(f"✅ {database_name} database already exists")
        else:
            print(f"📝 Creating {database_name} database...")
            create_database(database_name)
            print(f"✅ {database_name} database created successfully")
    except Exception as e:
        raise RuntimeError(
            f"Failed to ensure PostgreSQL database '{database_name}' exists: {e}"
        ) from e


@devops.require_env(devops.TESTING)
def purge_database(database_name: str) -> None:
    """Purge (drop and recreate) a PostgreSQL database for clean testing state.

    Args:
        database_name: Name of the database to purge

    Raises:
        FileNotFoundError: If psql command is not available
        subprocess.SubprocessError: If database operations fail
        OSError: If required postgres environment variables are not set
    """
    pg_env = os.environ

    # Drop the database if it exists
    try:
        result = subprocess.run([
            'psql', '-h', pg_env['PGHOST'], '-U', pg_env['PGUSER'], '-d', 'postgres',
            '-c', f'DROP DATABASE IF EXISTS {database_name};'
        ], env=pg_env, capture_output=True, text=True, timeout=10)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            "psql command not found. PostgreSQL client tools must be installed for database operations."
        ) from e

    if result.returncode != 0:
        raise subprocess.SubprocessError(
            f"Failed to drop database {database_name}: {result.stderr.strip()}")

    # Recreate the database
    create_database(database_name)
