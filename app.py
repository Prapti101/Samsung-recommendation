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

from flask import Flask, render_template, request, jsonify, session
import pandas as pd

from feature_engineering import load_engineered_phones
from personas import PERSONAS, PERSONA_ORDER, list_personas, match_persona_from_text, get_persona
from recommender import get_top_recommendations, get_full_ranking, generate_budget_change_reasons
from ai_longevity import compute_ai_longevity
from ecosystem import get_ecosystem_recommendations

app = Flask(__name__)
# Secret key enables server-side session storage (used to remember the last
# recommendation inputs so the "Recommend" tab can redisplay results on GET).
app.secret_key = "galaxy-match-local-dev-key"

CSV_PATH = "phones.csv"


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
    min_price = int(df["price_inr"].min())
    max_price = int(df["price_inr"].max())
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
            "w_value": form.get("w_value", ""),
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
            "weights": {"camera": 0.25, "performance": 0.25, "battery": 0.25, "value": 0.25},
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
        persona = PERSONAS["business_allrounder"]
        budget = int(budget_raw) if budget_raw else persona["default_budget"]

    weights = dict(persona["weights"])

    # Optional custom priority sliders (camera/performance/battery/value 0-100),
    # sent from the "Fine-tune priorities" panel on the home page. If present
    # and they sum to > 0, they override the persona's default weights.
    custom_weight_keys = ["w_camera", "w_performance", "w_battery", "w_value"]
    if all(form.get(k) not in (None, "") for k in custom_weight_keys):
        raw_vals = {k: float(form.get(k, 0)) for k in custom_weight_keys}
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

    # ------------------------------------------------------------------
    # "Smarter Upgrade" (presentation-only, complements the Budget Simulator).
    # Reuses the EXISTING WSM engine: rank the whole catalog (budget=None) with
    # the same weights, then pick the best-scoring phone priced ABOVE the current
    # #1 — i.e. what a slightly bigger budget would unlock. No new scoring logic;
    # improvement bullets are derived from existing spec fields below.
    # ------------------------------------------------------------------
    upgrade = None
    if top3_dicts:
        current = top3_dicts[0]
        full_pool = get_full_ranking(weights, budget=None, csv_path=CSV_PATH)
        pool_dicts = [_phone_to_dict(row) for _, row in full_pool.iterrows()]
        pricier = [p for p in pool_dicts if p["price_inr"] > current["price_inr"]]

        # Keep it a *small* step-up: cap the jump at the larger of +₹35,000 or
        # +80% of the current price, so a genuinely better phone can surface
        # while still feeling like a modest increase.
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

        if pricier:
            cap = current["price_inr"] + max(35000, int(current["price_inr"] * 0.8))
            window = [p for p in pricier if p["price_inr"] <= cap]
            pool_for_pick = window if window else pricier

            # Prefer, within the modest-upgrade window, the option that has the
            # most tangible spec gains (then best match, then smallest jump).
            scored = []
            for cand in pool_for_pick:
                g = compute_gains(current, cand)
                scored.append((cand, g))
            scored_with_gains = [(c, g) for (c, g) in scored if g]

            if scored_with_gains:
                upgrade_pick, gains = sorted(
                    scored_with_gains,
                    key=lambda cg: (-len(cg[1]), -(cg[0]["match_score"] or 0),
                                    cg[0]["price_inr"] - current["price_inr"]),
                )[0]
                upgrade = {
                    "current": current,
                    "pick": upgrade_pick,
                    "price_delta": upgrade_pick["price_inr"] - current["price_inr"],
                    "gains": gains,
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

    required_keys = ["camera", "performance", "battery", "value"]
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