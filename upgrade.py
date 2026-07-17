"""
upgrade.py — "Smarter Upgrade" / budget optimizer
=================================================
Answers one question: "if I stretched my budget by ₹X, what would I get?"

Pipeline context: this runs AFTER recommender.py has produced a #1 pick. It does
NOT re-rank, re-score or re-implement any part of the engine — it reads the same
`*_score` columns feature_engineering already computed, so an upgrade's claimed
benefit can never disagree with the score bars shown next to it.

    recommender.py  -> #1 pick + full ranked catalog
      -> [THIS MODULE] for each budget step, the nearest phone above the pick
      -> spec-by-spec gains derived from the pick's real scores

Selection rule (audit fix)
--------------------------
For each step the tier offers the NEAREST higher-priced phone within reach, not
the best-scoring one. The route previously indexed `candidates[0]` of a
match-ranked pool, so "+₹2,000" could surface whichever phone in that window
happened to score best — a more expensive jump than the user asked to consider.
"Nearest above current" is what makes the suggestion a genuine next step.
"""

# The budget increments the stepper walks, in rupees above the current pick.
#
# The ladder runs to ₹15,000 rather than stopping at ₹10,000 because of a real
# gap in Samsung's price list: above ₹40,000 the catalog jumps in large strides
# (₹59,999 -> ₹74,999 -> ₹94,999). With a ₹10,000 ceiling, a ₹59,999 pick could
# not reach ANY better phone, so every tier came back empty and the whole
# section vanished — for 30 of 48 budget/persona combinations.
#
# Steps that still reach nothing are no longer dropped: they are kept and
# labelled (see UPGRADE_NO_MATCH_TEMPLATE), because "nothing better for +₹2,000"
# is itself a useful, honest answer — and far better than the section silently
# disappearing.
UPGRADE_STEPS_INR = (2000, 4000, 6000, 8000, 10000, 15000)

# Shown on a step that unlocks nothing better.
UPGRADE_NO_MATCH_TEMPLATE = "No better Galaxy for +₹{delta:,} — your pick is the best at this price."

# A dimension score must improve by at least this much (0-10 scale) before it is
# worth telling the user about. Below this the difference is noise, not a reason
# to spend money.
MIN_SCORE_GAIN = 0.3


def find_nearest_upgrade(current: dict, catalog: list, max_price: int):
    """
    Purpose : Find the cheapest phone above `current` that is genuinely better.
    Inputs  : current  — the #1 pick (dict with price_inr)
              catalog  — every scored phone (list of dicts, any order)
              max_price— the highest price this tier allows
    Output  : The nearest *improving* higher-priced phone, or None.
    Algorithm: Walk candidates priced (current, max_price] from cheapest upward
              and return the first that improves on at least one dimension.
              phone_id breaks exact-price ties so the walk is deterministic.

    Why "nearest that improves" and not simply "nearest": the catalog contains
    near-duplicate phones. The M56 costs ₹1,000 more than the F56 and scores
    *identically* on all four dimensions — so a plain nearest-price rule locked
    every tier onto it and offered the user nothing for their money. Skipping
    non-improving neighbours keeps the "smallest sensible step up" promise while
    guaranteeing the step is worth paying for.
    """
    reachable = sorted(
        (phone for phone in catalog
         if current["price_inr"] < phone["price_inr"] <= max_price),
        key=lambda p: (p["price_inr"], p["phone_id"]),
    )
    for candidate in reachable:
        if describe_gains(current, candidate):
            return candidate
    return None


def describe_gains(current: dict, pick: dict) -> list:
    """
    Purpose : Explain, concretely, what the extra money buys.
    Inputs  : current and pick — two scored phone dicts.
    Output  : List of short strings, strongest improvement first. Empty if the
              pick is not actually better in any dimension.
    Algorithm: Compare the two phones dimension by dimension. Each entry is
              gated on the *computed score* improving by MIN_SCORE_GAIN, and its
              wording quotes the *raw spec* behind that score — so the claim and
              the evidence always come from the same data the bars are drawn
              from. Nothing here is hardcoded per phone.
    """
    gains = []

    def gained(dimension):
        return pick.get(f"{dimension}_score", 0) - current.get(f"{dimension}_score", 0)

    # (score gain, text) — collected then sorted so the biggest win leads.
    candidates = []

    if gained("camera") >= MIN_SCORE_GAIN:
        candidates.append((gained("camera"), "Better camera — {}MP main sensor vs {}MP".format(
            pick["main_camera_mp"], current["main_camera_mp"])))

    if gained("performance") >= MIN_SCORE_GAIN:
        candidates.append((gained("performance"), "Faster processor — {} vs {}".format(
            pick["processor"], current["processor"])))

    if gained("battery") >= MIN_SCORE_GAIN:
        candidates.append((gained("battery"), "Longer battery — {:,}mAh · {}W vs {:,}mAh · {}W".format(
            pick["battery_mah"], pick["charging_w"],
            current["battery_mah"], current["charging_w"])))

    if gained("display") >= MIN_SCORE_GAIN:
        candidates.append((gained("display"), "Better display — {}\" {} at {}Hz".format(
            pick["display_inch"], pick["display_type"], pick["refresh_rate_hz"])))

    # AI + software longevity: a real scored dimension (ai_longevity.py), not a
    # marketing line. Only mentioned when it genuinely improves.
    ai_gain = pick.get("ai_longevity_score", 0) - current.get("ai_longevity_score", 0)
    if ai_gain >= MIN_SCORE_GAIN:
        candidates.append((ai_gain, "Stronger Galaxy AI & longer software support"))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    gains = [text for _, text in candidates]

    # Value is comparative, so it is reported last and only as a footnote.
    if pick.get("value_score", 0) > current.get("value_score", 0):
        gains.append("Better overall value for money")

    return gains


def build_upgrade_tiers(current: dict, catalog: list, feature_list_fn,
                        steps=None) -> dict:
    """
    Purpose : Build the whole "Smarter Upgrade" payload for the results page.
    Inputs  : current        — the #1 pick
              catalog        — every scored phone (dicts)
              feature_list_fn— callable(phone) -> headline spec list (injected so
                               this module stays independent of app.py)
              steps          — budget increments; defaults to steps scaled to
                               the pick's price (see upgrade_steps_for)
    Output  : dict of {current, current_explore_url, tiers[], has_any} — the
              exact shape results.html already renders.
    Algorithm: For each step, take the nearest phone above the current price
              within (price + step); describe the gains; report the exact rupee
              difference. Steps that unlock nothing are marked unavailable so the
              UI can grey them out rather than inventing a suggestion.

    A tier is only "available" when the pick is genuinely better in at least one
    dimension — paying more for nothing is not an upgrade.
    """
    if steps is None:
        steps = UPGRADE_STEPS_INR

    tiers = []
    for step in steps:
        ceiling = current["price_inr"] + step
        pick = find_nearest_upgrade(current, catalog, ceiling)

        if pick:
            tiers.append({
                "delta": step,
                "new_budget": ceiling,
                "available": True,
                "pick": pick,
                # The exact extra rupees this phone costs — the real gap the
                # user must find, not the round step they clicked.
                "price_delta": pick["price_inr"] - current["price_inr"],
                "features": feature_list_fn(pick),
                "gains": describe_gains(current, pick),
                "explore_url": pick["official_url"],
            })
        else:
            # Kept, not dropped: the step is a real question ("what does
            # +₹2,000 buy me?") and "nothing better" is a real answer.
            tiers.append({
                "delta": step,
                "new_budget": ceiling,
                "available": False,
                "message": UPGRADE_NO_MATCH_TEMPLATE.format(delta=step),
            })

    return {
        "current": current,
        "current_explore_url": current["official_url"],
        "tiers": tiers,
        # True when at least one step unlocks something — the section still
        # hides for the single most expensive phone, where every step would
        # otherwise repeat "nothing better".
        "has_any": any(tier["available"] for tier in tiers),
    }
