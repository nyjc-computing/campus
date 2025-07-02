"""common.validation.name

Common functions used for validation of names and labels.
"""

def is_valid_identifier(name: str) -> bool:
    """
    Check if the given name is a valid Python identifier.
    """
    return name.isidentifier()

def is_valid_label(name: str) -> bool:
    """Check if the given name is a valid label.

    A label:
    - must start with a letter or underscore
    - can contain letters, digits, underscores, hyphens
    - cannot be empty
    - cannot contain spaces or special characters
    - cannot be longer than 64 characters
    """
    if not name:
        return False
    if len(name) > 64:
        return False
    if name[0] != '_' and not name[0].isalpha():
        return False
    for c in name[1:]:
        if c not in ('-', '_') and not c.isalnum():
            return False
    return True

