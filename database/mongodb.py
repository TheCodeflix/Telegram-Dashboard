import os
import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ConfigurationError

logger = logging.getLogger(__name__)

_client = None
_db = None


def connect_to_mongodb():
    global _client, _db

    mongodb_uri = os.environ.get("MONGODB_URI")
    database_name = os.environ.get("DATABASE_NAME", "telegram_dashboard")

    if not mongodb_uri:
        logger.error("MONGODB_URI environment variable is not set")
        raise ValueError("MONGODB_URI environment variable is not set")

    try:
        _client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        _client.admin.command("ping")
        _db = _client[database_name]
        logger.info("Successfully connected to MongoDB database: %s", database_name)
        return _db
    except ConnectionFailure as e:
        logger.error("Failed to connect to MongoDB: %s", str(e))
        raise
    except ConfigurationError as e:
        logger.error("MongoDB configuration error: %s", str(e))
        raise


def get_collection(collection_name):
    global _db

    if _db is None:
        connect_to_mongodb()

    return _db[collection_name]


def close_connection():
    global _client, _db

    if _client is not None:
        try:
            _client.close()
            _client = None
            _db = None
            logger.info("MongoDB connection closed")
        except Exception as e:
            logger.error("Error closing MongoDB connection: %s", str(e))


def get_database():
    global _db
    if _db is None:
        connect_to_mongodb()
    return _db
