"""common.validation.record

This module contains utility functions for validating records (dictionaries).
"""
from collections.abc import Callable, Collection, Mapping
from enum import Enum
from typing import (
    Any,
    NotRequired,
    Required,
    TypeVar,
    get_args,
    get_origin,
)

C = TypeVar('C', bound=Collection)

class Requiredness(Enum):
    """Enum for requiredness of a key."""
    REQUIRED = Required
    OPTIONAL = NotRequired
    UNMARKED = None


def _validate_key_names(
        record: Mapping[str, Any],
        valid_keys: Collection[str],
        ignore_extra=True,
        required=True
) -> None:
    """Validate that the keys in the record are valid according to the provided set of valid keys.

    Args:
        record (dict): The record to validate.
        valid_keys (Collection[str]): A collection of valid keys.
        ignore_extra (bool): If True, keys not in valid_keys are ignored.
            If False, an error is raised for any key not in valid_keys.
        required (bool): If True, all keys in valid_keys are required.

    Raises:
        KeyError: If any keys in the record are not valid.
    """
    valid_set, record_set = set(valid_keys), set(record.keys())
    if required:
        missing_keys = valid_set - record_set
        if missing_keys:
            raise KeyError(f"Missing required keys: {', '.join(missing_keys)}")
    # all required keys are present
    if not ignore_extra:
        extra_keys = record_set - valid_set
        if extra_keys:
            raise KeyError(f"Invalid keys: {', '.join(extra_keys)}")
    # all keys are valid

def get_requiredness_type(typ: type) -> tuple[Requiredness, type]:
    """Get the requiredness and wrapped type of a value."""
    # get_origin is expected to return NotRequired, Required, or None
    # if NotRequired or Required, args is expected to be a tuple of length 1
    # containing the type of the value
    # if None, args is expected to be an empty tuple, in which case typ is the
    # actual type of the value
    origin, unwrapped_type = get_origin(typ), get_args(typ)
    return Requiredness(origin), unwrapped_type[0] if origin is not None else typ

def unpack_required_optional(
        schema: Mapping[str, type],
        factory: Callable[[list[str]], C]=list,
) -> tuple[C, C]:
    """Unpack a schema into required and optional keys.

    If `schema` is a plain dict, all keys are required.
    If `schema` is a TypedDict,
    - keys marked as `Required` are required
    - keys marked as `NotRequired` are optional
    - unmarked keys are required if `total=True`, otherwise optional

    Args:
        schema (Mapping[str, type]): The schema to unpack.
            This should be a TypedDict or a plain dict.
        factory (callable): A callable that takes an iterable and returns a set-like object.

    Returns:
        tuple[list[str], list[str]]: A tuple of required and optional keys.
    """
    # Only TypedDicts have __total__ attribute
    # Treat plain dicts as if total=True
    total = getattr(schema, '__total__', True)
    required, optional = [], []
    for key, typ in schema.items():
        requiredness, unwrapped_type = get_requiredness_type(typ)
        if requiredness is not Requiredness.UNMARKED:
            typ = unwrapped_type
        match (requiredness, total):
            case (Requiredness.REQUIRED, _):
                required.append(key)
            case (Requiredness.OPTIONAL, _):
                optional.append(key)
            case (Requiredness.UNMARKED, True):
                required.append(key)
            case (Requiredness.UNMARKED, False):
                optional.append(key)
            case _:
                raise AssertionError(
                    f"Unexpected state: requiredness={requiredness}, total={total}"
                )
    return factory(required), factory(optional)

def _validate_key_names_types(
        record: Mapping[str, Any],
        valid_keys: Mapping[str, type],
        ignore_extra=True,
        required=True
    ) -> None:
    """Validate that the keys in the record are valid according to the provided
    set of valid keys.

    Args:
        record (dict): The record to validate.
        valid_keys (Mapping[str]): A mapping of valid keys to expected type.
        ignore_extra (bool): If True, keys not in valid_keys are ignored.
            If False, an error is raised for any key not in valid_keys.
        required (bool): If True, all keys in valid_keys are required.

    Raises:
        KeyError: If any keys in the record are not valid.
        TypeError: If any values in the record do not match the expected types.
    """
    # `valid_keys` may have NotRequired or Required as annotated types
    record_set = set(record.keys())
    required_keys, optional_keys = unpack_required_optional(valid_keys, set)
    if required:
        missing_keys = required_keys - record_set
        if missing_keys:
            raise KeyError(f"Missing required keys: {', '.join(missing_keys)}")
    # all required keys are present
    if not ignore_extra:
        extra_keys = record_set - required_keys - optional_keys
        if extra_keys:
            raise KeyError(f"Invalid keys: {', '.join(extra_keys)}")
    # all record keys are valid
    for key in record_set:
        requiredness, unwrapped_type = get_requiredness_type(valid_keys[key])
        KeyType = unwrapped_type if requiredness is not Requiredness.UNMARKED else valid_keys[key]
        if not isinstance(record[key], KeyType):
            raise TypeError(
                f"Invalid type for key '{key}': expected {valid_keys[key].__name__}, "
                f"got {type(record[key]).__name__}"
            )


def validate_keys(
        record: Mapping[str, Any],
        valid_keys: Collection[str] | Mapping[str, type],
        ignore_extra=True,
        required=True
    ) -> None:
    """Validate that the keys in the record are valid according to the provided set of valid keys.

    Args:
        record (dict): The record to validate.
        valid_keys (Collection[str] | Mapping[str, type]): A collection of valid keys or a mapping of valid keys to types.
            If a mapping is provided, the types are checked against the record values.
        ignore_extra (bool): If True, keys not in valid_keys are ignored.
        required (bool): If True, all keys in valid_keys are required.
            If valid_keys is a TypedDict, optional keys are allowed to be omitted.

    Raises:
        KeyError: If any keys in the record are not valid.
        TypeError: If any values in the record do not match the expected types.
    """
    match valid_keys:
        case Mapping():
            # Validate key names and types
            _validate_key_names_types(
                record,
                valid_keys,
                ignore_extra=ignore_extra,
                required=required
            )
        case Collection():
            # Validate key names only
            _validate_key_names(
                record,
                valid_keys,
                ignore_extra=ignore_extra,
                required=required
            )
        case _:
            raise TypeError(f"Invalid type for valid_keys: {type(valid_keys)}")

