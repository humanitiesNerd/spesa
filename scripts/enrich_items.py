#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ITEMS_CSV = PROJECT_ROOT / "exports" / "items.csv"
MAPPING_CSV = PROJECT_ROOT / "data" / "product_mapping.csv"
OUTPUT_CSV = PROJECT_ROOT / "exports" / "items_enriched.csv"


REQUIRED_MAPPING_COLUMNS = {
    "pattern",
    "description_norm",
    "category",
    "function",
}

OPTIONAL_MAPPING_COLUMNS = [
    "reference_quantity",
    "reference_unit",
    "normalized_automatically",
]


def has_value(value: object) -> bool:
    return pd.notna(value) and str(value).strip() != ""


def load_mapping() -> pd.DataFrame:
    mapping = pd.read_csv(MAPPING_CSV)

    missing_columns = REQUIRED_MAPPING_COLUMNS - set(mapping.columns)
    if missing_columns:
        raise ValueError(
            f"{MAPPING_CSV} non contiene le colonne richieste: "
            f"{sorted(missing_columns)}"
        )

    return mapping


def apply_mapping(items: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    mapping_for_merge = mapping[
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
        mapping_for_merge,
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


def build_missing_mapping_rows(
    items: pd.DataFrame,
    mapping: pd.DataFrame,
) -> pd.DataFrame:
    existing_patterns = set(mapping["pattern"].dropna().astype(str))

    missing_items = items[
        ~items["description_raw"].astype(str).isin(existing_patterns)
    ].copy()

    if missing_items.empty:
        return pd.DataFrame(columns=mapping.columns)

    missing_items = missing_items.drop_duplicates(subset=["description_raw"])

    rows: list[dict[str, object]] = []

    for _, item in missing_items.iterrows():
        description_raw = item["description_raw"]

        row: dict[str, object] = {
            column: pd.NA
            for column in mapping.columns
        }

        row["pattern"] = description_raw
        row["description_norm"] = pd.NA
        row["category"] = pd.NA
        row["function"] = pd.NA

        if "normalized_automatically" in mapping.columns:
            row["normalized_automatically"] = "todo"

        if (
            "reference_quantity" in mapping.columns
            and "quantity" in item
            and has_value(item["quantity"])
        ):
            row["reference_quantity"] = item["quantity"]

        if (
            "reference_unit" in mapping.columns
            and "unit" in item
            and has_value(item["unit"])
        ):
            row["reference_unit"] = item["unit"]

        if (
            "unit_price" in mapping.columns
            and "unit_price" in item
            and has_value(item["unit_price"])
        ):
            row["unit_price"] = item["unit_price"]

        rows.append(row)

    return pd.DataFrame(rows, columns=mapping.columns)


def update_mapping_with_missing_items(
    items: pd.DataFrame,
    mapping: pd.DataFrame,
) -> pd.DataFrame:
    missing_rows = build_missing_mapping_rows(items, mapping)

    if missing_rows.empty:
        print("Nessun nuovo prodotto da aggiungere al mapping.")
        return mapping

    updated_mapping = pd.concat(
        [mapping, missing_rows],
        ignore_index=True,
    )

    updated_mapping.to_csv(MAPPING_CSV, index=False)

    print(
        f"Aggiunte {len(missing_rows)} nuove righe incomplete a: "
        f"{MAPPING_CSV}"
    )

    return updated_mapping


def print_reports(enriched: pd.DataFrame) -> None:
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


def main() -> None:
    items = pd.read_csv(ITEMS_CSV)
    mapping = load_mapping()

    mapping = update_mapping_with_missing_items(items, mapping)

    enriched = apply_mapping(items, mapping)

    enriched["description_norm"] = enriched["description_norm"].fillna(
        enriched["description_raw"]
    )

    enriched["category"] = enriched["category"].fillna(
        enriched["description_norm"]
    )

    enriched["function"] = enriched["function"].fillna(
        enriched["category"]
    )

    OUTPUT_CSV.parent.mkdir(exist_ok=True)
    enriched.to_csv(OUTPUT_CSV, index=False)

    mapped_count = (
        enriched["description_raw"] != enriched["category"]
    ).sum()

    total_count = len(enriched)

    print(f"Salvato: {OUTPUT_CSV}")
    print(f"Righe aggregate tramite mapping: {mapped_count}/{total_count}")

    print_reports(enriched)


if __name__ == "__main__":
    main()
