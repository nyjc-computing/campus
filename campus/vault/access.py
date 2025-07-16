"""vault.access

Access control module for the vault service.

Manages client permissions for vault labels using bitflag permissions.

BITFLAGS EXPLAINED:
Bitflags are a way to store multiple boolean permissions in a single integer.
Each permission is represented by a power of 2 (1, 2, 4, 8, 16, ...).

Our permission system uses these values:
- READ = 1 (binary: 0001)
- CREATE = 2 (binary: 0010) 
- UPDATE = 4 (binary: 0100)
- DELETE = 8 (binary: 1000)

To combine permissions, we use the bitwise OR operator (|):
- READ + CREATE = 1 | 2 = 3 (binary: 0011)
- READ + UPDATE = 1 | 4 = 5 (binary: 0101)
- ALL permissions = 1 | 2 | 4 | 8 = 15 (binary: 1111)

To check if a permission is granted, we use the bitwise AND operator (&):
- If (granted_permissions & required_permission) == required_permission, access is granted
- Example: granted=5 (READ+UPDATE), checking for READ: (5 & 1) == 1 ✓ 
- Example: granted=5 (READ+UPDATE), checking for CREATE: (5 & 2) == 2 ✗

This allows efficient storage and checking of multiple permissions in one integer.
"""

from campus.common.utils import uid, utc_time
from campus.common import devops

from . import db

TABLE = "vault_access"

# Access permission bitflags
# Each permission is a power of 2, allowing them to be combined with | (OR)
READ = 1    # 0001 in binary - Can read existing secrets
CREATE = 2  # 0010 in binary - Can create new secrets
UPDATE = 4  # 0100 in binary - Can modify existing secrets
DELETE = 8  # 1000 in binary - Can delete secrets
# 1111 in binary - All permissions (value: 15)
ALL = READ | CREATE | UPDATE | DELETE

__all__ = [
    "grant_access",
    "revoke_access",
    "has_access",
    "init_db",
    "READ",
    "CREATE",
    "UPDATE",
    "DELETE",
    "ALL",
]


def grant_access(client_id: str, label: str, access: int) -> None:
    """Grant a client access to a vault label with specified permissions.

    The access parameter uses bitflags to specify which operations are allowed.
    You can combine multiple permissions using the | (OR) operator.

    Args:
        client_id: The client identifier
        label: The vault label  
        access: Bitflag permissions (default: ALL permissions)
                Examples:
                - READ: Only read secrets
                - READ | CREATE: Read and create new secrets
                - READ | UPDATE: Read and modify existing secrets
                - ALL: All permissions (READ | CREATE | UPDATE | DELETE)

    Examples:
        grant_access("client-123", "api-keys", READ)  # Read-only access
        grant_access("client-456", "api-keys", READ | CREATE)  # Read + create
        grant_access("admin-789", "api-keys", ALL)  # Full access
    """
    with db.get_connection_context() as conn:
        # Check if access already exists
        existing_access = db.execute_query(
            conn,
            "SELECT * FROM vault_access WHERE client_id = %s AND label = %s",
            (client_id, label),
            fetch_one=True
        )

        if existing_access:
            # Update existing access permissions
            db.execute_query(
                conn,
                "UPDATE vault_access SET access = %s WHERE id = %s",
                (access, existing_access["id"]),
                fetch_one=False,
                fetch_all=False
            )
        else:
            # Create new access record
            access_id = uid.generate_category_uid(TABLE, length=16)
            db.execute_query(
                conn,
                (
                    "INSERT INTO vault_access (id, created_at, client_id, label, access)"
                    "VALUES (%s, %s, %s, %s, %s)"
                ),
                (access_id, utc_time.now(), client_id, label, access),
                fetch_one=False,
                fetch_all=False
            )


def revoke_access(client_id: str, label: str) -> None:
    """Revoke a client's access to a vault label."""
    with db.get_connection_context() as conn:
        db.execute_query(
            conn,
            "DELETE FROM vault_access WHERE client_id = %s AND label = %s",
            (client_id, label),
            fetch_one=False,
            fetch_all=False
        )


def has_access(client_id: str, label: str, required_access: int) -> bool:
    """Check if a client has the required access permissions for a vault label.

    This function uses bitwise AND (&) to check if the client's granted permissions
    include all the required permissions. For example:
    - Client has READ | CREATE (value: 3)
    - We check for READ permission (value: 1)
    - Check: (3 & 1) == 1 → True (client has READ access)
    - We check for DELETE permission (value: 8)  
    - Check: (3 & 8) == 8 → False (client lacks delete access)

    Args:
        client_id: The client identifier
        label: The vault label
        required_access: Required permission bitflags (default: READ)
                        Can be a single permission or combined permissions.
                        Examples:
                        - READ: Check if client can read
                        - READ | UPDATE: Check if client can both read AND update

    Returns:
        True if the client has ALL the required permissions, False otherwise

    Examples:
        has_access("client-123", "secrets", READ)  # Can client read?
        has_access("client-123", "secrets", READ | UPDATE)  # Can client read AND update?
    """
    with db.get_connection_context() as conn:
        access_record = db.execute_query(
            conn,
            "SELECT access FROM vault_access WHERE client_id = %s AND label = %s",
            (client_id, label),
            fetch_one=True
        )

        if not access_record:
            return False

        granted_access = access_record["access"]
        return (granted_access & required_access) == required_access


@devops.block_env(devops.PRODUCTION)
def init_db():
    """Initialize the access control table.

    This function is intended to be called only in a test environment or
    staging.
    """
    with db.get_connection_context() as conn:
        with conn.cursor() as cursor:
            # Create vault_access table
            access_schema = """
                CREATE TABLE IF NOT EXISTS vault_access (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    access INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(client_id, label)
                )
            """
            cursor.execute(access_schema)
