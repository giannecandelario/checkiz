# Checkiz Blueprint

Design document for Checkiz: a payment-proof triage layer for Filipino online sellers.

## 1. Overview

Buyers on TikTok Live, Facebook, Instagram, and Viber send screenshots as proof of payment. Most of these receipts are GCash or Maya today, but nothing about the forgery is specific to them - any screenshot with an amount and a reference can be edited. Some are forged with Canva or Photoshop. Sellers can't verify every receipt at live-stream speed, so they ship goods that were never paid for.

Checkiz is deliberately not modelled on one provider. Every payment proof carries a reference number and an amount, those two fields are what the engine reconciles, and provider-specific text is meant to stay confined to the parsers.

Checkiz verifies a receipt in three independent ways and returns one verdict:

1. **Structure:** is the reference number well formed?
2. **Image integrity:** do the key fields look edited?
3. **Ledger:** did the money actually arrive, and has this receipt been used before?

The ledger check is the strongest signal. Image forensics supports it but is probabilistic.

## 2. Goals and Non-Goals

**Goals**
- Return a verdict in a few seconds per receipt.
- Work with normal personal transfers - wallet or bank, QR Ph or P2P - and no gateway fees.
- Catch edited amounts, edited reference numbers, and reused receipts.
- Run as a self-hosted web app for the hackathon prototype.

**Non-goals (prototype)**
- Direct integration with any provider's API. Nothing usable by a micro-seller is public for GCash or Maya, so the feed is built from what the seller's own phone receives instead.
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

**pending** - receipts held as PENDING_MATCH so a late alert can settle them: `ref` (primary key), `order_id`, `amount`, `created_at`.

**qr_orders** - orders issued through the QR page: `order_id` (primary key), `amount`, `coded`, `status` (OPEN/PAID), `paid_ref`, `paid_at`, `created_at`.

**verifications** - the verdict log, and the source the review list reads: `id`, `order_id`, `status`, `message`, `amount`, `ref`, `elapsed_ms`, `needs_app_check`, `created_at`.

**review_ack** - `order_id` (primary key), `acked_id`, `acked_at`. `acked_id` is the last verdict row acknowledged, so any newer verdict reopens the order.

**settings** - key/value, holds the registered seller QR payload.

Receipt images are never stored in any table.

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

Rule 4 runs after the ledger amount check so that a ledger match is never overridden silently by a noisy image heuristic. The implemented policy: when the reference and amount match the ledger, `VERIFIED` wins and the forensic flag is returned as a `warning` on the response instead of changing the verdict. A forensic flag with no ledger confirmation is `SUSPECTED_FAKE` (rule 5).

A `VERIFIED` verdict whose only evidence is a spoofable alert source (SMS or pasted text) at or above `CHECKIZ_CONFIRM_ABOVE` also carries `needs_app_check`, which is persisted on the verdict row so the reconciliation review list can surface it later.

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
| POST | `/ledger/sms` | Body: `{"text": "<alert text>", "source": "sms"\|"paste"}`. Parses and stores a transaction |
| POST | `/ledger/notification` | Body: `{"package", "title", "text"}`. Alert read from an allow-listed wallet app (highest trust) |
| POST | `/ledger/paste` | Several alerts at once, separated by a blank line. `added` counts payments the ledger did not already hold |
| POST | `/ledger/history-screenshot` | Multipart: `file` - a screenshot of the seller's **own** wallet Transactions screen. Reads it row by row into the ledger with `source="history"` (lowest trust). Returns `added`, `already_in_ledger`, `skipped` (money rows refused, with the reason and the row text) and `unmatched`. 400 when the screen placed no payment, 415 when the upload is not an image, 503 when the server has no OCR |
| GET | `/ledger` | Lists ledger entries (demo/debug) |
| GET | `/pending` | Receipts held as PENDING_MATCH, waiting for a late alert |
| GET | `/history`, `/stats` | Verdict log and per-verdict counts/timings |
| GET | `/review` | The reconciliation list: orders Checkiz could not settle |
| POST | `/review/{order_id}` | Acknowledge an order; a newer verdict reopens it |
| GET | `/orders` | Live order board (OPEN / PAID) |
| GET | `/orders/packing.csv` | Paid orders as a CSV checklist, with `confirm_in_app` |
| GET | `/orders/{order_id}/evidence` | Timestamped record for one order |
| POST | `/qr/decode`, `/qr/register`, `/qr/generate` | Register the seller's QR Ph, build a one-order QR |
| GET | `/health` | Liveness check |

Every endpoint except `/health` and `/verify` is locked when `CHECKIZ_API_KEY` is set.

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
