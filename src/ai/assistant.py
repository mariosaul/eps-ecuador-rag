"""RAG assistant that answers questions about Ecuador's EPS sector."""

from __future__ import annotations

from collections import Counter

import ollama
import pandas as pd

from src.ai.vector_search import search_organizations
from src.config import Config
from src.database import MongoDBConnection


def load_province_context() -> tuple[str, int]:
    """Load all province summaries from the database.

    Returns:
        Tuple of (concatenated summaries text, number of provinces).
    """
    with MongoDBConnection() as db:
        collection = db[Config.COLLECTION_PROVINCES]
        provinces = list(collection.find({}, {"_id": 0, "resumen_ia": 1}))

    context = "\n---\n".join(p["resumen_ia"] for p in provinces)
    return context, len(provinces)


def load_organization_stats() -> tuple[str, int]:
    """Load aggregate statistics about organizations.

    Returns:
        Tuple of (formatted statistics text, total organization count).
    """
    with MongoDBConnection() as db:
        collection = db[Config.COLLECTION_ORGS]
        total = collection.count_documents({})

        stats = f"Total de organizaciones: {total}\n\n"

        for field, label in [
            ("clase", "PRINCIPALES CLASES"),
            ("sector", "POR SECTOR"),
            ("tipo_organizacion", "POR TIPO"),
        ]:
            pipeline = [
                {"$group": {"_id": f"${field}", "cantidad": {"$sum": 1}}},
                {"$sort": {"cantidad": -1}},
            ]
            if field == "clase":
                pipeline.append({"$limit": 5})

            results = list(collection.aggregate(pipeline))
            stats += f"{label}:\n"
            for item in results:
                if item["_id"]:
                    stats += f"  - {item['_id']}: {item['cantidad']}\n"
            stats += "\n"

    return stats, total


def detect_provinces(query: str, province_names: list[str]) -> list[str]:
    """Detect province names mentioned in a query.

    Args:
        query: User's question text.
        province_names: List of valid province names.

    Returns:
        List of detected province names.
    """
    query_lower = query.lower()
    return [
        name for name in province_names
        if str(name).lower() in query_lower
    ]


def detect_sector(organizations: list[dict]) -> str | None:
    """Detect the most common sector from search results.

    Args:
        organizations: List of organization documents from vector search.

    Returns:
        Most common sector name, or None if no sectors found.
    """
    sectors = [
        org.get("sector", "")
        for org in organizations
        if org.get("sector")
    ]
    if sectors:
        return Counter(sectors).most_common(1)[0][0]
    return None


def build_prompt(
    query: str,
    province_context: str,
    org_context: str,
    *,
    system_role: str = "analista de datos de EPS Ecuador",
) -> str:
    """Build the final prompt for the LLM.

    Args:
        query: User's question.
        province_context: Province data context.
        org_context: Organization search results context.
        system_role: Role description for the system prompt.

    Returns:
        Formatted prompt string.
    """
    return (
        f"Eres un {system_role}. Responde en español.\n"
        f"DATOS DISPONIBLES:\n{province_context}\n"
        f"{org_context}\n"
        f"PREGUNTA: {query}\n"
        f"Sin saludos ni cierres. Formato técnico."
    )


def generate_response(prompt: str, *, stream: bool = False, max_tokens: int = 500):
    """Generate a response using the configured LLM.

    Args:
        prompt: The complete prompt to send.
        stream: Whether to stream the response.
        max_tokens: Maximum tokens to generate.

    Returns:
        If stream=False, returns the response text.
        If stream=True, returns a generator of response chunks.
    """
    if stream:
        return ollama.generate(
            model=Config.OLLAMA_MODEL,
            prompt=prompt,
            stream=True,
            options={"temperature": 0.2, "num_predict": max_tokens},
        )

    response = ollama.generate(
        model=Config.OLLAMA_MODEL,
        prompt=prompt,
        options={"temperature": 0.2, "num_predict": max_tokens},
    )
    return response["response"]
