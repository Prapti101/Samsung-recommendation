# Galaxy Compass — Project Brief

A web app that helps someone pick the right Samsung Galaxy phone by asking what
they care about and what they can spend, then explaining its answer in plain
English.

---

## The problem

Samsung sells a lot of phones. Our catalog alone has 47 models between ₹8,699
and ₹1,64,999, and most of them look the same on a spec sheet. If you walk into
a store or open a website, you get a wall of numbers: 8GB RAM, 5000mAh, 50MP,
120Hz. None of that tells you which phone is right for *you*.

So people fall back on bad shortcuts. They buy whatever is trending, or whatever
the shop wants to move, or they just buy the most expensive phone they can afford
and hope. Filters on retail sites don't help much either — they can narrow by
price or RAM, but they can't tell you that a 6000mAh battery matters more than a
200MP camera if you're a student on a long commute.

The gap isn't information. It's that nobody translates the specs into a decision.

## Business context

For Samsung, a confused buyer is a lost sale or a returned phone. Someone who
buys a gaming phone when they wanted a camera phone leaves a bad review and
doesn't come back. Someone who can't decide buys nothing.

There's also a second problem: people don't know what they can get. A shopper
with ₹60,000 often doesn't realise that ₹3,000 more moves them to a much better
camera. That's revenue Samsung leaves on the table, and it's why we built the
upgrade suggestions into the flow instead of a separate "you may also like" box.

The aim is a tool that gives an honest, explainable answer fast — one that a
buyer trusts because they can see the reasoning, not just the result.

## Our approach

We deliberately did **not** use an LLM or a chatbot. A recommendation engine that
can't explain itself is useless in a store, and a model that occasionally invents
specs is worse than no tool at all. Everything here is math you can check on a
whiteboard.

The engine is a **Weighted Sum Model (WSM)**. It works in four steps:

1. **Score every phone.** Each phone gets four scores out of 10 — camera,
   performance, battery, display — worked out from its real specs. Scores are
   measured against fixed reference points (a 200MP camera, a 5500mAh battery)
   rather than against the other phones, so one 200MP outlier can't squash
   everything else to zero.
2. **Learn what the user wants.** Three ways in: pick a persona (Student, Gamer,
   Photographer, and 3 more), describe yourself in your own words, or take an
   8-question quiz. All three end up as the same thing — four weights that add
   up to 100%.
3. **Rank.** `match = camera×w1 + performance×w2 + battery×w3 + display×w4`.
   Budget is a hard limit, never a suggestion. We also shortlist to a *budget
   band* (75–100% of what you said), because if you tell us ₹60,000, a ₹26,000
   phone isn't an answer to your question.
4. **Explain.** Every sentence on the results page is generated from the numbers
   above. "Leads with a strong 6000mAh battery" appears because the battery score
   is actually high, not because someone typed it in.

The same scores drive everything — the ranking, the bars on screen, the compare
page, the upgrade suggestions. There's one scoring engine and nothing duplicates
it, so the site can't contradict itself.

## What's in it

- **Top 3 recommendations** with a match %, a score breakdown, and a written reason
- **Smarter Upgrade** — the nearest phone above your pick that's genuinely better,
  with the exact rupees needed and what you get for them
- **Compare** — any two phones side by side on the same scores
- **View All** — the full 47-phone catalog with live filters
- **Community Insights** — strengths and trade-offs, plus links to Reddit,
  GSMArena, AnTuTu and Samsung so people can check our work
- **History & Wishlist** — saved in the browser, no login needed
- Dark mode, a rotating 3D phone on the homepage, works on mobile

## Tools used

| Area | What we used |
|---|---|
| Backend | Python 3.13, Flask |
| Data / math | pandas, NumPy |
| Frontend | Jinja2 templates, plain CSS, vanilla JavaScript |
| 3D | Google `<model-viewer>` with a .glb model |
| Data source | `raw_phones.xlsx` → build script → `phones.csv` |
| Analysis | Jupyter (EDA notebook), matplotlib |

No paid APIs, no database, no LLM. The whole thing runs with `python app.py`.

## The data

47 Galaxy phones, 21 fields each — name, price, chipset, RAM, storage, battery,
charging, all four cameras, display, and the official Samsung product link.

The catalog is **generated**, not hand-typed. `build_phones_csv.py` rebuilds
`phones.csv` from the spreadsheet, so adding a phone means adding a row and
re-running one script — no code changes.

Two honest gaps we chose not to paper over:

- **Weights are missing for 33 phones** because the spreadsheet doesn't have that
  column. We left them blank rather than guess. The compare page shows "—".
- **11 phones have no live Samsung product page** (mostly discontinued A-series).
  We checked all 47 links with real requests; those 11 fall back to a Samsung
  search for that exact model instead of a dead link.

## What we'd do next

- Wire the 2026 models (S26 series) into the catalog — they're in the spreadsheet
  and on the homepage carousel, but not yet scored, because 3 of them have no
  product photo yet.
- Replace the keyword-based text matcher with something smarter. It gets 7 of 8
  test phrases right, but "budget" is a Student keyword, so "amazing camera,
  budget 40k" matches Student instead of Photographer.
- Real review data for Community Insights. Right now those bullets come from our
  own spec scores and say so — they're not pretending to quote real users.

## Team

| Name | Role | Contribution |
|---|---|---|
| Prapti Priya | | |
| | | |
| | | |

_(Fill in the rest — this is the only name in the commit history.)_

## Running it

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

**Project:** Galaxy Compass · **Stack:** Flask + pandas · **Dataset:** 47 Galaxy
phones (₹8,699–₹1,64,999) · **Engine:** Weighted Sum Model, no LLM
