"""drum.py

A storage interface for Campus digital services.

Common assumptions across storage types:
- attributes/columns/fields are also valid Python identifiers
- primary keys are named `id`
- primary keys are unique strings
- timestamps are stored as RFC3339 strings
- records/documents are grouped by collections/tables
"""

from .base import DrumError, DrumResponse
