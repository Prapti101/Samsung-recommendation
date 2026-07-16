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

SCORE_COLS = ["camera_score", "performance_score", "battery_score", "value_score"]
WEIGHT_KEYS = ["camera", "performance", "battery", "value"]


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
        out["value_score"] * weights["value"]
    )
    # raw_score is out of 10 (since each component is 0-10 and weights sum to 1)
    out["wsm_raw"] = raw_score
    out["match_score"] = np.round(raw_score * 10, 1)  # convert to 0-100 for UI
    return out


def apply_budget_filter(df: pd.DataFrame, budget: int, tolerance: float = 0.15) -> pd.DataFrame:
    """
    Filter phones to those within budget, allowing a small tolerance
    above the stated budget (people often stretch a little for the
    right phone) so we don't return an empty result set for tight budgets.
    Falls back to the full catalog sorted by price if nothing qualifies.
    """
    if not budget or budget <= 0:
        return df

    ceiling = budget * (1 + tolerance)
    filtered = df[df["price_inr"] <= ceiling]

    if filtered.empty:
        # Nothing fits even with tolerance -- return the cheapest phones instead
        # of an empty page, so the user still gets useful recommendations.
        return df.nsmallest(5, "price_inr")

    return filtered


def _generate_reason(row: pd.Series, weights: dict, rank: int) -> str:
    """
    Build a dynamic, plain-English explanation for why this phone was
    recommended, based on which of its scores are strongest *and* most
    heavily weighted for the active persona.
    """
    # Rank each score dimension by (score * weight) contribution
    contributions = {
        "camera": row["camera_score"] * weights["camera"],
        "performance": row["performance_score"] * weights["performance"],
        "battery": row["battery_score"] * weights["battery"],
        "value": row["value_score"] * weights["value"],
    }
    top_dims = sorted(contributions, key=contributions.get, reverse=True)

    phrase_bank = {
        "camera": f"a standout {row['main_camera_mp']}MP camera system",
        "performance": f"top-tier performance from its {row['processor']} chipset",
        "battery": f"a strong {row['battery_mah']}mAh battery with {row['charging_w']}W charging",
        "value": "excellent value for what you're paying",
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
    df = apply_budget_filter(df, budget)
    df = compute_wsm_scores(df, persona_weights)

    ranked = df.sort_values("match_score", ascending=False).reset_index(drop=True)
    top = ranked.head(top_n).copy()
    top["_min_price_in_results"] = top["price_inr"].min()
    top["rank"] = range(1, len(top) + 1)
    top["reason"] = top.apply(lambda r: _generate_reason(r, persona_weights, r["rank"]), axis=1)

    return top.drop(columns=["_min_price_in_results"])


def get_full_ranking(persona_weights: dict, budget: int = None,
                      csv_path: str = "phones.csv") -> pd.DataFrame:
    """Return the entire catalog ranked by match score (used for 'see all results')."""
    df = load_engineered_phones(csv_path)
    df = apply_budget_filter(df, budget)
    df = compute_wsm_scores(df, persona_weights)
    ranked = df.sort_values("match_score", ascending=False).reset_index(drop=True)
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
        ("value_score", "💰 Value"),
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