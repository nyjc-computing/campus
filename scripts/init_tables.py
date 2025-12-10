#!/usr/bin/env python3
"""Initialize database tables for campus.auth."""

import os
import sys

# Set DEPLOY to avoid vault lookup for POSTGRESDB_URI
os.environ['DEPLOY'] = 'campus.auth'

# Load POSTGRESDB_URI from the service environment
# We need to provide it directly to avoid circular dependencies
if 'POSTGRESDB_URI' not in os.environ:
    print("ERROR: POSTGRESDB_URI not set in environment")
    print("This script must be run on Railway where POSTGRESDB_URI is available")
    sys.exit(1)

sys.path.insert(0, '/workspaces/nyjc-computing/campus')

print("=" * 80)
print("INITIALIZING DATABASE TABLES")
print("=" * 80)

from campus.auth.resources.vault import VaultsResource
from campus.auth.resources.client import ClientsResource
from campus.auth.resources.user import UsersResource
from campus.auth.resources.session import AuthSessionsResource
from campus.auth.resources.credentials import CredentialsResource
from campus.auth.resources.login import LoginSessionsResource

print("\nInitializing vault table...")
VaultsResource.init_storage()
print("✓ Vault table initialized")

print("\nInitializing client tables...")
ClientsResource.init_storage()
print("✓ Client tables initialized")

print("\nInitializing user table...")
UsersResource.init_storage()
print("✓ User table initialized")

print("\nInitializing auth session collection...")
AuthSessionsResource.init_storage()
print("✓ Auth session collection initialized")

print("\nInitializing credentials tables...")
CredentialsResource.init_storage()
print("✓ Credentials tables initialized")

print("\nInitializing login session collection...")
LoginSessionsResource.init_storage()
print("✓ Login session collection initialized")

print("\n" + "=" * 80)
print("ALL TABLES INITIALIZED SUCCESSFULLY")
print("=" * 80)
