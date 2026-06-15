#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ITEMS_CSV = PROJECT_ROOT / "exports" / "items_enriched.csv"
MAPPING_CSV = PROJECT_ROOT / "data" / "product_mapping.csv"


def has_value(value: object) -> bool:
    return pd.notna(value) and str(value).strip() != ""


def product_has_reference(mapping_group: pd.DataFrame) -> bool:
    return (
        mapping_group["reference_quantity"].apply(has_value)
        & mapping_group["reference_unit"].apply(has_value)
    ).any()


def main() -> None:
    items = pd.read_csv(ITEMS_CSV)
    mapping = pd.read_csv(MAPPING_CSV)

    required_item_columns = {
        "description_norm",
        "description_raw",
        "store_brand",
        "quantity",
        "unit_price",
        "net_amount",
    }

    missing_item_columns = required_item_columns - set(items.columns)
    if missing_item_columns:
        raise ValueError(
            f"{ITEMS_CSV} non contiene le colonne richieste: "
            f"{sorted(missing_item_columns)}"
        )

    if "unit" not in items.columns:
        items["unit"] = pd.NA

    if "description_norm" not in mapping.columns:
        raise ValueError(f"{MAPPING_CSV} non contiene description_norm")

    if "reference_quantity" not in mapping.columns:
        mapping["reference_quantity"] = pd.NA

    if "reference_unit" not in mapping.columns:
        mapping["reference_unit"] = pd.NA

    if "normalized_automatically" not in mapping.columns:
        mapping["normalized_automatically"] = pd.NA

    mapping = mapping.dropna(how="all").copy()
    items = items.dropna(subset=["description_norm"]).copy()

    mapping_products = {
        description_norm: product_has_reference(group)
        for description_norm, group in mapping.dropna(subset=["description_norm"]).groupby("description_norm")
    }

    auto_unit_price: list[str] = []
    mapping_ok: list[str] = []
    mapping_incomplete: list[str] = []
    not_normalizable: list[str] = []
    unknown: list[str] = []


    for description_norm, group in items.groupby("description_norm"):
        units = (
            group["unit"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )

        has_unit_price = group["unit_price"].notna().any()
        has_real_unit = units.ne("").any()
        has_non_unit_unit = units.ne("").any() and units.ne("unit").any()

        if has_unit_price and has_non_unit_unit:
            auto_unit_price.append(description_norm)
            continue

        if description_norm in mapping_products:
            if mapping_products[description_norm]:
                mapping_ok.append(description_norm)
            else:
                mapping_incomplete.append(description_norm)

            continue

        if has_real_unit:
            not_normalizable.append(description_norm)
        else:
            unknown.append(description_norm)

    auto_products = set(auto_unit_price)

    mapping["normalized_automatically"] = mapping["description_norm"].apply(
        lambda value: "si" if value in auto_products else "no"
    )

    def print_section(title: str, values: list[str]) -> None:
        print()
        print(title)
        print("-" * len(title))

        if not values:
            print("  nessuno")
            return

        for value in sorted(values):
            examples = (
                items.loc[
                    items["description_norm"] == value,
                    "description_raw",
                ]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .head(3)
                .tolist()
            )

            print(f"  {value}")

            for example in examples:
                print(f"    es. {example}")

    print()
    print("REPORT NORMALIZZAZIONE PREZZI")
    print("=============================")
    print(f"Prodotti distinti: {items['description_norm'].nunique()}")
    print(f"Righe acquisto:    {len(items)}")

    print_section(
        "OK: sfusi normalizzabili automaticamente da unit_price",
        auto_unit_price,
    )

    print_section(
        "OK: confezionati normalizzabili tramite product_mapping.csv",
        mapping_ok,
    )

    print_section(
        "TODO: presenti nel mapping ma senza reference_quantity/reference_unit",
        mapping_incomplete,
    )

    print_section(
        "ATTENZIONE: non normalizzabili dagli scontrini",
        not_normalizable,
    )

    print_section(
        "ATTENZIONE: prodotti non presenti nel mapping",
        unknown,
    )

    print()
    print("Sintesi")
    print("-------")
    print(f"OK da unit_price:      {len(auto_unit_price)}")
    print(f"OK da mapping:         {len(mapping_ok)}")
    print(f"Mapping incompleto:    {len(mapping_incomplete)}")
    print(f"Non normalizzabili:    {len(not_normalizable)}")
    print(f"Non presenti mapping:  {len(unknown)}")

    mapping.to_csv(MAPPING_CSV, index=False)
    print(f"\nAggiornato: {MAPPING_CSV}")


if __name__ == "__main__":
    main()
