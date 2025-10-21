#!/usr/bin/env python3
"""
Campus Testing Environment Setup

This script sets up a complete testing environment by:
1. Confirming we're in testing environment
2. Checking PostgreSQL connectivity
3. Initializing all fixtures (vault, yapper, storage)
"""
import subprocess
import sys

# General fixtures
from tests.fixtures import require, setup
# Service-specific fixtures
from tests.fixtures import storage, vault, yapper
from campus.common import env

# Add the project root to Python path so we can import from tests
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_environment() -> bool:
    """Confirm we're in the testing environment."""
    # Set up all testing environment variables
    setup.set_test_env_vars()
    setup.set_postgres_env_vars()

    # Use fixtures.require for consistent environment checking
    try:
        require.env("testing")
        print("✅ Environment confirmed: testing")
        print("✅ Testing environment variables configured")
        return True
    except RuntimeError:
        print("❌ Environment check failed")
        return False


def check_postgres_connectivity() -> bool:
    """Check PostgreSQL connectivity using the existing check_postgres.sh script."""
    print("🔍 Running PostgreSQL connectivity check...")

    try:
        # Run the existing postgres checker script
        result = subprocess.run(['./scripts/check_postgres.sh'],
                                capture_output=True,
                                text=True,
                                timeout=30)
    except subprocess.TimeoutExpired:
        print("❌ PostgreSQL check timed out")
        return False
    except FileNotFoundError:
        print("❌ scripts/check_postgres.sh script not found")
        return False
    except Exception as e:
        print(f"❌ Error running PostgreSQL check: {e}")
        return False
    else:
        if result.returncode == 0:
            # Show the output from scripts/check_postgres.sh
            print(result.stdout)
            return True
        else:
            print("❌ PostgreSQL check failed")
            print(result.stderr)
            return False


def main():
    """Main setup function."""
    print("🏫 Campus Testing Environment Setup")
    print("=" * 40)
    print("")

    # Step 1: Check environment
    if not check_environment():
        sys.exit(1)
    print("")

    # Step 2: Check PostgreSQL connectivity using existing script
    if not check_postgres_connectivity():
        print("")
        print("💡 Troubleshooting:")
        print("   - Ensure devcontainer is running")
        print("   - Check the PostgreSQL status above for detailed diagnostics")
        print("   - Run './scripts/check_postgres.sh' separately for more information")
        sys.exit(1)
    print("")

    # Step 3: Initialize all fixtures in dependency order
    print("🔧 Initializing all testing fixtures...")
    print("")

    try:
        # Initialize vault first (creates CLIENT_ID/CLIENT_SECRET)
        print("🔐 Initializing vault fixtures...")
        vault.init()
        print("✅ Vault fixtures initialized")
        print("")

        # Initialize yapper (creates yapperdb + vault secrets, no service)
        print("📢 Initializing yapper fixtures...")
        yapper.init()
        print("✅ Yapper fixtures initialized")
        print("")

        # Initialize storage (creates storagedb + vault secrets)
        print("🗃️  Initializing storage fixtures...")
        storage.init()
        print("✅ Storage fixtures initialized")
        print("")

    except Exception as e:
        print(f"❌ Failed to initialize fixtures: {e}")
        sys.exit(1)

    print("🎉 Complete testing environment setup finished!")
    print("")
    print("📊 Environment variables set:")
    print(f"   CLIENT_ID={env.CLIENT_ID or 'not set'}")
    print(f"   CLIENT_SECRET={env.CLIENT_SECRET or 'not set'}")
    print("")
    print("🚀 Next step:")
    print("   Run: ./start_testing.py   (starts vault + apps services)")
    print("")


if __name__ == '__main__':
    main()
