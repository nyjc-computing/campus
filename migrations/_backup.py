"""Backup and restore for Mongo rewrite migrations (#27 phase 3, #746).

`downgrade()` cannot restore values a rewrite has already overwritten —
a document backup can. Rewrite migrations (the 005 dry-run-by-default
pattern) therefore accept `--backup PATH` and dump every document they
are about to touch, BEFORE the first write, via `write_backup`. The
protocol doc's file conventions carry the full rule; a rewrite
migration's docstring states its backup usage.

Usage inside a rewrite migration:

    from migrations._backup import write_backup
    ...
    if args.backup:
        write_backup(args.backup, REVISION, __file__,
                     {"tokens": token_docs, "auth_sessions": session_docs})

Envelope format (`campus-migration-backup/1`): a JSON object carrying
the producing migration's identity, a UTC timestamp, the operator, and
the affected documents keyed by collection name. `default=str` keeps
non-JSON values (datetimes) representable — a restore writes their
string form, which is what the models already parse.

Restore from the same context a migration runs in (storage secrets
resolve):

    python migrations/_backup.py show backup.json            # summarize
    python migrations/_backup.py restore backup.json --dry-run
    python migrations/_backup.py restore backup.json
    python migrations/_backup.py restore backup.json --collection tokens

Restore semantics mirror update_by_id: every backed-up field is set,
fields whose backed-up value is None are unset, and fields the rewrite
ADDED after the backup are left in place (they carry no old value to
restore — the migration's downgrade() docstring names them; 005's
`scope` unset-sentinel is the pattern). Every document must carry an
"id"; the whole file is validated before anything is written.
"""

import argparse
import getpass
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKUP_FORMAT = "campus-migration-backup/1"


def _get_user() -> str | None:
    """Best-effort operator identity for the envelope's created_by."""
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - identity is optional metadata
        return None


def write_backup(
    path: str | Path,
    revision: str,
    filename: str,
    collections: dict[str, list[dict]],
) -> int:
    """Dump affected documents to PATH as a versioned JSON envelope.

    Returns the number of documents written. Call this BEFORE the
    rewrite's first write; a migration that finds nothing to change
    backs up an empty envelope, which still records the no-op.
    """
    envelope = {
        "format": BACKUP_FORMAT,
        "revision": revision,
        "filename": filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": _get_user(),
        "collections": collections,
    }
    Path(path).write_text(
        json.dumps(envelope, indent=2, default=str), encoding="utf-8"
    )
    return sum(len(docs) for docs in collections.values())


def read_backup(path: str | Path) -> dict:
    """Load and validate a backup envelope.

    Raises ValueError for JSON that is not a campus migration backup.
    """
    envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(envelope, dict) or envelope.get("format") != BACKUP_FORMAT:
        raise ValueError(
            f"{path} is not a campus migration backup "
            f"(expected format {BACKUP_FORMAT!r})"
        )
    return envelope


def restore(
    path: str | Path,
    collections: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Write a backup's documents back to their collections.

    `collections` limits the restore to the named collections (default:
    all in the envelope). Every document must carry an "id"; validation
    completes before the first write. Returns {collection: count}.
    Storage is imported lazily so inspection (--dry-run, show) needs no
    secrets.
    """
    envelope = read_backup(path)
    selected = {
        name: docs
        for name, docs in envelope.get("collections", {}).items()
        if collections is None or name in collections
    }
    invalid = [
        f"{name}[{index}]"
        for name, docs in selected.items()
        for index, doc in enumerate(docs)
        if not isinstance(doc, dict) or not doc.get("id")
    ]
    if invalid:
        raise ValueError(
            f"backup documents without an id: {', '.join(invalid)}"
        )

    if dry_run:
        print("dry run: no changes written")
        return {name: len(docs) for name, docs in selected.items()}

    from campus.storage import get_collection
    restored: dict[str, int] = {}
    for name, docs in selected.items():
        collection = get_collection(name)
        for doc in docs:
            collection.update_by_id(doc["id"], doc)
        restored[name] = len(docs)
        print(f"{name}: restored {len(docs)} document(s)")
    return restored


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrations/_backup.py",
        description="Inspect and restore migration document backups (#746).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_parser = subparsers.add_parser(
        "show", help="summarize a backup file",
    )
    show_parser.add_argument("path", metavar="PATH")

    restore_parser = subparsers.add_parser(
        "restore", help="write a backup's documents back to their collections",
    )
    restore_parser.add_argument("path", metavar="PATH")
    restore_parser.add_argument(
        "--collection",
        action="append",
        dest="collections",
        metavar="NAME",
        help="restore only this collection (repeatable; default: all)",
    )
    restore_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and count without writing",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "show":
            envelope = read_backup(args.path)
            print(
                f"{envelope.get('filename', '?')} "
                f"(revision {envelope.get('revision', '?')}, created "
                f"{envelope.get('created_at', '?')} by "
                f"{envelope.get('created_by', '?')})"
            )
            for name, docs in envelope.get("collections", {}).items():
                print(f"  {name}: {len(docs)} document(s)")
            return 0
        restore(args.path, collections=args.collections,
                dry_run=args.dry_run)
        return 0
    except (ValueError, OSError) as e:
        # json.JSONDecodeError is a ValueError; OSError covers a missing
        # or unreadable path
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
