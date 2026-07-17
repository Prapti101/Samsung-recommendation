<h1 align="center">🧭 Galaxy Compass</h1>

<p align="center">
  <b>A transparent, math-driven Samsung Galaxy phone recommendation assistant.</b><br>
  Tell it who you are and what you can spend — it tells you which phone fits, and <i>why</i>.
</p>

<p align="center">
  <b>Team:</b> Prapti Priya · Aditi Singh · Shatabdi Das · Subiksha
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white">
  <img alt="Flask" src="https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white">
  <img alt="pandas" src="https://img.shields.io/badge/pandas-2.2-150458?logo=pandas&logoColor=white">
  <img alt="NumPy" src="https://img.shields.io/badge/NumPy-1.26-013243?logo=numpy&logoColor=white">
  <img alt="No LLM" src="https://img.shields.io/badge/AI-No%20LLM%2C%20fully%20explainable-success">
</p>

---

## 📖 About

Buying a phone is harder than it should be. Samsung alone sells dozens of Galaxy models at once, and on a spec sheet they all blur together — 8GB RAM, 5000mAh, 50MP, 120Hz. None of that tells you which phone is right for **you**.

**Galaxy Compass** closes that gap. You describe yourself (or pick a persona, or take a quick quiz) and set a budget, and the app ranks every phone using a **Weighted Sum Model (WSM)** — a clear, explainable scoring formula. No chatbot, no black box, no invented specs. Every recommendation comes with a match score and a plain-English reason you can check.

> ⚠️ This is an independent, educational project. It is **not affiliated with or endorsed by Samsung**. Prices and specs are illustrative approximations for the Indian market (2024–2025).

---

## ✨ Features

- 🎯 **Top 3 recommendations** with an animated match-score ring, a score breakdown, and a generated reason for each pick
- 🧑‍🤝‍🧑 **3 ways to get recommendations** — pick a persona, describe yourself in plain text, or take a guided quiz
- 📈 **Smarter Upgrade** — "if I spent ₹X more, what would I get?" with the exact gain
- ⚖️ **Compare** — any two phones side by side on the same scores
- 📱 **View All** — the full 47-phone catalog with live filters
- 💬 **Community Insights** — strengths, trade-offs, and links out to Reddit, GSMArena, AnTuTu & Samsung to verify
- ❤️ **Wishlist & History** — saved right in your browser, no login required
- 🌗 **Dark mode**, a rotating **3D phone** on the homepage, and **multi-language** support
- 🧼 **Data cleaning pipeline** and an **EDA notebook** with 7 visualizations

---

## 🧮 How the recommendation engine works

The engine is a **Weighted Sum Model**. Every recommendation is math you could do on a whiteboard.

### 1. Score every phone (`feature_engineering.py`)
Each phone's raw specs are turned into **four scores from 0–10**:

| Score | Built from |
|---|---|
| 📷 **Camera** | main + telephoto + ultra-wide + front lenses (sqrt-scaled so a 200MP sensor doesn't swamp the scale) |
| ⚡ **Performance** | chipset tier + RAM |
| 🔋 **Battery** | capacity + charging speed |
| 🖥️ **Display** | panel quality (AMOLED > LCD) + refresh rate + size |

Scores use **fixed reference anchors** (e.g. 5500mAh = a great battery) instead of pure min-max normalisation, so one extreme phone can't crush every other phone to zero. A fifth **value** score (spec-per-rupee) is derived but **not** ranked on — it's shown only as extra info.

### 2. Understand the user (`personas.py`)
Priorities become **four weights that sum to 1.0**. There are **6 built-in personas**:

| Persona | Camera | Performance | Battery | Display |
|---|:--:|:--:|:--:|:--:|
| 🎓 Student | 0.15 | 0.20 | 0.35 | 0.30 |
| 💼 Business Professional | 0.20 | 0.35 | 0.25 | 0.20 |
| 🧭 Traveller | 0.30 | 0.20 | 0.35 | 0.15 |
| 🎮 Gamer | 0.10 | 0.45 | 0.20 | 0.25 |
| 🤳 Social Media Influencer | 0.40 | 0.20 | 0.15 | 0.25 |
| 📷 Photographer | 0.55 | 0.20 | 0.10 | 0.15 |

Free-text descriptions (e.g. *"student with a ₹35k budget who uses Instagram"*) are matched to the closest persona by **keyword scoring**, and the budget is pulled out with **regex** (understands `₹35k`, `35000`, `1.2 lakh`, `Rs 40000`, …).

### 3. Rank (`recommender.py`)
```
match_score = (camera·w₁ + performance·w₂ + battery·w₃ + display·w₄) × 10
```
Each score is 0–10 and the weights sum to 1, so the total is 0–10 → ×10 gives the **0–100 match %**. The pipeline:

1. **Filter** — budget is a hard limit; anything over budget is dropped
2. **Band** — shortlist phones priced **75–100% of the budget** (a ₹26k phone isn't the answer to a ₹60k question); widens automatically if too few qualify
3. **Score** — weighted sum of the four dimensions
4. **Rank** — sort by match score, with deterministic tie-breaks so results are reproducible
5. **Explain** — a plain-English reason generated from whichever dimensions scored highest *and* mattered most to that persona

If nothing fits the budget, it offers the phone **closest** to what you can spend instead of the best-scoring expensive one.

---

## 🗂️ Project structure

```
Samsung-recommendation/
├── app.py                    # Flask app — routes, input handling, view logic
├── recommender.py            # Weighted Sum Model + explanation engine
├── feature_engineering.py    # Raw specs → 4 normalized 0–10 scores
├── personas.py               # 6 personas + free-text persona/budget matcher
├── data_cleaning.py          # Cleans the raw catalog → phones.csv
├── build_phones_csv.py       # Rebuilds phones.csv from raw_phones.xlsx
├── build_eda_notebook.py     # Generates the EDA notebook
├── build_phone_images.py     # Prepares phone images
├── ai_longevity.py           # "AI & Longevity" radar score (visual only)
├── ecosystem.py              # "Complete your Galaxy" accessory suggestions
├── community.py              # Community Insights snapshot + trusted links
├── upgrade.py                # Smarter Upgrade / budget optimizer
├── translations.py           # Multi-language UI strings
├── raw_phones.xlsx           # Source of truth for the catalog
├── phones.csv                # Cleaned, production dataset (47 phones)
├── requirements.txt
├── notebooks/
│   └── EDA.ipynb             # Exploratory data analysis (7 charts + insights)
├── templates/                # Jinja2 HTML (home, results, compare, quiz, …)
└── static/
    ├── css/                  # Design system
    ├── js/                   # Vanilla JS (quiz, compare, upgrade, theme, …)
    ├── img/                  # Phone images
    └── models/               # 3D .glb model
```

---

## 📊 The dataset

**47 Samsung Galaxy phones**, 21 fields each — price, chipset, RAM, storage, battery, charging, all four cameras, display, weight, and the official Samsung link.

| Category | Count |
|---|:--:|
| Mid-range | 18 |
| Budget | 14 |
| Flagship | 9 |
| Foldable | 6 |

Years: 2023–2025 · Price range: **₹8,699 – ₹1,64,999**

The catalog is **generated, not hand-typed** — `build_phones_csv.py` rebuilds `phones.csv` from `raw_phones.xlsx`, so adding a phone is just adding a row and re-running one script.

---

## 🚀 Getting started

```bash
# 1. Clone the repo
git clone https://github.com/Prapti101/Samsung-recommendation.git
cd Samsung-recommendation

# 2. (Optional) create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

**Regenerate the data** after editing the spreadsheet:
```bash
python build_phones_csv.py   # rebuild phones.csv from raw_phones.xlsx
python data_cleaning.py      # clean it + print a cleaning report
```

**Regenerate the EDA notebook:**
```bash
python build_eda_notebook.py
jupyter nbconvert --to notebook --execute --inplace notebooks/EDA.ipynb
```

---

## 🛠️ Tech stack

| Area | Tools |
|---|---|
| Backend | Python, Flask |
| Data & math | pandas, NumPy |
| Frontend | Jinja2 templates, plain CSS, vanilla JavaScript |
| 3D | Google `<model-viewer>` + a `.glb` model |
| Analysis | Jupyter Notebook, matplotlib |
| Version control | Git & GitHub |

No paid APIs, no database, no LLM. The whole thing runs with `python app.py`.

---

## 🧭 Routes

| Route | What it does |
|---|---|
| `/` | Home — persona / free-text / budget input |
| `/recommend` | Runs the WSM, shows Top 3 + full ranking |
| `/quiz` | Guided discovery quiz |
| `/compare` | Compare two phones side by side |
| `/devices` | Full catalog with filters |
| `/wishlist`, `/history` | Browser-saved lists |
| `/api/phones`, `/api/persona-match`, `/api/simulate-budget` | JSON endpoints for the UI |

---

## 👥 Team

- **Prapti Priya** 
- **Aditi Singh**
- **Shatabdi Das**
- **Subiksha**

---

## 📄 License

This project is for educational purposes. It is not affiliated with Samsung, and all visual assets are original.
