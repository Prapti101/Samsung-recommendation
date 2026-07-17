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

# How many budget steps the stepper offers, and how big each one is as a share
# of the current pick's price.
#
# These used to be fixed at ₹2,000…₹10,000, which broke once recommender.py
# started picking from a budget band. The band puts the #1 pick at the TOP of
# the user's budget, and price gaps up there are large — from a ₹59,999 phone
# the next model up is ₹74,999, a ₹15,000 jump. Every fixed step topped out at
# ₹10,000, so no tier could reach anything and the whole section disappeared.
#
# Scaling with price keeps the steps meaningful at both ends: ~₹1,500 increments
# for a ₹26,000 phone, ~₹3,000 for a ₹60,000 one, ~₹5,000 for a ₹1,00,000 one.
UPGRADE_STEP_COUNT = 5
UPGRADE_STEP_FRACTION = 0.05      # one step ≈ 5% of the current price


def upgrade_steps_for(price: int) -> tuple:
    """
    Purpose : Budget increments to offer for a phone at this price.
    Inputs  : price of the current #1 pick, in INR.
    Output  : Ascending tuple of rupee amounts.
    Algorithm: One step is ~5% of the price, rounded to a friendly increment
              (₹500 below ₹2,000, otherwise ₹1,000) so the UI shows "+₹3,000"
              rather than "+₹2,999.95". Steps are multiples of that unit.
    """
    raw = price * UPGRADE_STEP_FRACTION
    rounding = 500 if raw < 2000 else 1000
    unit = max(rounding, int(round(raw / rounding) * rounding))
    return tuple(unit * n for n in range(1, UPGRADE_STEP_COUNT + 1))


# Kept for callers that want the historic fixed ladder (and for tests).
UPGRADE_STEPS_INR = (2000, 4000, 6000, 8000, 10000)

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
        steps = upgrade_steps_for(current["price_inr"])

    # Each rung of the stepper must be a DIFFERENT phone, otherwise clicking "+"
    # changes the rupee label while the suggestion underneath stays put — which
    # reads as broken. Walking the improving phones cheapest-first and taking
    # each new one gives a real ladder: the smallest worthwhile step, then the
    # next distinct option, and so on.
    improving = [
        phone for phone in sorted(catalog, key=lambda p: (p["price_inr"], p["phone_id"]))
        if phone["price_inr"] > current["price_inr"] and describe_gains(current, phone)
    ]

    tiers = []
    seen_ids = set()
    for phone in improving:
        if phone["phone_id"] in seen_ids:
            continue
        seen_ids.add(phone["phone_id"])
        tiers.append({
            # The exact extra rupees this phone costs — the real gap, which is
            # what the user actually has to find, not a rounded step.
            "delta": phone["price_inr"] - current["price_inr"],
            "price_delta": phone["price_inr"] - current["price_inr"],
            "new_budget": phone["price_inr"],
            "available": True,
            "pick": phone,
            "features": feature_list_fn(phone),
            "gains": describe_gains(current, phone),
            "explore_url": phone["official_url"],
        })
        if len(tiers) >= len(steps):
            break

    # The stepper still expects a fixed number of rungs; pad the tail when the
    # catalog runs out of better phones so the UI can grey those out.
    while len(tiers) < len(steps):
        tiers.append({"delta": steps[len(tiers)], "new_budget": None, "available": False})

    return {
        "current": current,
        "current_explore_url": current["official_url"],
        "tiers": tiers,
        "has_any": any(tier["available"] for tier in tiers),
    }
