"""Data loading utilities for uploading processed data to MongoDB Atlas.

Usage:
    python -m src.etl.data_loader
"""

from __future__ import annotations

import json
import os

import pandas as pd

from src.config import Config
from src.database import MongoDBConnection


def upload_organizations(json_path: str) -> int:
    """Upload organization data from a JSON file to MongoDB Atlas.

    Args:
        json_path: Path to the DATA_MAESTRA_EPS.json file.

    Returns:
        Number of documents uploaded.

    Raises:
        FileNotFoundError: If the JSON file doesn't exist.
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Data file not found: {json_path}")

    print("🚀 Connecting to MongoDB Atlas...")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"📦 Uploading {len(data)} records...")

    with MongoDBConnection() as db:
        collection = db[Config.COLLECTION_ORGS]
        collection.delete_many({})  # Clear existing data
        collection.insert_many(data)

    print(f"✅ Successfully uploaded {len(data)} organizations.")
    return len(data)


def update_province_statistics(
    rebpe_path: str,
    socios_paths: list[str],
) -> int:
    """Calculate and update province-level statistics in MongoDB.

    Computes incursion rates by comparing SEPS member counts against
    the adult population from REBPE census data.

    Args:
        rebpe_path: Path to the normalized REBPE CSV.
        socios_paths: List of paths to yearly socios CSV files.

    Returns:
        Number of provinces updated.
    """

    def normalize_text(text) -> str:
        if pd.isna(text):
            return ""
        return (
            str(text).upper().strip()
            .replace("Á", "A").replace("É", "E")
            .replace("Í", "I").replace("Ó", "O").replace("Ú", "U")
        )

    # Load adult population by province
    print("⏳ Processing REBPE (filtering adults 18+)...")
    df_rebpe = pd.read_csv(rebpe_path, low_memory=False)
    adults = df_rebpe[df_rebpe["EDAD"] >= 18]
    population = adults.groupby("PROV_RES").size().to_dict()

    # Load and aggregate socios across years
    print("⏳ Processing SEPS member records...")
    socios_frames = []
    for path in socios_paths:
        try:
            df = pd.read_csv(path, low_memory=False)
            df.columns = [c.strip().upper() for c in df.columns]

            if "NRO SOCIOS" not in df.columns:
                socios_col = [c for c in df.columns if "SOCIO" in c]
                if socios_col:
                    df.rename(columns={socios_col[0]: "NRO SOCIOS"}, inplace=True)

            socios_frames.append(df)
        except Exception as e:
            print(f"❌ Error reading {path}: {e}")

    df_socios = pd.concat(socios_frames, ignore_index=True)

    # Find the province column
    prov_col = next(
        (c for c in df_socios.columns if c in ["PROVINCIA", "PROV_RES", "DPA_PROVINCIA"]),
        next((c for c in df_socios.columns if "PROV" in c), None),
    )

    socios_count = {}
    if prov_col:
        socios_count = df_socios.groupby(prov_col)["NRO SOCIOS"].sum().to_dict()

    # Normalize keys
    pop_clean = {normalize_text(k): v for k, v in population.items()}
    soc_clean = {normalize_text(k): v for k, v in socios_count.items()}

    # Update MongoDB
    print("🚀 Updating MongoDB Atlas...")
    updated = 0

    with MongoDBConnection() as db:
        provinces = list(db[Config.COLLECTION_PROVINCES].find())
        for prov in provinces:
            name_key = normalize_text(prov["PROV_RES"])
            adult_pop = pop_clean.get(name_key, 0)
            members = soc_clean.get(name_key, 0)

            incursion = (members / adult_pop * 100) if adult_pop > 0 else 0

            if incursion < 2.0:
                classification = "Zona de Silencio"
            elif incursion > 10.0:
                classification = "Alta Inclusión"
            else:
                classification = "Desarrollo Medio"

            db[Config.COLLECTION_PROVINCES].update_one(
                {"_id": prov["_id"]},
                {"$set": {
                    "poblacion_adulta_rebpe": adult_pop,
                    "socios_seps_conteo": members,
                    "porcentaje_incursion": round(incursion, 2),
                    "clasificacion_inclusion": classification,
                }},
            )
            updated += 1

    print(f"✅ Updated {updated} provinces with adult population and member data.")
    return updated


if __name__ == "__main__":
    default_path = os.path.join(
        os.getenv("EPS_DATA_PATH", r"C:\Users\mario\Downloads"),
        "DATA_MAESTRA_EPS.json",
    )
    upload_organizations(default_path)
