"""Centralized configuration for the EPS Ecuador RAG platform."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    # MongoDB
    MONGODB_URI: str = os.getenv("MONGODB_URI", "")
    MONGODB_DATABASE: str = os.getenv("MONGODB_DATABASE", "Tesis_EPS")

    # Collections
    COLLECTION_ORGS: str = "organizaciones"
    COLLECTION_PROVINCES: str = "estadisticas_provincias"

    # Ollama Models
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
    OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # Embedding Settings
    EMBEDDING_BATCH_SIZE: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "1900"))
    VECTOR_SEARCH_INDEX: str = "vector_index_organizaciones"
    VECTOR_SEARCH_CANDIDATES: int = 100

    # Power BI
    POWERBI_EMBED_URL: str = os.getenv(
        "POWERBI_EMBED_URL",
        ""
    )

    @classmethod
    def validate(cls) -> None:
        """Raise an error if required configuration is missing."""
        if not cls.MONGODB_URI:
            raise ValueError(
                "MONGODB_URI is not set. "
                "Copy .env.example to .env and fill in your credentials."
            )
