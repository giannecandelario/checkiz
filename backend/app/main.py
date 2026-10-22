import base64
import io
import os
from pathlib import Path

from fastapi import (Depends, FastAPI, File, Form, Header, HTTPException, Query,
                     Response, UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import cv2
import numpy as np
import qrcode
from pytesseract import TesseractNotFoundError
from pydantic import BaseModel

from .db import init_db
from .config import APP_PACKAGES
from .history import screenshot, to_entry
from .ingest import ingest_alert
from .ledger import parse_alert, list_entries
from .parser import ocr_engine
from . import qrph, qrstore
from .report import evidence, packing_csv
from .review import acknowledge, review_list
from .verify import get_stats, list_history, list_pending, verify_receipt

app = FastAPI(title="Checkiz")
# Prototype only: restrict origins and add an API key before real use.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def frontend_dir():
    """Where the dashboard pages live, or None when they are not next to this
    process. Serving them from the API is what makes one origin: the pages then
    never guess a port, a phone on the same network works without `?api=`, and a
    link that 404s is a real bug instead of a missing second web server.

    The second candidate is also what the Docker image resolves: WORKDIR is
    /app/backend, so this file is /app/backend/app/main.py and the sibling folder
    is /app/frontend."""
    candidates = [os.getenv("CHECKIZ_FRONTEND"),
                  Path(__file__).resolve().parents[2] / "frontend"]
    for c in candidates:
        if c and Path(c).is_dir():
            return str(c)
    return None

FRONTEND = frontend_dir()

@app.on_event("startup")
def startup():
    init_db()
    if not os.getenv("CHECKIZ_API_KEY"):
        print("WARNING: CHECKIZ_API_KEY is not set. Anyone who can reach this server can "
              "post fake payment alerts. Set it before using real money.")
    if ocr_engine() is None:
        print("WARNING: Tesseract is not installed or not on PATH, so no receipt can be read. "
              "Install tesseract-ocr or use the Docker image; /verify answers 503 until then.")
    if FRONTEND:
        print(f"Dashboard pages served from {FRONTEND} - open them at whatever address "
              "this server was started on, e.g. http://localhost:8000/")
    else:
        print("No frontend found - API only. Set CHECKIZ_FRONTEND to the folder with index.html.")

def require_key(x_api_key: str | None = Header(None), key: str | None = Query(None)):
    """Optional protection: set CHECKIZ_API_KEY to lock the ledger and history
    endpoints. Send it as the X-API-Key header (or ?key= for the overlay page)."""
    expected = os.getenv("CHECKIZ_API_KEY")
    if expected and (x_api_key or key) != expected:
        raise HTTPException(401, "Invalid or missing API key")

class SMSIn(BaseModel):
    text: str
    source: str = "sms"          # "sms" or "paste"

class NotificationIn(BaseModel):
    package: str                 # Android package that posted the notification
    text: str
    title: str = ""

@app.get("/health")
def health():
    """`name` lets a page tell Checkiz from whatever else happens to be listening
    on the port it was pointed at - the failure mode where another project's
    server answers with HTML and the dashboard says only 'could not reach'.

    `ocr` is the Tesseract version the process can actually run, or null. Without
    it a receipt cannot be read at all, and that is a fact about the server the
    seller needs before the first upload, not a verdict about the image."""
    return {"ok": True, "name": "checkiz", "ui": bool(FRONTEND), "ocr": ocr_engine()}

@app.post("/verify")
async def verify(file: UploadFile = File(...), order_id: str = Form(...)):
    if not order_id.strip():
        raise HTTPException(422, "Order ID is required - a receipt is settled against an order")
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(415, "Upload an image file")
    limit = int(float(os.getenv("CHECKIZ_MAX_UPLOAD_MB", 8)) * 1024 * 1024)
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, "Image too large")
    try:
        return verify_receipt(data, order_id)
    except TesseractNotFoundError:
        # Checked where it actually fails, not up front: a stubbed reader is a
        # perfectly good way to test the verdict rules on a machine with no OCR
        # installed. Nothing about the photo was judged here, and no verdict is
        # written, so this is an HTTP answer about the server.
        raise HTTPException(503, "This server cannot read any receipt: Tesseract is not "
                                 "installed or not on its PATH. Install tesseract-ocr, or run "
                                 "the Docker image. Nothing about this photo was checked.")

@app.post("/ledger/sms", dependencies=[Depends(require_key)])
def ledger_sms(body: SMSIn):
    """SMS or pasted alert. SMS sender IDs can be spoofed, so these entries are
    marked as lower trust than notifications read from the wallet app."""
    source = body.source if body.source in ("sms", "paste") else "sms"
    entry = parse_alert(body.text, source)
    if not entry:
        raise HTTPException(400, "Could not parse an incoming payment from that text")
    return ingest_alert(entry)

@app.post("/ledger/notification", dependencies=[Depends(require_key)])
def ledger_notification(body: NotificationIn):
    """Notification text read from the wallet app on the seller's phone. The package
    name is set by Android, not by the sender, so only allow-listed wallet apps count."""
    if body.package not in APP_PACKAGES:
        raise HTTPException(403, "Not a recognised wallet app")
    entry = parse_alert(f"{body.title}. {body.text}" if body.title else body.text, "app")
    if not entry:
        raise HTTPException(400, "Could not parse an incoming payment from that notification")
    return ingest_alert(entry)

@app.post("/ledger/paste", dependencies=[Depends(require_key)])
def ledger_paste(body: SMSIn):
    """Paste several alerts at once (blank-line separated), e.g. copied from the
    wallet's in-app inbox when SMS alerts are not arriving."""
    out = []
    for chunk in [c for c in body.text.replace("\r", "").split("\n\n") if c.strip()]:
        entry = parse_alert(chunk, "paste")
        if entry:
            out.append(ingest_alert(entry))
    if not out:
        raise HTTPException(400, "No incoming payments found in that text")
    return {"added": sum(1 for e in out if e["stored"]), "entries": out}

@app.post("/ledger/history-screenshot", dependencies=[Depends(require_key)])
async def ledger_history_screenshot(file: UploadFile = File(...)):
    """The fallback when no alert reaches the server at all: a screenshot of the
    SELLER'S OWN wallet Transactions/Activity screen, read row by row into the ledger.

    `source="history"` is the lowest-trust source there is - words taken off an image
    by OCR, unsigned, and a reference can land on the wrong amount when the list is
    crooked. It is never treated as the wallet confirming a payment: `app_check_warning`
    still flags any payment at or above CHECKIZ_CONFIRM_ABOVE that was not read from a
    wallet app notification, including one seen only here."""
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(415, "Upload an image file")
    limit = int(float(os.getenv("CHECKIZ_MAX_UPLOAD_MB", 8)) * 1024 * 1024)
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, "Image too large")
    try:
        found = screenshot(data)
    except TesseractNotFoundError:
        raise HTTPException(503, "This server cannot read any screenshot: Tesseract is not "
                                 "installed or not on its PATH. Install tesseract-ocr, or run "
                                 "the Docker image. Nothing was added to the ledger.")
    if found is None:
        raise HTTPException(415, "That file is not an image this server can decode")
    rows, skipped = found
    if not rows:
        # Telling the seller that figures were read and refused is the difference
        # between "wrong screen" and "the parser was not sure", which they can act
        # on differently.
        why = f" {len(skipped)} figure(s) read and refused: " + \
              ", ".join(sorted({s["reason"] for s in skipped})) + "." if skipped else ""
        raise HTTPException(400, "No incoming payment could be placed in that screen." + why +
                            " Send a screenshot of the wallet's own Transactions/Activity "
                            "list with the whole list on screen and the text sharp enough "
                            "to read.")
    out = [ingest_alert(to_entry(r)) for r in rows]
    return {"added": sum(1 for e in out if e["stored"]),
            "entries": out, "source": "history",
            # The first copy of a reference wins, so a transaction the ledger already
            # had (from an SMS, or from the same screenshot an hour ago) stores nothing.
            # Counting those as added would tell the seller they were paid again.
            "already_in_ledger": [e["ref"] for e in out if not e["stored"]],
            # Rows refused and why, so a payment the parser was unsure about is
            # visible instead of silently absent.
            "skipped": skipped,
            # Payments *this screen* added that nothing matched, so the seller sees
            # them without clicking through the ledger to find which ones. A reference
            # the ledger already had is not listed again: nothing about it changed here.
            "unmatched": [e["ref"] for e in out if e["stored"]
                          and not e["resolved"] and not e["settled"]]}

@app.get("/ledger", dependencies=[Depends(require_key)])
def ledger():
    return list_entries()

@app.get("/history", dependencies=[Depends(require_key)])
def history(limit: int = 20):
    return list_history(min(max(limit, 1), 100))

@app.get("/pending", dependencies=[Depends(require_key)])
def pending():
    return list_pending()

@app.get("/stats", dependencies=[Depends(require_key)])
def stats():
    return get_stats()


# ---- QR Ph tools -----------------------------------------------------------

class QRPayload(BaseModel):
    payload: str

class QRGenerate(BaseModel):
    order_id: str
    amount: float
    centavo_code: bool = False

def _decode_image(data: bytes):
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    det = cv2.QRCodeDetector()
    text, _, _ = det.detectAndDecode(img)
    if not text:  # retry on an upscaled copy; phone photos often need it
        text, _, _ = det.detectAndDecode(cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
    return text or None

def _public(info):
    # never return account identifiers, only what a seller needs to recognise the QR
    if not info:
        return None
    return {k: info[k] for k in ("merchant_name", "merchant_city", "point_of_initiation",
                                 "amount", "guis", "bill_number", "reference_label")}

@app.post("/qr/decode", dependencies=[Depends(require_key)])
async def qr_decode(file: UploadFile = File(...)):
    """Read the payload from a photo or upload of your own QR (used to register it)."""
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(415, "Upload an image file")
    payload = _decode_image(await file.read(8 * 1024 * 1024))
    if not payload:
        return {"payload": None, "message": "No QR code found. Retake the photo closer and flatter."}
    return {"payload": payload, "message": "ok"}

@app.post("/qr/register", dependencies=[Depends(require_key)])
def qr_register(body: QRPayload):
    try:
        info = qrph.analyze(body.payload)
    except ValueError:
        raise HTTPException(400, "Not a payment QR")
    if not (info["is_emv"] and info["crc_valid"]):
        raise HTTPException(400, "Not a valid payment QR (format or checksum)")
    qrstore.set_seller_qr(body.payload.strip())
    return {"registered": True, "info": _public(info)}

@app.get("/qr/seller", dependencies=[Depends(require_key)])
def qr_seller():
    p = qrstore.get_seller_qr()
    return {"registered": bool(p), "info": _public(qrph.analyze(p)) if p else None}

@app.post("/qr/generate", dependencies=[Depends(require_key)])
def qr_generate(body: QRGenerate):
    seller = qrstore.get_seller_qr()
    if not seller:
        raise HTTPException(400, "Register your QR Ph first")
    try:
        amount = qrstore.next_free_amount(body.amount) if body.centavo_code else round(body.amount, 2)
        payload = qrph.build_dynamic(seller, amount, body.order_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    qrstore.save_order(body.order_id, amount, body.centavo_code)
    buf = io.BytesIO()
    qrcode.make(payload).save(buf, format="PNG")
    png = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return {"order_id": body.order_id, "amount": amount, "payload": payload, "png": png}

@app.get("/qr/orders", dependencies=[Depends(require_key)])
def qr_orders():
    return qrstore.list_orders()

@app.get("/orders", dependencies=[Depends(require_key)])
def orders():
    """Live order board: OPEN orders waiting for payment, PAID ones settled."""
    return qrstore.list_orders()


# ---- Reconciliation --------------------------------------------------------

@app.get("/review", dependencies=[Depends(require_key)])
def review():
    """The orders Checkiz could not settle on its own: fakes, duplicates,
    receipts still waiting for a payment, QRs that expired unpaid, and payments
    confirmed only by a spoofable alert source."""
    return review_list()

@app.post("/review/{order_id}", dependencies=[Depends(require_key)])
def review_ack(order_id: str):
    """Take an order off the review list. A newer verdict for it puts it back."""
    return acknowledge(order_id)

@app.get("/orders/packing.csv", dependencies=[Depends(require_key)])
def packing():
    """Paid orders as a CSV checklist, ready-to-pick straight off the screen."""
    return Response(packing_csv(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="packing-list.csv"'})

@app.get("/orders/{order_id}/evidence", dependencies=[Depends(require_key)])
def order_evidence(order_id: str):
    """Timestamped record of what happened to one order, for disputing it later.
    Never includes the raw alert text or a receipt image."""
    return evidence(order_id)


# ---- The dashboard pages ----------------------------------------------------
# Mounted last so it only answers paths no API route claimed. This is a catch-all
# for files, not a proxy: nothing here reads or writes money.

if FRONTEND:
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="dashboard")
