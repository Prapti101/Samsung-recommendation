
"""
app.py
------
Flask application entry point for the Samsung Galaxy Mobile Recommendation
Assistant.

Routes:
    GET  /                -> Home page (persona / text input / budget / priorities)
    POST /recommend       -> Runs the WSM recommender, shows Top 3 results
    GET  /compare          -> Compare-two-phones page
    GET  /wishlist         -> Saved wishlist page (localStorage-backed)
    GET  /history          -> Recommendation history page (localStorage-backed)
    GET  /api/phones       -> JSON list of all phones (used by the compare UI)
    GET  /api/persona-match -> JSON: infer persona + budget from free text (AJAX)
"""

import json
import os
import urllib.error
import urllib.request
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template, request, jsonify
import pandas as pd

from feature_engineering import load_engineered_phones
from personas import PERSONAS, PERSONA_ORDER, list_personas, match_persona_from_text, get_persona
from recommender import get_top_recommendations, get_full_ranking

app = Flask(__name__)

CSV_PATH = "phones.csv"

# ----------------------------------------------------------------------
# AI-powered multilingual support (Gemini API)
# ----------------------------------------------------------------------
# The Gemini API key is read from an environment variable / config only --
# it must never be hardcoded. Set GEMINI_API_KEY in your environment
# (see .env.example) before running the app.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

# Supported UI languages (code -> display name used in the Gemini prompt).
SUPPORTED_LANGUAGES = {
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "or": "Odia",
    "ur": "Urdu",
}


def _translate_with_gemini(texts, target_lang_name):
    """
    Call the Gemini API to translate a list of UI strings into the target
    language. Returns a list of translated strings (same length/order as
    `texts`) on success, or None if Gemini is unavailable / the call fails
    for any reason -- callers should fall back to English in that case.
    """
    if not GEMINI_API_KEY or not texts:
        return None

    prompt = (
        "You are translating user-interface text for a phone recommendation "
        f"web app into {target_lang_name}. Translate every string in the "
        "JSON array below into natural, concise UI-appropriate "
        f"{target_lang_name}. Keep numbers, currency symbols, units, and "
        "brand/model names unchanged unless there is a natural, widely "
        "understood localized form. Respond with ONLY a JSON array of "
        "translated strings, the same length and in the same order as the "
        "input array -- no extra keys, no commentary.\n\n"
        + json.dumps(texts, ensure_ascii=False)
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        },
    }

    req = urllib.request.Request(
        f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        translations = json.loads(text)
        if isinstance(translations, list) and len(translations) == len(texts):
            return [str(t) for t in translations]
        return None
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError,
            ValueError, json.JSONDecodeError):
        return None


def _phone_to_dict(row: pd.Series) -> dict:
    """Convert a phone row (with engineered scores) into a JSON/template-friendly dict."""
    return {
        "phone_id": int(row["phone_id"]),
        "model": row["model"],
        "brand": row["brand"],
        "release_year": int(row["release_year"]),
        "price_inr": int(row["price_inr"]),
        "ram_gb": int(row["ram_gb"]),
        "storage_gb": int(row["storage_gb"]),
        "battery_mah": int(row["battery_mah"]),
        "charging_w": int(row["charging_w"]),
        "main_camera_mp": int(row["main_camera_mp"]),
        "ultra_wide_mp": int(row["ultra_wide_mp"]),
        "telephoto_mp": int(row["telephoto_mp"]),
        "front_camera_mp": int(row["front_camera_mp"]),
        "processor": row["processor"],
        "display_inch": float(row["display_inch"]),
        "refresh_rate_hz": int(row["refresh_rate_hz"]),
        "display_type": row["display_type"],
        "weight_g": int(row["weight_g"]),
        "category": row["category"],
        "camera_score": float(row["camera_score"]),
        "performance_score": float(row["performance_score"]),
        "battery_score": float(row["battery_score"]),
        "value_score": float(row["value_score"]),
        "match_score": float(row["match_score"]) if "match_score" in row else None,
        "rank": int(row["rank"]) if "rank" in row else None,
        "reason": row["reason"] if "reason" in row else None,
    }


@app.route("/")
def home():
    """Home page: persona selection, free-text input, budget slider, priorities."""
    df = load_engineered_phones(CSV_PATH)
    min_price = int(df["price_inr"].min())
    max_price = int(df["price_inr"].max())
    return render_template(
        "index.html",
        personas=list_personas(),
        min_price=min_price,
        max_price=max_price,
    )


@app.route("/recommend", methods=["POST"])
def recommend():
    """
    Handle the recommendation form submission. Supports two input modes:
      1. Persona dropdown selection (persona_id present in form)
      2. Free-text description (user_text present, non-empty)
    Optional manual priority sliders can override/blend persona weights.
    """
    persona_id = request.form.get("persona_id", "").strip()
    user_text = request.form.get("user_text", "").strip()
    budget_raw = request.form.get("budget", "").strip()

    inferred_note = None

    if user_text:
        # Free-text mode: infer persona + budget from description
        match = match_persona_from_text(user_text)
        persona = match["persona"]
        budget = match["budget"] or (int(budget_raw) if budget_raw else persona["default_budget"])
        inferred_note = (f"Based on your description, we matched you to the "
                          f"\"{persona['name']}\" profile "
                          f"(confidence: {int(match['confidence'] * 100)}%).")
    elif persona_id:
        persona = get_persona(persona_id)
        budget = int(budget_raw) if budget_raw else persona["default_budget"]
    else:
        persona = PERSONAS["business_allrounder"]
        budget = int(budget_raw) if budget_raw else persona["default_budget"]

    weights = dict(persona["weights"])

    # Optional custom priority sliders (camera/performance/battery/value 0-100),
    # sent from the "Fine-tune priorities" panel on the home page. If present
    # and they sum to > 0, they override the persona's default weights.
    custom_weight_keys = ["w_camera", "w_performance", "w_battery", "w_value"]
    if all(request.form.get(k) not in (None, "") for k in custom_weight_keys):
        raw_vals = {k: float(request.form.get(k, 0)) for k in custom_weight_keys}
        total = sum(raw_vals.values())
        if total > 0:
            weights = {
                "camera": raw_vals["w_camera"] / total,
                "performance": raw_vals["w_performance"] / total,
                "battery": raw_vals["w_battery"] / total,
                "value": raw_vals["w_value"] / total,
            }

    top3 = get_top_recommendations(weights, budget, csv_path=CSV_PATH, top_n=3)
    full_ranking = get_full_ranking(weights, budget, csv_path=CSV_PATH)

    top3_dicts = [_phone_to_dict(row) for _, row in top3.iterrows()]
    full_dicts = [_phone_to_dict(row) for _, row in full_ranking.iterrows()]

    weight_pct = {k: round(v * 100) for k, v in weights.items()}

    return render_template(
        "results.html",
        persona=persona,
        budget=budget,
        weights=weight_pct,
        top3=top3_dicts,
        full_ranking=full_dicts,
        inferred_note=inferred_note,
        all_phones_json=full_dicts,  # for the compare widget on this page
        history_payload={
            "source_type": "description" if user_text else "persona",
            "source_label": user_text if user_text else persona["name"],
            "budget": budget,
            "weights": weight_pct,
            "top3": top3_dicts,
        },
    )


@app.route("/compare")
def compare_page():
    """Standalone compare-two-phones page."""
    df = load_engineered_phones(CSV_PATH)
    phones = [_phone_to_dict(row) for _, row in df.iterrows()]

    phone_a_id = request.args.get("a", type=int)
    phone_b_id = request.args.get("b", type=int)

    phone_a = next((p for p in phones if p["phone_id"] == phone_a_id), None)
    phone_b = next((p for p in phones if p["phone_id"] == phone_b_id), None)

    return render_template(
        "compare.html",
        phones=phones,
        phone_a=phone_a,
        phone_b=phone_b,
    )


@app.route("/wishlist")
def wishlist_page():
    """Wishlist page shell; saved phones are read from localStorage by the browser."""
    df = load_engineered_phones(CSV_PATH)
    phones = [_phone_to_dict(row) for _, row in df.iterrows()]
    return render_template("wishlist.html", phones=phones)


@app.route("/history")
def history_page():
    """Recommendation history page shell; entries are read from localStorage by the browser."""
    return render_template("history.html")


@app.route("/api/phones")
def api_phones():
    """JSON list of all phones with engineered scores (used by JS compare widget)."""
    df = load_engineered_phones(CSV_PATH)
    return jsonify([_phone_to_dict(row) for _, row in df.iterrows()])


@app.route("/api/persona-match", methods=["POST"])
def api_persona_match():
    """AJAX endpoint: live-preview which persona a free-text description matches."""
    text = request.json.get("text", "") if request.is_json else request.form.get("text", "")
    if not text or len(text.strip()) < 8:
        return jsonify({"matched": False})

    match = match_persona_from_text(text)
    return jsonify({
        "matched": True,
        "persona_id": match["persona"]["id"],
        "persona_name": match["persona"]["name"],
        "emoji": match["persona"]["emoji"],
        "budget": match["budget"],
        "confidence": match["confidence"],
    })


@app.route("/api/translate", methods=["POST"])
def api_translate():
    """
    AJAX endpoint used by the language switcher: translates a batch of
    UI strings into `target_lang` using the Gemini API. Translations are
    generated dynamically -- no hardcoded translation dictionaries are
    used or stored server-side. If Gemini is unavailable/misconfigured,
    responds with translations: None so the client falls back to English.
    """
    data = request.get_json(silent=True) or {}
    texts = data.get("texts")
    target_lang = (data.get("target_lang") or "").strip()

    if not texts or not isinstance(texts, list):
        return jsonify({"translations": []})

    lang_name = SUPPORTED_LANGUAGES.get(target_lang)
    if not lang_name:
        return jsonify({"translations": None, "error": "unsupported_language"}), 400

    translations = _translate_with_gemini(texts, lang_name)
    if translations is None:
        return jsonify({"translations": None, "error": "translation_unavailable"}), 503

    return jsonify({"translations": translations})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)