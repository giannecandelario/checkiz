import base64
import io
import os
from fastapi import (Depends, FastAPI, File, Form, Header, HTTPException, Query,
                     Response, UploadFile)
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import qrcode
from pydantic import BaseModel

from .db import init_db
from .config import APP_PACKAGES
from .ingest import ingest_alert
from .ledger import parse_alert, list_entries
from . import qrph, qrstore
from .report import evidence, packing_csv
from .review import acknowledge, review_list
from .verify import get_stats, list_history, list_pending, verify_receipt

app = FastAPI(title="Checkiz")
# Prototype only: restrict origins and add an API key before real use.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    init_db()
    if not os.getenv("CHECKIZ_API_KEY"):
        print("WARNING: CHECKIZ_API_KEY is not set. Anyone who can reach this server can "
              "post fake payment alerts. Set it before using real money.")

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
    return {"ok": True}

@app.post("/verify")
async def verify(file: UploadFile = File(...), order_id: str = Form(...)):
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(415, "Upload an image file")
    limit = int(float(os.getenv("CHECKIZ_MAX_UPLOAD_MB", 8)) * 1024 * 1024)
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, "Image too large")
    return verify_receipt(data, order_id)

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
    return {"added": len(out), "entries": out}

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
