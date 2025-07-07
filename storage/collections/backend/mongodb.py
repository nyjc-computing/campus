"""storage.collections.backend.mongodb

This module provides the MongoDB backend for the Collections storage interface.

Environment Variables:
- MONGODB_URI: MongoDB connection string (required)
- MONGODB_NAME: Database name (required)

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

import os
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from storage.collections.interface import CollectionInterface, PK

DB_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ["MONGODB_NAME"]
MONGO_PK = "_id"  # MongoDB uses _id as the primary key


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
        """Initialize the MongoDB collection with a name."""
        super().__init__(name)
        self.client = MongoClient(DB_URI)
        self.db = self.client[DB_NAME]
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
        self.collection.update_one({PK: doc_id}, {"$set": update})

    def update_matching(self, query: dict, update: dict) -> None:
        """Update documents matching a query in the collection."""
        self.collection.update_many(query, {"$set": update})

    def delete_by_id(self, doc_id: str) -> None:
        """Delete a document from the collection."""
        self.collection.delete_one({PK: doc_id})

    def delete_matching(self, query: dict) -> None:
        """Delete documents matching a query in the collection."""
        self.collection.delete_many(query)

    def init_collection(self) -> None:
        """Initialize the collection.
        
        This method is intended for development/testing environments.
        For MongoDB, collections are created automatically on first insert,
        so this method primarily ensures the collection exists and can be used
        for any setup operations if needed in the future.
        """
        import os
        
        # Safety check: prevent running in production  
        if os.getenv('ENV', 'development') == 'production':
            raise AssertionError(
                "Collection initialization detected in production environment"
            )
        
        # For MongoDB, collections are created automatically on first insert
        # This method exists for interface compatibility and future extensibility
        pass
