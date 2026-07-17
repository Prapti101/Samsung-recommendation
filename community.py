"""
community.py
------------
"Community Insights" — the validation step of the recommendation journey. It
builds two things for the phone the recommender already picked:

  1. a snapshot of the phone's strengths / trade-offs / bottom line, and
  2. dynamic search links to trusted external sources (Reddit, GSMArena,
     AnTuTu, Amazon, Flipkart, Samsung).

Scope and honesty note (important)
----------------------------------
This module has NO access to live community data: no Reddit threads, no review
aggregates, no benchmark database, no LLM. It therefore does NOT claim to report
what real people said. The snapshot is derived deterministically from data the
results page already has — the engineered 0-10 scores (feature_engineering.py)
and the phone's raw specs — and is worded as "what to weigh", never as "users
say". The Trusted Sources links are what let a reader go and check real
community opinion for themselves; that is the point of the section.

If a real reviews/benchmark dataset (or an LLM summariser) is wired up later,
replace `build_snapshot()` only — the route and template consume the same shape.

Like ecosystem.py, this is presentation-only: nothing here feeds back into the
WSM ranking in recommender.py.

Future-proofing
---------------
Every source URL is generated from the phone's brand + model string via a search
endpoint, so a new Galaxy added to phones.csv works with zero code changes. No
per-phone links are hardcoded anywhere.
"""

import json
from urllib.parse import quote_plus

import groq_client

# A dimension is "a strength" at or above this score, "a trade-off" at or below
# the weak threshold. Camera / performance / battery / display are scored on
# absolute anchors (see feature_engineering.py), so these thresholds are
# meaningful on their own; value_score is comparative across the catalog.
_STRONG = 7.5
_WEAK = 5.5

# Raw-spec flags that reviewers and buyers reliably care about, independent of
# the score model.
_HEAVY_G = 215
_SLOW_CHARGE_W = 30


def _full_name(phone: dict) -> str:
    """'Samsung Galaxy S25' — the string every external search is built from."""
    brand = (phone.get("brand") or "").strip()
    model = (phone.get("model") or "").strip()
    return "{} {}".format(brand, model).strip() if brand not in model else model


# ----------------------------------------------------------------------
# 1. Snapshot — derived from the phone's own scores + specs.
# ----------------------------------------------------------------------
def _dimensions(p: dict) -> list:
    """
    Every scored dimension with the wording to use if it turns out to be one of
    the phone's strengths or one of its trade-offs. Text stays tied to the
    number that produced it, so a bullet can always be traced back to the data.
    """
    return [
        {
            "key": "camera",
            "score": p["camera_score"],
            "strength": "Camera hardware is a highlight — {}MP main sensor "
                        "({}/10 on our camera score).".format(
                            p["main_camera_mp"], round(p["camera_score"], 1)),
            "tradeoff": "Camera is the softest spec here — {}MP main sensor "
                        "({}/10). Worth checking sample shots in the reviews "
                        "below.".format(
                            p["main_camera_mp"], round(p["camera_score"], 1)),
        },
        {
            "key": "performance",
            "score": p["performance_score"],
            "strength": "Performance holds up — {} ({}/10), comfortable for "
                        "gaming and heavy multitasking.".format(
                            p["processor"], round(p["performance_score"], 1)),
            "tradeoff": "Performance is mid-tier — {} ({}/10). Fine for daily "
                        "use, less so for sustained gaming.".format(
                            p["processor"], round(p["performance_score"], 1)),
        },
        {
            "key": "battery",
            "score": p["battery_score"],
            "strength": "Battery is dependable — {:,}mAh with {}W charging "
                        "({}/10).".format(
                            p["battery_mah"], p["charging_w"],
                            round(p["battery_score"], 1)),
            "tradeoff": "Battery and charging lag the class — {:,}mAh at {}W "
                        "({}/10).".format(
                            p["battery_mah"], p["charging_w"],
                            round(p["battery_score"], 1)),
        },
        {
            "key": "display",
            "score": p["display_score"],
            "strength": "Display is excellent — {}\" {} at {}Hz ({}/10).".format(
                p["display_inch"], p["display_type"], p["refresh_rate_hz"],
                round(p["display_score"], 1)),
            "tradeoff": "Display is basic for the price — {}\" {} at {}Hz "
                        "({}/10).".format(
                            p["display_inch"], p["display_type"],
                            p["refresh_rate_hz"], round(p["display_score"], 1)),
        },
        {
            "key": "value",
            "score": p["value_score"],
            "strength": "Strong value — {}/10 on specs-per-rupee against the "
                        "rest of the lineup.".format(round(p["value_score"], 1)),
            "tradeoff": "Value is the trade-off — {}/10 on specs-per-rupee; "
                        "you pay a premium for the badge.".format(
                            round(p["value_score"], 1)),
        },
    ]


def _spec_tradeoffs(p: dict) -> list:
    """Raw-spec caveats that don't come out of the score model."""
    out = []
    weight = p.get("weight_g")
    if weight and weight >= _HEAVY_G:
        out.append("It's a heavy phone at {}g — handle one before you commit."
                   .format(weight))
    if p.get("charging_w", 999) <= _SLOW_CHARGE_W:
        out.append("{}W charging is slow by current standards — expect a longer "
                   "top-up than rivals.".format(p["charging_w"]))
    return out


def _bottom_line(p: dict, strengths: list, tradeoffs: list) -> str:
    """One closing line, driven by the value score and the overall spec spread."""
    dims = _dimensions(p)
    avg = sum(d["score"] for d in dims) / len(dims)
    value = p["value_score"]
    name = p["model"]

    if value >= _STRONG and avg >= 7.0:
        return ("Overall: {} is a well-rounded pick that also prices well — the "
                "sources below should mostly confirm it.".format(name))
    if value >= _STRONG:
        return ("Overall: {} wins on price-to-spec rather than on any single "
                "headline feature.".format(name))
    if avg >= 7.5:
        return ("Overall: {} is a strong all-rounder, but you are paying for it "
                "— weigh the trade-offs above against your budget.".format(name))
    if tradeoffs:
        return ("Overall: {} fits your priorities, though the trade-offs above "
                "are the ones to check against real owner reports."
                .format(name))
    return ("Overall: {} matches what you asked for — use the sources below to "
            "confirm before buying.".format(name))


def build_snapshot(phone: dict) -> dict:
    """
    3-5 bullets: up to 2 strengths, up to 2 trade-offs, and 1 bottom line.
    At least one strength and one trade-off always appear (falling back to the
    best / worst dimension), so the card is never lopsided or empty.
    """
    dims = _dimensions(phone)
    ranked = sorted(dims, key=lambda d: d["score"], reverse=True)

    strengths = [d["strength"] for d in ranked if d["score"] >= _STRONG][:2]
    if not strengths:
        strengths = [ranked[0]["strength"]]          # best available dimension

    weak = [d["tradeoff"] for d in reversed(ranked) if d["score"] <= _WEAK]
    tradeoffs = (weak + _spec_tradeoffs(phone))[:2]
    if not tradeoffs:
        tradeoffs = [ranked[-1]["tradeoff"]]         # weakest dimension

    return {
        "strengths": strengths,
        "tradeoffs": tradeoffs,
        "bottom_line": _bottom_line(phone, strengths, tradeoffs),
    }


# ----------------------------------------------------------------------
# 2. Trusted sources — every URL generated from the model name.
# ----------------------------------------------------------------------
def build_sources(phone: dict) -> list:
    """
    Search links for the recommended phone. Each entry is generated from the
    model string, so any Galaxy added to phones.csv works automatically.
    """
    name = _full_name(phone)          # "Samsung Galaxy S25"
    model = phone.get("model", "")    # "Galaxy S25"
    q = quote_plus(name)

    return [
        {
            "key": "reddit",
            "icon": "bi-chat-dots",
            "label": "Reddit Discussions",
            "meta": "reddit.com",
            "blurb": "Unfiltered owner threads — the day-to-day gripes and wins.",
            "url": "https://www.reddit.com/search/?q={}&sort=relevance".format(q),
        },
        {
            "key": "gsmarena",
            "icon": "bi-newspaper",
            "label": "GSMArena Review",
            "meta": "gsmarena.com",
            "blurb": "Full expert review, lab tests and the complete spec sheet.",
            "url": "https://www.gsmarena.com/res.php3?sSearch={}".format(
                quote_plus(model)),
        },
        {
            "key": "antutu",
            "icon": "bi-speedometer2",
            "label": "AnTuTu Benchmark",
            "meta": "antutu.com",
            "blurb": "Live performance rankings to sanity-check the chipset.",
            # AnTuTu's own site, not a Google search for it.
            #
            # This link is the one card that cannot be phone-specific: antutu.com
            # has no site search at all (no form, no search endpoint — the
            # /search.htm?q= URL returns 200 but ignores the query and never
            # mentions the phone). So it opens their live performance ranking,
            # which is the page that actually answers "how fast is this chipset".
            "url": "https://www.antutu.com/web/ranking",
        },
        {
            "key": "amazon",
            "icon": "bi-star",
            "label": "Amazon Reviews",
            "meta": "amazon.in",
            "blurb": "Verified-buyer ratings and long-term ownership notes.",
            "url": "https://www.amazon.in/s?k={}".format(q),
        },
        {
            "key": "flipkart",
            "icon": "bi-bag-check",
            "label": "Flipkart Reviews",
            "meta": "flipkart.com",
            "blurb": "Indian pricing, offers and a second pool of buyer reviews.",
            "url": "https://www.flipkart.com/search?q={}".format(q),
        },
        {
            "key": "samsung",
            "icon": "bi-globe2",
            "label": "Samsung Official",
            "meta": "samsung.com/in",
            "blurb": "Official specs, colours, variants and current offers.",
            "url": "https://www.samsung.com/in/search/?searchvalue={}".format(q),
        },
    ]


# ----------------------------------------------------------------------
# 3. AI snapshot (Groq) — runs AFTER the WSM has already chosen the phone
# ----------------------------------------------------------------------
_AI_SYSTEM_PROMPT = """\
You are a smartphone analyst writing a short buyer's briefing for one Samsung \
Galaxy phone.

You will be given that phone's REAL specifications and its computed 0-10 scores. \
Base every statement only on those numbers. You have no access to reviews, \
forums or sales data, so never claim what "users say", never invent a rating, a \
quote, a review count or a benchmark figure, and never mention a spec you were \
not given.

Reply with a single JSON object, exactly this shape:
{
  "strengths":   ["...", "..."],   // 2 items: what this phone does well
  "tradeoffs":   ["...", "..."],   // 1-2 items: what a buyer should weigh
  "bottom_line": "..."             // 1 sentence verdict
}

Rules for the text:
- Every bullet must cite the actual figure behind it (e.g. "200MP main sensor",
  "5000mAh", "45W", the exact chipset name).
- Judge against the phone's price: a 50MP camera is good at Rs 15,000 and
  unremarkable at Rs 1,50,000.
- One sentence per bullet, plain English, no marketing language, no emoji.
- If a dimension scores low, say so plainly rather than softening it.\
"""


def _ai_prompt(phone: dict) -> str:
    """The phone's real specs and scores, as the only facts the model may use."""
    return json.dumps({
        "model": _full_name(phone),
        "price_inr": phone["price_inr"],
        "release_year": phone.get("release_year"),
        "category": phone.get("category"),
        "specs": {
            "processor": phone["processor"],
            "ram_gb": phone["ram_gb"],
            "storage_gb": phone["storage_gb"],
            "battery_mah": phone["battery_mah"],
            "charging_w": phone["charging_w"],
            "main_camera_mp": phone["main_camera_mp"],
            "ultra_wide_mp": phone["ultra_wide_mp"],
            "telephoto_mp": phone["telephoto_mp"],
            "front_camera_mp": phone["front_camera_mp"],
            "display_inch": phone["display_inch"],
            "display_type": phone["display_type"],
            "refresh_rate_hz": phone["refresh_rate_hz"],
        },
        "computed_scores_out_of_10": {
            "camera": phone["camera_score"],
            "performance": phone["performance_score"],
            "battery": phone["battery_score"],
            "display": phone["display_score"],
            "value_for_money": phone["value_score"],
            "ai_and_software_longevity": phone.get("ai_longevity_score"),
        },
    }, indent=2)


def _clean_lines(value, limit: int) -> list:
    """Keep only non-empty strings, trimmed, capped at `limit` — the model's
    output is untrusted input as far as the template is concerned."""
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        if len(out) == limit:
            break
    return out


def build_ai_snapshot(phone: dict):
    """
    Purpose : Ask Groq to write the snapshot from this phone's real data.
    Inputs  : a scored phone dict (post-WSM).
    Output  : {"strengths": [...], "tradeoffs": [...], "bottom_line": "..."}
              or None if Groq is unconfigured, unreachable, or replies with
              anything unusable — the caller then falls back to build_snapshot().
    Algorithm: Send specs + computed scores as JSON, require a JSON object back,
              then validate its shape before it is allowed near the template.

    This runs only AFTER the Weighted Sum Model has chosen the phone. It does
    not score, rank or influence the recommendation in any way.
    """
    if not groq_client.is_configured():
        return None

    data = groq_client.complete_json(_AI_SYSTEM_PROMPT, _ai_prompt(phone))
    if not isinstance(data, dict):
        return None

    strengths = _clean_lines(data.get("strengths"), 2)
    tradeoffs = _clean_lines(data.get("tradeoffs"), 2)
    bottom_line = data.get("bottom_line")
    bottom_line = bottom_line.strip() if isinstance(bottom_line, str) else ""

    # A half-empty answer is worse than the deterministic one, so reject it.
    if not strengths or not tradeoffs or not bottom_line:
        return None

    return {"strengths": strengths, "tradeoffs": tradeoffs,
            "bottom_line": bottom_line}


# Groq costs a network round trip, and the same phone is re-rendered on every
# reload, back-navigation and persona tweak. Cache per phone so a demo doesn't
# pay the latency (or the rate limit) twice.
_ai_cache = {}


def get_community_insights(phone: dict) -> dict:
    """
    Entry point used by the /recommend route. Returns None when there is no
    recommendation to talk about, so the template can skip the whole section.

    Snapshot source, in order:
      1. Groq, from this phone's real specs + scores   (build_ai_snapshot)
      2. the deterministic local writer                (build_snapshot)
    The fallback means a missing key, a rate limit, or no internet degrades the
    wording — never the page.
    """
    if not phone:
        return None

    phone_id = phone.get("phone_id")
    if phone_id in _ai_cache:
        snapshot, ai_generated = _ai_cache[phone_id]
    else:
        snapshot = build_ai_snapshot(phone)
        ai_generated = snapshot is not None
        if not ai_generated:
            snapshot = build_snapshot(phone)
        if phone_id is not None:
            _ai_cache[phone_id] = (snapshot, ai_generated)

    return {
        "model": phone.get("model", ""),
        "full_name": _full_name(phone),
        "snapshot": snapshot,
        # Lets the UI describe honestly where the words came from.
        "ai_generated": ai_generated,
        "sources": build_sources(phone),
    }
