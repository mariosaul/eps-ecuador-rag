"""Batch embedding generator for organization documents.

Processes organizations that don't have embeddings yet and generates
vector representations using Ollama's nomic-embed-text model.

Usage:
    python -m src.embeddings.generator
"""

from __future__ import annotations

import sys
import time

import ollama

from src.config import Config
from src.database import MongoDBConnection


def build_summary(doc: dict) -> str:
    """Build a text summary of an organization for embedding.

    Args:
        doc: Organization document from MongoDB.

    Returns:
        Formatted summary string.
    """
    name = doc.get("nombre", "Sin nombre")
    ruc = doc.get("ruc_limpio", "Sin RUC")
    clase = doc.get("clase", "No especificada")
    grupo = doc.get("grupo", "No especificado")
    sector = doc.get("sector", "No especificado")
    org_type = doc.get("tipo_organizacion", "No especificado")

    details = ""
    if isinstance(doc.get("detalles_fijos"), dict):
        fixed = doc["detalles_fijos"]
        if "ciudad" in fixed:
            details += f"Ubicada en {fixed['ciudad']}. "
        if "estado" in fixed:
            details += f"Estado: {fixed['estado']}. "
        if "fecha_constitucion" in fixed:
            details += f"Constituida en {fixed['fecha_constitucion']}. "

    timeline = ""
    if isinstance(doc.get("linea_tiempo"), list):
        timeline = f"Cuenta con {len(doc['linea_tiempo'])} eventos en su historial. "

    return (
        f"Organización: {name}. "
        f"RUC: {ruc}. "
        f"Clasificada como {clase} del grupo {grupo}. "
        f"Pertenece al {sector}. "
        f"Tipo de organización: {org_type}. "
        f"{details}{timeline}"
    )


def generate_embeddings() -> None:
    """Generate embeddings for all organizations that don't have one yet."""
    batch_size = Config.EMBEDDING_BATCH_SIZE

    with MongoDBConnection() as db:
        collection = db[Config.COLLECTION_ORGS]

        # Only process documents without embeddings
        query_filter = {"embedding_vector": {"$exists": False}}
        total_pending = collection.count_documents(query_filter)

        if total_pending == 0:
            print("✅ All documents already have embeddings. Nothing to do!")
            return

        print(f"📊 Pending documents: {total_pending}")
        print(f"📦 Batch size: {batch_size}")

        # Fetch all pending documents
        documents = list(collection.find(
            query_filter,
            {
                "nombre": 1, "ruc_limpio": 1, "clase": 1,
                "grupo": 1, "sector": 1, "tipo_organizacion": 1,
                "detalles_fijos": 1, "linea_tiempo": 1,
            },
        ))

        processed = 0
        errors = 0
        start_time = time.time()
        total_batches = (len(documents) + batch_size - 1) // batch_size

        for batch_start in range(0, len(documents), batch_size):
            batch = documents[batch_start : batch_start + batch_size]
            batch_num = batch_start // batch_size + 1

            try:
                summaries = [build_summary(doc) for doc in batch]

                response = ollama.embed(
                    model=Config.OLLAMA_EMBED_MODEL,
                    input=summaries,
                )
                vectors = response["embeddings"]

                for doc, summary, vector in zip(batch, summaries, vectors):
                    try:
                        collection.update_one(
                            {"_id": doc["_id"]},
                            {"$set": {
                                "resumen_ia": summary,
                                "embedding_vector": vector,
                            }},
                        )
                        processed += 1
                    except Exception:
                        errors += 1

                elapsed = time.time() - start_time
                rate = (processed + errors) / elapsed if elapsed > 0 else 0
                remaining = (len(documents) - processed - errors) / rate if rate > 0 else 0

                print(
                    f"📦 Batch {batch_num}/{total_batches} | "
                    f"✅ {processed} | ❌ {errors} | "
                    f"⚡ {rate:.1f} docs/s | "
                    f"⏳ {remaining / 60:.0f} min remaining"
                )
            except Exception as e:
                errors += len(batch)
                print(f"❌ Batch {batch_num} error: {e}")

        total_time = time.time() - start_time
        print(f"\n{'=' * 60}")
        print(f"✅ PROCESSING COMPLETE")
        print(f"   Successful: {processed}")
        print(f"   Errors: {errors}")
        print(f"   Total time: {total_time / 60:.1f} minutes")
        if processed > 0:
            print(f"   Average speed: {processed / total_time:.1f} docs/second")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    generate_embeddings()
