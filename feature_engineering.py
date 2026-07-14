"""
feature_engineering.py
-----------------------
Transforms raw phone specifications (phones.csv) into 4 normalised
scores on a 0-10 scale, which the Weighted Sum Model (WSM) in
recommender.py combines according to persona weights:

    Camera Score       - based on main / ultra-wide / telephoto / front MP
    Performance Score   - based on chipset tier, RAM and refresh rate
    Battery Score       - based on battery capacity and charging speed
    Value Score         - "spec-per-rupee": how much overall phone you get
                           for the price (higher = better value)

All scores use min-max normalisation (NumPy) so that the best phone in
the catalog for a given dimension scores close to 10 and the weakest
scores close to 0, keeping recommendations dataset-relative and easy to
reason about.
"""

import pandas as pd
import numpy as np

# ----------------------------------------------------------------------
# Chipset performance tiers (0-100 relative benchmark-style score).
# These are simplified, relative rankings used only to differentiate
# processors for scoring purposes -- not official benchmark figures.
# ----------------------------------------------------------------------
CHIPSET_TIER = {
    "Snapdragon 8 Elite": 98,
    "Snapdragon 8 Gen 3": 92,
    "Exynos 2400": 88,
    "Exynos 2400e": 82,
    "Snapdragon 7 Gen 3": 68,
    "Exynos 1480": 58,
    "Exynos 1380": 48,
    "Exynos 1280": 38,
    "MediaTek Dimensity 6100+": 30,
}
DEFAULT_CHIPSET_SCORE = 40  # fallback for any unseen chipset


def _min_max_normalize(series: pd.Series, invert: bool = False) -> pd.Series:
    """
    Scale a pandas Series to the 0-10 range using min-max normalisation.
    If invert=True, a *lower* raw value maps to a *higher* score (useful
    for e.g. price, where cheaper is "better" for value scoring).
    """
    arr = series.to_numpy(dtype=float)
    lo, hi = np.min(arr), np.max(arr)
    if hi == lo:  # avoid divide-by-zero when every phone ties
        return pd.Series(np.full(len(arr), 5.0), index=series.index)
    scaled = (arr - lo) / (hi - lo)
    if invert:
        scaled = 1 - scaled
    return pd.Series(np.round(scaled * 10, 2), index=series.index)


def compute_camera_score(df: pd.DataFrame) -> pd.Series:
    """
    Weighted composite of camera hardware, then min-max normalised.
    Main sensor and telephoto (zoom versatility) are weighted highest,
    since they matter most for everyday and creative photography.
    A sqrt transform is applied to each megapixel figure first -- sensor
    quality doesn't scale linearly with MP count (e.g. a 200MP sensor
    isn't "4x better" than a 50MP one), so this keeps very high-MP
    flagship sensors from completely swamping the 0-10 scale and squashing
    every other phone near zero.
    """
    composite = (
        np.sqrt(df["main_camera_mp"]) * 0.45 +
        np.sqrt(df["ultra_wide_mp"]) * 0.20 +
        np.sqrt(df["telephoto_mp"]) * 0.20 +
        np.sqrt(df["front_camera_mp"]) * 0.15
    )
    return _min_max_normalize(composite)


def compute_performance_score(df: pd.DataFrame) -> pd.Series:
    """
    Weighted composite of chipset tier, RAM, and refresh rate (smoothness),
    then min-max normalised.
    """
    chipset_score = df["processor"].map(CHIPSET_TIER).fillna(DEFAULT_CHIPSET_SCORE)
    composite = (
        chipset_score * 0.60 +
        df["ram_gb"] * 2.0 * 0.25 +      # scaled so RAM contributes meaningfully
        df["refresh_rate_hz"] * 0.15
    )
    return _min_max_normalize(composite)


def compute_battery_score(df: pd.DataFrame) -> pd.Series:
    """
    Weighted composite of battery capacity and charging speed (fast
    charging offsets a smaller cell), then min-max normalised.
    """
    composite = (
        df["battery_mah"] * 0.75 / 50 +   # scaled down so both terms are comparable
        df["charging_w"] * 0.25
    )
    return _min_max_normalize(composite)


def compute_value_score(df: pd.DataFrame) -> pd.Series:
    """
    "Spec-per-rupee": combines camera, performance and battery quality
    into an overall hardware score, then divides by sqrt(price) to see
    how much phone you get for the money -- sqrt is used instead of a
    straight linear divide so that ultra-premium flagships aren't
    penalised as harshly as a pure price ratio would (a genuinely
    excellent flagship should still register as *reasonable* value, not
    near-zero, while budget phones still win the value comparison
    overall). Normalised 0-10 across the catalog.
    """
    overall_hw = (
        compute_camera_score(df) +
        compute_performance_score(df) +
        compute_battery_score(df)
    )
    spec_per_sqrt_rupee = overall_hw / np.sqrt(df["price_inr"])
    return _min_max_normalize(spec_per_sqrt_rupee)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds camera_score, performance_score, battery_score and value_score
    columns (0-10) to a copy of the input DataFrame and returns it.
    """
    out = df.copy()
    out["camera_score"] = compute_camera_score(out)
    out["performance_score"] = compute_performance_score(out)
    out["battery_score"] = compute_battery_score(out)
    out["value_score"] = compute_value_score(out)
    return out


def load_engineered_phones(csv_path: str = "phones.csv") -> pd.DataFrame:
    """Convenience loader: reads phones.csv and returns it with scores added."""
    df = pd.read_csv(csv_path)
    return engineer_features(df)


if __name__ == "__main__":
    result = load_engineered_phones()
    cols = ["model", "price_inr", "camera_score", "performance_score",
            "battery_score", "value_score"]
    print(result[cols].to_string(index=False))
