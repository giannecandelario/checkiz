# Checkiz Blueprint

Design document for Checkiz: a fake-receipt detection filter for Filipino social commerce sellers.

## 1. Overview

Buyers on TikTok Live, Facebook, Instagram, and Viber send screenshots as proof of GCash/Maya payment. Some of these are forged with Canva or Photoshop. Sellers can't verify every receipt at live-stream speed, so they ship goods that were never paid for.

Checkiz verifies a receipt in three independent ways and returns one verdict:

1. **Structure:** is the reference number well formed?
2. **Image integrity:** do the key fields look edited?
3. **Ledger:** did the money actually arrive, and has this receipt been used before?

The ledger check is the strongest signal. Image forensics supports it but is probabilistic.

## 2. Goals and Non-Goals

**Goals**
- Return a verdict in a few seconds per receipt.
- Work with normal P2P payments (GCash, Maya, QR Ph) and no gateway fees.
- Catch edited amounts, edited reference numbers, and reused receipts.
- Run as a self-hosted web app for the hackathon prototype.

**Non-goals (prototype)**
- Direct integration with GCash/Maya (no public API for micro-sellers).
- Chargeback handling or dispute management.
- Guaranteed detection of every forgery.
- Multi-seller SaaS, billing, or user accounts.

## 3. Users

| User | Need |
|---|---|
| Solo seller / live host | Know instantly whether a payment is real without leaving the stream |
| Packing assistant | A clear go / no-go signal per order |
| Buyer | Fast confirmation that the payment was received |

## 4. Architecture

```
              +-------------------+
 Buyer -----> |  Upload endpoint  |
 (web/Msgr/   +---------+---------+
  Viber)                |
                        v
              +-------------------+
              |   OCR + parsing   |  amount, ref no., date, recipient
              +---------+---------+
                        |
          +-------------+--------------+
          v                            v
 +-------------------+       +--------------------+
 | Forensics (OpenCV)|       |   Ledger matcher   | <---- SMS / notification
 | ELA, sharpness    |       |   ref + amount     |       listener (seller phone)
 +---------+---------+       +----------+---------+
           |                            |
           +-------------+--------------+
                         v
              +-------------------+
              |  Verdict engine   |  + duplicate check (claims table)
              +---------+---------+
                        v
              Seller dashboard / OBS overlay
```

## 5. Components

| Component | Responsibility | Prototype tech |
|---|---|---|
| Upload API | Accepts image and order ID | FastAPI |
| OCR + parser | Extracts text, locates field boxes, validates formats | Tesseract (pytesseract) |
| Forensics | Error level analysis and sharpness checks on field regions | OpenCV, NumPy |
| Ledger store | Incoming transactions parsed from SMS alerts | SQLite |
| Claims store | Reference numbers already used for an order | SQLite |
| Verdict engine | Combines all signals into one status | Python |
| Dashboard | Upload, verdict banner, ledger view | Static HTML + JS |
| SMS sync (later) | Forwards incoming alerts to the ledger | Android app or SMS forwarder |
| OBS overlay (later) | Shows verdicts on stream | Browser source page |

## 6. Data Model

**ledger**

| Column | Type | Notes |
|---|---|---|
| ref | TEXT, primary key | 13 digits, no spaces |
| amount | REAL | In PHP |
| received_at | TEXT | ISO 8601 |
| sender | TEXT | From the SMS text, if present |
| raw | TEXT | Original SMS text |

**claims**

| Column | Type | Notes |
|---|---|---|
| ref | TEXT, primary key | Reference number already used |
| order_id | TEXT | Order that claimed it |
| claimed_at | TEXT | ISO 8601 |

## 7. Verdict Logic

Evaluated in order; the first matching rule wins.

| # | Condition | Status |
|---|---|---|
| 1 | Reference number missing or not 13 digits | SUSPECTED_FAKE |
| 2 | Reference already in `claims` | DUPLICATE |
| 3 | Reference in ledger but amount differs | SUSPECTED_FAKE |
| 4 | Forensic score above threshold | SUSPECTED_FAKE |
| 5 | Reference and amount match ledger | VERIFIED (write to `claims`) |
| 6 | Otherwise | PENDING_MATCH |

Rule 4 runs after the ledger amount check so that a ledger match is never overridden silently by a noisy image heuristic: if forensics flags an image that also matches the ledger, the response should include the flag as a warning. Decide which policy you want and keep it consistent.

## 8. Forensic Checks

| Check | What it detects | Method |
|---|---|---|
| Error level analysis (ELA) | Regions saved at a different compression level than the rest of the image | Re-encode as JPEG, compare per-pixel difference in field boxes against the whole image |
| Sharpness ratio | Crisp pasted text over a blurrier background | Laplacian variance of field boxes vs surrounding area |
| Format validation | Wrong reference length or impossible amount | Regex and range checks |

Known limits: screenshots are re-compressed by Messenger/Viber, which weakens ELA. Treat the forensic score as a flag for manual review, and tune thresholds on real samples.

## 9. API

| Method | Path | Purpose |
|---|---|---|
| POST | `/verify` | Multipart: `file`, `order_id`. Returns verdict JSON |
| POST | `/ledger/sms` | Body: `{"text": "<sms text>"}`. Parses and stores a transaction |
| GET | `/ledger` | Lists ledger entries (demo/debug) |
| GET | `/health` | Liveness check |

`/verify` response:

```json
{
  "status": "VERIFIED",
  "message": "Ref 1002849130490 matched incoming payment of 1250.00",
  "fields": {"amount": 1250.0, "ref": "1002849130490"},
  "forensic_score": 1.1,
  "order_id": "104"
}
```

## 10. Privacy and Security

- Store only what matching needs: reference number, amount, timestamp, sender name.
- Do not store buyer receipt images beyond processing, or set a short retention period.
- SMS access requires explicit user consent and platform permissions.
- Restrict `/ledger` and `/ledger/sms` with an API key before any real deployment.
- Never store PINs or e-wallet credentials. Checkiz never needs them.

## 11. Scope

**MVP (one day)**
- Upload and OCR extraction
- Reference validation
- Ledger matching with seeded and pasted SMS data
- Duplicate detection
- ELA and sharpness flagging
- Dashboard with verdict banners

**Later**
- Android SMS forwarder
- OBS overlay
- QR Ph dynamic reference generator
- Messenger / Viber bot
- Multi-seller accounts
- Trained classifier for GCash/Maya layout tampering

## 12. Success Metrics

| Metric | Target for demo |
|---|---|
| Time to verdict | Under 5 seconds |
| Real receipts verified | Majority of a small test set |
| Edited receipts flagged | Majority of a small test set |
| Duplicate receipts caught | All |

Measure on your own test set and report the real numbers. Avoid claiming absolute rates.

## 13. Risks

| Risk | Mitigation |
|---|---|
| E-wallets change receipt layouts | Keep layout rules in config; retest on new screenshots |
| SMS formats differ between GCash and Maya | Separate parser per provider with tests |
| Heuristics give false positives | Use PENDING/flag states and let the seller decide |
| Delayed SMS causes legitimate receipts to show pending | Re-check pending orders periodically |
| Sensitive data exposure | Minimal storage, consent, access control |
