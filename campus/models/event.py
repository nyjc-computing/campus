"""campus.models.event

This module provides classes for managing Campus events.

Data structures:
- 

Main operations:
- CRUD
"""

from campus.common.utils import uid, utc_time
from campus.common.schema import CampusID
from campus.storage import get_table
from campus.common import devops

# Create a new EventID with CampusID(uid.generate_category_uid("event", length=8))
EventID = CampusID

"""
Database schema:
id: TEXT - EventID, is the primary key
name: TEXT - name of the event
venue: TEXT - venue of the event
time: TEXT - rfc3339 time
length: INTEGER - length of event in seconds
"""

# TODO: Implement some venue validation through some master list?

TABLE = "events"

@devops.block_env(devops.PRODUCTION)
def init_db():
    """Initialize the tables needed by the model.

    This function is intended to be called only in a test environment (using a
    local-only db like SQLite), or in a staging environment before upgrading to
    production.
    """
    storage = get_table(TABLE)
    schema = f"""
        CREATE TABLE IF NOT EXISTS "{TABLE}" (
            id TEXT PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            venue TEXT NOT NULL,
            time TEXT NOT NULL,
            length INTEGER NULL,
        )
    """
    storage.init_table(schema)
