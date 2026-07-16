"""
recommender.py
---------------
Core recommendation engine. Implements the Weighted Sum Model (WSM):

    Score = Camera*w1 + Performance*w2 + Battery*w3 + Value*w4

for every phone in the catalog, applies an optional budget filter, ranks
phones by score, and generates a dynamic, human-readable explanation for
each of the Top 3 recommendations.
"""

import numpy as np
import pandas as pd

from feature_engineering import load_engineered_phones

SCORE_COLS = ["camera_score", "performance_score", "battery_score", "display_score"]
WEIGHT_KEYS = ["camera", "performance", "battery", "display"]


def compute_wsm_scores(df: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """
    Apply the Weighted Sum Model to every row of df.

    Args:
        df: DataFrame that already has camera_score, performance_score,
            battery_score, value_score columns (0-10 each).
        weights: dict with keys camera, performance, battery, value,
                 summing to 1.0.

    Returns:
        A copy of df with an added 'match_score' column (0-100, i.e. the
        WSM score out of 10, scaled to a percentage for display).
    """
    out = df.copy()
    raw_score = (
        out["camera_score"] * weights["camera"] +
        out["performance_score"] * weights["performance"] +
        out["battery_score"] * weights["battery"] +
        out["display_score"] * weights["display"]
    )
    # raw_score is out of 10 (since each component is 0-10 and weights sum to 1)
    out["wsm_raw"] = raw_score
    out["match_score"] = np.round(raw_score * 10, 1)  # convert to 0-100 for UI
    return out


def apply_budget_filter(df: pd.DataFrame, budget: int,
                        tolerance: float = 0.0) -> tuple:
    """
    Budget is a hard constraint, not a hint.

    Returns (pool, within_budget):
      * within_budget=True  -> every phone in `pool` costs <= the budget, so the
                               caller ranks purely by persona match score.
      * within_budget=False -> nothing in the catalog fits the budget. `pool` is
                               the whole catalog and the caller ranks by price
                               nearness instead, so the user is offered the
                               closest phone to what they can spend.

    Previously the no-fit case returned the five cheapest phones and let the
    match score decide, which surfaced a phone at ~2x the stated budget (a
    ₹13,000 budget recommended a ₹26,999 phone because it scored best of the
    five). Ranking is now the caller's job -- see _rank_pool().
    """
    if not budget or budget <= 0:
        return df, True

    ceiling = budget * (1 + tolerance)
    within = df[df["price_inr"] <= ceiling]

    if within.empty:
        return df.copy(), False

    return within, True


def _rank_pool(df: pd.DataFrame, budget: int, within_budget: bool) -> pd.DataFrame:
    """
    Order a scored pool.

    Within budget: best persona match first -- the user can afford any of these,
    so the only question is which suits them best.

    Nothing within budget: nearest price first (match score breaks ties), so the
    #1 pick is the closest phone to the stated budget rather than the
    best-scoring expensive one.
    """
    if within_budget:
        return df.sort_values("match_score", ascending=False).reset_index(drop=True)

    out = df.copy()
    out["_price_gap"] = (out["price_inr"] - budget).abs()
    ranked = out.sort_values(["_price_gap", "match_score"],
                             ascending=[True, False]).reset_index(drop=True)
    return ranked.drop(columns=["_price_gap"])


def _generate_reason(row: pd.Series, weights: dict, rank: int,
                     budget: int = None, within_budget: bool = True) -> str:
    """
    Build a dynamic, plain-English explanation for why this phone was
    recommended, based on which of its scores are strongest *and* most
    heavily weighted for the active persona.

    When nothing in the catalog fits the stated budget we say so outright:
    the pick is over budget, and presenting it as a plain match would mislead
    someone who told us exactly what they could spend.
    """
    # Rank each score dimension by (score * weight) contribution
    contributions = {
        "camera": row["camera_score"] * weights["camera"],
        "performance": row["performance_score"] * weights["performance"],
        "battery": row["battery_score"] * weights["battery"],
        "display": row["display_score"] * weights["display"],
    }
    top_dims = sorted(contributions, key=contributions.get, reverse=True)

    # Wording scales with the phone's ACTUAL score in each dimension. The
    # catalog spans ₹8,699 to ₹164,999, so fixed superlatives would lie: a
    # Helio G85 (3.5/10) is not "top-tier performance", and a 60Hz PLS LCD
    # (2.7/10) is not "a gorgeous display". Flagship wording is unchanged.
    def _tier(score, high, mid, low):
        return high if score >= 7.5 else (mid if score >= 5.0 else low)

    phrase_bank = {
        "camera": _tier(
            row["camera_score"],
            f"a standout {row['main_camera_mp']}MP camera system",
            f"a capable {row['main_camera_mp']}MP camera",
            f"a basic {row['main_camera_mp']}MP camera",
        ),
        "performance": _tier(
            row["performance_score"],
            f"top-tier performance from its {row['processor']} chipset",
            f"solid everyday performance from its {row['processor']} chipset",
            f"modest performance from its {row['processor']} chipset",
        ),
        "battery": _tier(
            row["battery_score"],
            f"a strong {row['battery_mah']}mAh battery with {row['charging_w']}W charging",
            f"a dependable {row['battery_mah']}mAh battery with {row['charging_w']}W charging",
            f"a modest {row['battery_mah']}mAh battery with {row['charging_w']}W charging",
        ),
        "display": _tier(
            row["display_score"],
            f"a gorgeous {row['display_inch']}\" {row['display_type']} display at {row['refresh_rate_hz']}Hz",
            f"a solid {row['display_inch']}\" {row['display_type']} display at {row['refresh_rate_hz']}Hz",
            f"a basic {row['display_inch']}\" {row['display_type']} display at {row['refresh_rate_hz']}Hz",
        ),
    }

    lead_dim, second_dim = top_dims[0], top_dims[1]
    reason = f"{row['model']} leads with {phrase_bank[lead_dim]}"

    if contributions[second_dim] > 0:
        reason += f", backed up by {phrase_bank[second_dim]}."
    else:
        reason += "."

    if rank == 1:
        reason = "Our #1 pick: " + reason
    elif row["price_inr"] == row.get("_min_price_in_results"):
        reason += " It's also the most affordable option in your Top 3."

    # Be explicit when we couldn't honour the budget, rather than quietly
    # showing a pricier phone as if it fit.
    if not within_budget and budget:
        over = int(row["price_inr"]) - int(budget)
        reason += (" Note: no Galaxy in our lineup costs ₹{:,} or less — this is "
                   "the closest at ₹{:,} (₹{:,} over your budget)."
                   .format(int(budget), int(row["price_inr"]), over))

    return reason


def get_top_recommendations(persona_weights: dict, budget: int = None,
                             csv_path: str = "phones.csv", top_n: int = 3) -> pd.DataFrame:
    """
    Full pipeline: load engineered data -> filter by budget -> score with
    WSM -> rank -> attach reasons -> return Top N.

    Returns a DataFrame sorted by match_score descending, limited to top_n
    rows, with an added 'reason' column and 'rank' column.
    """
    df = load_engineered_phones(csv_path)
    df, within_budget = apply_budget_filter(df, budget)
    df = compute_wsm_scores(df, persona_weights)

    ranked = _rank_pool(df, budget, within_budget)
    top = ranked.head(top_n).copy()
    top["_min_price_in_results"] = top["price_inr"].min()
    top["rank"] = range(1, len(top) + 1)
    top["reason"] = top.apply(
        lambda r: _generate_reason(r, persona_weights, r["rank"],
                                   budget=budget, within_budget=within_budget),
        axis=1)

    return top.drop(columns=["_min_price_in_results"])


def get_full_ranking(persona_weights: dict, budget: int = None,
                      csv_path: str = "phones.csv") -> pd.DataFrame:
    """Return the entire catalog ranked by match score (used for 'see all results')."""
    df = load_engineered_phones(csv_path)
    df, within_budget = apply_budget_filter(df, budget)
    df = compute_wsm_scores(df, persona_weights)
    ranked = _rank_pool(df, budget, within_budget)
    ranked["rank"] = range(1, len(ranked) + 1)
    return ranked


def generate_budget_change_reasons(previous: dict, new: dict) -> list:
    """
    USP: Budget Simulator support.

    Given the previously recommended phone and the newly recommended phone
    (both plain dicts containing the existing camera_score, performance_score,
    battery_score, value_score, match_score and price_inr fields produced by
    the WSM pipeline above), build a list of short, dynamic explanations for
    why the recommendation changed after the budget was adjusted.

    Uses only existing score/spec fields already computed by the recommender
    -- no hardcoded phone names, prices or canned reason text.
    """
    if not previous or not new:
        return []

    dims = [
        ("camera_score", "📸 Camera"),
        ("performance_score", "⚡ Performance"),
        ("battery_score", "🔋 Battery"),
        ("display_score", "🖥️ Display"),
    ]

    reasons = []
    for score_key, label in dims:
        prev_val = previous.get(score_key)
        new_val = new.get(score_key)
        if prev_val is None or new_val is None:
            continue
        diff = round(new_val - prev_val, 1)
        if diff >= 0.3:
            reasons.append(f"{label} improved ({prev_val:.1f} → {new_val:.1f})")
        elif diff <= -0.3:
            reasons.append(f"{label} is lower ({prev_val:.1f} → {new_val:.1f})")

    prev_price = previous.get("price_inr")
    new_price = new.get("price_inr")
    if prev_price is not None and new_price is not None and prev_price != new_price:
        price_diff = new_price - prev_price
        direction = "more expensive" if price_diff > 0 else "cheaper"
        reasons.append(f"💸 ₹{abs(price_diff):,} {direction} than your previous match")

    if not reasons:
        reasons.append("Overall match score is higher for your adjusted budget.")

    return reasons


if __name__ == "__main__":
    from personas import PERSONAS

    for pid, persona in PERSONAS.items():
        print(f"\n=== {persona['name']} (budget ~₹{persona['default_budget']:,}) ===")
        top3 = get_top_recommendations(persona["weights"], persona["default_budget"])
        for _, row in top3.iterrows():
            print(f"  #{row['rank']} {row['model']:20s} match={row['match_score']}%  "
                  f"₹{row['price_inr']:,}")
            print(f"      {row['reason']}")