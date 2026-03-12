# `campus.common.schema`

Schema definitions, enums, and constants used across Campus.

## What this provides

- **OpenAPI-aligned datatypes**: Small wrapper types that match OpenAPI 3 data
  types and common string formats.
- **Domain aliases**: Campus-specific ID types (`CampusID`, `UserID`).
- **Shared constants**: e.g. the primary key field name (`CAMPUS_KEY`).

## Folder structure

```text
campus/common/schema/
  README.md
  __init__.py     # public API surface (re-exports)
  base.py         # domain aliases + small shared types
  openapi.py      # OpenAPI-style datatypes
```

## Public API

Downstream code should typically import from the package root:

```python
from campus.common import schema
```

The public names are re-exported in `__init__.py` so callers don’t need to reach
into module internals.

### Constants

- **`schema.CAMPUS_KEY`**: The canonical primary key field name. Currently
  `"id"`.

## Usage examples

### IDs

```python
from campus.common import schema

circle_id = schema.CampusID("circle-123")
user_id = schema.UserID("user@example.com")
```

### Timestamps

```python
from campus.common import schema

now = schema.DateTime.utcnow()
in_5m = schema.DateTime.utcafter(minutes=5)

today = schema.Date.today()
tomorrow = schema.Date.utcafter(days=1)
```

### URLs and emails

```python
from campus.common import schema

u = schema.Url("https://example.com/api/v1?q=1")
assert u.scheme == "https"
assert u.get_query_params() == {"q": "1"}

e = schema.Email("user@example.com")
assert e.user == "user"
assert e.domain == "example.com"
```
