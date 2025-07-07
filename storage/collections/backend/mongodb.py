"""storage.collections.backend.mongodb

This module provides the MongoDB backend for the Collections storage interface.
"""

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from storage.collections.interface import CollectionInterface, PK

DB_NAME = "campus"  # Default database name for MongoDB
MONGO_PK = "_id"  # MongoDB uses _id as the primary key


class MongoRecord(dict):
    """MongoDB documents store an ObjectId as the primary key.
    
    Since Campus already has its own primary key system, we use a custom
    primary key field `id` to store the Campus ID.

    We use this MongoRecord class to carry out this mapping.
    Internally, the MongoDB class will use the `id` key as the primary key.

    Implementation:
    While speed is not the overriding concern, this class is expected to be
    used heavily, so validation is not carried out. Validation is expected to
    be done at the API level.
    """
    def __init__(self, *args, **kwargs):
        """Initialize the MongoRecord with given arguments."""
        super().__init__(*args, **kwargs)
        if "id" not in self:
            raise ValueError(
                "MongoRecord must have an 'id' field as primary key."
            )

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
    """MongoDB backend for the Collections storage interface."""

    def __init__(self, name: str):
        """Initialize the MongoDB collection with a name."""
        super().__init__(name)
        self.client = MongoClient()
        self.db = self.client[DB_NAME]
        self.collection: Collection = self.db[name]

    def get_by_id(self, doc_id: str) -> dict | None:
        """Retrieve a document by its ID."""
        record = self.collection.find_one({PK: doc_id})
        if record:
            return MongoRecord.from_mongo(record).to_record()
        return None

    def get_matching(self, query: dict) -> list[dict]:
        """Retrieve documents matching a query."""
        records = self.collection.find(query)
        if records:
            return [
                MongoRecord.from_mongo(record).to_record()
                for record in records
            ]
        return []

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
