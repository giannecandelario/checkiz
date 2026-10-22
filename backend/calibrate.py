"""Tune forensic thresholds on your own screenshots.

  python calibrate.py --real samples_real/ --edited samples_edited/

Prints ELA and sharpness for every image and, if the two groups separate,
suggests thresholds. Send the samples through Messenger/Viber first so the
numbers reflect real-world compression."""
import argparse
from pathlib import Path

from app.forensics import ela_ratio, sharpness_ratio
from app.parser import load_image, locate_boxes, parse_fields, run_ocr

def scores(folder):
    out = []
    for p in sorted(Path(folder).glob("*")):
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        img = load_image(p.read_bytes())
        if img is None:
            continue
        text, data = run_ocr(img)
        f = parse_fields(text)
        boxes = locate_boxes(data, f["amount"], f["ref"])
        e, s = ela_ratio(img, boxes), sharpness_ratio(img, boxes)
        print(f"{p.name:30} ref={f['ref']} amount={f['amount']} ela={e:.2f} sharp={s:.2f} boxes={len(boxes)}")
        out.append((e, s))
    return out

def suggest(name, real, edited):
    if not real or not edited:
        return
    hi_real, lo_edit = max(real), min(edited)
    if hi_real < lo_edit:
        print(f"{name}: groups separate. Suggested threshold ~{(hi_real + lo_edit) / 2:.2f}")
    else:
        print(f"{name}: groups overlap (real max {hi_real:.2f} >= edited min {lo_edit:.2f}); this signal alone can't separate them")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", required=True)
    ap.add_argument("--edited", required=True)
    a = ap.parse_args()
    print("== real =="); r = scores(a.real)
    print("== edited =="); e = scores(a.edited)
    suggest("ELA (CHECKIZ_ELA_THRESHOLD)", [x[0] for x in r], [x[0] for x in e])
    suggest("Sharpness (CHECKIZ_SHARPNESS_THRESHOLD)", [x[1] for x in r], [x[1] for x in e])
