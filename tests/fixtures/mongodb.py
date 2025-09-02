"""tests.fixtures.mongodb

Functions for MongoDB database management during testing.
"""

import os
from pymongo import MongoClient


def get_mongodb_uri() -> str:
    """Get MongoDB connection URI for testing.

    Returns:
        MongoDB connection URI string

    Raises:
        OSError: If required environment variables are not set
    """
    host = os.environ["MONGODB_HOST"]
    port = os.environ["MONGODB_PORT"]
    username = os.environ["MONGO_INITDB_ROOT_USERNAME"]
    password = os.environ["MONGO_INITDB_ROOT_PASSWORD"]

    return f"mongodb://{username}:{password}@{host}:{port}/"


def database_exists(database_name: str) -> bool:
    """Check if a MongoDB database exists.

    Args:
        database_name: Name of the database to check

    Returns:
        True if database exists, False otherwise

    Raises:
        ServerSelectionTimeoutError: If MongoDB connection fails
        OperationFailure: If authentication fails
    """
    uri = get_mongodb_uri()

    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        # Test the connection
        client.admin.command('ping')

        # List all database names
        db_names = client.list_database_names()
        return database_name in db_names


def create_database(database_name: str) -> None:
    """Create a MongoDB database by creating a dummy collection.

    MongoDB creates databases lazily, so we need to create a collection
    to actually create the database.

    Args:
        database_name: Name of the database to create

    Raises:
        ServerSelectionTimeoutError: If MongoDB connection fails
        OperationFailure: If authentication fails
    """
    uri = get_mongodb_uri()

    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        db = client[database_name]
        # Create a dummy collection to ensure the database is created
        # This collection will be removed when we initialize the first real collection
        db.create_collection("_init_collection")
        # Insert and remove a dummy document to persist the database
        collection = db["_init_collection"]
        result = collection.insert_one({"_init": True})
        collection.delete_one({"_id": result.inserted_id})


def ensure_database_exists(database_name: str) -> None:
    """Ensure a MongoDB database exists, creating it if necessary.

    Args:
        database_name: Name of the database to ensure exists

    Raises:
        ServerSelectionTimeoutError: If MongoDB connection fails
        OperationFailure: If authentication fails
    """
    print(f"🗃️  Ensuring MongoDB database '{database_name}' exists...")

    if database_exists(database_name):
        print(f"✅ MongoDB database '{database_name}' already exists")
    else:
        print(f"📝 Creating MongoDB database '{database_name}'...")
        create_database(database_name)
        print(f"✅ MongoDB database '{database_name}' created successfully")


def test_connection() -> None:
    """Test MongoDB connection.

    Raises:
        ServerSelectionTimeoutError: If MongoDB connection fails
        OperationFailure: If authentication fails
    """
    uri = get_mongodb_uri()

    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        # Test the connection
        client.admin.command('ping')
        print("✅ MongoDB connection successful")
