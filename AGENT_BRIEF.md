# Agent brief for Checkiz (read this and `README.md` first)

You are continuing work on **Checkiz**, a hackathon project (CSSPRINT 2026, MSME problem statement). The goal is a credible, honest, demonstrable product, not a bigger claim list.

## Product in one paragraph

Checkiz checks e-wallet receipts for **one user: the small Filipino online seller** who takes personal-wallet transfers (live selling, chat orders) and confirms payments by hand. **One job:** for each order, know whether it was really paid, and spot reused or mismatched receipts without opening the wallet app for every screenshot. Buyers are not users; a simple buyer pay page exists only to make exact-amount payment easy.

Verdicts: **Verified / Reused / Doesn't match / Likely edited / Can't confirm yet**. The strongest signals are (1) ledger confirmation from payment alerts the seller receives and (2) **order binding**: each order has a unique centavo-coded amount, so a payment settles one specific order without a screenshot. Image forensics is a weak, secondary signal. Do not make it the headline.

## Scope (read before anything else)

Stay on the one user and one job. **Do not build anything listed under "Deferred" below** unless the owner asks. When in doubt, choose the smaller change that makes the seller's check faster or more trustworthy. Do not add roles, accounts, staff features, lending features or new audiences.

## Ground rules

1. **Work on a feature branch** (for example continue `feat/product-hardening`). Never touch `main`. Small commits with clear messages (the commit history is evidence of what was built when). No force pushes, no history rewriting.
2. **No unverified claims.** No invented numbers, no "first/only/best" claims, no statistics without a link. If you cannot verify a claim, remove it or label it unverified. Competitor statements must cite a page you actually read.
3. **Never claim more than the code does.** Before editing README claims, read the code and tests. If a feature in `README.md` does not exist in the repo, either implement it per this brief or mark it Planned.
4. **Do not break the existing API or tests.** Add fields or endpoints instead of renaming. All tests must pass (`cd backend && pytest`).
5. **Privacy:** receipt images are not stored (only extracted fields and the verdict). Never log full alert text at INFO level. Escape or neutralise any value that came from SMS/notification text before it reaches CSV, HTML or logs. No secrets in the repo.
6. **Security defaults:** alert endpoints must require `CHECKIZ_API_KEY` when set, and the server must warn at startup if it is not set.
7. Everything user-facing is honest about uncertainty: use "Can't confirm yet", and tell the seller to confirm large payments in the wallet app.

## Step 0: reconcile (do this first)

Read the repo and write `docs/STATUS.md` listing, for each README feature, whether it exists, where, and whether a test covers it. Pay special attention to whether these exist; implement any that are missing:

- `POST /ledger/notification` (allow-listed package via `CHECKIZ_APP_PACKAGES`), `POST /ledger/paste` (blank-line separated alerts), `POST /ledger/sms` with a `source`.
- `ledger.source` and `ledger.consumed_order` columns, with migration for old databases.
- `parse_alert()`: reference optional (synthetic `NOREF-<hash>` key when absent), outgoing alerts ("sent", "paid", "cash out") rejected, incoming-only.
- Auto-settlement of an open, recent, centavo-coded order when an alert with exactly that amount arrives (`ingest_alert`), idempotent on replay.
- Receipt amount must equal the amount issued for a coded order (otherwise SUSPECTED_FAKE with a clear message). A genuine receipt for order A must not settle order B.
- `needs_app_check` for large payments not from the app source (`CHECKIZ_CONFIRM_ABOVE`), persisted on the verdict row, including the late-alert path.
- `GET /review` queue, `GET /orders/packing.csv`, `GET /orders/{id}/evidence`.
- `GET /pay/{order_id}` and `/pay/{order_id}/qr.png` (public, minimal: amount and status only) and `frontend/pay.html`.
- `backend/demo.py` scripted demo on a throwaway database.

## Tasks, in priority order

### 1. Verdict labels (small, high visibility)
Add a `label` field to every verdict response and history row, mapping existing statuses without changing them:
`VERIFIED` → "Verified"; `DUPLICATE` → "Reused"; amount or order mismatch → "Doesn't match"; forensic flag with no ledger match → "Likely edited"; `PENDING_MATCH` → "Can't confirm yet". Show the labels in the dashboard and overlay. Tests for each mapping.

### 2. Image fingerprint for reuse
Compute a perceptual hash (for example dHash with OpenCV or Pillow, no new heavy dependency) of each accepted receipt image and store only the hash. A new upload within a small Hamming distance of an accepted one is "Reused", even when OCR misreads the reference. Do not store images. Tests: same image, re-saved JPEG, mild crop, unrelated image. Document the distance threshold and its false-positive risk.

### 3. Consistency checks that don't need alerts
Pure functions with tests: reference length/format, amount format (two decimals, plausible range), timestamp plausibility (not in the future, not older than a configurable window), layout sanity against the known receipt template (config-driven, not hardcoded to one wallet). Each failed check adds a reason string. Label these as signals, not proof.

### 4. Camera capture on the main page
Let a cashier photograph a customer's phone from the main page (`<input type="file" accept="image/*" capture="environment">`, plus a live camera option if simple). Photos of screens are noisier than screenshots, so surface a "retake for a clearer photo" hint when OCR confidence is low.

### 5. Real-device test protocol and alert-feed fallback
- Write `docs/DEVICE_TEST.md`: a step-by-step protocol to send a PHP 1.00 payment and record what the phone receives (SMS, app notification, both, neither), the exact alert wording, the package name (`termux-notification-list`), and a results table to fill in. **Do not claim results you did not observe.**
- Build the fallback: `POST /ledger/history-screenshot` takes a screenshot of the **seller's own** wallet Transactions/Activity screen, OCRs rows (reference, amount, time) into the ledger with `source="history"` (trust: manual). Tests with stubbed OCR.

### 6. Calibration with real data
Do not invent numbers. Provide a script and a short guide for the team to run `calibrate.py` on genuine and edited receipts, and make the README's results table fill from real runs. Until real data exists, keep the "forensics did not separate the samples" note.

### 7. Optional AI-assisted receipt reading (gated, last priority)

**Do this only after tasks 1-6 are done or the owner has explicitly skipped them.** It is optional, off by default, and must never decide a verdict.

**Why it exists:** phone photos of screens (glare, angle, different wallet layouts) are where Tesseract is weakest. A vision model may extract reference, amount and time better. This is the "why AI is necessary" answer for judges **only if the evaluation below proves it**. If it does not help, the task ends with a documented negative result.

**Design**
- A small `ReceiptReader` interface with `TesseractReader` (default, local, free, no data leaves the device) and `VisionReader` (optional, cloud). Optionally evaluate a local open-source OCR engine (for example PaddleOCR or docTR) as another reader; they have not been evaluated yet, so measure before claiming anything. Enabled with `CHECKIZ_AI_READER=on` (default `off`). The provider API key comes from the environment, never from the repo. With the flag off, **no network call may be made** (test this).
- **Extraction only.** The model returns JSON: `reference`, `amount`, `time`, `recipient`, `wallet`, and a per-field confidence. It never returns a verdict, label or opinion about authenticity.
- **Treat model output as untrusted data.** Validate against a strict schema. Reference must match the configured length and digits only; amount must match a two-decimal pattern in a plausible range; reject anything else. Cap lengths. Never render model text as HTML and never execute it. Text inside a receipt image that looks like instructions must have no effect (the prompt says to ignore it, and validation enforces it).
- **Cross-check with Tesseract.** If both readers return a value and they **disagree** on reference or amount, the result is "Can't confirm yet: readings disagree". Show both readings to the seller. Never auto-settle, and never mark Reused, on a disputed reading.
- **Fallback.** Timeout (configurable, default a few seconds), retry at most once, then fall back to Tesseract automatically and show a visible notice "AI reading unavailable, used standard OCR". Add a daily call cap (`CHECKIZ_AI_DAILY_CAP`) and per-key rate limit. Cache by image hash, storing extracted fields only, never the image.
- **Explanations:** build the plain-language explanation of a verdict from **deterministic templates over the verdict's reason codes** first. An AI-worded explanation is optional and may only rephrase those reasons. It must not introduce new facts.

**Privacy and consent**
- Show a plain consent notice before the first AI-assisted check ("this sends your receipt photo to <provider> to read it"), make it revocable, and never enable it silently.
- Minimize what is sent: strip EXIF, downscale, and where practical send only cropped regions (amount, reference, time) instead of the whole receipt. Do not store images. Do not log image data or full model responses at INFO level.
- Provider decision (already researched; see `docs/AI_PRIVACY.md`, re-verify the dates before relying on it): **the default reader is local.** The only cloud reader to evaluate first is the Gemini API.
  - **Unpaid/free quota: test data only.** Google's terms say content on unpaid services is used to improve its products and human reviewers may read it, and they say not to submit sensitive, confidential or personal information. Use it only with synthetic receipts or the owner's own receipts. **Never send a real customer's or seller's receipt to an unpaid service.**
  - **Real user receipts: only through a Cloud project with an active billing account** (paid service: not used to improve products, processed under Google's data processing addendum, prompts and responses logged for a limited period for abuse detection, may be stored or cached transiently in any country), plus the consent flow. This is not free; check current pricing and whether free quota still applies on a billed project before deciding.
  - The Gemini terms say the service is for professional or business developers, requires users to be 18+, and says an API client must not be directed at or likely accessed by under-18s. A public buyer-upload page could be accessed by minors, so keep the AI path on the seller side.
  - Update `docs/AI_PRIVACY.md` if the provider, its terms or the plan changes. **Do not state anything about a provider's terms that you have not read.**

**Evaluation gate (required)**
- Add `eval/run_eval.py` and a labeled CSV format for a set of genuine and edited receipts that **includes phone photos of screens**. The owner supplies the real receipts; do not fabricate data or use real people's information in the repo (redact or use the owner's own test payments).
- Report, for Tesseract alone, AI alone and the combined reader: reference exact-match rate, amount exact-match rate, edits caught and missed, false alarms, failure rate, and latency (median and slow tail). Always report the **number of receipts (n)** and the date.
- Write results to `docs/AI_EVAL.md` as a table. **The README may claim only what that table shows.** If the combined reader does not beat Tesseract alone, leave the flag off, keep the code only if it is clean, and record the negative result. No AI-accuracy claim in the README in that case.

**Tests (fake reader, no network)**
- Flag off makes no network call.
- Schema violation or oversized output is rejected and falls back.
- Disagreement between readers yields "Can't confirm yet" and no settlement.
- Output containing instruction-like text, HTML or extra fields changes nothing and is not rendered.
- Timeout and provider error fall back to Tesseract and show the notice.
- Daily cap reached falls back cleanly.

**Risk register for this task**

| Risk | Prevention | If it still happens |
|---|---|---|
| Model misreads a digit | Strict format validation; Tesseract cross-check; disagreement blocks settlement and Reused | Seller sees both readings and confirms in the wallet app |
| Model gives confident but wrong judgement | It never judges: extraction only, no verdict or label from AI | Remove AI wording from any seller-facing text |
| No real benefit | Evaluation gate; flag off by default | Document negative result; no claims |
| Privacy leak of receipt data | Consent, minimization, no image storage, no payload logging, provider terms read and recorded | Disable flag; document the incident; purge caches |
| Prompt injection in image text | Untrusted output, schema validation, no tool use, no rendering | Treat as a failed extraction and fall back |
| Cost, rate limits, latency | Timeout, retry once, daily cap, hash cache | Automatic fallback to Tesseract |
| Network failure during the demo | Flag off for demo unless tested offline; rehearsed fallback; recorded backup | Demo on Tesseract path, say so honestly |
| Scope creep delays core work | Last priority; skip rule above | Owner may drop it without affecting the core |

## Deferred (do not build now)

- **Staff mode** (roles, PINs, `submitted_by`, `/reconcile/daily`): a possible second use case for stores with employees. Needs the alert feed on the owner's device and human review of flags, and it competes with counter devices.
- **Verified sales statement / credit direction:** unvalidated whether lenders would accept it.
- **Messenger / Viber intake.**
- **Freelancer-specific features.**

## Acceptance criteria

- `cd backend && pytest` passes; new behavior has tests; OCR stays stubbed in tests.
- `python backend/demo.py` runs on a clean checkout and prints honest outcomes (not asserted wins).
- Docker image builds and `/health` responds.
- README, `docs/STATUS.md` and the code agree. Every external claim has a link you opened, or is removed.
- No endpoint that decides "paid" works without the API key when `CHECKIZ_API_KEY` is set.
- CSV and HTML outputs neutralise injected values from alert text.
- No Deferred feature has been added.
- If task 7 was built: with the flag off, no network call occurs; the AI path can never approve, reject or label a receipt; `docs/AI_EVAL.md` exists with n and date, and the README claims only what it shows.

## Do not

- Do not let any AI output decide, approve, reject or label a receipt.
- Do not enable AI reading by default, or send receipt images anywhere without consent.
- Do not claim AI improves accuracy unless `docs/AI_EVAL.md` shows it.
- Do not add payment processing, hold money, or call wallet-private APIs.
- Do not claim edit detection works until real-data calibration supports it.
- Do not claim Checkiz is the first, only or best receipt checker.
- Do not rename or delete the existing tests to make them pass.
- Do not include real personal data, real receipts or real wallet numbers in the repo.

## Pitch framing (for README/docs wording)

Lead with the user and the job: *"For small online sellers who get paid by personal e-wallet: know which orders were really paid, and catch reused or mismatched receipts, without checking the app one screenshot at a time."* Then the differentiator (order binding), then honest limits (alert feed, weak edit detection, confirm big payments in the app). Stores with staff and the verified sales record appear only under "Future directions."

## Report back

When done, update `docs/STATUS.md`, list what changed, what is untested, and what still depends on a real device.
