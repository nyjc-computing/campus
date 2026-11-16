#!/usr/bin/env python3
"""Seed the public OAuth client ('guest') into the database.

Creates the public client used by CLI/device applications for the OAuth
2.0 Device Authorization Flow (RFC 8628), if it does not already exist.
Idempotent: safe to re-run.

This seed cannot go through the HTTP API because creating a client
requires an authenticated token, which requires completing the device
flow, which requires this client to exist (chicken-and-egg). It must be
applied directly against storage.

The seed also runs automatically at auth service startup; this script
exists for manual recovery and for initial database setup.

Usage (on Railway where POSTGRESDB_URI is available):
    python scripts/seed_public_oauth_client.py
"""

import os
import sys

# Set DEPLOY to avoid vault lookup for POSTGRESDB_URI
os.environ.setdefault('DEPLOY', 'campus.auth')

# Make the campus package importable when run from a repo checkout
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if 'POSTGRESDB_URI' not in os.environ:
    print("WARNING: POSTGRESDB_URI not set in environment")
    print("Proceeding - the storage backend will fail if unconfigured")

import campus.config
from campus.auth.resources.client import (
    ensure_public_client,
    ensure_public_client_schema,
)

print("=" * 80)
print("SEEDING PUBLIC OAUTH CLIENT")
print("=" * 80)

try:
    # Align the table schema first (no-op where not applicable), so the
    # seed works on databases whose vault_clients table predates PR #604
    ensure_public_client_schema()
    created = ensure_public_client()
except Exception as e:
    print(f"✗ Error seeding public OAuth client: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

client_id = campus.config.PUBLIC_OAUTH_CLIENT_ID
if created:
    print(f"✓ Created public OAuth client '{client_id}' (is_public, no secret)")
else:
    print(f"✓ Public OAuth client '{client_id}' already exists")

print("=" * 80)
print("DONE")
print("=" * 80)
