"""
personas.py
-----------
Defines the 4 built-in buyer personas used by the Weighted Sum Model, and
provides a lightweight rule-based matcher that maps free-text user
descriptions (e.g. "I'm a student with a ₹35k budget who mostly uses
Instagram and WhatsApp") to the closest persona + an inferred budget.

Each persona's weights (camera, performance, battery, value) always sum
to 1.0, matching the WSM formula:

    Score = camera*w1 + performance*w2 + battery*w3 + value*w4
"""

import re

# ----------------------------------------------------------------------
# 1. Persona definitions
# ----------------------------------------------------------------------
PERSONAS = {
    "student": {
        "id": "student",
        "name": "Student",
        "emoji": "🎓",
        "description": "You want the best possible phone for the money -- solid "
                        "all-round specs and a battery that lasts through long "
                        "days of classes, notes and entertainment, without "
                        "overspending.",
        "weights": {"camera": 0.15, "performance": 0.15, "battery": 0.25, "value": 0.45},
        "default_budget": 30000,
        "keywords": ["student", "budget", "college", "school", "cheap", "affordable",
                     "value", "money", "tight budget", "low budget", "study", "save"],
    },
    "business_professional": {
        "id": "business_professional",
        "name": "Business Professional",
        "emoji": "💼",
        "description": "You need a dependable phone for work and life -- strong "
                        "performance for multitasking, all-day battery, and the "
                        "reliability to handle calls, email and meetings anywhere.",
        "weights": {"camera": 0.20, "performance": 0.30, "battery": 0.30, "value": 0.20},
        "default_budget": 120000,
        "keywords": ["business", "work", "professional", "office", "productivity",
                     "meetings", "reliable", "corporate", "executive", "email",
                     "all rounder", "all-rounder", "balanced"],
    },
    "traveller": {
        "id": "traveller",
        "name": "Traveller",
        "emoji": "🧭",
        "description": "You want a phone that lasts through long journeys, captures "
                        "every moment on the go, and stays connected and reliable "
                        "wherever the road takes you.",
        "weights": {"camera": 0.30, "performance": 0.20, "battery": 0.35, "value": 0.15},
        "default_budget": 80000,
        "keywords": ["travel", "traveller", "traveler", "explorer", "journey", "trip",
                     "outdoor", "adventure", "navigation", "maps", "roaming", "hiking"],
    },
    "gamer": {
        "id": "gamer",
        "name": "Gamer",
        "emoji": "🎮",
        "description": "You want raw speed -- smooth high-refresh gaming, effortless "
                        "multitasking, and a phone that never lags, with a battery "
                        "that keeps up with long sessions.",
        "weights": {"camera": 0.15, "performance": 0.50, "battery": 0.25, "value": 0.10},
        "default_budget": 110000,
        "keywords": ["gaming", "gamer", "game", "pubg", "bgmi", "fps", "multitask",
                     "performance", "fast", "power user", "processor", "chipset",
                     "benchmark", "120hz", "refresh"],
    },
    "social_influencer": {
        "id": "social_influencer",
        "name": "Social Media Influencer",
        "emoji": "🤳",
        "description": "You live for content -- stunning photos and video, a great "
                        "front camera for selfies and vlogs, and the power to edit "
                        "and post to your followers on the go.",
        "weights": {"camera": 0.45, "performance": 0.25, "battery": 0.15, "value": 0.15},
        "default_budget": 100000,
        "keywords": ["influencer", "content creator", "instagram", "reels", "tiktok",
                     "youtube", "vlog", "selfie", "social media", "creator", "posting",
                     "streaming", "followers"],
    },
    "photographer": {
        "id": "photographer",
        "name": "Photographer",
        "emoji": "📷",
        "description": "You care most about capturing stunning photos -- the best "
                        "camera system, sharp detail and strong low-light "
                        "performance, all in your pocket.",
        "weights": {"camera": 0.55, "performance": 0.20, "battery": 0.15, "value": 0.10},
        "default_budget": 140000,
        "keywords": ["photo", "photography", "photographer", "camera", "portrait",
                     "night mode", "zoom", "telephoto", "megapixel", "shoot", "dslr",
                     "low light", "detail"],
    },
}

PERSONA_ORDER = ["student", "business_professional", "traveller", "gamer",
                 "social_influencer", "photographer"]


def get_persona(persona_id: str) -> dict:
    """Return a persona dict by id, defaulting to the balanced all-rounder."""
    return PERSONAS.get(persona_id, PERSONAS["business_professional"])


def list_personas() -> list:
    """Return all personas in a stable display order."""
    return [PERSONAS[pid] for pid in PERSONA_ORDER]


# ----------------------------------------------------------------------
# 2. Free-text description -> persona + budget inference
# ----------------------------------------------------------------------
def _extract_budget(text: str):
    """
    Extract a rupee budget from free text. Understands forms like:
    "₹35k", "35k", "Rs 35000", "under 40,000", "budget of 1.2 lakh".
    Returns an int (INR) or None if nothing found.
    """
    text = text.lower().replace(",", "")

    # e.g. "1.2 lakh" / "1 lakh"
    lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*lakh", text)
    if lakh_match:
        return int(float(lakh_match.group(1)) * 100000)

    # e.g. "35k" / "₹35k" / "rs35k"
    k_match = re.search(r"(?:₹|rs\.?)?\s*(\d+(?:\.\d+)?)\s*k\b", text)
    if k_match:
        return int(float(k_match.group(1)) * 1000)

    # e.g. "₹35000" / "rs 35000" / "35000 rupees"
    plain_match = re.search(r"(?:₹|rs\.?\s*)(\d{4,7})", text)
    if plain_match:
        return int(plain_match.group(1))

    generic_match = re.search(r"\b(\d{4,7})\s*(?:rupees|inr)?\b", text)
    if generic_match:
        val = int(generic_match.group(1))
        if 5000 <= val <= 250000:  # sanity range for a phone budget
            return val

    return None


def match_persona_from_text(text: str) -> dict:
    """
    Score free text against each persona's keyword list and return the
    best match, along with any budget mentioned in the text.

    Returns:
        {
            "persona": <persona dict>,
            "budget": <int or None>,
            "confidence": <float 0-1, fraction of keyword hits vs total>
        }
    """
    text_lower = text.lower()
    best_id, best_score = "business_professional", 0

    for pid in PERSONA_ORDER:
        persona = PERSONAS[pid]
        hits = sum(1 for kw in persona["keywords"] if kw in text_lower)
        if hits > best_score:
            best_score = hits
            best_id = pid

    budget = _extract_budget(text)
    confidence = min(1.0, best_score / 3) if best_score else 0.0

    return {
        "persona": PERSONAS[best_id],
        "budget": budget,
        "confidence": round(confidence, 2),
    }


if __name__ == "__main__":
    samples = [
        "I'm a student with ₹35k budget who mostly uses Instagram and WhatsApp",
        "Need something for heavy PUBG gaming and multitasking, budget around 90k",
        "I run a travel vlog and need the best camera for reels, budget 1.2 lakh",
        "Looking for a reliable phone for work meetings and emails, all day battery",
    ]
    for s in samples:
        result = match_persona_from_text(s)
        print(f"Text: {s}")
        print(f"  -> Persona: {result['persona']['name']}, "
              f"Budget: {result['budget']}, Confidence: {result['confidence']}\n")