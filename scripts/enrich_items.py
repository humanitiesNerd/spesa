#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ITEMS_CSV = PROJECT_ROOT / "exports" / "items.csv"
MAPPING_CSV = PROJECT_ROOT / "data" / "product_mapping.csv"
OUTPUT_CSV = PROJECT_ROOT / "exports" / "items_enriched.csv"
QUANTITY_OVERRIDES_CSV = PROJECT_ROOT / "data" / "item_quantity_overrides.csv"
MANUAL_ITEMS_CSV = PROJECT_ROOT / "data" / "manual_items.csv"

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

MANUAL_REQUIRED_COLUMNS = {
    "receipt_id",
    "line_index",
    "payment_date",
    "competence_date",
    "description_raw",
    "description_norm",
    "category",
    "function",
    "net_amount",
    "source_type",
    "replaces_receipt_id",
    "expected_transaction_total",
    "status",
}

NUMERIC_MANUAL_COLUMNS = [
    "quantity",
    "unit_price",
    "gross_amount",
    "discount_amount",
    "net_amount",
    "expected_transaction_total",
]


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Data non valida: {value!r}. Usa il formato YYYY-MM-DD."
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Arricchisce le righe degli scontrini e le eventuali righe manuali, "
            "eventualmente limitandole a un intervallo temporale."
        )
    )
    parser.add_argument(
        "--from-date",
        type=parse_iso_date,
        help="Data iniziale inclusiva, nel formato YYYY-MM-DD.",
    )
    parser.add_argument(
        "--to-date",
        type=parse_iso_date,
        help="Data finale inclusiva, nel formato YYYY-MM-DD.",
    )
    parser.add_argument(
        "--date-basis",
        choices=["payment", "competence"],
        default="competence",
        help=(
            "Usa payment_date per il flusso di cassa oppure competence_date "
            "per attribuire la spesa al periodo corretto. Default: competence."
        ),
    )

    args = parser.parse_args()

    if (
        args.from_date is not None
        and args.to_date is not None
        and args.from_date > args.to_date
    ):
        parser.error("--from-date non può essere successiva a --to-date.")

    return args


def parse_date_column(
    frame: pd.DataFrame,
    column_name: str,
    source_path: Path,
) -> pd.Series:
    if column_name not in frame.columns:
        raise ValueError(
            f"{source_path} non contiene la colonna richiesta: {column_name}"
        )

    values = frame[column_name].astype("string").str.strip()
    parsed = pd.to_datetime(values, format="%Y-%m-%d", errors="coerce")

    invalid = frame.loc[
        parsed.isna() & values.notna() & values.ne(""),
        column_name,
    ]

    if not invalid.empty:
        examples = sorted(invalid.astype(str).unique())[:5]
        raise ValueError(
            f"Alcuni valori di {column_name} in {source_path} non sono date "
            f"valide nel formato YYYY-MM-DD: {examples}"
        )

    return parsed


def normalize_automatic_items(items: pd.DataFrame) -> pd.DataFrame:
    if "receipt_date" not in items.columns:
        raise ValueError(
            f"{ITEMS_CSV} non contiene la colonna richiesta: receipt_date"
        )

    normalized = items.copy()

    if "payment_date" not in normalized.columns:
        normalized["payment_date"] = normalized["receipt_date"]

    if "competence_date" not in normalized.columns:
        normalized["competence_date"] = normalized["receipt_date"]

    if "source_type" not in normalized.columns:
        normalized["source_type"] = "receipt"

    if "supporting_document" not in normalized.columns:
        normalized["supporting_document"] = pd.NA

    if "replaces_receipt_id" not in normalized.columns:
        normalized["replaces_receipt_id"] = pd.NA

    if "expected_transaction_total" not in normalized.columns:
        normalized["expected_transaction_total"] = pd.NA

    if "note" not in normalized.columns:
        normalized["note"] = pd.NA

    return normalized


def parse_manual_numeric_columns(items: pd.DataFrame) -> pd.DataFrame:
    parsed = items.copy()

    for column in NUMERIC_MANUAL_COLUMNS:
        if column not in parsed.columns:
            parsed[column] = pd.NA

        strings = (
            parsed[column]
            .astype("string")
            .str.strip()
            .str.replace(",", ".", regex=False)
        )
        numbers = pd.to_numeric(strings, errors="coerce")

        invalid = parsed.loc[
            numbers.isna() & strings.notna() & strings.ne(""),
            column,
        ]

        if not invalid.empty:
            examples = sorted(invalid.astype(str).unique())[:5]
            raise ValueError(
                f"Alcuni valori di {column} in {MANUAL_ITEMS_CSV} non sono "
                f"numerici: {examples}"
            )

        parsed[column] = numbers

    return parsed


def validate_manual_transactions(items: pd.DataFrame) -> None:
    duplicated = items.duplicated(
        subset=["receipt_id", "line_index"],
        keep=False,
    )

    if duplicated.any():
        duplicates = (
            items.loc[duplicated, ["receipt_id", "line_index"]]
            .drop_duplicates()
            .to_dict("records")
        )
        raise ValueError(
            "Chiavi duplicate in manual_items.csv: "
            f"{duplicates}"
        )

    for receipt_id, group in items.groupby("receipt_id", dropna=False):
        expected_values = (
            group["expected_transaction_total"]
            .dropna()
            .round(2)
            .unique()
        )

        if len(expected_values) == 0:
            continue

        if len(expected_values) > 1:
            raise ValueError(
                f"Più expected_transaction_total diversi per {receipt_id}: "
                f"{sorted(expected_values.tolist())}"
            )

        expected = float(expected_values[0])
        actual = round(float(group["net_amount"].sum()), 2)

        if abs(actual - expected) >= 0.01:
            raise ValueError(
                f"Totale manuale non riconciliato per {receipt_id}: "
                f"righe={actual:.2f} EUR, atteso={expected:.2f} EUR"
            )


def load_manual_items() -> pd.DataFrame:
    if not MANUAL_ITEMS_CSV.exists():
        return pd.DataFrame()

    manual = pd.read_csv(
        MANUAL_ITEMS_CSV,
        dtype={
            "receipt_id": "string",
            "replaces_receipt_id": "string",
        },
    )

    missing = MANUAL_REQUIRED_COLUMNS - set(manual.columns)
    if missing:
        raise ValueError(
            f"Mancano colonne in {MANUAL_ITEMS_CSV}: {sorted(missing)}"
        )

    manual = manual[
        manual["status"].astype("string").str.strip().eq("ok")
    ].copy()

    if manual.empty:
        return manual

    manual["payment_date"] = parse_date_column(
        manual,
        "payment_date",
        MANUAL_ITEMS_CSV,
    ).dt.strftime("%Y-%m-%d")

    manual["competence_date"] = parse_date_column(
        manual,
        "competence_date",
        MANUAL_ITEMS_CSV,
    ).dt.strftime("%Y-%m-%d")

    manual = parse_manual_numeric_columns(manual)

    line_indexes = pd.to_numeric(manual["line_index"], errors="coerce")
    invalid_indexes = manual.loc[line_indexes.isna(), "line_index"]

    if not invalid_indexes.empty:
        examples = sorted(invalid_indexes.astype(str).unique())[:5]
        raise ValueError(
            f"Alcuni line_index in {MANUAL_ITEMS_CSV} non sono interi: "
            f"{examples}"
        )

    manual["line_index"] = line_indexes.astype(int)
    manual["receipt_date"] = manual["competence_date"]

    validate_manual_transactions(manual)

    return manual


def merge_manual_items(
    automatic_items: pd.DataFrame,
    manual_items: pd.DataFrame,
) -> pd.DataFrame:
    if manual_items.empty:
        return automatic_items.copy()

    replacement_ids = set(
        manual_items["replaces_receipt_id"]
        .dropna()
        .astype(str)
        .str.strip()
    )
    replacement_ids.discard("")

    merged_automatic = automatic_items.copy()

    if replacement_ids:
        before = len(merged_automatic)
        merged_automatic = merged_automatic[
            ~merged_automatic["receipt_id"].astype(str).isin(replacement_ids)
        ].copy()
        removed = before - len(merged_automatic)
        print(
            "Righe automatiche sostituite da ricostruzioni manuali: "
            f"{removed}"
        )

    combined = pd.concat(
        [merged_automatic, manual_items],
        ignore_index=True,
        sort=False,
    )

    duplicated = combined.duplicated(
        subset=["receipt_id", "line_index"],
        keep=False,
    )

    if duplicated.any():
        duplicates = (
            combined.loc[duplicated, ["receipt_id", "line_index", "source_type"]]
            .sort_values(["receipt_id", "line_index"])
            .to_dict("records")
        )
        raise ValueError(
            "Chiavi receipt_id + line_index duplicate dopo l'unione: "
            f"{duplicates}"
        )

    return combined


def filter_items_by_period(
    items: pd.DataFrame,
    from_date: date | None,
    to_date: date | None,
    date_basis: str,
) -> pd.DataFrame:
    if from_date is None and to_date is None:
        return items.copy()

    column_name = (
        "payment_date"
        if date_basis == "payment"
        else "competence_date"
    )

    parsed_dates = parse_date_column(
        items,
        column_name,
        ITEMS_CSV,
    )

    mask = parsed_dates.notna()

    if from_date is not None:
        mask &= parsed_dates >= pd.Timestamp(from_date)

    if to_date is not None:
        mask &= parsed_dates <= pd.Timestamp(to_date)

    return items.loc[mask].copy()


def output_path_for_period(
    from_date: date | None,
    to_date: date | None,
    date_basis: str,
) -> Path:
    if from_date is None and to_date is None:
        return OUTPUT_CSV

    if from_date is not None and to_date is not None:
        period_suffix = f"{from_date.isoformat()}_{to_date.isoformat()}"
    elif from_date is not None:
        period_suffix = f"from_{from_date.isoformat()}"
    else:
        assert to_date is not None
        period_suffix = f"to_{to_date.isoformat()}"

    return OUTPUT_CSV.with_name(
        f"{OUTPUT_CSV.stem}_{date_basis}_{period_suffix}{OUTPUT_CSV.suffix}"
    )


def format_period(
    from_date: date | None,
    to_date: date | None,
) -> str:
    if from_date is None and to_date is None:
        return "tutte le righe"

    if from_date is not None and to_date is not None:
        return f"dal {from_date.isoformat()} al {to_date.isoformat()} inclusi"

    if from_date is not None:
        return f"dal {from_date.isoformat()} in poi"

    assert to_date is not None
    return f"fino al {to_date.isoformat()} incluso"


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

    enriched["function"] = enriched["mapped_function"].combine_first(
        enriched["function"]
    )

    if "mapped_reference_quantity" in enriched.columns:
        if "reference_quantity" in enriched.columns:
            enriched["reference_quantity"] = enriched[
                "mapped_reference_quantity"
            ].combine_first(enriched["reference_quantity"])
        else:
            enriched["reference_quantity"] = enriched[
                "mapped_reference_quantity"
            ]

    if "mapped_reference_unit" in enriched.columns:
        if "reference_unit" in enriched.columns:
            enriched["reference_unit"] = enriched[
                "mapped_reference_unit"
            ].combine_first(enriched["reference_unit"])
        else:
            enriched["reference_unit"] = enriched[
                "mapped_reference_unit"
            ]

    if "mapped_normalized_automatically" in enriched.columns:
        if "normalized_automatically" in enriched.columns:
            enriched["normalized_automatically"] = enriched[
                "mapped_normalized_automatically"
            ].combine_first(enriched["normalized_automatically"])
        else:
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

    return enriched.drop(columns=columns_to_drop)


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

    print(f"Applicati override quantità: {int(has_override.sum())}")

    return merged


def build_missing_mapping_rows(
    items: pd.DataFrame,
    mapping: pd.DataFrame,
) -> pd.DataFrame:
    existing_patterns = set(mapping["pattern"].dropna().astype(str))

    semantic_columns = ["description_norm", "category", "function"]
    incomplete_semantics = items[semantic_columns].apply(
        lambda column: column.isna() | column.astype("string").str.strip().eq("")
    ).any(axis=1)

    missing_items = items[
        incomplete_semantics
        & ~items["description_raw"].astype(str).isin(existing_patterns)
    ].copy()

    if missing_items.empty:
        return pd.DataFrame(columns=mapping.columns)

    missing_items = missing_items.drop_duplicates(subset=["description_raw"])

    rows: list[dict[str, object]] = []

    for _, item in missing_items.iterrows():
        row: dict[str, object] = {
            column: pd.NA
            for column in mapping.columns
        }

        row["pattern"] = item["description_raw"]
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


def print_manual_summary(enriched: pd.DataFrame) -> None:
    if "source_type" not in enriched.columns:
        return

    manual = enriched[
        enriched["source_type"].astype("string").ne("receipt")
    ].copy()

    if manual.empty:
        return

    print()
    print("Righe non provenienti direttamente da scontrini")
    print("-----------------------------------------------")

    summary = (
        manual.groupby(["receipt_id", "source_type"], dropna=False)["net_amount"]
        .sum()
        .round(2)
        .reset_index()
    )
    print(summary.to_string(index=False))


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
    args = parse_args()

    automatic_items = pd.read_csv(
        ITEMS_CSV,
        dtype={"receipt_id": "string"},
    )
    automatic_items = normalize_automatic_items(automatic_items)

    manual_items = load_manual_items()
    all_items = merge_manual_items(automatic_items, manual_items)

    items = filter_items_by_period(
        all_items,
        from_date=args.from_date,
        to_date=args.to_date,
        date_basis=args.date_basis,
    )

    if items.empty:
        print(
            "Nessuna riga trovata nel periodo richiesto: "
            f"{format_period(args.from_date, args.to_date)} "
            f"(base data: {args.date_basis})."
        )
        return

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

    output_csv = output_path_for_period(
        from_date=args.from_date,
        to_date=args.to_date,
        date_basis=args.date_basis,
    )

    output_csv.parent.mkdir(exist_ok=True)
    enriched.to_csv(output_csv, index=False)

    mapped_count = (
        enriched["description_raw"] != enriched["category"]
    ).sum()

    total_count = len(enriched)
    receipt_count = (
        enriched["receipt_id"].nunique()
        if "receipt_id" in enriched.columns
        else None
    )

    print(f"Periodo: {format_period(args.from_date, args.to_date)}")
    print(f"Base temporale: {args.date_basis}")

    if receipt_count is not None:
        print(f"Transazioni/documenti inclusi: {receipt_count}")

    print(f"Righe incluse: {total_count}")
    print(f"Totale righe: {enriched['net_amount'].sum():.2f} EUR")
    print(f"Salvato: {output_csv}")
    print(f"Righe aggregate tramite mapping: {mapped_count}/{total_count}")

    print_manual_summary(enriched)
    print_reports(enriched)


if __name__ == "__main__":
    main()
