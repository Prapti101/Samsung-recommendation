# 📱 Galaxy Match — Samsung Galaxy Mobile Recommendation Assistant

A **premium, Samsung-inspired recommendation assistant** (not a chatbot) that
recommends the best Samsung Galaxy phone for you using a transparent,
math-driven **Weighted Sum Model (WSM)** — no LLMs, no black-box AI, just
clear, explainable data science.

```
User opens app
  → Selects a persona OR describes themselves in free text
  → System analyzes preferences (persona weights + budget)
  → Weighted Sum Model ranks all 15 Samsung Galaxy phones
  → Top 3 recommendations shown with match scores and plain-English reasons
```

---

## ✨ Features

- **15-phone realistic dataset** (Galaxy S24/S25 series, Z Fold6/Flip6,
  A-series, M55) with 2024–2025 Indian pricing
- **Data cleaning pipeline** — removes duplicates, fills missing values,
  fixes unrealistic prices using domain-informed validation
- **Feature engineering** — normalizes raw specs into 4 scores (0–10):
  Camera, Performance, Battery, Value
- **4 built-in personas** with weights summing to 1.0, or describe yourself
  in free text (e.g. *"I'm a student with a ₹35k budget..."*) and the app
  infers your persona + budget automatically
- **Weighted Sum Model**: `Score = Camera·w1 + Performance·w2 + Battery·w3 + Value·w4`
- **Fine-tune priorities** — override persona weights with custom sliders
- **Top 3 recommendation cards** with animated match-score rings, score
  breakdowns, specs, and dynamically generated reasons
- **Compare two phones** side-by-side, with a floating compare tray on the
  results page
- **Full ranking table** of every phone that fits your budget
- **Responsive**, Samsung India–inspired UI: minimal, whitespace-led,
  rounded cards, blue accents, smooth animations (all original assets — no
  Samsung IP is copied)
- **EDA notebook** with 7 matplotlib visualizations and written insights

---

## 🗂 Project Structure

```
samsung_recommender/
├── app.py                     # Flask application (routes, view logic)
├── recommender.py             # Weighted Sum Model + explanation engine
├── feature_engineering.py     # Raw specs -> 4 normalized 0-10 scores
├── personas.py                # 4 personas + free-text persona matcher
├── data_cleaning.py           # Cleans raw_phones.csv -> phones.csv
├── raw_phones.csv             # Intentionally "dirty" source data
├── phones.csv                 # Cleaned, production dataset (15 phones)
├── build_eda_notebook.py      # Script that generates notebooks/EDA.ipynb
├── requirements.txt
├── README.md
├── templates/
│   ├── base.html              # Shared layout, navbar, footer
│   ├── index.html             # Home: persona/text input, budget, priorities
│   ├── results.html           # Top 3 + full ranking + compare tray
│   ├── compare.html           # Standalone two-phone comparison page
│   └── _compare_table.html    # Shared comparison table partial
├── static/
│   ├── css/style.css          # Full design system
│   └── js/
│       ├── main.js            # Shared utilities, reveal animations
│       ├── home.js             # Form interactions, live persona preview
│       ├── results.js          # Floating compare tray logic
│       └── compare.js          # Client-side dynamic comparison rendering
└── notebooks/
    └── EDA.ipynb               # Exploratory data analysis (executed)
```

---

## 🚀 Getting Started

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

> The app ships with a pre-cleaned `phones.csv`. If you want to regenerate
> it from the raw (intentionally dirty) source data and see the cleaning
> report, run:
> ```bash
> python data_cleaning.py
> ```

To regenerate the EDA notebook from scratch:
```bash
python build_eda_notebook.py
jupyter nbconvert --to notebook --execute --inplace notebooks/EDA.ipynb
```

---

## 🧮 How the recommendation engine works

### 1. Data cleaning (`data_cleaning.py`)
`raw_phones.csv` contains realistic data-quality issues: a duplicate row, two
missing `storage_gb` values, and one unrealistic price (an accidental extra
digit). The cleaning pipeline:
- Drops exact duplicates
- Fills missing values using the **median of the same category**
- Flags unrealistic prices using **domain-informed price bands per
  category** (more robust than IQR when each category only has a handful
  of phones) and replaces them with the category median
- Validates value ranges and standardizes text fields

### 2. Feature engineering (`feature_engineering.py`)
Raw specs are transformed into 4 scores, each **min-max normalized to
0–10** across the catalog:

| Score | Built from |
|---|---|
| 📸 **Camera** | Main / ultra-wide / telephoto / front MP (sqrt-scaled so a 200MP sensor doesn't swamp the scale) |
| ⚡ **Performance** | Chipset tier + RAM + refresh rate |
| 🔋 **Battery** | Battery capacity (mAh) + charging speed (W) |
| 💰 **Value** | Overall hardware score ÷ √price — "spec-per-rupee" |

### 3. Personas (`personas.py`)
| Persona | Camera | Performance | Battery | Value |
|---|---|---|---|---|
| 📸 Camera Enthusiast / Content Creator | 50% | 20% | 15% | 15% |
| 🎮 Gamer / Power User | 15% | 50% | 25% | 10% |
| 🎓 Student / Budget Buyer | 15% | 15% | 25% | 45% |
| 💼 Business / All-Rounder | 20% | 30% | 30% | 20% |

Free-text descriptions are matched to the closest persona via keyword
scoring, and budgets are extracted with regex (`₹35k`, `1.2 lakh`, `Rs
40000`, etc.).

### 4. Weighted Sum Model (`recommender.py`)
```
Score = Camera·w1 + Performance·w2 + Battery·w3 + Value·w4
```
Phones are filtered to the user's budget (with a small tolerance so tight
budgets don't return empty results), scored, and ranked. The Top 3 get a
**dynamically generated explanation** based on which scoring dimensions
contributed most to their ranking.

---

## 🎨 Design

The UI takes cues from Samsung India's site — minimal layouts, generous
whitespace, rounded cards, a deep-blue palette, and subtle motion — while
using entirely original CSS/SVG assets (no Samsung logos, photography, or
copyrighted material). The signature visual is an animated **match-score
ring**, tying the UI directly to the WSM score that drives every
recommendation.

---

## ⚠️ Disclaimer

This is an independent, educational project. It is **not affiliated with or
endorsed by Samsung**. Prices and specifications are illustrative
approximations for the Indian market (2024–2025) and may not reflect
current retail prices.
