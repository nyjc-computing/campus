"""campus.storage.errors

Storage-specific error definitions for Campus storage backends.

These errors are used by storage backends (documents and tables) to handle
common error conditions like documents not found or no changes applied.
"""

from typing import Optional


class StorageError(Exception):
    """Base class for all storage-related errors."""

    def __init__(
            self,
            message: str = "An error occurred in storage.",
            group_name: Optional[str] = None,
            details: Optional[dict] = None
    ):
        full_message = message
        if group_name:
            full_message += f" in group '{group_name}'"
            self.group_name = group_name
        if details:
            self.details = details
            full_message += f". Details: {details}"
        super().__init__(full_message)
        self.message = message


class ConflictError(StorageError):
    """Error raised when a storage operation encounters a conflict.

    This error is raised when an operation cannot proceed due to a conflict,
    such as attempting to insert a duplicate record or violating a unique constraint.
    """

    def __init__(
            self,
            message: str = "A conflict occurred in storage.",
            group_name: Optional[str] = None,
            details: Optional[dict] = None
    ):
        full_message = message
        if group_name:
            full_message += f" in group '{group_name}'"
            self.group_name = group_name
        if details:
            self.details = details
            full_message += f". Details: {details}"
        super().__init__(full_message)


class NoChangesAppliedError(StorageError):
    """Error raised when a storage operation affects no documents.

    This error is raised when attempting to update or delete documents
    with a query that matches no documents in the storage backend.
    """

    def __init__(
            self,
            operation: str,
            query: Optional[dict] = None,
            group_name: Optional[str] = None
    ):
        self.operation = operation
        message = f"No documents were affected by {operation} operation"
        if group_name:
            message += f" in group '{group_name}'"
            self.group_name = group_name
        if query:
            self.query = query
            message += f" with query: {query}"
        super().__init__(message)


class NotFoundError(StorageError):
    """Error raised when a document/row is not found in storage.

    This error is raised when attempting to update or delete a
    document/row that does not exist in the storage backend.
    """

    def __init__(self, doc_id: str, name: Optional[str] = None):
        self.doc_id = doc_id
        message = f"Document/row with id '{doc_id}' not found"
        if name:
            message += f" in collection/table '{name}'"
            self.group_name = name
        super().__init__(message)
