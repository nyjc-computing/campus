# campus-storage

`campus-storage` provides a unified storage abstraction layer for the Campus platform.
It allows application code to interact with different databases through a consistent interface.

Supported storage models:

* **Tables** – structured rows with a fixed schema (relational databases)
* **Documents** – flexible JSON-like objects (document databases)

Current backends:

* Tables → PostgreSQL
* Documents → MongoDB

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
* `get_matching(query)`
* `insert_one(data)`
* `update_by_id(id, update)`
* `update_matching(query, update)`
* `delete_by_id(id)`
* `delete_matching(query)`

Each record/document is expected to include:

* `id` – primary identifier
* `created_at` – creation timestamp

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
