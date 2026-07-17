# Galaxy Compass — Project Brief

**A Samsung Galaxy phone recommendation assistant**

Team: Prapti Priya · Shatabdi Das . Aditi Singh . Subiksha
Repository: github.com/Prapti101/Samsung-recommendation

---

## The problem we set out to solve

Buying a phone is harder than it should be. Samsung alone sells dozens of Galaxy models at once — our own catalog has **47 phones** priced anywhere from **₹8,699 to ₹1,64,999** — and on paper they all start to look the same: 8GB RAM, 5000mAh, 50MP, 120Hz. That wall of numbers doesn't actually tell you which phone is right for *you*.

So people fall back on bad shortcuts. They buy whatever's trending, or whatever the shop is pushing, or just the most expensive phone they can afford and hope for the best. Retail-site filters don't really help either — they can narrow by price or RAM, but they can't tell you that a big battery matters more than a 200MP camera if you're a student with a long daily commute.

The gap isn't information. It's that nobody translates the specs into an actual decision. That's the gap we wanted to close: **tell us who you are and what you can spend, and we'll tell you which Samsung phone makes sense — and explain why in plain English.**

## Business context

For a retailer or for Samsung, a confused buyer is a lost sale or a returned phone. Someone who buys a gaming phone when they wanted a camera phone leaves a bad review and doesn't come back. Someone who can't decide buys nothing at all.

There's a second, quieter problem too: people don't know what they could get. A shopper with ₹60,000 often has no idea that a little more moves them to a much better camera. That's money left on the table — which is exactly why we built upgrade suggestions *into* the recommendation flow instead of bolting on a generic "you may also like" box.

The whole aim is a tool that gives an honest, explainable answer fast — one a buyer trusts because they can see the reasoning, not just the result. It's an independent, educational project and isn't affiliated with Samsung; the prices are illustrative approximations for the Indian market (2024–2025) and all the visual assets are original.

## Our approach

A recommender that can't explain itself is useless in a store, and a model that occasionally invents specs is worse than no tool at all. Everything here is math you could check on a whiteboard.

The engine is a **Weighted Sum Model (WSM)**, and it works in four clear steps:

1. **Score every phone.** Each phone gets four scores out of 10 — camera, performance, battery, and display — worked out from its real specs. We measure against fixed reference points (like a 200MP camera or a 5,500mAh battery) rather than against the other phones, so one extreme outlier can't squash everything else down to zero.

2. **Figure out what you want.** There are three ways in, and they all end up in the same place: pick one of **6 personas** (Student, Gamer, Photographer, Business Professional, Traveller, Social Influencer), describe yourself in your own words, or answer a short guided quiz. Whichever you choose becomes four weights that add up to 100%.

3. **Rank.** `match = camera·w1 + performance·w2 + battery·w3 + display·w4`. Your budget is a hard limit, never a suggestion. We also shortlist to a *budget band* (roughly 75–100% of what you said), because if you tell us ₹60,000, a ₹26,000 phone isn't really an answer to your question.

4. **Explain.** Every line on the results page is generated from those numbers. "Leads with a strong 6000mAh battery" shows up because the battery score is genuinely high — not because someone typed it in.

The same scores drive everything: the ranking, the bars on screen, the compare page, the upgrade suggestions. There's one scoring engine and nothing duplicates it, so the site can't quietly contradict itself.

Before any of that runs, a **data-cleaning pipeline** removes duplicate rows, fills missing values using category medians, and catches unrealistic prices (like an accidental extra digit) so they can't throw the scores off.

## What's in it

- **Top 3 recommendations** with a match %, a score breakdown, and a written reason for each
- **Smarter Upgrade** — the nearest phone above your pick that's genuinely better, showing the exact rupees needed and what you get for them
- **Compare** — any two phones side by side on the same scores
- **View All** — the full 47-phone catalog with live filters
- **Community Insights** — a phone's strengths and trade-offs, plus links out to Reddit, GSMArena, AnTuTu and Samsung so people can check our work
- **History & Wishlist** — saved right in the browser, no login needed
- Dark mode, a rotating 3D phone on the homepage, and a responsive layout that works on mobile
- **Multi-language support**

One thing we're happy with: all of these extras are presentation-only. None of them secretly change the ranking — the WSM stays the single, honest source of truth for every recommendation.

## The data

**47 Galaxy phones, 21 fields each** — name, price, chipset, RAM, storage, battery, charging, all four cameras, display, and the official Samsung product link. The mix is realistic: 18 mid-range, 14 budget, 9 flagship, and 6 foldable, spanning 2023–2025.

The catalog is **generated, not hand-typed.** A build script rebuilds `phones.csv` from a source spreadsheet, so adding a phone just means adding a row and re-running one script — no code changes. We were also honest about the gaps rather than papering over them: where the spreadsheet is missing a field the compare page simply shows "—", and the handful of discontinued models without a live Samsung page fall back to a search for that exact model instead of a dead link.

## Tools and tech we used

| Area | What we used |
|---|---|
| Backend | Python, Flask |
| Data & math | pandas, NumPy |
| Frontend | Jinja2 templates, plain CSS, vanilla JavaScript |
| 3D | Google `<model-viewer>` with a `.glb` model |
| Analysis | Jupyter notebook (EDA) with matplotlib |
| Version control | Git & GitHub |

No paid APIs, no database, no LLM. The whole thing runs with `python app.py`.

The code is organized so each stage does one job — `data_cleaning.py` → `feature_engineering.py` → `personas.py` → `recommender.py` → `app.py` — which keeps everything testable and easy to follow.

## Running it
## Live Project Running On - https://samsung-recommendation.onrender.com
```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
python app.py                  # http://localhost:5000
```

Rebuild the catalog after editing the spreadsheet:

```bash
python build_phones_csv.py
```

---

