"""Vector search operations using MongoDB Atlas and Ollama embeddings."""

from __future__ import annotations

import ollama
from pymongo.database import Database

from src.config import Config
from src.database import MongoDBConnection


def generate_query_embedding(query: str) -> list[float]:
    """Generate an embedding vector for a search query.

    Args:
        query: Natural language search query.

    Returns:
        Embedding vector as a list of floats.
    """
    response = ollama.embeddings(
        model=Config.OLLAMA_EMBED_MODEL,
        prompt=query,
    )
    return response["embedding"]


def search_organizations(
    query: str,
    limit: int = 5,
    db: Database | None = None,
) -> list[dict]:
    """Find organizations relevant to a query using vector similarity search.

    Uses MongoDB Atlas Vector Search to find the most semantically similar
    organizations based on their embedding vectors.

    Args:
        query: Natural language search query.
        limit: Maximum number of results to return.
        db: Optional database connection (creates one if not provided).

    Returns:
        List of organization documents with similarity scores.
    """
    embedding = generate_query_embedding(query)

    pipeline = [
        {
            "$vectorSearch": {
                "index": Config.VECTOR_SEARCH_INDEX,
                "path": "embedding_vector",
                "queryVector": embedding,
                "numCandidates": Config.VECTOR_SEARCH_CANDIDATES,
                "limit": limit,
            }
        },
        {
            "$project": {
                "_id": 0,
                "nombre": 1,
                "ruc_limpio": 1,
                "clase": 1,
                "grupo": 1,
                "sector": 1,
                "tipo_organizacion": 1,
                "resumen_ia": 1,
                "detalles_fijos": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    try:
        if db is not None:
            return list(db[Config.COLLECTION_ORGS].aggregate(pipeline))

        with MongoDBConnection() as db_conn:
            return list(db_conn[Config.COLLECTION_ORGS].aggregate(pipeline))
    except Exception:
        return []
