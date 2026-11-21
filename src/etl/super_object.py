"""ETL pipeline to build unified organization objects from multiple data sources.

Merges registration records, financial data, member (socios) counts,
and poverty indicators into a single JSON dataset spanning 2022-2024.

Usage:
    python -m src.etl.super_object
"""

from __future__ import annotations

import json
import os

import pandas as pd


# Default data paths (override via environment or CLI args)
DEFAULT_BASE_PATH = os.getenv("EPS_DATA_PATH", r"C:\Users\mario\Downloads")

PATHS = {
    "enemdu": os.path.join(DEFAULT_BASE_PATH, "POBREZA", "ENEMDU24_LIMPIA_FINAL.csv"),
    "registros": os.path.join(DEFAULT_BASE_PATH, "REGISTROS"),
    "financiero": os.path.join(DEFAULT_BASE_PATH, "FINANCIERO"),
    "socios": os.path.join(DEFAULT_BASE_PATH, "SOCIOS"),
}

YEARS = ["2022", "2023", "2024"]


def find_ruc_column(df: pd.DataFrame) -> str | None:
    """Auto-detect the RUC column in a DataFrame.

    Args:
        df: Input DataFrame.

    Returns:
        Column name containing 'RUC', or None if not found.
    """
    for col in df.columns:
        if "RUC" in col.upper():
            return col
    return None


def load_poverty_context(path: str) -> dict[str, str]:
    """Load poverty percentages by province from ENEMDU data.

    Args:
        path: Path to the cleaned ENEMDU CSV file.

    Returns:
        Dictionary mapping province names to poverty percentage strings.
    """
    if not os.path.exists(path):
        print(f"⚠️ ENEMDU file not found at: {path}")
        return {}

    try:
        df = pd.read_csv(path, usecols=["PROVINCIA", "ESTADO_POBREZA"], dtype=str)
        df.columns = df.columns.str.strip().str.upper()
        return df.groupby("PROVINCIA")["ESTADO_POBREZA"].apply(
            lambda x: f"{round((x == 'POBRE').mean() * 100, 2)}%"
        ).to_dict()
    except Exception as e:
        print(f"⚠️ Error loading ENEMDU: {e}")
        return {}


def build_super_objects(
    base_path: str = DEFAULT_BASE_PATH,
    output_path: str | None = None,
) -> list[dict]:
    """Build unified organization objects from all data sources.

    Merges 3 years of registros, financial, and socios data with
    provincial poverty context into a single dataset.

    Args:
        base_path: Root directory containing the data folders.
        output_path: Where to save the JSON output. Defaults to
                     base_path/DATA_MAESTRA_EPS.json.

    Returns:
        List of unified organization dictionaries.
    """
    if output_path is None:
        output_path = os.path.join(base_path, "DATA_MAESTRA_EPS.json")

    print("--- 🧬 BUILDING UNIFIED ORGANIZATION OBJECTS (2022-2024) ---")

    poverty_context = load_poverty_context(PATHS["enemdu"])
    if poverty_context:
        print(f"✅ Poverty context loaded: {len(poverty_context)} provinces")

    organizations: dict[str, dict] = {}

    for year in YEARS:
        print(f"\n📂 Processing year: {year}...")

        reg_path = os.path.join(PATHS["registros"], f"{year}_LIMPIO_FINAL.csv")
        fin_path = os.path.join(PATHS["financiero"], f"{year}_COMPLETO_LIMPIO.csv")
        soc_path = os.path.join(PATHS["socios"], f"{year}_LIMPIO_FINAL.csv")

        if not all(os.path.exists(f) for f in [reg_path, fin_path, soc_path]):
            print(f"   ⚠️ Skipping {year}: missing files")
            continue

        # Load DataFrames
        reg = pd.read_csv(reg_path, dtype=str)
        fin = pd.read_csv(fin_path, dtype=str)
        soc = pd.read_csv(soc_path, dtype=str)

        for df in [reg, fin, soc]:
            df.columns = df.columns.str.strip().str.upper()

        ruc_reg = find_ruc_column(reg)
        ruc_fin = find_ruc_column(fin)
        ruc_soc = find_ruc_column(soc)

        # Build lookup dictionaries for O(1) access
        fin_lookup = fin.set_index(ruc_fin).to_dict("index") if ruc_fin else {}
        soc_lookup = (
            soc.groupby(ruc_soc)["NRO SOCIOS"]
            .apply(lambda x: pd.to_numeric(x, errors="coerce").sum())
            .to_dict()
            if ruc_soc
            else {}
        )

        total = len(reg)
        for i, (_, row) in enumerate(reg.iterrows()):
            ruc = row[ruc_reg]
            if pd.isna(ruc):
                continue

            # Create base record on first encounter
            if ruc not in organizations:
                province = row.get("PROVINCIA", "DESCONOCIDO")
                organizations[ruc] = {
                    "ruc": ruc,
                    "nombre": row.get("DW AMBITO", row.get("ORGANIZACION", "DESCONOCIDO")),
                    "detalles_fijos": {
                        "tipo": row.get("TIPO", "N/A"),
                        "sector": row.get("SECTOR", "N/A"),
                        "provincia": province,
                        "pobreza_entorno": poverty_context.get(province, "0%"),
                    },
                    "linea_tiempo": [],
                }

            # Append yearly metrics
            fin_data = fin_lookup.get(ruc, {})
            n_socios = soc_lookup.get(ruc, 0)

            organizations[ruc]["linea_tiempo"].append({
                "anio": year,
                "metricas": {
                    "activos": fin_data.get("ACTIVO", fin_data.get("TOTAL ACTIVO", "0")),
                    "utilidad": fin_data.get("UTILIDAD", fin_data.get("UTILIDAD DEL EJERCICIO", "0")),
                    "total_socios": int(n_socios),
                },
            })

            if i % 1000 == 0:
                print(f"   ⏳ {year}: {i}/{total} organizations processed...", end="\r")

    # Save output
    if organizations:
        result = list(organizations.values())
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
        print(f"\n\n✨ Success! Processed {len(result)} unique organizations.")
        print(f"📍 Saved to: {output_path}")
        return result

    print("\n🛑 No data could be generated. Check your input files.")
    return []


if __name__ == "__main__":
    build_super_objects()
