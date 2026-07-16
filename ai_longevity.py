"""
ai_longevity.py
----------------
Computes a dynamic "AI & Longevity" score (0-10) for a phone, used ONLY by the
Recommendation Insights radar chart on the results page.

This is deliberately SEPARATE from the Weighted Sum Model in recommender.py:
it does not touch, extend or influence the recommendation ranking in any way.
It simply derives an extra, visual-only dimension from data the catalog
already contains.

Design goal (per the feature brief): the score must be computed from a set of
independent SIGNALS, each of which:
  * reads whatever field(s) it needs from the phone dict,
  * gracefully falls back to a neutral contribution if those fields are
    absent, and
  * carries a fixed weight in the blend.

That means the UI never needs redesigning as the dataset grows: to make future
fields (e.g. `galaxy_ai`, `android_update_years`, `security_update_years`)
count, you only add or enable a SIGNAL below — nothing else changes. When a
real field arrives it simply overrides the heuristic used in its absence.

Every signal returns a value on a 0-10 scale; the weighted blend is also 0-10,
matching the other four radar dimensions produced by feature_engineering.py.
"""

from datetime import date


# ----------------------------------------------------------------------
# Reference tables (relative, illustrative — not official figures).
# ----------------------------------------------------------------------

# Chipset "AI tier": newer NPUs handle on-device Galaxy AI features better.
# Mirrors the performance tiers already used in feature_engineering.py but is
# intentionally its own table so the two can evolve independently.
_CHIPSET_AI_TIER = {
    "Snapdragon 8 Elite": 10.0,
    "Snapdragon 8 Gen 3": 9.2,
    "Exynos 2400": 8.6,
    "Exynos 2400e": 8.0,
    "Snapdragon 7 Gen 3": 6.6,
    "Exynos 1480": 5.6,
    "Exynos 1380": 4.6,
    "Exynos 1280": 3.6,
    "MediaTek Dimensity 6100+": 3.0,
}
_DEFAULT_CHIPSET_AI = 4.0

# How many years of OS + security support a Samsung tier typically receives.
# Used only as a FALLBACK when explicit update-policy fields are absent.
_CATEGORY_SUPPORT_YEARS = {
    "flagship": 7,
    "foldable": 7,
    "midrange": 5,
    "budget": 4,
}
_DEFAULT_SUPPORT_YEARS = 4

# Which Samsung tiers currently ship the full Galaxy AI suite (fallback only,
# used when an explicit `galaxy_ai` field is not present in the dataset).
_GALAXY_AI_BY_CATEGORY = {
    "flagship": 1.0,
    "foldable": 1.0,
    "midrange": 0.4,   # partial / subset of Galaxy AI features
    "budget": 0.1,
}


def _clamp(value, lo=0.0, hi=10.0):
    return max(lo, min(hi, value))


def _num(phone, key, default=None):
    """Safely pull a numeric field from a phone dict/row."""
    try:
        val = phone.get(key) if hasattr(phone, "get") else phone[key]
    except Exception:
        return default
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _text(phone, key, default=""):
    try:
        val = phone.get(key) if hasattr(phone, "get") else phone[key]
    except Exception:
        return default
    return str(val) if val is not None else default


# ----------------------------------------------------------------------
# Individual signals. Each returns (score_0_10, present: bool).
# `present=False` means the signal had to fall back to a heuristic because the
# richer field wasn't in the dataset yet — the blend still uses the value, but
# this lets callers see how "data-backed" the score currently is.
# ----------------------------------------------------------------------

def _signal_freshness(phone):
    """Newer launch year -> more years of useful life ahead. Uses
    `release_year` (present today). A 5-year window maps to 0-10."""
    year = _num(phone, "release_year")
    if year is None:
        return 5.0, False
    current = date.today().year
    age = max(0, current - int(year))
    # 0 yrs old -> 10, 5+ yrs old -> ~2. Linear, floored.
    return _clamp(10.0 - age * 1.6, 2.0, 10.0), True


def _signal_galaxy_ai(phone):
    """On-device Galaxy AI capability. Prefers an explicit `galaxy_ai` field
    (0/1 or 0-1 fraction) if the dataset provides it; otherwise falls back to a
    per-category heuristic. Blended with chipset AI tier for nuance."""
    chipset = _text(phone, "processor")
    chipset_ai = _CHIPSET_AI_TIER.get(chipset, _DEFAULT_CHIPSET_AI)

    explicit = _num(phone, "galaxy_ai")
    if explicit is not None:
        # Accept either 0/1, 0-1 fraction, or a 0-10 rating.
        frac = explicit / 10.0 if explicit > 1 else explicit
        ai_support = _clamp(frac * 10.0)
        return _clamp(0.5 * ai_support + 0.5 * chipset_ai), True

    category = _text(phone, "category").lower()
    heuristic = _GALAXY_AI_BY_CATEGORY.get(category, 0.3) * 10.0
    return _clamp(0.5 * heuristic + 0.5 * chipset_ai), False


def _signal_update_policy(phone):
    """Years of OS + security updates. Prefers explicit
    `android_update_years` / `security_update_years` fields; otherwise falls
    back to a per-category norm. A 7-year policy maps to 10."""
    os_years = _num(phone, "android_update_years")
    sec_years = _num(phone, "security_update_years")

    if os_years is not None or sec_years is not None:
        years = max(os_years or 0, sec_years or 0)
        return _clamp(years / 7.0 * 10.0), True

    category = _text(phone, "category").lower()
    years = _CATEGORY_SUPPORT_YEARS.get(category, _DEFAULT_SUPPORT_YEARS)
    return _clamp(years / 7.0 * 10.0), False


# Signal registry: (name, function, weight). Weights need not sum to 1; they
# are normalised at blend time, so adding a new signal is a one-line change.
SIGNALS = [
    ("freshness", _signal_freshness, 0.30),
    ("galaxy_ai", _signal_galaxy_ai, 0.40),
    ("update_policy", _signal_update_policy, 0.30),
]


def compute_ai_longevity(phone) -> float:
    """
    Blend all registered signals into a single 0-10 AI & Longevity score.

    `phone` may be a dict (as produced by _phone_to_dict) or a pandas row;
    both support the `.get`/`[]` access used above. Missing fields never raise
    — the relevant signal simply falls back to a neutral/heuristic value.
    """
    total_w = sum(w for _, _, w in SIGNALS) or 1.0
    blended = 0.0
    for _name, fn, weight in SIGNALS:
        score, _present = fn(phone)
        blended += score * weight
    return round(blended / total_w, 2)


def ai_longevity_breakdown(phone) -> dict:
    """Optional diagnostics: per-signal scores + whether each was data-backed
    or heuristic. Not required by the UI, but handy for debugging/future work."""
    out = {}
    for name, fn, weight in SIGNALS:
        score, present = fn(phone)
        out[name] = {"score": round(score, 2), "weight": weight, "data_backed": present}
    out["ai_longevity_score"] = compute_ai_longevity(phone)
    return out


if __name__ == "__main__":
    import pandas as pd
    df = pd.read_csv("phones.csv")
    for _, row in df.iterrows():
        p = row.to_dict()
        print(f"{p['model']:20s} AI&Longevity = {compute_ai_longevity(p)}")