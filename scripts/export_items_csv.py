#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARSED_DIR = PROJECT_ROOT / "parsed_receipts"
EXPORTS_DIR = PROJECT_ROOT / "exports"
OUTPUT_CSV = EXPORTS_DIR / "items.csv"


FIELDNAMES = [
    "receipt_id",
    "receipt_date",
    "receipt_time",
    "store_brand",
    "store_name",
    "store_address",
    "source_image_count",
    "primary_source_image",
    "line_index",
    "description_raw",
    "description_norm",
    "category",
    "quantity",
    "unit_price",
    "gross_amount",
    "discount_amount",
    "net_amount",
    "vat_rate",
    "parser_warning",
]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"{path}: JSON root is not an object")

    return data


def first_source_image_filename(receipt: dict[str, Any]) -> str:
    source_images = receipt.get("source_images") or []

    if not source_images:
        return ""

    first = source_images[0]

    if isinstance(first, dict):
        return str(first.get("filename") or "")

    return str(first)


def source_image_count(receipt: dict[str, Any]) -> int:
    source_images = receipt.get("source_images") or []

    if isinstance(source_images, list):
        return len(source_images)

    return 0


def flatten_receipt(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    receipt_id = receipt.get("receipt_id", "")

    datetime_data = receipt.get("datetime") or {}
    store = receipt.get("store") or {}

    items = receipt.get("items") or []
    rows: list[dict[str, Any]] = []

    for item in items:
        warnings = item.get("warnings") or []

        rows.append(
            {
                "receipt_id": receipt_id,
                "receipt_date": datetime_data.get("date", ""),
                "receipt_time": datetime_data.get("time", ""),
                "store_brand": store.get("brand", ""),
                "store_name": store.get("name", ""),
                "store_address": store.get("address", ""),
                "source_image_count": source_image_count(receipt),
                "primary_source_image": first_source_image_filename(receipt),
                "line_index": item.get("line_index", ""),
                "description_raw": item.get("description_raw", ""),
                "description_norm": item.get("description_norm", ""),
                "category": item.get("category", ""),
                "quantity": item.get("quantity", ""),
                "unit_price": item.get("unit_price", ""),
                "gross_amount": item.get("gross_amount", ""),
                "discount_amount": item.get("discount_amount", ""),
                "net_amount": item.get("net_amount", ""),
                "vat_rate": item.get("vat_rate", ""),
                "parser_warning": "; ".join(str(w) for w in warnings),
            }
        )

    return rows


def main() -> None:
    EXPORTS_DIR.mkdir(exist_ok=True)

    rows: list[dict[str, Any]] = []

    for path in sorted(PARSED_DIR.glob("*.parsed.json")):
        receipt = load_json(path)
        rows.extend(flatten_receipt(receipt))

    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Esportate {len(rows)} righe in {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
