# Checkiz Implementation Guide

Step-by-step build of the MVP described in `BLUEPRINT.md`. It stops at the MVP: the alert feed, order binding, QR Ph tools and reconciliation reports added later are documented in `README.md` and `BLUEPRINT.md`, not here.

**Assumed stack** (change if you prefer another): Python 3.10+, FastAPI, Tesseract, OpenCV, SQLite, plain HTML/JS frontend.

## 1. Setup

Install Tesseract:

```bash
# Ubuntu/Debian
sudo apt install tesseract-ocr
# macOS
brew install tesseract
# Windows: install from https://github.com/UB-Mannheim/tesseract/wiki and add it to PATH
```

Project layout:

```
checkiz/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── db.py
│   │   ├── parser.py
│   │   ├── forensics.py
│   │   ├── ledger.py
│   │   └── verify.py
│   ├── tests/
│   │   └── test_verify.py
│   ├── seed.py
│   └── requirements.txt
├── frontend/
│   └── index.html
└── samples/            # real, edited, and duplicate test receipts
```

`backend/requirements.txt`:

```
fastapi
uvicorn[standard]
python-multipart
pytesseract
opencv-python-headless
numpy
pillow
pytest
```

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
touch app/__init__.py
```

## 2. Database (`app/db.py`)

```python
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "checkiz.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    ref TEXT PRIMARY KEY,
    amount REAL NOT NULL,
    received_at TEXT,
    sender TEXT,
    raw TEXT
);
CREATE TABLE IF NOT EXISTS claims (
    ref TEXT PRIMARY KEY,
    order_id TEXT,
    claimed_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
```

## 3. OCR and Parsing (`app/parser.py`)

```python
import re
import cv2
import numpy as np
import pytesseract

AMOUNT_RE = re.compile(r"(?:PHP|₱|P)\s?([\d,]+\.\d{2})")
REF_RE = re.compile(r"(?<!\d)(\d{4}\s?\d{3}\s?\d{6})(?!\d)")  # 13 digits, grouped 4-3-6

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
    return {"amount": amount, "ref": ref}

def locate_boxes(data: dict, amount: float | None, ref: str | None, scale: int = 2):
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
```

Receipt layouts and SMS text differ between GCash and Maya. Run OCR on 5 to 10 real receipts from each and adjust the regexes to match what Tesseract actually returns.

## 4. Forensics (`app/forensics.py`)

```python
import cv2
import numpy as np

def ela_ratio(img, boxes, quality=90) -> float:
    """Mean recompression error inside field boxes relative to the whole image."""
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    recompressed = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    diff = cv2.absdiff(img, recompressed).astype(np.float32).mean(axis=2)
    base = float(diff.mean()) + 1e-6
    ratios = []
    for x, y, w, h in boxes:
        region = diff[max(y, 0):y + h, max(x, 0):x + w]
        if region.size:
            ratios.append(float(region.mean()) / base)
    return max(ratios) if ratios else 0.0

def sharpness_ratio(img, boxes, pad=20) -> float:
    """Laplacian variance of field boxes vs the area around them."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape
    ratios = []
    for x, y, w, h in boxes:
        inner = gray[y:y + h, x:x + w]
        y0, y1 = max(y - pad, 0), min(y + h + pad, H)
        x0, x1 = max(x - pad, 0), min(x + w + pad, W)
        outer = gray[y0:y1, x0:x1]
        if inner.size and outer.size:
            v_in = cv2.Laplacian(inner, cv2.CV_64F).var()
            v_out = cv2.Laplacian(outer, cv2.CV_64F).var() + 1e-6
            ratios.append(v_in / v_out)
    return max(ratios) if ratios else 0.0

# Starting thresholds. Tune these on your own real and edited samples.
ELA_THRESHOLD = 2.5
SHARPNESS_THRESHOLD = 6.0

def forensic_report(img, boxes) -> dict:
    ela = ela_ratio(img, boxes)
    sharp = sharpness_ratio(img, boxes)
    return {
        "ela": round(ela, 2),
        "sharpness": round(sharp, 2),
        "flagged": ela > ELA_THRESHOLD or sharp > SHARPNESS_THRESHOLD,
    }
```

The thresholds are guesses. Collect a small set of genuine and edited screenshots, print both scores for each, and pick thresholds that separate them. Sending samples through Messenger first will show you how much compression affects the numbers.

## 5. Ledger (`app/ledger.py`)

```python
import re
from .db import get_conn

SMS_AMOUNT = re.compile(r"(?:PHP|₱)\s?([\d,]+\.\d{2})", re.I)
SMS_REF = re.compile(r"Ref(?:erence)?\.?\s*(?:No\.?|#)?\s*:?\s*(\d[\d\s]{11,16}\d)", re.I)
SMS_SENDER = re.compile(r"from\s+(.+?)(?:\s+w/|\s+with|\.|\s+Ref|$)", re.I)

def parse_sms(text: str) -> dict | None:
    a, r = SMS_AMOUNT.search(text), SMS_REF.search(text)
    if not (a and r):
        return None
    ref = re.sub(r"\s", "", r.group(1))
    if len(ref) != 13:
        return None
    s = SMS_SENDER.search(text)
    return {
        "ref": ref,
        "amount": float(a.group(1).replace(",", "")),
        "sender": s.group(1).strip() if s else None,
        "raw": text,
    }

def add_entry(entry: dict):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ledger (ref, amount, received_at, sender, raw) "
            "VALUES (?, ?, datetime('now'), ?, ?)",
            (entry["ref"], entry["amount"], entry.get("sender"), entry.get("raw")),
        )

def find_entry(ref: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM ledger WHERE ref = ?", (ref,)).fetchone()

def list_entries():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM ledger ORDER BY received_at DESC")]
```

## 6. Verdict Engine (`app/verify.py`)

```python
from .db import get_conn
from .ledger import find_entry
from .parser import load_image, run_ocr, parse_fields, locate_boxes
from .forensics import forensic_report

def get_claim(ref: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM claims WHERE ref = ?", (ref,)).fetchone()

def add_claim(ref: str, order_id: str):
    with get_conn() as conn:
        conn.execute("INSERT INTO claims (ref, order_id) VALUES (?, ?)", (ref, order_id))

def result(status, message, fields, forensics, order_id):
    return {"status": status, "message": message, "fields": fields,
            "forensics": forensics, "order_id": order_id}

def verify_receipt(image_bytes: bytes, order_id: str) -> dict:
    img = load_image(image_bytes)
    if img is None:
        return result("SUSPECTED_FAKE", "Unreadable image", {}, {}, order_id)

    text, data = run_ocr(img)
    fields = parse_fields(text)
    ref, amount = fields["ref"], fields["amount"]

    # 1. Structure
    if not ref:
        return result("SUSPECTED_FAKE", "Missing or invalid reference number",
                      fields, {}, order_id)

    # 2. Duplicate
    claim = get_claim(ref)
    if claim:
        return result("DUPLICATE",
                      f"Ref {ref} was already claimed on Order #{claim['order_id']}",
                      fields, {}, order_id)

    # Forensics
    boxes = locate_boxes(data, amount, ref)
    forensics = forensic_report(img, boxes)

    # 3. Ledger
    entry = find_entry(ref)
    if entry and amount is not None and abs(entry["amount"] - amount) > 0.01:
        return result("SUSPECTED_FAKE",
                      f"Amount mismatch: receipt {amount:.2f}, ledger {entry['amount']:.2f}",
                      fields, forensics, order_id)

    # 4. Forensic flag
    if forensics["flagged"]:
        return result("SUSPECTED_FAKE",
                      "Image shows signs of editing on the amount or reference fields",
                      fields, forensics, order_id)

    # 5. Verified
    if entry:
        add_claim(ref, order_id)
        return result("VERIFIED",
                      f"Ref {ref} matched incoming payment of {entry['amount']:.2f}",
                      fields, forensics, order_id)

    # 6. Pending
    return result("PENDING_MATCH",
                  "Receipt looks valid but no matching payment in the ledger yet",
                  fields, forensics, order_id)
```

**Rule 4 above is the MVP as first built, and the shipped engine no longer works that way.** A forensic flag on its own now returns `PENDING_MATCH` with the flag as a `warning` and still goes on the pending list, because nothing has calibrated the score against a genuine receipt - a photographed genuine page measures *lower* than the unsaved file. See `BLUEPRINT.md` section 7 for the current rule order and `app/verify.py` for the code.

## 7. API (`app/main.py`)

```python
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .db import init_db
from .ledger import parse_sms, add_entry, list_entries
from .verify import verify_receipt

app = FastAPI(title="Checkiz")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    init_db()

class SMSIn(BaseModel):
    text: str

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/verify")
async def verify(file: UploadFile = File(...), order_id: str = Form(...)):
    data = await file.read()
    return verify_receipt(data, order_id)

@app.post("/ledger/sms")
def ledger_sms(body: SMSIn):
    entry = parse_sms(body.text)
    if not entry:
        raise HTTPException(400, "Could not parse SMS")
    add_entry(entry)
    return entry

@app.get("/ledger")
def ledger():
    return list_entries()
```

Run it:

```bash
uvicorn app.main:app --reload
```

Restrict CORS origins and protect the ledger endpoints with an API key before any real use.

## 8. Seed Data (`seed.py`)

Use reference numbers that match your real test receipts.

```python
from app.db import init_db
from app.ledger import add_entry

init_db()
add_entry({"ref": "1002849130490", "amount": 1250.00, "sender": "JUAN D.", "raw": "demo"})
add_entry({"ref": "2003951240871", "amount": 850.00, "sender": "MARIA S.", "raw": "demo"})
print("Seeded ledger")
```

```bash
python seed.py
```

## 9. Frontend (`frontend/index.html`)

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Checkiz</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 560px; margin: 40px auto; padding: 0 16px; }
  #drop { border: 2px dashed #888; padding: 40px; text-align: center; border-radius: 8px; }
  #drop.over { background: #f0f0f0; }
  input { padding: 8px; margin: 12px 0; width: 100%; box-sizing: border-box; }
  #banner { margin-top: 20px; padding: 16px; border-radius: 8px; color: #fff; display: none; }
  .VERIFIED { background: #2e7d32; } .PENDING_MATCH { background: #f9a825; color: #000 !important; }
  .SUSPECTED_FAKE { background: #c62828; } .DUPLICATE { background: #ef6c00; }
  small { display: block; margin-top: 8px; opacity: .85; }
</style>
</head>
<body>
<h1>Checkiz</h1>
<input id="order" placeholder="Order ID" value="101">
<div id="drop">Drop receipt screenshot here or click to choose</div>
<input id="file" type="file" accept="image/*" hidden>
<div id="banner"></div>
<script>
const API = "http://localhost:8000";
const drop = document.getElementById("drop"), fileInput = document.getElementById("file");
drop.onclick = () => fileInput.click();
drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); send(e.dataTransfer.files[0]); };
fileInput.onchange = () => send(fileInput.files[0]);

async function send(file) {
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  form.append("order_id", document.getElementById("order").value);
  const banner = document.getElementById("banner");
  banner.style.display = "block"; banner.className = ""; banner.textContent = "Checking...";
  try {
    const res = await fetch(API + "/verify", { method: "POST", body: form });
    const r = await res.json();
    banner.className = r.status;
    banner.innerHTML = `<strong>${r.status.replace("_", " ")}</strong><br>${r.message}` +
      `<small>ELA ${r.forensics.ela ?? "-"} | Sharpness ${r.forensics.sharpness ?? "-"}</small>`;
  } catch (err) {
    banner.className = "SUSPECTED_FAKE"; banner.textContent = "Could not reach the server";
  }
}
</script>
</body>
</html>
```

This is the guide's first draft of the page, and it guesses the API origin. What ships
is different in two ways: `frontend/api.js` decides the origin once for all three pages
(own origin, else `?api=`, else `localhost:8000`) and explains a wrong answer instead of
saying "could not reach the server", and the backend serves `frontend/` itself. So
`uvicorn app.main:app` and then open http://localhost:8000/ - no second web server.

## 9a. Reference number note

The example reference in the original concept (`1002 8491 3049`) has 12 digits, but this guide validates 13 digits. Check real GCash and Maya receipts and set the pattern in `parser.py` and `ledger.py` to what they actually show, including how the digits are grouped.

## 10. Tests (`tests/test_verify.py`)

```python
from app.ledger import parse_sms
from app.parser import parse_fields

def test_parse_fields():
    f = parse_fields("Amount PHP 1,250.00\nRef No. 1002 849 130490")
    assert f["amount"] == 1250.00
    assert f["ref"] == "1002849130490"

def test_parse_sms():
    sms = "You have received PHP 1,250.00 of GCash from JUAN D. Ref. No. 1002 849 130490."
    e = parse_sms(sms)
    assert e and e["ref"] == "1002849130490" and e["amount"] == 1250.00

def test_parse_sms_rejects_garbage():
    assert parse_sms("hello world") is None
```

```bash
pytest
```

## 11. Demo Script

Prepare three images in `samples/`: a real receipt (`real.png`), an edited copy of it with a changed amount or reference (`edited.png`), and the real receipt again. Make sure the real receipt's reference and amount are in the ledger.

| Step | Action | Expected |
|---|---|---|
| 1 | Upload `real.png` as Order 101 | VERIFIED |
| 2 | Upload `edited.png` as Order 102 | SUSPECTED FAKE (reference not found, amount mismatch, or forensic flag) |
| 3 | Upload `real.png` again as Order 103 | DUPLICATE, claimed on Order #101 |
| 4 | POST a new SMS to `/ledger/sms`, then upload a matching receipt | VERIFIED |
| 5 | Upload a valid receipt whose SMS has not arrived | PENDING MATCH |

Rehearse with the exact files you'll use. Run OCR on them first and confirm the fields parse correctly.

## 12. One-Day Build Plan

| Block | Task |
|---|---|
| 1 | Environment, project skeleton, database, seed data |
| 2 | OCR and field parsing tuned on real receipts |
| 3 | Ledger, duplicate check, verdict engine, `/verify` |
| 4 | Frontend and end-to-end test of the three demo cases |
| 5 | Forensic thresholds tuned on real and edited samples |
| 6 | Tests, README polish, demo rehearsal |

Cut forensics tuning before cutting ledger matching or duplicate detection if time runs short. Those two give deterministic results and carry the demo.

## 13. After the MVP

- SMS forwarding from the seller's phone to `/ledger/sms`
- OBS browser-source overlay that polls recent verdicts
- QR Ph code generator with the order ID in the transaction note
- Messenger / Viber webhook that calls `/verify`
- API key auth and per-seller ledgers
