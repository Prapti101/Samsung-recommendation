"""
build_phones_csv.py
-------------------
Regenerates phones.csv from raw_phones.xlsx — the actual source of truth for
the catalog.

Why this exists
---------------
phones.csv had drifted to a hand-made 15-row subset whose cheapest phone was
₹16,999, while raw_phones.xlsx holds the real 47-phone catalog starting at
₹8,699 (Galaxy A05). Any budget below ₹16,999 therefore had no phone to
recommend, so the engine could only ever return something over budget. Rather
than patch rows in by hand again (and drift again), this script rebuilds the
CSV from the spreadsheet.

Run it whenever raw_phones.xlsx changes:

    python build_phones_csv.py

Schema mapping (xlsx -> phones.csv)
-----------------------------------
The app's existing columns are kept exactly as they were, so no application
code has to change:

    model_name      -> model      ("Samsung Galaxy A05" -> "Galaxy A05")
    base_ram_gb     -> ram_gb
    battery_mAh     -> battery_mah
    screen_size     -> display_inch
    series_tier     -> category   (mapped to the app's vocabulary, below)
    (constant)      -> brand      ("Samsung")

Two deliberate notes
--------------------
1. weight_g: the spreadsheet has no weight column. Weights are NOT invented
   here — the real weights already known for the previously-shipped models are
   carried over by model name, and every other phone is left blank. The compare
   table renders a blank weight as "—". Add a `weight_g` column to the
   spreadsheet and it will flow through automatically.

2. phone_id is assigned by spreadsheet row order. Inserting a row mid-file will
   renumber later phones, which invalidates phone_ids already saved in a
   browser's localStorage wishlist/history. Append new phones at the end to
   avoid that.
"""

import csv
import os
import zipfile
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

XLSX_PATH = "raw_phones.xlsx"
CSV_PATH = "phones.csv"

# The app's category vocabulary is budget / midrange / flagship / foldable —
# ecosystem.py and ai_longevity.py key their heuristics off exactly these.
# Foldables are detected from the display type, so they win over the tier.
_TIER_TO_CATEGORY = {
    "Entry Budget": "budget",
    "Core Mid-Range": "midrange",
    "High Mid-Range": "midrange",
    "Premium Flagship": "flagship",
    # XCover7 is a rugged enterprise handset; at ₹29,999 it sits in the
    # midrange price tier, which is how `category` is actually consumed.
    "Enterprise": "midrange",
}

# Output schema — unchanged from the CSV the app already reads.
FIELDNAMES = [
    "phone_id", "brand", "model", "release_year", "price_inr", "ram_gb",
    "storage_gb", "battery_mah", "charging_w", "main_camera_mp",
    "ultra_wide_mp", "telephoto_mp", "front_camera_mp", "processor",
    "display_inch", "refresh_rate_hz", "display_type", "weight_g", "category",
]


def read_xlsx(path: str) -> list:
    """
    Minimal .xlsx reader (rows as dicts). Implemented against the raw
    SpreadsheetML so the build does not require openpyxl to be installed.
    """
    zf = zipfile.ZipFile(path)

    shared = []
    if "xl/sharedStrings.xml" in zf.namelist():
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in root.findall(NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))

    rows = []
    for row in ET.fromstring(zf.read("xl/worksheets/sheet1.xml")).iter(NS + "row"):
        values = []
        for cell in row.findall(NS + "c"):
            v = cell.find(NS + "v")
            if v is None:
                values.append("")
            elif cell.get("t") == "s":
                values.append(shared[int(v.text)])
            else:
                values.append(v.text)
        rows.append(values)

    header = rows[0]
    return [dict(zip(header, r)) for r in rows[1:]]


def existing_weights(path: str) -> dict:
    """
    Real weights already recorded for previously-shipped models, keyed by model
    name. Used so regenerating the catalog does not throw away data we have --
    and so that no weight is ever guessed for a phone we don't have one for.
    """
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["model"]: r.get("weight_g", "")
                for r in csv.DictReader(fh) if r.get("weight_g")}


def to_int(value) -> int:
    """'5000' / '5000.0' -> 5000."""
    return int(round(float(value)))


def category_for(row: dict) -> str:
    if "foldable" in str(row["display_type"]).lower():
        return "foldable"
    return _TIER_TO_CATEGORY.get(str(row["series_tier"]).strip(), "midrange")


def main() -> None:
    src = read_xlsx(XLSX_PATH)
    weights = existing_weights(CSV_PATH)

    out = []
    for i, row in enumerate(src, start=1):
        model = row["model_name"].strip()
        if model.lower().startswith("samsung "):
            model = model[len("samsung "):]

        out.append({
            "phone_id": i,
            "brand": "Samsung",
            "model": model,
            "release_year": to_int(row["release_year"]),
            "price_inr": to_int(row["price_inr"]),
            "ram_gb": to_int(row["base_ram_gb"]),
            "storage_gb": to_int(row["storage_gb"]),
            "battery_mah": to_int(row["battery_mAh"]),
            "charging_w": to_int(row["charging_w"]),
            "main_camera_mp": to_int(row["main_camera_mp"]),
            "ultra_wide_mp": to_int(row["ultra_wide_mp"]),
            "telephoto_mp": to_int(row["telephoto_mp"]),
            "front_camera_mp": to_int(row["front_camera_mp"]),
            "processor": row["processor"].strip(),
            "display_inch": float(row["screen_size"]),
            "refresh_rate_hz": to_int(row["refresh_rate_hz"]),
            "display_type": row["display_type"].strip(),
            # Never invented: carried over when known, blank otherwise.
            "weight_g": weights.get(model, ""),
            "category": category_for(row),
        })

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(out)

    known = sum(1 for r in out if r["weight_g"])
    print("Wrote {} phones to {}".format(len(out), CSV_PATH))
    print("  cheapest: {} ₹{:,}".format(
        min(out, key=lambda r: r["price_inr"])["model"],
        min(r["price_inr"] for r in out)))
    print("  weight_g known for {}/{} (blank = not in the spreadsheet; "
          "not guessed)".format(known, len(out)))


if __name__ == "__main__":
    main()
