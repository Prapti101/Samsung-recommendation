"""
describe.py — understanding "Describe It" free text
===================================================
Turns whatever the user types into the four inputs the Weighted Sum Model
already takes: camera / performance / battery / display weights, plus a budget.

    "I shoot a lot of night photos, around 50k"
        -> weights {camera .55, performance .2, battery .15, display .10}
        -> budget 50000

Where this sits in the pipeline:

    free text -> [THIS MODULE] -> weights + budget -> recommender.py (unchanged)

It does NOT score, rank or recommend. It only decides what the user asked for.
The Weighted Sum Model, personas, budget filtering and ranking are untouched.

Why an LLM here
---------------
The previous matcher counted keywords, which fails the moment someone writes a
normal sentence. It scored 7 of 8 test phrases, and its miss was instructive:
"amazing camera, budget 40000" matched *Student*, because "budget" is a Student
keyword and ties broke on dictionary order. It also had no notion of intent — it
could not tell "I don't care about the camera" from "I care about the camera".

Refusing out-of-scope requests
------------------------------
The catalog is Samsung Galaxy phones only. Asked for an iPhone, a laptop, or
anything we do not stock, the model must say so rather than quietly returning
the closest Galaxy — recommending an S24 to someone who asked for an iPhone is
the exact failure this section is meant to avoid. `supported: false` carries a
plain-English reason to show the user.

Fallback
--------
If Groq is unconfigured, down, or replies with junk, this returns None and the
caller uses the original keyword matcher. The feature degrades; it never breaks.
"""

import json

import groq_client
from feature_engineering import RANKED_DIMENSIONS

_SYSTEM_PROMPT = """\
You read a shopper's description and decide what they want in a phone.

This service recommends SAMSUNG GALAXY smartphones only, from a catalog priced
₹8,699 to ₹1,64,999.

Reply with a single JSON object, exactly this shape:
{
  "supported": true | false,
  "refusal": "",                  // filled ONLY when supported is false
  "budget_inr": 45000 | null,     // a number ONLY if they state or imply one
  "weights": {                    // how much each matters, 0-100, must total 100
    "camera": 40, "performance": 25, "battery": 20, "display": 15
  },
  "summary": "..."                // one short sentence: what you understood
}

Set "supported": false when the request cannot be served, for example:
- a non-Samsung phone (iPhone, Pixel, OnePlus, Xiaomi, ...)
- a non-phone product (laptop, tablet, watch, earbuds)
- something the catalog cannot express (a phone under ₹5,000)
- the text is gibberish or unrelated to buying a phone
Then write "refusal" as one friendly sentence saying what we cannot do and what
we can. Example: "We only recommend Samsung Galaxy phones, so an iPhone isn't
something I can match you with — tell me what matters to you and I'll find a
Galaxy that fits."

When supported is true:
- Weight the four dimensions by what they actually said. Reading between the
  lines is fine ("I game a lot" -> performance and display high, "photos of my
  kids" -> camera high, "always travelling" -> battery high).
- Respect negatives: "I don't care about the camera" means camera LOW.
- Nothing stated at all -> a balanced 25/25/25/25.
- budget_inr: only if stated or clearly implied ("35k" -> 35000, "1 lakh" ->
  100000, "cheap" -> null, not a guess). Use null when unsure.
- Never invent a phone name, price or spec. You only output weights and a budget.\
"""


def _normalise_weights(raw) -> dict:
    """
    Coerce the model's weights into the four dimensions the WSM expects, summing
    to 1.0. Anything missing or non-numeric falls back to an equal share, so a
    sloppy reply can never produce a lopsided or zero-sum ranking.
    """
    if not isinstance(raw, dict):
        return None
    values = {}
    for dimension in RANKED_DIMENSIONS:
        try:
            values[dimension] = max(0.0, float(raw.get(dimension, 0)))
        except (TypeError, ValueError):
            values[dimension] = 0.0
    total = sum(values.values())
    if total <= 0:
        return None
    return {dim: value / total for dim, value in values.items()}


def interpret(text: str):
    """
    Purpose : Turn free text into WSM inputs, or a refusal.
    Inputs  : text — whatever the user typed.
    Output  : dict, or None when Groq is unavailable / unusable:
              {"supported": True,  "weights": {...}, "budget": int|None,
               "summary": str}
              {"supported": False, "refusal": str}
    Algorithm: One Groq call with a JSON-only contract, then every field is
              validated before it can reach the engine — the model's output is
              untrusted input.
    """
    text = (text or "").strip()
    if not text or not groq_client.is_configured():
        return None

    data = groq_client.complete_json(_SYSTEM_PROMPT, text, temperature=0.2,
                                     max_tokens=400)
    if not isinstance(data, dict):
        return None

    # Out-of-scope request: pass the reason through, with a safe default.
    if data.get("supported") is False:
        refusal = data.get("refusal")
        if not isinstance(refusal, str) or not refusal.strip():
            refusal = ("We only recommend Samsung Galaxy phones. Tell me what "
                       "matters to you and I'll find one that fits.")
        return {"supported": False, "refusal": refusal.strip()}

    weights = _normalise_weights(data.get("weights"))
    if not weights:
        return None

    # Budget: accept only a sane number; the catalog tops out at ₹1,64,999.
    budget = data.get("budget_inr")
    try:
        budget = int(budget) if budget is not None else None
    except (TypeError, ValueError):
        budget = None
    if budget is not None and not (1000 <= budget <= 1000000):
        budget = None

    summary = data.get("summary")
    summary = summary.strip() if isinstance(summary, str) else ""

    return {"supported": True, "weights": weights, "budget": budget,
            "summary": summary}
