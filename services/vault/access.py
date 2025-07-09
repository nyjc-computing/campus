"""services.vault.access

Access control module for the vault service.

Manages client permissions for vault labels using bitflag permissions.
"""

from storage import get_table
from common.utils import uid, utc_time

TABLE = "vault_access"

# Access permission bitflags
READ = 1
CREATE = 2
UPDATE = 4
DELETE = 8
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


def grant_access(client_id: str, label: str, access: int = ALL) -> None:
    """Grant a client access to a vault label with specified permissions.
    
    Args:
        client_id: The client identifier
        label: The vault label
        access: Bitflag permissions (default: ALL permissions)
    """
    access_storage = get_table(TABLE)
    
    # Check if access already exists
    existing_access = access_storage.get_matching({"client_id": client_id, "label": label})
    if existing_access:
        # Update existing access permissions
        record_id = existing_access[0]["id"]
        access_storage.update_by_id(record_id, {"access": access})
    else:
        # Create new access record
        access_id = uid.generate_category_uid(TABLE, length=16)
        access_record = {
            "id": access_id,
            "created_at": utc_time.now(),
            "client_id": client_id,
            "label": label,
            "access": access
        }
        access_storage.insert_one(access_record)


def revoke_access(client_id: str, label: str) -> None:
    """Revoke a client's access to a vault label."""
    access_storage = get_table(TABLE)
    access_records = access_storage.get_matching({"client_id": client_id, "label": label})
    for record in access_records:
        access_storage.delete_by_id(record["id"])


def has_access(client_id: str, label: str, required_access: int = READ) -> bool:
    """Check if a client has the required access permissions for a vault label.
    
    Args:
        client_id: The client identifier
        label: The vault label
        required_access: Required permission bitflags (default: READ)
        
    Returns:
        True if the client has the required permissions, False otherwise
    """
    access_storage = get_table(TABLE)
    access_records = access_storage.get_matching({"client_id": client_id, "label": label})
    if not access_records:
        return False
    
    granted_access = access_records[0]["access"]
    return (granted_access & required_access) == required_access


def init_db():
    """Initialize the access control table.

    This function is intended to be called only in a test environment or
    staging.
    """
    access_storage = get_table(TABLE)
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
    access_storage.init_table(access_schema)
