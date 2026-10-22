# checkiz
Fake payment receipt detector for social commerce seller. Combines OCR, image forensics, and ledger matching to catch edited and reused screenshots from GCash, Maya, and bank transfers.

Automated fake-receipt detection for Filipino social commerce sellers.

Checkiz sits between a buyer's payment submission and the seller's order fulfillment. It reads an uploaded GCash/Maya receipt, checks the image for tampering, and matches the reference number against the seller's incoming transaction log.

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

## Features

- **Anti-Canva forensic engine:** font, spacing, and compression analysis on the Amount and Reference Number fields.
- **SMS/notification sync:** parses incoming e-wallet alerts into a local ledger, so sellers don't need to open GCash/Maya during a stream.
- **Anti-replay protection:** stores every processed reference number and flags reuse.
- **Live-stream overlay:** OBS/web widget showing real-time verification alerts.
- **QR Ph reference generator:** fee-free QR codes embedded with an Order ID for automatic matching.

## Comparison With Existing Options

| Option | Flaws | Checkiz |
|---|---|---|
| Manual in-app checking | Slow, session timeouts, app lag, human error | Automatic matching against the ledger |
| Payment gateways (PayMongo, Maya Checkout, Xendit) | Business documents required, 2% to 3.5%+ fees, buyer friction | No gateway fees; buyers pay as usual |
| Generic OCR / metadata checkers | Messenger/Viber strip EXIF; can't detect edits or confirm funds | OCR, forensics, ledger matching, duplicate detection |

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React / Next.js or Flutter |
| Backend | Node.js (Express) or Python (FastAPI) |
| OCR / Vision | Tesseract, Google Cloud Vision, or OpenAI Vision |
| Image analysis | OpenCV |
| Database | Firebase, Supabase, or SQLite |

## Getting Started

Commands below are placeholders; adjust to your setup.

```bash
git clone https://github.com/<your-username>/checkiz.git
cd checkiz

# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd ../frontend
npm install
npm run dev
```

`.env` (backend):

```env
OCR_PROVIDER=tesseract        # tesseract | google | openai
VISION_API_KEY=your_key_here  # cloud providers only
DATABASE_URL=sqlite:///checkiz.db
```

## Demo Scenarios

| Scenario | Input | Expected Output |
|---|---|---|
| Real transaction | Unedited GCash receipt | PAYMENT VERIFIED: Ref # 1002 8491 3049 matched with incoming balance of 1,250.00 PHP. |
| Canva/Photoshop scam | Edited amount or reference number | ALERT: SUSPECTED FRAUD. Font inconsistency on Amount field; reference number not found in ledger. |
| Replay attack | Same valid receipt uploaded twice | ALERT: DUPLICATE RECEIPT. Ref # 1002 8491 3049 already claimed on Order #104. |

## Roadmap

- [ ] Receipt upload and OCR extraction
- [ ] Reference number validation
- [ ] Mock ledger and duplicate detection
- [ ] Font and compression checks
- [ ] Seller dashboard
- [ ] SMS/notification sync
- [ ] OBS overlay
- [ ] QR Ph generator
- [ ] Messenger / Viber integration

## Limitations

- Forensic detection is probabilistic; treat flags as strong signals, not guarantees.
- Delayed transaction notifications show as PENDING MATCH.
- Receipt layouts change when GCash/Maya update their apps, so reference profiles need maintenance.
- The prototype uses a mock ledger; real SMS access requires platform permissions and user consent.

## License

MIT (change if needed).

Checkiz is an independent project and is not affiliated with GCash, Maya, or any other e-wallet provider.
