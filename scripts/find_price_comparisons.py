#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ITEMS_CSV = PROJECT_ROOT / "exports" / "items_enriched.csv"
MAPPING_CSV = PROJECT_ROOT / "data" / "product_mapping.csv"


def main() -> None:
    items = pd.read_csv(ITEMS_CSV)
    mapping = pd.read_csv(MAPPING_CSV)

    required_item_columns = {
        "description_norm",
        "description_raw",
        "store_brand",
        "quantity",
        "net_amount",
    }

    required_mapping_columns = {
        "pattern",
        "description_norm",
        "reference_quantity",
        "reference_unit",
    }

    missing_items = required_item_columns - set(items.columns)
    if missing_items:
        raise ValueError(f"Mancano colonne in {ITEMS_CSV}: {sorted(missing_items)}")

    missing_mapping = required_mapping_columns - set(mapping.columns)
    if missing_mapping:
        raise ValueError(f"Mancano colonne in {MAPPING_CSV}: {sorted(missing_mapping)}")

    mapping = mapping[
        [
            "pattern",
            "description_norm",
            "reference_quantity",
            "reference_unit",
        ]
    ].copy()

    df = items.merge(
        mapping,
        left_on=["description_raw", "description_norm"],
        right_on=["pattern", "description_norm"],
        how="left",
    )

    df = df.dropna(subset=["description_norm", "store_brand"]).copy()

    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(1)
    df.loc[df["quantity"] == 0, "quantity"] = 1

    df["net_amount"] = pd.to_numeric(df["net_amount"], errors="coerce")
    df["reference_quantity"] = pd.to_numeric(
        df["reference_quantity"],
        errors="coerce",
    )
    df["reference_unit"] = (
        df["reference_unit"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    df = df.dropna(subset=["net_amount", "reference_quantity"]).copy()
    df = df[df["reference_quantity"] > 0].copy()

    df["total_reference_quantity"] = df["reference_quantity"] * df["quantity"]

    df["comparison_price"] = pd.NA
    df["comparison_unit"] = pd.NA

    grams = df["reference_unit"] == "g"
    milliliters = df["reference_unit"] == "ml"

    df.loc[grams, "comparison_price"] = (
        df.loc[grams, "net_amount"]
        / df.loc[grams, "total_reference_quantity"]
        * 1000
    )
    df.loc[grams, "comparison_unit"] = "€/kg"

    df.loc[milliliters, "comparison_price"] = (
        df.loc[milliliters, "net_amount"]
        / df.loc[milliliters, "total_reference_quantity"]
        * 1000
    )
    df.loc[milliliters, "comparison_unit"] = "€/L"

    df["comparison_price"] = pd.to_numeric(df["comparison_price"], errors="coerce")
    df = df.dropna(subset=["comparison_price", "comparison_unit"]).copy()

    rows: list[dict[str, object]] = []

    for product, group in df.groupby("description_norm"):
        stores = group["store_brand"].dropna().unique()

        if len(stores) < 2:
            continue

        units = group["comparison_unit"].dropna().unique()
        if len(units) != 1:
            continue

        by_store = (
            group.groupby("store_brand")
            .agg(
                n=("comparison_price", "size"),
                min_price=("comparison_price", "min"),
                avg_price=("comparison_price", "mean"),
                max_price=("comparison_price", "max"),
                examples=(
                    "description_raw",
                    lambda s: " | ".join(sorted(set(map(str, s)))[:3]),
                ),
            )
            .reset_index()
            .sort_values("avg_price")
        )

        if len(by_store) < 2:
            continue

        cheapest = by_store.iloc[0]
        most_expensive = by_store.iloc[-1]

        cheapest_avg = float(cheapest["avg_price"])
        expensive_avg = float(most_expensive["avg_price"])

        rows.append(
            {
                "description_norm": product,
                "comparison_unit": units[0],
                "stores": len(by_store),
                "cheapest_store": cheapest["store_brand"],
                "cheapest_avg": cheapest_avg,
                "expensive_store": most_expensive["store_brand"],
                "expensive_avg": expensive_avg,
                "difference_abs": expensive_avg - cheapest_avg,
                "difference_pct": (
                    (expensive_avg / cheapest_avg - 1) * 100
                    if cheapest_avg > 0
                    else pd.NA
                ),
                "total_rows": len(group),
            }
        )

    summary = pd.DataFrame(rows)

    print()
    print("CONFRONTI PREZZO PRATICABILI")
    print("============================")

    if summary.empty:
        print("Nessun confronto praticabile trovato.")
        return

    summary = summary.sort_values(
        ["difference_pct", "difference_abs"],
        ascending=False,
    )

    for _, row in summary.iterrows():
        unit = row["comparison_unit"]

        print()
        print(f"{row['description_norm']}")
        print(f"  righe acquisto: {row['total_rows']}")
        print(f"  supermercati:   {row['stores']}")
        print(
            f"  più economico:  {row['cheapest_store']} "
            f"({row['cheapest_avg']:.2f} {unit})"
        )
        print(
            f"  più caro:       {row['expensive_store']} "
            f"({row['expensive_avg']:.2f} {unit})"
        )
        print(
            f"  differenza:     +{row['difference_abs']:.2f} {unit} "
            f"({row['difference_pct']:.1f}%)"
        )


if __name__ == "__main__":
    main()
