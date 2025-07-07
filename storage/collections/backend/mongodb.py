"""storage.collections.backend.mongodb

This module provides the MongoDB backend for the Collections storage interface.

Features:
- Full CRUD Operations: Create, Read, Update, Delete operations
- Flexible Schema: Native JSON document storage
- Primary Key Support: Uses standard `id` field as primary key (mapped to MongoDB's `_id`)
- Automatic ObjectId Handling: Transparent mapping between Campus `id` and MongoDB `_id`
- Query Support: Supports MongoDB's native query capabilities

Architecture:
The MongoDB implementation uses a document-based approach:
1. Primary Key Mapping: Campus `id` field maps to MongoDB's `_id` field
2. Document Storage: All other fields are stored as native JSON documents
3. MongoRecord Class: Handles transparent key mapping between Campus and MongoDB formats

Usage:
```python
from storage.collections.backend.mongodb import MongoDBCollection

# Create a collection instance
users_collection = MongoDBCollection("users")

# Insert a document
user_data = {
    "id": "user_123",
    "name": "John Doe",
    "email": "john@example.com",
    "age": 30
}
users_collection.insert_one(user_data)

# Retrieve by ID
user = users_collection.get_by_id("user_123")

# Query matching documents
young_users = users_collection.get_matching({"age": 25})

# Update a document
users_collection.update_by_id("user_123", {"age": 31, "status": "active"})

# Delete a document
users_collection.delete_by_id("user_123")
```

Database Configuration:
The implementation requires these environment variables:
- MONGO_URI: MongoDB connection string (required)
- MONGO_DB_NAME: Database name (required)

Dependencies:
- pymongo: MongoDB driver for Python

Performance Considerations:
- Native JSON document storage for optimal performance
- Automatic connection management
- Efficient document mapping through MongoRecord class
- Leverages MongoDB's native indexing capabilities

Note: Collections are created automatically by MongoDB when first accessed.
Record validation is handled before storage and is not the responsibility of this module.
"""

import os
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from storage.collections.interface import CollectionInterface, PK

DB_URI = os.environ["MONGO_URI"]
DB_NAME = os.environ["MONGO_DB_NAME"]
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
