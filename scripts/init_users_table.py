#!/usr/bin/env python3
"""Initialize users table only."""

import os
import sys

# Set DEPLOY to avoid vault lookup for POSTGRESDB_URI
os.environ['DEPLOY'] = 'campus.auth'

# Load POSTGRESDB_URI from .env file if not already set
if 'POSTGRESDB_URI' not in os.environ:
    env_file = '/workspaces/nyjc-computing/campus/.env'
    if os.path.exists(env_file):
        print(f"Loading environment from {env_file}")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
    
    if 'POSTGRESDB_URI' not in os.environ:
        print("ERROR: POSTGRESDB_URI not set in environment or .env file")
        sys.exit(1)

sys.path.insert(0, '/workspaces/nyjc-computing/campus')

print("=" * 80)
print("INITIALIZING USERS TABLE")
print("=" * 80)

from campus.auth.resources.user import UsersResource

print("\nInitializing users table...")
try:
    UsersResource.init_storage()
    print("✓ Users table initialized successfully")
except Exception as e:
    print(f"✗ Error initializing users table: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("USERS TABLE INITIALIZED SUCCESSFULLY")
print("=" * 80)
