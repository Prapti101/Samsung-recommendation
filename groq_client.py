"""
groq_client.py — thin Groq API wrapper
======================================
One job: send a prompt to Groq and return parsed JSON. Nothing in here knows
what a phone is; community.py owns the prompt and the meaning of the response.

Why stdlib urllib instead of the `groq` SDK
-------------------------------------------
Groq's endpoint is an OpenAI-compatible REST call, so this needs no third-party
package. That keeps requirements.txt at four entries and removes a whole class
of "works locally, fails on Render" dependency problems.

Failure policy
--------------
Every failure path returns None rather than raising: missing key, network error,
timeout, HTTP error, malformed JSON. Callers are expected to fall back to a
deterministic local result. The recommendation engine must never depend on an
external API being up, and a hackathon demo must not break because of Wi-Fi.
"""

import json
import os
import urllib.error
import urllib.request

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Identifies this app to Groq's Cloudflare edge. Without a User-Agent, urllib
# sends "Python-urllib/x.y" and Cloudflare blocks the call with 403 / error 1010.
USER_AGENT = "galaxy-compass/1.0"

# Overridable so a model can be swapped without a code change (Groq retires
# model names periodically).
DEFAULT_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# Short on purpose: a page render waits on this. If Groq is slow we would rather
# show the deterministic fallback than make the user stare at a blank page.
TIMEOUT_SECONDS = float(os.environ.get("GROQ_TIMEOUT", "8"))


def is_configured() -> bool:
    """True when a Groq API key is present in the environment."""
    return bool(os.environ.get("GROQ_API_KEY", "").strip())


def complete_json(system_prompt: str, user_prompt: str,
                  temperature: float = 0.3, max_tokens: int = 700):
    """
    Purpose : Ask Groq for a JSON object and return it parsed.
    Inputs  : system_prompt — the model's instructions / role
              user_prompt   — the data to reason about
              temperature   — low by default; this is analysis, not creative
                              writing, and we want stable output across reloads
    Output  : dict parsed from the model's JSON reply, or None on ANY failure.
    Algorithm: POST an OpenAI-compatible chat completion with
              response_format=json_object, which constrains the model to emit
              a single valid JSON object, then parse the reply.
    """
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return None

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        # Forces a single valid JSON object rather than prose we would have to
        # scrape.
        "response_format": {"type": "json_object"},
    }

    request = urllib.request.Request(
        GROQ_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
            # REQUIRED. Groq sits behind Cloudflare, which rejects urllib's
            # default "Python-urllib/3.13" signature with HTTP 403 "error code:
            # 1010" — before the request ever reaches Groq, so the API key is
            # irrelevant. Any ordinary User-Agent gets through.
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        return json.loads(content)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            KeyError, IndexError, ValueError, OSError):
        # Deliberately broad: no Groq problem may ever surface as a 500.
        return None
