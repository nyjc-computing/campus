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

Storage interfaces mirror this expectation (see comments in
`campus.storage.tables.interface` and `campus.storage.documents.interface`).

### Domain types (`base.py`)

- **`schema.CampusID`**: Alias of `schema.openapi.String`. Used for primary keys
  and other Campus identifiers.
- **`schema.UserID`**: Alias of `schema.openapi.Email`. Used as the canonical
  user identifier.
- **`schema.ResponseStatus`**: `Literal["ok", "error"]`.

### OpenAPI datatypes (`openapi.py`)

These types mostly subclass the closest built-in Python type so they behave like
normal values, while being explicit in models and API boundaries.

- **Primitives**
  - `Boolean` (emulates `bool` behavior; `bool` is not subclassable)
  - `Integer` (`int`)
  - `Number` (`float`)
  - `String` (`str`)
- **String formats**
  - `DateTime`: RFC3339 timestamp string with helpers like `utcnow()`,
    `from_datetime()`, `to_datetime()`, `to_timestamp()`, and `utcafter(...)`.
  - `Date`: RFC3339 date string with helpers like `today()`, `from_date()`,
    and `utcafter(...)`.
  - `Email`: string with convenience accessors `.user` and `.domain`.
  - `Url`: string with URL component accessors and `get_query_params()`.
- **Structures**
  - `Array` (`list`)
  - `Object` (`dict`)

For the OpenAPI 3 datatype reference, see:
`https://swagger.io/specification/v3/#data-types`

## How the main application uses this

### Models

Models commonly type fields using these schema types for clarity and consistency
(e.g. `schema.CampusID`, `schema.UserID`, `schema.DateTime`). This helps keep
API resources, storage, and model code aligned.

### API routes and resources

Routes and resources frequently cast incoming parameters into schema types at
boundaries (for example, turning a string `circle_id` into `schema.CampusID`).

### Storage

Storage interfaces assume a consistent primary key field name (`"id"`). Keep
`schema.CAMPUS_KEY` aligned with any storage backends and interfaces that embed
this assumption.

### Utilities

Common utilities return schema types for IDs (for example,
`campus.common.utils.uid.generate_category_uid(...) -> schema.CampusID`), so
callers don’t have to repeatedly cast.

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
