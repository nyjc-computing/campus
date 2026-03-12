#!/usr/bin/env python3
"""Setup vault access for campus OAuth proxy."""

import os
import sys

# Set DEPLOY to avoid vault lookup for POSTGRESDB_URI
os.environ['DEPLOY'] = 'campus.auth'

sys.path.insert(0, '/workspaces/nyjc-computing/campus')

from campus.auth.resources.client import ClientsResource

# Get CLIENT_ID from environment
client_id = os.environ.get('CLIENT_ID')
if not client_id:
    print("ERROR: CLIENT_ID environment variable not set")
    sys.exit(1)

print(f"Checking vault access for CLIENT_ID: {client_id}")
print("=" * 60)

# Get the client resource
print("\nAccessing client resource...")
clients = ClientsResource()
client = clients[client_id]

# Check current permissions
print("\nCurrent permissions:")
permissions = client.access.list()
for label, access in permissions.items():
    print(f"  - {label}: {access}")

# Check if google vault access is needed
if "google" not in permissions:
    print("\n✗ Missing access to 'google' vault")
    print("Granting access to 'google' vault with permission level 15 (ALL)")
    try:
        client.access.grant(vault_label="google", permission=15)
        print("✓ Access granted to 'google' vault")
    except Exception as e:
        print(f"✗ Error granting google vault access: {e}")
        sys.exit(1)
else:
    print(f"\n✓ Already has access to 'google' vault: {permissions['google']}")

# Check if campus vault access is needed
if "campus" not in permissions:
    print("\n✗ Missing access to 'campus' vault")
    print("Granting access to 'campus' vault with permission level 15 (ALL)")
    try:
        client.access.grant(vault_label="campus", permission=15)
        print("✓ Access granted to 'campus' vault")
    except Exception as e:
        print(f"✗ Error granting campus vault access: {e}")
        sys.exit(1)
else:
    print(f"\n✓ Already has access to 'campus' vault: {permissions['campus']}")

# Show final permissions
print("\n" + "=" * 60)
print("Final permissions:")
permissions = client.access.list()
for label, access in permissions.items():
    print(f"  - {label}: {access}")

print("\n" + "=" * 60)
print("Done!")
