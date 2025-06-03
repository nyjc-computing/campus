"""apps/api/models/source
Source Models

This module provides classes for creating and managing Campus sources, which
are data sources from third-party platforms and APIs.

Data structures:
- collections (Integrations)

Main operations:
- 
"""

from .integration import Integration, init_db as init_db_integration

init_db_integration()

def init_db():
    """Initialize the collections needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    For MongoDB, collections are created automatically on first insert.
    """
    init_db_integration()

__all__ = [
    "Integration",
    "init_db",
]
