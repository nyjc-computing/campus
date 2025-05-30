"""common/drum/mongodb.py

MongoDB implementation of the Drum interface.
"""

import os
from typing import Any
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from common.schema import Message
from .base import PK, Condition, DrumInterface, DrumResponse, Record, Update

DBNAME = "campus"  # Default database name
MONGOPK = "_id"


def get_conn() -> MongoClient:
    """Get a prepared connection to the MongoDB database."""
    uri = os.environ["MONGODB_URI"]
    return MongoClient(uri)

def get_db() -> Database:
    """Get a prepared database instance."""
    client = get_conn()
    return client[DBNAME]

def get_drum() -> 'MongoDrum':
    """Get a prepared Drum instance."""
    return MongoDrum()

# MongoDB uses _id as the primary key field.
# https://www.mongodb.com/docs/manual/core/document/#field-names
# These functions help to convert between the MongoDB _id field and
# Campus PK field.

def to_mongo_id(record: Record) -> dict[str, Any]:
    """Convert a record to use MongoDB _id field."""
    doc = dict(record.items())
    doc[MONGOPK] = record[PK]
    return doc

def from_mongo_id(record: dict[str, Any]) -> Record:
    """Convert a record to use Campus PK field."""
    record[PK] = record.pop(MONGOPK)
    return record

def error_response(message: str) -> DrumResponse:
    """Helper function to create an error response."""
    return DrumResponse("error", Message.FAILED, message)


class MongoDrum(DrumInterface):
    """MongoDB implementation of the Drum interface."""

    def __init__(self):
        self.client = get_conn()
        self.db = self.client[os.environ.get("MONGODB_DB", "campus")]

    def get_all(self, group: str) -> DrumResponse:
        try:
            docs = list(self.db[group].find())
            if docs:
                return DrumResponse("ok", Message.FOUND, docs)
            else:
                return DrumResponse("ok", Message.EMPTY, docs)
        except PyMongoError as e:
            return error_response(str(e))

    def get_by_id(self, group: str, id: str) -> DrumResponse:
        try:
            doc = self.db[group].find_one({PK: id})
            if doc is None:
                return DrumResponse("error", Message.NOT_FOUND)
            return DrumResponse("ok", Message.FOUND, from_mongo_id(doc))
        except PyMongoError as e:
            return error_response(str(e))

    def get_matching(self, group: str, condition: Condition) -> DrumResponse:
        if PK in condition:
            return error_response(
                f"Condition must not include a {PK} field."
                " Use get_by_id() instead."
            )
        try:
            docs = [from_mongo_id(d) for d in self.db[group].find(condition)]
            if docs:
                return DrumResponse("ok", Message.FOUND, docs)
            else:
                return DrumResponse("ok", Message.EMPTY, docs)
        except PyMongoError as e:
            return error_response(str(e))

    def insert(self, group: str, record: Record) -> DrumResponse:
        try:
            doc = to_mongo_id(record)
            self.db[group].insert_one(doc)
            return DrumResponse("ok", Message.SUCCESS, record)
        except PyMongoError as e:
            return error_response(str(e))

    def set(self, group: str, record: Record) -> DrumResponse:
        try:
            record = to_mongo_id(record)
            result = self.db[group].replace_one(
                {MONGOPK: record[MONGOPK]},
                record,
                upsert=True
            )
            if result.matched_count:
                return DrumResponse("ok", Message.UPDATED)
            else:
                return DrumResponse("ok", Message.SUCCESS)
        except PyMongoError as e:
            return error_response(str(e))

    def update_by_id(self, group: str, id: str, updates: Update) -> DrumResponse:
        if PK in updates:
            return error_response(f"Updates must not include a {PK} field")
        try:
            result = self.db[group].update_one({MONGOPK: id}, {"$set": updates})
            if result.matched_count == 0:
                return DrumResponse("ok", Message.NOT_FOUND)
            return DrumResponse("ok", Message.UPDATED)
        except PyMongoError as e:
            return error_response(str(e))

    def update_matching(self, group: str, updates: Update, condition: Condition) -> DrumResponse:
        if PK in updates:
            return error_response(f"Updates must not include a {PK} field")
        if PK in condition:
            return error_response(
                f"Condition must not include a {PK} field."
                " Use update_by_id() instead."
            )
        try:
            result = self.db[group].update_many(condition, {"$set": updates})
            if result.matched_count == 0:
                return DrumResponse("ok", Message.NOT_FOUND)
            return DrumResponse("ok", Message.UPDATED, result.modified_count)
        except PyMongoError as e:
            return error_response(str(e))

    def delete_by_id(self, group: str, id: str) -> DrumResponse:
        try:
            result = self.db[group].delete_one({MONGOPK: id})
            if result.deleted_count == 0:
                return DrumResponse("ok", Message.NOT_FOUND)
            return DrumResponse("ok", Message.DELETED, result.deleted_count)
        except PyMongoError as e:
            return error_response(str(e))

    def delete_matching(self, group: str, condition: Condition) -> DrumResponse:
        if PK in condition:
            return error_response(
                f"Condition must not include a {PK} field."
                " Use delete_by_id() instead."
            )
        try:
            result = self.db[group].delete_many(condition)
            if result.deleted_count == 0:
                return DrumResponse("ok", Message.NOT_FOUND)
            return DrumResponse("ok", Message.DELETED, result.deleted_count)
        except PyMongoError as e:
            return error_response(str(e))
