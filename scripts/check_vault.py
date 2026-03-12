#!/usr/bin/env python3
"""Check what's in the vault storage."""

import os
import sys

sys.path.insert(0, '/workspaces/nyjc-computing/campus')

import campus.storage

# Recreate vault_storage exactly as in vault.py
vault_storage = campus.storage.get_table("vault")

# Get CLIENT_ID from environment
client_id = os.environ.get('CLIENT_ID')
print(f"Using CLIENT_ID: {client_id}")
print("=" * 60)

# Check what's in the google vault
print("\nQuerying google vault for CLIENT_ID:")
print(f"  vault_storage.get_matching({{'key': 'CLIENT_ID', 'label': 'google'}})")

rec = vault_storage.get_matching({"key": "CLIENT_ID", "label": "google"})

print(f"\nResult type: {type(rec)}")
print(f"Result: {rec}")

if rec:
    print(f"\nNumber of records: {len(rec)}")
    for i, record in enumerate(rec):
        print(f"\nRecord {i}:")
        for k, v in record.items():
            if k == "value" and v:
                masked = v[:20] + "..." if len(v) > 20 else v
                print(f"  {k}: {masked}")
            else:
                print(f"  {k}: {v}")
else:
    print("\n✗ No records found!")

# Also check all google vault entries
print("\n" + "=" * 60)
print("All entries in google vault:")
all_google = vault_storage.get_matching({"label": "google"})
if all_google:
    print(f"Found {len(all_google)} entries:")
    for rec in all_google:
        key = rec.get("key", "N/A")
        print(f"  - {key}")
else:
    print("  (no entries)")

# Check all vault labels
print("\n" + "=" * 60)
print("All vault labels:")
all_vaults = vault_storage.get_all()
labels = set(rec.get("label") for rec in all_vaults if rec.get("label"))
for label in sorted(labels):
    count = len([r for r in all_vaults if r.get("label") == label])
    print(f"  - {label}: {count} entries")
