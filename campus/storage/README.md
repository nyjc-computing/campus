# campus-storage

`campus-storage` provides a unified storage abstraction layer for the Campus platform.
It allows application code to interact with different databases through a consistent interface.

Supported storage models:

* **Tables** – structured rows with a fixed schema (relational databases)
* **Documents** – flexible JSON-like objects (document databases)

Current backends:

* Tables → PostgreSQL (production), SQLite (testing)
* Documents → MongoDB (production), Memory (testing)

---

# Installation

Install using Poetry:

```bash
poetry install
```

Run this from the directory containing the package's `pyproject.toml`.

---

# Quick Usage

## Tables

```python
from campus.storage import get_table

users = get_table("users")

users.insert_one({"id": "123", "name": "Alice"})
user = users.get_by_id("123")
```

## Documents

```python
from campus.storage import get_collection

events = get_collection("events")

events.insert_one({"type": "meeting", "room": "A101"})
docs = events.get_matching({"type": "meeting"})
```

---

# Storage Interfaces

Both storage types support similar operations:

* `get_by_id(id)`
* `get_matching(query, *, order_by, ascending, limit, offset)`
* `insert_one(data)`
* `update_by_id(id, update)`
* `update_matching(query, update)`
* `delete_by_id(id)`
* `delete_matching(query)`

Each record/document is expected to include:

* `id` – primary identifier
* `created_at` – creation timestamp

---

# Query Operators

The `get_matching()` method supports comparison operators for more expressive queries:

## Available Operators

```python
from campus.storage import gt, gte, lt, lte
```

* `gt(value)` – greater than
* `gte(value)` – greater than or equal
* `lt(value)` – less than
* `lte(value)` – less than or equal

## Examples

### Exact Match (Backward Compatible)

```python
# Simple exact match queries work as before
traces.get_matching({"user_id": "user_123"})
traces.get_matching({"status": "active", "type": "request"})
```

### Comparison Operators

```python
# Greater than: find slow requests (> 1000ms)
traces.get_matching({"duration_ms": gt(1000)})

# Greater than or equal: find recent errors
traces.get_matching({"created_at": gte("2024-01-01"), "status_code": gte(500)})

# Less than: find quick requests
traces.get_matching({"duration_ms": lt(100)})

# Less than or equal: find old records
traces.get_matching({"created_at": lte("2024-01-01")})
```

### Sorting

```python
from campus.storage import get_table

traces = get_table("traces")

# Ascending sort (default)
traces.get_matching({}, order_by="created_at")

# Descending sort
traces.get_matching({}, order_by="created_at", ascending=False)

# Sort by duration
traces.get_matching({"status": "error"}, order_by="duration_ms", ascending=False)
```

### Pagination

```python
# Limit results
traces.get_matching({}, limit=10)

# Skip first N results
traces.get_matching({}, offset=20)

# Combined pagination (page 2, 10 per page)
traces.get_matching({}, order_by="created_at", limit=10, offset=10)
```

### Combining Filters

Multiple fields are treated as implicit AND (all conditions must match):

```python
# Find recent error traces from a specific user
traces.get_matching({
    "user_id": "user_123",
    "status_code": gte(500),
    "created_at": gte("2024-01-01")
})
```

---

# Errors

Common storage errors:

* `StorageError` – base storage exception
* `NotFoundError` – item does not exist
* `NoChangesAppliedError` – update/delete affected zero records

Example:

```python
from campus.storage import NotFoundError

try:
    users.delete_by_id("123")
except NotFoundError:
    print("User not found")
```

---

# Development Utilities

For development/testing only:

```python
from campus.storage import purge_tables, purge_collections, purge_all
```

* `purge_tables()` – delete all table data
* `purge_collections()` – delete all document data
* `purge_all()` – delete everything

⚠️ These operations permanently delete data and should **never be used in production**.
