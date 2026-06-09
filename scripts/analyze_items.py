#!/usr/bin/env python3

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ITEMS_CSV = PROJECT_ROOT / "exports" / "items.csv"


def euro_series(series: pd.Series) -> pd.Series:
    return series.round(2)


def main() -> None:
    df = pd.read_csv(ITEMS_CSV)




    print()
    print("Spesa per prodotto")
    print("------------------")
    print(
        euro_series(
            df.groupby("description_raw")["net_amount"]
            .sum()
            .sort_values(ascending=False)
        ).head(20)
    )

    print()
    print("Spesa per supermercato")
    print("----------------------")
    print(
        euro_series(
            df.groupby("store_brand")["net_amount"]
            .sum()
            .sort_values(ascending=False)
        )
    )

    print()
    print("Singoli articoli più costosi")
    print("----------------------------")
    print(
        df[
            [
                "receipt_date",
                "store_brand",
                "description_raw",
                "quantity",
                "unit_price",
                "net_amount",
            ]
        ]
        .sort_values("net_amount", ascending=False)
        .head(20)
        .to_string(index=False)
    )

    print()
    print("Righe con categoria mancante")
    print("----------------------------")
    print(df["category"].isna().sum())


if __name__ == "__main__":
    main()
