"""
recommender.py — STAGE 2 of the recommendation pipeline
======================================================
Ranks the catalog for one user. Implements a Weighted Sum Model (WSM):

    match_score = ( camera*w_camera + performance*w_performance
                  + battery*w_battery + display*w_display ) * 10

where each dimension score comes from feature_engineering.py on a 0-10 scale
and the weights come from the user's persona / quiz answers / sliders and sum
to 1.0. The weighted total is therefore also 0-10; the single `* 10` is the one
place a score becomes the 0-100 "match %" the UI shows.

Order of operations (all four steps are deliberate and testable):
    1. FILTER     budget is a hard constraint      -> apply_budget_filter()
    2. SCORE      weighted sum of the 4 dimensions -> compute_wsm_scores()
    3. RANK       deterministic sort + tie-break   -> _rank_pool()
    4. EXPLAIN    prose derived from those scores  -> _generate_reason()

Why value_score is deliberately not ranked
------------------------------------------
feature_engineering also derives a value_score, and this module's docstring used
to claim the formula was "Camera*w1 + Performance*w2 + Battery*w3 + Value*w4".
It never was — the code has always multiplied display_score, and zeroing
value_score changes no ranking. Ranking on value as well would double-count:
value is *itself* computed from camera + performance + battery, so those specs
would be counted once directly and again through value. The four ranked
dimensions are also exactly the four sliders the UI exposes, so persona weights,
the UI, and this formula stay in one-to-one agreement. value_score remains a
derived, informational metric (Community Insights).
"""

import numpy as np
import pandas as pd

from feature_engineering import RANKED_DIMENSIONS, SCORE_MAX, load_engineered_phones

# Column holding each ranked dimension's score, keyed by weight name. Derived
# from RANKED_DIMENSIONS so the engine cannot drift from the scorer.
DIMENSION_COLUMNS = {dim: f"{dim}_score" for dim in RANKED_DIMENSIONS}

# match_score is the weighted 0-10 total expressed as a percentage.
MATCH_SCORE_MAX = 100.0
_MATCH_SCALE = MATCH_SCORE_MAX / SCORE_MAX      # == 10.0

# Applied when two phones tie on match_score, in order. Without an explicit
# tie-break, pandas' default quicksort is unstable and equal scores came back in
# a different order run to run (verified: 5 shuffled inputs -> 5 orderings).
# Cheaper wins first (better value at an equal match), then phone_id purely so
# the result is reproducible.
TIE_BREAK_COLUMNS = ["price_inr", "phone_id"]

# ----------------------------------------------------------------------
# Budget band
# ----------------------------------------------------------------------
# A budget is a TARGET, not just a ceiling. Someone who says "₹60,000" is
# telling us two things: don't go over, and this is roughly what I mean to
# spend. Ranking the whole under-budget pool on match score alone ignored the
# second half — a ₹25,999 phone with a great battery beat every ₹59,999 phone
# for a ₹60,000 battery-focused user, i.e. we answered a ₹60k question with a
# phone using 43% of the budget.
#
# So the Top 3 is drawn from a BAND: phones priced between
# BUDGET_BAND_FLOOR x budget and the budget itself. Inside that band the
# persona's weights alone decide the order, which keeps match_score honest —
# it stays a pure "how well does this suit you" number that the score bars
# fully explain, rather than a blend of fit and price that no bar could show.
#
# The band widens automatically when it is too narrow to fill (see
# _narrow_to_budget_band), so a sparse price range can never leave the user
# with nothing.
BUDGET_BAND_FLOOR = 0.75          # consider phones from 75% of budget upward
MIN_BAND_CANDIDATES = 3           # widen until at least a Top 3 is available
BAND_WIDENING_STEPS = (0.75, 0.60, 0.45, 0.30, 0.0)


def normalize_weights(weights: dict) -> dict:
    """
    Purpose : Guarantee the WSM's core precondition — weights summing to 1.0.
    Inputs  : weights dict keyed by RANKED_DIMENSIONS (values need not be
              normalised; the UI sliders post raw 0-100 numbers).
    Output  : A new dict over the same keys summing to 1.0.
    Algorithm: Divide each weight by the total. A non-positive total (e.g. every
              slider dragged to zero) falls back to an equal split rather than
              dividing by zero.

    This matters because match_score is only a true 0-100 percentage while the
    weights sum to 1; unnormalised weights would silently rescale every score.
    """
    values = {dim: max(0.0, float(weights.get(dim, 0.0))) for dim in RANKED_DIMENSIONS}
    total = sum(values.values())
    if total <= 0:
        return {dim: 1.0 / len(RANKED_DIMENSIONS) for dim in RANKED_DIMENSIONS}
    return {dim: value / total for dim, value in values.items()}


def compute_wsm_scores(df: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """
    Purpose : STEP 2 — score every phone against one user's priorities.
    Inputs  : df carrying the four *_score columns (0-10) from
              feature_engineering; weights keyed by RANKED_DIMENSIONS.
    Output  : Copy of df with `wsm_raw` (0-10) and `match_score` (0-100) added.
    Algorithm: match = Σ(dimension_score × weight) — a Weighted Sum Model.
              Because each score is 0-10 and the weights sum to 1, the total is
              also 0-10; multiplying by 10 once yields the 0-100 match %.

    Every ranked dimension is read from DIMENSION_COLUMNS, so a dimension can
    never be silently skipped or counted twice.
    """
    out = df.copy()
    weights = normalize_weights(weights)

    weighted_total = sum(
        out[column] * weights[dim] for dim, column in DIMENSION_COLUMNS.items()
    )

    out["wsm_raw"] = weighted_total                                   # 0-10
    out["match_score"] = np.round(weighted_total * _MATCH_SCALE, 1)   # 0-100
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


def _narrow_to_budget_band(df: pd.DataFrame, budget: int) -> pd.DataFrame:
    """
    Purpose : Shortlist the phones that actually answer the user's budget.
    Inputs  : df already filtered to price <= budget; the budget.
    Output  : The subset inside the budget band (never empty).
    Algorithm: Keep phones priced >= floor x budget, trying each floor in
              BAND_WIDENING_STEPS from tightest to loosest and stopping as soon
              as MIN_BAND_CANDIDATES phones qualify. The final 0.0 step is the
              whole under-budget pool, so this always returns something.

    Worked example — budget ₹60,000:
        floor 0.75 -> ₹45,000..₹60,000 -> the three ₹59,999 FE models -> stop.
        The ₹25,999 F56 is excluded not because it is a bad phone, but because
        it does not answer the question the user asked.
    """
    if not budget or budget <= 0 or df.empty:
        return df

    for floor in BAND_WIDENING_STEPS:
        band = df[df["price_inr"] >= budget * floor]
        if len(band) >= MIN_BAND_CANDIDATES:
            return band
    return df


def _rank_pool(df: pd.DataFrame, budget: int, within_budget: bool) -> pd.DataFrame:
    """
    Purpose : STEP 3 — put a scored pool into final, reproducible order.
    Inputs  : scored df; the user's budget; whether anything fits it.
    Output  : df sorted best-first with a clean 0..n-1 index.
    Algorithm:
        within budget      -> match_score DESC, then TIE_BREAK_COLUMNS
        nothing fits budget-> price distance ASC, then match_score DESC, then
                              TIE_BREAK_COLUMNS

    Two properties this guarantees:
      * DETERMINISM. Sorting on match_score alone was unstable — pandas defaults
        to quicksort, so tied phones came back in a different order run to run
        (verified: 5 shuffled inputs produced 5 different orderings). Appending
        TIE_BREAK_COLUMNS makes the order a total ordering, and `kind=stable`
        removes any remaining dependence on input order.
      * BUDGET HONESTY. When nothing fits, nearness to budget outranks match, so
        the #1 pick is the closest phone the user could actually buy rather than
        the best-scoring expensive one. (This case previously returned the five
        cheapest phones ranked by score, which answered a ₹13,000 budget with a
        ₹26,999 phone.)
    """
    out = df.copy()

    if within_budget:
        sort_columns = ["match_score"] + TIE_BREAK_COLUMNS
        ascending = [False] + [True] * len(TIE_BREAK_COLUMNS)
    else:
        out["_price_gap"] = (out["price_inr"] - budget).abs()
        sort_columns = ["_price_gap", "match_score"] + TIE_BREAK_COLUMNS
        ascending = [True, False] + [True] * len(TIE_BREAK_COLUMNS)

    ranked = out.sort_values(sort_columns, ascending=ascending,
                             kind="stable").reset_index(drop=True)
    return ranked.drop(columns=["_price_gap"], errors="ignore")


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
    Purpose : The full pipeline for one user — the function the app calls.
    Inputs  : persona_weights (keyed by RANKED_DIMENSIONS), budget in INR,
              catalog path, how many results to return.
    Output  : DataFrame of the Top N, best first, with `rank`, `match_score`
              and a generated `reason` per row.
    Algorithm:
        1. LOAD    catalog + engineered scores      (feature_engineering)
        2. FILTER  drop anything over budget        (apply_budget_filter)
        3. BAND    shortlist phones that actually   (_narrow_to_budget_band)
                   answer the stated budget
        4. SCORE   weighted sum of 4 dimensions     (compute_wsm_scores)
        5. RANK    deterministic order + tie-break  (_rank_pool)
        6. EXPLAIN prose from those same scores     (_generate_reason)

    The band only applies when a budget fits something; when nothing fits, the
    pool stays whole and _rank_pool switches to nearest-price so the user is
    still offered the closest phone they could buy.
    """
    df = load_engineered_phones(csv_path)
    df, within_budget = apply_budget_filter(df, budget)
    if within_budget:
        df = _narrow_to_budget_band(df, budget)
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