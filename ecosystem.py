"""
ecosystem.py
-------------
"Complete Your Galaxy Experience" — a small, modular, data-driven engine that
suggests complementary Galaxy devices (Buds, Watch, SmartTag2) to pair with the
phone the recommendation flow already produced.

It does NOT recompute or influence the phone recommendation (recommender.py /
the WSM). It only reads signals the results page already has:
  * the recommended phone's `category` (flagship / foldable / midrange / budget)
    and `price_inr` (price segment), and
  * the run's WSM `weights` (camera / performance / battery / value) which encode
    the persona / quiz / custom-slider intent.

From those it (a) orders the three ecosystem products by relevance, (b) picks a
per-product "tier variant" (flagship / balanced / value) so different users see
different products/emphasis, and (c) writes a dynamic, non-repetitive
"why it pairs well" line referencing the actual recommended phone.

Future-proofing: each product is a dict with image/url/name/tags fields. Today
they hold placeholders; when a real dataset arrives, populate `image`, `url`,
`variants[...].name` etc. and the UI renders them with NO template changes.
"""


# ----------------------------------------------------------------------
# Product catalog. Each product has tier "variants" so the same card can
# present a flagship / balanced / value edition depending on the phone.
# `image` and `url` are placeholders today, structured for real data later.
# ----------------------------------------------------------------------
PRODUCTS = {
    "buds": {
        "id": "buds",
        "key_priority": "camera",   # creators/students/business lean on audio
        "icon": "🎧",
        "tag": "Perfect Audio Companion",
        "image": "",   # future: real product image URL
        "url": "",     # future: dedicated Samsung product page
        "variants": {
            "flagship": {
                "name": "Galaxy Buds3 Pro",
                "desc": "Studio-grade sound with intelligent ANC and 360 Audio for a truly immersive listen.",
            },
            "balanced": {
                "name": "Galaxy Buds3",
                "desc": "Crisp, balanced audio and clear calls in a light, all-day-comfortable design.",
            },
            "value": {
                "name": "Galaxy Buds FE",
                "desc": "Rich sound and active noise cancelling that punch well above their price.",
            },
        },
    },
    "watch": {
        "id": "watch",
        "key_priority": "battery",  # fitness/health & endurance users
        "icon": "⌚",
        "tag": "Stay Connected",
        "image": "",
        "url": "",
        "variants": {
            "flagship": {
                "name": "Galaxy Watch Ultra",
                "desc": "Rugged titanium build with advanced health sensors and multi-day endurance.",
            },
            "balanced": {
                "name": "Galaxy Watch7",
                "desc": "Comprehensive health tracking, notifications and fitness insights on your wrist.",
            },
            "value": {
                "name": "Galaxy Watch FE",
                "desc": "Essential health and fitness tracking that syncs effortlessly with your phone.",
            },
        },
    },
    "smarttag": {
        "id": "smarttag",
        "key_priority": "value",    # everyday tracking, great value add-on
        "icon": "📍",
        "tag": "Never Lose What Matters",
        "image": "",
        "url": "",
        "variants": {
            # SmartTag2 doesn't tier by price much; keep one edition across tiers.
            "flagship": {
                "name": "Galaxy SmartTag2",
                "desc": "Precision finding for keys, bags and valuables with long battery life.",
            },
            "balanced": {
                "name": "Galaxy SmartTag2",
                "desc": "Track keys, luggage and everyday essentials with SmartThings Find.",
            },
            "value": {
                "name": "Galaxy SmartTag2",
                "desc": "An affordable way to keep tabs on the things you can't afford to lose.",
            },
        },
    },
}


# Map the recommended phone's category to a product tier + a human label.
_CATEGORY_TIER = {
    "flagship": ("flagship", "flagship"),
    "foldable": ("flagship", "flagship"),
    "midrange": ("balanced", "mid-range"),
    "budget":   ("value", "budget"),
}


def _price_segment(price_inr):
    """Coarse price segment used to nudge tiering when category is missing."""
    if price_inr is None:
        return "balanced"
    if price_inr >= 90000:
        return "flagship"
    if price_inr >= 30000:
        return "balanced"
    return "value"


def _dominant_priority(weights):
    """Return the highest-weighted WSM dimension (camera/performance/battery/
    value), which encodes the user's persona/quiz intent."""
    if not weights:
        return "value"
    return max(("camera", "performance", "battery", "value"),
               key=lambda k: weights.get(k, 0))


# Relevance boosts: how strongly each user-intent favours each product.
# (Higher = shown earlier.) Modular — tweak here without touching the UI.
_INTENT_BOOST = {
    "camera":      {"buds": 3, "watch": 2, "smarttag": 1},   # creators: audio + wearable
    "performance": {"buds": 3, "watch": 1, "smarttag": 2},   # gamers: audio latency, tracking gear
    "battery":     {"watch": 3, "buds": 1, "smarttag": 2},   # endurance/fitness: watch first
    "value":       {"buds": 2, "smarttag": 3, "watch": 1},   # value/students: buds + affordable tag
}


def _pairing_reason(product_id, phone, intent):
    """Dynamic, non-repetitive 'why it pairs well' copy referencing the actual
    recommended phone and the user's dominant intent."""
    model = phone.get("model", "your Galaxy phone") if phone else "your Galaxy phone"

    if product_id == "buds":
        if intent == "camera":
            return (f"Capture the moment, then hear it come alive — Galaxy Buds pair "
                    f"instantly with your {model} for immersive playback and crystal-clear calls.")
        if intent == "performance":
            return (f"Low-latency audio keeps you in sync during gaming and video on your "
                    f"{model}, with seamless auto-switching across your devices.")
        if intent == "battery":
            return (f"All-day audio to match your {model}'s endurance, with quick, "
                    f"clear calls whenever you need them.")
        return (f"Seamless auto-switching, immersive sound and clear calls make them the "
                f"perfect everyday companion for your {model}.")

    if product_id == "watch":
        if intent == "battery":
            return (f"Track workouts, sleep and heart rate all day — the watch's endurance "
                    f"is a natural match for your {model}, syncing health insights effortlessly.")
        if intent == "performance":
            return (f"Glanceable notifications and quick controls keep you moving without "
                    f"reaching for your {model} mid-session.")
        if intent == "camera":
            return (f"Frame the perfect shot with a remote viewfinder on your wrist, and get "
                    f"health and notification sync with your {model}.")
        return (f"Health tracking, notifications and fitness insights that sync effortlessly "
                f"with your {model}, right from your wrist.")

    # smarttag
    if intent == "value":
        return (f"An affordable, essential add-on: locate keys, bags and everyday items with "
                f"SmartThings Find directly from your {model}.")
    return (f"Keep track of luggage, keys and valuables on the go — find them in seconds with "
            f"SmartThings Find on your {model}.")


def get_ecosystem_recommendations(phone, weights=None):
    """
    Build the ordered list of ecosystem product cards for the given recommended
    phone + run weights. Returns a list of plain dicts ready for the template.

    Never raises on missing fields; falls back to sensible defaults so the
    section always renders.
    """
    phone = phone or {}
    category = str(phone.get("category", "")).lower()
    tier, tier_label = _CATEGORY_TIER.get(category, (None, None))
    if tier is None:
        tier = _price_segment(phone.get("price_inr"))
        tier_label = {"flagship": "flagship", "balanced": "mid-range",
                      "value": "budget"}.get(tier, "your")

    intent = _dominant_priority(weights or {})
    boosts = _INTENT_BOOST.get(intent, _INTENT_BOOST["value"])

    cards = []
    for pid, product in PRODUCTS.items():
        variant = product["variants"].get(tier) or product["variants"]["balanced"]
        cards.append({
            "id": pid,
            "icon": product["icon"],
            "tag": product["tag"],
            "name": variant["name"],
            "description": variant["desc"],
            "pairing_reason": _pairing_reason(pid, phone, intent),
            "tier": tier,
            "tier_label": tier_label,
            "image": product.get("image", ""),   # placeholder-ready
            "url": product.get("url", ""),        # placeholder-ready
            "_score": boosts.get(pid, 0),
        })

    # Highest relevance first; stable for equal scores.
    cards.sort(key=lambda c: c["_score"], reverse=True)
    for c in cards:
        c.pop("_score", None)
    return cards


if __name__ == "__main__":
    demo_phone = {"model": "Galaxy S25 Ultra", "category": "flagship", "price_inr": 134999}
    for intent_w in [
        {"camera": 0.5, "performance": 0.2, "battery": 0.15, "value": 0.15},
        {"battery": 0.5, "performance": 0.2, "camera": 0.15, "value": 0.15},
        {"value": 0.5, "battery": 0.25, "performance": 0.15, "camera": 0.1},
    ]:
        recs = get_ecosystem_recommendations(demo_phone, intent_w)
        print("intent:", max(intent_w, key=intent_w.get),
              "->", [c["name"] for c in recs])