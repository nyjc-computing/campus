"""Backfill Mongo documents to the RFC 6749 scope string shape.

Revision ID: 005
Create Date: 2026-09-30

Completes the storage side of the #648 deprecation (decision 4 end
state): documents in the `tokens`, `auth_sessions` and `device_codes`
collections stop storing the `scopes` list and store the RFC 6749
`scope` string instead. Model from_storage() tolerates both shapes, so
this migration is safe to run any time after the flip deploys and is
idempotent.

For `tokens` (checklist item 5) this migration also backfills the
#648-added fields onto legacy documents so reads no longer depend on
read-time derivation:
- expires_in: derived from expires_at - created_at when missing
- token_type: defaulted to "Bearer" when missing
- provider_fields: defaulted to {} when missing

Run (from a context where the storage secrets resolve, e.g. via
`railway ssh` into campus.auth):

    python migrations/005_backfill_scope_string.py            # dry run
    python migrations/005_backfill_scope_string.py --apply    # write
"""

import argparse
import typing

from campus.common import schema
from campus.storage import get_collection

SCOPE_COLLECTIONS = ("auth_sessions", "device_codes")


def _derive_expires_in(record: dict) -> int | None:
    """Derive the token lifetime in seconds from its expiry timestamps."""
    expires_at = record.get("expires_at")
    created_at = record.get("created_at")
    if expires_at is None or created_at is None:
        return None
    delta = (
        schema.DateTime(str(expires_at)).to_datetime()
        - schema.DateTime(str(created_at)).to_datetime()
    )
    return int(delta.total_seconds())


def _token_update(record: dict) -> dict[str, typing.Any]:
    """Compute the migration update for one token document."""
    update: dict[str, typing.Any] = {}
    if "scopes" in record:
        update["scope"] = " ".join(str(s) for s in record["scopes"])
        update["scopes"] = None  # sentinel: unset
    if "expires_in" not in record or record["expires_in"] is None:
        expires_in = _derive_expires_in(record)
        if expires_in is not None:
            update["expires_in"] = expires_in
    if not record.get("token_type"):
        update["token_type"] = "Bearer"
    if "provider_fields" not in record or record["provider_fields"] is None:
        update["provider_fields"] = {}
    return update


def _scope_update(record: dict) -> dict[str, typing.Any]:
    """Compute the migration update for one session/device document."""
    if "scopes" not in record:
        return {}
    return {
        "scope": " ".join(str(s) for s in record["scopes"]),
        "scopes": None,  # sentinel: unset
    }


def _backfill(collection_name: str, update_fn, apply: bool) -> tuple[int, int]:
    """Run one collection's backfill; return (converted, unchanged)."""
    collection = get_collection(collection_name)
    converted = unchanged = 0
    for record in collection.get_matching({}):
        update = update_fn(record)
        if not update:
            unchanged += 1
            continue
        if apply:
            collection.update_by_id(record["id"], update)
        converted += 1
    return converted, unchanged


def upgrade(apply: bool = False) -> None:
    """Backfill scope strings and legacy token fields."""
    for name in SCOPE_COLLECTIONS:
        converted, unchanged = _backfill(name, _scope_update, apply)
        print(f"{name}: {converted} to convert, {unchanged} already conforming")
    converted, unchanged = _backfill("tokens", _token_update, apply)
    print(f"tokens: {converted} to convert, {unchanged} already conforming")
    if not apply:
        print("dry run: no changes written (pass --apply to write)")


def downgrade() -> None:
    """Restore the scopes list from the scope string.

    Best-effort: the token field backfill (expires_in, token_type,
    provider_fields) is intentionally not reverted — the fields are
    additive and harmless to pre-#648 readers.
    """
    for name in SCOPE_COLLECTIONS:
        collection = get_collection(name)
        count = 0
        for record in collection.get_matching({}):
            if "scope" in record:
                collection.update_by_id(record["id"], {
                    "scopes": str(record["scope"]).split(),
                    "scope": None,
                })
                count += 1
        print(f"{name}: {count} reverted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill Mongo documents to the scope-string shape (#648)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write changes (default: dry run)"
    )
    args = parser.parse_args()
    upgrade(apply=args.apply)
