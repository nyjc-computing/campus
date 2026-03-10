"""campus.storage.objects.backend

Backend implementations for the Objects storage interface.

Available backends:
    - local: Local filesystem storage for testing/development
    - railway: Railway Bucket storage using S3-compatible API
"""

__all__ = [
    "LocalBucket",
    "RailwayBucket",
]

from .local import LocalBucket
from .railway import RailwayBucket
