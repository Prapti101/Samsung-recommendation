"""
build_phone_images.py
---------------------
Trims the dead white padding baked into the product shots in static/img.

Why
---
The catalog's photos were sourced from different places and carry wildly
different amounts of white border. Galaxy F56's handset occupies just 26% of its
image width; the S25+ shot is 1800x1200 with the phones spanning only the middle
47%. Every surface renders these with `object-fit:contain`, which scales the
*whole frame* — padding included — to fit its box. So the padded shots draw a
small phone marooned in empty space, while tightly-cropped shots (A56, S24+)
fill their box properly. That inconsistency is a property of the files, not the
CSS, so it is fixed here rather than papered over with per-image CSS.

`object-fit:cover` is NOT the answer: several images have zero padding and the
handset touches the frame edge, so cropping to fill would slice the phone.

What it does
------------
For each image: find the bounding box of everything that isn't near-white, add a
small even margin, and crop to it. Only background is removed — the handset is
never touched, and nothing is scaled or stretched. Images that are already tight
(margin below the threshold) are left byte-for-byte alone.

Originals are copied to static/img/_original/ before the first trim, so this is
reversible and re-runnable (it always re-trims from the pristine original).

Run:
    python build_phone_images.py            # trim
    python build_phone_images.py --dry-run  # report only, write nothing
"""

import os
import shutil
import sys

from PIL import Image

IMG_DIR = "static/img"
BACKUP_DIR = os.path.join(IMG_DIR, "_original")

# A pixel is "background" when every channel is at least this bright.
WHITE_LEVEL = 243
# Keep this much of the shortest side as breathing room around the phone.
MARGIN_FRAC = 0.04
# Don't rewrite an image whose padding is already smaller than this.
MIN_TRIM_FRAC = 0.03

EXTS = (".webp", ".png", ".jpg", ".jpeg")


def content_box(im: Image.Image):
    """Bounding box of the non-white content, or None if the image is blank."""
    rgb = im.convert("RGB")
    # Everything brighter than WHITE_LEVEL becomes white, the rest black, so
    # getbbox() (which trims black) returns the handset's bounds.
    mask = rgb.point(lambda v: 255 if v > WHITE_LEVEL else 0).convert("L")
    return mask.point(lambda v: 0 if v == 255 else 255).getbbox()


def main() -> None:
    dry = "--dry-run" in sys.argv
    os.makedirs(BACKUP_DIR, exist_ok=True)

    names = sorted(
        f for f in os.listdir(IMG_DIR)
        if f.lower().endswith(EXTS) and os.path.isfile(os.path.join(IMG_DIR, f))
    )

    trimmed = skipped = failed = 0
    print("{:<18} {:>11} {:>11} {:>7}  {}".format(
        "IMAGE", "BEFORE", "AFTER", "SAVED", "NOTE"))
    print("-" * 66)

    for name in names:
        path = os.path.join(IMG_DIR, name)
        backup = os.path.join(BACKUP_DIR, name)

        # Always work from the pristine original so re-runs never compound.
        if os.path.exists(backup):
            source = backup
        else:
            source = path

        try:
            im = Image.open(source)
            im.load()
        except Exception as exc:
            print("{:<18} {:>11}  cannot read: {}".format(name, "-", exc))
            failed += 1
            continue

        w, h = im.size
        box = content_box(im)
        if not box:
            print("{:<18} {:>11} {:>11} {:>7}  blank - left alone".format(
                name, f"{w}x{h}", f"{w}x{h}", "0%"))
            skipped += 1
            continue

        pad = min(box[0], box[1], w - box[2], h - box[3])
        if pad / min(w, h) < MIN_TRIM_FRAC:
            print("{:<18} {:>11} {:>11} {:>7}  already tight".format(
                name, f"{w}x{h}", f"{w}x{h}", "0%"))
            skipped += 1
            continue

        margin = int(min(w, h) * MARGIN_FRAC)
        crop = (
            max(0, box[0] - margin), max(0, box[1] - margin),
            min(w, box[2] + margin), min(h, box[3] + margin),
        )
        out = im.crop(crop)
        saved = 100 * (1 - (out.size[0] * out.size[1]) / (w * h))

        print("{:<18} {:>11} {:>11} {:>6.0f}%  trimmed".format(
            name, f"{w}x{h}", f"{out.size[0]}x{out.size[1]}", saved))

        if not dry:
            if not os.path.exists(backup):
                shutil.copy2(path, backup)
            fmt = "WEBP" if name.lower().endswith(".webp") else None
            if fmt:
                out.save(path, fmt, quality=90, method=6)
            else:
                out.save(path)
        trimmed += 1

    print()
    print("trimmed {} | already tight {} | unreadable {}{}".format(
        trimmed, skipped, failed, "   (dry run - nothing written)" if dry else ""))
    if not dry and trimmed:
        print("originals backed up in", BACKUP_DIR)


if __name__ == "__main__":
    main()
