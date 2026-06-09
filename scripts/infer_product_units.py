#!/usr/bin/env python3

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ITEMS_CSV = PROJECT_ROOT / "exports" / "items_enriched.csv"


UNIT_CANDIDATE_RE = re.compile(
    r"""
    (?:
        (?P<qty_before>\d+(?:[,.]\d+)?)\s*
        (?P<unit_after>
            kg|kgs|chilogrammi|
            g|gr|grammi|
            l|lt|litri|
            ml
        )
    )
    |
    (?:
        (?P<unit_before>
            kg|kgs|chilogrammi|
            g|gr|grammi|
            l|lt|litri|
            ml
        )
        \.?\s*
        (?P<qty_after>\d+(?:[,.]\d+)?)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def clean_match_text(match: re.Match[str]) -> str:
    return match.group(0).strip()


def main() -> None:
    items = pd.read_csv(ITEMS_CSV)

    required_columns = {
        "description_norm",
        "description_raw",
    }

    missing_columns = required_columns - set(items.columns)
    if missing_columns:
        raise ValueError(
            f"{ITEMS_CSV} non contiene le colonne richieste: "
            f"{sorted(missing_columns)}"
        )

    candidates: list[tuple[str, str, str]] = []

    for row in items.itertuples(index=False):
        description_norm = str(row.description_norm)
        description_raw = str(row.description_raw)

        for match in UNIT_CANDIDATE_RE.finditer(description_raw):
            candidates.append(
                (
                    description_norm,
                    description_raw,
                    clean_match_text(match),
                )
            )

    unique_candidates = sorted(set(candidates))

    if not unique_candidates:
        print("Nessun candidato trovato.")
        return

    print("Candidati possibili per quantità/unità")
    print("=" * 80)

    current_description_norm: str | None = None

    for description_norm, description_raw, matched_text in unique_candidates:
        if description_norm != current_description_norm:
            current_description_norm = description_norm
            print()
            print(f"[{description_norm}]")

        print(f"  - match: {matched_text!r}")
        print(f"    raw:   {description_raw}")

    print()
    print(f"Totale candidati unici: {len(unique_candidates)}")


if __name__ == "__main__":
    main()
