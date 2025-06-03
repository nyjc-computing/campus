"""apps/api/models/source
Source Models

This module provides classes for creating and managing Campus sources, which
are data sources from third-party platforms and APIs.

Data structures:
- collections (Integrations)

Main operations:
- 
"""
from common.drum.mongodb import get_db

from .integration import Integration

TABLE = "sources"


def init_db():
    """Initialize the collections needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    For MongoDB, collections are created automatically on first insert.
    """
    db = get_db()
    source_meta = db[TABLE].find_one({"@meta": True})
    if source_meta is None:
        db[TABLE].insert_one({
            "@meta": True,
            "integrations": {},
            "sourcetypes": {},
        })
    

__all__ = [
    "Integration",
    "init_db",
]
