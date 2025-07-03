"""common.validation.record

This module contains utility functions for validating records (dictionaries).
"""
from collections.abc import Collection, Mapping
from typing import Any


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


def _validate_key_names_types(
        record: Mapping[str, Any],
        valid_keys: Mapping[str, type],
        ignore_extra=True,
        required=True
    ) -> None:
    """Validate that the keys in the record are valid according to the provided set of valid keys.

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
    for key in record_set & valid_set:  # iterate keys common to both sets
        if not isinstance(record[key], valid_keys[key]):
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
            _validate_key_names_types(record, valid_keys, ignore_extra=ignore_extra, required=required)
        case Collection():
            _validate_key_names(record, valid_keys, ignore_extra=ignore_extra, required=required)
        case _:
            raise TypeError(f"Invalid type for valid_keys: {type(valid_keys)}")

