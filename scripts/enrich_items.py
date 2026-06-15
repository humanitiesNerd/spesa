#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ITEMS_CSV = PROJECT_ROOT / "exports" / "items.csv"
MAPPING_CSV = PROJECT_ROOT / "data" / "product_mapping.csv"
OUTPUT_CSV = PROJECT_ROOT / "exports" / "items_enriched.csv"
QUANTITY_OVERRIDES_CSV = PROJECT_ROOT / "data" / "item_quantity_overrides.csv"

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
    mapping_columns = [
        "pattern",
        "description_norm",
        "category",
        "function",
    ]

    for optional_column in OPTIONAL_MAPPING_COLUMNS:
        if optional_column in mapping.columns:
            mapping_columns.append(optional_column)

    mapping_for_merge = mapping[mapping_columns].rename(
        columns={
            "pattern": "description_raw",
            "description_norm": "mapped_description_norm",
            "category": "mapped_category",
            "function": "mapped_function",
            "reference_quantity": "mapped_reference_quantity",
            "reference_unit": "mapped_reference_unit",
            "normalized_automatically": "mapped_normalized_automatically",
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

    if "mapped_reference_quantity" in enriched.columns:
        enriched["reference_quantity"] = enriched["mapped_reference_quantity"]

    if "mapped_reference_unit" in enriched.columns:
        enriched["reference_unit"] = enriched["mapped_reference_unit"]

    if "mapped_normalized_automatically" in enriched.columns:
        enriched["normalized_automatically"] = enriched[
            "mapped_normalized_automatically"
        ]

    columns_to_drop = [
        column
        for column in [
            "mapped_description_norm",
            "mapped_category",
            "mapped_function",
            "mapped_reference_quantity",
            "mapped_reference_unit",
            "mapped_normalized_automatically",
        ]
        if column in enriched.columns
    ]

    enriched = enriched.drop(columns=columns_to_drop)

    return enriched


def apply_quantity_overrides(items: pd.DataFrame) -> pd.DataFrame:
    if not QUANTITY_OVERRIDES_CSV.exists():
        return items

    overrides = pd.read_csv(QUANTITY_OVERRIDES_CSV)

    required_columns = {
        "receipt_id",
        "line_index",
        "reference_quantity",
        "reference_unit",
        "status",
    }

    missing = required_columns - set(overrides.columns)
    if missing:
        raise ValueError(
            f"Mancano colonne in {QUANTITY_OVERRIDES_CSV}: {sorted(missing)}"
        )

    valid_overrides = overrides[
        overrides["status"].astype(str).str.strip().eq("ok")
    ].copy()

    if valid_overrides.empty:
        return items

    valid_overrides = valid_overrides[
        [
            "receipt_id",
            "line_index",
            "reference_quantity",
            "reference_unit",
        ]
    ].copy()

    valid_overrides = valid_overrides.rename(
        columns={
            "reference_quantity": "override_reference_quantity",
            "reference_unit": "override_reference_unit",
        }
    )

    merged = items.merge(
        valid_overrides,
        on=["receipt_id", "line_index"],
        how="left",
    )

    has_override = (
        merged["override_reference_quantity"].notna()
        & merged["override_reference_unit"].notna()
    )

    merged.loc[has_override, "reference_quantity"] = merged.loc[
        has_override, "override_reference_quantity"
    ]

    merged.loc[has_override, "reference_unit"] = merged.loc[
        has_override, "override_reference_unit"
    ]

    merged = merged.drop(
        columns=[
            "override_reference_quantity",
            "override_reference_unit",
        ]
    )

    print(f"Applicati override quantità: {has_override.sum()}")

    return merged


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

    enriched = apply_quantity_overrides(enriched)

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
