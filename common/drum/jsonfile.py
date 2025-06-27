"""common/drum/jsonfile.py

JSON file implementation of the Drum interface.

This is intended as a read-only interface, and does not support mutation.
"""

import os
from pathlib import Path
from typing import Any

from common.schema import Message
from .base import PK, Condition, DrumInterface, DrumResponse, Record, Update

ROOTDIR = "apps"


def get_drum() -> 'JsonDrum':
    """Get a prepared Drum instance."""
    return JsonDrum(ROOTDIR)

def load_json(filepath: os.PathLike) -> Any:
    """Load a JSON file and return its content."""
    import json
    with open(filepath, 'r', encoding='utf-8') as file:
        return json.load(file)

def error_response(message: str) -> DrumResponse:
    """Helper function to create an error response."""
    return DrumResponse("error", Message.FAILED, message)


class JsonDrum(DrumInterface):
    """JSON file implementation of the Drum interface."""

    def __init__(self, srcdir: os.PathLike):
        self.srcdir = Path(srcdir)

    def get_all(self, group: str) -> DrumResponse:
        """Return all JSON documents in parh srcdir/group."""
        path = os.path.join(self.srcdir, group)
        files = [
            entry for entry in os.listdir(path)
            if os.path.isfile(os.path.join(path, entry))
            and os.path.splitext(entry)[-1].lower() == ".json"
        ]
        if not files:
            return error_response(f"No JSON files found in {path}.")
        data = [
            self.get_by_id(group, os.path.splitext(filename)[0]).data
            for filename in files
        ]
        return DrumResponse(status="ok", message=Message.SUCCESS, data=data)

    def get_by_id(self, group: str, id: str) -> DrumResponse:
        """Return JSON document with matching name as id."""
        filepath = os.path.join(self.srcdir, group, id + ".json")
        if not os.path.exists(filepath):
            return error_response(f"File {filepath} does not exist.")
        try:
            data = load_json(filepath)
        except Exception as e:
            return error_response(f"Failed to load JSON from {filepath}: {str(e)}")
        else:
            return DrumResponse(status="ok", message=Message.SUCCESS, data=data)

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
