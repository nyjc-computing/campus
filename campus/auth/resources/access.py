"""campus.auth.access

Defines access control utilities for Campus authentication and vault access.
"""

from campus.common.errors import api_errors

# Access permission bitflags
# Each permission is a power of 2, allowing them to be combined with | (OR)
READ = 1    # 0001 in binary - Can read existing secrets
CREATE = 2  # 0010 in binary - Can create new secrets
UPDATE = 4  # 0100 in binary - Can modify existing secrets
DELETE = 8  # 1000 in binary - Can delete secrets
# 1111 in binary - All permissions (value: 15)
ALL = READ | CREATE | UPDATE | DELETE


class PermissionError(Exception):
    """Error raised when user does not have the required permissions for an operation."""


def permissions_to_access(permissions: int | list[str]) -> int:
    """Convert permissions given as an integer or list of strings
    to an access value integer.
    """
    match permissions:
        case list():
            # Convert permission names to bitflags
            permission_map = {
                "READ": READ,
                "CREATE": CREATE,
                "UPDATE": UPDATE,
                "DELETE": DELETE,
                "ALL": ALL
            }
            access_flags = 0
            invalid_perms = [
                perm for perm in permissions
                if perm not in permission_map
            ]
            if invalid_perms:
                raise api_errors.InvalidRequestError(
                    "Invalid permissions provided",
                    invalid_perms=invalid_perms
                )
            access_flags = 0
            for perm in permissions:
                access_flags |= permission_map[perm]
        case int():
            if not READ <= permissions <= ALL:
                raise api_errors.InvalidRequestError(
                    "Invalid permissions range",
                    accepted_range="1 - 15"
                )
            access_flags = permissions
        case _:
            raise api_errors.InvalidRequestError(
                "Invalid permissions argument type",
                given_type=type(permissions).__name__,
                required_type="integer | array[string]"
            )
    return access_flags


def access_to_permissions(access: int) -> list[str]:
    """Get a list of permission names from an access integer bitflag."""
    permissions = []
    if access & READ:
        permissions.append("READ")
    if access & CREATE:
        permissions.append("CREATE")
    if access & UPDATE:
        permissions.append("UPDATE")
    if access & DELETE:
        permissions.append("DELETE")
    if access == ALL:
        permissions = ["ALL"]
    return permissions
