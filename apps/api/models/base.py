"""apps/palmtree/models/base.py

Base types and classes for all Palmtree models.
"""

from common.schema import Message, Response


class ModelResponse(Response):
    """Represents a response from any model operation."""
