"""storage.collections.backend.mongodb

This module provides the MongoDB backend for the Collections storage interface.

Vault Integration:
The MongoDB connection URI is retrieved from the vault secret 'MONGODB_URI' in the 'storage' 
vault. The database name is retrieved from the vault secret 'MONGODB_NAME' in the same vault.

Implementation:
Uses MongoDB's native document storage with transparent primary key mapping
between Campus `id` and MongoDB `_id` fields. Collections are created automatically.
Record validation is handled before storage and is not the responsibility of this module.

Usage Example:
```python
from storage.collections.backend.mongodb import MongoDBCollection

collection = MongoDBCollection("users")
collection.insert_one({"id": "123", "name": "John"})
user = collection.get_by_id("123")
collection.update_by_id("123", {"name": "Jane"})
collection.delete_by_id("123")
```
"""

from pymongo import MongoClient
from pymongo.collection import Collection

from common import devops
from services.vault import get_vault
from storage.collections.interface import CollectionInterface, PK
from storage.errors import NotFoundError, NoChangesAppliedError

MONGO_PK = "_id"  # MongoDB uses _id as the primary key


def _get_mongodb_uri() -> str:
    """Get the MongoDB URI from vault.

    Retrieves MONGODB_URI from the 'storage' vault.

    Returns:
        MongoDB connection string

    Raises:
        RuntimeError: If vault secret retrieval fails
    """
    try:
        storage_vault = get_vault("storage")
        return storage_vault.get("MONGODB_URI")
    except Exception as e:
        raise RuntimeError(
            f"Failed to retrieve MongoDB URI from vault secret 'MONGODB_URI' "
            f"in 'storage' vault: {e}"
        ) from e


def _get_mongodb_name() -> str:
    """Get the MongoDB database name from vault.

    Retrieves MONGODB_NAME from the 'storage' vault.

    Returns:
        MongoDB database name

    Raises:
        RuntimeError: If vault secret retrieval fails
    """
    try:
        storage_vault = get_vault("storage")
        return storage_vault.get("MONGODB_NAME")
    except Exception as e:
        raise RuntimeError(
            f"Failed to retrieve MongoDB database name from vault secret 'MONGODB_NAME' "
            f"in 'storage' vault: {e}"
        ) from e


class MongoRecord(dict):
    """Handles transparent mapping between Campus and MongoDB primary keys.

    Maps Campus `id` field to MongoDB's `_id` field.

    Example:
        record = MongoRecord({"id": "123", "name": "John"})
        mongo_doc = record.to_mongo()  # {"_id": "123", "name": "John"}
    """

    def __init__(self, *args, **kwargs):
        """Initialize the MongoRecord with given arguments."""
        super().__init__(*args, **kwargs)

    @classmethod
    def from_mongo(cls, mongo_doc: dict) -> "MongoRecord":
        """Create a MongoRecord from a MongoDB document."""
        mongo_doc[PK] = mongo_doc.pop(MONGO_PK)
        return cls(mongo_doc)

    @classmethod
    def from_record(cls, record: dict) -> "MongoRecord":
        """Create a MongoRecord from an API document."""
        record[MONGO_PK] = record.pop(PK)
        return cls(record)

    def to_mongo(self) -> dict:
        """Convert the MongoRecord to a MongoDB document."""
        mongo_doc = dict(self)
        mongo_doc[MONGO_PK] = mongo_doc.pop(PK)
        return mongo_doc

    def to_record(self) -> dict:
        """Convert the MongoRecord to an API document."""
        record = dict(self)
        record[PK] = record.pop(MONGO_PK)
        return record


class MongoDBCollection(CollectionInterface):
    """MongoDB backend for the Collections storage interface.

    Uses MongoDB's native document storage with automatic primary key mapping
    between Campus `id` and MongoDB `_id` fields.

    Example:
        collection = MongoDBCollection("users")
        collection.insert_one({"id": "123", "name": "John"})
        user = collection.get_by_id("123")
    """

    def __init__(self, name: str):
        """Initialize the MongoDB collection with a name.

        Retrieves MongoDB connection details from vault and establishes connection.

        Raises:
            RuntimeError: If vault secret retrieval fails
            pymongo.errors.ConnectionFailure: If MongoDB connection fails
        """
        super().__init__(name)
        mongodb_uri = _get_mongodb_uri()
        mongodb_name = _get_mongodb_name()
        self.client = MongoClient(mongodb_uri)
        self.db = self.client[mongodb_name]
        self.collection: Collection = self.db[name]

    def get_by_id(self, doc_id: str) -> dict:
        """Retrieve a document by its ID."""
        record = self.collection.find_one({PK: doc_id})
        if record:
            return MongoRecord.from_mongo(record).to_record()
        return {}

    def get_matching(self, query: dict) -> list[dict]:
        """Retrieve documents matching a query."""
        cursor = self.collection.find(query)
        return [
            MongoRecord.from_mongo(record).to_record()
            for record in cursor
        ]

    def insert_one(self, row: dict) -> None:
        """Insert a document into the collection."""
        self.collection.insert_one(
            MongoRecord.from_record(row).to_mongo()
        )

    def update_by_id(self, doc_id: str, update: dict) -> None:
        """Update a document in the collection."""
        result = self.collection.update_one({PK: doc_id}, {"$set": update})
        if result.matched_count == 0:
            raise NotFoundError(doc_id, self.name)

    def update_matching(self, query: dict, update: dict) -> None:
        """Update documents matching a query in the collection."""
        result = self.collection.update_many(query, {"$set": update})
        if result.matched_count == 0:
            raise NoChangesAppliedError("update", query, self.name)

    def delete_by_id(self, doc_id: str) -> None:
        """Delete a document from the collection."""
        result = self.collection.delete_one({PK: doc_id})
        if result.deleted_count == 0:
            raise NotFoundError(doc_id, self.name)

    def delete_matching(self, query: dict) -> None:
        """Delete documents matching a query in the collection."""
        result = self.collection.delete_many(query)
        if result.deleted_count == 0:
            raise NoChangesAppliedError("delete", query, self.name)

    @devops.block_env(devops.PRODUCTION)
    def init_collection(self) -> None:
        """Initialize the collection.

        This method is intended for development/testing environments.
        For MongoDB, collections are created automatically on first insert,
        so this method primarily ensures the collection exists and can be used
        for any setup operations if needed in the future.
        """
        # For MongoDB, collections are created automatically on first insert
        # This method exists for interface compatibility and future extensibility


@devops.block_env(devops.PRODUCTION)
def purge_collections() -> None:
    """Purge all collections by dropping the entire database.

    This function is intended for development/testing environments only.
    It drops all collections in the MongoDB database.

    Raises:
        RuntimeError: If database connection or purge operations fail
    """
    try:
        uri = _get_mongodb_uri()
        db_name = _get_mongodb_name()

        client = MongoClient(uri)
        db = client[db_name]

        # Drop all collections
        for collection_name in db.list_collection_names():
            db.drop_collection(collection_name)

        client.close()

    except Exception as e:
        raise RuntimeError(f"Failed to purge MongoDB collections: {e}") from e
