import argparse
import os
from typing import List, Optional

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="View and filter extracted capture data using pandas.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--csv",
        default="captures.csv",
        help="Path to the CSV file produced by the extractor GUI.",
    )
    parser.add_argument(
        "--head",
        type=int,
        default=20,
        help="Number of rows to show from the filtered result.",
    )
    parser.add_argument(
        "--columns",
        type=str,
        default="",
        help="Comma-separated list of columns to display (e.g., 'user_name,summary').",
    )
    parser.add_argument(
        "--where",
        type=str,
        default="",
        help="Pandas query expression to filter rows (e.g., 'follower_count.astype(int) > 1000').",
    )
    parser.add_argument(
        "--sort",
        type=str,
        default="",
        help="Column name to sort by.",
    )
    parser.add_argument(
        "--desc",
        action="store_true",
        help="Sort in descending order if set.",
    )
    parser.add_argument(
        "--export-csv",
        type=str,
        default="",
        help="Optional path to export the filtered result as CSV.",
    )
    parser.add_argument(
        "--export-excel",
        type=str,
        default="",
        help="Optional path to export the filtered result as Excel (.xlsx).",
    )
    return parser.parse_args()


def load_dataframe(csv_path: str) -> pd.DataFrame:
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    # Keep strings as-is; many fields may be textual or numeric-like
    return pd.read_csv(csv_path, dtype=str, keep_default_na=False)


def select_columns(df: pd.DataFrame, columns: str) -> pd.DataFrame:
    if not columns:
        return df
    desired: List[str] = [c.strip() for c in columns.split(",") if c.strip()]
    missing = [c for c in desired if c not in df.columns]
    if missing:
        print(f"Warning: missing columns ignored: {missing}")
    present = [c for c in desired if c in df.columns]
    return df[present] if present else df


def apply_filter(df: pd.DataFrame, expr: str) -> pd.DataFrame:
    if not expr:
        return df
    try:
        return df.query(expr, engine="python")
    except Exception as e:
        print(f"Invalid filter expression, returning unfiltered data. Error: {e}")
        return df


def maybe_sort(df: pd.DataFrame, sort_col: str, descending: bool) -> pd.DataFrame:
    if not sort_col or sort_col not in df.columns:
        if sort_col:
            print(f"Warning: sort column '{sort_col}' not found; skipping sort.")
        return df
    try:
        return df.sort_values(by=sort_col, ascending=not descending, kind="stable")
    except Exception as e:
        print(f"Sort failed: {e}. Returning unsorted data.")
        return df


def print_overview(df: pd.DataFrame) -> None:
    print("\n=== Columns ===")
    print(list(df.columns))

    print("\n=== Row count ===")
    print(len(df))

    print("\n=== Missing values per column ===")
    # Count empty strings as missing too
    missing = (df == "").sum().to_dict()
    for col in df.columns:
        missing[col] = missing.get(col, 0)
    print(missing)


def main() -> None:
    args = parse_args()
    df = load_dataframe(args.csv)

    print_overview(df)

    df_view = select_columns(df, args.columns)
    df_view = apply_filter(df_view, args.where)
    df_view = maybe_sort(df_view, args.sort, args.desc)

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 200)

    print("\n=== Preview ===")
    print(df_view.head(args.head))

    if args.export_csv:
        out_csv = args.export_csv
        df_view.to_csv(out_csv, index=False)
        print(f"\nExported CSV to: {out_csv}")

    if args.export_excel:
        out_xlsx = args.export_excel
        if not out_xlsx.lower().endswith(".xlsx"):
            out_xlsx += ".xlsx"
        try:
            df_view.to_excel(out_xlsx, index=False)
            print(f"Exported Excel to: {out_xlsx}")
        except Exception as e:
            print(f"Excel export failed: {e}")


if __name__ == "__main__":
    main()






