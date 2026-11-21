"""MongoDB connection manager with context manager support."""

from __future__ import annotations

from pymongo import MongoClient
from pymongo.database import Database

from src.config import Config


class MongoDBConnection:
    """Context manager for MongoDB connections.

    Usage:
        with MongoDBConnection() as db:
            docs = list(db["organizaciones"].find())
    """

    def __init__(self, uri: str | None = None, database: str | None = None) -> None:
        self._uri = uri or Config.MONGODB_URI
        self._database = database or Config.MONGODB_DATABASE
        self._client: MongoClient | None = None

    def __enter__(self) -> Database:
        Config.validate()
        self._client = MongoClient(self._uri, serverSelectionTimeoutMS=5000)
        self._client.admin.command("ping")
        return self._client[self._database]

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            self._client.close()

    @classmethod
    def get_client(cls) -> MongoClient:
        """Get a raw MongoClient (caller is responsible for closing)."""
        Config.validate()
        return MongoClient(Config.MONGODB_URI, serverSelectionTimeoutMS=5000)
