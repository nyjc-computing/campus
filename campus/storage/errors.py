"""campus.storage.errors

Storage-specific error definitions for Campus storage backends.

These errors are used by storage backends (documents and tables) to handle
common error conditions like documents not found or no changes applied.
"""

from typing import Optional


class StorageError(Exception):
    """Base class for all storage-related errors."""

    def __init__(self, message: str = "An error occurred in storage."):
        super().__init__(message)
        self.message = message


class ConflictError(StorageError):
    """Error raised when a storage operation encounters a conflict.

    This error is raised when an operation cannot proceed due to a conflict,
    such as attempting to insert a duplicate record or violating a unique constraint.
    """

    def __init__(self, message: str = "A conflict occurred in storage.", collection_name: Optional[str] = None, details: Optional[dict] = None):
        self.collection_name = collection_name
        self.details = details
        full_message = message
        if collection_name:
            full_message += f" in collection '{collection_name}'"
        if details:
            full_message += f". Details: {details}"
        super().__init__(full_message)


class NoChangesAppliedError(StorageError):
    """Error raised when a storage operation affects no documents.

    This error is raised when attempting to update or delete documents
    with a query that matches no documents in the storage backend.
    """

    def __init__(self, operation: str, query: Optional[dict] = None, collection_name: Optional[str] = None):
        self.operation = operation
        self.query = query
        self.collection_name = collection_name
        message = f"No documents were affected by {operation} operation"
        if collection_name:
            message += f" in collection '{collection_name}'"
        if query:
            message += f" with query: {query}"
        super().__init__(message)


class NotFoundError(StorageError):
    """Error raised when a document is not found in storage.

    This error is raised when attempting to update or delete a document
    that does not exist in the storage backend.
    """

    def __init__(self, doc_id: str, collection_name: Optional[str] = None):
        self.doc_id = doc_id
        self.collection_name = collection_name
        message = f"Document with id '{doc_id}' not found"
        if collection_name:
            message += f" in collection '{collection_name}'"
        super().__init__(message)
