#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ITEMS_CSV = PROJECT_ROOT / "exports" / "items.csv"
MAPPING_CSV = PROJECT_ROOT / "data" / "product_mapping.csv"
OUTPUT_CSV = PROJECT_ROOT / "exports" / "items_enriched.csv"


REQUIRED_MAPPING_COLUMNS = {
    "match_type",
    "pattern",
    "description_norm",
    "category",
    "function",
}


def load_mapping() -> pd.DataFrame:
    mapping = pd.read_csv(MAPPING_CSV)

    missing_columns = REQUIRED_MAPPING_COLUMNS - set(mapping.columns)
    if missing_columns:
        raise ValueError(
            f"{MAPPING_CSV} non contiene le colonne richieste: "
            f"{sorted(missing_columns)}"
        )

    return mapping


def apply_contains_mapping(enriched: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    contains_mapping = mapping[mapping["match_type"] == "contains"]

    for _, row in contains_mapping.iterrows():
        mask = enriched["description_raw"].str.contains(
            row["pattern"],
            case=False,
            regex=False,
            na=False,
        )

        enriched.loc[mask, "description_norm"] = row["description_norm"]
        enriched.loc[mask, "category"] = row["category"]
        enriched.loc[mask, "function"] = row["function"]

    return enriched

def apply_exact_mapping(items: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    exact_mapping = mapping[mapping["match_type"] == "exact"].copy()

    exact_mapping = exact_mapping[
        [
            "pattern",
            "description_norm",
            "category",
            "function",
        ]
    ].rename(
        columns={
            "pattern": "description_raw",
            "description_norm": "mapped_description_norm",
            "category": "mapped_category",
            "function": "mapped_function",
        }
    )

    enriched = items.merge(
        exact_mapping,
        on="description_raw",
        how="left",
    )

    enriched["description_norm"] = enriched["mapped_description_norm"].combine_first(
        enriched["description_norm"]
    )

    enriched["category"] = enriched["mapped_category"].combine_first(
        enriched["category"]
    )

    enriched["function"] = enriched["mapped_function"]



    enriched = enriched.drop(
        columns=[
            "mapped_description_norm",
            "mapped_category",
            "mapped_function",
        ]
    )

    return enriched


def main() -> None:
    items = pd.read_csv(ITEMS_CSV)
    mapping = load_mapping()

    unsupported_match_types = sorted(
        set(mapping["match_type"].dropna()) - {"exact", "contains"}
    )

    if unsupported_match_types:
        raise ValueError(
            "match_type non supportati in product_mapping.csv: "
            f"{unsupported_match_types}"
        )

    enriched = apply_exact_mapping(items, mapping)
    enriched = apply_contains_mapping(enriched, mapping)

    enriched["description_norm"] = (
    enriched["description_norm"]
        .fillna(enriched["description_raw"])
    )






    print()
    print("Spesa per prodotto")
    print("------------------")

    product_report = (
        enriched.groupby(["description_norm", "category", "function"])["net_amount"]
        .sum()
        .reset_index()
        .sort_values("net_amount", ascending=False)
    )

    product_report["net_amount"] = product_report["net_amount"].round(2)

    print(product_report.to_string(index=False))




    



    
    enriched["category"] = (
        enriched["category"]
        .fillna(enriched["description_norm"])
    )


    enriched["function"] = (
        enriched["function"]
        .fillna(enriched["category"])
    )

    OUTPUT_CSV.parent.mkdir(exist_ok=True)

    enriched.to_csv(OUTPUT_CSV, index=False)

    mapped_count = (
        enriched["description_raw"] != enriched["category"]
    ).sum()

    total_count = len(enriched)

    print(f"Salvato: {OUTPUT_CSV}")
    print(
        f"Righe aggregate tramite mapping: "
        f"{mapped_count}/{total_count}"
    )



    print()
    print("Spesa per categoria")
    print("-------------------")

    category_report = (
        enriched.groupby(["category", "function"])["net_amount"]
        .sum()
        .reset_index()
        .sort_values("net_amount", ascending=False)
    )

    category_report["net_amount"] = category_report["net_amount"].round(2)

    print(category_report.to_string(index=False))




    
    print()
    print("Spesa per funzione")
    print("------------------")
    print(
        enriched.groupby("function")["net_amount"]
        .sum()
        .sort_values(ascending=False)
        .round(2)
    )

if __name__ == "__main__":
    main()
