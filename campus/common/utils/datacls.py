"""campus.common.utils.datacls

Utilities for working with Python dataclasses and type signatures.
"""

import dataclasses
import typing


def get_pytype(t: type) -> type:
    """Get the underlying Python type of a dataclass field, stripping
    Optional if present.
    """
    origin = typing.get_origin(t)
    if origin is typing.Union:
        args = typing.get_args(t)
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            return non_none_args[0]
    return t


def has_default(field: dataclasses.Field) -> bool:
    """Check if a dataclass field has a default value."""
    return field.default is not dataclasses.MISSING


def is_optional(field: dataclasses.Field) -> bool:
    """Check if a dataclass field is Optional.

    A field is optional if:
    - field.type annotation is of the form Optional[T] or Union[T, None]
    - It has a field.default value
    """
    t = field.type
    origin = typing.get_origin(t)
    if origin is not typing.Union:
        return False
    args = typing.get_args(t)
    if type(None) not in args:
        return False
    if not has_default(field):
        return False
    return True
