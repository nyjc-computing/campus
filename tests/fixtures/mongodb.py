"""tests.fixtures.mongodb

Functions for MongoDB database management during testing.
"""

from pymongo import MongoClient

from campus.common import devops
from campus.common import env


def get_mongodb_uri(database_name: str | None = None) -> str:
    """Get MongoDB connection URI for testing.

    Args:
        database_name: Optional name of the database to connect to (e.g., "storagedb").
                      If None, returns a general connection URI.

    Returns:
        MongoDB connection URI string with authSource=admin for dev container.
        The authSource=admin parameter is required because in the dev container
        setup, the MongoDB root user credentials are stored in the 'admin'
        database, but we need to connect to other databases. MongoDB requires
        authentication against the database where the user was created (admin),
        then allows access to the target database.

    Raises:
        OSError: If required environment variables are not set
    """
    host = env.MONGODB_HOST
    port = env.MONGODB_PORT
    username = env.MONGO_INITDB_ROOT_USERNAME
    password = env.MONGO_INITDB_ROOT_PASSWORD

    if database_name:
        return f"mongodb://{username}:{password}@{host}:{port}/{database_name}?authSource=admin"
    else:
        return f"mongodb://{username}:{password}@{host}:{port}/?authSource=admin"


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
        RuntimeError: If MongoDB connection fails or database cannot be ensured
        ServerSelectionTimeoutError: If MongoDB connection fails
        OperationFailure: If authentication fails
    """
    print(f"🗃️  Ensuring MongoDB database '{database_name}' exists...")

    try:
        if database_exists(database_name):
            print(f"✅ MongoDB database '{database_name}' already exists")
        else:
            print(f"📝 Creating MongoDB database '{database_name}'...")
            create_database(database_name)
            print(f"✅ MongoDB database '{database_name}' created successfully")
    except Exception as e:
        raise RuntimeError(
            f"Failed to ensure MongoDB database '{database_name}' exists: {e}"
        ) from e


@devops.require_env(devops.TESTING)
def purge_database(database_name: str) -> None:
    """Purge (drop and recreate) a MongoDB database for clean testing state.

    Args:
        database_name: Name of the database to purge

    Raises:
        ServerSelectionTimeoutError: If MongoDB connection fails
        OperationFailure: If authentication fails
    """
    uri = get_mongodb_uri()

    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        # Drop the database if it exists
        if database_name in client.list_database_names():
            client.drop_database(database_name)

        # Recreate the database
        create_database(database_name)


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
