"""common/drum/jsonfile.py

JSON file implementation of the Drum interface.

This is intended as a read-only interface, and does not support mutation.
"""

import os
from typing import Any

from common.schema import Message
from .base import PK, Condition, DrumInterface, DrumResponse, Record, Update


def get_drum() -> 'JsonDrum':
    """Get a prepared Drum instance."""
    return JsonDrum()

def error_response(message: str) -> DrumResponse:
    """Helper function to create an error response."""
    return DrumResponse("error", Message.FAILED, message)


class JsonDrum(DrumInterface):
    """MongoDB implementation of the Drum interface."""

    def __init__(self, srcdir: os.path.PathLike):
        self.srcdir = srcdir

    def get_all(self, group: str) -> DrumResponse:
        """Return all JSON documents in srcdir."""
        pass

    def get_by_id(self, group: str, id: str) -> DrumResponse:
        """Return JSON document with matching name as id."""
        pass

    def get_matching(self, group: str, condition: Condition) -> DrumResponse:
        raise NotImplementedError("operation not supported.")

    def insert(self, group: str, record: Record) -> DrumResponse:
        raise NotImplementedError("operation not supported.")

    def set(self, group: str, record: Record) -> DrumResponse:
        raise NotImplementedError("operation not supported.")

    def update_by_id(self, group: str, id: str, updates: Update) -> DrumResponse:
        raise NotImplementedError("operation not supported.")

    def update_matching(self, group: str, updates: Update, condition: Condition) -> DrumResponse:
        raise NotImplementedError("operation not supported.")

    def delete_by_id(self, group: str, id: str) -> DrumResponse:
        raise NotImplementedError("operation not supported.")

    def delete_matching(self, group: str, condition: Condition) -> DrumResponse:
        raise NotImplementedError("operation not supported.")
