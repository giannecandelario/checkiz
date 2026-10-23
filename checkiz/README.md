# Checkiz

Order-bound payment checking for Filipino social commerce sellers.

**Target user:** small online sellers (MSMEs) on TikTok Live, Facebook, and Viber who take GCash/Maya payments by personal wallet, with no payment gateway and no one to watch the app during a rush.

Checkiz does two things. It settles orders straight from the seller's own payment alerts, and it checks receipt screenshots for the buyers who still send them. It sits between a buyer's payment submission and the seller's order fulfillment. It reads an uploaded GCash/Maya receipt, checks the image for tampering, and matches the reference number against the seller's incoming transaction log.

## The Problem

Sellers on TikTok Live, Facebook, Instagram, and Viber are targeted by the "Canva scam": buyers use Canva or Photoshop templates to fake GCash/Maya receipts in under 30 seconds, editing the amount, timestamp, and reference number. During live streams (50 to 200 orders per hour), sellers can't manually verify every 13-digit reference number, so they lose both inventory and shipping fees.

## How It Works

1. **Ingestion:** the buyer uploads a screenshot via a web widget, Messenger, or Viber bot.
2. **OCR and parsing:** extracts amount, reference number, timestamp, and recipient.
3. **Tampering analysis:**
   - Font check: verifies font family, size, and kerning against GCash/Maya UI specs.
   - Compression check: detects localized artifacts such as crisp pasted text on a blurry background.
4. **Ledger matching:** compares the reference number against the seller's incoming transaction log (SMS/email alerts, or a mock ledger in the prototype).
5. **Verdict:**

| Status | Meaning |
|---|---|
| VERIFIED | Valid format and matching reference number found. Approved for packing. |
| PENDING MATCH | Valid format, but the reference number hasn't appeared in the logs yet. |
| SUSPECTED FAKE | Font misalignment, invalid reference format, or duplicate reference number. |

## Unique feature: order-bound payments

Most checkers ask "is this receipt real?". Checkiz also asks "was this payment made for *this order*?"

1. The seller makes a QR Ph for each order with a fixed amount and a free centavo code (for example PHP 150.37), so every open order has a different amount.
2. When the matching payment alert arrives, **the order settles itself. The buyer doesn't need to send a screenshot, and the seller doesn't need to open the wallet app.** The live order board and the stream overlay show it as paid.
3. If a buyer does send a receipt, its amount must equal the amount issued for that order. A genuine receipt from another order, or from a different payment, can't be reused, and one payment can only settle one order.

This works with ordinary personal-wallet transfers, so no business registration or gateway is needed. Its limits: amount matching only covers orders made through Checkiz's QR, the wallet may ignore the reference label (the centavo code is the fallback), and an unrelated payment that happens to equal an open order's exact amount within the 24-hour window would match it (the window is `CHECKIZ_ORDER_TTL_HOURS`).

## Features

- **Order-bound auto-settlement:** described above.
- **Trust-aware alert feed:** wallet-app notifications (hardest to fake), SMS, or pasted inbox text. SMS sender IDs can be spoofed, so large payments seen only by SMS are flagged "confirm in the app". Alerts without a reference number are accepted. Outgoing alerts are ignored.
- **Anti-Canva forensic engine:** compression and sharpness analysis on the Amount and Reference Number fields.
- **Anti-replay protection:** every settled reference is locked to one order.
- **Live order board and stream overlay:** open and paid orders, plus an OBS/web widget with real-time verdicts.
- **QR Ph reference generator:** QR codes with a fixed amount and Order ID.

## How it compares

Checkiz is a cheap, low-friction first check. It is not better than the options below overall, and it does not replace them.

| Option | What it is good at | Where Checkiz differs |
|---|---|---|
| Checking the wallet app by hand (GCash's own advice: confirm the reference number, sender, amount, and time in Transactions) | The most reliable check there is | Too slow to do for every order in a live stream. Checkiz automates the same check from the alert feed and still tells you to confirm large SMS-only payments in the app. |
| Licensed payment gateways (for example HitPay, PayMongo) | Confirmation comes from the payment system itself, which Checkiz can't match | Gateways need business verification and checkout changes for buyers. Checkiz works with normal personal-wallet transfers. Fees vary by provider, so check their current pricing pages. |
| Receipt-checking tools | Not assessed: I only found none in two quick searches, which doesn't prove none exist | Checkiz's difference is order binding and screenshot-free settlement, not that it reads receipts. |

## Why OCR and image analysis

Buyers already send screenshots, so reading them is the only way to support the habit sellers have today. OCR extracts the reference and amount, and the forensic check is a secondary signal. The ledger match is the strongest signal and is never overridden by the forensic check. The order-bound settlement path uses no image analysis at all.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React / Next.js or Flutter |
| Backend | Node.js (Express) or Python (FastAPI) |
| OCR / Vision | Tesseract, Google Cloud Vision, or OpenAI Vision |
| Image analysis | OpenCV |
| Database | Firebase, Supabase, or SQLite |

## Getting Started (Prototype)

This repo is an initial prototype. It runs end to end on a mock ledger, but forensic thresholds are untuned and the font check is not built yet. Verdict logic, settlement and alert parsing have tests; the phone forwarders and wallet behavior have not been tried on a real device.

```bash
# 1. Install Tesseract (Ubuntu: sudo apt install tesseract-ocr | macOS: brew install tesseract | Windows: UB-Mannheim build, add to PATH)

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed.py            # seeds the mock ledger
python make_samples.py    # writes synthetic samples/real.png and samples/edited.png
uvicorn app.main:app --reload

# 3. Frontend (new terminal)
cd frontend
python -m http.server 3000   # open http://localhost:3000
```

Run the tests with `cd backend && pytest` (the verdict engine is tested with stubbed OCR).

**Extras in the prototype**
- `GET /history` and a dashboard table log every verdict (receipt images are never stored, only the extracted fields and verdict).
- `frontend/overlay.html` is an OBS Browser Source that shows the latest verdict on stream (`?api=` and `?key=` are optional).
- **Late SMS handling.** A valid receipt with no ledger match is held as PENDING MATCH (`GET /pending`). When the matching SMS arrives at `/ledger/sms`, the order is settled automatically (VERIFIED, or SUSPECTED FAKE on an amount mismatch) and shows up in the history and overlay.
- **Threshold tuning.** `python calibrate.py --real <folder> --edited <folder>` prints ELA and sharpness for your own screenshots and suggests thresholds if the groups separate.
- **QR Ph order references** (`frontend/qr.html`, `docs/QR_PH.md`). Register your own wallet QR once, then generate a one-order QR with a fixed amount and the order ID as the reference label, plus an optional centavo code so each open order has a unique amount. A receipt whose coded amount was issued for a different order gets a warning. Receipts can also be captured with the device camera (the QR page can scan your QR the same way).
- **Timing and stats.** Each verdict reports `elapsed_ms`, and `GET /stats` (shown on the dashboard) gives counts per verdict and average time, so you can report real numbers against the under-5-seconds target.
- **Alert feed.** See `docs/SMS_FORWARDING.md`, `tools/termux_notification_forwarder.sh` (reads the wallet app's own notification) and `tools/termux_sms_forwarder.sh`. Both scripts are untested on a device. Extra env vars: `CHECKIZ_ORDER_TTL_HOURS` (24), `CHECKIZ_CONFIRM_ABOVE` (2000), `CHECKIZ_APP_PACKAGES`.
- **Docker.** `docker build -t checkiz . && docker run -p 8000:8000 checkiz` runs the backend with Tesseract and a seeded ledger (untested here).
- Uploads must be images and are capped in size.
- Set `CHECKIZ_API_KEY` (strongly recommended, since the alert endpoints decide what counts as paid) to lock `/ledger`, `/ledger/*`, `/orders` and `/history` (send `X-API-Key`; the dashboard has a key field). Optional env vars: `CHECKIZ_ELA_THRESHOLD`, `CHECKIZ_SHARPNESS_THRESHOLD`, `CHECKIZ_REF_LENGTH` (default 13), `CHECKIZ_API_KEY` and `CHECKIZ_MAX_UPLOAD_MB` (default 8). See `docs/` for the blueprint and the step-by-step implementation guide.

## Demo Scenarios

| Scenario | Input | Expected Output |
|---|---|---|
| Real transaction | Unedited GCash receipt | PAYMENT VERIFIED: Ref # 1002 8491 3049 matched with incoming balance of 1,250.00 PHP. |
| Canva/Photoshop scam | Edited amount or reference number | ALERT: SUSPECTED FRAUD. Font inconsistency on Amount field; reference number not found in ledger. |
| Replay attack | Same valid receipt uploaded twice | ALERT: DUPLICATE RECEIPT. Ref # 1002 8491 3049 already claimed on Order #104. |
| Screenshot-free payment | Buyer pays the exact coded amount of Order #105; no screenshot sent | Auto-settled: payment of 150.37 matches the amount issued for Order #105. |
| Receipt reused on another order | Real receipt for Order #105 submitted for Order #106 | SUSPECTED FAKE or DUPLICATE: the amount and payment belong to a different order. |

Demo order note: upload `edited.png` before `real.png`, because the edited copy shares the real receipt's reference number and would otherwise be reported as a duplicate.

## Roadmap

- [x] Receipt upload and OCR extraction
- [x] Reference number validation
- [x] Mock ledger and duplicate detection
- [x] Compression check (ELA and sharpness)
- [ ] Font check and threshold tuning on real samples
- [x] Seller dashboard (basic)
- [x] Order-bound auto-settlement and live order board
- [~] Alert feed: SMS, wallet-app notification and paste endpoints with trust levels (Termux scripts untested on a device; no native app yet)
- [x] OBS overlay (basic browser source: `frontend/overlay.html`)
- [~] QR Ph order-reference generator (built on the EMVCo format; wallet behaviour with the order reference is untested)
- [ ] Messenger / Viber integration

## Limitations

- **The ledger is only as good as the alert feed.** GCash has changed how it sends confirmations before (a 2024 report said it would move them from SMS to the in-app inbox), and scammers have faked messages under GCash's sender ID. Check what your phone receives today. Checkiz therefore accepts wallet-app notifications and pasted inbox text, marks SMS-only entries as lower trust, and asks for an in-app check on large ones. It does not make a spoofed SMS impossible, so confirm big orders in the app.
- Forensic detection is probabilistic and its thresholds are untuned; treat flags as signals, not guarantees.
- Auto-settlement relies on amounts being unique per open order, so it only covers orders made through Checkiz's QR page.
- Notification-reading and wallet behavior with QR Ph order references are untested on real devices.
- Receipt layouts and alert wording change when GCash/Maya update their apps, so parsers need maintenance.
- Checkiz is a triage layer, not proof of funds. It does not replace confirming in the wallet app or using a licensed gateway.

## License

MIT (change if needed).

Checkiz is an independent project and is not affiliated with GCash, Maya, or any other e-wallet provider.
