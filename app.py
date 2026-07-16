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

from flask import Flask, render_template, request, jsonify, session, url_for
import pandas as pd
import os
import re
import glob

from feature_engineering import load_engineered_phones
from personas import PERSONAS, PERSONA_ORDER, list_personas, match_persona_from_text, get_persona
from recommender import get_top_recommendations, get_full_ranking, generate_budget_change_reasons
from ai_longevity import compute_ai_longevity
from ecosystem import get_ecosystem_recommendations
from community import get_community_insights

app = Flask(__name__)
# Secret key enables server-side session storage (used to remember the last
# recommendation inputs so the "Recommend" tab can redisplay results on GET).
app.secret_key = "galaxy-match-local-dev-key"

CSV_PATH = "phones.csv"

# ----------------------------------------------------------------------
# Phone image resolution
# ----------------------------------------------------------------------
# The phone images live in static/img as .webp files (e.g. "s25_ultra.webp").
# The CSV has no image column, and model names ("Galaxy S25 Ultra") do not
# literally equal the filenames ("s25_ultra"), so we resolve them robustly:
#   1. an explicit override by phone_id or model (for edge cases with no
#      dedicated asset), then
#   2. a normalization of the model name that is matched, case-insensitively,
#      against the actual files present on disk.
# Resolution happens once at startup (filenames are scanned into a set) and the
# result is cached, so it adds no per-request cost. If nothing matches, the
# template simply omits the <img> (no broken placeholder).

IMAGE_DIR = os.path.join(app.static_folder, "img")

# Fallback images for models whose own file is missing OR corrupt. Keys may be
# a model name (str) or a phone_id (int); values are filenames in static/img.
# These are only used when the model's correctly-named valid image is absent, so
# re-downloading a proper "s24_ultra.webp"/"m55.webp" will automatically win.
IMAGE_OVERRIDES = {
    "Galaxy S25 Edge": "s25.webp",   # no dedicated Edge render; use the S25 image
    "Galaxy S24 Ultra": "s24.webp",  # shipped s24_ultra.webp was corrupt; same-gen fallback
    "Galaxy M55 5G": "m56.webp",     # shipped m55.webp was corrupt; closest M-series fallback
}


def _is_valid_image(path: str) -> bool:
    """
    True only if the file is a real, decodable image. Some downloaded files
    can be corrupt or an HTML/JS page saved with an image extension; those
    return 200 from Flask but render as a broken icon in the browser. We detect
    them by their magic bytes so they are never served.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return False
    # WEBP: "RIFF"...."WEBP" | PNG | JPEG | GIF
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return True
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if head[:3] == b"\xff\xd8\xff":            # JPEG
        return True
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return True
    return False


def _available_images() -> dict:
    """Map lowercase filename (without extension) -> actual filename on disk,
    including ONLY files that are genuinely valid images."""
    mapping = {}
    for path in glob.glob(os.path.join(IMAGE_DIR, "*")):
        fname = os.path.basename(path)
        stem, ext = os.path.splitext(fname)
        if ext.lower() in (".webp", ".png", ".jpg", ".jpeg") and _is_valid_image(path):
            mapping[stem.lower()] = fname
    return mapping


# Scanned once at import; safe because the image folder is static.
_IMAGE_INDEX = _available_images()
_IMAGE_CACHE = {}


def _normalize_model(model: str) -> str:
    """
    Turn a model name into a filename stem candidate, e.g.:
        "Galaxy S25 Ultra" -> "s25_ultra"
        "Galaxy S24+"       -> "s24_plus"
        "Galaxy Z Fold6"    -> "z_fold6"
        "Galaxy A55 5G"     -> "a55"
    """
    s = str(model).lower().strip()
    s = s.replace("galaxy", "")
    s = s.replace("+", " plus ")
    s = re.sub(r"\b5g\b", "", s)                # drop the "5G" suffix
    s = re.sub(r"[^a-z0-9]+", "_", s)           # non-alphanumerics -> underscore
    return re.sub(r"_+", "_", s).strip("_")


def _resolve_image_filename(phone_id, model: str):
    """Return the best-matching image filename in static/img, or None."""
    cache_key = (phone_id, model)
    if cache_key in _IMAGE_CACHE:
        return _IMAGE_CACHE[cache_key]

    result = None

    # 1. Correctly-named valid image on disk (from the validated index).
    base = _normalize_model(model)
    for cand in (base, base.replace("_", ""), base.replace("plus", "_plus")):
        if cand in _IMAGE_INDEX:
            result = _IMAGE_INDEX[cand]
            break

    # 2. Fallback override (by phone_id, then exact model) — used only when the
    #    model has no valid correctly-named file (missing or corrupt).
    if result is None:
        override = IMAGE_OVERRIDES.get(phone_id) or IMAGE_OVERRIDES.get(model)
        if override and os.path.splitext(override)[0].lower() in _IMAGE_INDEX:
            result = _IMAGE_INDEX[os.path.splitext(override)[0].lower()]

    _IMAGE_CACHE[cache_key] = result
    return result


def _phone_image_url(phone_id, model: str):
    """Return a url_for('static', ...) URL for the phone image, or None."""
    fname = _resolve_image_filename(phone_id, model)
    if not fname:
        return None
    return url_for("static", filename="img/" + fname)


def _samsung_explore_url(model: str) -> str:
    """
    Build a Samsung India link for a model. We use the site search endpoint
    (rather than guessing exact product slugs) so the link always resolves to
    the right phone on samsung.com.
    """
    from urllib.parse import quote_plus
    return "https://www.samsung.com/in/search/?searchvalue=" + quote_plus(model)


def _phone_feature_list(p: dict) -> list:
    """Five headline specs for a phone, used in the Smarter Upgrade card."""
    return [
        {"icon": "camera",   "label": "{}MP main camera".format(p["main_camera_mp"])},
        {"icon": "cpu",      "label": p["processor"]},
        {"icon": "battery",  "label": "{:,}mAh · {}W charging".format(p["battery_mah"], p["charging_w"])},
        {"icon": "display",  "label": "{}\" · {}Hz display".format(p["display_inch"], p["refresh_rate_hz"])},
        {"icon": "memory",   "label": "{}GB RAM · {}GB storage".format(p["ram_gb"], p["storage_gb"])},
    ]


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
        "image": _phone_image_url(int(row["phone_id"]), row["model"]),
        "camera_score": float(row["camera_score"]),
        "performance_score": float(row["performance_score"]),
        "battery_score": float(row["battery_score"]),
        "value_score": float(row["value_score"]),
        "display_score": float(row["display_score"]),
        # AI & Longevity is a visual-only, radar-chart dimension computed by a
        # separate scorer (ai_longevity.py). It does NOT affect the WSM ranking.
        "ai_longevity_score": compute_ai_longevity(row),
        "match_score": float(row["match_score"]) if "match_score" in row else None,
        "rank": int(row["rank"]) if "rank" in row else None,
        "reason": row["reason"] if "reason" in row else None,
    }


@app.route("/")
def home():
    """Home page: persona selection, free-text input, budget slider, priorities."""
    df = load_engineered_phones(CSV_PATH)
    # Budget slider bounds: fixed range ₹8,000 – ₹2,00,000 (per product spec).
    min_price = 8000
    max_price = 200000
    return render_template(
        "index.html",
        personas=list_personas(),
        min_price=min_price,
        max_price=max_price,
    )


@app.route("/quiz")
def quiz():
    """Smart Discovery Quiz: a conversational, scenario-based path to a
    recommendation. The quiz itself is client-side; on completion it POSTs
    weights + budget to the existing /recommend route (source=quiz)."""
    return render_template("quiz.html")


@app.route("/recommend", methods=["GET", "POST"])
def recommend():
    """
    Handle the recommendation form submission. Supports two input modes:
      1. Persona dropdown selection (persona_id present in form)
      2. Free-text description (user_text present, non-empty)
    Optional manual priority sliders can override/blend persona weights.

    Works as a navigable "Recommend" tab too: on POST the submitted inputs are
    saved to the session; a GET replays the last inputs (re-running the same
    engine) so the tab keeps showing the latest recommendation. A GET with no
    prior recommendation shows a centered empty state.
    """
    if request.method == "POST":
        form = request.form
        # Remember the raw inputs so the "Recommend" tab can redisplay results.
        session["last_reco"] = {
            "persona_id": form.get("persona_id", ""),
            "user_text": form.get("user_text", ""),
            "budget": form.get("budget", ""),
            "source": form.get("source", ""),
            "w_camera": form.get("w_camera", ""),
            "w_performance": form.get("w_performance", ""),
            "w_battery": form.get("w_battery", ""),
            "w_display": form.get("w_display", form.get("w_value", "")),
            "priorities_touched": form.get("priorities_touched", ""),
        }
    else:
        form = session.get("last_reco")
        if not form:
            # No recommendation yet — show a friendly, centered empty state.
            return render_template("results.html", empty_recommend=True)

    persona_id = form.get("persona_id", "").strip()
    user_text = form.get("user_text", "").strip()
    budget_raw = form.get("budget", "").strip()
    source = form.get("source", "").strip()

    inferred_note = None

    if source == "quiz":
        # Smart Discovery Quiz mode: the quiz already translated the user's
        # answers into custom weights + a budget (handled by the shared
        # custom-weight block below). We use a friendly, quiz-branded label
        # instead of a persona, and let the weights speak for themselves.
        persona = {
            "id": "quiz",
            "name": "Your Quiz Match",
            "emoji": "\u2728",
            "default_budget": 60000,
            "weights": {"camera": 0.25, "performance": 0.25, "battery": 0.25, "display": 0.25},
        }
        budget = int(budget_raw) if budget_raw else persona["default_budget"]
        inferred_note = ("Built from your quiz answers \u2014 your priorities were "
                         "translated into the weighting below.")
    elif user_text:
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
        persona = PERSONAS["business_professional"]
        budget = int(budget_raw) if budget_raw else persona["default_budget"]

    weights = dict(persona["weights"])

    # Optional custom priority sliders (camera/performance/battery/display 0-100),
    # from the "Fine-tune priorities" panel. These are ALWAYS present in the form
    # (they have default values), so we must only let them override the persona's
    # weights when the user actually dragged a slider (priorities_touched == "1")
    # or when the request came from the quiz (which supplies real weights).
    # Otherwise every persona/description would collapse to the same 25/25/25/25
    # weighting and return identical recommendations.
    priorities_touched = form.get("priorities_touched", "").strip() == "1"
    if source == "quiz" or priorities_touched:
        # Home page posts w_display; the quiz posts w_value — accept either.
        raw_vals = {
            "camera": form.get("w_camera", ""),
            "performance": form.get("w_performance", ""),
            "battery": form.get("w_battery", ""),
            "display": form.get("w_display", form.get("w_value", "")),
        }
        if all(v not in (None, "") for v in raw_vals.values()):
            nums = {k: float(v) for k, v in raw_vals.items()}
            total = sum(nums.values())
            if total > 0:
                weights = {k: nums[k] / total for k in nums}

    top3 = get_top_recommendations(weights, budget, csv_path=CSV_PATH, top_n=3)
    full_ranking = get_full_ranking(weights, budget, csv_path=CSV_PATH)

    top3_dicts = [_phone_to_dict(row) for _, row in top3.iterrows()]
    full_dicts = [_phone_to_dict(row) for _, row in full_ranking.iterrows()]

    weight_pct = {k: round(v * 100) for k, v in weights.items()}

    # Bounds for the Budget Simulator slider (USP), derived from the whole
    # catalog so the user can explore both cheaper and pricier options.
    catalog_df = load_engineered_phones(CSV_PATH)
    sim_min_budget = int(catalog_df["price_inr"].min())
    sim_max_budget = int(catalog_df["price_inr"].max())

    # "Complete Your Galaxy Experience": modular ecosystem suggestions derived
    # from the already-computed top pick + run weights. No extra recommendation
    # computation; reuses existing data only.
    ecosystem = get_ecosystem_recommendations(
        top3_dicts[0] if top3_dicts else None, weights)

    # "Community Insights": spec-derived snapshot + dynamic links to trusted
    # external sources for the #1 pick. Presentation-only; see community.py.
    community = get_community_insights(top3_dicts[0] if top3_dicts else None)

    # ------------------------------------------------------------------
    # "Smarter Upgrade" (presentation-only, complements the Budget Simulator).
    # Reuses the EXISTING WSM engine: rank the whole catalog (budget=None) with
    # the same weights, then, for each small budget increase (+₹2k … +₹10k),
    # surface the best-scoring phone the extra money unlocks (priced above the
    # current #1, within the raised budget). No new scoring logic; the feature
    # list and improvement bullets are derived from existing spec fields.
    # ------------------------------------------------------------------
    upgrade = None
    if top3_dicts:
        current = top3_dicts[0]
        full_pool = get_full_ranking(weights, budget=None, csv_path=CSV_PATH)
        pool_dicts = [_phone_to_dict(row) for _, row in full_pool.iterrows()]
        # pool_dicts is already ranked by match_score (best first).

        def compute_gains(cur, pick):
            g = []
            if pick["main_camera_mp"] > cur["main_camera_mp"]:
                g.append("Better camera — {}MP vs {}MP main sensor".format(
                    pick["main_camera_mp"], cur["main_camera_mp"]))
            if pick["performance_score"] > cur["performance_score"]:
                g.append("Faster processor — {}".format(pick["processor"]))
            if pick["battery_mah"] > cur["battery_mah"]:
                g.append("Longer battery life — {:,}mAh vs {:,}mAh".format(
                    pick["battery_mah"], cur["battery_mah"]))
            if pick["display_inch"] > cur["display_inch"] or \
               pick["refresh_rate_hz"] > cur["refresh_rate_hz"]:
                g.append("Better display — {}\" · {}Hz".format(
                    pick["display_inch"], pick["refresh_rate_hz"]))
            if pick["charging_w"] > cur["charging_w"]:
                g.append("Faster charging — {}W vs {}W".format(
                    pick["charging_w"], cur["charging_w"]))
            if pick["value_score"] > cur["value_score"]:
                g.append("Better overall value rating")
            return g

        # Best phone unlocked at each small budget increase (+₹2k … +₹10k).
        # "Adding ₹X" means ₹X on top of the CURRENT pick's price, and we show
        # the best phone at that exact new price point (priced above the current
        # pick, up to current price + ₹X).
        tiers = []
        for delta in (2000, 4000, 6000, 8000, 10000):
            ceiling = current["price_inr"] + delta
            candidates = [p for p in pool_dicts
                          if current["price_inr"] < p["price_inr"] <= ceiling]
            pick = candidates[0] if candidates else None   # pool order = best score
            if pick:
                tiers.append({
                    "delta": delta,
                    "new_budget": ceiling,
                    "available": True,
                    "pick": pick,
                    "price_delta": pick["price_inr"] - current["price_inr"],
                    "features": _phone_feature_list(pick),
                    "gains": compute_gains(current, pick),
                    "explore_url": _samsung_explore_url(pick["model"]),
                })
            else:
                tiers.append({"delta": delta, "new_budget": ceiling,
                              "available": False})

        upgrade = {
            "current": current,
            "current_explore_url": _samsung_explore_url(current["model"]),
            "tiers": tiers,
            "has_any": any(t["available"] for t in tiers),
        }

    return render_template(
        "results.html",
        persona=persona,
        budget=budget,
        weights=weight_pct,
        weights_raw=weights,
        sim_min_budget=sim_min_budget,
        sim_max_budget=sim_max_budget,
        top3=top3_dicts,
        full_ranking=full_dicts,
        inferred_note=inferred_note,
        ecosystem=ecosystem,
        community=community,
        upgrade=upgrade,
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


@app.route("/api/simulate-budget", methods=["POST"])
def api_simulate_budget():
    """
    USP: Budget Simulator (AJAX endpoint).

    Re-runs the existing WSM recommender (get_top_recommendations) with the
    same persona/weights already used on the results page, but with an
    updated budget supplied by the slider. Returns the new top pick plus a
    dynamic explanation of what changed relative to the previous pick, built
    only from existing scores/specs -- no separate scoring logic and no
    hardcoded phone data.
    """
    data = request.get_json(silent=True) or {}
    weights = data.get("weights") or {}
    budget_raw = data.get("budget")
    previous = data.get("previous") or None

    required_keys = ["camera", "performance", "battery", "display"]
    if not all(k in weights for k in required_keys):
        return jsonify({"error": "invalid_weights"}), 400

    try:
        budget = int(budget_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_budget"}), 400

    # Reuse the exact same recommendation algorithm/backend as the results
    # page -- same persona weights, same WSM pipeline, same reason builder --
    # just with the updated budget. Ask for a fresh Top 3 (no logic rewritten
    # here, no hardcoded phones/prices/reasons).
    top3 = get_top_recommendations(weights, budget, csv_path=CSV_PATH, top_n=3)
    if top3.empty:
        return jsonify({
            "top3": [],
            "phone": None,
            "budget": budget,
            "changed": True,
            "reasons": [],
        })

    top3_dicts = [_phone_to_dict(row) for _, row in top3.iterrows()]
    new_dict = top3_dicts[0]

    same_phone = bool(previous) and previous.get("phone_id") == new_dict["phone_id"]
    reasons = [] if same_phone else generate_budget_change_reasons(previous, new_dict)

    price_diff = (new_dict["price_inr"] - previous["price_inr"]
                  if previous and previous.get("price_inr") is not None else None)
    match_diff = (round(new_dict["match_score"] - previous["match_score"], 1)
                  if previous and previous.get("match_score") is not None else None)

    return jsonify({
        "top3": top3_dicts,
        "phone": new_dict,                 # new #1 (kept for backward compatibility)
        "previous_top1": previous,         # previous #1 recommendation, if any
        "new_top1": new_dict,              # new #1 recommendation
        "budget": budget,
        "changed": not same_phone,
        "reasons": reasons,
        "price_diff": price_diff,
        "match_diff": match_diff,
    })



if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)