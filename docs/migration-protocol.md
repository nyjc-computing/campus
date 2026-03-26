# Campus Storage Migration Protocol

## Overview

This document defines the storage migration protocol for Campus. Migrations are versioned changes to database schemas and data that evolve the storage layer over time while maintaining data integrity and enabling rollback.

**Design Philosophy**: Simple, explicit, and auditable. For ~2000 users, we prioritize clarity over automation complexity.

---

## Requirements

Per [issue #27](https://github.com/nyjc-computing/campus/issues/27):

1. **Initialize the app** - Apply pending migrations on deployment
2. **Update existing data** - Transform data when schemas change
3. **Cross-database migration** - Support PostgreSQL tables and MongoDB documents
4. **Rollback/restore** - Ability to revert migrations
5. **Audit logging** - Record all migration actions for investigation

---

## Architecture

### Storage Types

| Storage Type | Backend | Use Case |
|-------------|---------|----------|
| **Tables** | PostgreSQL | Relational data with fixed schema (users, sessions, clients) |
| **Documents** | MongoDB | Flexible JSON-like objects (assignments, submissions) |
| **Objects** | S3-compatible | Binary blobs (files, attachments) |

### Migration Structure

```
campus/storage/migrations/
├── __init__.py           # Migration runner interface
├── state.py              # Migration state tracking (uses storage layer)
├── runner.py             # Main migration execution logic
├── scripts/
│   ├── migrate.py        # CLI entry point: `campus migrate`
│   └── rollback.py       # CLI entry point: `campus rollback`
└── migrations/
    ├── 001_init_assignments.py
    ├── 002_init_submissions.py
    ├── 003_add_response_timestamps.py
    └── ...
```

---

## Transaction Strategy

### Design Decision: Autocommit per Migration, Atomic Within

Each migration file commits independently, but operations within a single migration are atomic.

```python
# Each migration is ONE transaction boundary
def upgrade():
    """All operations in this migration commit together."""
    with PostgreSQLTransaction():
        # Multiple statements execute atomically
        cursor.execute("ALTER TABLE submissions ADD COLUMN status TEXT")
        cursor.execute("UPDATE submissions SET status = 'pending'")
        # If anything fails, entire upgrade() rolls back
```

**Transaction boundary = migration file**, not individual statements.

### Why This Approach?

| Factor | Autocommit per Migration | Single Atomic Transaction |
|--------|-------------------------|---------------------------|
| **Failure recovery** | Manual rollback via `downgrade()` | Automatic rollback |
| **Large datasets** | ✅ Handles 10k+ rows with batching | ❌ Transaction timeout |
| **Cross-storage** | ✅ Works with PostgreSQL + MongoDB | ❌ No cross-DB transactions |
| **Intermediate states** | ⚠️ Partial if migration fails | ✅ Always consistent |
| **Testing** | ⚠️ Must test downgrade path | ✅ Simpler error handling |

### Trade-off Analysis

**Autocommit with Downgrade (Chosen)**

*Pros:*
- Resilient to partial failures - failed migration leaves earlier migrations intact
- Works with large datasets - no single transaction timeout for bulk updates
- Cross-database compatible - MongoDB and PostgreSQL can migrate independently
- Progress visibility - `_migrations` table shows exactly what's been applied
- Safe for long-running operations - data backfills won't hit transaction limits

*Cons:*
- No automatic atomic rollback - if migration fails, database in intermediate state
- Manual cleanup required - must run `campus rollback` to reverse failed migrations
- Potential inconsistency - app could start mid-migration if deploy continues unchecked
- Harder testing - must explicitly test `downgrade()` path

**Alternative: All-or-Nothing Transaction**

*Pros:*
- Automatic safety - any failure rolls back entire migration
- No intermediate states - database always in consistent schema
- Simpler error handling - just let transaction fail

*Cons:*
- Transaction limits - PostgreSQL has size/duration constraints
- Fails with large datasets - updating thousands of rows times out
- Not cross-storage compatible - can't atomically update PostgreSQL + MongoDB
- Blocks longer - tables locked during entire transaction
- Memory pressure - large transactions consume connection resources

### For Campus (~2000 users)

The hybrid approach balances safety with practicality:

1. **One migration = one logical change** - Natural atomic boundary
2. **Manageable transaction sizes** - ~2000 users means reasonable single-migration volume
3. **Clear rollback semantics** - `downgrade()` reverses at same boundary
4. **Matches existing patterns** - `init_from_schema()` already uses explicit transactions

### For Large Migrations

Document batched approach for operations that exceed single transaction limits:

```python
def upgrade():
    """For very large tables, process in batches."""
    batch_size = 100
    for offset in range(0, total_rows, batch_size):
        with PostgreSQLTransaction():
            # Each batch is atomic
            for row in get_batch(offset, batch_size):
                transform_and_update(row)
        # Commits between batches
```

This pattern provides atomicity at the batch level while avoiding transaction timeouts.

---

## Migration File Format

Each migration is a Python module with:

1. **Revision ID** - Sequential 3-digit number
2. **Description** - Human-readable change summary
3. **upgrade()** - Forward transformation
4. **downgrade()** - Reverse transformation
5. **Storage type** - One of: `table`, `document`, `object`

### Accessing Storage: Type-Safe vs String-Based

**Option 1: Import from resource module (type-safe, recommended)**

```python
from campus.api.resources import SubmissionsResource

def upgrade():
    """Access collection through resource - no typos possible."""
    submissions = SubmissionsResource._storage  # Internal access
```

**Option 2: Direct string access (simple, common in migrations)**

```python
from campus.storage import get_collection

def upgrade():
    """Direct access - be careful with typos."""
    submissions = get_collection("submissions")
```

> **Note:** Using resource imports (`campus.api.resources.*`) provides type safety and prevents typos. Direct string access is simpler but requires careful testing.

### Example Migration

```python
"""Add response timestamps to submissions.

Revision ID: 003
Create Date: 2025-03-13
Storage Type: document
"""

from datetime import datetime, UTC
from campus.storage import get_collection


REVISION_ID = "003"
DESCRIPTION = "Add response timestamps to submissions"
STORAGE_TYPE = "document"


def upgrade():
    """Add created_at field to existing responses."""
    submissions = get_collection("submissions")

    # Get all submissions with responses
    all_docs = submissions.get_matching({})

    for doc in all_docs:
        updated_responses = []
        for response in doc.get("responses", []):
            # Add timestamp if not present
            if "created_at" not in response:
                response["created_at"] = datetime.now(UTC).isoformat()
            updated_responses.append(response)

        # Update document
        if updated_responses:
            submissions.update_by_id(doc["id"], {"responses": updated_responses})


def downgrade():
    """Remove created_at field from responses."""
    submissions = get_collection("submissions")

    all_docs = submissions.get_matching({})

    for doc in all_docs:
        updated_responses = []
        for response in doc.get("responses", []):
            # Strip out created_at
            response.pop("created_at", None)
            updated_responses.append(response)

        submissions.update_by_id(doc["id"], {"responses": updated_responses})
```

---

## Migration State Tracking

Migrations track their state using the storage layer itself:

### PostgreSQL Schema (for state tracking)

```sql
CREATE TABLE IF NOT EXISTS "_migrations" (
    "id" TEXT PRIMARY KEY,           -- Revision ID (e.g., "001", "002")
    "description" TEXT NOT NULL,     -- Human-readable description
    "storage_type" TEXT NOT NULL,    -- "table", "document", "object"
    "applied_at" TIMESTAMP NOT NULL, -- When migration was applied
    "rollback_at" TIMESTAMP NULL     -- When migration was rolled back (if applicable)
);
```

### State Interface

```python
# campus/storage/migrations/state.py

from campus.storage import get_table
from datetime import datetime, UTC

class MigrationState:
    """Track migration application state."""

    def __init__(self):
        self._table = get_table("_migrations")

    def init_state_table(self):
        """Initialize the _migrations table if not exists."""
        # Uses init_from_schema() - allowed for system table
        sql = '''CREATE TABLE IF NOT EXISTS "_migrations" (
            "id" TEXT PRIMARY KEY,
            "description" TEXT NOT NULL,
            "storage_type" TEXT NOT NULL,
            "applied_at" TIMESTAMP NOT NULL,
            "rollback_at" TIMESTAMP NULL
        );'''
        from campus.storage.tables.backend.postgres import PostgreSQLTable
        table = PostgreSQLTable("_migrations")
        table.init_from_schema(sql)

    def record_migration(self, revision_id: str, description: str, storage_type: str):
        """Record a successful migration."""
        self._table.insert_one({
            "id": revision_id,
            "description": description,
            "storage_type": storage_type,
            "applied_at": datetime.now(UTC).isoformat(),
            "rollback_at": None
        })

    def get_applied_migrations(self) -> set[str]:
        """Get set of applied migration IDs."""
        return {row["id"] for row in self._table.get_matching({})}

    def mark_rollback(self, revision_id: str):
        """Mark a migration as rolled back."""
        self._table.update_by_id(revision_id, {
            "rollback_at": datetime.now(UTC).isoformat()
        })

    def is_applied(self, revision_id: str) -> bool:
        """Check if a migration has been applied."""
        try:
            self._table.get_by_id(revision_id)
            return True
        except NotFoundError:
            return False
```

---

## Migration Runner

```python
# campus/storage/migrations/runner.py

import importlib
from pathlib import Path
from campus.yapper import Yapper
from .state import MigrationState

class MigrationRunner:
    """Execute and track migrations."""

    def __init__(self, migrations_dir: Path):
        self.migrations_dir = migrations_dir
        self.state = MigrationState()
        self.logger = Yapper()

    def discover_migrations(self) -> list[dict]:
        """Find all migration files and return sorted list."""
        migrations = []
        for file in self.migrations_dir.glob("*.py"):
            if file.name.startswith("_"):
                continue

            module = importlib.import_module(f".migrations.{file.stem}", package="campus.storage")
            migrations.append({
                "id": module.REVISION_ID,
                "description": module.DESCRIPTION,
                "storage_type": module.STORAGE_TYPE,
                "module": module,
                "path": file
            })

        return sorted(migrations, key=lambda m: m["id"])

    def upgrade(self, target: str | None = None):
        """Apply pending migrations up to target revision."""
        self.state.init_state_table()
        applied = self.state.get_applied_migrations()
        migrations = self.discover_migrations()

        for migration in migrations:
            if migration["id"] in applied:
                continue
            if target and migration["id"] > target:
                break

            print(f"Applying {migration['id']}: {migration['description']}")
            migration["module"].upgrade()
            self.state.record_migration(
                migration["id"],
                migration["description"],
                migration["storage_type"]
            )

            # Log migration event via Yapper
            self.logger.emit("migration.applied", {
                "revision_id": migration["id"],
                "description": migration["description"],
                "storage_type": migration["storage_type"]
            })
            print(f"  ✓ Applied {migration['id']}")

    def downgrade(self, target: str):
        """Rollback migrations back to target revision."""
        self.state.init_state_table()
        applied = self.state.get_applied_migrations()
        migrations = list(reversed(self.discover_migrations()))

        for migration in migrations:
            if migration["id"] not in applied:
                continue
            if migration["id"] <= target:
                break

            print(f"Rolling back {migration['id']}: {migration['description']}")
            migration["module"].downgrade()
            self.state.mark_rollback(migration["id"])

            # Log rollback event via Yapper
            self.logger.emit("migration.rolled_back", {
                "revision_id": migration["id"],
                "description": migration["description"],
                "storage_type": migration["storage_type"]
            })
            print(f"  ✓ Rolled back {migration['id']}")
```

---

## CLI Interface

Add to `campus` CLI via `main.py`:

```python
# main.py additions

def migrate(target: str | None = None):
    """Run database migrations."""
    from campus.storage.migrations import MigrationRunner
    from pathlib import Path

    migrations_dir = Path(__file__).parent / "storage" / "migrations" / "migrations"
    runner = MigrationRunner(migrations_dir)
    runner.upgrade(target)
    print("Migration complete.")


def rollback(target: str):
    """Rollback to a specific migration."""
    from campus.storage.migrations import MigrationRunner
    from pathlib import Path

    migrations_dir = Path(__file__).parent / "storage" / "migrations" / "migrations"
    runner = MigrationRunner(migrations_dir)
    runner.downgrade(target)
    print("Rollback complete.")


if __name__ == "__main__":
    import sys
    command = sys.argv[1] if len(sys.argv) >= 2 else None

    if command == "migrate":
        target = sys.argv[2] if len(sys.argv) >= 3 else None
        migrate(target)
    elif command == "rollback":
        target = sys.argv[2]
        rollback(target)
    else:
        main(deployment=command)
```

### Usage

```bash
# Apply all pending migrations
campus migrate

# Apply up to specific revision
campus migrate 003

# Rollback to specific revision
campus rollback 002
```

---

## Deployment Integration

### Automatic Migration on Deploy

Add to deployment configuration (`wsgi.py` or app factory):

```python
# wsgi.py or apps/*/factory.py

from campus.storage.migrations import MigrationRunner
from pathlib import Path
import os

def create_app():
    app = Flask(__name__)

    # Run migrations on app startup in production
    if os.getenv("ENV") in ("staging", "production"):
        try:
            migrations_dir = Path(__file__).parent / "storage" / "migrations" / "migrations"
            runner = MigrationRunner(migrations_dir)
            runner.upgrade()
        except Exception as e:
            # Log but don't fail deployment
            app.logger.error(f"Migration failed: {e}")

    return app
```

### Pre-Deployment Checklist

1. **Backup database** before running migrations in production
2. **Test migrations** on staging with production-like data
3. **Review downgrade logic** - ensure rollback path exists
4. **Monitor logs** via Yapper events for migration completion

---

## Best Practices

### 1. Idempotent Migrations

Migrations should be safe to run multiple times:

```python
def upgrade():
    """Add index if not exists."""
    table = get_table("submissions")
    # Check before creating
    try:
        table.execute('CREATE INDEX idx_submissions_course ON "submissions"("course_id")')
    except psycopg2.errors.DuplicateTable:
        pass  # Index already exists
```

### 2. Zero-Downtime for Schema Changes

For PostgreSQL schema changes with active users:

1. **Add columns** as nullable first
2. **Backfill data** in separate migration
3. **Add constraints** only after backfill complete
4. **Drop old columns** only after verifying usage

### 3. Data Migration Batching

For large collections, process in batches:

```python
def upgrade():
    """Backfill data for all users."""
    users = get_table("users")
    batch_size = 100
    offset = 0

    while True:
        batch = users.get_matching({}).skip(offset).limit(batch_size)
        if not batch:
            break

        for user in batch:
            # Transform data
            users.update_by_id(user["id"], {...})

        offset += batch_size
```

### 4. Transaction Safety

Wrap related changes in transactions. See [Transaction Strategy](#transaction-strategy) for rationale.

```python
def upgrade():
    """Make multiple related changes atomically within this migration."""
    from campus.storage.tables.backend.postgres import PostgreSQLTable

    table = PostgreSQLTable("assignments")
    with table._get_connection() as conn:
        with conn.cursor() as cursor:
            # These statements commit together as one unit
            cursor.execute("ALTER TABLE assignments ADD COLUMN new_field TEXT")
            cursor.execute("UPDATE assignments SET new_field = default_value")
            conn.commit()
            # If either fails, both roll back automatically
```

**Key principle:** Each `upgrade()`/`downgrade()` function is its own transaction boundary. Don't commit mid-migration.

---

## Migration Types

### Type 1: Schema Migration (DDL)

Changes to table/collection structure:

```python
# PostgreSQL - Add column
def upgrade():
    table = PostgreSQLTable("users")
    table.init_from_schema(
        'ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "display_name" TEXT;'
    )

def downgrade():
    table = PostgreSQLTable("users")
    table.init_from_schema(
        'ALTER TABLE "users" DROP COLUMN IF EXISTS "display_name";'
    )
```

### Type 2: Data Migration (DML)

Transform existing data:

```python
def upgrade():
    users = get_table("users")
    all_users = users.get_matching({})

    for user in all_users:
        if "email" in user and "@" not in user["email"]:
            # Fix malformed emails
            users.update_by_id(user["id"], {"email": None})
```

### Type 3: Cross-Storage Migration

Move data between storage types:

```python
def upgrade():
    """Migrate from table to document storage."""
    old_table = get_table("sessions")
    new_collection = get_collection("sessions")

    for session in old_table.get_matching({}):
        new_collection.insert_one(session)
```

---

## Rollback Protocol

### Pre-Rollback Checklist

1. **Backup current state** - Export data before rollback
2. **Verify downgrade logic** - Test on staging first
3. **Check dependencies** - Ensure no later migrations depend on this one
4. **Plan forward migration** - Know how you'll re-apply after rollback

### Rollback Execution

```bash
# 1. Check current state
campus migrate status

# 2. Backup production data
pg_dump $POSTGRESDB_URI > backup_$(date +%Y%m%d).sql

# 3. Rollback to safe revision
campus rollback 002

# 4. Verify application health
curl -f https://api.campus.nyjc.app/health || exit 1
```

---

## Event Logging via Yapper

All migrations emit events for audit and monitoring:

```python
# Events emitted:
logger.emit("migration.applied", {
    "revision_id": "003",
    "description": "Add response timestamps",
    "storage_type": "document",
    "applied_at": "2025-03-13T10:30:00Z"
})

logger.emit("migration.rolled_back", {
    "revision_id": "003",
    "description": "Add response timestamps",
    "storage_type": "document",
    "rolled_back_at": "2025-03-13T11:00:00Z"
})

logger.emit("migration.failed", {
    "revision_id": "004",
    "error": "Duplicate key violation",
    "traceback": "..."
})
```

### Consuming Migration Events

```python
from campus.yapper import Yapper

yapper = Yapper()

@yapper.on_event("migration.applied")
def log_migration(event):
    """Send migration notification to admins."""
    send_alert(f"Migration {event.data['revision_id']} applied: {event.data['description']}")
```

---

## Appendix: Migration Template

```python
"""{Description}.

Revision ID: {XXX}
Create Date: {YYYY-MM-DD}
Storage Type: {table/document/object}
"""

from campus.storage import {{get_table, get_collection}}

REVISION_ID = "{XXX}"
DESCRIPTION = "{Description}"
STORAGE_TYPE = "{table/document/object}"


def upgrade():
    """Apply this migration."""
    # TODO: Implement forward migration
    pass


def downgrade():
    """Reverse this migration."""
    # TODO: Implement rollback
    pass
```

---

## References

- [Issue #27: Storage Migration Protocol](https://github.com/nyjc-computing/campus/issues/27)
- [Campus Storage Architecture](../architecture.md)
- [PostgreSQL Table Backend](../campus/storage/tables/backend/postgres.py)
- [MongoDB Document Backend](../campus/storage/documents/backend/mongodb.py)
- [Yapper Event Framework](../campus/yapper/base.py)
