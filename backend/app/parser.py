import re
import cv2
import numpy as np
import pytesseract

from .config import REF_LENGTH

AMOUNT_RE = re.compile(r"(?:PHP|₱|P)\s?([\d,]+\.\d{2})")
REF_RE = re.compile(rf"(?<!\d)(\d(?: ?\d){{{REF_LENGTH - 1}}})(?!\d)")  # REF_LENGTH digits, optional single spaces
# Date and time are only read as strings; app/consistency.py decides what they
# mean, so a wallet that words them differently is a config change, not a code
# change. Receipts that show neither (or a photo where OCR misses them) simply
# produce no signal.
MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
DATE_RE = re.compile(rf"(\d{{4}}-\d{{2}}-\d{{2}}"
                     rf"|\d{{1,2}}[/.-]\d{{1,2}}[/.-]\d{{4}}"
                     rf"|\d{{1,2}} {MONTH} \d{{4}}"
                     rf"|{MONTH} \d{{1,2}},? \d{{4}})", re.IGNORECASE)
TIME_RE = re.compile(r"(?<![\d:.])(\d{1,2}:\d{2}(?::\d{2})? ?(?:[AP]\.?[Mm]\.?)?)(?![\d:])")

def load_image(data: bytes):
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def run_ocr(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
    text = pytesseract.image_to_string(gray)
    return text, data

def parse_fields(text: str) -> dict:
    amount = None
    m = AMOUNT_RE.search(text)
    if m:
        amount = float(m.group(1).replace(",", ""))
    ref = None
    r = REF_RE.search(text)
    if r:
        ref = re.sub(r"\s", "", r.group(1))
    d = DATE_RE.search(text)
    t = TIME_RE.search(text)
    return {"amount": amount, "ref": ref,
            "date": d.group(1) if d else None,
            "time": t.group(1).strip() if t else None}

def ocr_confidence(data: dict):
    """Tesseract's own mean confidence over the words it thinks it read, or None
    when it read nothing. A photo of a screen at an angle scores low on every
    token, which is a fact about the photo, not about the payment - so it becomes
    a "take it again" hint, never a verdict.

    Only rows that are both a word and scored count. On samples/real.png the
    reader returns 44 rows, 20 of them structure with no text at all; averaging
    every row gives 51.1 where the words alone give 94.5, and 51 is under the
    retake floor, so an unfiltered mean would tell a seller to retake every clean
    photo. An empty page is None rather than 0 for the same reason: no advice is
    honest advice about a picture the reader never saw."""
    try:
        confs = [int(c) for c, word in zip(data["conf"], data["text"])
                 if int(c) >= 0 and word.strip()]
    except (KeyError, TypeError, ValueError):
        return None
    if not confs:
        return None
    return round(sum(confs) / len(confs), 1)

def locate_boxes(data: dict, amount, ref, scale: int = 2):
    """Return (x, y, w, h) boxes in original-image coordinates for tokens
    that belong to the amount or the reference number."""
    boxes = []
    amount_digits = re.sub(r"\D", "", f"{amount:.2f}") if amount is not None else ""
    for i, word in enumerate(data["text"]):
        digits = re.sub(r"\D", "", word)
        if len(digits) < 3:
            continue
        in_ref = ref and digits in ref
        in_amount = amount_digits and digits in amount_digits
        if in_ref or in_amount:
            x, y, w, h = (data[k][i] // scale for k in ("left", "top", "width", "height"))
            boxes.append((x, y, w, h))
    return boxes
