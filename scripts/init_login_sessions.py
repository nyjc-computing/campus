#!/usr/bin/env python3
"""Initialize login sessions collection only."""

import os
import sys

# Set DEPLOY to avoid vault lookup for POSTGRESDB_URI
os.environ['DEPLOY'] = 'campus.auth'

# Load POSTGRESDB_URI from the service environment
if 'POSTGRESDB_URI' not in os.environ:
    print("ERROR: POSTGRESDB_URI not set in environment")
    print("This script must be run on Railway where POSTGRESDB_URI is available")
    sys.exit(1)

sys.path.insert(0, '/workspaces/nyjc-computing/campus')

print("=" * 80)
print("INITIALIZING LOGIN SESSIONS COLLECTION")
print("=" * 80)

from campus.auth.resources.login import LoginSessionsResource

print("\nInitializing login sessions collection...")
try:
    LoginSessionsResource.init_storage()
    print("✓ Login sessions collection initialized successfully")
except Exception as e:
    print(f"✗ Error initializing login sessions collection: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("LOGIN SESSIONS COLLECTION INITIALIZED SUCCESSFULLY")
print("=" * 80)
