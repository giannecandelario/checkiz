# Checkiz

Order-bound payment checking for Filipino online sellers.

**Target user:** small online sellers (MSMEs) on TikTok Live, Facebook, and Viber who get paid by personal wallet or personal bank account - GCash, Maya, ShopeePay, a bank app - with no payment gateway and no one to watch the apps during a rush.

Checkiz does two things. It settles orders straight from the seller's own payment alerts, and it checks receipt screenshots for the buyers who still send them. It sits between a buyer's payment submission and the seller's order fulfillment. It reads an uploaded payment receipt, checks the image for tampering, and matches the reference number against the seller's incoming transaction log. It is not tied to one wallet, because it keys on what every payment produces: a reference number and an amount.

## The Problem

Sellers on TikTok Live, Facebook, Instagram, and Viber are targeted by the "Canva scam": buyers use Canva or Photoshop templates to fake payment receipts - GCash and Maya are the usual forgeries because that is where the money moves - editing the amount, timestamp, and reference number. During a live stream, orders arrive faster than a seller can open an app and read a reference number for each one, so they ship against proof they never actually verified and lose both inventory and shipping fees.

This is not a hypothetical. GCash itself has warned about AI-generated fake receipt screenshots and tells payees to confirm a payment in the app's Transactions tab instead of trusting an image the sender sent ([Mynt newsroom, Jul 2025](https://mynt.com.ph/newsroom/gcash-warns-public-on-emerging-ai-generated-fake-receipts-scams-urges-users-to-always-check-transactions-tab)). Online selling fraud big enough to make the news is still happening in this market - police reported a ₱1.4 million online tire scam suspect in October 2026 ([Tribune](https://tribune.net.ph/2026-10-16/p14-m-online-tire-scam-suspect-collared)), though that report is about the sale, not specifically a forged receipt.

## How It Works

1. **Ingestion:** the buyer uploads a screenshot through the web page in this repo. Messenger and Viber delivery is on the roadmap, not built.
2. **OCR and parsing:** extracts amount, reference number, timestamp, and recipient.
3. **Tampering analysis:**
   - Compression check (built): error-level analysis and local sharpness on the Amount and Reference Number fields.
   - Font check (not built): would compare font family, size, and kerning against the receipt screen of the app the seller actually uses - which is the reason it is not built yet, since that differs per provider.
4. **Ledger matching:** compares the reference number against the seller's incoming transaction log (SMS/email alerts, or a mock ledger in the prototype).
5. **Verdict:**

| Status | Meaning |
|---|---|
| VERIFIED | Valid format and matching reference number found. Approved for packing. |
| PENDING MATCH | Valid format, but the reference number hasn't appeared in the logs yet. |
| SUSPECTED FAKE | Invalid reference format, an amount that disagrees with the matched alert, or a forensic flag with no payment behind it. |
| DUPLICATE | This reference number already settled another order. |

The forensic check alone never produces SUSPECTED FAKE when a payment matches the ledger; a flagged image on a matched payment becomes a warning instead, because a confirmed transfer is stronger evidence than an image score.

## Order-bound payments

The obvious question is "is this receipt real?". Checkiz also asks "was this payment made for *this order*?"

1. The seller makes a QR Ph for each order with a fixed amount and a free centavo code (for example PHP 150.37), so every open order has a different amount.
2. When the matching payment alert arrives, **the order settles itself. The buyer doesn't need to send a screenshot, and the seller doesn't need to open the wallet app.** The live order board and the stream overlay show it as paid.
3. If a buyer does send a receipt, its amount must equal the amount issued for that order. A genuine receipt from another order, or from a different payment, can't be reused, and one payment can only settle one order.

This works with ordinary personal transfers, so no business registration or gateway is needed. Its limits: amount matching only covers orders made through Checkiz's QR, the receiving app may ignore the reference label (the centavo code is the fallback), and an unrelated payment that happens to equal an open order's exact amount within the 24-hour window would match it (the window is `CHECKIZ_ORDER_TTL_HOURS`).

## Not tied to one wallet

A small seller's money arrives through GCash, Maya, ShopeePay, a bank app, or a plain bank transfer, often two or three of those on the same day. Checkiz models none of them specifically. It keys on what every payment produces: a reference number and an amount.

| Part | Why it is not provider-specific |
|---|---|
| Ledger reconciliation | Entries are keyed by reference number, then settled by comparing the amount. No provider name appears anywhere in that path. |
| Alert intake | Three sources in trust order: app notification, SMS, pasted text. Which apps count as trusted is an env var (`CHECKIZ_APP_PACKAGES`), so adding a bank app is a package name, not a code change. |
| Order binding | QR Ph is the national standard supervised by the BSP, and one QR Ph is payable from both bank and e-money accounts ([PayMongo's QR Ph doc](https://docs.paymongo.com/docs/payment-acceptance-qr-ph), [QR Ph on Wikipedia](https://en.wikipedia.org/wiki/QR_Ph)). The coded amount lives in the shared EMVCo payload, not in a wallet's own feature. |
| Receipt reference | The digit count the parser searches for is built from `CHECKIZ_REF_LENGTH` (default 13), not hard-coded ([backend/app/parser.py:9](backend/app/parser.py#L9)). |

What *is* coupled, and what an added provider would actually need:

- **Currency formatting.** Both parsers need a currency token and two decimals: the alert parser accepts `PHP` / `₱` / `PhP` ([backend/app/ledger.py:6](backend/app/ledger.py#L6)), the receipt parser also a bare `P` ([backend/app/parser.py:8](backend/app/parser.py#L8)). An amount written `1,250` with no symbol and no cents parses as nothing.
- **English alert wording.** Text only counts as money-in when it matches `received|credited|money in|you got` ([backend/app/ledger.py:9](backend/app/ledger.py#L9)). Bank SMS phrase this differently often enough to need per-provider tests.
- **The `Ref` label.** A reference number is only read after `Ref` / `Reference No` / `Ref. #` ([backend/app/ledger.py:7](backend/app/ledger.py#L7)). Without it the entry gets a synthetic hash key, which still matches on amount but can no longer be checked for replay.

And nothing here has been validated against a second provider: every measured number in this README came from a synthetic GCash-style receipt, and the QR payload was written from the general EMVCo spec without the BSP book or a real bank QR ([docs/QR_PH.md](docs/QR_PH.md) says the same). "Not tied to one wallet" describes the design, not a tested multi-bank capability.

## After the stream: the review list

The seller's job is not to check every order. It is to check the few Checkiz could not decide on.

`GET /review` merges everything still needing a person into one list, and the dashboard puts it at the top:

| Reason | What it means |
|---|---|
| SUSPECTED FAKE | Bad reference format, an amount that disagrees with the ledger, or an image the forensic check flagged with no matching payment. |
| DUPLICATE | This reference number already settled another order. |
| PENDING MATCH | A receipt arrived, but no matching payment alert yet. |
| CONFIRM IN APP | Paid, but the only evidence is a source a texter could spoof (SMS or pasted text) and the amount is at or above `CHECKIZ_CONFIRM_ABOVE`. |
| NEVER PAID | A QR was issued for the order and nothing matched it inside `CHECKIZ_ORDER_TTL_HOURS`. |

Marking an order reviewed takes it off the list. A newer verdict for the same order puts it back, so reviewing is never a way to hide a problem.

Two reports for the packing shift:

- `GET /orders/packing.csv` - paid orders as a checklist. A row still waiting on an in-app confirmation is printed with `confirm_in_app=YES`, so a printed list cannot hide an unsettled risk.
- `GET /orders/{id}/evidence` - the timestamped record for one order: the QR issued, the alert that settled it and which source it came from, every verdict, and when it was reviewed. This is what a dispute is argued with.

## Features

- **Order-bound auto-settlement:** described above.
- **Trust-aware alert feed:** wallet-app notifications (hardest to fake), SMS, or pasted inbox text. SMS sender IDs can be spoofed, so large payments seen only by SMS are flagged "confirm in the app". Alerts without a reference number are accepted. Outgoing alerts are ignored.
- **Anti-Canva forensic engine:** compression and sharpness analysis on the Amount and Reference Number fields.
- **Anti-replay protection:** every settled reference is locked to one order.
- **Reconciliation review list:** the exceptions, in one queue, with a per-order evidence trail and a packing-list export.
- **Live order board and stream overlay:** open and paid orders, plus an OBS/web widget with real-time verdicts and a running count of orders still needing review.
- **QR Ph reference generator:** QR codes with a fixed amount and Order ID.

## How it compares

Checkiz is a cheap, low-friction first check. It is not better than the options below overall, and it does not replace them.

| Option | What it is good at | Where Checkiz differs |
|---|---|---|
| Checking the wallet app by hand ([GCash's own advice: confirm in the Transactions tab](https://mynt.com.ph/newsroom/gcash-warns-public-on-emerging-ai-generated-fake-receipts-scams-urges-users-to-always-check-transactions-tab)) | The most reliable check there is | Too slow to do for every order in a live stream. Checkiz automates the same check from the alert feed and still tells you to confirm large SMS-only payments in the app. |
| Licensed payment gateways (for example [HitPay](https://hitpayapp.com/ph/), [PayMongo](https://www.paymongo.com/)) | Confirmation comes from the payment system itself, which Checkiz can't match ([HitPay's payment flow](https://docs.hitpayapp.com/apis/guide/online-payments), [PayMongo webhooks](https://docs.paymongo.com/docs/webhooks)) | Gateways need business verification and checkout changes for buyers. Checkiz works with normal personal-wallet transfers. Fees vary by provider, so check their current pricing pages. |
| Receipt-checking tools | Not assessed: I only found none in two quick searches, which doesn't prove none exist | Checkiz's difference is order binding and screenshot-free settlement, not that it reads receipts. |

Adjacent to all of these are order-management apps for social sellers ([BigSeller](https://www.bigseller.com/en_US/index.htm), [EasyStore](https://www.easystore.co/en-ph), [Prosperna](https://www.prosperna.com/)), which handle listings, stock, and shipping across channels. I did not verify whether any of them reconcile personal-wallet payments against orders, so treat that as a gap in this comparison rather than a claim that they don't.

## Why OCR and image analysis

Buyers already send screenshots, so reading them is the only way to support the habit sellers have today. OCR extracts the reference and amount, and the forensic check is a secondary signal. The ledger match is the strongest signal and is never overridden by the forensic check. The order-bound settlement path uses no image analysis at all.

## Tech Stack

As built, not as wished for:

| Layer | Technology |
|---|---|
| Frontend | Static HTML/JS dashboard, OBS overlay and QR page - no framework, no build step |
| Backend | Python 3.10+, FastAPI |
| OCR | Tesseract via pytesseract (cloud vision is not used) |
| Image analysis | OpenCV (error-level analysis and Laplacian sharpness) |
| Database | SQLite, one file |
| Packaging | Dockerfile with Tesseract installed |

No React, no Firebase, no cloud vision. Keeping it to Python, one SQLite file and a browser is what lets a seller run it on a spare laptop or a phone in Termux.

## Getting Started (Prototype)

This repo is an initial prototype. **Verified on this machine:** the backend suite passes on Python 3.12 (43 tests, `cd backend && pytest`, with OCR stubbed so Tesseract is not needed for the tests), and the Docker image runs end to end with real Tesseract - `samples/edited.png` reads as 9250.00 and returns SUSPECTED FAKE on the ledger mismatch. See Measured results. **Not verified:** the forensic thresholds (untuned, and they do not separate the shipped sample pair), the font check (not built), and anything needing a real phone - the Termux forwarders, the wallet's behaviour with a dynamic QR, and the alert wording the parser expects.

Requires Python 3.10 or newer and Tesseract on the machine running the backend.

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
# From a phone on the same network, point it at the server instead of localhost:
#   http://<computer-ip>:3000/?api=http://<computer-ip>:8000
```

Run the tests with `cd backend && pytest` (the verdict engine is tested with stubbed OCR).

**Extras in the prototype**
- `GET /history` and a dashboard table log every verdict (receipt images are never stored, only the extracted fields and verdict).
- `frontend/overlay.html` is an OBS Browser Source that shows the latest verdict on stream (`?api=` and `?key=` are optional).
- **Reconciliation endpoints.** `GET /review`, `POST /review/{order_id}` (acknowledge), `GET /orders/packing.csv` and `GET /orders/{order_id}/evidence`, all behind the same API key as the rest.
- **Late SMS handling.** A valid receipt with no ledger match is held as PENDING MATCH (`GET /pending`). When the matching SMS arrives at `/ledger/sms`, the order is settled automatically (VERIFIED, or SUSPECTED FAKE on an amount mismatch) and shows up in the history and overlay.
- **Threshold tuning.** `python calibrate.py --real <folder> --edited <folder>` prints ELA and sharpness for your own screenshots and suggests thresholds if the groups separate.
- **QR Ph order references** (`frontend/qr.html`, `docs/QR_PH.md`). Register your own wallet QR once, then generate a one-order QR with a fixed amount and the order ID as the reference label, plus an optional centavo code so each open order has a unique amount. A receipt whose coded amount was issued for a different order gets a warning. Receipts can also be captured with the device camera (the QR page can scan your QR the same way).
- **Timing and stats.** Each verdict reports `elapsed_ms`, and `GET /stats` (shown on the dashboard) gives counts per verdict and average time, so you can report real numbers against the under-5-seconds target.
- **Alert feed.** See `docs/SMS_FORWARDING.md`, `tools/termux_notification_forwarder.sh` (reads the wallet app's own notification) and `tools/termux_sms_forwarder.sh`. Both scripts are untested on a device. Extra env vars: `CHECKIZ_ORDER_TTL_HOURS` (24), `CHECKIZ_CONFIRM_ABOVE` (2000), `CHECKIZ_APP_PACKAGES`.
- **Docker.** `docker build -t checkiz . && docker run -p 8000:8000 checkiz` runs the backend with Tesseract and a seeded ledger. This path is the one used for the Measured results above.
- Uploads must be images and are capped in size.
- Set `CHECKIZ_API_KEY` (strongly recommended, since the alert endpoints decide what counts as paid) to lock `/ledger`, `/ledger/*`, `/orders` and `/history` (send `X-API-Key`; the dashboard has a key field). Optional env vars: `CHECKIZ_ELA_THRESHOLD`, `CHECKIZ_SHARPNESS_THRESHOLD`, `CHECKIZ_REF_LENGTH` (default 13), `CHECKIZ_API_KEY` and `CHECKIZ_MAX_UPLOAD_MB` (default 8). See `docs/` for the blueprint and the step-by-step implementation guide.

## Demo Scenarios

| Scenario | Input | Expected Output |
|---|---|---|
| Real transaction | Unedited GCash receipt | PAYMENT VERIFIED: Ref # 1002 8491 3049 matched with incoming balance of 1,250.00 PHP. |
| Canva/Photoshop scam | Edited amount (`samples/edited.png`) | SUSPECTED FAKE: "Amount mismatch: receipt 9250.00, ledger 1250.00". Caught by the ledger, not by the image check - see the measured results below. |
| Edited reference number | A plausible 13-digit reference that never appeared in an alert | PENDING MATCH, not a fake verdict: nothing in the ledger contradicts it. This is the case the prototype does not catch. |
| Replay attack | Same valid receipt uploaded twice | ALERT: DUPLICATE RECEIPT. Ref # 1002 8491 3049 already claimed on Order #104. |
| Screenshot-free payment | Buyer pays the exact coded amount of Order #105; no screenshot sent | Auto-settled: payment of 150.37 matches the amount issued for Order #105. |
| Receipt reused on another order | Real receipt for Order #105 submitted for Order #106 | SUSPECTED FAKE or DUPLICATE: the amount and payment belong to a different order. |
| Large SMS-only payment | A 9,000 PHP alert arrives over SMS and settles its order | Auto-settled, but the order lands on the review list as CONFIRM IN APP and prints `confirm_in_app=YES` on the packing list. |
| QR never paid | Order #107's coded amount never appears in the ledger | After `CHECKIZ_ORDER_TTL_HOURS` it shows as NEVER PAID instead of silently staying open. |
| Dispute | "Did this buyer actually pay?" | `GET /orders/107/evidence` returns the issued QR, the alert that settled it and which source it came from, every verdict, and when it was reviewed. |

Demo order note: upload `edited.png` before `real.png`, because the edited copy shares the real receipt's reference number and would otherwise be reported as a duplicate.

Which rows were actually observed: the first two ran through real OCR in the Docker run in Measured results. The rest are asserted by tests in `backend/tests/` (`test_verify.py`, `test_settle.py`, `test_review.py`), which stub OCR - so the verdict logic is proven, but the alert wording those tests feed in is written by this repo, not captured from a wallet.

## Measured results

Run end to end in the Docker image with real Tesseract (the tests stub OCR, so these are not test numbers) against the pair `make_samples.py` writes, at the shipped defaults `CHECKIZ_ELA_THRESHOLD=8.0` and `CHECKIZ_SHARPNESS_THRESHOLD=6.0`:

| Sample | OCR read | ELA | Sharpness | Verdict | Time |
|---|---|---|---|---|---|
| `samples/real.png` | amount 1250.00, ref `100284913049` | 5.78 | 4.08 | VERIFIED | 582 ms |
| `samples/edited.png` | amount 9250.00, same ref | 5.82 | 4.08 | SUSPECTED FAKE | 693 ms |

Read this table honestly:

- The `edited.png` verdict came from the ledger, not the image: the receipt said 9250.00 and the matching alert said 1250.00. The forensic scores are 0.04 apart with identical sharpness, so at these thresholds **the image check contributed nothing to catching the edit**.
- Both samples are synthetic, generated by this repo. These numbers describe the demo images and are not a detection rate for real GCash/Maya screenshots.
- What this does show: OCR extraction and ledger reconciliation work end to end, and both verdicts came back well inside the 5-second target including OCR (582 ms and 693 ms on the machine used for this run).

`python calibrate.py --real <folder> --edited <folder>` prints the same scores for your own screenshots and suggests thresholds only when the two groups actually separate. Until someone runs it on real receipts, the forensic layer is a signal in the review list, not a detector.

## Roadmap

- [x] Receipt upload and OCR extraction
- [x] Reference number validation
- [x] Mock ledger and duplicate detection
- [x] Compression check (ELA and sharpness)
- [ ] Font check and threshold tuning on real samples
- [x] Seller dashboard (basic)
- [x] Order-bound auto-settlement and live order board
- [x] Reconciliation review list, packing-list export and per-order evidence log
- [~] Alert feed: SMS, wallet-app notification and paste endpoints with trust levels (Termux scripts untested on a device; no native app yet)
- [x] OBS overlay (basic browser source: `frontend/overlay.html`)
- [~] QR Ph order-reference generator (built on the EMVCo format; wallet behaviour with the order reference is untested)
- [ ] Provider parsers beyond GCash-style wording (a bank SMS feed, ShopeePay), each with its own samples and tests
- [ ] Messenger / Viber integration
- [ ] Hosted setup, so a seller is not asked to run Termux and an API key themselves
- [ ] Buyer-side payment page that shows the exact coded amount for the order
- [ ] Recording "I confirmed this in the app" as a step on the order, instead of only warning on screen

## Limitations

- **The ledger is only as good as the alert feed.** GCash moved transaction alerts from SMS to the in-app inbox in September 2022, saying the change was to reduce scam texts ([BitPinas](https://bitpinas.com/news/gcash-to-remove-text-alerts-for-each-transaction/), [Newsbytes](https://newsbytes.ph/2022-09-07/gcash-shifts-notifications-from-text-to-app-inbox-to-avoid-scam-messages/)), so which alerts a seller receives depends on their app version and device. Scammers have also sent texts under GCash's sender ID ([Inquirer Technology](https://technology.inquirer.net/139503/hindi-gcash-yan-what-is-sms-spoofing-scam-and-what-you-shoud-do-when-you-see-one)). Checkiz therefore accepts wallet-app notifications and pasted inbox text, marks SMS-only entries as lower trust, and asks for an in-app check on large ones. It does not make a spoofed SMS impossible, so confirm big orders in the app.
- **The forensic check is not yet a detector.** On the only sample pair the repo ships, its scores do not separate the real receipt from the edited one (see Measured results). Everything the prototype catches today comes from the ledger, the reference format, and duplicate/replay state. Treat the image scores as an extra column in the review list, not as a verdict.
- Forensic detection is probabilistic and its thresholds are untuned; treat flags as signals, not guarantees.
- Auto-settlement relies on amounts being unique per open order, so it only covers orders made through Checkiz's QR page.
- Notification-reading and wallet behavior with QR Ph order references are untested on real devices.
- **Only one provider's wording is exercised.** The design is provider-independent, the parsers are not: alert text and receipt layouts are matched with regexes written against GCash-style samples. Bank and ShopeePay feeds need their own parser plus tests before being claimed.
- Receipt layouts and alert wording change when any provider updates their app, so parsers need maintenance.
- Checkiz is a triage layer, not proof of funds. It does not replace confirming in the app the money arrived in - wallet or bank - or using a licensed gateway.

## Sources

Checked October 2026; only links that resolved and whose content supports the sentence they sit in are listed.

- [GCash warns public on emerging AI-generated fake receipts scams, urges users to always check Transactions tab](https://mynt.com.ph/newsroom/gcash-warns-public-on-emerging-ai-generated-fake-receipts-scams-urges-users-to-always-check-transactions-tab) - Mynt newsroom, 14 Jul 2025. The wallet provider's own guidance, which is why Checkiz defers to an in-app check instead of claiming to replace it.
- [GCash to remove text alerts for each transaction](https://bitpinas.com/news/gcash-to-remove-text-alerts-for-each-transaction/) - BitPinas, 2 Sep 2022, and [GCash shifts notifications from text to app inbox to avoid scam messages](https://newsbytes.ph/2022-09-07/gcash-shifts-notifications-from-text-to-app-inbox-to-avoid-scam-messages/) - Newsbytes, 7 Sep 2022. Why the alert feed is a trust-tiered design problem, not a solved one.
- [Hindi GCash yan: What is SMS spoofing scam](https://technology.inquirer.net/139503/hindi-gcash-yan-what-is-sms-spoofing-scam-and-what-you-shoud-do-when-you-see-one) - Inquirer Technology, 27 Dec 2024. Why SMS-only entries carry `needs_app_check`.
- [P1.4M online tire scam suspect collared](https://tribune.net.ph/2026-10-16/p14-m-online-tire-scam-suspect-collared) - Tribune, 16 Oct 2026. Online selling fraud at MSME scale is current.
- Payment-side alternatives: [HitPay PH](https://hitpayapp.com/ph/) and its [online payments guide](https://docs.hitpayapp.com/apis/guide/online-payments), [PayMongo](https://www.paymongo.com/) and its [webhooks docs](https://docs.paymongo.com/docs/webhooks).
- Why order binding is not wallet-specific: [PayMongo's QR Ph explanation](https://docs.paymongo.com/docs/payment-acceptance-qr-ph) and [QR Ph](https://en.wikipedia.org/wiki/QR_Ph) on Wikipedia - a BSP-supervised national standard payable from bank and e-money accounts alike.
- Adjacent order tooling: [BigSeller](https://www.bigseller.com/en_US/index.htm), [EasyStore PH](https://www.easystore.co/en-ph), [Prosperna](https://www.prosperna.com/).

Not used, for the record: the BSP's own [QR Ph P2P FAQ](https://www.bsp.gov.ph/Media_and_Research/Primers%20Faqs/QR_Ph_P2P_FAQs.pdf) is the right primary source but returns 403 to non-browsers, so it is cited only through the two pages above; GCash Help Center articles also 403; the PNP anti-scam advisories are Facebook-only; a PhilStar spoofing piece 404s; and an August 2026 report on Apple Pay entering the Philippines 403s, so it is not referenced. No fee percentages are quoted anywhere in this README because none could be confirmed from a primary page.

## License

MIT (change if needed).

Checkiz is an independent project and is not affiliated with GCash, Maya, ShopeePay, any bank, or any other payment provider. Those names appear only to describe where a seller's money usually comes from.
