#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ITEMS_ENRICHED_CSV = PROJECT_ROOT / "exports" / "items_enriched.csv"
OUTPUT_CSV = PROJECT_ROOT / "data" / "item_quantity_overrides.csv"


OUTPUT_COLUMNS = [
    "receipt_id",
    "line_index",
    "store_brand",
    "description_raw",
    "description_norm",
    "net_amount",
    "suggested_reference_quantity",
    "suggested_reference_unit",
    "reference_quantity",
    "reference_unit",
    "note",
    "status",
]


def has_value(value: object) -> bool:
    return pd.notna(value) and str(value).strip() != ""


def suggest_quantity(row: pd.Series) -> tuple[object, object, str]:
    store_brand = str(row.get("store_brand", "")).strip()
    description_raw = str(row.get("description_raw", "")).strip()
    description_norm = str(row.get("description_norm", "")).strip()
    net_amount = float(row.get("net_amount", 0) or 0)

    if (
        store_brand == "LIDL"
        and description_raw == "MOZZARELLA LIGHT"
        and description_norm == "mozzarella_light"
    ):
        if abs(net_amount - 1.99) < 0.01:
            return 375, "g", "probabile multipack 3x125 g Lidl, prezzo netto scontato"
        if abs(net_amount - 0.99) < 0.01:
            return 125, "g", "probabile mozzarella singola 125 g Lidl"

        return "", "g", "mozzarella Lidl ambigua: quantità da verificare"

    return "", "", ""


def main() -> None:
    if not ITEMS_ENRICHED_CSV.exists():
        raise FileNotFoundError(f"File non trovato: {ITEMS_ENRICHED_CSV}")

    items = pd.read_csv(ITEMS_ENRICHED_CSV)

    required_columns = {
        "receipt_id",
        "line_index",
        "store_brand",
        "description_raw",
        "description_norm",
        "net_amount",
    }

    missing = required_columns - set(items.columns)
    if missing:
        raise ValueError(
            f"Mancano colonne in {ITEMS_ENRICHED_CSV}: {sorted(missing)}"
        )

    rows: list[dict[str, object]] = []

    for _, row in items.iterrows():
        description_norm = row.get("description_norm")

        if not has_value(description_norm):
            continue

        suggested_quantity, suggested_unit, note = suggest_quantity(row)

        has_suggestion = has_value(suggested_quantity) or has_value(note)

        if not has_suggestion:
            continue

        rows.append(
            {
                "receipt_id": row["receipt_id"],
                "line_index": row["line_index"],
                "store_brand": row["store_brand"],
                "description_raw": row["description_raw"],
                "description_norm": row["description_norm"],
                "net_amount": row["net_amount"],
                "suggested_reference_quantity": suggested_quantity,
                "suggested_reference_unit": suggested_unit,
                "reference_quantity": "",
                "reference_unit": "",
                "note": note,
                "status": "da_verificare",
            }
        )

    output = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)

    if OUTPUT_CSV.exists():
        existing = pd.read_csv(OUTPUT_CSV)

        key_columns = ["receipt_id", "line_index"]

        merged = existing.merge(
            output[key_columns],
            on=key_columns,
            how="outer",
            indicator=True,
        )

        existing_keys = set(
            tuple(row)
            for row in existing[key_columns].itertuples(index=False, name=None)
        )

        new_rows = output[
            ~output[key_columns].apply(tuple, axis=1).isin(existing_keys)
        ]

        if len(new_rows) == 0:
            print(f"Nessuna nuova annotazione da aggiungere a {OUTPUT_CSV}")
            return

        combined = pd.concat([existing, new_rows], ignore_index=True)
        combined.to_csv(OUTPUT_CSV, index=False)

        print(f"Aggiunte {len(new_rows)} nuove annotazioni a {OUTPUT_CSV}")
        return

    output.to_csv(OUTPUT_CSV, index=False)
    print(f"Creato {OUTPUT_CSV} con {len(output)} annotazioni")


if __name__ == "__main__":
    main()
