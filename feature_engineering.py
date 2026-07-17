"""
feature_engineering.py — STAGE 1 of the recommendation pipeline
==============================================================
Turns raw phone specs (phones.csv) into comparable scores. This module is the
single source of truth for "how good is this phone at X"; nothing else in the
codebase scores a phone.

Pipeline context:
    phones.csv
      -> [THIS MODULE]  raw specs        -> per-dimension scores (0-10)
      -> recommender.py per-dimension    -> weighted match score (0-100)
      -> app.py         match score      -> page / API response

The four RANKED dimensions (what the WSM actually ranks on):
    camera_score       main + telephoto + ultra-wide + front lenses
    performance_score  chipset tier + RAM
    battery_score      capacity + charging speed
    display_score      panel tier + refresh rate + size

One derived dimension (informational, NOT ranked):
    value_score        spec-per-rupee, surfaced in Community Insights

Why absolute anchors, not min-max
---------------------------------
Camera / performance / battery / display are measured against fixed best-in-class
references (see the REFERENCE_* constants). Pure min-max normalisation let one
outlier (a 200MP camera, a 5000mAh battery) crush every other phone toward zero,
which made a single phone win for *every* persona. Anchoring keeps a real
4000mAh battery at a sensible mid score, so genuine strengths show through and
different persona weightings surface different phones. value_score is the
exception and stays min-max, because "value for money" is only meaningful
relative to the rest of the catalog.

Every score in this module is on the same 0-10 scale (SCORE_MAX).
"""

import pandas as pd
import numpy as np

# ----------------------------------------------------------------------
# Chipset performance tiers (relative benchmark-style score, ~0-100).
# Simplified relative rankings used only to differentiate processors for
# scoring purposes -- not official benchmark figures.
# ----------------------------------------------------------------------
# Values are the `relative_performance_index` from raw_phones.xlsx (0-10),
# scaled x10 onto this table's 0-100 scale. Taking them from the spreadsheet
# keeps the catalog and the scorer in agreement instead of hand-guessing tiers.
# Legacy names kept as aliases so older CSV exports still resolve.
CHIPSET_TIER = {
    "Snapdragon 8 Gen 4": 98,
    "Snapdragon 8 Gen 3": 95,
    "Exynos 2500": 94,
    "Dimensity 9400": 92,
    "Exynos 2400": 90,
    "Exynos 2400e": 88,
    "Snapdragon 8 Gen 2": 88,
    "Exynos 1580": 78,
    "Exynos 1480": 72,
    "Exynos 2200": 70,
    "Snapdragon 7 Gen 1": 68,
    "Snapdragon 6 Gen 3": 65,
    "Exynos 1380": 60,
    "Dimensity 1080": 58,
    "Exynos 1280": 56,
    "Exynos 1330": 55,
    "Dimensity 6100+": 50,
    "Helio G99": 45,
    "Snapdragon 680": 42,
    "Helio G85": 38,
    "Exynos 850": 30,
    "Helio P35": 25,
    # --- aliases for chipset names used by earlier catalog exports ---
    "MediaTek Dimensity 6100+": 50,
    "Snapdragon 8 Elite": 98,
    "Snapdragon 7 Gen 3": 68,
}
# Deliberately below every real entry above: an unseen chipset must never
# out-rank a chipset we actually know is slow. (The old default of 40 outranked
# the Dimensity 6100+ at 30, so unknown budget silicon scored *better* than
# known budget silicon.)
DEFAULT_CHIPSET_SCORE = 20

# ----------------------------------------------------------------------
# Scale + reference anchors
# ----------------------------------------------------------------------
# Every dimension score in this module is produced on ONE scale: 0-10.
# recommender.py combines them with weights that sum to 1.0, so the weighted
# total is also 0-10; it is multiplied by 10 exactly once, at the presentation
# boundary, to read as a 0-100 "match %". There is no other scale in the system.
SCORE_MAX = 10.0

# "Best in class" anchors. Scores are measured against these fixed references
# rather than min-max normalised, so a phone's real capability shows through.
# (Pure min-max let one 200MP outlier crush every other phone toward zero,
# which made a single phone win for *every* persona.)
MAX_CHIPSET_TIER = 98      # fastest entry in CHIPSET_TIER
REFERENCE_RAM_GB = 12
REFERENCE_MAIN_MP = 200
REFERENCE_LENS_MP = 50     # telephoto / ultra-wide / front reference
REFERENCE_BATTERY_MAH = 5500
REFERENCE_CHARGING_W = 65
REFERENCE_REFRESH_HZ = 120
BASELINE_REFRESH_HZ = 60   # 60Hz is the floor, so it scores 0 on refresh
REFERENCE_SIZE_MAX_IN = 7.6
REFERENCE_SIZE_MIN_IN = 6.0


def _clip10(series: pd.Series) -> pd.Series:
    """Clamp a numeric series to the 0-10 scale and round to 2 dp."""
    return np.round(np.clip(series, 0, SCORE_MAX), 2)


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
        np.sqrt(df["main_camera_mp"]) / np.sqrt(REFERENCE_MAIN_MP) * 5.0 +
        np.sqrt(df["telephoto_mp"]) / np.sqrt(REFERENCE_LENS_MP) * 3.2 +
        np.sqrt(df["ultra_wide_mp"]) / np.sqrt(REFERENCE_LENS_MP) * 1.2 +
        np.sqrt(df["front_camera_mp"]) / np.sqrt(REFERENCE_LENS_MP) * 1.1 +
        1.5                                   # floor: no phone scores a true zero
    )
    return _clip10(score)


def compute_performance_score(df: pd.DataFrame) -> pd.Series:
    """
    Purpose : Score raw compute power on a 0-10 absolute anchor.
    Inputs  : df with `processor` and `ram_gb`.
    Output  : Series of 0-10 scores.
    Algorithm:
        chipset_tier / 98 * 8.6   -- the dominant driver; 98 = fastest chipset
                                     in CHIPSET_TIER, so the class leader nears 8.6
        + ram_gb / 12 * 1.4       -- headroom for multitasking; 12GB = reference

    AUDIT FIX — refresh rate removed from this formula. It previously added a
    +0.8 bonus for >=120Hz while compute_display_score() *also* scores refresh
    rate, so a 120Hz phone was rewarded twice for one spec: once under
    "Performance" and again under "Display". Every persona weights both
    dimensions, so the double count silently inflated 120Hz phones in the final
    WSM total. Refresh rate is a display property and is now scored there only.
    The freed 0.8 was folded into chipset (8.0 -> 8.6) and RAM (1.2 -> 1.4) so a
    top phone can still reach 10 and the dimension keeps its full 0-10 range.
    """
    chipset = df["processor"].map(CHIPSET_TIER).fillna(DEFAULT_CHIPSET_SCORE)
    score = (
        chipset / MAX_CHIPSET_TIER * 8.6 +
        df["ram_gb"] / REFERENCE_RAM_GB * 1.4
    )
    return _clip10(score)


def compute_battery_score(df: pd.DataFrame) -> pd.Series:
    """
    Battery score on an absolute anchor: capacity (against a 5500mAh reference)
    plus charging speed (against a 65W reference). A real 4000mAh battery scores
    a sensible mid value instead of being normalised down to near-zero.
    """
    score = (
        df["battery_mah"] / REFERENCE_BATTERY_MAH * 7.0 +
        df["charging_w"] / REFERENCE_CHARGING_W * 3.0
    )
    return _clip10(score)


def compute_value_score(df: pd.DataFrame, camera: pd.Series = None,
                        performance: pd.Series = None,
                        battery: pd.Series = None) -> pd.Series:
    """
    Purpose : Rate "spec-per-rupee" on a 0-10 scale.
    Inputs  : df with `price_inr`; optionally the three hardware scores if the
              caller has already computed them (engineer_features does).
    Output  : Series of 0-10 scores.
    Algorithm:
        (camera + performance + battery) / sqrt(price)
        then min-max normalised across the catalog.
        sqrt(price) rather than price so premium flagships aren't punished as
        harshly as a straight ratio would, while budget phones still win.
        Value is the one dimension that is *comparative* by nature ("value
        against what?"), so min-max is correct here where it would be wrong for
        the absolute-anchored dimensions.

    NOTE ON SCOPE: value_score is NOT an input to the WSM ranking — see the
    "value_score is deliberately not ranked" note in recommender.py. It is a
    derived, informational metric surfaced in Community Insights.

    The optional arguments exist to avoid recomputing the three hardware scores;
    this function used to call compute_camera/performance/battery_score itself,
    so engineer_features() computed each of them twice per request.
    """
    camera = compute_camera_score(df) if camera is None else camera
    performance = compute_performance_score(df) if performance is None else performance
    battery = compute_battery_score(df) if battery is None else battery

    overall_hw = camera + performance + battery
    spec_per_sqrt_rupee = overall_hw / np.sqrt(df["price_inr"])
    return _min_max_normalize(spec_per_sqrt_rupee)


# Panel quality tiers (0-1). An LCD is a genuinely worse panel than any AMOLED
# -- worse contrast, worse blacks, worse viewing angles -- so it must score
# below them. The previous rule only tested for "2X" and gave everything else
# 0.75, which graded the catalog's PLS LCD phones exactly like Super AMOLED.
PANEL_TIER = {
    "dynamic amoled 2x": 1.0,
    "foldable dynamic amoled": 1.0,
    "super amoled plus": 0.82,
    "super amoled": 0.75,
    "pls lcd": 0.45,
    "tft lcd": 0.40,
}
DEFAULT_PANEL_TIER = 0.75    # unknown AMOLED-ish panel: unchanged from before


def _panel_tier(display_type: pd.Series) -> pd.Series:
    """
    Map a display_type string to its quality tier. Matched most-specific-first
    so "Super AMOLED Plus" doesn't get picked up by the "super amoled" entry.
    """
    s = display_type.astype(str).str.strip().str.lower()
    tier = pd.Series(DEFAULT_PANEL_TIER, index=s.index, dtype=float)
    for name in sorted(PANEL_TIER, key=len, reverse=True):
        tier = tier.mask(s == name, PANEL_TIER[name])
    # Fall back to substring matching for any unseen variant spelling.
    unmatched = ~s.isin(PANEL_TIER)
    for name in sorted(PANEL_TIER, key=len, reverse=True):
        tier = tier.mask(unmatched & s.str.contains(name, regex=False), PANEL_TIER[name])
    return tier


def compute_display_score(df: pd.DataFrame) -> pd.Series:
    """
    Display score on an absolute anchor: panel quality (Dynamic AMOLED 2X is
    Samsung's best tier, Super AMOLED is very good, LCD is clearly a step down),
    high refresh rate (120Hz), and screen size all contribute, so flagships with
    the best screens score highest while budget panels still register as decent.
    """
    panel_score = _panel_tier(df["display_type"])
    refresh_score = np.clip(
        (df["refresh_rate_hz"] - BASELINE_REFRESH_HZ)
        / (REFERENCE_REFRESH_HZ - BASELINE_REFRESH_HZ), 0, 1)
    size_score = np.clip(
        (df["display_inch"] - REFERENCE_SIZE_MIN_IN)
        / (REFERENCE_SIZE_MAX_IN - REFERENCE_SIZE_MIN_IN), 0, 1)
    score = panel_score * 4.0 + refresh_score * 4.0 + size_score * 2.0
    return _clip10(score)


# The four dimensions the WSM ranks on. Kept here, next to the functions that
# produce them, so recommender.py and the UI can never drift out of step with
# the scorer.
RANKED_DIMENSIONS = ("camera", "performance", "battery", "display")


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Purpose : Attach every derived score to the raw catalog.
    Inputs  : df of raw specs (the columns of phones.csv).
    Output  : A copy with camera_score, performance_score, battery_score,
              display_score and value_score added — all on the 0-10 SCORE_MAX
              scale.
    Algorithm: Each dimension is scored independently against fixed anchors, then
              value_score is derived from the three hardware scores (passed in,
              not recomputed).
    """
    out = df.copy()
    camera = compute_camera_score(out)
    performance = compute_performance_score(out)
    battery = compute_battery_score(out)

    out["camera_score"] = camera
    out["performance_score"] = performance
    out["battery_score"] = battery
    out["display_score"] = compute_display_score(out)
    # Derived from the three above; reusing them avoids scoring each phone twice.
    out["value_score"] = compute_value_score(out, camera, performance, battery)
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