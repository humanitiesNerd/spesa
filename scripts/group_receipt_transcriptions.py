#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

TRANSCRIPTIONS_DIR = PROJECT_ROOT / "trascrizioni"
GROUPED_DIR = PROJECT_ROOT / "trascrizioni_raggruppate"

THRESHOLD_SECONDS = 40

TIMESTAMP_RE = re.compile(
    r"(?P<date>\d{8})[_-]?(?P<time>\d{6})"
)

BREAKS_FILE = PROJECT_ROOT / "data" / "receipt_group_breaks.txt"

def timestamp_from_filename(path: Path) -> datetime:
    match = TIMESTAMP_RE.search(path.name)

    if not match:
        raise ValueError(f"Nome file senza timestamp riconoscibile: {path}")

    value = f"{match.group('date')} {match.group('time')}"
    return datetime.strptime(value, "%Y%m%d %H%M%S")


def load_raw_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError(f"{path}: JSON root non è un oggetto")

    if "raw_lines" not in data:
        raise ValueError(f"{path}: manca raw_lines")

    if not isinstance(data["raw_lines"], list):
        raise ValueError(f"{path}: raw_lines non è una lista")

    return data


def load_group_breaks() -> set[str]:
    if not BREAKS_FILE.exists():
        return set()

    breaks: set[str] = set()

    for raw_line in BREAKS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        breaks.add(line)

    return breaks




def group_transcriptions(paths: list[Path], breaks: set[str]) -> list[list[Path]]:
    if not paths:
        return []

    sorted_paths = sorted(paths, key=timestamp_from_filename)

    groups: list[list[Path]] = []
    current_group: list[Path] = [sorted_paths[0]]

    for path in sorted_paths[1:]:
        previous_path = current_group[-1]

        previous_ts = timestamp_from_filename(previous_path)
        current_ts = timestamp_from_filename(path)

        delta_seconds = (current_ts - previous_ts).total_seconds()

        must_break = path.name in breaks

        if delta_seconds <= THRESHOLD_SECONDS and not must_break:
            current_group.append(path)
        else:
            groups.append(current_group)
            current_group = [path]
            
    groups.append(current_group)

    return groups


def source_entry(path: Path) -> dict:
    return {
        "filename": path.name,
        "timestamp": timestamp_from_filename(path).isoformat(timespec="seconds"),
    }


def output_path_for_group(group: list[Path]) -> Path:
    first = group[0]
    stem = first.stem

    return GROUPED_DIR / f"{stem}.receipt.raw.json"


def merge_group(group: list[Path]) -> dict:
    merged_raw_lines: list[str] = []

    for index, path in enumerate(group):
        data = load_raw_json(path)

        if index > 0:
            merged_raw_lines.append("")

        merged_raw_lines.extend(str(line) for line in data["raw_lines"])

    return {
        "source_images": [
            source_entry(path)
            for path in group
        ],
        "raw_lines": merged_raw_lines,
    }


def print_group(group_index: int, group: list[Path]) -> None:
    output_path = output_path_for_group(group)

    print()
    print(f"Gruppo {group_index}")
    print("-" * 40)

    if len(group) == 1:
        print("Tipo: singolo file")
    else:
        print(f"Tipo: scontrino multi-foto ({len(group)} file)")

    print(f"Output: {output_path}")

    previous_ts: datetime | None = None

    for path in group:
        ts = timestamp_from_filename(path)

        if previous_ts is None:
            delta = "-"
        else:
            delta = f"{int((ts - previous_ts).total_seconds())}s"

        print(f"  - {path.name}  timestamp={ts.isoformat(timespec='seconds')}  delta={delta}")

        previous_ts = ts


def main() -> None:
    if not TRANSCRIPTIONS_DIR.exists():
        raise FileNotFoundError(f"Cartella non trovata: {TRANSCRIPTIONS_DIR}")

    paths = sorted(TRANSCRIPTIONS_DIR.glob("*.json"))

    breaks = load_group_breaks()
    groups = group_transcriptions(paths, breaks)

    GROUPED_DIR.mkdir(exist_ok=True)

    print(f"Input:  {TRANSCRIPTIONS_DIR}")
    print(f"Output: {GROUPED_DIR}")
    print(f"Soglia raggruppamento: {THRESHOLD_SECONDS}s")
    print(f"Trascrizioni trovate: {len(paths)}")
    print(f"Gruppi prodotti: {len(groups)}")

    print(f"Break manuali caricati: {len(breaks)}")
    if breaks:
        print("Break manuali:")
        for filename in sorted(breaks):
            print(f"  - {filename}")

    for index, group in enumerate(groups, start=1):
        print_group(index, group)

        merged = merge_group(group)
        output_path = output_path_for_group(group)

        output_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print()
    print("Fatto.")


if __name__ == "__main__":
    main()
