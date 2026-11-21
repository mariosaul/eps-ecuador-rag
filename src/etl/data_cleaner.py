"""Data cleaning utilities for preprocessing raw CSV files.

Handles encoding issues, column normalization, numeric formatting,
and geographic code standardization.

Usage:
    python -m src.etl.data_cleaner --type socios --input path/to/file.csv
"""

from __future__ import annotations

import os
import re

import pandas as pd


def clean_socios_file(input_path: str, output_path: str) -> None:
    """Clean and normalize a socios (members) CSV file.

    Handles:
    - Encoding detection and normalization (latin-1 → utf-8)
    - Column name standardization
    - Numeric extraction for member counts
    - Geographic code formatting (DPA codes)
    - Date formatting

    Args:
        input_path: Path to the raw CSV file.
        output_path: Path for the cleaned output file.
    """
    print(f"--- Processing: {os.path.basename(input_path)} ---")

    try:
        df = pd.read_csv(input_path, sep=None, engine="python", encoding="latin-1", dtype=str)
        df.columns = [col.strip().upper() for col in df.columns]

        # Fix encoding issues in text columns
        for col in df.columns:
            df[col] = (
                df[col]
                .str.encode("latin-1", errors="ignore")
                .str.decode("utf-8", errors="ignore")
                .str.strip()
                .str.upper()
            )

        # Clean numeric member counts
        if "NRO SOCIOS" in df.columns:
            df["NRO SOCIOS"] = (
                pd.to_numeric(
                    df["NRO SOCIOS"].str.extract(r"(\d+)", expand=False),
                    errors="coerce",
                )
                .fillna(0)
                .astype(int)
            )

        # Standardize geographic codes
        dpa_col = "DPA PARROQUIA MATRIZ"
        if dpa_col in df.columns:
            df[dpa_col] = "'" + df[dpa_col].str.replace(r"\.0$", "", regex=True).str.zfill(6)

        # Format dates
        if "FECHA CORTE" in df.columns:
            df["FECHA CORTE"] = pd.to_datetime(df["FECHA CORTE"], errors="coerce").dt.strftime("%d-%m-%Y")

        if len(df) > 0:
            df.to_csv(output_path, index=False, sep=",", encoding="utf-8-sig")
            print(f"✅ Cleaned file saved: {os.path.basename(output_path)}")
        else:
            print("⚠️ Output file would be empty, skipping.")

    except Exception as e:
        print(f"❌ Critical error: {e}")


def extract_statistical_sample(
    input_path: str,
    output_path: str,
    fraction: float = 0.05,
    seed: int = 42,
) -> None:
    """Extract a reproducible statistical sample from a large CSV file.

    Uses chunked reading to handle files that don't fit in memory.

    Args:
        input_path: Path to the large input CSV.
        output_path: Path for the sample output file.
        fraction: Fraction of data to sample (default 5%).
        seed: Random seed for reproducibility.
    """
    print(f"--- Statistical Sampling ({fraction * 100}%) ---")

    if not os.path.exists(input_path):
        print(f"❌ File not found: {input_path}")
        return

    try:
        chunk_size = 1_000_000
        reader = pd.read_csv(input_path, chunksize=chunk_size, dtype=str, low_memory=False)
        samples = []

        for i, chunk in enumerate(reader):
            sample = chunk.sample(frac=fraction, random_state=seed)
            samples.append(sample)
            processed = (i + 1) * chunk_size
            print(f"✅ Processed {processed:,} records (sample: {sum(len(s) for s in samples):,})")

        result = pd.concat(samples)
        result.columns = [c.upper().strip() for c in result.columns]
        result.to_csv(output_path, index=False, encoding="utf-8-sig")

        print(f"\n🚀 Sampling complete! {len(result):,} records saved to {output_path}")

    except Exception as e:
        print(f"❌ Sampling error: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Clean EPS data files")
    parser.add_argument("--type", choices=["socios", "sample"], required=True)
    parser.add_argument("--input", required=True, help="Input file path")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--fraction", type=float, default=0.05, help="Sample fraction")

    args = parser.parse_args()

    if args.type == "socios":
        clean_socios_file(args.input, args.output)
    elif args.type == "sample":
        extract_statistical_sample(args.input, args.output, fraction=args.fraction)
