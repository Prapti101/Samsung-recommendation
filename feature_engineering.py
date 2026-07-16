"""
feature_engineering.py
-----------------------
Transforms raw phone specifications (phones.csv) into 4 scores on a 0-10
scale, which the Weighted Sum Model (WSM) in recommender.py combines
according to persona weights:

    Camera Score       - main / telephoto / ultra-wide / front cameras
    Performance Score   - chipset tier, RAM, high-refresh display
    Battery Score       - battery capacity and charging speed
    Value Score         - "spec-per-rupee": how much phone you get for the price

Design note (why the scores differentiate personas):
Camera, Performance and Battery are scored on **absolute anchors** (against
sensible best-in-class reference values) rather than pure min-max
normalisation. Pure min-max let a single outlier (e.g. a 200MP camera or a
5000mAh battery) crush every other phone toward zero, which made one phone win
for *every* persona. Absolute anchoring keeps a real 4000mAh battery or a 50MP
camera at a sensible mid-high score, so a phone's genuine strengths show
through and different persona weightings surface different phones. Value stays
relative (min-max) because "value for money" is inherently comparative.
"""

import pandas as pd
import numpy as np

# ----------------------------------------------------------------------
# Chipset performance tiers (relative benchmark-style score, ~0-100).
# Simplified relative rankings used only to differentiate processors for
# scoring purposes -- not official benchmark figures.
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


def _clip10(series: pd.Series) -> pd.Series:
    """Clamp a numeric series to the 0-10 range and round to 2 dp."""
    return np.round(np.clip(series, 0, 10), 2)


def _min_max_normalize(series: pd.Series, invert: bool = False,
                       hi_cap: float = 10.0) -> pd.Series:
    """
    Scale a series to 0..hi_cap using min-max normalisation. If invert=True,
    a lower raw value maps to a higher score. Used for the (comparative)
    value score only.
    """
    arr = series.to_numpy(dtype=float)
    lo, hi = np.min(arr), np.max(arr)
    if hi == lo:  # avoid divide-by-zero when every phone ties
        return pd.Series(np.full(len(arr), hi_cap / 2.0), index=series.index)
    scaled = (arr - lo) / (hi - lo)
    if invert:
        scaled = 1 - scaled
    return pd.Series(np.round(scaled * hi_cap, 2), index=series.index)


def compute_camera_score(df: pd.DataFrame) -> pd.Series:
    """
    Camera score on an absolute anchor. A sqrt transform is applied to each
    megapixel figure (sensor quality doesn't scale linearly with MP), then each
    lens is measured against a best-in-class reference so a phone's real
    capability shows through instead of being crushed by the 200MP flagships:

      - main sensor gives a solid base (50MP lands mid, 200MP tops it),
      - a telephoto (zoom) lens is rewarded strongly -- it is what most
        separates a "camera phone" from an ordinary one,
      - ultra-wide and front cameras add smaller bonuses,
      - a small base keeps every phone off the zero floor.
    """
    score = (
        np.sqrt(df["main_camera_mp"]) / np.sqrt(200) * 5.0 +
        np.sqrt(df["telephoto_mp"]) / np.sqrt(50) * 3.2 +
        np.sqrt(df["ultra_wide_mp"]) / np.sqrt(50) * 1.2 +
        np.sqrt(df["front_camera_mp"]) / np.sqrt(50) * 1.1 +
        1.5
    )
    return _clip10(score)


def compute_performance_score(df: pd.DataFrame) -> pd.Series:
    """
    Performance score on an absolute anchor: chipset tier is the main driver,
    with RAM and a high-refresh (120Hz+) display adding smaller bonuses.
    """
    chipset = df["processor"].map(CHIPSET_TIER).fillna(DEFAULT_CHIPSET_SCORE)
    score = (
        chipset / 98 * 8.0 +
        df["ram_gb"] / 12 * 1.2 +
        (df["refresh_rate_hz"] >= 120).astype(float) * 0.8
    )
    return _clip10(score)


def compute_battery_score(df: pd.DataFrame) -> pd.Series:
    """
    Battery score on an absolute anchor: capacity (against a 5500mAh reference)
    plus charging speed (against a 65W reference). A real 4000mAh battery scores
    a sensible mid value instead of being normalised down to near-zero.
    """
    score = (
        df["battery_mah"] / 5500 * 7.0 +
        df["charging_w"] / 65 * 3.0
    )
    return _clip10(score)


def compute_value_score(df: pd.DataFrame) -> pd.Series:
    """
    "Spec-per-rupee": overall hardware quality (camera + performance + battery)
    divided by sqrt(price) -- sqrt so premium flagships aren't punished as
    harshly as a straight price ratio would, while budget phones still win the
    value comparison. Value is inherently comparative, so it is min-max
    normalised across the catalog.
    """
    overall_hw = (
        compute_camera_score(df) +
        compute_performance_score(df) +
        compute_battery_score(df)
    )
    spec_per_sqrt_rupee = overall_hw / np.sqrt(df["price_inr"])
    return _min_max_normalize(spec_per_sqrt_rupee)


def compute_display_score(df: pd.DataFrame) -> pd.Series:
    """
    Display score on an absolute anchor: panel quality (Dynamic AMOLED 2X is
    Samsung's best tier, Super AMOLED is very good), high refresh rate (120Hz),
    and screen size all contribute, so flagships with the best screens score
    highest while budget panels still register as decent.
    """
    panel = df["display_type"].astype(str).str.contains("2X", case=False).astype(float)
    panel_score = 0.75 + panel * 0.25            # Super AMOLED 0.75, Dynamic AMOLED 2X 1.0
    refresh_score = np.clip((df["refresh_rate_hz"] - 60) / (120 - 60), 0, 1)
    size_score = np.clip((df["display_inch"] - 6.0) / (7.6 - 6.0), 0, 1)
    score = panel_score * 4.0 + refresh_score * 4.0 + size_score * 2.0
    return _clip10(score)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds camera_score, performance_score, battery_score, value_score and
    display_score columns (0-10) to a copy of the input DataFrame.
    """
    out = df.copy()
    out["camera_score"] = compute_camera_score(out)
    out["performance_score"] = compute_performance_score(out)
    out["battery_score"] = compute_battery_score(out)
    out["value_score"] = compute_value_score(out)
    out["display_score"] = compute_display_score(out)
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