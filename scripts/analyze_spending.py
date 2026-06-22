#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import re

import pandas as pd

try:
    import matplotlib

    matplotlib.use("Agg")

    import matplotlib.pyplot as plt
except ImportError as exc:
    raise SystemExit(
        "Manca matplotlib. Installalo nel progetto con: uv add matplotlib"
    ) from exc


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INPUT_CSV = PROJECT_ROOT / "exports" / "items_enriched.csv"
DEFAULT_ANALYSES_DIR = PROJECT_ROOT / "exports" / "analyses"


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
            "Analizza la spesa in un intervallo temporale e genera report CSV "
            "e grafici PNG."
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
            "per la competenza economica. Default: competence."
        ),
    )
    parser.add_argument(
        "--function",
        dest="function_name",
        help=(
            "Funzione di spesa di cui generare il grafico a torta, "
            "per esempio proteine_pronte."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_CSV,
        help=f"CSV arricchito da analizzare. Default: {DEFAULT_INPUT_CSV}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Directory di destinazione. Se omessa viene creata automaticamente "
            "sotto exports/analyses."
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


def load_items(input_csv: Path, date_basis: str) -> pd.DataFrame:
    if not input_csv.exists():
        raise FileNotFoundError(
            f"File non trovato: {input_csv}\n"
            "Esegui prima: uv run python -m scripts.enrich_items"
        )

    items = pd.read_csv(input_csv, dtype={"receipt_id": "string"})

    required_columns = {
        "net_amount",
        "description_norm",
        "category",
        "function",
    }

    missing_columns = required_columns - set(items.columns)
    if missing_columns:
        raise ValueError(
            f"{input_csv} non contiene le colonne richieste: "
            f"{sorted(missing_columns)}"
        )

    date_column = (
        "payment_date"
        if date_basis == "payment"
        else "competence_date"
    )

    if date_column not in items.columns:
        if "receipt_date" not in items.columns:
            raise ValueError(
                f"{input_csv} non contiene né {date_column} né receipt_date."
            )
        items[date_column] = items["receipt_date"]

    date_strings = items[date_column].astype("string").str.strip()
    parsed_dates = pd.to_datetime(
        date_strings,
        format="%Y-%m-%d",
        errors="coerce",
    )

    invalid_dates = items.loc[
        parsed_dates.isna() & date_strings.notna() & date_strings.ne(""),
        date_column,
    ]

    if not invalid_dates.empty:
        examples = sorted(invalid_dates.astype(str).unique())[:5]
        raise ValueError(
            f"Alcuni valori di {date_column} non sono date valide nel formato "
            f"YYYY-MM-DD: {examples}"
        )

    amount_strings = (
        items["net_amount"]
        .astype("string")
        .str.strip()
        .str.replace(",", ".", regex=False)
    )
    parsed_amounts = pd.to_numeric(amount_strings, errors="coerce")

    invalid_amounts = items.loc[
        parsed_amounts.isna() & items["net_amount"].notna(),
        "net_amount",
    ]

    if not invalid_amounts.empty:
        examples = sorted(invalid_amounts.astype(str).unique())[:5]
        raise ValueError(
            f"Alcuni valori di net_amount non sono numerici: {examples}"
        )

    items = items.copy()
    items["_analysis_date"] = parsed_dates
    items["net_amount"] = parsed_amounts

    items["description_norm"] = items["description_norm"].fillna(
        "non_classificato"
    )
    items["category"] = items["category"].fillna("non_classificato")
    items["function"] = items["function"].fillna("non_classificato")

    if "source_type" not in items.columns:
        items["source_type"] = "receipt"

    return items


def filter_items_by_period(
    items: pd.DataFrame,
    from_date: date | None,
    to_date: date | None,
) -> pd.DataFrame:
    mask = items["_analysis_date"].notna()

    if from_date is not None:
        mask &= items["_analysis_date"] >= pd.Timestamp(from_date)

    if to_date is not None:
        mask &= items["_analysis_date"] <= pd.Timestamp(to_date)

    return items.loc[mask].copy()


def effective_period(
    items: pd.DataFrame,
    from_date: date | None,
    to_date: date | None,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    if items.empty:
        raise ValueError("Non ci sono righe nel periodo richiesto.")

    start = (
        pd.Timestamp(from_date)
        if from_date is not None
        else items["_analysis_date"].min()
    )
    end = (
        pd.Timestamp(to_date)
        if to_date is not None
        else items["_analysis_date"].max()
    )

    if pd.isna(start) or pd.isna(end):
        raise ValueError("Non è stato possibile determinare il periodo di analisi.")

    return start.normalize(), end.normalize()


def period_label(
    from_date: date | None,
    to_date: date | None,
    date_basis: str,
) -> str:
    if from_date is None and to_date is None:
        period = "all"
    elif from_date is not None and to_date is not None:
        period = f"{from_date.isoformat()}_{to_date.isoformat()}"
    elif from_date is not None:
        period = f"from_{from_date.isoformat()}"
    else:
        assert to_date is not None
        period = f"to_{to_date.isoformat()}"

    return f"{date_basis}_{period}"


def safe_filename(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_-]+", "_", value.strip())
    normalized = normalized.strip("_")
    return normalized or "function"


def build_reports(
    items: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    full_date_range = pd.date_range(start=start, end=end, freq="D")

    daily_report = (
        items.groupby("_analysis_date")["net_amount"]
        .sum()
        .reindex(full_date_range, fill_value=0.0)
        .rename_axis("analysis_date")
        .reset_index()
    )
    daily_report["analysis_date"] = daily_report["analysis_date"].dt.date
    daily_report["net_amount"] = daily_report["net_amount"].round(2)

    function_report = (
        items.groupby("function", dropna=False)["net_amount"]
        .sum()
        .sort_values(ascending=False)
        .round(2)
        .rename("net_amount")
        .reset_index()
    )

    category_report = (
        items.groupby("category", dropna=False)["net_amount"]
        .sum()
        .sort_values(ascending=False)
        .round(2)
        .rename("net_amount")
        .reset_index()
    )

    source_report = (
        items.groupby("source_type", dropna=False)["net_amount"]
        .sum()
        .sort_values(ascending=False)
        .round(2)
        .rename("net_amount")
        .reset_index()
    )

    return daily_report, function_report, category_report, source_report


def save_daily_chart(
    daily_report: pd.DataFrame,
    output_path: Path,
) -> None:
    figure, axis = plt.subplots(figsize=(10, 5))

    axis.plot(
        pd.to_datetime(daily_report["analysis_date"]),
        daily_report["net_amount"],
        marker="o",
    )
    axis.set_title("Spesa giornaliera")
    axis.set_xlabel("Data")
    axis.set_ylabel("Euro")
    axis.grid(axis="y", alpha=0.3)
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def save_bar_chart(
    report: pd.DataFrame,
    label_column: str,
    title: str,
    output_path: Path,
) -> None:
    chart_data = report.sort_values("net_amount", ascending=True)

    figure_height = max(4.5, len(chart_data) * 0.35)
    figure, axis = plt.subplots(figsize=(10, figure_height))

    axis.barh(chart_data[label_column].astype(str), chart_data["net_amount"])
    axis.set_title(title)
    axis.set_xlabel("Euro")
    axis.set_ylabel("")
    axis.grid(axis="x", alpha=0.3)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def build_function_composition(
    items: pd.DataFrame,
    function_name: str,
) -> pd.DataFrame:
    function_items = items.loc[items["function"].eq(function_name)].copy()

    if function_items.empty:
        available_functions = sorted(items["function"].astype(str).unique())
        raise ValueError(
            f"Nessuna riga trovata per function={function_name!r}. "
            f"Funzioni disponibili: {available_functions}"
        )

    return (
        function_items.groupby("description_norm", dropna=False)["net_amount"]
        .sum()
        .sort_values(ascending=False)
        .round(2)
        .rename("net_amount")
        .reset_index()
    )


def save_pie_chart(
    composition: pd.DataFrame,
    function_name: str,
    output_path: Path,
) -> None:
    positive_composition = composition.loc[
        composition["net_amount"] > 0
    ].copy()

    if positive_composition.empty:
        raise ValueError(
            f"La funzione {function_name!r} non contiene importi positivi "
            "rappresentabili in un grafico a torta."
        )

    figure, axis = plt.subplots(figsize=(9, 7))

    axis.pie(
        positive_composition["net_amount"],
        labels=positive_composition["description_norm"].astype(str),
        autopct="%1.1f%%",
        startangle=90,
    )
    axis.set_title(f"Composizione della spesa: {function_name}")
    axis.axis("equal")
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def write_summary(
    output_path: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
    date_basis: str,
    item_count: int,
    receipt_count: int | None,
    total: float,
    day_count: int,
    daily_average: float,
    projected_30_days: float,
) -> None:
    lines = [
        f"Periodo: {start.date().isoformat()} -> {end.date().isoformat()}",
        f"Base temporale: {date_basis}",
        f"Giorni di calendario: {day_count}",
    ]

    if receipt_count is not None:
        lines.append(f"Transazioni/documenti: {receipt_count}")

    lines.extend(
        [
            f"Righe: {item_count}",
            f"Totale speso: {total:.2f} EUR",
            f"Media giornaliera: {daily_average:.2f} EUR",
            f"Proiezione su 30 giorni: {projected_30_days:.2f} EUR",
        ]
    )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()

    items = load_items(args.input, date_basis=args.date_basis)
    items = filter_items_by_period(
        items,
        from_date=args.from_date,
        to_date=args.to_date,
    )

    if items.empty:
        print("Nessuna riga trovata nel periodo richiesto.")
        return

    start, end = effective_period(
        items,
        from_date=args.from_date,
        to_date=args.to_date,
    )

    output_dir = (
        args.output_dir
        if args.output_dir is not None
        else DEFAULT_ANALYSES_DIR / period_label(
            args.from_date,
            args.to_date,
            args.date_basis,
        )
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    (
        daily_report,
        function_report,
        category_report,
        source_report,
    ) = build_reports(
        items,
        start=start,
        end=end,
    )

    daily_report.to_csv(
        output_dir / "spesa_giornaliera.csv",
        index=False,
    )
    function_report.to_csv(
        output_dir / "spesa_per_funzione.csv",
        index=False,
    )
    category_report.to_csv(
        output_dir / "spesa_per_categoria.csv",
        index=False,
    )
    source_report.to_csv(
        output_dir / "spesa_per_tipo_fonte.csv",
        index=False,
    )

    save_daily_chart(
        daily_report,
        output_dir / "spesa_giornaliera.png",
    )
    save_bar_chart(
        function_report,
        label_column="function",
        title="Spesa per funzione",
        output_path=output_dir / "spesa_per_funzione.png",
    )
    save_bar_chart(
        category_report,
        label_column="category",
        title="Spesa per categoria",
        output_path=output_dir / "spesa_per_categoria.png",
    )

    if args.function_name is not None:
        composition = build_function_composition(
            items,
            function_name=args.function_name,
        )
        function_slug = safe_filename(args.function_name)

        composition.to_csv(
            output_dir / f"{function_slug}.csv",
            index=False,
        )
        save_pie_chart(
            composition,
            function_name=args.function_name,
            output_path=output_dir / f"{function_slug}_torta.png",
        )

    total = float(items["net_amount"].sum())
    day_count = len(pd.date_range(start=start, end=end, freq="D"))
    daily_average = total / day_count
    projected_30_days = daily_average * 30

    receipt_count = (
        int(items["receipt_id"].nunique())
        if "receipt_id" in items.columns
        else None
    )

    summary_path = output_dir / "summary.txt"
    write_summary(
        output_path=summary_path,
        start=start,
        end=end,
        date_basis=args.date_basis,
        item_count=len(items),
        receipt_count=receipt_count,
        total=total,
        day_count=day_count,
        daily_average=daily_average,
        projected_30_days=projected_30_days,
    )

    print(f"Periodo: {start.date().isoformat()} -> {end.date().isoformat()}")
    print(f"Base temporale: {args.date_basis}")
    print(f"Giorni di calendario: {day_count}")

    if receipt_count is not None:
        print(f"Transazioni/documenti: {receipt_count}")

    print(f"Totale speso: {total:.2f} EUR")
    print(f"Media giornaliera: {daily_average:.2f} EUR")
    print(f"Proiezione su 30 giorni: {projected_30_days:.2f} EUR")
    print(f"Report e grafici salvati in: {output_dir}")


if __name__ == "__main__":
    main()
