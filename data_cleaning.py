"""
data_cleaning.py
-----------------
Cleans the raw Samsung Galaxy phone dataset (raw_phones.csv) and produces
a production-ready dataset (phones.csv).

Cleaning steps performed:
    1. Remove exact duplicate rows (by phone_id / model).
    2. Fill missing numeric values (e.g. storage_gb) using sensible
       category-based defaults (median of same category/RAM tier).
    3. Detect and fix unrealistic prices (e.g. data-entry errors such as
       a Rs. 9,99,999 mid-range phone) using an IQR-based outlier check
       against phones of the same category.
    4. Standardise text fields (strip whitespace, consistent casing).
    5. Validate value ranges (battery, RAM, storage must be positive).

Run standalone:
    python data_cleaning.py
This regenerates phones.csv from raw_phones.csv and prints a cleaning report.
"""

import pandas as pd
import numpy as np

RAW_PATH = "raw_phones.csv"
CLEAN_PATH = "phones.csv"


def load_raw(path: str = RAW_PATH) -> pd.DataFrame:
    """Load the raw, unclean dataset."""
    return pd.read_csv(path)


def drop_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Remove exact duplicate phone entries (same phone_id + model)."""
    before = len(df)
    df = df.drop_duplicates(subset=["phone_id", "model"], keep="first").reset_index(drop=True)
    removed = before - len(df)
    if removed:
        print(f"[clean] Removed {removed} duplicate row(s).")
    return df


def fix_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fill missing numeric values using the median of phones in the same
    'category' (flagship / midrange / budget / foldable), which is a more
    realistic estimate than a global median.
    """
    numeric_cols = ["ram_gb", "storage_gb", "battery_mah", "charging_w",
                     "main_camera_mp", "ultra_wide_mp", "telephoto_mp",
                     "front_camera_mp", "weight_g"]

    for col in numeric_cols:
        if df[col].isna().any():
            missing_idx = df[df[col].isna()].index.tolist()
            df[col] = df.groupby("category")[col].transform(
                lambda s: s.fillna(s.median())
            )
            # Fallback: if still NaN (whole category missing), use global median
            df[col] = df[col].fillna(df[col].median())
            print(f"[clean] Filled {len(missing_idx)} missing value(s) in '{col}' "
                  f"using category median (rows: {missing_idx}).")
    return df


#: Domain-informed realistic price bands per category (India, 2024-2025),
#: used to catch data-entry errors (e.g. a stray extra digit). With only a
#: handful of phones per category in this dataset, a purely statistical
#: test (IQR / leave-one-out) is unreliable — one bad value skews the very
#: reference it's compared against — so real catalog-cleaning pipelines
#: typically fall back on known-good domain bounds instead.
PRICE_BANDS = {
    "flagship": (45_000, 175_000),
    "foldable": (90_000, 200_000),
    "midrange": (18_000, 48_000),
    "budget": (8_000, 27_000),
}


def fix_unrealistic_prices(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect unrealistic prices using domain-informed price bands per
    category (a flagship costing Rs.1,29,999 is normal; a budget phone
    costing Rs.9,99,999 is clearly a data-entry error / extra digit).
    Detected outliers are replaced with the median price of the *other*,
    valid phones in the same category.
    """
    df["price_inr"] = pd.to_numeric(df["price_inr"], errors="coerce")

    for cat, group in df.groupby("category"):
        low, high = PRICE_BANDS.get(cat, (0, np.inf))
        bad_mask = (group["price_inr"] < low) | (group["price_inr"] > high)
        bad_idx = group[bad_mask].index

        if len(bad_idx) > 0:
            good_prices = group.loc[~bad_mask, "price_inr"]
            replacement = good_prices.median() if not good_prices.empty else (low + high) / 2
            for idx in bad_idx:
                old_val = df.loc[idx, "price_inr"]
                df.loc[idx, "price_inr"] = replacement
                print(f"[clean] Row {idx} ({df.loc[idx, 'model']}): unrealistic "
                      f"price Rs.{old_val:,.0f} (outside expected Rs.{low:,.0f}-"
                      f"Rs.{high:,.0f} range for '{cat}') replaced with "
                      f"Rs.{replacement:,.0f}.")
    return df


def standardise_text(df: pd.DataFrame) -> pd.DataFrame:
    """Trim whitespace and normalise casing on text columns."""
    text_cols = ["brand", "model", "processor", "display_type", "category"]
    for col in text_cols:
        df[col] = df[col].astype(str).str.strip()
    df["category"] = df["category"].str.lower()
    return df


def validate_ranges(df: pd.DataFrame) -> pd.DataFrame:
    """Drop/flag rows with impossible values (defensive check)."""
    before = len(df)
    df = df[(df["ram_gb"] > 0) & (df["storage_gb"] > 0) &
            (df["battery_mah"] > 1000) & (df["price_inr"] > 1000)]
    dropped = before - len(df)
    if dropped:
        print(f"[clean] Dropped {dropped} row(s) with impossible values.")
    return df.reset_index(drop=True)


def clean_dataset(raw_path: str = RAW_PATH) -> pd.DataFrame:
    """Full cleaning pipeline. Returns the cleaned DataFrame."""
    print("=" * 60)
    print("Samsung Galaxy Dataset — Cleaning Report")
    print("=" * 60)

    df = load_raw(raw_path)
    print(f"[load] Loaded {len(df)} raw rows.")

    df = drop_duplicates(df)
    df = standardise_text(df)
    df = fix_missing_values(df)
    df = fix_unrealistic_prices(df)
    df = validate_ranges(df)

    # Ensure correct dtypes after cleaning
    int_cols = ["release_year", "ram_gb", "storage_gb", "battery_mah",
                "charging_w", "main_camera_mp", "ultra_wide_mp",
                "telephoto_mp", "front_camera_mp", "weight_g"]
    for col in int_cols:
        df[col] = df[col].round().astype(int)
    df["price_inr"] = df["price_inr"].round().astype(int)

    print(f"[done] Final clean dataset: {len(df)} rows, {df.shape[1]} columns.")
    print("=" * 60)
    return df


def save_clean(df: pd.DataFrame, path: str = CLEAN_PATH) -> None:
    df.to_csv(path, index=False)
    print(f"[save] Clean dataset written to '{path}'.")


if __name__ == "__main__":
    cleaned = clean_dataset()
    save_clean(cleaned)
