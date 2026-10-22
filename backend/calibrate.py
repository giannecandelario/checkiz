"""Measure your own genuine and edited receipts, and print a table the README accepts.

  python calibrate.py --real samples_real/ --edited samples_edited/          # text
  python calibrate.py --real samples_real/ --edited samples_edited/ --markdown
  python calibrate.py --real samples_real/ --edited samples_edited/ --at 6.5 5.2

`--markdown` prints the table shape docs/CALIBRATION.md tells you to paste, and `--at`
answers the only question that matters about a threshold: how many genuine receipts it
would have cried wolf about, and how many edited ones it would have missed.

Run it inside the Docker image, which has the Tesseract this repo's tests do not:

  docker run --rm -v "$PWD":/work -w /work/backend checkiz \\
    python calibrate.py --real /work/samples_real --edited /work/samples_edited --markdown

Every number it prints was measured on the images you pointed it at. It has no opinions:
a group with no samples prints no numbers, a box it could not find prints `no boxes`
rather than a score of 0.00 (which would read like a clean receipt), and the suggested
thresholds only appear when the two groups actually separate. Send the samples through
Messenger or Viber before measuring them, because that is the copy the seller receives.
"""
import argparse
import statistics
import sys
import time
from datetime import date
from pathlib import Path

from app.config import OCR_CONFIDENCE_MIN
from app.forensics import ELA_THRESHOLD, SHARPNESS_THRESHOLD, ela_ratio, sharpness_ratio
from app.parser import load_image, locate_boxes, ocr_confidence, ocr_engine, parse_fields, run_ocr

IMAGES = (".png", ".jpg", ".jpeg", ".webp")


def measure(path: Path):
    """One image, as far as this machine can read it. None means there was no image
    in there at all."""
    started = time.perf_counter()
    img = load_image(path.read_bytes())
    if img is None:
        return None
    text, data = run_ocr(img)
    f = parse_fields(text)
    boxes = locate_boxes(data, f["amount"], f["ref"])
    # ela_ratio/sharpness_ratio return 0.0 for no boxes, and 0.0 is the *cleanest*
    # score they can produce. Printing it would flatter an unreadable image.
    return {
        "name": path.name,
        "ref": f["ref"],
        "amount": f["amount"],
        "ela": round(ela_ratio(img, boxes), 2) if boxes else None,
        "sharp": round(float(sharpness_ratio(img, boxes)), 2) if boxes else None,
        "read": ocr_confidence(data),
        "boxes": len(boxes),
        "ms": round((time.perf_counter() - started) * 1000),
    }


def folder(dirpath, group):
    out = []
    for p in sorted(Path(dirpath).glob("*")):
        if p.suffix.lower() not in IMAGES:
            continue
        m = measure(p)
        if m is None:
            print(f"{p.name:34} NOT READ - no image in this file", file=sys.stderr)
            continue
        m["group"] = group
        out.append(m)
    return out


def fmt(v, spec=".2f"):
    return format(v, spec) if isinstance(v, (int, float)) else "-"


def cells(m):
    return [m["name"], m["group"],
            fmt(m["ela"]), fmt(m["sharp"]),
            (fmt(m["read"], ".1f") if m["read"] is not None else "no read"),
            ("no boxes" if not m["boxes"] else
             ("FLAGGED" if m["ela"] > ELA_THRESHOLD or m["sharp"] > SHARPNESS_THRESHOLD else "not flagged")),
            f"{m['ms']} ms"]


HEADER = ["Sample", "Group", "ELA", "Sharpness", "Read score",
          "Flagged at these thresholds", "Time"]


def summary(rows, label):
    if not rows:
        print(f"{label}: no samples. Nothing is measured for this group, and no "
              f"comparison with it means anything.")
        return
    for key, name in (("ela", "ELA"), ("sharp", "Sharpness"), ("read", "Read score")):
        vals = [r[key] for r in rows if isinstance(r[key], (int, float))]
        if not vals:
            print(f"{label} {name}: nothing readable")
            continue
        print(f"{label} {name}: n={len(vals)} of {len(rows)}  "
              f"min {min(vals):.2f}  median {statistics.median(vals):.2f}  max {max(vals):.2f}")
    unread = [r["name"] for r in rows if not r["boxes"]]
    if unread:
        print(f"{label}: no amount/reference box found in {', '.join(unread)} - "
              f"forensics need the field boxes, so those rows carry no ELA or sharpness")


def suggest(name, env, real, edited):
    """One candidate threshold, and why there isn't one."""
    rv = [r[name] for r in real if isinstance(r[name], (int, float))]
    ev = [r[name] for r in edited if isinstance(r[name], (int, float))]
    if not rv or not ev:
        print(f"{env}: no suggestion - {len(rv)} readable real value(s) and {len(ev)} "
              f"readable edited value(s)")
        return
    hi_real, lo_edit = max(rv), min(ev)
    apart = hi_real < lo_edit
    if len(rv) < 3 or len(ev) < 3:
        print(f"{env}: n={len(rv)}/{len(ev)} is too few to set a threshold on. "
              + (f"The groups do not overlap here (real max {hi_real:.2f} < edited min "
                 f"{lo_edit:.2f}), but two samples that happen to differ is not a signal - "
                 "measure more before changing it."
                 if apart else
                 f"They overlap (real max {hi_real:.2f} >= edited min {lo_edit:.2f}), and "
                 "with this few samples even that is not yet a conclusion."))
        return
    if apart:
        print(f"{env}: groups separate. Candidate {(hi_real + lo_edit) / 2:.2f} "
              f"(real max {hi_real:.2f}, edited min {lo_edit:.2f}, n={len(rv)}/{len(ev)}).")
    else:
        print(f"{env}: groups overlap (real max {hi_real:.2f} >= edited min "
              f"{lo_edit:.2f}, n={len(rv)}/{len(ev)}); this signal alone cannot separate "
              f"them, and the README must keep saying so.")


def rates(real, edited, ela_at, sharp_at):
    """What these thresholds would actually have done to the samples measured.

    Reported as counts, not percentages, because with six samples a percentage makes a
    single photo look like a 17 % error rate. `missed` is the number that matters most:
    an edited receipt nobody flagged is the one that ships."""
    def flagged(m):
        return (m["ela"] is not None and m["ela"] > ela_at) or \
               (m["sharp"] is not None and m["sharp"] > sharp_at)

    def both(group):
        read = [m for m in group if m["boxes"]]
        return len(read), sum(1 for m in read if flagged(m))

    n_real, hit_real = both(real)
    n_edit, hit_edit = both(edited)
    print(f"\nAt ELA > {ela_at} or sharpness > {sharp_at}:")
    print(f"  genuine receipts flagged (false alarms): {hit_real} of {n_real}")
    print(f"  edited receipts flagged (caught):        {hit_edit} of {n_edit}")
    print(f"  edited receipts NOT flagged (missed):    {n_edit - hit_edit} of {n_edit}")
    if n_edit - hit_edit:
        print("  missed: " + ", ".join(m["name"] for m in edited
                                       if m["boxes"] and not flagged(m)))
    if hit_real:
        print("  false alarms: " + ", ".join(m["name"] for m in real
                                             if m["boxes"] and flagged(m)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", required=True, help="folder of genuine receipts")
    ap.add_argument("--edited", required=True, help="folder of edited receipts")
    ap.add_argument("--markdown", action="store_true",
                    help="print the README-shaped table (paste it, or redirect the whole run)")
    ap.add_argument("--at", nargs=2, metavar=("ELA", "SHARPNESS"), type=float,
                    help="report what these two thresholds would have caught and missed "
                         "in the samples measured, counts only")
    a = ap.parse_args()

    engine = ocr_engine()
    if engine is None:
        print("No Tesseract on this machine, so there is nothing to measure: no text is "
              "read, no field boxes exist, and ELA/sharpness would print as nothing. "
              "Run it in the Docker image - the command is at the top of this file.")
        sys.exit(2)

    real = folder(a.real, "real")
    edited = folder(a.edited, "edited")
    rows = real + edited
    print(f"# Tesseract {engine}  run {date.today().isoformat()}  "
          f"thresholds ELA > {ELA_THRESHOLD}, sharpness > {SHARPNESS_THRESHOLD}  "
          f"retake floor {OCR_CONFIDENCE_MIN}  "
          f"n real={len(real)} edited={len(edited)}")
    for m in rows:
        print("  ".join(f"{k}={v}" for k, v in (
            ("file", m["name"]), ("ref", m["ref"]), ("amount", m["amount"]),
            ("ela", m["ela"]), ("sharp", m["sharp"]), ("read", m["read"]),
            ("boxes", m["boxes"]), ("ms", m["ms"]))))
    print()
    summary(real, "real")
    summary(edited, "edited")
    print()
    suggest("ela", "CHECKIZ_ELA_THRESHOLD", real, edited)
    suggest("sharp", "CHECKIZ_SHARPNESS_THRESHOLD", real, edited)

    if a.at:
        rates(real, edited, a.at[0], a.at[1])

    if a.markdown:
        print("\n| " + " | ".join(HEADER) + " |")
        print("|" + "---|" * len(HEADER))
        for m in rows:
            print("| " + " | ".join(cells(m)) + " |")
        print(f"\nRun {date.today().isoformat()} on {len(real)} genuine and "
              f"{len(edited)} edited sample(s), Tesseract {engine}, thresholds "
              f"ELA > {ELA_THRESHOLD} / sharpness > {SHARPNESS_THRESHOLD}.")
