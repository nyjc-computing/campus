#!/usr/bin/env python3
"""Seed the audit operator API key into the audit database.

Creates the operator key used to manage audit API keys (apikeys:*), if
it does not already exist. Idempotent: safe to re-run; an existing
record is never modified.

This seed cannot go through the HTTP API because creating a key
requires an authenticated key with apikeys:write, which cannot exist
before the first one does (chicken-and-egg). It must be applied
directly against storage. The same seed runs automatically at audit
service startup; this script exists for manual recovery and for
initial database setup.

The key plaintext comes from the AUDIT_OPERATOR_API_KEY env var (the
same variable the startup seed reads). Keep it out of the repo; set it
on the campus.audit deployment as well, so the startup seed can
self-heal after a database reset.

Usage (on Railway where POSTGRESDB_URI is available):
    AUDIT_OPERATOR_API_KEY=audit_v1_<22-char-base64url> \
        python scripts/seed_audit_operator_key.py
"""

import os
import sys

# Set DEPLOY to avoid vault lookup for POSTGRESDB_URI
os.environ.setdefault('DEPLOY', 'campus.audit')

# Make the campus package importable when run from a repo checkout
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if 'AUDIT_OPERATOR_API_KEY' not in os.environ:
    print("ERROR: AUDIT_OPERATOR_API_KEY not set in environment")
    print("Generate one with: "
          "python -c \"from campus.common.utils import secret; "
          "print(secret.generate_audit_api_key())\"")
    sys.exit(1)

if 'POSTGRESDB_URI' not in os.environ:
    print("WARNING: POSTGRESDB_URI not set in environment")
    print("Proceeding - the storage backend will fail if unconfigured")

import campus.config
from campus.audit.resources.apikeys import APIKeysResource, ensure_operator_key

print("=" * 80)
print("SEEDING AUDIT OPERATOR API KEY")
print("=" * 80)

try:
    # Ensure the apikeys table exists (idempotent CREATE TABLE IF NOT
    # EXISTS), then seed.
    APIKeysResource.init_storage()
    created = ensure_operator_key()
except Exception as e:
    print(f"✗ Error seeding audit operator key: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

key_id = campus.config.AUDIT_OPERATOR_API_KEY_ID
if created:
    print(f"✓ Created audit operator key '{key_id}' "
          f"(scopes: {', '.join(campus.config.AUDIT_OPERATOR_API_KEY_SCOPES)})")
else:
    print(f"✓ Audit operator key '{key_id}' already exists (not modified)")

print("=" * 80)
print("DONE")
print("=" * 80)
