"""campus.storage.query

This module provides query operators for storage filtering.

These operators enable more expressive queries while maintaining backward
compatibility with simple exact-match queries.

Example:
    from campus.storage.query import gt, gte, lt, lte, between

    # Simple exact match (backward compatible)
    storage.get_matching({"user_id": "user_123"})

    # With operators
    storage.get_matching({"duration_ms": gt(1000)})
    storage.get_matching({"started_at": gte("2024-01-01")})
    storage.get_matching({"status_code": lt(500)})
    storage.get_matching({"started_at": between("2024-01-01", "2024-12-31")})
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Operator:
    """Base class for query operators.

    Operators are immutable value objects that represent comparison
    operations in queries.
    """
    value: Any


class gt(Operator):
    """Greater than comparison.

    Example:
        {"duration_ms": gt(1000)}  # duration_ms > 1000
    """


class gte(Operator):
    """Greater than or equal comparison.

    Example:
        {"started_at": gte("2024-01-01")}  # started_at >= "2024-01-01"
    """


class lt(Operator):
    """Less than comparison.

    Example:
        {"timeout": lt(5000)}  # timeout < 5000
    """


class lte(Operator):
    """Less than or equal comparison.

    Example:
        {"retries": lte(3)}  # retries <= 3
    """


@dataclass(frozen=True)
class between(Operator):
    """Range comparison for inclusive lower and upper bounds.

    Example:
        {"started_at": between("2024-01-01", "2024-12-31")}  # 2024-01-01 <= started_at <= 2024-12-31

    Attributes:
        value: A tuple of (min_value, max_value) representing the inclusive range
    """
    value: tuple[Any, Any]

    def __init__(self, min_value: Any, max_value: Any):
        # Use object.__setattr__ since dataclass is frozen
        object.__setattr__(self, "value", (min_value, max_value))


def is_operator(value: Any) -> bool:
    """Check if a value is a query operator.

    Args:
        value: The value to check

    Returns:
        True if the value is an Operator instance, False otherwise
    """
    return isinstance(value, Operator)
