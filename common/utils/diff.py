"""common.utils.diff

Utility functions for comparing complex data types.
"""

from typing import Any

def diff_dict(
        dict_A: dict[str, Any],
        dict_B: dict[str, Any]
) -> tuple[list[str], list[str], dict[str, Any]]:
    """
    Compare two unsorted dictionaries and return the differences.

    Args:
        dict_A: First dictionary.
        dict_B: Second dictionary.

    Returns:
        A tuple comprising three elements:
            - The first list contains keys present in dict_A but not in dict_B.
            - The second list contains keys present in dict_B but not in dict_A.
            - The third element is a dict containing keys that are present in
              both dictionaries but have different values, and values from dict_B.

    """
    in_A_not_B = [k for k in dict_A if k not in dict_B]
    in_B_not_A = [k for k in dict_B if k not in dict_A]
    updated_in_B = {
        k: dict_B[k]
        for k in dict_A
            if k in dict_B and dict_A[k] != dict_B[k]
    }
    return in_A_not_B, in_B_not_A, updated_in_B

def diff_list(list_A: list[Any], list_B: list[Any]) -> tuple[list[Any], list[Any]]:
    """
    Compare two unsorted lists and return the differences.

    Args:
        list_A: First list.
        list_B: Second list.

    Returns:
        A tuple containing two lists:
            - The first list contains elements present in list_A but not in list_B.
            - The second list contains elements present in list_B but not in list_A.
    """
    diff_A = [item for item in list_A if item not in list_B]
    diff_B = [item for item in list_B if item not in list_A]
    return diff_A, diff_B

